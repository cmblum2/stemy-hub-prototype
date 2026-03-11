from __future__ import annotations
from typing import List, Dict, Any
from .catalog import CATALOG
from .extractor import Candidate

THRESH = 0.75

# Lower number = ask about this sooner
CONFIRM_PRIORITY = {
    "diff.chir99021_concentration": 10,
    "cm.chir_conc_uM": 10,
    "maintenance.o2_percent": 20,
    "maintenance.co2_percent": 21,
    "diff.chir_exposure_time": 30,
    "cm.chir_duration_hr": 30,
    "cm.wnt_inhibitor_type": 40,
    "cm.wnt_inhibitor_dose_uM": 41,
    "qc.ctnt_percent": 50,
}


def _candidate_priority(c: Candidate) -> tuple:
    key = getattr(c, "key", "")
    conf = getattr(c, "confidence", 0.0)
    return (
        CONFIRM_PRIORITY.get(key, 999),
        conf,   # lower confidence first if same type
        key,
    )


def next_question(cands: List[Candidate], state: Dict[str, Any]) -> Dict[str, Any]:
    """
    Returns a structured follow-up object.

    Priority:
    1. Tentative candidates that need confirmation, in deterministic order.
    2. Low-confidence critical items.
    3. Otherwise no follow-up.
    """

    # 1) Tentative language -> confirm before commit
    tentative = [
        c for c in cands
        if getattr(c, "needs_confirmation", False)
    ]

    if tentative:
        tentative = sorted(tentative, key=_candidate_priority)
        c = tentative[0]

        vdef = CATALOG.get(c.key)
        label = vdef.label if vdef else c.key

        return {
            "followup_mode": "confirm_candidate",
            "pending_followup": {
                "type": "confirm_candidate",
                "key": c.key,
                "value": c.value,
                "confidence": c.confidence,
                "evidence": c.evidence,
                "question": f"I heard {label} as {c.value}, but that sounded approximate. Should I log that exactly?",
            },
        }

    # 2) Low-confidence critical items
    for c in sorted(cands, key=lambda x: x.confidence):
        vdef = CATALOG.get(c.key)
        if not vdef:
            continue

        if vdef.priority == "critical" and c.confidence < THRESH:
            if c.key == "cm.wnt_inhibitor_type":
                return {
                    "followup_mode": "clarify_variable",
                    "pending_followup": {
                        "type": "clarify_variable",
                        "key": c.key,
                        "question": "Which Wnt inhibitor did you use—IWP2 or IWR-1?",
                    },
                }

            return {
                "followup_mode": "clarify_variable",
                "pending_followup": {
                    "type": "clarify_variable",
                    "key": c.key,
                    "question": f"Quick check: can you confirm {vdef.label}?",
                },
            }

    return {
        "followup_mode": "none",
        "pending_followup": None,
    }