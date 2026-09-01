# backend/storage/fs_manager.py
from pathlib import Path
from backend.core.config import DATA_DIR

def get_channel_dir(channel_id: str) -> Path:
    return DATA_DIR / "channels" / channel_id

def get_project_dir(channel_id: str, project_id: str) -> Path:
    # P-01: Stable folder path. NEVER uses the human-readable slug.
    folder_name = f"{channel_id}_{project_id}"
    return DATA_DIR / "projects" / folder_name

def create_channel_dirs(channel_id: str):
    ch_dir = get_channel_dir(channel_id)
    (ch_dir / "style_kit" / "refs").mkdir(parents=True, exist_ok=True)
    (ch_dir / "library").mkdir(parents=True, exist_ok=True)

def create_project_dirs(channel_id: str, project_id: str):
    p_dir = get_project_dir(channel_id, project_id)
    
    # P-02: Notice 07_beats is explicitly included here
    subdirs = [
        "01_concept", 
        "02_title", 
        "03_script", 
        "04_cast", 
        "05_world",
        "06_sheets/prompts", 
        "06_sheets/references", 
        "06_sheets/drafts", 
        "06_sheets/finals", 
        "06_sheets/editor_notes",
        "07_beats/prompts", 
        "07_beats/one_offs",
        "08_handoff", 
        "09_intelligence"
    ]
    
    for sub in subdirs:
        (p_dir / sub).mkdir(parents=True, exist_ok=True)
        
    # Create Explorer-friendly README
    readme = p_dir / "README.txt"
    if not readme.exists():
        readme.write_text(
            f"Project Folder: {channel_id}_{project_id}\n"
            "This folder is managed by the Pixel Platformer app.\n"
            "You can browse and edit text files here, then use the 'Rescan' button in the app.\n"
        )