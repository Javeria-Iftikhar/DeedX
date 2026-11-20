# Start Vite frontend (from project root)
Set-Location (Join-Path $PSScriptRoot "frontend")
Write-Host "Starting frontend at http://localhost:5173 ..."
npm run dev
