# Levanta backend (uvicorn) y frontend (Vite) en paralelo

$root = $PSScriptRoot

# .env
if (-not (Test-Path "$root\.env")) {
    Copy-Item "$root\.env.example" "$root\.env"
    Write-Host ".env creado desde .env.example"
}

# Backend
Start-Process powershell -ArgumentList "-NoExit", "-Command", "cd '$root'; uvicorn pokegrading.main:app --reload"

# Frontend
Start-Process powershell -ArgumentList "-NoExit", "-Command", "cd '$root'; npx --prefix '.\frontend' vite '.\frontend' --host"

Write-Host ""
Write-Host "Servicios iniciados:"
Write-Host "  Backend  -> http://localhost:8000/docs"
Write-Host "  Frontend -> http://localhost:5173"
