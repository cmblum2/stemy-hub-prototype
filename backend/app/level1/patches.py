from __future__ import annotations
from dataclasses import dataclass, asdict
from datetime import datetime, timezone
from typing import Any, Optional, Literal, Dict
import uuid

Source = Literal["voice", "manual"]
Op = Literal["set"]

def utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()

def new_id(prefix: str) -> str:
    return f"{prefix}_{uuid.uuid4().hex[:16]}"

@dataclass(frozen=True)
class Patch:
    patch_id: str
    run_id: str
    ts: str
    source: Source
    actor: str
    op: Op
    key: str
    value: Any
    confidence: float
    evidence: str
    note: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)

def make_patch(
    run_id: str,
    key: str,
    value: Any,
    confidence: float,
    evidence: str,
    source: Source = "voice",
    actor: str = "researcher",
    note: Optional[str] = None,
) -> Patch:
    return Patch(
        patch_id=new_id("patch"),
        run_id=run_id,
        ts=utc_now_iso(),
        source=source,
        actor=actor,
        op="set",
        key=key,
        value=value,
        confidence=float(confidence),
        evidence=evidence[:200],  # keep short
        note=note,
    )