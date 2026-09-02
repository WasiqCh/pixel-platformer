@echo off
cd /d "%~dp0"
echo Pulling latest changes...
git pull --rebase
echo Saving changes...
git add .
git commit -m "sync %date% %time%" || echo Nothing new to commit.
git push
echo.
echo Done! You are synced.
pause
