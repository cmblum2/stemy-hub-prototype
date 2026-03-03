from __future__ import annotations
from typing import List, Optional, Dict, Any
from .catalog import CATALOG
from .extractor import Candidate

THRESH = 0.75

def next_question(cands: List[Candidate], state: Dict[str, Any]) -> Optional[str]:
    """
    Returns ONE clinician-style clarifying question if needed,
    otherwise returns None.
    """
    # Ask about lowest-confidence critical items first (but only 1 question)
    for c in sorted(cands, key=lambda x: x.confidence):
        vdef = CATALOG.get(c.key)
        if not vdef:
            continue

        if vdef.priority == "critical" and c.confidence < THRESH:
            if c.key == "cm.wnt_inhibitor_type":
                return "Which Wnt inhibitor did you use—**IWP2** or **IWR-1**?"
            return f"Quick check: can you confirm **{vdef.label}**?"

    return None