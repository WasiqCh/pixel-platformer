import json
from pathlib import Path

DATA_DIR = Path(__file__).resolve().parents[2] / "data"
SETTINGS_PATH = DATA_DIR / "settings.json"

DEFAULTS = {
    "endpoint": "https://api.openai.com/v1",
    "api_key": "",
    "use_single_model": False,
    "models": {"light": "gpt-4o-mini", "medium": "gpt-4o", "high": "gpt-4o"},
    "sfx": False,
}

def ensure_data_dirs():
    (DATA_DIR / "channels").mkdir(parents=True, exist_ok=True)
    (DATA_DIR / "projects").mkdir(parents=True, exist_ok=True)

def load_settings() -> dict:
    if SETTINGS_PATH.exists():
        saved = json.loads(SETTINGS_PATH.read_text(encoding="utf-8"))
        merged = {**DEFAULTS, **saved}
        merged["models"] = {**DEFAULTS["models"], **saved.get("models", {})}
        return merged
    return json.loads(json.dumps(DEFAULTS))

def save_settings(s: dict):
    SETTINGS_PATH.write_text(json.dumps(s, indent=2), encoding="utf-8")