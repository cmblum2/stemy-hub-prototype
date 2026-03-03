# backend/app/main.py
from fastapi import FastAPI, HTTPException, Query
from fastapi.responses import StreamingResponse
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from typing import List, Dict, Any, Optional, Set
import os
import sqlite3
import json
import asyncio
import time
from pathlib import Path

from app.level1.extractor import extract_candidates
from app.level1.commit import commit_candidates
from app.level1.ask_policy import next_question
from app.level1.state import derive_state
from app.level1.patches import Patch

app = FastAPI()

# ---------------------------
# CORS (MVP)
# ---------------------------
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # MVP; later restrict to your frontend domain
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Fly volume mount path (from fly.toml: destination="/data")
DB_PATH = os.environ.get("STEMY_DB_PATH", "/data/stemy.db")

# ---------------------------
# Variable Catalog (NEW)
# ---------------------------
# Put your file at: backend/app/variable_catalog.json
CATALOG_PATH = Path(__file__).parent / "variable_catalog.json"


def load_catalog() -> Dict[str, Any]:
    """
    Loads the variable catalog from disk.
    If missing/invalid, returns a safe empty catalog so the API still boots.
    """
    try:
        if not CATALOG_PATH.exists():
            return {"version": "1.0", "variables": [], "error": f"missing: {str(CATALOG_PATH)}"}
        with open(CATALOG_PATH, "r", encoding="utf-8") as f:
            data = json.load(f)
        if not isinstance(data, dict):
            return {"version": "1.0", "variables": [], "error": "catalog is not a JSON object"}
        if "variables" not in data or not isinstance(data["variables"], list):
            return {"version": data.get("version", "1.0"), "variables": [], "error": "catalog.variables missing/not a list"}
        return data
    except Exception as e:
        return {"version": "1.0", "variables": [], "error": f"failed to load catalog: {repr(e)}"}


def catalog_index(catalog: Dict[str, Any]) -> Dict[str, Dict[str, Any]]:
    """
    Index variables by id for quick lookup. Duplicate ids keep the first.
    """
    idx: Dict[str, Dict[str, Any]] = {}
    for v in catalog.get("variables", []):
        if not isinstance(v, dict):
            continue
        vid = (v.get("id") or "").strip()
        if not vid:
            continue
        if vid not in idx:
            idx[vid] = v
    return idx


VARIABLE_CATALOG: Dict[str, Any] = {}
CATALOG_BY_ID: Dict[str, Dict[str, Any]] = {}


# ---------------------------
# Request models
# ---------------------------
class CreateRunReq(BaseModel):
    run_id: str
    title: Optional[str] = None
    notes: Optional[str] = None


class IngestReq(BaseModel):
    run_id: str
    text: str


class RunMetaUpdateReq(BaseModel):
    title: Optional[str] = None
    notes: Optional[str] = None


# ---------------------------
# SSE broker (per-run)
# ---------------------------
# Each run_id -> set of asyncio.Queue subscribers
SUBSCRIBERS: Dict[str, Set[asyncio.Queue]] = {}


def _subscribe(run_id: str) -> asyncio.Queue:
    q: asyncio.Queue = asyncio.Queue(maxsize=200)
    SUBSCRIBERS.setdefault(run_id, set()).add(q)
    return q


def _unsubscribe(run_id: str, q: asyncio.Queue) -> None:
    subs = SUBSCRIBERS.get(run_id)
    if not subs:
        return
    subs.discard(q)
    if not subs:
        SUBSCRIBERS.pop(run_id, None)


def _publish(run_id: str, event: Dict[str, Any]) -> None:
    subs = SUBSCRIBERS.get(run_id)
    if not subs:
        return
    # best-effort broadcast
    for q in list(subs):
        try:
            q.put_nowait(event)
        except Exception:
            # queue full or closed - drop
            pass


# ---------------------------
# SQLite helpers
# ---------------------------
def connect() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_PATH, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    return conn


def init_db() -> None:
    """
    Create tables if missing, and MIGRATE older tables on your Fly volume
    (so deploys don't crash with 'no such column confidence' etc.)
    """
    os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)
    conn = connect()
    try:
        conn.execute("PRAGMA journal_mode=WAL;")

        # Ensure runs table exists
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS runs (
                run_id TEXT PRIMARY KEY,
                created_ts TEXT NOT NULL,
                updated_ts TEXT NOT NULL,
                title TEXT,
                notes TEXT
            );
            """
        )

        # Ensure patches table exists (new shape)
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS patches (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                run_id TEXT NOT NULL,
                ts TEXT NOT NULL,
                patch_id TEXT NOT NULL,
                confidence REAL NOT NULL DEFAULT 1.0,
                patch_json TEXT NOT NULL
            );
            """
        )

        # MIGRATE older DBs that already had 'patches' but missing columns
        cols = conn.execute("PRAGMA table_info(patches);").fetchall()
        existing = {c["name"] for c in cols}

        # add missing columns safely
        if "run_id" not in existing:
            conn.execute("ALTER TABLE patches ADD COLUMN run_id TEXT;")
        if "ts" not in existing:
            conn.execute("ALTER TABLE patches ADD COLUMN ts TEXT;")
        if "patch_id" not in existing:
            conn.execute("ALTER TABLE patches ADD COLUMN patch_id TEXT;")
        if "confidence" not in existing:
            conn.execute("ALTER TABLE patches ADD COLUMN confidence REAL NOT NULL DEFAULT 1.0;")
        if "patch_json" not in existing:
            conn.execute("ALTER TABLE patches ADD COLUMN patch_json TEXT;")

        # Indexes (do NOT reference 'id' in index definitions for compatibility)
        conn.execute("CREATE INDEX IF NOT EXISTS idx_patches_run_ts ON patches(run_id, ts, patch_id);")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_patches_run_conf ON patches(run_id, confidence);")

        conn.commit()
    finally:
        conn.close()


@app.on_event("startup")
def startup() -> None:
    global VARIABLE_CATALOG, CATALOG_BY_ID
    init_db()

    # Load catalog on boot (NEW)
    VARIABLE_CATALOG = load_catalog()
    CATALOG_BY_ID = catalog_index(VARIABLE_CATALOG)


def _now_iso_z() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())


def upsert_run_meta(run_id: str) -> None:
    """Create run row if missing; update updated_ts always."""
    rid = (run_id or "").strip()
    if not rid:
        return

    now = _now_iso_z()
    conn = connect()
    try:
        row = conn.execute("SELECT run_id FROM runs WHERE run_id = ?", (rid,)).fetchone()
        if row is None:
            conn.execute(
                "INSERT INTO runs (run_id, created_ts, updated_ts, title, notes) VALUES (?, ?, ?, NULL, NULL)",
                (rid, now, now),
            )
        else:
            conn.execute("UPDATE runs SET updated_ts = ? WHERE run_id = ?", (now, rid))
        conn.commit()
    finally:
        conn.close()


def save_committed_patches(run_id: str, committed: List[Patch]) -> None:
    """Append-only patch persistence."""
    if not committed:
        return

    upsert_run_meta(run_id)

    conn = connect()
    try:
        rows = []
        for p in committed:
            d = p.to_dict()
            rows.append(
                (
                    run_id,
                    d.get("ts", _now_iso_z()),
                    d.get("patch_id", ""),
                    float(d.get("confidence", 1.0)),
                    json.dumps(d),
                )
            )

        conn.executemany(
            "INSERT INTO patches (run_id, ts, patch_id, confidence, patch_json) VALUES (?, ?, ?, ?, ?)",
            rows,
        )
        conn.commit()
    finally:
        conn.close()


def load_patch_dicts(run_id: str, limit: int = 5000, min_conf: float = 0.0) -> List[Dict[str, Any]]:
    conn = connect()
    try:
        rows = conn.execute(
            """
            SELECT patch_json
            FROM patches
            WHERE run_id = ? AND confidence >= ?
            ORDER BY ts ASC, rowid ASC
            LIMIT ?
            """,
            (run_id, float(min_conf), int(limit)),
        ).fetchall()

        out: List[Dict[str, Any]] = []
        for r in rows:
            pj = r["patch_json"]
            if not pj:
                continue
            try:
                out.append(json.loads(pj))
            except Exception:
                # ignore corrupted row
                continue
        return out
    finally:
        conn.close()


# ---------------------------
# Routes
# ---------------------------
@app.get("/")
def root():
    return {"ok": True}


@app.get("/api/debug/whoami")
def whoami():
    return {
        "file": __file__,
        "cwd": os.getcwd(),
        "db_path": DB_PATH,
        "catalog_path": str(CATALOG_PATH),
        "catalog_loaded": bool(VARIABLE_CATALOG.get("variables")),
        "catalog_count": len(VARIABLE_CATALOG.get("variables", [])),
        "catalog_error": VARIABLE_CATALOG.get("error"),
    }


# NEW: expose catalog so frontend can confirm all variables exist
@app.get("/api/catalog")
def get_catalog():
    return VARIABLE_CATALOG


# NEW: quick lookup by id (handy for UI + debugging)
@app.get("/api/catalog/{var_id}")
def get_catalog_var(var_id: str):
    vid = (var_id or "").strip()
    if not vid:
        raise HTTPException(status_code=400, detail="var_id required")
    v = CATALOG_BY_ID.get(vid)
    if not v:
        raise HTTPException(status_code=404, detail="variable not found in catalog")
    return {"variable": v}


# NEW: optional reload endpoint for development (no restart needed)
@app.post("/api/catalog/reload")
def reload_catalog():
    global VARIABLE_CATALOG, CATALOG_BY_ID
    VARIABLE_CATALOG = load_catalog()
    CATALOG_BY_ID = catalog_index(VARIABLE_CATALOG)
    return {
        "ok": True,
        "catalog_count": len(VARIABLE_CATALOG.get("variables", [])),
        "catalog_error": VARIABLE_CATALOG.get("error"),
    }


@app.post("/api/runs")
def create_run(req: CreateRunReq) -> Dict[str, Any]:
    run_id = (req.run_id or "").strip()
    if not run_id:
        raise HTTPException(status_code=400, detail="run_id required")

    # ensure run exists + bump updated_ts
    upsert_run_meta(run_id)

    # set optional title/notes
    if req.title is not None or req.notes is not None:
        conn = connect()
        try:
            if req.title is not None:
                conn.execute("UPDATE runs SET title = ? WHERE run_id = ?", (req.title, run_id))
            if req.notes is not None:
                conn.execute("UPDATE runs SET notes = ? WHERE run_id = ?", (req.notes, run_id))
            conn.commit()
        finally:
            conn.close()

    conn = connect()
    try:
        row = conn.execute("SELECT * FROM runs WHERE run_id = ?", (run_id,)).fetchone()
        return {"run": dict(row) if row else None}
    finally:
        conn.close()


@app.post("/api/voice/ingest")
def ingest(req: IngestReq) -> Dict[str, Any]:
    run_id = (req.run_id or "").strip()
    text = (req.text or "").strip()

    if not run_id:
        raise HTTPException(status_code=400, detail="run_id required")
    if not text:
        raise HTTPException(status_code=400, detail="text required")

    # ensure run exists
    upsert_run_meta(run_id)

    # Load existing patches for state derivation (unfiltered)
    existing_dicts = load_patch_dicts(run_id, min_conf=0.0)
    existing = [Patch(**d) for d in existing_dicts]

    # Extract + commit (your logic)
    cands = extract_candidates(text)
    committed, needs = commit_candidates(run_id, text, cands)

    # Persist committed patches (append-only)
    save_committed_patches(run_id, committed)

    # SSE events per committed patch
    for p in committed:
        _publish(run_id, {"type": "patch", "patch": p.to_dict()})

    # Derive state from all patches
    all_patches = existing + committed
    state = derive_state(all_patches)
    question = next_question(needs, state)

    _publish(run_id, {"type": "state", "state": state})

    return {
        "committed_patches": [p.to_dict() for p in committed],
        "needs_clarification": [c.__dict__ for c in needs],
        "assistant_message": question or "",
        "state": state,
    }


@app.get("/api/runs")
def list_runs(limit: int = 200) -> Dict[str, Any]:
    conn = connect()
    try:
        rows = conn.execute(
            """
            SELECT
              r.run_id,
              r.created_ts,
              r.updated_ts,
              r.title,
              r.notes,
              COALESCE(p.patch_count, 0) AS patch_count,
              COALESCE(p.last_ts, r.updated_ts) AS last_ts
            FROM runs r
            LEFT JOIN (
              SELECT run_id, COUNT(*) AS patch_count, MAX(ts) AS last_ts
              FROM patches
              GROUP BY run_id
            ) p
            ON p.run_id = r.run_id
            ORDER BY r.updated_ts DESC
            LIMIT ?
            """,
            (int(limit),),
        ).fetchall()
        return {"runs": [dict(r) for r in rows], "count": len(rows)}
    finally:
        conn.close()


@app.patch("/api/runs/{run_id}")
def update_run_meta(run_id: str, req: RunMetaUpdateReq) -> Dict[str, Any]:
    rid = (run_id or "").strip()
    if not rid:
        raise HTTPException(status_code=400, detail="run_id required")

    conn = connect()
    try:
        row = conn.execute("SELECT run_id FROM runs WHERE run_id = ?", (rid,)).fetchone()
        if row is None:
            raise HTTPException(status_code=404, detail="Run not found")

        if req.title is not None:
            conn.execute("UPDATE runs SET title = ? WHERE run_id = ?", (req.title, rid))
        if req.notes is not None:
            conn.execute("UPDATE runs SET notes = ? WHERE run_id = ?", (req.notes, rid))

        # bump updated_ts
        now = _now_iso_z()
        conn.execute("UPDATE runs SET updated_ts = ? WHERE run_id = ?", (now, rid))

        conn.commit()
        out = conn.execute("SELECT * FROM runs WHERE run_id = ?", (rid,)).fetchone()
        return {"run": dict(out) if out else None}
    finally:
        conn.close()


@app.delete("/api/runs/{run_id}")
def delete_run(run_id: str) -> Dict[str, Any]:
    rid = (run_id or "").strip()
    if not rid:
        raise HTTPException(status_code=400, detail="run_id required")

    conn = connect()
    try:
        conn.execute("DELETE FROM patches WHERE run_id = ?", (rid,))
        cur = conn.execute("DELETE FROM runs WHERE run_id = ?", (rid,))
        conn.commit()
        SUBSCRIBERS.pop(rid, None)
        return {"deleted": True, "run_id": rid, "rows": cur.rowcount}
    finally:
        conn.close()


@app.get("/api/runs/{run_id}/patches")
def get_patches(
    run_id: str,
    limit: int = 5000,
    min_conf: float = Query(0.0, ge=0.0, le=1.0),
) -> Dict[str, Any]:
    rid = (run_id or "").strip()
    if not rid:
        raise HTTPException(status_code=400, detail="run_id required")

    patch_dicts = load_patch_dicts(rid, limit=limit, min_conf=min_conf)
    return {"patches": patch_dicts, "count": len(patch_dicts), "min_conf": float(min_conf)}


@app.get("/api/runs/{run_id}/state")
def get_state(
    run_id: str,
    limit: int = 5000,
    min_conf: float = Query(0.0, ge=0.0, le=1.0),
) -> Dict[str, Any]:
    rid = (run_id or "").strip()
    if not rid:
        raise HTTPException(status_code=400, detail="run_id required")

    patch_dicts = load_patch_dicts(rid, limit=limit, min_conf=min_conf)
    patches = [Patch(**d) for d in patch_dicts]
    return {"state": derive_state(patches), "min_conf": float(min_conf)}


@app.get("/api/runs/{run_id}/stream")
async def stream_run(run_id: str):
    """
    SSE stream for a run.
    Sends:
      - {type:"patch", patch:{...}}
      - {type:"state", state:{...}}
      - keepalive pings
    """
    rid = (run_id or "").strip()
    if not rid:
        raise HTTPException(status_code=400, detail="run_id required")

    q = _subscribe(rid)

    async def gen():
        try:
            yield "event: hello\ndata: {}\n\n"
            while True:
                try:
                    event = await asyncio.wait_for(q.get(), timeout=20.0)
                    yield f"data: {json.dumps(event)}\n\n"
                except asyncio.TimeoutError:
                    yield "event: ping\ndata: {}\n\n"
        finally:
            _unsubscribe(rid, q)

    return StreamingResponse(gen(), media_type="text/event-stream")