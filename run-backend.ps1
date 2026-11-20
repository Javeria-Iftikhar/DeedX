# Start FastAPI backend (from project root)
Set-Location $PSScriptRoot
Write-Host "Starting backend at http://127.0.0.1:8000 ..."
python -m uvicorn app.main:app --reload --host 127.0.0.1 --port 8000
