from pydantic import BaseModel, Field
from typing import List

class WorldItem(BaseModel):
    type: str               # brand_logo|trademark|real_person|meme|map_trigger
    text: str
    script_context: str = ""
    usage_intent: str = "on_screen_insert"
    search_query: str = ""  # 1-4 words
    era_hint: str = ""
    map_template: str = ""  # flag_fill|region_highlight|paper|split

class WorldScanResult(BaseModel):
    records: List[WorldItem]