from contextlib import asynccontextmanager
from threading import Thread
import os
import time
import traceback

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from hoops.config import CBB_DB_PATH, DATA_DIR, DB_PATH, WNBA_DB_PATH, cors_origins
from hoops.db import connect
from hoops.routes import router

def _log(message: str) -> None:
    print(message, flush=True)


def _ingest_complete(path) -> bool:
    if not path.exists():
        return False
    conn = connect(path)
    try:
        row = conn.execute("SELECT value FROM meta WHERE key = 'ingest_complete'").fetchone()
        return bool(row and str(row["value"]) == "1")
    except Exception:
        return False
    finally:
        conn.close()


def _boot_ingest(league: str, path, lock) -> None:
    time.sleep(2)
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    try:
        fd = os.open(lock, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
        os.write(fd, str(os.getpid()).encode())
        os.close(fd)
    except FileExistsError:
        _log(f"Skip {league} ingest; lock already present at {lock}")
        return
    try:
        if _ingest_complete(path):
            _log(f"Skip {league} ingest; already complete")
            return
        from hoops.ingest import run_ingest

        run_ingest(league)
    except Exception:
        traceback.print_exc()
    finally:
        lock.unlink(missing_ok=True)


@asynccontextmanager
async def lifespan(_app: FastAPI):
    try:
        DATA_DIR.mkdir(parents=True, exist_ok=True)
    except OSError as exc:
        _log(f"Could not create data dir {DATA_DIR}: {exc}")
    books = (
        ("nba", DB_PATH, DATA_DIR / "ingest.lock"),
        ("wnba", WNBA_DB_PATH, DATA_DIR / "ingest-wnba.lock"),
        ("cbb", CBB_DB_PATH, DATA_DIR / "ingest-cbb.lock"),
    )
    for league, path, lock in books:
        if lock.exists():
            _log(f"Removing stale ingest lock {lock}")
            lock.unlink(missing_ok=True)
        if _ingest_complete(path):
            _log(f"{league.upper()} database ready")
        else:
            _log(f"Starting {league.upper()} ingest thread")
            Thread(target=_boot_ingest, args=(league, path, lock), daemon=True).start()
    yield


app = FastAPI(title="HOOPS", version="0.1.0", lifespan=lifespan)
app.add_middleware(
    CORSMiddleware,
    allow_origins=cors_origins(),
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
app.include_router(router)


@app.get("/")
def root():
    return {"ok": True, "service": "hoops-api", "health": "/health", "slate": "/api/slate"}
