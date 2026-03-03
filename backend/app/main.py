from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from typing import Dict, List, Any

from app.level1.extractor import extract_candidates
from app.level1.commit import commit_candidates
from app.level1.ask_policy import next_question
from app.level1.state import derive_state
from app.level1.patches import Patch

app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# In-memory storage for MVP. Replace with SQLite after it works.
PATCH_STORE: Dict[str, List[Patch]] = {}

class IngestReq(BaseModel):
    run_id: str
    text: str

@app.post("/api/voice/ingest")
def ingest(req: IngestReq) -> Dict[str, Any]:
    patches = PATCH_STORE.setdefault(req.run_id, [])
    cands = extract_candidates(req.text)
    committed, needs = commit_candidates(req.run_id, req.text, cands)
    patches.extend(committed)

    state = derive_state(patches)
    question = next_question(needs, state)

    return {
        "committed_patches": [p.to_dict() for p in committed],
        "needs_clarification": [c.__dict__ for c in needs],
        "assistant_message": question or "",   # empty means “no question”
        "state": state
    }

@app.get("/api/runs/{run_id}/patches")
def get_patches(run_id: str) -> Dict[str, Any]:
    patches = PATCH_STORE.get(run_id, [])
    return {"patches": [p.to_dict() for p in patches], "count": len(patches)}

@app.get("/api/runs/{run_id}/state")
def get_state(run_id: str) -> Dict[str, Any]:
    patches = PATCH_STORE.get(run_id, [])
    return {"state": derive_state(patches)}