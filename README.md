# Pixel Platformer

Localhost app: FastAPI backend (brain) + React/Vite frontend (display only).

## Run

- Backend (port 8100): `.venv\Scripts\python.exe -m uvicorn backend.main:app --reload --reload-dir backend --port 8100`
- Frontend (port 3000): `cd frontend; npm run dev`
- Or `start.bat` / `start.sh` (boots both, opens browser).

## Docs

- `docs/OPERATOR_RUNBOOK.md` — pipeline DONE criteria (source of truth).
- `docs/CHATBOT_RUNBOOK.md` — chatbot driver rules (layman mode).
- `HOW_IT_WORKS.md` — plain-language flow.

## Notes

- `data/` is gitignored (settings, DBs, project files) — never commit.
- Frontend proxies `/api` → 8100 (see `frontend/vite.config.js`).
