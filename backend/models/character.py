from pydantic import BaseModel, Field, field_validator, model_validator
from typing import List, Any


def _flatten(v: Any) -> str:
    """Coerce a model-returned value into a plain string.

    Weaker/free models frequently return structured objects where the recipe
    asked for a sentence (e.g. appearance as {"build": "robust", ...}) which
    hard-fails validation. Flatten instead of rejecting the whole extraction.
    """
    if isinstance(v, dict):
        return "; ".join(f"{k}: {val}" for k, val in v.items() if val)
    if isinstance(v, (list, tuple)):
        return "; ".join(_flatten(x) for x in v)
    return "" if v is None else str(v)


class MentionItem(BaseModel):
    text: str = ""
    character_name: str = ""
    section: str = ""
    confidence: float = 0.8

    @model_validator(mode="before")
    @classmethod
    def _accept_key_variants(cls, data):
        """Map the key names weaker models actually emit onto our schema."""
        if not isinstance(data, dict):
            return data
        if not data.get("character_name"):
            for src in ("name", "character", "resolved_to", "character_id", "char"):
                if data.get(src):
                    data = {**data, "character_name": data[src]}
                    break
        if not data.get("text"):
            for src in ("mention", "mention_text", "surface"):
                if data.get(src):
                    data = {**data, "text": data[src]}
                    break
        return data

class CharacterExtractItem(BaseModel):
    name: str
    aliases: List[str] = Field(default_factory=list)
    kind: str = "named"                 # named|generic
    faction: str = ""
    significance: str = "supporting"    # core|supporting|minor
    render: str = "drawn"               # drawn|fetched
    appearance: str = ""
    presence_sections: List[str] = Field(default_factory=list)
    green_conflict: bool = False
    world_annotations: List[str] = Field(default_factory=list)
    # Sprite-sheet actions the AI judges this character actually needs.
    # 2-6 entries; 6 is a hard ceiling (one sheet must hold them all).
    actions: List[str] = Field(default_factory=list)

    @field_validator("appearance", mode="before")
    @classmethod
    def _appearance_to_text(cls, v):
        return _flatten(v)

    @field_validator("actions", "aliases", "world_annotations", mode="before")
    @classmethod
    def _list_to_str_list(cls, v):
        if v is None:
            return []
        if isinstance(v, str):
            return [v]
        return [_flatten(x) for x in v]

class CharacterExtractResult(BaseModel):
    characters: List[CharacterExtractItem]
    mentions: List[MentionItem] = Field(default_factory=list)