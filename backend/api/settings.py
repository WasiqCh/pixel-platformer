from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from openai import AsyncOpenAI
from backend.core import config
from backend.core.id_generator import IDGenerator
from backend.db.connection import get_app_db
from backend.storage.fs_manager import create_channel_dirs, create_project_dirs

router = APIRouter(tags=["settings"])

class Models(BaseModel):
    light: str; medium: str; high: str

class SettingsUpdate(BaseModel):
    endpoint: str; api_key: str; use_single_model: bool
    models: Models; sfx: bool = False

@router.get("/settings")
async def get_settings():
    return config.load_settings()

@router.put("/settings")
async def put_settings(update: SettingsUpdate):
    config.save_settings(update.model_dump())
    return {"status": "saved"}

@router.post("/settings/test-connection")
async def test_connection():
    s = config.load_settings()
    if not s["api_key"]:
        raise HTTPException(400, "No API key saved yet.")
    model = s["models"]["high"] if s["use_single_model"] else s["models"]["light"]
    client = AsyncOpenAI(base_url=s["endpoint"], api_key=s["api_key"])
    try:
        await client.chat.completions.create(
            model=model, messages=[{"role": "user", "content": "ping"}], max_tokens=1)
        return {"ok": True, "model": model}
    except Exception as e:
        return {"ok": False, "error": str(e)}

# Add this route inside the router
@router.post("/test-utilities")
async def test_utilities():
    # 1. Test File System Manager
    create_channel_dirs("CH99")
    create_project_dirs("CH99", "EP99")
    
    # 2. Test ID Generator (using app_db for library assets)
    db = await get_app_db()
    id_gen = IDGenerator(db)
    lib_id = await id_gen.mint_library_asset()
    await db.close()
    
    return {
        "message": "Utilities executed successfully!",
        "fs_check": "Look in data/channels/CH99 and data/projects/CH99_EP99",
        "id_gen_check": f"Next Library ID minted: {lib_id}"
    }