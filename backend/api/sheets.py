# backend/api/sheets.py
from fastapi import APIRouter, HTTPException
import json

from backend.db.connection import get_app_db, get_project_db
from backend.storage.fs_manager import get_project_dir

router = APIRouter(tags=["sheets"])

CHAR_CELLS = [
    "wide full-body neutral stance",
    "medium front three-quarter view",
    "medium profile walking",
    "close-up face neutral",
    "close-up face determined",
    "close-up face angry or afraid",
    "signature action pose",
    "holding signature props",
    "pure silhouette",
]

ENV_CELLS = [
    "wide establishing shot, dawn light",
    "wide shot, harsh noon light",
    "wide shot, dusk or night",
    "wide shot, bad weather",
    "medium shot of the key detail",
    "close texture study",
    "populated with characters",
    "empty and still",
    "silhouette / shape study",
]


async def _get_proj_info(project_id: str) -> tuple[str, str]:
    db = await get_app_db()
    async with db.execute("SELECT folder_name, channel_id FROM projects WHERE id=?", (project_id,)) as cur:
        row = await cur.fetchone()
    await db.close()
    if not row: raise HTTPException(404, "Project not found")
    return row["folder_name"], row["channel_id"]


async def _get_descriptor(ch_id: str) -> str:
    app_db = await get_app_db()
    async with app_db.execute("SELECT descriptor FROM channels WHERE id=?", (ch_id,)) as cur:
        row = await cur.fetchone()
    await app_db.close()
    if row and row["descriptor"]:
        return row["descriptor"]
    return "clean flat 2D animation, bold outlines, limited palette"


def _char_grid_prompt(descriptor: str, name: str, appearance: str) -> str:
    cells = "; ".join(f"[{i + 1}] {c}" for i, c in enumerate(CHAR_CELLS))
    desc = descriptor.rstrip(". ")
    return (f"{desc}. 3x3 character grid sheet of {name}: {appearance}. "
            f"Nine panels, same character, identical design in every panel. {cells}. "
            f"Consistent line weight and palette across all panels.")


def _env_grid_prompt(descriptor: str, name: str, elements: str, green: bool) -> str:
    cells = "; ".join(f"[{i + 1}] {c}" for i, c in enumerate(ENV_CELLS))
    desc = descriptor.rstrip(". ")
    extra = (" AVOID chroma green as a dominant tone; use a painted-sky alternative palette."
             if green else "")
    return (f"{desc}. 3x3 environment grid sheet of {name}: {elements}. "
            f"Nine panels of the SAME location at different times and angles. {cells}.{extra} "
            f"Consistent architecture and palette across all panels.")


@router.post("/projects/{project_id}/sheets/generate")
async def generate_sheets(project_id: str):
    folder, ch_id = await _get_proj_info(project_id)
    descriptor = await _get_descriptor(ch_id)

    proj_db = await get_project_db(folder)
    async with proj_db.execute(
        "SELECT * FROM characters WHERE project_id=? AND stale=0 ORDER BY id", (project_id,)) as cur:
        chars = [dict(r) for r in await cur.fetchall()]
    for c in chars:
        c["names"] = json.loads(c["names"])
        async with proj_db.execute("SELECT * FROM variants WHERE character_id=? ORDER BY id", (c["id"],)) as cur:
            c["variants"] = [dict(v) for v in await cur.fetchall()]
    async with proj_db.execute(
        "SELECT * FROM environments WHERE project_id=? AND stale=0 ORDER BY id", (project_id,)) as cur:
        envs = [dict(r) for r in await cur.fetchall()]
    for e in envs:
        e["elements"] = json.loads(e["elements"] or "[]")
        async with proj_db.execute("SELECT state FROM env_variations WHERE environment_id=? ORDER BY id", (e["id"],)) as cur:
            e["variations"] = [v["state"] for v in await cur.fetchall()]
    async with proj_db.execute("SELECT asset_ref, COUNT(*) AS n FROM beat_elements GROUP BY asset_ref") as cur:
        beat_counts = {r["asset_ref"]: r["n"] for r in await cur.fetchall()}
    await proj_db.close()

    assets_dir = get_project_dir(ch_id, folder.split("_")[1]) / "06_assets"
    (assets_dir / "characters").mkdir(parents=True, exist_ok=True)
    (assets_dir / "environments").mkdir(parents=True, exist_ok=True)

    for c in chars:
        name = c["names"][0]
        lines = [
            f"# {c['id']} — {name} ({c['kind']} · {c['significance']} · {c['render']})",
            f"STYLE KIT: {descriptor}",
            f"BEAT PRESENCE: {beat_counts.get(c['id'], 0)} beats",
            "",
            "## Master appearance",
            c["appearance"] or "TBD",
            "",
        ]
        if c["variants"]:
            lines.append("## Variants")
            for v in c["variants"]:
                lines.append(f"- {v['id']} [{v['span']}]: {v['delta']}")
            lines.append("")
        lines.append(f"## Green conflict: {'YES — plan non-green palette' if c['green_conflict'] else 'no'}")
        lines.append("")
        lines.append("## 3x3 grid prompt")
        lines.append(_char_grid_prompt(descriptor, name, c["appearance"] or "as described above"))
        (assets_dir / "characters" / f"{c['id']}_sheet.md").write_text("\n".join(lines), encoding="utf-8")

    for e in envs:
        elements_txt = "; ".join(e["elements"]) or "as described in script"
        elements_lines = [f"- {el}" for el in e["elements"]] if e["elements"] else ["- TBD"]
        lines = [
            f"# {e['id']} — {e['name']}",
            f"STYLE KIT: {descriptor}",
            f"BEAT PRESENCE: {beat_counts.get(e['id'], 0)} beats",
            "",
            "## Elements",
            *elements_lines,
            "",
        ]
        if e["variations"]:
            lines.append("## Variations")
            lines += [f"- {v}" for v in e["variations"]]
            lines.append("")
        lines.append(f"## Green conflict: {'YES — plan non-green palette' if e['green_conflict'] else 'no'}")
        lines.append("")
        lines.append("## 3x3 grid prompt")
        lines.append(_env_grid_prompt(descriptor, e["name"], elements_txt, bool(e["green_conflict"])))
        (assets_dir / "environments" / f"{e['id']}_sheet.md").write_text("\n".join(lines), encoding="utf-8")

    return {"characters": len(chars), "environments": len(envs)}


@router.get("/projects/{project_id}/sheets")
async def list_sheets(project_id: str):
    folder, ch_id = await _get_proj_info(project_id)
    assets_dir = get_project_dir(ch_id, folder.split("_")[1]) / "06_assets"
    out = []
    for kind in ("characters", "environments"):
        d = assets_dir / kind
        if not d.exists():
            continue
        for f in sorted(d.glob("*_sheet.md")):
            text = f.read_text(encoding="utf-8")
            first = text.split("\n", 1)[0].lstrip("# ").strip()
            out.append({"asset_id": f.name.replace("_sheet.md", ""), "kind": kind,
                        "title": first, "text": text})
    return out
