@echo off
chcp 65001 >nul
set "PYTHONUTF8=1"
set "PYTHONIOENCODING=utf-8"

:: 切到專案目錄（bat 檔所在資料夾）
cd /d "%~dp0"
set "PYTHONPATH=%~dp0"

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
    echo [提示] 找不到 .venv\Scripts\python.exe，正在自動建立虛擬環境...
    python -m venv .venv
    if errorlevel 1 (
        echo [錯誤] 無法建立 .venv 虛擬環境，請確認系統已安裝 Python 3.10+。
        pause
        exit /b 1
    )
)

:: 自動檢查核心套件是否已安裝於 .venv（如 pymupdf / cv2 / fastapi）
.venv\Scripts\python.exe -c "import fastapi, cv2, pymupdf, docx, pypdfium2" >nul 2>&1
if errorlevel 1 (
    echo [提示] 偵測到 .venv 缺少必要套件，正在自動安裝 requirements.txt...
    .venv\Scripts\python.exe -m pip install -r requirements.txt
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
