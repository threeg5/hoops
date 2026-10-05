"""Pull NBA teams, schedules, and the injury report into SQLite.

Each game is stored once. Team form on the desk reads completed regular-season
games from this table. Live clock and score are refreshed separately.
"""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime
from zoneinfo import ZoneInfo

from hoops.config import DB_PATH, SEASONS, WNBA_DB_PATH, WNBA_SEASONS
from hoops.db import connect
from hoops.espn import fetch_injuries, fetch_schedule, fetch_teams, quiet_http_error

ET = ZoneInfo("America/New_York")

SEASON_TYPE = {
    1: "PRE",
    2: "REG",
    3: "POST",
    4: "POST",
    5: "POST",
}


def _score(value) -> int | None:
    if isinstance(value, dict):
        value = value.get("value", value.get("displayValue"))
    if value in (None, ""):
        return None
    try:
        return int(round(float(value)))
    except (TypeError, ValueError):
        return None


def _hex(value: str | None) -> str | None:
    if not value:
        return None
    text = str(value).strip()
    if not text:
        return None
    return text if text.startswith("#") else f"#{text}"


def _state(name: str) -> str:
    name = name or ""
    if "FINAL" in name:
        return "post"
    if name in {"STATUS_SCHEDULED", "STATUS_PRE"}:
        return "pre"
    return "in"


def _split_start(iso: str | None) -> tuple[str | None, str | None]:
    if not iso:
        return None, None
    try:
        dt = datetime.fromisoformat(iso.replace("Z", "+00:00"))
    except ValueError:
        return None, None
    return dt.isoformat(), dt.astimezone(ET).date().isoformat()


def parse_team(team: dict) -> dict:
    return {
        "team_id": str(team.get("id") or ""),
        "abbr": team.get("abbreviation") or "",
        "name": team.get("displayName") or team.get("name") or "",
        "city": team.get("location") or "",
        "nickname": team.get("nickname") or team.get("shortDisplayName") or "",
        "color": _hex(team.get("color")),
    }


def parse_event(event: dict) -> dict | None:
    competitions = event.get("competitions") or []
    if not competitions:
        return None
    comp = competitions[0]
    competitors = comp.get("competitors") or []
    home = next((c for c in competitors if c.get("homeAway") == "home"), None)
    away = next((c for c in competitors if c.get("homeAway") == "away"), None)
    if not home or not away:
        return None
    home_info = home.get("team") or {}
    away_info = away.get("team") or {}
    home_team = home_info.get("abbreviation")
    away_team = away_info.get("abbreviation")
    if not home_team or not away_team:
        return None
    status = comp.get("status") or {}
    status_type = status.get("type") or {}
    season = event.get("season") or {}
    season_type = event.get("seasonType") or {}
    type_num = season_type.get("type")
    start_utc, gameday = _split_start(event.get("date") or comp.get("date"))
    venue = comp.get("venue") or {}
    address = venue.get("address") or {}
    city = address.get("city") or ""
    state = address.get("state") or ""
    location = ", ".join(part for part in (city, state) if part)
    notes = comp.get("notes") or []
    note = ""
    if notes and isinstance(notes[0], dict):
        note = notes[0].get("headline") or ""
    state_name = _state(status_type.get("name") or "")
    home_score = _score(home.get("score"))
    away_score = _score(away.get("score"))
    if state_name != "post":
        home_score = home_score if state_name == "in" else None
        away_score = away_score if state_name == "in" else None
    return {
        "game_id": str(event.get("id") or comp.get("id") or ""),
        "season": season.get("year"),
        "season_label": season.get("displayName") or "",
        "season_type": SEASON_TYPE.get(type_num, "REG" if type_num == 2 else "PRE"),
        "gameday": gameday,
        "start_utc": start_utc,
        "status": state_name,
        "status_detail": status_type.get("shortDetail") or status_type.get("detail") or "",
        "period": status.get("period") or 0,
        "clock": status.get("displayClock") or "",
        "home_team": home_team,
        "away_team": away_team,
        "home_name": home_info.get("displayName") or home_team,
        "away_name": away_info.get("displayName") or away_team,
        "home_id": str(home_info.get("id") or ""),
        "away_id": str(away_info.get("id") or ""),
        "home_score": home_score,
        "away_score": away_score,
        "neutral": 1 if comp.get("neutralSite") else 0,
        "venue": venue.get("fullName") or "",
        "location": location,
        "note": note,
    }


def _load_schedules(teams: list[dict], seasons: list[int], league: str) -> tuple[dict[str, dict], list[str]]:
    games: dict[str, dict] = {}
    notes: list[str] = []
    jobs = [(team["team_id"], season) for team in teams for season in seasons]

    def pull(team_id: str, season: int):
        try:
            payload = fetch_schedule(team_id, season, league)
        except Exception as exc:
            return team_id, season, [], quiet_http_error(exc)
        parsed = []
        for event in payload.get("events") or []:
            game = parse_event(event)
            if game and game["game_id"]:
                parsed.append(game)
        return team_id, season, parsed, ""

    with ThreadPoolExecutor(max_workers=4) as pool:
        futures = [pool.submit(pull, team_id, season) for team_id, season in jobs]
        for future in as_completed(futures):
            team_id, season, parsed, error = future.result()
            if error:
                notes.append(f"team {team_id} season {season}: {error}")
                continue
            for game in parsed:
                games[game["game_id"]] = game
    return games, notes


def apply_rest(conn) -> None:
    rows = conn.execute(
        """
        SELECT game_id, gameday, home_team, away_team
        FROM games
        WHERE gameday IS NOT NULL
        ORDER BY start_utc, gameday, game_id
        """
    ).fetchall()
    last: dict[str, datetime] = {}
    updates = []
    for row in rows:
        day = datetime.strptime(row["gameday"], "%Y-%m-%d").date()

        def rest_for(abbr: str):
            prev = last.get(abbr)
            last[abbr] = day
            if prev is None:
                return None
            return max(0, (day - prev).days - 1)

        updates.append((rest_for(row["home_team"]), rest_for(row["away_team"]), row["game_id"]))
    conn.executemany(
        "UPDATE games SET home_rest = ?, away_rest = ? WHERE game_id = ?",
        updates,
    )


def store_injuries(conn, teams_by_id: dict[str, dict], league: str = "nba") -> int:
    try:
        payload = fetch_injuries(league)
    except Exception as exc:
        print(f"Injury report skipped: {quiet_http_error(exc)}", flush=True)
        return 0
    conn.execute("DELETE FROM injuries")
    count = 0
    for group in payload.get("injuries") or []:
        team_id = str(group.get("id") or "")
        team = teams_by_id.get(team_id)
        if not team:
            continue
        for item in group.get("injuries") or []:
            athlete = item.get("athlete") or {}
            name = athlete.get("displayName") or ""
            if not name:
                continue
            position = ((athlete.get("position") or {}).get("abbreviation")) or ""
            details = item.get("details") or {}
            detail = " ".join(
                part
                for part in (
                    details.get("side"),
                    details.get("location"),
                    details.get("type"),
                )
                if part
            )
            conn.execute(
                """
                INSERT OR REPLACE INTO injuries
                  (team_id, player_name, position, status, detail, comment)
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (
                    team_id,
                    name,
                    position,
                    item.get("status") or "",
                    detail,
                    item.get("shortComment") or "",
                ),
            )
            count += 1
    return count


def league_setup(league: str = "nba") -> dict:
    if league == "wnba":
        return {
            "league": "wnba",
            "name": "W-HOOPS",
            "seasons": WNBA_SEASONS,
            "db": WNBA_DB_PATH,
            "source": "ESPN WNBA scoreboard, team schedules, injury report",
        }
    return {
        "league": "nba",
        "name": "HOOPS",
        "seasons": SEASONS,
        "db": DB_PATH,
        "source": "ESPN NBA scoreboard, team schedules, injury report",
    }


def run_ingest(league: str = "nba") -> dict:
    setup = league_setup(league)
    print(f"{setup['name']} ingest: teams, seasons {setup['seasons']}, injuries", flush=True)
    raw_teams = fetch_teams(setup["league"])
    teams = [parse_team(team) for team in raw_teams if team.get("id") and team.get("abbreviation")]
    teams_by_id = {team["team_id"]: team for team in teams}
    games, notes = _load_schedules(teams, setup["seasons"], setup["league"])
    for note in notes:
        print(note, flush=True)
    known = {team["abbr"] for team in teams}
    for game in games.values():
        for abbr, name, team_id in (
            (game["home_team"], game["home_name"], game["home_id"]),
            (game["away_team"], game["away_name"], game["away_id"]),
        ):
            if abbr in known:
                continue
            teams.append(
                {
                    "team_id": team_id or abbr,
                    "abbr": abbr,
                    "name": name,
                    "city": "",
                    "nickname": name,
                    "color": None,
                }
            )
            known.add(abbr)
    teams_by_id = {team["team_id"]: team for team in teams}
    conn = connect(setup["db"])
    try:
        conn.execute("BEGIN")
        conn.execute("DELETE FROM games")
        conn.execute("DELETE FROM teams")
        conn.execute("DELETE FROM injuries")
        conn.executemany(
            """
            INSERT INTO teams (team_id, abbr, name, city, nickname, color)
            VALUES (:team_id, :abbr, :name, :city, :nickname, :color)
            """,
            teams,
        )
        conn.executemany(
            """
            INSERT INTO games (
              game_id, season, season_label, season_type, gameday, start_utc,
              status, status_detail, period, clock,
              home_team, away_team, home_id, away_id,
              home_score, away_score, neutral, venue, location, note
            ) VALUES (
              :game_id, :season, :season_label, :season_type, :gameday, :start_utc,
              :status, :status_detail, :period, :clock,
              :home_team, :away_team, :home_id, :away_id,
              :home_score, :away_score, :neutral, :venue, :location, :note
            )
            """,
            list(games.values()),
        )
        apply_rest(conn)
        injuries = store_injuries(conn, teams_by_id, setup["league"])
        now = datetime.now(ZoneInfo("UTC")).isoformat()
        conn.execute(
            "INSERT OR REPLACE INTO meta(key, value) VALUES ('ingest_complete', '1')"
        )
        conn.execute(
            "INSERT OR REPLACE INTO meta(key, value) VALUES ('ingested_at', ?)",
            (now,),
        )
        conn.execute(
            "INSERT OR REPLACE INTO meta(key, value) VALUES ('source', ?)",
            (setup["source"],),
        )
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()
    finals = sum(1 for game in games.values() if game["status"] == "post")
    result = {
        "teams": len(teams),
        "games": len(games),
        "finals": finals,
        "injuries": injuries,
        "warnings": notes,
    }
    print(f"{setup['name']} ingest finished {result}", flush=True)
    return result


if __name__ == "__main__":
    import sys

    run_ingest(sys.argv[1] if len(sys.argv) > 1 else "nba")
