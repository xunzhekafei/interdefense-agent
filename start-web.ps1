param([int]$Port = 8000)
$ErrorActionPreference = 'Stop'
$projectRoot = $PSScriptRoot
$pythonPath = Join-Path $projectRoot '.venv\Scripts\python.exe'
if (-not (Test-Path -LiteralPath $pythonPath)) {
    throw 'Missing .venv. Run: python -m venv .venv; then install requirements-lock.txt (or requirements-web.txt).'
}
$dist = Join-Path $projectRoot 'frontend\dist\index.html'
if (-not (Test-Path -LiteralPath $dist)) {
    throw 'Frontend not built. Run npm install and npm run build inside frontend.'
}
# 改了前端源码却忘记 build 时，别静默启动旧页面。
$distTime = (Get-Item -LiteralPath $dist).LastWriteTimeUtc
$inputs = @(
    (Join-Path $projectRoot 'frontend\index.html'),
    (Join-Path $projectRoot 'frontend\package.json'),
    (Join-Path $projectRoot 'frontend\vite.config.ts')
) | Where-Object { Test-Path -LiteralPath $_ } | ForEach-Object { Get-Item -LiteralPath $_ }
$sources = Get-ChildItem -LiteralPath (Join-Path $projectRoot 'frontend\src') -Recurse -File
$newer = (@($inputs) + @($sources)) | Where-Object { $_.LastWriteTimeUtc -gt $distTime } |
    Select-Object -First 1
if ($newer) {
    throw "Frontend is stale: $($newer.FullName) is newer than dist. Run npm run build inside frontend."
}
# 语音识别首次使用要从 Hugging Face 下载模型；国内直连通常会卡到超时，看起来像卡死。
# 默认走镜像，想用官方源就自己先设 HF_ENDPOINT。
if (-not $env:HF_ENDPOINT) { $env:HF_ENDPOINT = 'https://hf-mirror.com' }

Push-Location $projectRoot
try {
    Write-Host "Interview Studio: http://127.0.0.1:$Port"
    & $pythonPath -m uvicorn backend.app:app --host 127.0.0.1 --port $Port
} finally {
    Pop-Location
}
