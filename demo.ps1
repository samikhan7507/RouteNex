# RouteNex phone demo (laptop + public HTTPS link). Double-click start-phone.bat or run:  powershell -ExecutionPolicy Bypass -File demo.ps1
$ErrorActionPreference = 'Stop'
Set-Location $PSScriptRoot
$py = Join-Path $env:LOCALAPPDATA 'RouteNexVenv\Scripts\python.exe'
if (-not (Test-Path $py)) { Write-Host "Run setup.bat first." -ForegroundColor Yellow; exit 1 }
if (-not (Get-Command cloudflared -ErrorAction SilentlyContinue)) {
  Write-Host "cloudflared not found. Install once with:  winget install --id Cloudflare.cloudflared   (then reopen the window)" -ForegroundColor Yellow; exit 1
}
if (-not (Test-Path backend\.env)) { Copy-Item backend\.env.example backend\.env }
if (-not $env:ROUTENEX_SECRET) { $env:ROUTENEX_SECRET = -join ((48..57) + (65..90) + (97..122) | Get-Random -Count 40 | ForEach-Object { [char]$_ }) }
$env:ROUTENEX_DB = Join-Path $PSScriptRoot 'database\routenex.db'
Start-Process powershell -ArgumentList '-NoExit','-Command',"Set-Location '$PSScriptRoot\backend'; & '$py' -m uvicorn app:app --host 127.0.0.1 --port 8000"
Start-Sleep -Seconds 4
Write-Host "`nLaptop:  http://localhost:8000" -ForegroundColor Green
Write-Host "Phone :  open the https://....trycloudflare.com link printed below in Chrome, then menu > Install app`n" -ForegroundColor Green
cloudflared tunnel --url http://localhost:8000
