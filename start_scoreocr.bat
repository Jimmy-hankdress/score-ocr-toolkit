@echo off
chcp 65001 >nul
title ScoreOCR Toolkit 啟動器 v3.00

echo ╔══════════════════════════════════════════════════════════════╗
echo ║           ScoreOCR Toolkit 啟動器 v3.00                      ║
echo ║           SheetMusicOMR 樂譜編輯器                            ║
echo ╚══════════════════════════════════════════════════════════════╝
echo.

set "PROJECT_ROOT=%~dp0"
set "VENV_PATH=%PROJECT_ROOT%.venv"
set "PYTHON_EXE=%VENV_PATH%\Scripts\python.exe"
set "PORT=8000"
set "HOST=127.0.0.1"
set "SERVER_URL=http://%HOST%:%PORT%"

REM 檢查虛擬環境
if not exist "%PYTHON_EXE%" (
    echo ❌ 找不到虛擬環境: %PYTHON_EXE%
    echo 請先建立虛擬環境並安裝依賴:
    echo   python -m venv .venv
    echo   .venv\Scripts\activate
    echo   pip install -r requirements.txt
    pause
    exit /b 1
)

REM 檢查關鍵依賴
echo 🔍 檢查依賴...
"%PYTHON_EXE%" -c "import cv2, numpy, fastapi, uvicorn, pydantic, pypdfium2, PIL" 2>nul
if errorlevel 1 (
    echo ⚠️  缺少依賴，正在安裝...
    "%PYTHON_EXE%" -m pip install -r "%PROJECT_ROOT%requirements.txt" --quiet
    if errorlevel 1 (
        echo ❌ 依賴安裝失敗，請手動執行:
        echo   .venv\Scripts\activate ^&^& pip install -r requirements.txt
        pause
        exit /b 1
    )
    echo ✅ 依賴安裝完成
)

REM 檢查端口是否被佔用
netstat -ano | findstr ":%PORT% " | findstr "LISTENING" >nul
if not errorlevel 1 (
    echo ⚠️  端口 %PORT% 已被佔用，嘗試關閉現有進程...
    for /f "tokens=5" %%a in ('netstat -ano ^| findstr ":%PORT% " ^| findstr "LISTENING"') do (
        taskkill /F /PID %%a >nul 2>&1
        echo ✅ 已終止佔用端口的進程 (PID: %%a)
    )
    timeout /t 2 /nobreak >nul
)

REM 設定 PYTHONPATH
set "PYTHONPATH=%VENV_PATH%\Lib\site-packages;%PYTHONPATH%"

echo.
echo 🚀 啟動伺服器...
echo    專案目錄: %PROJECT_ROOT%
echo    Python:   %PYTHON_EXE%
echo    網址:     %SERVER_URL%
echo.

REM 建立啟動資訊
echo {"url":"%SERVER_URL%","timestamp":"%DATE% %TIME%","pid":%PID%} > "%PROJECT_ROOT%.launch_info.json"

REM 啟動伺服器 (背景)
start /b "" "%PYTHON_EXE%" -m uvicorn app:app --host %HOST% --port %PORT%

echo ✅ 伺服器啟動指令已發送
echo.

REM 等待伺服器就緒
echo ⏳ 等待伺服器就緒...
set READY=0
for /l %%i in (1,1,15) do (
    curl -s -f "%SERVER_URL%/health" >nul 2>&1
    if not errorlevel 1 (
        set READY=1
        goto :server_ready
    )
    echo.|set /p=.
    timeout /t 1 /nobreak >nul
)
echo.

:server_ready
if %READY% equ 0 (
    echo ❌ 伺服器啟動超時，請檢查錯誤日誌
    if exist "%PROJECT_ROOT%.launch_info.json" del "%PROJECT_ROOT%.launch_info.json"
    pause
    exit /b 1
)

echo ✅ 伺服器就緒！
echo.

REM 開啟瀏覽器
echo 🌐 正在開啟瀏覽器...
start "" "%SERVER_URL%"
echo ✅ 瀏覽器已開啟
echo.

echo ═══════════════════════════════════════════════════════════════
echo   ScoreOCR Toolkit 正在運行中...
echo   訪問地址: %SERVER_URL%
echo   停止伺服器: 按 Ctrl+C 或關閉此視窗
echo ═══════════════════════════════════════════════════════════════
echo.

REM 保持視窗開啟
echo 按任意鍵停止伺服器並退出...
pause >nul

REM 清理
if exist "%PROJECT_ROOT%.launch_info.json" del "%PROJECT_ROOT%.launch_info.json"
taskkill /F /IM python.exe /FI "WINDOWTITLE eq *uvicorn*" >nul 2>&1
echo 🛑 伺服器已停止