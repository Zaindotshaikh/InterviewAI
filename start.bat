@echo off
cd /d "%~dp0"
start "InterviewAI Server" cmd /k "cd /d %~dp0server && bun run dev"
timeout /t 2 /nobreak >nul
start "InterviewAI Client" cmd /k "cd /d %~dp0client && bun run dev"
echo Opened server + client terminals.
echo App: http://localhost:5173
pause
