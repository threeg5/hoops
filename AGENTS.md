# HOOPS — NBA situational research desk

Personal research tool for NBA teams. The slate shows the day’s games with each side’s recent scoring, days off, listed injuries, and an expected score from those numbers. The minute log is the live play-by-play: quarter, clock, score, and the play text.

Data comes from ESPN’s public NBA JSON (scoreboard, game summary plays, team schedules, injury report). Not an official NBA feed and not a betting lock engine.

W-HOOPS is its own page for the WNBA, on ESPN’s `basketball/wnba` feed. Locally it is `http://127.0.0.1:5177/whoops/`. The public page is `https://theprofitengineer.com/whoops/`. It lives in `whoops.db`, separate from `hoops.db`, so Atlanta and New York never mix the Hawks with the Dream or the Knicks with the Liberty. Load it with `python -m hoops.ingest wnba`. The HOOPS page does not list it and does not read that book. Publish the page with `npm run build:whoops` and `python deploy-hostgator.py whoops` after the API on Render knows `league=wnba`.

The NBA.com live CDN (`cdn.nba.com` liveData scoreboard / box score / play-by-play) is the official page feed and updates during games. It answered 403 on 2026-10-04 even with an nba.com referrer, so the desk uses ESPN until that CDN is usable again.

## Structure

- `api/` — FastAPI + SQLite. Entry: `main.py`. Ingest: `python -m hoops.ingest`
- `web/` — Vite + React desk UI

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

## Deploy

API on Render from `render.yaml` (Python + SQLite disk). Public site is HostGator at `https://theprofitengineer.com/hoops/`.

1. Push this repo to GitHub.
2. Render → New → Blueprint → this repo. First boot ingests if the disk is empty.
3. The live API is `https://hoops-api-5cu4.onrender.com`. Put that in `web/.env.hostgator` as `VITE_API_URL` if it changes.
4. From `web/`: `npm run build:hostgator` then `python deploy-hostgator.py`.
5. Add HOOPS on the Profit Engineer home page only after `https://theprofitengineer.com/hoops/` answers.
