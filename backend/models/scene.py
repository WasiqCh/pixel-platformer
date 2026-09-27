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


class OverlayItem(BaseModel):
    """One on-screen text overlay proposed for a scene (SCENES-MP4 D9-T01).
    role is the closed set from the overlay_text recipe; color is the plate
    color for that role (hex like #FFD34D or a plain color name); position is
    a free-text box hint (e.g. "bottom", "lower-third", "top")."""

    text: str = Field(min_length=1)
    role: Literal["name", "place", "date", "number", "quote", "warning"]
    color: str = Field(min_length=1)
    position: str = Field(min_length=1)
    reasoning: str = Field(min_length=1)

    @field_validator("role", mode="before")
    @classmethod
    def _normalise_role(cls, v):
        return _strip(v).lower() if isinstance(v, str) else v

    @field_validator("text", "color", "position", "reasoning", mode="before")
    @classmethod
    def _strip_text(cls, v):
        return _strip(v)

    @field_validator("reasoning", mode="after")
    @classmethod
    def _reasoning_non_empty(cls, v):
        if not v.strip():
            raise ValueError("reasoning must be non-empty")
        return v


class OverlayPlan(BaseModel):
    """overlay_text job output: list wrapper. An empty list IS the explicit
    none (the beat needs no on-screen text) — not a failure."""

    overlays: list[OverlayItem] = Field(default_factory=list)


def _local_tag(tag: str) -> str:
    return tag.split("}")[-1].split(":")[-1].lower() if isinstance(tag, str) else ""


def validate_svg_text(svg: str) -> str:
    """SCENES-MP4 P2-T03 server validation: XML parses + viewBox/width/height
    present + no <script>/external refs. Returns the stripped SVG or raises
    ValueError with a repair-actionable message (dispatch() feeds it back)."""
    import re as _re
    import xml.etree.ElementTree as _et

    text = svg.strip() if isinstance(svg, str) else ""
    if not text:
        raise ValueError("svg must be non-empty")
    # The stock SVG namespace declarations (http://www.w3.org/...) are part of
    # every well-formed SVG, not external refs — blanket them out before the
    # URL scan so valid output is not flagged.
    _XMLNS_RE = _re.compile(r"""\s+xmlns(?::\w+)?\s*=\s*["']https?://www\.w3\.org/[^"']*["']""",
                            _re.IGNORECASE)
    lowered = _XMLNS_RE.sub("", text.lower())
    if "<script" in lowered:
        raise ValueError("svg must not contain <script>")
    if "http://" in lowered or "https://" in lowered:
        raise ValueError("svg must not contain external refs (http/https URLs)")
    if "javascript:" in lowered:
        raise ValueError("svg must not contain javascript: URLs")
    try:
        root = _et.fromstring(text)
    except Exception as e:
        raise ValueError(f"svg must be parseable XML: {e}")
    if _local_tag(root.tag) != "svg":
        raise ValueError("svg root element must be <svg>")
    for attr in ("viewBox", "width", "height"):
        val = root.get(attr)
        # viewBox is case-sensitive per spec; accept viewbox mis-casing with a
        # clear message so the repair retry can fix it.
        if (val is None or not str(val).strip()) and attr == "viewBox":
            val = root.get("viewbox") or root.get("VIEWBOX")
        if val is None or not str(val).strip():
            raise ValueError(f"svg root must carry a non-empty {attr} attribute")
    for el in root.iter():
        if _local_tag(el.tag) == "script":
            raise ValueError("svg must not contain <script>")
        for name, value in (el.attrib or {}).items():
            lname = _local_tag(name)
            if lname.startswith("on"):
                raise ValueError(f"svg must not contain event-handler attribute '{name}'")
            if isinstance(value, str) and "javascript:" in value.lower():
                raise ValueError("svg must not contain javascript: URLs")
    return text


class SvgGen(BaseModel):
    """svg_gen job output: raw SVG text + non-empty reasoning (owner review)."""

    svg: str = Field(min_length=1)
    reasoning: str = Field(min_length=1)

    @field_validator("svg", mode="before")
    @classmethod
    def _strip_svg(cls, v):
        return _strip(v)

    @field_validator("reasoning", mode="before")
    @classmethod
    def _strip_text(cls, v):
        return _strip(v)

    @field_validator("svg", mode="after")
    @classmethod
    def _svg_must_be_safe(cls, v):
        return validate_svg_text(v)

    @field_validator("reasoning", mode="after")
    @classmethod
    def _reasoning_non_empty(cls, v):
        if not v.strip():
            raise ValueError("reasoning must be non-empty")
        return v
