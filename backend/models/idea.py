# backend/models/idea.py
from pydantic import BaseModel, Field
from typing import List

class ScaleEstimate(BaseModel):
    characters: int = 0
    environments: int = 0

class IdeaCard(BaseModel):
    concept: str
    hooks: List[str] = Field(default_factory=list)
    appeal: str = ""
    tags: List[str] = Field(default_factory=list)
    scale_estimate: ScaleEstimate = Field(default_factory=ScaleEstimate)
    rw_watchout: bool = False

class SurpriseResult(BaseModel):
    ideas: List[IdeaCard]