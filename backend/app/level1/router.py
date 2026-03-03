from fastapi import APIRouter
from pydantic import BaseModel
from typing import Dict, List, Any

from app.level1.extractor import extract_candidates
from app.level1.commit import commit_candidates
from app.level1.ask_policy import next_question
from app.level1.state import derive_state
from app.level1.patches import Patch

router = APIRouter()

PATCH_STORE: Dict[str, List[Patch]] = {}

class IngestReq(BaseModel):
    run_id: str
    text: str

@router.post("/api/voice/ingest")
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
        "assistant_message": question or "",
        "state": state,
    }