from __future__ import annotations
from typing import Any, Dict, List, Tuple
from .patches import Patch

def derive_state(patches: List[Patch]) -> Dict[str, Any]:
    # last patch for each key wins
    latest: Dict[str, Tuple[str, Any]] = {}
    for p in patches:
        prev = latest.get(p.key)
        if prev is None or p.ts >= prev[0]:
            latest[p.key] = (p.ts, p.value)
    return {k: v for k, (_, v) in latest.items()}