from __future__ import annotations
from dataclasses import dataclass, field
from typing import Any, List
import re
from .catalog import CATALOG


@dataclass
class Candidate:
    key: str
    value: Any
    confidence: float
    evidence: str
    reason: str
    needs_confirmation: bool = False
    uncertainty_flags: List[str] = field(default_factory=list)
    assertion_strength: str = "certain"


_uM = re.compile(r"(\d+(\.\d+)?)\s*(uM|µM|micromolar)\b", re.IGNORECASE)
_hr = re.compile(r"(\d+(\.\d+)?)\s*(h|hr|hrs|hours)\b", re.IGNORECASE)
_pct = re.compile(r"(\d+(\.\d+)?)\s*%")


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


def detect_uncertainty_flags(text: str) -> List[str]:
    lowered = text.lower()
    return [phrase for phrase in UNCERTAINTY_PHRASES if phrase in lowered]


def _set_candidate_meta(candidate: Candidate, text: str) -> Candidate:
    flags = detect_uncertainty_flags(text)
    needs_confirmation = len(flags) > 0
    assertion_strength = "tentative" if needs_confirmation else "certain"

    candidate.needs_confirmation = needs_confirmation
    candidate.uncertainty_flags = flags
    candidate.assertion_strength = assertion_strength
    return candidate


def extract_candidates(text: str) -> List[Candidate]:
    t = text.strip()
    tl = t.lower()
    cands: List[Candidate] = []

    # CHIR conc: if "chir" mentioned + uM present → map to cm.chir_conc_uM
    if any(s in tl for s in CATALOG["cm.chir_conc_uM"].synonyms):
        m = _uM.search(t)
        if m:
            cands.append(
                Candidate(
                    key="cm.chir_conc_uM",
                    value=float(m.group(1)),
                    confidence=0.90,
                    evidence=m.group(0),
                    reason="Matched CHIR synonym + micromolar pattern",
                )
            )

    # CHIR duration: if "chir" mentioned + hours present → map to cm.chir_duration_hr
    if "chir" in tl:
        m = _hr.search(t)
        if m and ("for" in tl or "duration" in tl or "exposure" in tl):
            cands.append(
                Candidate(
                    key="cm.chir_duration_hr",
                    value=float(m.group(1)),
                    confidence=0.85,
                    evidence=m.group(0),
                    reason="Matched CHIR duration hours pattern",
                )
            )

    # Wnt inhibitor type
    if "iwp2" in tl:
        cands.append(
            Candidate(
                key="cm.wnt_inhibitor_type",
                value="IWP2",
                confidence=0.95,
                evidence="IWP2",
                reason="Keyword match",
            )
        )

    if "iwr" in tl:
        cands.append(
            Candidate(
                key="cm.wnt_inhibitor_type",
                value="IWR-1",
                confidence=0.90,
                evidence="IWR",
                reason="Keyword match",
            )
        )

    if "wnt inhibitor" in tl and not any(x in tl for x in ["iwp2", "iwr"]):
        cands.append(
            Candidate(
                key="cm.wnt_inhibitor_type",
                value="WNT_INHIBITOR_UNSPECIFIED",
                confidence=0.55,
                evidence="wnt inhibitor",
                reason="Mentioned but unspecified",
            )
        )

    # Wnt inhibitor dose
    if "iwp2" in tl or "iwr" in tl or "wnt inhibitor" in tl:
        m = _uM.search(t)
        if m:
            cands.append(
                Candidate(
                    key="cm.wnt_inhibitor_dose_uM",
                    value=float(m.group(1)),
                    confidence=0.80,
                    evidence=m.group(0),
                    reason="Dose pattern",
                )
            )

    # % cTnT+
    if "ctnt" in tl or "troponin" in tl:
        m = _pct.search(t)
        if m:
            cands.append(
                Candidate(
                    key="qc.ctnt_percent",
                    value=float(m.group(1)),
                    confidence=0.85,
                    evidence=m.group(0),
                    reason="Percent pattern",
                )
            )

    # Oxygen %
    if "oxygen" in tl or "o2" in tl:
        m = _pct.search(t)
        if m:
            cands.append(
                Candidate(
                    key="maintenance.o2_percent",
                    value=float(m.group(1)),
                    confidence=0.90,
                    evidence=t,
                    reason="Matched oxygen/O2 mention + percent pattern",
                )
            )
        else:
            m_num = re.search(r"(\d+(\.\d+)?)", t)
            if m_num:
                cands.append(
                    Candidate(
                        key="maintenance.o2_percent",
                        value=float(m_num.group(1)),
                        confidence=0.90,
                        evidence=t,
                        reason="Matched oxygen/O2 mention + numeric pattern",
                    )
                )

    return [_set_candidate_meta(c, text) for c in cands]