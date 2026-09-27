# backend/api/channels.py
from datetime import datetime, timezone
from pathlib import Path

from fastapi import APIRouter, HTTPException, UploadFile, File
from fastapi.responses import FileResponse
from pydantic import BaseModel

from backend.core.id_generator import IDGenerator
from backend.core.llm_client import dispatch_vision
from backend.db.connection import get_app_db
from backend.storage.fs_manager import create_channel_dirs, get_channel_dir

router = APIRouter(tags=["channels"])

DEFAULT_AVOID = """1. No background clutter — isolated subjects only.
2. No text, logos, or watermarks in the image.
3. No blurry or soft edges.
4. No extra characters or objects not requested.
5. Subject only — nothing else in frame."""


class ChannelCreate(BaseModel):
    name: str


class KitUpdate(BaseModel):
    descriptor: str | None = None
    avoid_list: str | None = None


# ---------- Channel CRUD ----------

@router.get("/channels")
async def list_channels():
    db = await get_app_db()
    async with db.execute("SELECT * FROM channels ORDER BY created_at DESC") as cur:
        rows = [dict(r) for r in await cur.fetchall()]
    await db.close()
    return rows


@router.post("/channels")
async def create_channel(data: ChannelCreate):
    db = await get_app_db()
    gen = IDGenerator(db)
    ch_id = await gen.mint_channel()
    now = datetime.now(timezone.utc).isoformat()

    await db.execute(
        "INSERT INTO channels (id, name, created_at, updated_at) VALUES (?, ?, ?, ?)",
        (ch_id, data.name, now, now),
    )
    await db.commit()
    await db.close()

    create_channel_dirs(ch_id)
    return {"id": ch_id, "name": data.name}


@router.get("/channels/{ch_id}")
async def get_channel(ch_id: str):
    db = await get_app_db()
    async with db.execute("SELECT * FROM channels WHERE id=?", (ch_id,)) as cur:
        row = await cur.fetchone()
    await db.close()
    if not row:
        raise HTTPException(404, "channel not found")
    return dict(row)


# ---------- Style presets (F1-T01) ----------
# Wobbly body is served byte-identical from docs/scenes-mp4/STYLE_WOBBLY_SKETCH.md
# (style paragraph only — title + HOW-IT-FLOWS stay in the doc). Flat-toon +
# Paper-cut are owner-worded stubs (body=None) until the owner provides text —
# never invented here.

_WOBBLY_DOC = (
    Path(__file__).resolve().parents[2]
    / "docs" / "scenes-mp4" / "STYLE_WOBBLY_SKETCH.md"
)


def _wobbly_body() -> str:
    if not _WOBBLY_DOC.exists():
        raise HTTPException(500, f"Wobbly style doc missing: {_WOBBLY_DOC}")
    lines = _WOBBLY_DOC.read_text(encoding="utf-8").splitlines()
    paras = []
    for ln in lines[1:]:
        if ln.strip() == "---":
            break
        if ln.strip():
            paras.append(ln)
    return "\n".join(paras)


STYLE_PRESETS = [
    {"id": "wobbly", "name": "Wobbly sketch", "version": 1, "status": "ready"},
    {"id": "flat-toon", "name": "Flat-toon", "version": 1,
     "status": "pending-owner-words"},
    {"id": "paper-cut", "name": "Paper-cut", "version": 1,
     "status": "pending-owner-words"},
]


@router.get("/channels/kit/presets")
async def list_presets():
    out = []
    for p in STYLE_PRESETS:
        body = _wobbly_body() if p["id"] == "wobbly" else None
        note = None
        if body is None:
            note = "Owner wording pending — pick Wobbly or write a custom descriptor."
        out.append({**p, "body": body, "note": note})
    return out


# ---------- Style Kit (P08) ----------

@router.post("/channels/{ch_id}/kit/refs")
async def upload_refs(ch_id: str, files: list[UploadFile] = File(...)):
    refs_dir = get_channel_dir(ch_id) / "style_kit" / "refs"
    refs_dir.mkdir(parents=True, exist_ok=True)
    saved = []
    for f in files:
        if f.filename.lower().endswith((".png", ".jpg", ".jpeg", ".webp")):
            with open(refs_dir / f.filename, "wb") as out:
                out.write(await f.read())
            saved.append(f.filename)
    return {"saved": saved}


@router.get("/channels/{ch_id}/kit/refs")
async def list_refs(ch_id: str):
    refs_dir = get_channel_dir(ch_id) / "style_kit" / "refs"
    if not refs_dir.exists():
        return []
    return sorted(p.name for p in refs_dir.iterdir() if p.is_file())


@router.get("/channels/{ch_id}/kit/refs/{filename}")
async def get_ref(ch_id: str, filename: str):
    path = get_channel_dir(ch_id) / "style_kit" / "refs" / filename
    if not path.exists():
        raise HTTPException(404, "not found")
    return FileResponse(path)


@router.post("/channels/{ch_id}/kit/descriptor")
async def draft_descriptor(ch_id: str):
    refs_dir = get_channel_dir(ch_id) / "style_kit" / "refs"
    imgs = sorted(
        p for p in refs_dir.glob("*")
        if p.suffix.lower() in (".png", ".jpg", ".jpeg", ".webp")
    )
    if not imgs:
        raise HTTPException(400, "Upload at least one reference image first.")
    return await dispatch_vision(
        "style_descriptor", [str(p) for p in imgs],
        {"channel_id": ch_id}, channel_id=ch_id,
    )


@router.put("/channels/{ch_id}/kit")
async def update_kit(ch_id: str, data: KitUpdate):
    db = await get_app_db()
    async with db.execute("SELECT * FROM channels WHERE id=?", (ch_id,)) as cur:
        row = await cur.fetchone()
    if not row:
        await db.close()
        raise HTTPException(404, "channel not found")

    now = datetime.now(timezone.utc).isoformat()
    descriptor = data.descriptor if data.descriptor is not None else (row["descriptor"] or "")
    avoid_list = data.avoid_list if data.avoid_list is not None else (row["avoid_list"] or DEFAULT_AVOID)
    kit_version = row["kit_version"] + 1

    await db.execute(
        "UPDATE channels SET descriptor=?, avoid_list=?, kit_version=?, updated_at=? WHERE id=?",
        (descriptor, avoid_list, kit_version, now, ch_id),
    )
    await db.commit()
    await db.close()

    kit_dir = get_channel_dir(ch_id) / "style_kit"
    kit_dir.mkdir(parents=True, exist_ok=True)
    (kit_dir / "descriptor.md").write_text(descriptor, encoding="utf-8")
    (kit_dir / "avoid_list.md").write_text(avoid_list, encoding="utf-8")
    return {"kit_version": kit_version}