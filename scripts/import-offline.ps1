$ErrorActionPreference = 'Stop'
Set-Location (Split-Path -Parent $PSScriptRoot)
$bundle = Join-Path (Get-Location) 'qk3-ai-offline-images.tar'
if (-not (Test-Path $bundle)) { throw "Khong tim thay $bundle. Hay dat file TAR vao thu muc goc du an." }
if (-not (Test-Path '.env')) { throw 'Khong tim thay .env. Hay tao file .env duoc phe duyet cho may chu nay.' }
docker load -i $bundle
docker compose up -d --no-build
Write-Host 'Da nap image va khoi dong (khong build, phu hop may chu tach mang).' -ForegroundColor Green
Write-Host 'Truy cap: http://localhost:8080 va tu may khac: http://<IP-MAY-CHU>:8080'
