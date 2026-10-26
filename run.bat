@echo off
chcp 65001 >nul
set "PYTHONUTF8=1"
set "PYTHONIOENCODING=utf-8"
set "PYTHONPATH=D:\SheetMusicOMR_v3.00"

:: 切到 V3.00 專案目錄（bat 檔所在資料夾）
cd /d "%~dp0"

echo ==========================================
echo SheetMusicOMR V3.00 一鍵啟動 server
echo ==========================================
echo 專案目錄: %CD%
echo Python:   .venv\Scripts\python.exe
echo Port:     8763
echo URL:      http://127.0.0.1:8763
echo ==========================================
echo.

:: 檢查 venv 是否存在
if not exist ".venv\Scripts\python.exe" (
    echo [錯誤] 找不到 .venv\Scripts\python.exe
    echo 請先執行: python -m venv .venv 並 pip install -r requirements.txt
    pause
    exit /b 1
)

:: 啟動 server（--no-browser 不自動開瀏覽器，手動開 http://127.0.0.1:8763）
echo.
echo 啟動中...
echo.
call .venv\Scripts\python.exe launcher.py --port 8763 --no-browser %*

echo.
echo.
echo Server 已停止。
pause
