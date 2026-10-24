"""Keep today's score, clock, and injury list current.

ESPN's scoreboard is the working up-to-the-minute feed. The NBA.com live CDN
(cdn.nba.com liveData scoreboard, box score, and play-by-play) is the official
page feed, and it answers 403 from this desk as of October 2026 even with an
nba.com referrer. HOOPS reads ESPN until that CDN opens again.
"""

from __future__ import annotations

import threading
import time
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

from hoops.config import LIVE_CACHE_SECONDS
from hoops.espn import fetch_scoreboard, fetch_summary, quiet_http_error
from hoops.ingest import parse_event, store_injuries

ET = ZoneInfo("America/New_York")
_lock = threading.Lock()
_scoreboard_at: dict[str, float] = {}
_minutes_cache: dict[str, tuple[float, dict]] = {}
_injuries_at: dict[str, float] = {}
INJURY_SECONDS = 300
# Upcoming games are listed from the scoreboard. That pass is not the book.
SCHEDULE_SECONDS = 6 * 60 * 60
# Book pulls (injuries, and later the lines) only at these checkpoints:
# about 3 days out, the day before gameday, and inside 2 hours of tip.
BOOK_DAYS = (3, 1)
TIP_HOURS = 2


def _meta(conn, key: str, value: str) -> None:
    conn.execute(
        "INSERT OR REPLACE INTO meta(key, value) VALUES (?, ?)",
        (key, value),
    )


def _meta_value(conn, key: str) -> str | None:
    row = conn.execute("SELECT value FROM meta WHERE key = ?", (key,)).fetchone()
    return row["value"] if row else None


def _stamped_today(conn, key: str, today) -> bool:
    raw = _meta_value(conn, key)
    return bool(raw and raw.startswith(today.isoformat()))


def _refresh_injuries(conn, league: str) -> None:
    if time.time() - _injuries_at.get(league, 0.0) < INJURY_SECONDS:
        return
    team_count = conn.execute("SELECT COUNT(*) AS n FROM teams").fetchone()["n"]
    if not team_count:
        return
    teams = {
        row["team_id"]: dict(row)
        for row in conn.execute("SELECT team_id, abbr, name FROM teams")
    }
    store_injuries(conn, teams, league)
    _injuries_at[league] = time.time()


def _lookback_days(conn, today) -> int:
    lookback = 3
    row = conn.execute(
        "SELECT MAX(gameday) AS day FROM games WHERE gameday < ?",
        (today.isoformat(),),
    ).fetchone()
    if row and row["day"]:
        last = datetime.strptime(row["day"], "%Y-%m-%d").date()
        gap = (today - last).days
        if gap > lookback:
            lookback = min(gap, 21)
    return lookback


def _in_tip_window(conn, today) -> bool:
    """A game on today's card is inside two hours of tip, or already on."""
    now = datetime.now(ET)
    soon = now + timedelta(hours=TIP_HOURS)
    rows = conn.execute(
        """
        SELECT start_utc, status
        FROM games
        WHERE gameday = ? AND status != 'post'
        """,
        (today.isoformat(),),
    ).fetchall()
    for row in rows:
        if row["status"] == "in":
            return True
        if not row["start_utc"]:
            continue
        try:
            start = datetime.fromisoformat(row["start_utc"])
        except ValueError:
            continue
        if start.tzinfo is None:
            start = start.replace(tzinfo=timezone.utc)
        start = start.astimezone(ET)
        if now - timedelta(hours=5) <= start <= soon:
            return True
    return False


def _schedule_due(conn, league: str) -> bool:
    raw = _meta_value(conn, f"schedule:{league}")
    if not raw:
        return True
    try:
        prev = datetime.fromisoformat(raw)
    except ValueError:
        return True
    if prev.tzinfo is None:
        prev = prev.replace(tzinfo=timezone.utc)
    return (datetime.now(timezone.utc) - prev).total_seconds() >= SCHEDULE_SECONDS


def refresh_day(
    conn,
    yyyymmdd: str,
    *,
    force: bool = False,
    league: str = "nba",
    injuries: bool = False,
) -> dict:
    """Update one date's clock and score. Cached for a few seconds.

    Injuries are the book side of the pull. The schedule pass lists games
    without them.
    """
    now = time.time()
    cache_key = f"{league}:{yyyymmdd}"
    pulled = _scoreboard_at.get(cache_key)
    if not force and pulled is not None and now - pulled < LIVE_CACHE_SECONDS:
        row = conn.execute(
            "SELECT value FROM meta WHERE key = 'live_pulled_at'"
        ).fetchone()
        return {
            "source": "ESPN",
            "pulled_at": row["value"] if row else None,
            "cached": True,
        }
    if not _lock.acquire(blocking=False):
        row = conn.execute(
            "SELECT value FROM meta WHERE key = 'live_pulled_at'"
        ).fetchone()
        return {
            "source": "ESPN",
            "pulled_at": row["value"] if row else None,
            "cached": True,
        }
    try:
        try:
            payload = fetch_scoreboard(yyyymmdd, league)
        except Exception as exc:
            return {"source": "ESPN", "error": quiet_http_error(exc), "pulled_at": None}
        updated = 0
        inserted = 0
        for event in payload.get("events") or []:
            game = parse_event(event)
            if not game or not game["game_id"]:
                continue
            existing = conn.execute(
                "SELECT game_id FROM games WHERE game_id = ?",
                (game["game_id"],),
            ).fetchone()
            if existing:
                conn.execute(
                    """
                    UPDATE games
                    SET status = ?, status_detail = ?, period = ?, clock = ?,
                        home_score = ?, away_score = ?,
                        neutral = ?, venue = ?, location = ?, note = ?,
                        season = COALESCE(?, season),
                        season_type = ?,
                        season_label = CASE WHEN ? != '' THEN ? ELSE season_label END
                    WHERE game_id = ?
                    """,
                    (
                        game["status"],
                        game["status_detail"],
                        game["period"],
                        game["clock"],
                        game["home_score"],
                        game["away_score"],
                        game["neutral"],
                        game["venue"],
                        game["location"],
                        game["note"],
                        game["season"],
                        game["season_type"],
                        game["season_label"] or "",
                        game["season_label"] or "",
                        game["game_id"],
                    ),
                )
            else:
                conn.execute(
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
                    game,
                )
                inserted += 1
            updated += 1
        if injuries:
            _refresh_injuries(conn, league)
        if inserted:
            from hoops.ingest import apply_rest

            apply_rest(conn)
        stamp = datetime.now(timezone.utc).isoformat()
        _meta(conn, "live_pulled_at", stamp)
        _meta(conn, "live_source", "ESPN")
        conn.commit()
        _scoreboard_at[cache_key] = time.time()
        return {
            "source": "ESPN",
            "pulled_at": stamp,
            "updated": updated,
            "inserted": inserted,
            "cached": False,
        }
    except Exception as exc:
        conn.rollback()
        return {"source": "ESPN", "error": quiet_http_error(exc), "pulled_at": None}
    finally:
        _lock.release()


def _pull_book_day(conn, day, kind: str, league: str) -> None:
    """One book pull for a checkpoint. Lines stay off the slate."""
    key = f"book:{league}:{day.isoformat()}:{kind}"
    today = datetime.now(ET).date()
    if _stamped_today(conn, key, today):
        return
    result = refresh_day(
        conn,
        day.strftime("%Y%m%d"),
        force=True,
        league=league,
        injuries=True,
    )
    if result.get("error"):
        return
    _meta(conn, key, datetime.now(ET).isoformat())
    conn.commit()


def refresh_window(conn, league: str = "nba", ahead: int = 14) -> dict:
    """List upcoming games, and pull the book only at the close checkpoints.

    The scoreboard pass keeps the next dates on the slate. It does not ask
    for lines. Injuries (the book this desk has today) refresh when a game
    is about three days out, again the day before gameday, and again inside
    two hours of tip. Today's score still updates while a game is on.
    """
    today = datetime.now(ET).date()
    live = refresh_day(conn, today.strftime("%Y%m%d"), league=league, injuries=False)
    if live.get("error"):
        return live
    if _in_tip_window(conn, today):
        _pull_book_day(conn, today, "tip", league)

    for offset in BOOK_DAYS:
        _pull_book_day(conn, today + timedelta(days=offset), f"t{offset}", league)

    lookback = _lookback_days(conn, today)
    backfill_key = f"backfill:{league}"
    need_backfill = lookback > 3 and not _stamped_today(conn, backfill_key, today)
    if _schedule_due(conn, league) or need_backfill:
        horizon = max(0, min(ahead, 21))
        failed = False
        schedule_due = _schedule_due(conn, league)
        offsets = range(-lookback, horizon + 1) if schedule_due else range(-lookback, 0)
        for offset in offsets:
            if offset == 0:
                continue
            day = (today + timedelta(days=offset)).strftime("%Y%m%d")
            result = refresh_day(conn, day, league=league, injuries=False)
            if result.get("error"):
                failed = True
        if not failed and _schedule_due(conn, league):
            _meta(conn, f"schedule:{league}", datetime.now(timezone.utc).isoformat())
            conn.commit()
        if need_backfill and not failed:
            _meta(conn, backfill_key, datetime.now(ET).isoformat())
            conn.commit()
    _correct_preseason_labels(conn, league, today)
    return live


def _correct_preseason_labels(conn, league: str, today) -> None:
    """Re-read dates the scoreboard had stored as preseason.

    One pass per day. Real preseason stays preseason. Regular-season and
    playoff games pick up the type ESPN sends on the scoreboard.
    """
    key = f"seasonfix:{league}"
    if _stamped_today(conn, key, today):
        return
    start = (today - timedelta(days=3)).isoformat()
    rows = conn.execute(
        """
        SELECT DISTINCT gameday
        FROM games
        WHERE gameday >= ? AND season_type = 'PRE'
        ORDER BY gameday
        """,
        (start,),
    ).fetchall()
    failed = False
    for row in rows:
        result = refresh_day(
            conn,
            row["gameday"].replace("-", ""),
            league=league,
            injuries=False,
        )
        if result.get("error"):
            failed = True
    if not failed:
        _meta(conn, key, datetime.now(ET).isoformat())
        conn.commit()


def game_minutes(event_id: str, league: str = "nba") -> dict:
    now = time.time()
    cache_key = f"{league}:{event_id}"
    cached = _minutes_cache.get(cache_key)
    if cached and now - cached[0] < LIVE_CACHE_SECONDS:
        payload = dict(cached[1])
        payload["cached"] = True
        return payload
    try:
        summary = fetch_summary(event_id, league)
    except Exception as exc:
        return {"game_id": event_id, "error": quiet_http_error(exc), "plays": []}
    plays = []
    for play in summary.get("plays") or []:
        text = (play.get("text") or "").strip()
        if not text:
            continue
        period = play.get("period") or {}
        clock = play.get("clock") or {}
        plays.append(
            {
                "period": period.get("number"),
                "period_label": period.get("displayValue") or "",
                "clock": clock.get("displayValue") or "",
                "text": text,
                "away_score": play.get("awayScore"),
                "home_score": play.get("homeScore"),
                "scoring": bool(play.get("scoringPlay")),
                "wallclock": play.get("wallclock"),
            }
        )
    plays.reverse()
    meta = summary.get("meta") or {}
    header = summary.get("header") or {}
    competitions = (header.get("competitions") or [{}])[0]
    status = (competitions.get("status") or {}).get("type") or {}
    payload = {
        "game_id": event_id,
        "source": "ESPN",
        "updated_at": meta.get("lastPlayWallClock") or meta.get("lastUpdatedAt"),
        "state": meta.get("gameState") or status.get("state"),
        "status_detail": status.get("shortDetail") or status.get("detail") or "",
        "plays": plays,
        "cached": False,
    }
    _minutes_cache[cache_key] = (time.time(), payload)
    return payload
