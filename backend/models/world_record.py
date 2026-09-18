from pydantic import BaseModel, Field, field_validator, model_validator
from typing import List, Any

# Known type vocabulary - cheap models invent their own, which downstream code
# can't route. Normalise anything unrecognised to the nearest sane bucket.
_VALID_TYPES = ("brand_logo", "trademark", "real_person", "meme", "map_trigger")


def _flatten(v: Any) -> str:
    """Coerce a model-returned value into a plain string.

    Weaker models return objects/lists where the recipe asked for a sentence,
    which hard-fails validation and kills the whole extraction.
    """
    if isinstance(v, dict):
        return "; ".join(f"{k}: {val}" for k, val in v.items() if val)
    if isinstance(v, (list, tuple)):
        return "; ".join(_flatten(x) for x in v)
    return "" if v is None else str(v)


class WorldItem(BaseModel):
    type: str = "real_person"   # brand_logo|trademark|real_person|meme|map_trigger
    text: str = ""
    script_context: str = ""
    usage_intent: str = "on_screen_insert"
    search_query: str = ""  # 1-4 words
    era_hint: str = ""
    map_template: str = ""  # flag_fill|region_highlight|paper|split

    @model_validator(mode="before")
    @classmethod
    def _accept_key_variants(cls, data):
        if not isinstance(data, dict):
            return data
        if not data.get("text"):
            for src in ("name", "label", "entity", "item", "description", "value"):
                if data.get(src):
                    data = {**data, "text": data[src]}
                    break
        return data

    @field_validator("text", "script_context", "search_query", "era_hint",
                     "map_template", "usage_intent", mode="before")
    @classmethod
    def _to_text(cls, v):
        return _flatten(v)

    @field_validator("type", mode="before")
    @classmethod
    def _normalise_type(cls, v):
        t = _flatten(v).strip().lower().replace(" ", "_").replace("-", "_")
        if t in _VALID_TYPES:
            return t
        # Map common invented labels onto the real vocabulary.
        for key in _VALID_TYPES:
            if key in t:
                return key
        if any(k in t for k in ("brand", "logo", "company")):
            return "brand_logo"
        if any(k in t for k in ("person", "figure", "people", "historical")):
            return "real_person"
        if "map" in t or "geo" in t or "territory" in t:
            return "map_trigger"
        return "real_person"


class WorldScanResult(BaseModel):
    records: List[WorldItem] = Field(default_factory=list)