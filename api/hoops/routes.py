from __future__ import annotations

import re

from fastapi import APIRouter, HTTPException, Query

from hoops.config import DATA_DIR, DB_PATH
from hoops.db import connect
from hoops.live import game_minutes
from hoops.slate import get_slate

router = APIRouter()


def rows(conn, sql: str, params: tuple = ()) -> list[dict]:
    return [dict(row) for row in conn.execute(sql, params).fetchall()]


@router.get("/health")
def health():
    return {"ok": True, "db": DB_PATH.exists()}


@router.get("/api/meta")
def meta():
    if not DB_PATH.exists():
        return {"ingested": False}
    conn = connect()
    try:
        kv = {row["key"]: row["value"] for row in rows(conn, "SELECT key, value FROM meta")}
        counts = conn.execute(
            """
            SELECT
              (SELECT COUNT(*) FROM games) AS games,
              (SELECT COUNT(*) FROM teams) AS teams,
              (SELECT COUNT(*) FROM injuries) AS injuries,
              (SELECT COUNT(*) FROM games WHERE status = 'post' AND season_type = 'REG') AS regular_finals
            """
        ).fetchone()
        return {
            "ingested": kv.get("ingest_complete") == "1",
            "ingest_lock": (DATA_DIR / "ingest.lock").exists(),
            **kv,
            **(dict(counts) if counts else {}),
        }
    finally:
        conn.close()


@router.get("/api/slate")
def slate(date: str | None = Query(default=None, alias="date")):
    if date and not re.fullmatch(r"\d{4}-\d{2}-\d{2}", date):
        raise HTTPException(400, "date is YYYY-MM-DD")
    conn = connect()
    try:
        if not DB_PATH.exists():
            return {"slate": None, "days": [], "games": [], "ingesting": True}
        done = conn.execute(
            "SELECT value FROM meta WHERE key = 'ingest_complete'"
        ).fetchone()
        if not done or done["value"] != "1":
            return {"slate": None, "days": [], "games": [], "ingesting": True}
        return get_slate(conn, date)
    finally:
        conn.close()


@router.get("/api/players")
def players(q: str = ""):
    conn = connect()
    try:
        sql = """
            SELECT i.player_name, i.position, i.status, i.detail, i.comment,
                   t.abbr, t.name AS team_name
            FROM injuries i
            JOIN teams t ON t.team_id = i.team_id
        """
        params: tuple = ()
        if q.strip():
            needle = f"%{q.strip()}%"
            sql += " WHERE i.player_name LIKE ? OR t.abbr LIKE ? OR t.name LIKE ?"
            params = (needle, needle, needle)
        found = rows(conn, sql + " ORDER BY t.abbr, i.player_name", params)
        return {"players": found}
    finally:
        conn.close()


@router.get("/api/games/{game_id}/minutes")
def minutes(game_id: str):
    if not game_id.isdigit():
        raise HTTPException(400, "Game id should be the ESPN event id")
    return game_minutes(game_id)
