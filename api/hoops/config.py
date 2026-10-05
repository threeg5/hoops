import os
from pathlib import Path

from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parents[1]
REPO_ROOT = ROOT.parent
load_dotenv(ROOT / ".env")
load_dotenv(REPO_ROOT / ".env")

DATA_DIR = Path(os.environ.get("DATA_DIR", str(ROOT / "data")))
DB_PATH = DATA_DIR / "hoops.db"
WNBA_DB_PATH = DATA_DIR / "whoops.db"
CBB_DB_PATH = DATA_DIR / "collegehoops.db"

# ESPN NBA season year is the year the season ends. 2026 is 2025-26, 2027 is 2026-27.
SEASONS = [2026, 2027]
# WNBA season year is the calendar year. 2026 is the 2026 season.
WNBA_SEASONS = [2025, 2026]
# Men's college basketball uses the ending year, same as the NBA. 2027 is 2026-27.
CBB_SEASONS = [2026, 2027]
# Season body is the full regular season once 10 games exist.
# Before that (preseason, opening weeks) the body stays the previous season.
SEASON_BODY_GAMES = 10
TEAM_RECENT_GAMES = 8
LIVE_CACHE_SECONDS = 12

HOSTGATOR_ORIGINS = (
    "https://theprofitengineer.com",
    "https://www.theprofitengineer.com",
)


def cors_origins() -> list[str]:
    raw = os.environ.get(
        "CORS_ORIGINS",
        "http://127.0.0.1:5177,http://localhost:5177",
    )
    origins = [origin.strip().rstrip("/") for origin in raw.split(",") if origin.strip()]
    for origin in HOSTGATOR_ORIGINS:
        if origin not in origins:
            origins.append(origin)
    return origins
