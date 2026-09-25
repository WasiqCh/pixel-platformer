# backend/models/scene.py (SCENES-MP4 P1-T04)
from typing import Literal

from pydantic import BaseModel, Field, field_validator


def _strip(v):
    return v.strip() if isinstance(v, str) else v


class ScenePlan(BaseModel):
    place_ref: str | None = None
    shot: str = Field(min_length=1)
    reasoning: str = Field(min_length=1)

    @field_validator("place_ref", mode="before")
    @classmethod
    def _empty_place_to_none(cls, v):
        if v is None:
            return None
        if isinstance(v, str) and not v.strip():
            return None
        return _strip(v)

    @field_validator("shot", "reasoning", mode="before")
    @classmethod
    def _strip_text(cls, v):
        return _strip(v)

    @field_validator("reasoning", mode="after")
    @classmethod
    def _reasoning_non_empty(cls, v):
        if not v.strip():
            raise ValueError("reasoning must be non-empty")
        return v


class AssetNeed(BaseModel):
    name: str = Field(min_length=1)
    kind: Literal["character", "prop", "place", "photo"]
    search_query: str = Field(min_length=1)
    reasoning: str = Field(min_length=1)

    @field_validator("kind", mode="before")
    @classmethod
    def _normalise_kind(cls, v):
        return _strip(v).lower() if isinstance(v, str) else v

    @field_validator("name", "search_query", "reasoning", mode="before")
    @classmethod
    def _strip_text(cls, v):
        return _strip(v)

    @field_validator("reasoning", mode="after")
    @classmethod
    def _reasoning_non_empty(cls, v):
        if not v.strip():
            raise ValueError("reasoning must be non-empty")
        return v


class AssetPlan(BaseModel):
    """asset_plan job output: list wrapper. Empty needs allowed ONLY for
    pure-narration beats with no visuals (recipe rule)."""

    needs: list[AssetNeed] = Field(default_factory=list)
