from fastapi import FastAPI, HTTPException, Request, Header, Depends
from fastapi.responses import StreamingResponse
import sqlite3, json, threading, queue, os, time
from typing import Optional, List

# On Fly, mount a volume at /data so SQLite persists
DB_PATH = os.getenv("STEMY_DB_PATH", "/data/stemy.db")

# Optional shared secret (set on Fly with: fly secrets set STEMY_API_KEY="...")
API_KEY = os.getenv("STEMY_API_KEY", "")

app = FastAPI(title="SteMy Hub Prototype", version="0.1.0")

# ---------------------------
# Simple auth (optional but recommended)
# ---------------------------
def require_key(x_api_key: str = Header(default="")):
    if API_KEY and x_api_key != API_KEY:
        raise HTTPException(status_code=401, detail="Unauthorized")

# ---------------------------
# In-memory pub/sub for SSE (prototype)
# Note: for MVP on 1 Fly machine, this is fine.
# ---------------------------
subscribers_lock = threading.Lock()
subscribers: List[queue.Queue] = []

def broadcast(msg: dict) -> None:
    payload = json.dumps(msg)
    with subscribers_lock:
        for q in list(subscribers):
            try:
                q.put_nowait(payload)
            except Exception:
                pass

# ---------------------------
# DB init
# ---------------------------
def init_db() -> None:
    os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)
    con = sqlite3.connect(DB_PATH)
    cur = con.cursor()

    cur.execute("""
    CREATE TABLE IF NOT EXISTS patches (
        patch_id TEXT PRIMARY KEY,
        run_id TEXT NOT NULL,
        ts TEXT NOT NULL,
        patch_json TEXT NOT NULL
    )
    """)

    cur.execute("""
    CREATE TABLE IF NOT EXISTS run_kv_events (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        run_id TEXT NOT NULL,
        ts TEXT NOT NULL,
        key TEXT NOT NULL,
        value_json TEXT NOT NULL,
        patch_id TEXT NOT NULL
    )
    """)

    cur.execute("""
    CREATE TABLE IF NOT EXISTS run_kv_current (
        run_id TEXT NOT NULL,
        key TEXT NOT NULL,
        ts TEXT NOT NULL,
        value_json TEXT NOT NULL,
        PRIMARY KEY (run_id, key)
    )
    """)

    con.commit()
    con.close()

init_db()

# ---------------------------
# Health check
# ---------------------------
@app.get("/api/health")
def health():
    return {"ok": True}

# ---------------------------
# PATCH ingest endpoint
# ---------------------------
@app.post("/api/runs/{run_id}/patch")
async def submit_patch(run_id: str, request: Request, _=Depends(require_key)):
    patch = await request.json()

    # Basic consistency checks
    if patch.get("run_id") != run_id:
        raise HTTPException(status_code=400, detail="run_id mismatch (URL vs body)")

    patch_id = patch.get("patch_id")
    ts = patch.get("ts")
    kv = patch.get("kv", {})
    events = patch.get("events", [])

    if not patch_id or not ts:
        raise HTTPException(status_code=400, detail="patch_id and ts are required")

    if not isinstance(kv, dict):
        raise HTTPException(status_code=400, detail="kv must be an object/dict")

    if not isinstance(events, list):
        raise HTTPException(status_code=400, detail="events must be a list")

    con = sqlite3.connect(DB_PATH)
    cur = con.cursor()

    # Deduplicate: if patch_id already exists, ignore safely
    cur.execute("SELECT 1 FROM patches WHERE patch_id = ?", (patch_id,))
    if cur.fetchone():
        con.close()
        return {"ok": True, "patch_id": patch_id, "deduped": True}

    # Store raw patch
    cur.execute(
        "INSERT INTO patches (patch_id, run_id, ts, patch_json) VALUES (?, ?, ?, ?)",
        (patch_id, run_id, ts, json.dumps(patch)),
    )

    # Store key updates (history) and snapshot (latest)
    for key, value_obj in kv.items():
        cur.execute(
            "INSERT INTO run_kv_events (run_id, ts, key, value_json, patch_id) VALUES (?, ?, ?, ?, ?)",
            (run_id, ts, key, json.dumps(value_obj), patch_id),
        )
        cur.execute(
            """
            INSERT INTO run_kv_current (run_id, key, ts, value_json)
            VALUES (?, ?, ?, ?)
            ON CONFLICT(run_id, key) DO UPDATE SET
              ts=excluded.ts,
              value_json=excluded.value_json
            """,
            (run_id, key, ts, json.dumps(value_obj)),
        )

    con.commit()
    con.close()

    # Broadcast to subscribers (Level 3 + any UI)
    broadcast({"type": "patch", "data": patch})

    return {"ok": True, "patch_id": patch_id, "deduped": False}

# ---------------------------
# SSE stream endpoint for Level 3
# ---------------------------
@app.get("/api/stream/patches")
def stream_patches(run_id: Optional[str] = None, _=Depends(require_key)):
    """
    Server-Sent Events stream.
    Level 3 connects here and receives patches as they are accepted.
    Optional filter by run_id.
    """
    q: queue.Queue = queue.Queue()

    with subscribers_lock:
        subscribers.append(q)

    def gen():
        try:
            # Initial hello
            yield "event: hello\ndata: {}\n\n"

            # Keepalive every ~15s so proxies don't kill SSE
            last_keepalive = time.time()

            while True:
                try:
                    msg = q.get(timeout=1.0)  # wait for broadcast
                    payload = json.loads(msg)

                    if run_id:
                        patch = payload.get("data", {})
                        if patch.get("run_id") != run_id:
                            continue

                    yield f"event: patch\ndata: {json.dumps(payload)}\n\n"
                except queue.Empty:
                    # no message, maybe send keepalive
                    now = time.time()
                    if now - last_keepalive > 15:
                        yield "event: keepalive\ndata: {}\n\n"
                        last_keepalive = now
        finally:
            with subscribers_lock:
                if q in subscribers:
                    subscribers.remove(q)

    return StreamingResponse(gen(), media_type="text/event-stream")

# ---------------------------
# Snapshot (latest values)
# ---------------------------
@app.get("/api/runs/{run_id}/state")
def get_state(run_id: str, prefix: Optional[str] = None, _=Depends(require_key)):
    con = sqlite3.connect(DB_PATH)
    cur = con.cursor()

    if prefix:
        cur.execute(
            "SELECT key, value_json, ts FROM run_kv_current WHERE run_id=? AND key LIKE ? ORDER BY key",
            (run_id, f"{prefix}%"),
        )
    else:
        cur.execute(
            "SELECT key, value_json, ts FROM run_kv_current WHERE run_id=? ORDER BY key",
            (run_id,),
        )

    rows = cur.fetchall()
    con.close()

    return {
        "run_id": run_id,
        "state": {k: {"value": json.loads(v), "ts": ts} for (k, v, ts) in rows}
    }

# ---------------------------
# Backfill (event history since timestamp)
# ---------------------------
@app.get("/api/runs/{run_id}/export_events")
def export_events(run_id: str, since_ts: Optional[str] = None, _=Depends(require_key)):
    con = sqlite3.connect(DB_PATH)
    cur = con.cursor()

    if since_ts:
        cur.execute(
            "SELECT ts, key, value_json, patch_id FROM run_kv_events WHERE run_id=? AND ts>? ORDER BY ts ASC",
            (run_id, since_ts),
        )
    else:
        cur.execute(
            "SELECT ts, key, value_json, patch_id FROM run_kv_events WHERE run_id=? ORDER BY ts ASC",
            (run_id,),
        )

    rows = cur.fetchall()
    con.close()

    return {
        "run_id": run_id,
        "events": [
            {"ts": ts, "key": key, "value": json.loads(val), "patch_id": pid}
            for (ts, key, val, pid) in rows
        ]
    }