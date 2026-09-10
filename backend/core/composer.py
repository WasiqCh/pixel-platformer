# backend/core/composer.py
import re


def clean_text(s):
    if not s:
        return s
    if "â" in s or "Ã" in s:
        try:
            return s.encode("cp1252", errors="strict").decode("utf-8")
        except Exception:
            return s
    return s


def classify_overlay(text):
    t = (text or "").strip()
    if not t:
        return None
    if re.match(r"^\d", t):
        return "year_chip"
    if "=" in t:
        return "emphasis"
    if "•" in t or "·" in t:
        return "list_ticker"
    if "→" in t or "←" in t:
        return "route_arrow"
    words = t.split()
    if t.endswith(".") and len(words) >= 4:
        return "payoff_line"
    low = t.lower()
    if any(k in low for k in ("empire", "company", "dynasty", "kingdom", "republic")) or (t.isupper() and len(t) <= 6):
        return "faction_tag"
    if len(words) <= 5:
        return "place_label"
    return "faction_tag"


def pacing_flags(dur):
    flags = []
    if dur < 3.5:
        flags.append("FLASH")
    if dur > 11:
        flags.append("HOLD")
    return flags


def parse_directives(improv):
    toks = set((improv or "").lower().split())
    return {t for t in ("lock", "static", "dynamic") if t in toks}


def split_note(editor_note):
    diegetic, director = [], []
    for line in (editor_note or "").splitlines():
        line = line.strip()
        if not line:
            continue
        if line.lower().startswith("diegetic:"):
            diegetic.append(line.split(":", 1)[1].strip())
        else:
            director.append(line)
    return diegetic, director


def base_class(ref, layer):
    if ref.startswith("C"):
        return "dynamic"
    if ref.startswith("E") or ref.startswith("MT"):
        return "static"
    return "dynamic" if layer == "midground" else "static"


def variant_for(char_variants, beat_text, chunk_text):
    for v in char_variants:
        span = v.get("span") or ""
        if " -> " in span:
            start, end = span.split(" -> ", 1)
        else:
            start, end = span, ""
        s = chunk_text.find(start.strip())
        if s == -1:
            continue
        e = chunk_text.find(end.strip()) if end.strip() else len(chunk_text)
        if e == -1:
            e = len(chunk_text)
        p = chunk_text.find(beat_text.strip())
        if p == -1:
            continue
        if s <= p <= e:
            return v
    return None


def master_prompt_env(descriptor, name, elements, green):
    g = " AVOID chroma green as dominant tone; use painted-sky alternative palette." if green else ""
    return (f"{descriptor} Environment plate, 16:9, empty scene, no characters, no text, no labels. "
            f"Location: {name} — {'; '.join(elements) or 'as described in script'}.{g} "
            f"Architecture and palette identical to reference sheet.")


def master_prompt_map(descriptor, text, template, era):
    return (f"{descriptor} Stylized map plate, 16:9, no labels, no text, no captions (labels added in editor). "
            f"Composition hint: {template or 'region_highlight'}. Subject: {text}. Era: {era or 'unspecified'}.")


def master_prompt_insert(descriptor, text, era, diegetic):
    d = f" Diegetic text to render exactly: {diegetic}." if diegetic else " No text anywhere."
    return (f"{descriptor} Insert cutout, square canvas, isolated on solid single-color background.{d} "
            f"Object: {text} ({era or 'era unspecified'}).")


def master_prompt_world_plate(descriptor, text, era):
    return (f"{descriptor} Environment-style plate, 16:9, empty scene, no characters, no text. "
            f"Subject: {text} ({era or 'era unspecified'}). Palette identical to reference.")


def pose_prompt(descriptor, name, identity, svo, beat_snip, framing, diegetic, director):
    extra = ""
    if diegetic:
        extra += f" Diegetic text to render exactly: {'; '.join(diegetic)}."
    if director:
        extra += f" Director note: {'; '.join(director)}."
    return (f"{descriptor} Character cutout, square canvas, isolated on solid single-color background, "
            f"no environment, no text. Identity: {name} — {identity}. "
            f"In this moment: {svo}; mood: {beat_snip}. Framing: {framing} shot. "
            f"Design identical to reference sheet.{extra}")
