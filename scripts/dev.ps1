# Frontend (5173) + Backend (8787) - Windows PowerShell
$ErrorActionPreference = "Stop"
$Root = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
Set-Location $Root

$NaverAuto = Join-Path $Root ".venv\Scripts\naver-auto.exe"
if (-not (Test-Path $NaverAuto)) {
    Write-Error "naver-auto not found. Run: .venv\Scripts\pip install -e ."
}

if (-not (Test-Path "$Root\frontend\node_modules")) {
    Write-Host "frontend npm install..."
    & npm.cmd install --prefix frontend
}

$env:Path = "$(Join-Path $Root '.venv\Scripts');$env:Path"

Write-Host "Backend:  http://127.0.0.1:8787"
$backend = Start-Process -FilePath $NaverAuto -ArgumentList @("ui", "--dev") -PassThru -NoNewWindow

Write-Host "Frontend: http://127.0.0.1:5173"
$frontend = Start-Process -FilePath "npm.cmd" -ArgumentList @("run", "dev") -WorkingDirectory "$Root\frontend" -PassThru -NoNewWindow

Write-Host ""
Write-Host "Open: http://127.0.0.1:5173"
Write-Host "Stop: Ctrl+C"
Write-Host ""

try {
    Wait-Process -Id $backend.Id, $frontend.Id
} finally {
    Write-Host "Shutting down..."
    Stop-Process -Id $backend.Id, $frontend.Id -Force -ErrorAction SilentlyContinue
}