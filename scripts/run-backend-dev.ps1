$ErrorActionPreference = 'Stop'
Set-Location (Join-Path (Split-Path -Parent $PSScriptRoot) 'backend')
if (-not (Test-Path '.venv')) { py -3.14 -m venv .venv }
& .\.venv\Scripts\python.exe -m pip install --upgrade pip
& .\.venv\Scripts\python.exe -m pip install -r requirements.txt
$env:DATA_DIR = Join-Path (Get-Location) 'data'
$env:DATABASE_URL = 'sqlite:///./data/qk3-dev.db'
New-Item -ItemType Directory -Force -Path $env:DATA_DIR | Out-Null
& .\.venv\Scripts\python.exe -m uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
