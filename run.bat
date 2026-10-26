@echo off
chcp 65001 >nul
set "PYTHONUTF8=1"
set "PYTHONIOENCODING=utf-8"

cd /d "%~dp0"
set "PYTHONPATH=%CD%"

echo ==========================================
echo SheetMusicOMR V3.00 Server Launcher
echo ==========================================
echo Project : %CD%
echo Python  : .venv\Scripts\python.exe
echo Port    : 8763
echo URL     : http://127.0.0.1:8763
echo ==========================================
echo.

if not exist ".venv\Scripts\python.exe" (
    echo [INFO] Creating virtual environment .venv ...
    python -m venv .venv
)

.venv\Scripts\python.exe -c "import fastapi, cv2, pymupdf, docx, pypdfium2" >nul 2>&1
if errorlevel 1 (
    echo [INFO] Installing dependencies from requirements.txt ...
    .venv\Scripts\python.exe -m pip install -r requirements.txt
)

echo Starting SheetMusicOMR V3.00 Server ...
echo.
.venv\Scripts\python.exe launcher.py --port 8763 %*

echo.
echo Server stopped.
pause
