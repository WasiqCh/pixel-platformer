# backend/main.py
from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from backend.core import config
from backend.db.connection import setup_databases
from backend.api import settings as settings_api
from backend.api import llm as llm_api
from backend.api import channels as channels_api  # <--- ADD
from backend.api import projects as projects_api    # <--- ADD
from backend.api import ideation as ideation_api  # <--- ADD
from backend.api import titles as titles_api  # <--- ADD
from backend.api import scripts as scripts_api  # <--- ADD

@asynccontextmanager
async def lifespan(app: FastAPI):
    config.ensure_data_dirs()
    await setup_databases()
    yield

app = FastAPI(title="Pixel Platformer", version="0.1.0", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000", "http://127.0.0.1:3000", "http://localhost:5173", "http://127.0.0.1:5173"],
    allow_credentials=True, allow_methods=["*"], allow_headers=["*"],
)

# ... down by the other include_router lines ...
app.include_router(scripts_api.router, prefix="/api/v1")  # <--- ADD
app.include_router(titles_api.router, prefix="/api/v1")  # <--- ADD
app.include_router(ideation_api.router, prefix="/api/v1")  # <--- ADD
app.include_router(settings_api.router, prefix="/api/v1")
app.include_router(llm_api.router, prefix="/api/v1")
app.include_router(channels_api.router, prefix="/api/v1")  # <--- ADD
app.include_router(projects_api.router, prefix="/api/v1")  # <--- ADD