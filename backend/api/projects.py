# backend/api/projects.py
import asyncio
import gc
import shutil
from datetime import datetime, timezone

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from backend.core.config import DATA_DIR
from backend.core.id_generator import IDGenerator
from backend.db.connection import get_app_db, get_project_db
from backend.db.migrations import init_project_db
from backend.storage.fs_manager import create_project_dirs

router = APIRouter(tags=["projects"])


class ProjectCreate(BaseModel):
    slug: str


class ProjectRename(BaseModel):
    slug: str


# SCENES-MP4 F1-T02: project canvas background (color-wheel input).
# Stored per project in app.db projects.bg_color_hex (NULL = channel chroma
# default). The green auto-white asset logic is untouched — this is the
# scene canvas only (compositor + previews + frames read it).
class BackgroundUpdate(BaseModel):
    color: str | None = None


_DEFAULT_CHROMA = "#00FF00"


def _normalize_hex_color(raw: str | None) -> str | None:
    """Validate + normalize a #RGB/#RRGGBB color. None/empty = reset to
    default (NULL). Returns uppercase #RRGGBB. Raises ValueError on bad input."""
    if raw is None:
        return None
    s = raw.strip()
    if not s:
        return None
    if not s.startswith("#"):
        raise ValueError("color must be #RGB or #RRGGBB (e.g. #FF0000)")
    h = s[1:].strip()
    if len(h) == 3 and all(c in "0123456789abcdefABCDEF" for c in h):
        return "#" + "".join(c.upper() * 2 for c in h)
    if len(h) == 6 and all(c in "0123456789abcdefABCDEF" for c in h):
        return "#" + h.upper()
    raise ValueError("color must be #RGB or #RRGGBB (e.g. #FF0000)")


def _hex_to_rgb(hex_color: str) -> tuple[int, int, int]:
    h = hex_color.lstrip("#")
    if len(h) == 3:
        h = "".join(c * 2 for c in h)
    return (int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16))


async def resolve_project_background(project_id: str) -> dict:
    """Effective canvas background for a project. Returns {bg_color,
    channel_chroma, is_default, rgb}. bg_color is the effective #RRGGBB
    (project override when set+valid, else channel chroma, else #00FF00).
    Never raises 404-friendly — raises HTTPException(404) when unknown."""
    db = await get_app_db()
    try:
        async with db.execute(
            "SELECT channel_id, bg_color_hex FROM projects WHERE id=?",
            (project_id,)) as cur:
            proj = await cur.fetchone()
        if not proj:
            raise HTTPException(404, "Project not found")
        ch_id = proj["channel_id"]
        try:
            raw = (proj["bg_color_hex"] or "").strip()
        except Exception:
            raw = ""
        chroma = _DEFAULT_CHROMA
        try:
            async with db.execute(
                "SELECT bg_default_hex FROM channels WHERE id=?", (ch_id,)) as cur:
                ch = await cur.fetchone()
            if ch and (ch["bg_default_hex"] or "").strip():
                chroma = ch["bg_default_hex"].strip().upper()
        except Exception:
            pass
        if raw:
            try:
                norm = _normalize_hex_color(raw)
                eff = norm or chroma
                is_default = False if norm else True
            except ValueError:
                eff, is_default = chroma, True
        else:
            eff, is_default = chroma, True
        try:
            rgb = _hex_to_rgb(eff)
        except Exception:
            eff, rgb, is_default = _DEFAULT_CHROMA, (0, 255, 0), True
        return {"bg_color": eff, "channel_chroma": chroma,
                "is_default": is_default, "rgb": rgb,
                "project_override": raw or None}
    finally:
        await db.close()


def _now():
    return datetime.now(timezone.utc).isoformat()


async def _rmtree_with_retry(folder, attempts: int = 5, delay: float = 0.3) -> bool:
    """Remove a project folder, retrying past transient Windows file locks.

    Endpoints can leak an open aiosqlite handle; on Windows that keeps project.db
    locked and makes a plain rmtree blow up. Collect garbage and retry a few times
    before giving up, and never let a stuck folder turn into a 500.
    """
    for i in range(attempts):
        gc.collect()
        try:
            shutil.rmtree(folder)
            return True
        except FileNotFoundError:
            return True
        except OSError:
            if i == attempts - 1:
                return False
            await asyncio.sleep(delay * (i + 1))
    return False


@router.get("/channels/{ch_id}/projects")
async def list_projects(ch_id: str):
    db = await get_app_db()
    async with db.execute("SELECT * FROM projects WHERE channel_id = ? ORDER BY created_at DESC", (ch_id,)) as cur:
        rows = [dict(r) for r in await cur.fetchall()]
    await db.close()
    return rows


@router.post("/channels/{ch_id}/projects")
async def create_project(ch_id: str, data: ProjectCreate):
    db = await get_app_db()
    gen = IDGenerator(db)
    ep_suffix = await gen.mint_project(ch_id)
    proj_id = f"{ch_id}_{ep_suffix}"
    now = _now()

    await db.execute(
        "INSERT INTO projects (id, channel_id, slug, folder_name, created_at, updated_at) VALUES (?, ?, ?, ?, ?, ?)",
        (proj_id, ch_id, data.slug, proj_id, now, now),
    )
    await db.commit()
    await db.close()

    create_project_dirs(ch_id, ep_suffix)
    proj_db = await get_project_db(proj_id)
    await init_project_db(proj_db)
    await proj_db.close()
    return {"id": proj_id, "slug": data.slug}


@router.get("/projects/{project_id}")
async def get_project(project_id: str):
    db = await get_app_db()
    async with db.execute("SELECT * FROM projects WHERE id=?", (project_id,)) as cur:
        row = await cur.fetchone()
    await db.close()
    if not row:
        raise HTTPException(404, "Project not found")
    return dict(row)


# P-01: rename touches slug ONLY — folder path never changes
@router.put("/projects/{project_id}")
async def rename_project(project_id: str, data: ProjectRename):
    db = await get_app_db()
    await db.execute("UPDATE projects SET slug=?, updated_at=? WHERE id=?", (data.slug, _now(), project_id))
    await db.commit()
    await db.close()
    return {"status": "renamed"}


# --- SCENES-MP4 F1-T02: project canvas background (wheel input, per project).
@router.get("/projects/{project_id}/background")
async def get_background(project_id: str):
    """Effective canvas background: project override or channel chroma default.
    The color-wheel input defaults to channel_chroma; is_default=True means
    the project follows the channel (green auto-white asset logic untouched)."""
    return await resolve_project_background(project_id)


@router.put("/projects/{project_id}/background")
async def set_background(project_id: str, data: BackgroundUpdate):
    """Save per-project canvas background. {color: '#FF0000'} sets it;
    {color: null/''} resets to the channel chroma default. Returns the
    resolved effective background (same shape as GET)."""
    try:
        norm = _normalize_hex_color(data.color)
    except ValueError as e:
        raise HTTPException(422, str(e))
    db = await get_app_db()
    try:
        async with db.execute(
            "SELECT id FROM projects WHERE id=?", (project_id,)) as cur:
            row = await cur.fetchone()
        if not row:
            raise HTTPException(404, "Project not found")
        await db.execute(
            "UPDATE projects SET bg_color_hex=?, updated_at=? WHERE id=?",
            (norm, _now(), project_id))
        await db.commit()
    finally:
        await db.close()
    out = await resolve_project_background(project_id)
    out["status"] = "saved"
    return out


@router.delete("/projects/{project_id}")
async def delete_project(project_id: str):
    db = await get_app_db()
    async with db.execute("SELECT folder_name FROM projects WHERE id=?", (project_id,)) as cur:
        row = await cur.fetchone()
    if not row:
        await db.close()
        raise HTTPException(404, "Project not found")
    await db.execute("DELETE FROM projects WHERE id=?", (project_id,))
    await db.commit()
    await db.close()
    if row:
        folder = DATA_DIR / "projects" / row["folder_name"]
        folder_removed = await _rmtree_with_retry(folder)
        return {"status": "deleted", "folder_removed": folder_removed}
    return {"status": "deleted", "folder_removed": True}


@router.post("/projects/{project_id}/duplicate")
async def duplicate_project(project_id: str, data: ProjectCreate):
    db = await get_app_db()
    async with db.execute("SELECT * FROM projects WHERE id=?", (project_id,)) as cur:
        src = await cur.fetchone()
    if not src:
        await db.close()
        raise HTTPException(404, "Source project not found")

    gen = IDGenerator(db)
    ep_suffix = await gen.mint_project(src["channel_id"])
    new_id = f"{src['channel_id']}_{ep_suffix}"
    now = _now()

    await db.execute(
        "INSERT INTO projects (id, channel_id, slug, folder_name, created_at, updated_at) VALUES (?, ?, ?, ?, ?, ?)",
        (new_id, src["channel_id"], data.slug, new_id, now, now),
    )
    await db.commit()
    await db.close()

    create_project_dirs(src["channel_id"], ep_suffix)
    new_db = await get_project_db(new_id)
    await init_project_db(new_db)

    src_db = await get_project_db(src["folder_name"])
    async with src_db.execute("SELECT content, channel_id FROM idea_cards WHERE project_id=? AND is_current=1", (project_id,)) as cur:
        for i in await cur.fetchall():
            await new_db.execute(
                "INSERT INTO idea_cards (project_id, channel_id, content, created_at, updated_at) VALUES (?, ?, ?, ?, ?)",
                (new_id, i["channel_id"], i["content"], now, now))
    async with src_db.execute("SELECT text, angle, style_tag, char_count, locked FROM titles WHERE project_id=?", (project_id,)) as cur:
        for t in await cur.fetchall():
            await new_db.execute(
                "INSERT INTO titles (project_id, text, angle, style_tag, char_count, locked, created_at, updated_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                (new_id, t["text"], t["angle"], t["style_tag"], t["char_count"], t["locked"], now, now))
    async with src_db.execute("SELECT text, word_count, duration_sec, locked FROM scripts WHERE project_id=? AND locked=1", (project_id,)) as cur:
        for s in await cur.fetchall():
            await new_db.execute(
                "INSERT INTO scripts (project_id, text, word_count, duration_sec, locked, locked_at, created_at) VALUES (?, ?, ?, ?, ?, ?, ?)",
                (new_id, s["text"], s["word_count"], s["duration_sec"], s["locked"], now, now))
    await new_db.commit()
    await new_db.close()
    await src_db.close()
    return {"id": new_id, "slug": data.slug}


@router.post("/projects/scan")
async def scan_projects():
    """Reconcile data/projects/ with DB: recover folders, remove ghosts."""
    db = await get_app_db()
    added, removed = [], []
    projects_dir = DATA_DIR / "projects"

    async with db.execute("SELECT id FROM projects") as cur:
        known = {r["id"] for r in await cur.fetchall()}

    if projects_dir.exists():
        for folder in sorted(projects_dir.iterdir()):
            if not folder.is_dir() or len(folder.name.split("_")) != 2:
                continue
            ch_id = folder.name.split("_")[0]
            if folder.name not in known:
                try:
                    now = _now()
                    await db.execute(
                        "INSERT INTO projects (id, channel_id, slug, folder_name, stage, created_at, updated_at) VALUES (?, ?, ?, ?, 'idea', ?, ?)",
                        (folder.name, ch_id, folder.name, folder.name, now, now))
                    added.append(folder.name)
                except Exception:
                    pass  # channel row missing — skip silently

    async with db.execute("SELECT id, folder_name FROM projects") as cur:
        rows = await cur.fetchall()
    for r in rows:
        if not (projects_dir / r["folder_name"]).exists():
            await db.execute("DELETE FROM projects WHERE id=?", (r["id"],))
            removed.append(r["id"])

    await db.commit()
    await db.close()
    return {"added": added, "removed": removed}