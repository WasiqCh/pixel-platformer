from pydantic import BaseModel, Field
from typing import List

class VariantItem(BaseModel):
    character_name: str
    label: str
    delta: str
    from_section: str = ""
    to_section: str = ""
    evidence: str = ""
    confidence: float = 0.8
    rare: bool = False      # ≤2 beats → one-off candidate

class VariantExtractResult(BaseModel):
    variants: List[VariantItem]