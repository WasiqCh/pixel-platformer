# backend/models/script.py
from pydantic import BaseModel, Field
from typing import List

class OutlineSection(BaseModel):
    heading: str
    summary: str
    target_words: int
    role: str = "build"          # hook|build|turn|payoff|outro

class OutlineResult(BaseModel):
    sections: List[OutlineSection]

class CheckIssue(BaseModel):
    type: str                    # names|timeline|tone|repetition|narration|hook
    location: str = ""
    note: str
    severity: str = "minor"      # minor|major

class CheckResult(BaseModel):
    issues: List[CheckIssue] = Field(default_factory=list)
    hook_strength: str = "ok"    # strong|ok|weak
    summary: str = ""

class AutoSectionItem(BaseModel):
    heading: str
    summary: str = ""
    role: str = "build"
    chunk_text: str          # EXACT verbatim original text of the section

class AutoSectionResult(BaseModel):
    sections: List[AutoSectionItem]
