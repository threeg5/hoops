"""ESPN's public NBA JSON. No key.

Scoreboard and the game summary (play log) are what the ESPN game page polls
while a game is on, so the clock and the last play stay current.
"""

from __future__ import annotations

import json
import urllib.error
import urllib.request

UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36"
)
BASE = "https://site.api.espn.com/apis/site/v2/sports/basketball/nba"


def get_json(url: str) -> dict:
    req = urllib.request.Request(
        url,
        headers={"User-Agent": UA, "Accept": "application/json"},
    )
    with urllib.request.urlopen(req, timeout=45) as resp:
        return json.loads(resp.read().decode("utf-8"))


def fetch_teams() -> list[dict]:
    data = get_json(f"{BASE}/teams?limit=50")
    league = data["sports"][0]["leagues"][0]
    teams = []
    for item in league.get("teams") or []:
        team = item.get("team") or item
        if team.get("isAllStar"):
            continue
        if team.get("isActive") is False:
            continue
        teams.append(team)
    return teams


def fetch_schedule(team_id: str, season: int) -> dict:
    return get_json(f"{BASE}/teams/{team_id}/schedule?season={season}")


def fetch_scoreboard(yyyymmdd: str | None = None) -> dict:
    url = f"{BASE}/scoreboard"
    if yyyymmdd:
        url = f"{url}?dates={yyyymmdd}"
    return get_json(url)


def fetch_summary(event_id: str) -> dict:
    return get_json(f"{BASE}/summary?event={event_id}")


def fetch_injuries() -> dict:
    return get_json(f"{BASE}/injuries")


def quiet_http_error(exc: BaseException) -> str:
    if isinstance(exc, urllib.error.HTTPError):
        return f"HTTP {exc.code}"
    return str(exc)
