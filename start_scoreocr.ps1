<# 
.SYNOPSIS
    ScoreOCR Toolkit 啟動腳本 - 自動啟動伺服器並開啟瀏覽器
.DESCRIPTION
    啟動 Uvicorn 伺服器並在預設瀏覽器中開啟 http://127.0.0.1:8000
    支持自動檢查虛擬環境、依賴安裝狀態
#>

param(
    [switch]$NoBrowser,
    [int]$Port = 8000,
    [string]$Host = "127.0.0.1"
)

$ProjectRoot = Split-Path -Parent $MyInvocation.MyCommand.Definition
$VenvPath = Join-Path $ProjectRoot ".venv"
$PythonExe = Join-Path $VenvPath "Scripts\python.exe"
$ServerUrl = "http://$Host`:$Port"

Write-Host "╔══════════════════════════════════════════════════════════════╗" -ForegroundColor Cyan
Write-Host "║           ScoreOCR Toolkit 啟動器 v3.00                      ║" -ForegroundColor Cyan
Write-Host "║           SheetMusicOMR 樂譜編輯器                            ║" -ForegroundColor Cyan
Write-Host "╚══════════════════════════════════════════════════════════════╝" -ForegroundColor Cyan
Write-Host ""

# 檢查虛擬環境
if (-not (Test-Path $PythonExe)) {
    Write-Host "❌ 找不到虛擬環境: $PythonExe" -ForegroundColor Red
    Write-Host "請先建立虛擬環境並安裝依賴:" -ForegroundColor Yellow
    Write-Host "  python -m venv .venv" -ForegroundColor Gray
    Write-Host "  .venv\Scripts\activate" -ForegroundColor Gray
    Write-Host "  pip install -r requirements.txt" -ForegroundColor Gray
    Read-Host "按 Enter 鍵退出"
    exit 1
}

# 檢查關鍵依賴
Write-Host "🔍 檢查依賴..." -ForegroundColor Yellow
$MissingDeps = @()
try {
    & $PythonExe -c "import cv2, numpy, fastapi, uvicorn, pydantic, pypdfium2, PIL" 2>$null
} catch {
    $MissingDeps += "核心依賴缺失"
}

if ($MissingDeps.Count -gt 0) {
    Write-Host "⚠️  缺少依賴，正在安裝..." -ForegroundColor Yellow
    & $PythonExe -m pip install -r (Join-Path $ProjectRoot "requirements.txt") --quiet
    if ($LASTEXITCODE -ne 0) {
        Write-Host "❌ 依賴安裝失敗，請手動執行:" -ForegroundColor Red
        Write-Host "  .venv\Scripts\activate && pip install -r requirements.txt" -ForegroundColor Gray
        Read-Host "按 Enter 鍵退出"
        exit 1
    }
    Write-Host "✅ 依賴安裝完成" -ForegroundColor Green
}

# 檢查端口是否被佔用
$PortInUse = Get-NetTCPConnection -LocalPort $Port -State Listen -ErrorAction SilentlyContinue
if ($PortInUse) {
    Write-Host "⚠️  端口 $Port 已被佔用，嘗試關閉現有進程..." -ForegroundColor Yellow
    $Pid = (Get-NetTCPConnection -LocalPort $Port -State Listen).OwningProcess
    try {
        Stop-Process -Id $Pid -Force -ErrorAction Stop
        Write-Host "✅ 已終止佔用端口的進程 (PID: $Pid)" -ForegroundColor Green
        Start-Sleep -Seconds 1
    } catch {
        Write-Host "❌ 無法終止進程，請手動關閉佔用端口 $Port 的程式" -ForegroundColor Red
        Read-Host "按 Enter 鍵退出"
        exit 1
    }
}

# 設定 PYTHONPATH 確保使用正確的 numpy
$Env:PYTHONPATH = (Join-Path $VenvPath "Lib\site-packages") + ";" + $Env:PYTHONPATH

Write-Host ""
Write-Host "🚀 啟動伺服器..." -ForegroundColor Green
Write-Host "   專案目錄: $ProjectRoot" -ForegroundColor Gray
Write-Host "   Python:   $PythonExe" -ForegroundColor Gray
Write-Host "   網址:     $ServerUrl" -ForegroundColor Cyan
Write-Host ""

# 建立啟動資訊檔案供瀏覽器開啟使用
$LaunchInfo = @{
    url = $ServerUrl
    timestamp = Get-Date -Format "yyyy-MM-dd HH:mm:ss"
    pid = $PID
} | ConvertTo-Json
$LaunchInfo | Out-File -FilePath (Join-Path $ProjectRoot ".launch_info.json") -Encoding utf8

# 啟動伺服器 (背景執行)
$ServerProcess = Start-Process -FilePath $PythonExe -ArgumentList "-m", "uvicorn", "app:app", "--host", $Host, "--port", $Port -WorkingDirectory $ProjectRoot -PassThru -WindowStyle Hidden

Write-Host "✅ 伺服器已啟動 (PID: $($ServerProcess.Id))" -ForegroundColor Green
Write-Host ""

# 等待伺服器就緒
Write-Host "⏳ 等待伺服器就緒..." -ForegroundColor Yellow
$Ready = $false
for ($i = 0; $i -lt 15; $i++) {
    try {
        $Response = Invoke-WebRequest -Uri "$ServerUrl/health" -TimeoutSec 2 -ErrorAction Stop
        if ($Response.StatusCode -eq 200) {
            $Ready = $true
            break
        }
    } catch {}
    Start-Sleep -Seconds 1
    Write-Host "." -NoNewline -ForegroundColor Gray
}
Write-Host ""

if (-not $Ready) {
    Write-Host "❌ 伺服器啟動超時，請檢查錯誤日誌" -ForegroundColor Red
    Stop-Process -Id $ServerProcess.Id -Force -ErrorAction SilentlyContinue
    Read-Host "按 Enter 鍵退出"
    exit 1
}

Write-Host "✅ 伺服器就緒！" -ForegroundColor Green

# 開啟瀏覽器
if (-not $NoBrowser) {
    Write-Host "🌐 正在開啟瀏覽器..." -ForegroundColor Cyan
    try {
        Start-Process $ServerUrl
        Write-Host "✅ 瀏覽器已開啟" -ForegroundColor Green
    } catch {
        Write-Host "⚠️  無法自動開啟瀏覽器，請手動訪問: $ServerUrl" -ForegroundColor Yellow
    }
}

Write-Host ""
Write-Host "═══════════════════════════════════════════════════════════════" -ForegroundColor Cyan
Write-Host "  ScoreOCR Toolkit 正在運行中..." -ForegroundColor White
Write-Host "  📍 訪問地址: $ServerUrl" -ForegroundColor Cyan
Write-Host "  🛑 停止伺服器: 按 Ctrl+C 或關閉此視窗" -ForegroundColor Yellow
Write-Host "═══════════════════════════════════════════════════════════════" -ForegroundColor Cyan
Write-Host ""

# 保持視窗開啟並監控伺服器進程
try {
    $ServerProcess.WaitForExit()
} finally {
    Write-Host ""
    Write-Host "🛑 伺服器已停止" -ForegroundColor Yellow
    if (Test-Path (Join-Path $ProjectRoot ".launch_info.json")) {
        Remove-Item (Join-Path $ProjectRoot ".launch_info.json") -Force
    }
}