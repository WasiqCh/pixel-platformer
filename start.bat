@echo off
cd /d "%~dp0"

echo [1/3] Starting backend on :8100 ...
start "PixelBackend" cmd /k ".venv\Scripts\python.exe -m uvicorn backend.main:app --reload --reload-dir backend --port 8100"

echo [2/3] Starting frontend on :3000 ...
cd frontend
start "PixelFrontend" cmd /k "npm run dev"
cd ..

echo [3/3] Opening browser ...
timeout /t 4 /nobreak >nul
start http://localhost:3000

echo.
echo Pixel Platformer is booting. Keep the two popped-up windows open.