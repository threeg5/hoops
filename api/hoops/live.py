"""Keep today's score, clock, and injury list current.

ESPN's scoreboard is the working up-to-the-minute feed. The NBA.com live CDN
(cdn.nba.com liveData scoreboard, box score, and play-by-play) is the official
page feed, and it answers 403 from this desk as of October 2026 even with an
nba.com referrer. HOOPS reads ESPN until that CDN opens again.
"""

from __future__ import annotations

import threading
import time
from datetime import datetime, timezone

from hoops.config import LIVE_CACHE_SECONDS
from hoops.espn import fetch_scoreboard, fetch_summary, quiet_http_error
from hoops.ingest import parse_event, store_injuries

_lock = threading.Lock()
_scoreboard_at: dict[str, float] = {}
_minutes_cache: dict[str, tuple[float, dict]] = {}
_injuries_at: dict[str, float] = {}
INJURY_SECONDS = 300


def _meta(conn, key: str, value: str) -> None:
    conn.execute(
        "INSERT OR REPLACE INTO meta(key, value) VALUES (?, ?)",
        (key, value),
    )


def refresh_day(conn, yyyymmdd: str, *, force: bool = False, league: str = "nba") -> dict:
    """Update one date's clock and score. Cached for a few seconds."""
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
                        neutral = ?, venue = ?, location = ?, note = ?
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
            updated += 1
        global _injuries_at
        team_count = conn.execute("SELECT COUNT(*) AS n FROM teams").fetchone()["n"]
        last_injuries = _injuries_at.get(league, 0.0)
        if team_count and time.time() - last_injuries >= INJURY_SECONDS:
            teams = {
                row["team_id"]: dict(row)
                for row in conn.execute("SELECT team_id, abbr, name FROM teams")
            }
            store_injuries(conn, teams, league)
            _injuries_at[league] = time.time()
        stamp = datetime.now(timezone.utc).isoformat()
        _meta(conn, "live_pulled_at", stamp)
        _meta(conn, "live_source", "ESPN")
        conn.commit()
        _scoreboard_at[cache_key] = time.time()
        return {"source": "ESPN", "pulled_at": stamp, "updated": updated, "cached": False}
    except Exception as exc:
        conn.rollback()
        return {"source": "ESPN", "error": quiet_http_error(exc), "pulled_at": None}
    finally:
        _lock.release()


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
