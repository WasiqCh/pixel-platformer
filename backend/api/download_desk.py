# backend/api/download_desk.py
import asyncio
import re
from datetime import datetime, timezone
from typing import Optional

import httpx
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from backend.db.connection import get_app_db, get_project_db
from backend.storage.fs_manager import get_project_dir

router = APIRouter(tags=["download_desk"])

ALLOWED = ("public domain", "pd-", "cc0", "cc by", "cc-by")
BLOCKED = ("nc", "nd")


def _now():
    return datetime.now(timezone.utc).isoformat()


def _clean_html(s):
    return re.sub(r"<[^>]+>", "", s or "").strip()


def _license_ok(lic):
    l = (lic or "").lower()
    if not l:
        return False
    if any(b in l for b in BLOCKED):
        return False
    return any(a in l for a in ALLOWED)


class DownloadReq(BaseModel):
    url: str
    source_url: str
    license: str = ""
    author: str = ""


@router.get("/projects/{project_id}/world/{rw_id}/autosearch")
async def autosearch(project_id: str, rw_id: str, q: Optional[str] = None):
    db = await get_app_db()
    async with db.execute("SELECT folder_name FROM projects WHERE id=?", (project_id,)) as cur:
        prow = await cur.fetchone()
    await db.close()
    if not prow: raise HTTPException(404, "Project not found")
    proj_db = await get_project_db(prow["folder_name"])
    async with proj_db.execute("SELECT * FROM world_records WHERE id=? AND project_id=?", (rw_id, project_id)) as cur:
        w = await cur.fetchone()
    await proj_db.close()
    if not w: raise HTTPException(404, "World record not found")

    query = q or ((w["search_query"] or w["text"]) + " " + (w["era_hint"] or ""))
    url = ("https://commons.wikimedia.org/w/api.php?action=query&format=json&generator=search"
           f"&gsrsearch=filetype:bitmap%20{query.replace(' ', '%20')}&gsrlimit=10&gsrnamespace=6"
           "&prop=imageinfo&iiprop=url%7Cextmetadata%7Csize&iiurlwidth=320")
    # Wikimedia rate-limits aggressively and hands out transient 403/429s that clear
    # on their own, so retry a couple of times before surfacing an error to the user.
    headers = {"User-Agent": "PixelPlatformer/1.0 (animation pipeline; localhost)"}
    r = None
    for attempt in range(3):
        async with httpx.AsyncClient(timeout=30) as cl:
            r = await cl.get(url, headers=headers)
        if r.status_code == 200:
            break
        if r.status_code not in (403, 429, 500, 502, 503, 504):
            break
        if attempt < 2:
            await asyncio.sleep(1.0 * (attempt + 1))
    if r is None or r.status_code != 200:
        raise HTTPException(502, f"Wikimedia HTTP {getattr(r, 'status_code', 'no response')}")
    pages = (r.json().get("query") or {}).get("pages") or {}
    out = []
    for p in pages.values():
        ii = (p.get("imageinfo") or [{}])[0]
        md = ii.get("extmetadata") or {}
        lic = _clean_html((md.get("LicenseShortName") or {}).get("value"))
        if not _license_ok(lic):
            continue
        out.append({
            "title": p.get("title", ""),
            "thumb": ii.get("thumburl") or ii.get("url"),
            "file_url": ii.get("url"),
            "source_url": ii.get("descriptionurl"),
            "license": lic,
            "author": _clean_html((md.get("Artist") or {}).get("value"))[:120],
        })
    out.sort(key=lambda x: x["title"])
    return {"query": query, "results": out[:8]}


@router.post("/projects/{project_id}/library/{lib_id}/download")
async def download_into_library(project_id: str, lib_id: str, data: DownloadReq):
    db = await get_app_db()
    async with db.execute("SELECT folder_name, channel_id FROM projects WHERE id=?", (project_id,)) as cur:
        prow = await cur.fetchone()
    await db.close()
    if not prow: raise HTTPException(404, "Project not found")
    folder, ch_id = prow["folder_name"], prow["channel_id"]
    proj_db = await get_project_db(folder)
    async with proj_db.execute("SELECT * FROM library WHERE id=? AND project_id=?", (lib_id, project_id)) as cur:
        row = await cur.fetchone()
    if not row:
        await proj_db.close(); raise HTTPException(404, "Library slot not found")
    row = dict(row)

    async with httpx.AsyncClient(timeout=60, follow_redirects=True) as cl:
        r = await cl.get(data.url)
    if r.status_code != 200 or not r.content:
        await proj_db.close(); raise HTTPException(502, f"Download failed HTTP {r.status_code}")
    ct = r.headers.get("content-type", "")
    ext = ".png" if "png" in ct else (".webp" if "webp" in ct else ".jpg")
    base = get_project_dir(ch_id, folder.split("_")[1])
    rel = f"06_assets/library/{lib_id}_auto{ext}"
    (base / rel).parent.mkdir(parents=True, exist_ok=True)
    (base / rel).write_bytes(r.content)

    prov = f"{data.source_url} | {data.license} | {data.author}"
    await proj_db.execute("UPDATE library SET file_path=?, status='ready', source='downloaded', updated_at=? WHERE id=?",
                          (rel, _now(), lib_id))
    if row["kind"] == "world" and row["asset_ref"]:
        await proj_db.execute("UPDATE world_records SET provenance=?, updated_at=? WHERE id=?",
                              (prov, _now(), row["asset_ref"]))
    from backend.core.vault import vault_put, asset_key
    await vault_put(ch_id, asset_key(row["title"]), row["kind"], row["title"], base / rel, project_id)
    await proj_db.commit(); await proj_db.close()
    return {"status": "ready", "file_path": rel, "provenance": prov}