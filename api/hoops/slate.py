"""Tonight's NBA slate: team form and an expected score from those numbers."""

from __future__ import annotations

from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

from hoops.config import SEASON_BODY_GAMES, TEAM_RECENT_GAMES

ET = ZoneInfo("America/New_York")
CT = ZoneInfo("America/Chicago")

SHOWN_STATUSES = ("out", "doubtful", "questionable")


def rows(conn, sql: str, params: tuple = ()) -> list[dict]:
    return [dict(row) for row in conn.execute(sql, params).fetchall()]


def one(conn, sql: str, params: tuple = ()) -> dict | None:
    found = conn.execute(sql, params).fetchone()
    return dict(found) if found else None


def _mean(values: list[float]) -> float | None:
    if not values:
        return None
    return round(sum(values) / len(values), 1)


def _ampm(dt: datetime) -> str:
    return dt.strftime("%I:%M %p").lstrip("0")


def tip_labels(start_utc: str | None) -> dict:
    if not start_utc:
        return {"ct": "", "et": ""}
    try:
        dt = datetime.fromisoformat(start_utc)
    except ValueError:
        return {"ct": "", "et": ""}
    return {
        "ct": f"{_ampm(dt.astimezone(CT))} CT",
        "et": f"{_ampm(dt.astimezone(ET))} ET",
    }


def rest_label(rest) -> str:
    if rest is None:
        return "First game on file"
    rest = int(rest)
    if rest == 0:
        return "Back-to-back"
    if rest == 1:
        return "1 day off"
    if rest < 14:
        return f"{rest} days off"
    return f"{rest} days since last game"


def today_et() -> str:
    return datetime.now(ET).date().isoformat()


def list_days(conn, anchor: str) -> list[dict]:
    start = (datetime.strptime(anchor, "%Y-%m-%d").date() - timedelta(days=3)).isoformat()
    end = (datetime.strptime(anchor, "%Y-%m-%d").date() + timedelta(days=14)).isoformat()
    return rows(
        conn,
        """
        SELECT gameday,
               COUNT(*) AS games,
               SUM(CASE WHEN status = 'post' THEN 1 ELSE 0 END) AS finals
        FROM games
        WHERE gameday >= ? AND gameday <= ?
        GROUP BY gameday
        ORDER BY gameday
        """,
        (start, end),
    )


def resolve_day(conn, gameday: str | None) -> str:
    anchor = today_et()
    if gameday:
        return gameday
    days = [item["gameday"] for item in list_days(conn, anchor)]
    if anchor in days:
        return anchor
    future = [day for day in days if day >= anchor]
    if future:
        return future[0]
    past = [day for day in days if day < anchor]
    if past:
        return past[-1]
    return anchor


def league_environment(conn) -> dict:
    env = one(
        conn,
        """
        SELECT
          AVG((home_score + away_score) / 2.0) AS league_ppg,
          AVG(CASE WHEN COALESCE(neutral, 0) = 0 THEN home_score - away_score END) AS hca,
          COUNT(*) AS games
        FROM games
        WHERE status = 'post'
          AND season_type = 'REG'
          AND home_score IS NOT NULL
          AND away_score IS NOT NULL
        """,
    ) or {}
    league = env.get("league_ppg")
    hca = env.get("hca")
    return {
        "league_ppg": round(float(league), 1) if league is not None else None,
        "hca": round(float(hca), 1) if hca is not None else None,
        "games": env.get("games") or 0,
    }


def _profile(games: list[dict]) -> dict | None:
    if not games:
        return None
    wins = sum(1 for game in games if game["pts"] > game["allowed"])
    ppg = _mean([game["pts"] for game in games])
    papg = _mean([game["allowed"] for game in games])
    return {
        "games": len(games),
        "wins": wins,
        "losses": len(games) - wins,
        "ppg": ppg,
        "papg": papg,
        "margin": round(ppg - papg, 1) if ppg is not None and papg is not None else None,
    }


def team_log(conn, abbr: str, before: str, season_types: tuple[str, ...]) -> list[dict]:
    marks = ",".join("?" for _ in season_types)
    return rows(
        conn,
        f"""
        SELECT
          season,
          CASE WHEN home_team = ? THEN home_score ELSE away_score END AS pts,
          CASE WHEN home_team = ? THEN away_score ELSE home_score END AS allowed
        FROM games
        WHERE (home_team = ? OR away_team = ?)
          AND status = 'post'
          AND home_score IS NOT NULL
          AND away_score IS NOT NULL
          AND season_type IN ({marks})
          AND gameday < ?
        ORDER BY gameday DESC, start_utc DESC
        """,
        (abbr, abbr, abbr, abbr, *season_types, before),
    )


def season_label(year, calendar: bool = False) -> str:
    if not year:
        return "regular season"
    text = str(int(year))
    if calendar:
        return f"{text} regular season"
    return f"{int(year) - 1}-{text[-2:]} regular season"


def choose_samples(log: list[dict], season, calendar: bool = False) -> tuple[list[dict], list[dict], str]:
    """Full current season once it has a body. Opening weeks stay on last season."""
    if not log:
        return [], [], "regular season"
    current = [game for game in log if season and game.get("season") == season]
    if len(current) >= SEASON_BODY_GAMES:
        body = current
        label = season_label(season, calendar)
    else:
        years = sorted({game["season"] for game in log if game.get("season") not in (None, season)}, reverse=True)
        prior_year = years[0] if years else None
        body = [game for game in log if game.get("season") == prior_year] if prior_year else current
        label = season_label(prior_year or season, calendar)
    recent_pool = current if len(current) >= TEAM_RECENT_GAMES else log
    return body, recent_pool[:TEAM_RECENT_GAMES], label


def outs_for(conn, team_id: str | None) -> list[dict]:
    if not team_id:
        return []
    found = rows(
        conn,
        """
        SELECT player_name, position, status, detail
        FROM injuries
        WHERE team_id = ?
        ORDER BY
          CASE LOWER(status)
            WHEN 'out' THEN 0
            WHEN 'doubtful' THEN 1
            WHEN 'questionable' THEN 2
            ELSE 3
          END,
          player_name
        """,
        (team_id,),
    )
    shown = []
    for item in found:
        if (item.get("status") or "").strip().lower() not in SHOWN_STATUSES:
            continue
        shown.append(
            {
                "name": item["player_name"],
                "position": item.get("position") or "",
                "status": item.get("status") or "",
                "detail": item.get("detail") or "",
            }
        )
    return shown


def side_card(conn, abbr: str, team_id: str | None, before: str, season_type: str, season, rest, sport: str = "NBA") -> dict:
    team = one(conn, "SELECT abbr, name, color FROM teams WHERE abbr = ?", (abbr,)) or {}
    types = ("REG", "POST") if season_type == "POST" else ("REG",)
    log = team_log(conn, abbr, before, types)
    if not log and season_type != "REG":
        log = team_log(conn, abbr, before, ("REG", "POST", "PRE"))
    body, recent, label = choose_samples(log, season, sport == "WNBA")
    if not body:
        label = f"No {sport} season on file"
    elif season_type == "POST":
        label = label.replace("regular season", "games already played")
    return {
        "team": abbr,
        "name": team.get("name") or abbr,
        "color": team.get("color"),
        "rest": rest,
        "rest_label": rest_label(rest),
        "overall": _profile(body),
        "recent": _profile(recent),
        "sample": label,
        "out": outs_for(conn, team_id),
    }


def expected_points(offense, defense, league, extra: float = 0.0):
    if offense is None or defense is None or league is None:
        return None
    return round(float(offense) + float(defense) - float(league) + extra, 1)


def expected_score(home: dict, away: dict, env: dict, neutral: bool, season_type: str) -> dict | None:
    home_over = home.get("overall") or {}
    away_over = away.get("overall") or {}
    league = env.get("league_ppg")
    hca = 0.0 if neutral else float(env.get("hca") or 0)
    home_pts = expected_points(home_over.get("ppg"), away_over.get("papg"), league, hca)
    away_pts = expected_points(away_over.get("ppg"), home_over.get("papg"), league, 0.0)
    if home_pts is None or away_pts is None:
        return None
    home_recent = home.get("recent") or {}
    away_recent = away.get("recent") or {}
    recent_home = expected_points(home_recent.get("ppg"), away_recent.get("papg"), league, hca)
    recent_away = expected_points(away_recent.get("ppg"), home_recent.get("papg"), league, 0.0)
    recent = None
    if recent_home is not None and recent_away is not None:
        recent = {
            "away_pts": recent_away,
            "home_pts": recent_home,
            "total": round(recent_away + recent_home, 1),
            "margin": round(recent_home - recent_away, 1),
        }
    if season_type == "PRE":
        lead = "Preseason game. Numbers are from each team's last regular-season games. "
    elif season_type == "POST":
        lead = "Playoff game. Numbers include that team's playoff games already played. "
    else:
        lead = ""
    return {
        "away_pts": away_pts,
        "home_pts": home_pts,
        "total": round(away_pts + home_pts, 1),
        "margin": round(home_pts - away_pts, 1),
        "hca": round(hca, 1),
        "league_ppg": league,
        "recent": recent,
        "method": (
            lead
            + "Expected points are the team's points per game plus the opponent's points allowed, "
            "minus the league average. Home court from the regular season is added when the floor is not neutral. "
            "Listed injuries are not taken out of the number yet."
        ),
    }


def decorate_game(conn, game: dict, env: dict, sport: str = "NBA") -> dict:
    tips = tip_labels(game.get("start_utc"))
    before = game.get("gameday") or "9999-12-31"
    season_type = game.get("season_type") or "REG"
    away = side_card(
        conn, game["away_team"], game.get("away_id"), before, season_type, game.get("season"), game.get("away_rest"), sport
    )
    home = side_card(
        conn, game["home_team"], game.get("home_id"), before, season_type, game.get("season"), game.get("home_rest"), sport
    )
    return {
        "game_id": game["game_id"],
        "gameday": game.get("gameday"),
        "start_utc": game.get("start_utc"),
        "tip_ct": tips["ct"],
        "tip_et": tips["et"],
        "season": game.get("season"),
        "season_label": game.get("season_label"),
        "season_type": season_type,
        "status": game.get("status") or "pre",
        "status_detail": game.get("status_detail") or "",
        "period": game.get("period") or 0,
        "clock": game.get("clock") or "",
        "neutral": bool(game.get("neutral")),
        "venue": game.get("venue") or "",
        "location": game.get("location") or "",
        "note": game.get("note") or "",
        "away": away,
        "home": home,
        "score": {
            "away": game.get("away_score"),
            "home": game.get("home_score"),
        },
        "expected": expected_score(home, away, env, bool(game.get("neutral")), season_type),
    }


def get_slate(conn, gameday: str | None = None, league: str = "nba") -> dict:
    from hoops.live import refresh_day

    sport = "WNBA" if league == "wnba" else "NBA"
    anchor = today_et()
    day = resolve_day(conn, gameday)
    live = refresh_day(conn, day.replace("-", ""), league=league)
    env = league_environment(conn)
    games = rows(
        conn,
        """
        SELECT game_id, season, season_label, season_type, gameday, start_utc,
               status, status_detail, period, clock,
               home_team, away_team, home_id, away_id,
               home_score, away_score, neutral, venue, location, note,
               home_rest, away_rest
        FROM games
        WHERE gameday = ?
        ORDER BY start_utc, game_id
        """,
        (day,),
    )
    label_dt = datetime.strptime(day, "%Y-%m-%d")
    return {
        "slate": {
            "gameday": day,
            "label": label_dt.strftime("%A, %b ") + str(label_dt.day),
            "games": len(games),
            "is_today": day == anchor,
            "league": league,
        },
        "days": list_days(conn, anchor if not gameday else day),
        "environment": env,
        "live": live,
        "games": [decorate_game(conn, game, env, sport) for game in games],
        "ingesting": False,
    }
