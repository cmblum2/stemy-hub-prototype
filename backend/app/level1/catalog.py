from __future__ import annotations
from dataclasses import dataclass
from typing import Callable, Any, Optional, List, Dict
import re

@dataclass(frozen=True)
class VarDef:
    id: str
    label: str
    vtype: str              # "float" | "int" | "str" | "bool" | "ts"
    unit: Optional[str]
    stage: str              # e.g. "D0-D1"
    priority: str           # "critical" | "useful" | "optional"
    synonyms: List[str]     # phrases to match in speech

CATALOG: Dict[str, VarDef] = {
    "cm.chir_conc_uM": VarDef(
        id="cm.chir_conc_uM",
        label="CHIR99021 concentration",
        vtype="float",
        unit="uM",
        stage="D0-D1",
        priority="critical",
        synonyms=["chir", "chir99021", "wnt agonist", "chir dose", "chir concentration"],
    ),
    "cm.chir_duration_hr": VarDef(
        id="cm.chir_duration_hr",
        label="CHIR exposure duration",
        vtype="float",
        unit="hr",
        stage="D0-D1",
        priority="critical",
        synonyms=["chir for", "chir exposure", "exposed to chir", "chir duration"],
    ),
    "cm.wnt_inhibitor_type": VarDef(
        id="cm.wnt_inhibitor_type",
        label="Wnt inhibitor type",
        vtype="str",
        unit=None,
        stage="D1-D3",
        priority="critical",
        synonyms=["iwp2", "iwr-1", "wnt inhibitor", "wnt inhibition"],
    ),
    "cm.wnt_inhibitor_dose_uM": VarDef(
        id="cm.wnt_inhibitor_dose_uM",
        label="Wnt inhibitor dose",
        vtype="float",
        unit="uM",
        stage="D1-D3",
        priority="critical",
        synonyms=["iwp2 dose", "iwr dose", "wnt inhibitor dose"],
    ),
    "qc.ctnt_percent": VarDef(
        id="qc.ctnt_percent",
        label="% cTnT+",
        vtype="float",
        unit="%",
        stage="D3-D20",
        priority="critical",
        synonyms=["ctnt", "cardiac troponin t", "ctnt positive", "ctnt percent"],
    ),
}