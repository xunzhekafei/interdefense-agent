[CmdletBinding()]
param(
    [int]$Port = 8000,
    [string]$ApiKey = "",
    [switch]$Reload,
    [switch]$NoBrowser,
    [switch]$CheckOnly
)

$ErrorActionPreference = "Stop"
$root = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location -LiteralPath $root

function Write-Step([string]$message) {
    Write-Host "==> $message" -ForegroundColor Cyan
}

function Fail([string]$message) {
    Write-Host "错误：$message" -ForegroundColor Red
    exit 1
}

# 1. Python：优先 .venv，没有就用系统 python
$python = Join-Path $root ".venv\Scripts\python.exe"
if (-not (Test-Path -LiteralPath $python)) {
    $command = Get-Command python -ErrorAction SilentlyContinue
    if ($null -eq $command) {
        Fail "找不到 Python。请安装 Python 3.10+，或先创建 .venv。"
    }
    $python = $command.Source
}
Write-Step "Python: $python"

# 2. 运行依赖
& $python -c "import fastapi, uvicorn, anthropic" 2>$null
if ($LASTEXITCODE -ne 0) {
    Fail "缺少运行依赖。请执行：`n  $python -m pip install -r requirements-lock.txt"
}

# 3. 密钥与提供商
if ($ApiKey) {
    $env:ANTHROPIC_API_KEY = $ApiKey
}
$provider = if ($env:PROVIDER) { $env:PROVIDER } else { "deepseek（默认）" }
$hasKey = [bool]$env:ANTHROPIC_API_KEY
$hasToken = [bool]$env:ANTHROPIC_AUTH_TOKEN
Write-Step "提供商: $provider"

if ($hasToken) {
    Write-Host "  注意：检测到 ANTHROPIC_AUTH_TOKEN，它优先于 ANTHROPIC_API_KEY。" -ForegroundColor Yellow
    Write-Host "        如果它是别的提供商的密钥，请先 Remove-Item Env:ANTHROPIC_AUTH_TOKEN 再启动。" -ForegroundColor Yellow
}
if (-not $hasKey -and -not $hasToken) {
    Write-Host "  警告：没有检测到模型密钥。页面能打开，但开始面试会提示未配置密钥。" -ForegroundColor Yellow
    Write-Host "        用法：.\start.ps1 -ApiKey `"sk-...`"" -ForegroundColor Yellow
}

# 4. 前端产物
$frontend = Join-Path $root "frontend"
$dist = Join-Path $frontend "dist\index.html"
$npm = (Get-Command npm.cmd -ErrorAction SilentlyContinue).Source
if (-not (Test-Path -LiteralPath $dist)) {
    if (-not $npm) {
        Fail "前端尚未构建，且找不到 npm。请安装 Node.js 后重试。"
    }
    Write-Step "前端尚未构建，开始安装依赖并构建..."
    Push-Location $frontend
    try {
        if (-not (Test-Path -LiteralPath "node_modules")) {
            & $npm ci
            if ($LASTEXITCODE -ne 0) { Fail "npm ci 失败。" }
        }
        & $npm run build
        if ($LASTEXITCODE -ne 0) { Fail "前端构建失败。" }
    } finally {
        Pop-Location
    }
} else {
    $distTime = (Get-Item -LiteralPath $dist).LastWriteTimeUtc
    $newer = Get-ChildItem -LiteralPath (Join-Path $frontend "src") -Recurse -File |
        Where-Object { $_.LastWriteTimeUtc -gt $distTime } | Select-Object -First 1
    if ($newer) {
        if (-not $npm) {
            Fail "前端源码已更新，但找不到 npm；请安装 Node.js 后执行 npm run build。"
        }
        Write-Step "前端源码比 dist 新，重新构建..."
        Push-Location $frontend
        try {
            & $npm run build
            if ($LASTEXITCODE -ne 0) { Fail "前端构建失败。" }
        } finally {
            Pop-Location
        }
    }
}

if ($CheckOnly) {
    Write-Step "检查通过（未启动服务）。"
    exit 0
}

# 5. 启动
$url = "http://127.0.0.1:$Port"
if (-not $NoBrowser) {
    Start-Process -FilePath "powershell" -WindowStyle Hidden -ArgumentList @(
        "-NoProfile", "-Command", "Start-Sleep -Seconds 2; Start-Process '$url'"
    ) | Out-Null
}

Write-Step "启动后端：$url（Ctrl+C 停止）"
$uvicornArgs = @("-m", "uvicorn", "backend.app:app", "--host", "127.0.0.1", "--port", "$Port")
if ($Reload) {
    $uvicornArgs += "--reload"
}
& $python @uvicornArgs