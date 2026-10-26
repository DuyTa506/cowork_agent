$ErrorActionPreference = 'Stop'
Set-Location (Split-Path -Parent $PSScriptRoot)
if (-not (Test-Path '.env')) { throw 'Hay tao va kiem tra file .env truoc khi dong goi.' }
Write-Host 'Build cac image tren may co quyen tai dependency/image...' -ForegroundColor Cyan
docker compose build
$bundle = Join-Path (Get-Location) 'qk3-ai-offline-images.tar'
$images = @('qk3-ai-document-api:0.2.0', 'qk3-ai-document-web:0.1.0', 'postgres:17-alpine', 'qdrant/qdrant:v1.19.2', 'minio/minio:RELEASE.2025-09-07T16-13-09Z')
# Chi keo image chua co san tren may nay (minio/minio khong con keo duoc tu Docker Hub tren mot so mang: dung ban da co san).
foreach ($image in $images | Where-Object { $_ -notlike 'qk3-ai-document-*' }) {
    docker image inspect $image *> $null
    if ($LASTEXITCODE -ne 0) {
        docker pull $image
        if ($LASTEXITCODE -ne 0) { throw "Khong co image $image tren may nay va khong keo duoc. Hay nap image nay (docker load) truoc khi dong goi." }
    }
}
docker save -o $bundle @images
Write-Host "Da tao $bundle" -ForegroundColor Green
Write-Host 'Sao chep file TAR, source va file .env da duoc phe duyet sang may chu noi bo. Bao mat file .env.'
