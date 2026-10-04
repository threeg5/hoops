# HOOPS — NBA team research desk

Personal research desk for professional basketball. The slate is NBA teams: tonight’s games, each side’s recent points, days off, who is out, and an expected score from those numbers. Open a game for the minute log (quarter, clock, score, play) while it is on.

HOOPS is part of The Profit Engineer, next to Gridiron, College Gridiron, and Diamond. It is not an official NBA feed and not a pick sheet.

## Where the live information comes from

**Working feed: ESPN’s public NBA JSON** (no key).

- Scoreboard: `https://site.api.espn.com/apis/site/v2/sports/basketball/nba/scoreboard`
- Play log: `.../summary?event={id}` — every play has quarter, clock, score, and a wall-clock time
- Team schedules and final scores, plus the league injury report, come from the same host

The desk polls that scoreboard about every 15 seconds and the open game’s play log about every 10 seconds. That is the up-to-the-minute layer.

**NBA.com’s own live CDN** (`cdn.nba.com/static/json/liveData/…` scoreboard, box score, and play-by-play) is what nba.com polls during a game. As of October 2026 it returns 403 from this machine even with an `https://www.nba.com/` referrer, so HOOPS does not depend on it. If that CDN opens up again, it is the sharper official clock.

Team form uses completed games already stored from ESPN schedules (2025-26 and the current 2026-27 season). The expected score is team points per game plus the opponent’s points allowed, minus the league average, plus regular-season home court when the floor is not neutral. Injuries are listed. They are not removed from the number yet.

## Run locally

```
cd api
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
python -m hoops.ingest
uvicorn main:app --reload --port 8003

cd web
npm install
npm run dev
```

Open `http://127.0.0.1:5177`. API defaults to `http://127.0.0.1:8003`.

First ingest pulls every NBA team schedule. It takes a minute or two.

## Deploy

API on Render from `render.yaml`. The public page is `https://theprofitengineer.com/hoops/`. From `web/`, run `npm run build:hostgator` and then `python deploy-hostgator.py`. Add the HOOPS card on the Profit Engineer home page after that folder answers.
