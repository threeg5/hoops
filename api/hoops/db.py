from __future__ import annotations

import sqlite3
from pathlib import Path

from hoops.config import DATA_DIR, DB_PATH

SCHEMA = """
CREATE TABLE IF NOT EXISTS meta (
  key TEXT PRIMARY KEY,
  value TEXT
);

CREATE TABLE IF NOT EXISTS teams (
  team_id TEXT PRIMARY KEY,
  abbr TEXT NOT NULL,
  name TEXT,
  city TEXT,
  nickname TEXT,
  color TEXT
);

CREATE TABLE IF NOT EXISTS games (
  game_id TEXT PRIMARY KEY,
  season INTEGER,
  season_label TEXT,
  season_type TEXT,
  gameday TEXT,
  start_utc TEXT,
  status TEXT,
  status_detail TEXT,
  period INTEGER,
  clock TEXT,
  home_team TEXT,
  away_team TEXT,
  home_id TEXT,
  away_id TEXT,
  home_score INTEGER,
  away_score INTEGER,
  neutral INTEGER,
  venue TEXT,
  location TEXT,
  note TEXT,
  home_rest INTEGER,
  away_rest INTEGER
);

CREATE INDEX IF NOT EXISTS idx_games_day ON games(gameday);
CREATE INDEX IF NOT EXISTS idx_games_teams ON games(home_team, away_team);

CREATE TABLE IF NOT EXISTS injuries (
  team_id TEXT NOT NULL,
  player_name TEXT NOT NULL,
  position TEXT,
  status TEXT,
  detail TEXT,
  comment TEXT,
  PRIMARY KEY (team_id, player_name)
);
"""


def ensure_dirs() -> None:
    DATA_DIR.mkdir(parents=True, exist_ok=True)


def connect(path: Path | None = None) -> sqlite3.Connection:
    ensure_dirs()
    conn = sqlite3.connect(path or DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    init_db(conn)
    return conn


def init_db(conn: sqlite3.Connection) -> None:
    conn.executescript(SCHEMA)
    conn.commit()
