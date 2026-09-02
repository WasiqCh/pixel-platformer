from pydantic import BaseModel
from typing import List

class TitleCandidate(BaseModel):
    text: str
    angle: str
    style_tag: str

class TitleGenResult(BaseModel):
    titles: List[TitleCandidate]

class TitleShortenResult(BaseModel):
    shortened: str
