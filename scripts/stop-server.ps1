$ErrorActionPreference = 'Stop'
Set-Location (Split-Path -Parent $PSScriptRoot)
docker compose down
Write-Host 'Da dung cac container. Du lieu trong volumes van duoc giu lai.' -ForegroundColor Green
