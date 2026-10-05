"""ESPN's public basketball JSON. No key.

NBA and WNBA and men's college basketball use the same site feed. Scoreboard and the game summary are
what the ESPN game page polls while a game is on.
"""

from __future__ import annotations

import json
import urllib.error
import urllib.request

UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36"
)
LEAGUE_BASE = {
    "nba": "https://site.api.espn.com/apis/site/v2/sports/basketball/nba",
    "wnba": "https://site.api.espn.com/apis/site/v2/sports/basketball/wnba",
    "cbb": "https://site.api.espn.com/apis/site/v2/sports/basketball/mens-college-basketball",
}


def base(league: str = "nba") -> str:
    try:
        return LEAGUE_BASE[league]
    except KeyError as exc:
        raise ValueError("league is nba, wnba, or cbb") from exc


def get_json(url: str) -> dict:
    req = urllib.request.Request(
        url,
        headers={"User-Agent": UA, "Accept": "application/json"},
    )
    with urllib.request.urlopen(req, timeout=45) as resp:
        return json.loads(resp.read().decode("utf-8"))


def fetch_teams(league: str = "nba") -> list[dict]:
    data = get_json(f"{base(league)}/teams?limit=400")
    league_node = data["sports"][0]["leagues"][0]
    teams = []
    for item in league_node.get("teams") or []:
        team = item.get("team") or item
        if team.get("isAllStar"):
            continue
        if team.get("isActive") is False:
            continue
        teams.append(team)
    return teams


def fetch_schedule(team_id: str, season: int, league: str = "nba") -> dict:
    return get_json(f"{base(league)}/teams/{team_id}/schedule?season={season}")


def fetch_scoreboard(yyyymmdd: str | None = None, league: str = "nba") -> dict:
    url = f"{base(league)}/scoreboard"
    if yyyymmdd:
        url = f"{url}?dates={yyyymmdd}"
    return get_json(url)


def fetch_summary(event_id: str, league: str = "nba") -> dict:
    return get_json(f"{base(league)}/summary?event={event_id}")


def fetch_injuries(league: str = "nba") -> dict:
    return get_json(f"{base(league)}/injuries")


def quiet_http_error(exc: BaseException) -> str:
    if isinstance(exc, urllib.error.HTTPError):
        return f"HTTP {exc.code}"
    return str(exc)
