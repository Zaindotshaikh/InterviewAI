@echo off
cd /d "%~dp0"
echo Installing with bun...
call bun install
cd server
call bun install
cd ..\client
call bun install
cd ..
echo.
echo DONE. Put your OpenAI key in server\.env then run:
echo   bun run --cwd server dev
echo   bun run --cwd client dev
echo Or double-click start.bat
pause
