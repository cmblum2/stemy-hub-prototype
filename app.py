# app.py
import os, json, sqlite3, time, uuid
from datetime import datetime, timezone
from typing import Any, Dict, Optional, List

from fastapi import FastAPI, HTTPException, Request, Query
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field

DB_PATH = os.getenv("STEMY_DB_PATH", "/data/stemy.db")
API_KEY = os.getenv("STEMY_API_KEY", "")
UI_TOKEN = os.getenv("STEMY_UI_TOKEN", "")

app = FastAPI(title="SteMy Hub", version="1.0")

from fastapi.middleware.cors import CORSMiddleware

app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:5173",
        "http://127.0.0.1:5173",
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ----------------------------
# Helpers
# ----------------------------
def iso_now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

def db() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_PATH, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    conn = db()
    cur = conn.cursor()

    cur.execute("""
    CREATE TABLE IF NOT EXISTS runs (
      run_id TEXT PRIMARY KEY,
      created_at TEXT NOT NULL,
      updated_at TEXT NOT NULL,
      status TEXT NOT NULL,
      title TEXT,
      meta_json TEXT
    );
    """)

    cur.execute("""
    CREATE TABLE IF NOT EXISTS patches (
      patch_id TEXT PRIMARY KEY,
      run_id TEXT NOT NULL,
      ts TEXT NOT NULL,
      patch_json TEXT NOT NULL
    );
    """)

    cur.execute("""
    CREATE TABLE IF NOT EXISTS events (
      id INTEGER PRIMARY KEY AUTOINCREMENT,
      run_id TEXT NOT NULL,
      ts TEXT NOT NULL,
      key TEXT NOT NULL,
      value_json TEXT NOT NULL,
      patch_id TEXT NOT NULL
    );
    """)

    cur.execute("""
    CREATE TABLE IF NOT EXISTS snapshot (
      run_id TEXT NOT NULL,
      key TEXT NOT NULL,
      ts TEXT NOT NULL,
      value_json TEXT NOT NULL,
      PRIMARY KEY (run_id, key)
    );
    """)

    conn.commit()
    conn.close()

@app.on_event("startup")
def _startup():
    init_db()

# ----------------------------
# Auth
# ----------------------------
def is_ui_request(req: Request) -> bool:
    # Any request coming from your UI can include X-UI-Token.
    # SSE from UI uses ?token=
    return True

def require_auth(req: Request, token_query: Optional[str] = None):
    """
    - Level 3 / external clients: must send X-API-Key == STEMY_API_KEY
    - UI:
        - Normal fetch calls: can send X-UI-Token == STEMY_UI_TOKEN
        - SSE calls: can pass ?token=STEMY_UI_TOKEN (EventSource can't set headers)
    """
    x_api = req.headers.get("x-api-key")
    x_ui = req.headers.get("x-ui-token")

    # UI token pathway
    if UI_TOKEN:
        if x_ui and x_ui == UI_TOKEN:
            return
        if token_query and token_query == UI_TOKEN:
            return

    # API key pathway
    if API_KEY:
        if x_api and x_api == API_KEY:
            return

    raise HTTPException(status_code=401, detail="Unauthorized")

# ----------------------------
# Models
# ----------------------------
class RunCreate(BaseModel):
    title: Optional[str] = None
    meta: Dict[str, Any] = Field(default_factory=dict)

class RunUpdate(BaseModel):
    status: Optional[str] = None  # "active" | "paused" | "complete"
    title: Optional[str] = None
    meta: Optional[Dict[str, Any]] = None

class PatchValue(BaseModel):
    v: Any
    t: str
    src: str = "human"
    q: str = "measured"

class Patch(BaseModel):
    run_id: str
    patch_id: str
    ts: str
    kv: Dict[str, PatchValue] = Field(default_factory=dict)
    events: List[Dict[str, Any]] = Field(default_factory=list)

# ----------------------------
# In-memory SSE subscribers (single machine MVP)
# ----------------------------
subscribers: Dict[str, List] = {}  # run_id -> list of queues

def publish(run_id: str, payload: dict):
    qs = subscribers.get(run_id, [])
    for q in qs:
        q.append(payload)

# ----------------------------
# Runs endpoints
# ----------------------------
@app.post("/api/runs")
def create_run(body: RunCreate, req: Request):
    require_auth(req)  # UI will send X-UI-Token
    run_id = f"RUN_{uuid.uuid4().hex[:10].upper()}"
    now = iso_now()
    conn = db()
    conn.execute(
        "INSERT INTO runs (run_id, created_at, updated_at, status, title, meta_json) VALUES (?, ?, ?, ?, ?, ?)",
        (run_id, now, now, "active", body.title, json.dumps(body.meta or {})),
    )
    conn.commit()
    conn.close()
    return {"run_id": run_id, "created_at": now, "status": "active"}

@app.get("/api/runs")
def list_runs(req: Request, limit: int = 50):
    require_auth(req)  # UI will send X-UI-Token
    conn = db()
    # include "stage" if present in snapshot
    rows = conn.execute(
        """
        SELECT r.run_id, r.created_at, r.updated_at, r.status, r.title,
               (SELECT json_extract(value_json, '$.v')
                FROM snapshot s
                WHERE s.run_id = r.run_id AND s.key = 'process.diff.stage'
                LIMIT 1) AS stage
        FROM runs r
        ORDER BY r.updated_at DESC
        LIMIT ?
        """,
        (limit,),
    ).fetchall()
    conn.close()
    return {"runs": [dict(x) for x in rows]}

@app.patch("/api/runs/{run_id}")
def update_run(run_id: str, body: RunUpdate, req: Request):
    require_auth(req)
    conn = db()
    row = conn.execute("SELECT * FROM runs WHERE run_id=?", (run_id,)).fetchone()
    if not row:
        conn.close()
        raise HTTPException(404, "Run not found")

    now = iso_now()
    new_status = body.status if body.status else row["status"]
    new_title = body.title if body.title is not None else row["title"]
    if body.meta is None:
        meta_json = row["meta_json"]
    else:
        meta_json = json.dumps(body.meta)

    conn.execute(
        "UPDATE runs SET status=?, title=?, meta_json=?, updated_at=? WHERE run_id=?",
        (new_status, new_title, meta_json, now, run_id),
    )
    conn.commit()
    conn.close()
    return {"ok": True, "run_id": run_id, "updated_at": now}

# ----------------------------
# Patch ingestion
# ----------------------------
@app.post("/api/runs/{run_id}/patch")
def ingest_patch(run_id: str, patch: Patch, req: Request):
    require_auth(req)  # Level 3 uses X-API-Key, UI can use X-UI-Token
    if patch.run_id != run_id:
        raise HTTPException(400, "run_id mismatch")

    conn = db()
    # dedupe
    exists = conn.execute("SELECT 1 FROM patches WHERE patch_id=?", (patch.patch_id,)).fetchone()
    if exists:
        conn.close()
        return {"ok": True, "patch_id": patch.patch_id, "deduped": True}

    patch_json = patch.model_dump()
    conn.execute(
        "INSERT INTO patches (patch_id, run_id, ts, patch_json) VALUES (?, ?, ?, ?)",
        (patch.patch_id, run_id, patch.ts, json.dumps(patch_json)),
    )

    # write key-level events + snapshot
    for k, vobj in patch.kv.items():
        vjson = vobj.model_dump()
        conn.execute(
            "INSERT INTO events (run_id, ts, key, value_json, patch_id) VALUES (?, ?, ?, ?, ?)",
            (run_id, patch.ts, k, json.dumps(vjson), patch.patch_id),
        )
        conn.execute(
            "INSERT INTO snapshot (run_id, key, ts, value_json) VALUES (?, ?, ?, ?) "
            "ON CONFLICT(run_id, key) DO UPDATE SET ts=excluded.ts, value_json=excluded.value_json",
            (run_id, k, patch.ts, json.dumps(vjson)),
        )

    # bump run updated_at
    conn.execute("UPDATE runs SET updated_at=? WHERE run_id=?", (iso_now(), run_id))
    conn.commit()
    conn.close()

    # publish SSE
    publish(run_id, {"type": "patch", "data": patch_json})

    return {"ok": True, "patch_id": patch.patch_id, "deduped": False}

# ----------------------------
# Patch history (NEW) - for UI to view all patches per run
# ----------------------------
@app.get("/api/runs/{run_id}/patches")
def list_patches(
    run_id: str,
    req: Request,
    limit: int = Query(500, ge=1, le=5000),
    offset: int = Query(0, ge=0),
    order: str = Query("asc", pattern="^(asc|desc)$"),
):
    """
    Returns patch history for a run so the UI can show:
    - all patch_ids
    - timestamps
    - the full stored patch JSON payloads

    Pagination included (limit/offset) to keep the UI fast for long runs.
    """
    require_auth(req)

    order_sql = "ASC" if order == "asc" else "DESC"

    conn = db()
    rows = conn.execute(
        f"""
        SELECT patch_id, ts, patch_json
        FROM patches
        WHERE run_id = ?
        ORDER BY ts {order_sql}
        LIMIT ? OFFSET ?
        """,
        (run_id, limit, offset),
    ).fetchall()
    conn.close()

    patches = []
    for r in rows:
        patch_payload = json.loads(r["patch_json"])
        patches.append(
            {
                "run_id": run_id,
                "patch_id": r["patch_id"],
                "ts": r["ts"],
                "patch": patch_payload,
            }
        )

    return {
        "run_id": run_id,
        "count": len(patches),
        "limit": limit,
        "offset": offset,
        "order": order,
        "patches": patches,
    }

# ----------------------------
# Snapshot
# ----------------------------
@app.get("/api/runs/{run_id}/state")
def get_state(run_id: str, req: Request):
    require_auth(req)
    conn = db()
    rows = conn.execute("SELECT key, ts, value_json FROM snapshot WHERE run_id=?", (run_id,)).fetchall()
    conn.close()
    state = {}
    for r in rows:
        state[r["key"]] = {"ts": r["ts"], "value": json.loads(r["value_json"])}
    return {"run_id": run_id, "state": state}

# ----------------------------
# Backfill
# ----------------------------
@app.get("/api/runs/{run_id}/export_events")
def export_events(run_id: str, req: Request, since_ts: Optional[str] = None, limit: int = 5000):
    require_auth(req)
    conn = db()
    if since_ts:
        rows = conn.execute(
            "SELECT ts, key, value_json, patch_id FROM events WHERE run_id=? AND ts>? ORDER BY ts ASC LIMIT ?",
            (run_id, since_ts, limit),
        ).fetchall()
    else:
        rows = conn.execute(
            "SELECT ts, key, value_json, patch_id FROM events WHERE run_id=? ORDER BY ts ASC LIMIT ?",
            (run_id, limit),
        ).fetchall()
    conn.close()
    return {
        "run_id": run_id,
        "since_ts": since_ts,
        "events": [
            {"ts": r["ts"], "key": r["key"], "value": json.loads(r["value_json"]), "patch_id": r["patch_id"]}
            for r in rows
        ],
    }

# ----------------------------
# SSE stream
# ----------------------------
@app.get("/api/stream/patches")
def stream_patches(req: Request, run_id: str, token: Optional[str] = None):
    # Allow either:
    # - Level 3: X-API-Key header
    # - UI: ?token=STEMY_UI_TOKEN
    require_auth(req, token_query=token)

    # simple in-memory queue
    q: List[dict] = []
    subscribers.setdefault(run_id, []).append(q)

    def gen():
        # hello
        yield "event: hello\ndata: {}\n\n"
        try:
            while True:
                if q:
                    msg = q.pop(0)
                    yield f"event: patch\ndata: {json.dumps(msg)}\n\n"
                else:
                    time.sleep(0.25)
        finally:
            # prevent ValueError if already removed
            if run_id in subscribers and q in subscribers[run_id]:
                subscribers[run_id].remove(q)

    return StreamingResponse(gen(), media_type="text/event-stream")