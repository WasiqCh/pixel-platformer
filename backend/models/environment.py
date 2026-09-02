from pydantic import BaseModel, Field, field_validator
from typing import List


def _to_strings(v):
    """AI sometimes returns objects instead of strings — normalize them."""
    if not isinstance(v, list):
        return []
    out = []
    for item in v:
        if isinstance(item, str):
            out.append(item)
        elif isinstance(item, dict):
            val = (item.get("name") or item.get("state") or
                   item.get("description") or item.get("text"))
            if val is None and item:
                val = next(iter(item.values()))
            out.append(str(val) if val is not None else "")
        else:
            out.append(str(item))
    return [s for s in out if s]


class EnvironmentItem(BaseModel):
    name: str
    elements: List[str]
    variations: List[str] = Field(default_factory=list)
    green_conflict: bool = False
    presence_sections: List[str] = Field(default_factory=list)

    @field_validator("elements", "variations", "presence_sections", mode="before")
    @classmethod
    def stringify_lists(cls, v):
        return _to_strings(v)


class EnvironmentExtractResult(BaseModel):
    environments: List[EnvironmentItem]