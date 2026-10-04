# Single-click PowerShell launcher for the dashboard
Set-Location -Path $PSScriptRoot
Write-Host "================================================================" -ForegroundColor Cyan
Write-Host "Starting Scholarly Reference Validation Studio (FastAPI + React)" -ForegroundColor Green
Write-Host "Dashboard URL: http://localhost:8000" -ForegroundColor Yellow
Write-Host "================================================================" -ForegroundColor Cyan

if (Test-Path ".\.venv312\Scripts\python.exe") {
    & ".\.venv312\Scripts\python.exe" run_dashboard.py --port 8000
} elseif (Test-Path ".\.venv\Scripts\python.exe") {
    & ".\.venv\Scripts\python.exe" run_dashboard.py --port 8000
} else {
    python run_dashboard.py --port 8000
}

