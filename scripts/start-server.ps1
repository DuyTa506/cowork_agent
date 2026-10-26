$ErrorActionPreference = 'Stop'
Set-Location (Split-Path -Parent $PSScriptRoot)

if (-not (Get-Command docker -ErrorAction SilentlyContinue)) {
  Write-Host 'CHUA TIM THAY Docker CLI. Cai Docker Desktop/Docker Engine va khoi dong dich vu truoc.' -ForegroundColor Red
  exit 1
}
try { docker info | Out-Null } catch {
  Write-Host 'Docker chua san sang. Hay mo Docker Desktop va doi den khi Engine da chay.' -ForegroundColor Red
  exit 1
}
if (-not (Test-Path '.env')) {
  Copy-Item '.env.example' '.env'
  Write-Host 'Da tao file .env tu .env.example.' -ForegroundColor Yellow
  Write-Host 'Hay sua .env: POSTGRES_PASSWORD, JWT_SECRET va ADMIN_PASSWORD; sau do chay lai script.' -ForegroundColor Yellow
  exit 2
}
$envText = Get-Content '.env' -Raw
if ($envText -match 'THAY_BANG' -or $envText -match 'CHANGE_THIS_SECRET') {
  Write-Host 'File .env van con gia tri mau. Hay thay tat ca gia tri THAY_BANG va JWT_SECRET truoc khi mo cong mang noi bo.' -ForegroundColor Red
  exit 2
}
Write-Host 'Dang build va khoi dong he thong...' -ForegroundColor Cyan
docker compose up --build -d
Write-Host ''
Write-Host 'He thong da duoc yeu cau khoi dong.' -ForegroundColor Green
Write-Host 'Truy cap tren may chu: http://localhost:8080'
Write-Host 'May khac trong LAN: http://<IP-MAY-CHU>:8080'
Write-Host 'Kiem tra trang thai: docker compose ps'
Write-Host 'Xem nhat ky: docker compose logs -f api web'
