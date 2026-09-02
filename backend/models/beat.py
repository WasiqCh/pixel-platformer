from pydantic import BaseModel, Field, field_validator
from typing import List


def _norm_elements(v):
    if not isinstance(v, list):
        return []
    out = []
    for item in v:
        if isinstance(item, dict):
            name = item.get("name") or item.get("asset") or item.get("text") or ""
            out.append({"name": str(name),
                        "layer": str(item.get("layer") or "midground"),
                        "framing": str(item.get("framing") or "medium")})
        elif isinstance(item, str):
            out.append({"name": item, "layer": "midground", "framing": "medium"})
    return [e for e in out if e["name"]]


class BeatElementItem(BaseModel):
    name: str
    layer: str = "midground"
    framing: str = "medium"


class BeatItem(BaseModel):
    section: str = ""
    text: str
    svo: str = ""
    overlay_text: str = ""
    text_only: bool = False
    elements: List[BeatElementItem] = Field(default_factory=list)

    @field_validator("elements", mode="before")
    @classmethod
    def norm(cls, v):
        return _norm_elements(v)


class BeatBreakdownResult(BaseModel):
    beats: List[BeatItem]
