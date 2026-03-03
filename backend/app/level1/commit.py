from __future__ import annotations
from typing import List, Tuple, Dict, Any
from .extractor import Candidate
from .patches import Patch, make_patch
from .catalog import CATALOG

THRESH = 0.75

def commit_candidates(run_id: str, text: str, cands: List[Candidate]) -> Tuple[List[Patch], List[Candidate]]:
    committed: List[Patch] = []
    needs_clarify: List[Candidate] = []

    for c in cands:
        vdef = CATALOG.get(c.key)
        if vdef and vdef.priority == "critical" and c.confidence < THRESH:
            needs_clarify.append(c)
            continue

        committed.append(make_patch(
            run_id=run_id,
            key=c.key,
            value=c.value,
            confidence=c.confidence,
            evidence=c.evidence,
            source="voice",
            actor="researcher",
            note=c.reason
        ))

    return committed, needs_clarify