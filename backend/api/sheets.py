# backend/api/sheets.py
from fastapi import APIRouter, HTTPException
import json
import math

from backend.db.connection import get_app_db, get_project_db
from backend.storage.fs_manager import get_project_dir

router = APIRouter(tags=["sheets"])

# Sprite-sheet layout lives in backend/core/sheet_layout.py (single source of
# truth). These were duplicated here and in prompts.py and had already drifted.
from backend.core.sheet_layout import (CHAR_ACTIONS_PER_SHEET, CHAR_CELLS,
                                       ENV_VARIATIONS_PER_SHEET, ENV_FALLBACK_STATES,
                                       env_cells)


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


def _char_grid_prompt(descriptor: str, name: str, appearance: str, sheet_num: int, actions: list, total_sheets: int) -> str:
    cells = "; ".join(f"[{i + 1}] {c}" for i, c in enumerate(actions))
    desc = descriptor.rstrip(". ")
    sheet_label = f"Sheet {sheet_num} of {total_sheets}"
    action_labels = ", ".join(f"{sheet_num}.{i+1}" for i in range(len(actions)))
    return (f"{desc}. {sheet_label} — {name}: {appearance}. "
            f"Actions on this sheet: {action_labels}. "
            f"Grid: {len(actions)} panels, same character, identical design in every panel. {cells}. "
            f"Consistent line weight and palette across all panels. "
            f"Label each panel with its action number ({action_labels}).")


def _char_sheet_prompts(descriptor: str, name: str, appearance: str,
                        actions: list = None) -> list[tuple[int, list, str]]:
    """Split character actions into sheets, return [(sheet_num, actions_list, prompt)].

    Prefers the actions the AI chose for this character (2-6, from
    character_extract). Falls back to the generic cell list for characters
    extracted before that field existed.
    """
    all_actions = [a for a in (actions or []) if a and a.strip()] or CHAR_CELLS[:]
    sheets = []
    for i in range(0, len(all_actions), CHAR_ACTIONS_PER_SHEET):
        sheet_actions = all_actions[i:i + CHAR_ACTIONS_PER_SHEET]
        sheet_num = (i // CHAR_ACTIONS_PER_SHEET) + 1
        total_sheets = math.ceil(len(all_actions) / CHAR_ACTIONS_PER_SHEET)
        prompt = _char_grid_prompt(descriptor, name, appearance, sheet_num, sheet_actions, total_sheets)
        sheets.append((sheet_num, sheet_actions, prompt))
    return sheets


def _env_grid_prompt(descriptor: str, name: str, elements: str, green: bool,
                     variations: list = None) -> str:
    """Build an environment sheet prompt.

    An environment sheet is TWO STATES OF ONE LOCATION. If the AI already
    extracted script-specific variations for this location we use those
    (previously they were read from the DB, printed into the .md, and then
    ignored here in favour of a hardcoded generic list). Otherwise fall back
    to the first N generic cells so the sheet is still usable.
    """
    states = [v for v in (variations or []) if v and v.strip()]
    if not states:
        states = env_cells()
    states = states[:ENV_VARIATIONS_PER_SHEET]
    # Pad to the target: a sheet should always show 2 contrasting states, but
    # the extractor often finds only one. Fill with generic STATES, not shots.
    for fb in ENV_FALLBACK_STATES:
        if len(states) >= ENV_VARIATIONS_PER_SHEET:
            break
        if fb not in states:
            states.append(fb)

    cells = "; ".join(f"[{i + 1}] {c}" for i, c in enumerate(states))
    desc = descriptor.rstrip(". ")
    extra = (" AVOID chroma green as a dominant tone; use a painted-sky alternative palette."
             if green else "")
    return (f"{desc}. Environment sheet for {name}: {elements}. "
            f"ONE location shown in {len(states)} states, identical architecture and "
            f"layout in every panel - only light/condition/state changes. {cells}.{extra} "
            f"Consistent architecture and palette across all panels. "
            f"Label each panel with its state number.")


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
        # AI-chosen sprite-sheet actions (added later - column may be absent
        # or NULL on characters extracted before it existed).
        c["actions"] = json.loads(c["actions"]) if c.get("actions") else []
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

    # Clear stale sheets first. Action/variation counts change between runs
    # (a character that needed 2 sheets yesterday may need 1 today), so old
    # files would linger and show up in the sheet list as ghosts.
    for stale in list((assets_dir / "characters").glob("*_sheet.md")) + \
                 list((assets_dir / "environments").glob("*_sheet.md")):
        try:
            stale.unlink()
        except OSError:
            pass

    for c in chars:
        name = c["names"][0]
        base_lines = [
            f"# {c['id']} — {name} ({c['kind']} · {c['significance']} · {c['render']})",
            f"STYLE KIT: {descriptor}",
            f"BEAT PRESENCE: {beat_counts.get(c['id'], 0)} beats",
            "",
            "## Master appearance",
            c["appearance"] or "TBD",
            "",
        ]
        if c["variants"]:
            base_lines.append("## Variants")
            for v in c["variants"]:
                base_lines.append(f"- {v['id']} [{v['span']}]: {v['delta']}")
            base_lines.append("")
        base_lines.append(f"## Green conflict: {'YES — plan non-green palette' if c['green_conflict'] else 'no'}")
        base_lines.append("")

        char_sheets = _char_sheet_prompts(descriptor, name,
                                          c["appearance"] or "as described above",
                                          c.get("actions"))
        for sheet_num, actions, prompt in char_sheets:
            lines = base_lines[:]
            lines.append(f"## Character Sheet {sheet_num} ({len(actions)} actions)")
            lines.append(f"Actions: {', '.join(f'{sheet_num}.{i+1}' for i in range(len(actions)))}")
            lines.append("")
            lines.append("## Grid prompt")
            lines.append(prompt)
            sheet_id = f"{c['id']}_S{sheet_num}"
            (assets_dir / "characters" / f"{sheet_id}_sheet.md").write_text("\n".join(lines), encoding="utf-8")

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
        lines.append("## Grid prompt")
        lines.append(_env_grid_prompt(descriptor, e["name"], elements_txt,
                                      bool(e["green_conflict"]), e.get("variations")))
        (assets_dir / "environments" / f"{e['id']}_sheet.md").write_text("\n".join(lines), encoding="utf-8")

    total_char_sheets = sum(
        math.ceil(len([a for a in (c.get("actions") or []) if a and a.strip()]
                      or CHAR_CELLS) / CHAR_ACTIONS_PER_SHEET)
        for c in chars)
    return {"characters": len(chars), "character_sheets": total_char_sheets, "environments": len(envs)}


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
