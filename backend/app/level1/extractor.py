from __future__ import annotations
from dataclasses import dataclass
from typing import Any, List, Optional
import re
from .catalog import CATALOG

@dataclass
class Candidate:
    key: str
    value: Any
    confidence: float
    evidence: str
    reason: str

_uM = re.compile(r"(\d+(\.\d+)?)\s*(uM|µM|micromolar)\b", re.IGNORECASE)
_hr = re.compile(r"(\d+(\.\d+)?)\s*(h|hr|hrs|hours)\b", re.IGNORECASE)
_pct = re.compile(r"(\d+(\.\d+)?)\s*%")

def extract_candidates(text: str) -> List[Candidate]:
    t = text.strip()
    cands: List[Candidate] = []

    # CHIR conc: if "chir" mentioned + uM present → map to cm.chir_conc_uM
    if any(s in t.lower() for s in CATALOG["cm.chir_conc_uM"].synonyms):
        m = _uM.search(t)
        if m:
            cands.append(Candidate(
                key="cm.chir_conc_uM",
                value=float(m.group(1)),
                confidence=0.90,
                evidence=m.group(0),
                reason="Matched CHIR synonym + micromolar pattern"
            ))

    # CHIR duration: if "chir" mentioned + hours present → map to cm.chir_duration_hr
    if "chir" in t.lower():
        m = _hr.search(t)
        if m and ("for" in t.lower() or "duration" in t.lower() or "exposure" in t.lower()):
            cands.append(Candidate(
                key="cm.chir_duration_hr",
                value=float(m.group(1)),
                confidence=0.85,
                evidence=m.group(0),
                reason="Matched CHIR duration hours pattern"
            ))

    # Wnt inhibitor type
    if "iwp2" in t.lower():
        cands.append(Candidate("cm.wnt_inhibitor_type", "IWP2", 0.95, "IWP2", "Keyword match"))
    if "iwr" in t.lower():
        cands.append(Candidate("cm.wnt_inhibitor_type", "IWR-1", 0.90, "IWR", "Keyword match"))
    if "wnt inhibitor" in t.lower() and not any(x in t.lower() for x in ["iwp2", "iwr"]):
        cands.append(Candidate("cm.wnt_inhibitor_type", "WNT_INHIBITOR_UNSPECIFIED", 0.55, "wnt inhibitor", "Mentioned but unspecified"))

    # Wnt inhibitor dose
    if "iwp2" in t.lower() or "iwr" in t.lower() or "wnt inhibitor" in t.lower():
        m = _uM.search(t)
        if m:
            cands.append(Candidate("cm.wnt_inhibitor_dose_uM", float(m.group(1)), 0.80, m.group(0), "Dose pattern"))

    # % cTnT+
    if "ctnt" in t.lower() or "troponin" in t.lower():
        m = _pct.search(t)
        if m:
            cands.append(Candidate("qc.ctnt_percent", float(m.group(1)), 0.85, m.group(0), "Percent pattern"))

    return cands