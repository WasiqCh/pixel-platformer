from pydantic import BaseModel, Field
from typing import List

class MentionItem(BaseModel):
    text: str
    character_name: str
    section: str = ""
    confidence: float = 0.8

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

class CharacterExtractResult(BaseModel):
    characters: List[CharacterExtractItem]
    mentions: List[MentionItem] = Field(default_factory=list)