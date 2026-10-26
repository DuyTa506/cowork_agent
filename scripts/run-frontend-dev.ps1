$ErrorActionPreference = 'Stop'
Set-Location (Join-Path (Split-Path -Parent $PSScriptRoot) 'frontend')
if (-not (Get-Command node -ErrorAction SilentlyContinue)) { throw 'Chua cai Node.js. Cai ban LTS tu nodejs.org.' }
npm install
npm run dev -- --host 0.0.0.0
