from pydantic import BaseModel, Field
from typing import List

class EnvironmentItem(BaseModel):
    name: str
    elements: List[str]
    variations: List[str] = Field(default_factory=list)
    green_conflict: bool = False
    presence_sections: List[str] = Field(default_factory=list)

class EnvironmentExtractResult(BaseModel):
    environments: List[EnvironmentItem]