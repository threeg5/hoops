from contextlib import asynccontextmanager
from threading import Thread
import os
import time
import traceback

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from hoops.config import DATA_DIR, DB_PATH, cors_origins
from hoops.db import connect
from hoops.routes import router

LOCK_PATH = DATA_DIR / "ingest.lock"


def _log(message: str) -> None:
    print(message, flush=True)


def _ingest_complete() -> bool:
    if not DB_PATH.exists():
        return False
    conn = connect()
    try:
        row = conn.execute("SELECT value FROM meta WHERE key = 'ingest_complete'").fetchone()
        return bool(row and str(row["value"]) == "1")
    except Exception:
        return False
    finally:
        conn.close()


def _boot_ingest() -> None:
    time.sleep(2)
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    try:
        fd = os.open(LOCK_PATH, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
        os.write(fd, str(os.getpid()).encode())
        os.close(fd)
    except FileExistsError:
        _log(f"Skip ingest; lock already present at {LOCK_PATH}")
        return
    try:
        if _ingest_complete():
            _log("Skip ingest; already complete")
            return
        from hoops.ingest import run_ingest

        run_ingest()
    except Exception:
        traceback.print_exc()
    finally:
        LOCK_PATH.unlink(missing_ok=True)


@asynccontextmanager
async def lifespan(_app: FastAPI):
    try:
        DATA_DIR.mkdir(parents=True, exist_ok=True)
    except OSError as exc:
        _log(f"Could not create data dir {DATA_DIR}: {exc}")
    if LOCK_PATH.exists():
        _log(f"Removing stale ingest lock {LOCK_PATH}")
        LOCK_PATH.unlink(missing_ok=True)
    if _ingest_complete():
        _log("HOOPS database ready")
    else:
        _log("Starting HOOPS ingest thread")
        Thread(target=_boot_ingest, daemon=True).start()
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
