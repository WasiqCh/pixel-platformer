#!/bin/bash
cd "$(dirname "$0")"
./.venv/bin/python -m uvicorn backend.main:app --reload --port 8100 &
BACK_PID=$!
cd frontend && npm run dev &
FRONT_PID=$!
cd ..
sleep 4
xdg-open http://localhost:3000 2>/dev/null || open http://localhost:3000 2>/dev/null
trap "kill $BACK_PID $FRONT_PID 2>/dev/null" INT TERM EXIT
wait