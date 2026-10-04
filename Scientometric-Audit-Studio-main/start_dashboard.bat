@echo off
title Scholarly Reference Validation Studio
echo ================================================================
echo Starting Scholarly Reference Validation Studio (FastAPI + React)
echo Dashboard URL: http://localhost:8000
echo ================================================================
cd /d "%~dp0"
if exist ".venv312\Scripts\python.exe" (
    ".venv312\Scripts\python.exe" run_dashboard.py --port 8000
) else if exist ".venv\Scripts\python.exe" (
    ".venv\Scripts\python.exe" run_dashboard.py --port 8000
) else (
    python run_dashboard.py --port 8000
)
pause

