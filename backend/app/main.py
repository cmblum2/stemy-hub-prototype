from fastapi import FastAPI, HTTPException, Query, UploadFile, File
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
import tempfile
from types import SimpleNamespace
from openai import OpenAI

from app.level1.extractor import extract_candidates
from app.level1.commit import commit_candidates
from app.level1.ask_policy import next_question
from app.level1.state import derive_state
from app.level1.patches import Patch, make_patch
from app.catalog_matcher import CatalogMatcher


app = FastAPI()
client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))

# ---------------------------
# CORS
# ---------------------------

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ---------------------------
# Database
# ---------------------------

DB_PATH = os.environ.get("STEMY_DB_PATH", "/data/stemy.db")
DATA_DIR = os.path.dirname(DB_PATH) or "/data"

# ---------------------------
# Catalog
# ---------------------------

CATALOG_PATH = Path(__file__).parent / "variable_catalog.json"

VARIABLE_CATALOG: Dict[str, Any] = {}
CATALOG_BY_ID: Dict[str, Dict[str, Any]] = {}
CATALOG_MATCHER: CatalogMatcher = None

# ---------------------------
# In-memory pending followups
# ---------------------------

PENDING_FOLLOWUPS: Dict[str, Dict[str, Any]] = {}

YES_WORDS = {"yes", "yeah", "yep", "correct", "confirm", "log it", "that's right", "do it"}
NO_WORDS = {"no", "nope", "incorrect", "don't log it", "not exactly", "wrong"}

UNCERTAINTY_PHRASES = [
    "maybe",
    "around",
    "about",
    "approximately",
    "approx",
    "kind of",
    "sort of",
    "i think",
    "probably",
    "roughly",
    "seems like",
    "looks like",
    "almost",
    "close to",
]


def is_yes(text: str) -> bool:
    t = (text or "").strip().lower()
    return any(word in t for word in YES_WORDS)


def is_no(text: str) -> bool:
    t = (text or "").strip().lower()
    return any(word in t for word in NO_WORDS)


def detect_uncertainty_flags(text: str) -> List[str]:
    lowered = (text or "").lower()
    return [phrase for phrase in UNCERTAINTY_PHRASES if phrase in lowered]


def apply_uncertainty_to_candidates(
    candidates: List[Dict[str, Any]],
    transcript: str
) -> List[Dict[str, Any]]:
    flags = detect_uncertainty_flags(transcript)
    if not flags:
        return candidates or []

    out = []
    for c in candidates or []:
        cc = dict(c)
        cc["needs_confirmation"] = True
        cc["uncertainty_flags"] = flags
        cc["assertion_strength"] = "tentative"
        out.append(cc)
    return out


def load_catalog():
    try:
        with open(CATALOG_PATH, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {"variables": []}


def catalog_index(catalog):
    idx = {}
    for v in catalog.get("variables", []):
        vid = (v.get("id") or "").strip()
        if vid:
            idx[vid] = v
    return idx


# ---------------------------
# Models
# ---------------------------

class CreateRunReq(BaseModel):
    run_id: str
    title: Optional[str] = None
    notes: Optional[str] = None


class VoiceCommitRequest(BaseModel):
    run_id: str
    transcript: str
    patch_candidates: List[Dict[str, Any]]


class VoiceReasonRequest(BaseModel):
    run_id: str
    transcript: str


class ManualPatchReq(BaseModel):
    key: str
    value: Any
    actor: Optional[str] = "researcher"
    source: Optional[str] = "manual"
    note: Optional[str] = None


# ---------------------------
# DB helpers
# ---------------------------

def connect():
    conn = sqlite3.connect(DB_PATH, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    return conn


def init_db():
    os.makedirs(DATA_DIR, exist_ok=True)

    conn = connect()

    conn.execute("""
    CREATE TABLE IF NOT EXISTS runs(
        run_id TEXT PRIMARY KEY,
        created_ts TEXT,
        updated_ts TEXT,
        title TEXT,
        notes TEXT
    )
    """)

    conn.execute("""
    CREATE TABLE IF NOT EXISTS patches(
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        run_id TEXT,
        ts TEXT,
        patch_id TEXT,
        confidence REAL,
        patch_json TEXT
    )
    """)

    conn.commit()
    conn.close()


def now():
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())


def upsert_run_meta(run_id):
    conn = connect()

    row = conn.execute(
        "SELECT run_id FROM runs WHERE run_id=?",
        (run_id,)
    ).fetchone()

    if not row:
        conn.execute(
            "INSERT INTO runs VALUES (?,?,?,?,?)",
            (run_id, now(), now(), None, None)
        )
    else:
        conn.execute(
            "UPDATE runs SET updated_ts=? WHERE run_id=?",
            (now(), run_id)
        )

    conn.commit()
    conn.close()


# ---------------------------
# Patch persistence
# ---------------------------

def save_committed_patches(run_id, committed):
    if not committed:
        return

    conn = connect()
    rows = []

    for p in committed:
        d = p.to_dict()
        rows.append((
            run_id,
            d.get("ts"),
            d.get("patch_id"),
            float(d.get("confidence", 1.0)),
            json.dumps(d)
        ))

    conn.executemany(
        "INSERT INTO patches(run_id,ts,patch_id,confidence,patch_json) VALUES(?,?,?,?,?)",
        rows
    )

    conn.commit()
    conn.close()


def load_patch_dicts(run_id, limit=5000, min_conf=0.0):
    conn = connect()

    rows = conn.execute(
        """
        SELECT patch_json
        FROM patches
        WHERE run_id=? AND confidence>=?
        ORDER BY ts ASC
        LIMIT ?
        """,
        (run_id, min_conf, limit)
    ).fetchall()

    conn.close()

    out = []
    for r in rows:
        try:
            out.append(json.loads(r["patch_json"]))
        except Exception:
            pass

    return out


# ---------------------------
# Startup
# ---------------------------

@app.on_event("startup")
def startup():
    global VARIABLE_CATALOG, CATALOG_BY_ID, CATALOG_MATCHER

    init_db()

    VARIABLE_CATALOG = load_catalog()
    CATALOG_BY_ID = catalog_index(VARIABLE_CATALOG)

    CATALOG_MATCHER = CatalogMatcher(VARIABLE_CATALOG["variables"])


# ---------------------------
# Reasoning prompt
# ---------------------------

def build_voice_reason_prompt(run_id: str, transcript: str, state: dict, recent_patches: list) -> str:
    catalog_vars = [
        v["id"]
        for v in VARIABLE_CATALOG.get("variables", [])
        if "id" in v
    ]

    catalog_text = "\n".join(catalog_vars)

    return f"""
You are StemY, an AI research assistant that logs experiment variables.

You must extract experiment variables from researcher speech.

Use ONLY variables from this catalog.

Available catalog variables:

{catalog_text}

When selecting a variable you MUST return the exact catalog id.

Examples:

"seeding density"
→ maintenance.seeding_density

"incubator temperature"
→ maintenance.media_temperature

"CO2 level"
→ maintenance.co2_percent

"oxygen concentration"
→ maintenance.o2_percent

"substrate stiffness"
→ maintenance.elastic_modulus


Confidence scoring rules:

0.95–1.0 → variable explicitly stated with clear unit
0.85–0.95 → clearly implied variable
0.70–0.85 → reasonable inference
<0.70 → uncertain


Return STRICT JSON only in this format:

{{
  "assistant_text": "string",

  "patch_candidates": [
    {{
      "key": "catalog_variable_id",
      "value": any valid JSON value,
      "confidence": 0.0,
      "evidence": "quote from transcript",
      "needs_confirmation": false
    }}
  ],

  "followup_mode": "none | immediate | deferred",

  "pending_followup": null
}}


If no variable applies return:

"patch_candidates": []


Current run id:
{run_id}

Current derived state:
{json.dumps(state, indent=2)}

Recent patches:
{json.dumps(recent_patches, indent=2)}

Researcher transcript:
{transcript}
"""


# ---------------------------
# Reasoning
# ---------------------------

@app.post("/api/voice/reason")
async def voice_reason(req: VoiceReasonRequest):
    try:
        patch_dicts = load_patch_dicts(req.run_id)
        patches = [Patch(**d) for d in patch_dicts]
        state = derive_state(patches)

        prompt = build_voice_reason_prompt(
            req.run_id,
            req.transcript,
            state,
            patch_dicts[-10:]
        )

        response = client.responses.create(
            model=os.getenv("VOICE_REASON_MODEL", "gpt-5"),
            input=prompt
        )

        raw_text = (response.output_text or "").strip()

        if not raw_text:
            return {
                "ok": False,
                "error": "Model returned empty output"
            }

        try:
            parsed = json.loads(raw_text)
        except Exception:
            return {
                "ok": False,
                "error": f"Model returned non-JSON output: {raw_text}"
            }

        patch_candidates = apply_uncertainty_to_candidates(
            parsed.get("patch_candidates", []) or [],
            req.transcript
        )
        parsed["patch_candidates"] = patch_candidates

        followup = next_question(
            [SimpleNamespace(**c) for c in patch_candidates],
            state
        )

        if followup.get("followup_mode") == "confirm_candidate":
            assistant_text = followup["pending_followup"]["question"]
        else:
            assistant_text = parsed.get("assistant_text", "No structured update identified.")

        parsed["assistant_text"] = assistant_text
        parsed["followup_mode"] = followup.get("followup_mode", "none")
        parsed["pending_followup"] = followup.get("pending_followup")

        return {
            "ok": True,
            "reasoning": parsed
        }

    except Exception as e:
        return {
            "ok": False,
            "error": str(e)
        }


# ---------------------------
# Commit candidates
# ---------------------------

@app.post("/api/voice/commit_candidates")
async def voice_commit_candidates(req: VoiceCommitRequest):
    try:
        rid = (req.run_id or "").strip()

        if not rid:
            raise HTTPException(status_code=400, detail="run_id required")

        upsert_run_meta(rid)

        threshold = float(os.getenv("VOICE_AUTO_COMMIT_THRESHOLD", "0.70"))

        normalized_candidates = apply_uncertainty_to_candidates(
            req.patch_candidates or [],
            req.transcript
        )

        # 1) Handle pending confirmation first
        pending = PENDING_FOLLOWUPS.get(rid)

        if pending and pending.get("type") == "confirm_candidate":
            transcript_text = (req.transcript or "").strip()

            if is_yes(transcript_text):
                c = pending["candidate"]

                raw_key = (c.get("key") or "").strip()
                confidence = float(c.get("confidence", 0))

                if raw_key in CATALOG_BY_ID:
                    key = raw_key
                    similarity = 1.0
                else:
                    matched_key, similarity = CATALOG_MATCHER.match(raw_key)

                    if similarity > 0.72:
                        key = matched_key
                        confidence *= similarity
                    else:
                        key = raw_key

                    confidence = min(confidence, 0.98)

                    if similarity < 0.8:
                        confidence *= 0.85

                if key not in CATALOG_BY_ID:
                    PENDING_FOLLOWUPS.pop(rid, None)
                    return {
                        "ok": False,
                        "error": f"Pending candidate variable not in catalog: {key}"
                    }

                patch = make_patch(
                    run_id=rid,
                    key=key,
                    value=c.get("value"),
                    confidence=confidence,
                    evidence=c.get("evidence", ""),
                    source="voice",
                    actor="researcher",
                    note=c.get("note")
                )

                committed = [patch]
                save_committed_patches(rid, committed)
                PENDING_FOLLOWUPS.pop(rid, None)

                patch_dicts = load_patch_dicts(rid)
                patches = [Patch(**d) for d in patch_dicts]
                state = derive_state(patches)

                return {
                    "ok": True,
                    "assistant": f"Logged {key} = {c.get('value')}.",
                    "committed_patches": [p.to_dict() for p in committed],
                    "state": state,
                    "skipped_candidates": [],
                    "followup": {
                        "followup_mode": "none",
                        "pending_followup": None
                    }
                }

            if is_no(transcript_text):
                PENDING_FOLLOWUPS.pop(rid, None)

                patch_dicts = load_patch_dicts(rid)
                patches = [Patch(**d) for d in patch_dicts]
                state = derive_state(patches)

                return {
                    "ok": True,
                    "assistant": "Okay, I did not log it. Please provide the exact value.",
                    "committed_patches": [],
                    "state": state,
                    "skipped_candidates": [],
                    "followup": {
                        "followup_mode": "await_exact_value",
                        "pending_followup": None
                    }
                }

        # 2) Normal commit flow
        committed = []
        skipped = []
        tentative_candidates = []

        for c in normalized_candidates:
            if c.get("needs_confirmation", False):
                skipped.append({
                    "candidate": c,
                    "reason": "needs confirmation before commit"
                })
                tentative_candidates.append(c)
                continue

            raw_key = (c.get("key") or "").strip()
            confidence = float(c.get("confidence", 0))

            if not raw_key:
                skipped.append({
                    "candidate": c,
                    "reason": "missing key"
                })
                continue

            if raw_key in CATALOG_BY_ID:
                key = raw_key
                similarity = 1.0
            else:
                matched_key, similarity = CATALOG_MATCHER.match(raw_key)

                if similarity > 0.72:
                    key = matched_key
                    confidence *= similarity
                else:
                    key = raw_key

                confidence = min(confidence, 0.98)

                if similarity < 0.8:
                    confidence *= 0.85

            if key not in CATALOG_BY_ID:
                skipped.append({
                    "candidate": c,
                    "reason": f"LLM returned variable not in catalog: {key}"
                })
                continue

            if confidence < threshold:
                skipped.append({
                    "candidate": c,
                    "reason": f"confidence too low: {confidence:.3f} < {threshold}"
                })
                continue

            patch = make_patch(
                run_id=rid,
                key=key,
                value=c.get("value"),
                confidence=confidence,
                evidence=c.get("evidence", ""),
                source="voice",
                actor="researcher",
                note=c.get("note")
            )

            committed.append(patch)

        save_committed_patches(rid, committed)

        patch_dicts = load_patch_dicts(rid)
        patches = [Patch(**d) for d in patch_dicts]
        state = derive_state(patches)

        followup = next_question(
            [SimpleNamespace(**c) for c in normalized_candidates],
            state
        )

        # Store exactly the candidate that the followup is asking about
        if (
            followup.get("followup_mode") == "confirm_candidate"
            and followup.get("pending_followup")
        ):
            pf = followup["pending_followup"]

            matching_candidate = next(
                (
                    c for c in tentative_candidates
                    if c.get("key") == pf.get("key")
                    and c.get("value") == pf.get("value")
                ),
                None,
            )

            if matching_candidate is not None:
                PENDING_FOLLOWUPS[rid] = {
                    "type": "confirm_candidate",
                    "candidate": matching_candidate
                }

        return {
            "ok": True,
            "committed_patches": [p.to_dict() for p in committed],
            "state": state,
            "skipped_candidates": skipped,
            "followup": followup
        }

    except Exception as e:
        return {
            "ok": False,
            "error": str(e)
        }


@app.get("/api/runs")
def list_runs():
    conn = connect()

    rows = conn.execute(
        """
        SELECT run_id, created_ts, updated_ts, title, notes
        FROM runs
        ORDER BY created_ts DESC
        """
    ).fetchall()

    conn.close()

    return {
        "runs": [dict(r) for r in rows]
    }


@app.post("/api/runs")
def create_run(req: CreateRunReq):
    rid = (req.run_id or "").strip()

    if not rid:
        raise HTTPException(status_code=400, detail="run_id required")

    conn = connect()

    conn.execute(
        """
        INSERT OR REPLACE INTO runs(run_id,created_ts,updated_ts,title,notes)
        VALUES(?,?,?,?,?)
        """,
        (
            rid,
            now(),
            now(),
            req.title,
            req.notes
        )
    )

    conn.commit()
    conn.close()

    return {"ok": True, "run_id": rid}


@app.get("/api/runs/{run_id}/patches")
def get_patches(run_id: str):
    patch_dicts = load_patch_dicts(run_id)

    return {
        "patches": patch_dicts
    }


@app.get("/api/runs/{run_id}/state")
def get_state(run_id: str):
    patch_dicts = load_patch_dicts(run_id)
    patches = [Patch(**d) for d in patch_dicts]
    state = derive_state(patches)

    return {
        "state": state
    }