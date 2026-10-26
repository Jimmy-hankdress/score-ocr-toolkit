#!/bin/bash
# ScoreOCR Toolkit 啟動腳本 (Linux/macOS/Git Bash)
# 自動啟動伺服器並開啟瀏覽器

set -e

PROJECT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
VENV_PATH="$PROJECT_ROOT/.venv"
PYTHON_EXE="$VENV_PATH/bin/python"
PORT=8000
HOST="127.0.0.1"
SERVER_URL="http://$HOST:$PORT"

# 顏色定義
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
CYAN='\033[0;36m'
NC='\033[0m' # No Color

print_header() {
    echo -e "${CYAN}╔══════════════════════════════════════════════════════════════╗${NC}"
    echo -e "${CYAN}║           ScoreOCR Toolkit 啟動器 v3.00                      ║${NC}"
    echo -e "${CYAN}║           SheetMusicOMR 樂譜編輯器                            ║${NC}"
    echo -e "${CYAN}╚══════════════════════════════════════════════════════════════╝${NC}"
    echo
}

check_venv() {
    if [ ! -f "$PYTHON_EXE" ]; then
        echo -e "${RED}❌ 找不到虛擬環境: $PYTHON_EXE${NC}"
        echo "請先建立虛擬環境並安裝依賴:"
        echo "  python -m venv .venv"
        echo "  source .venv/bin/activate"
        echo "  pip install -r requirements.txt"
        exit 1
    fi
}

check_deps() {
    echo -e "${YELLOW}🔍 檢查依賴...${NC}"
    if ! "$PYTHON_EXE" -c "import cv2, numpy, fastapi, uvicorn, pydantic, pypdfium2, PIL" 2>/dev/null; then
        echo -e "${YELLOW}⚠️  缺少依賴，正在安裝...${NC}"
        "$PYTHON_EXE" -m pip install -r "$PROJECT_ROOT/requirements.txt" --quiet
        if [ $? -ne 0 ]; then
            echo -e "${RED}❌ 依賴安裝失敗${NC}"
            exit 1
        fi
        echo -e "${GREEN}✅ 依賴安裝完成${NC}"
    fi
}

check_port() {
    if lsof -ti:$PORT >/dev/null 2>&1; then
        echo -e "${YELLOW}⚠️  端口 $PORT 已被佔用，嘗試關閉現有進程...${NC}"
        lsof -ti:$PORT | xargs kill -9 2>/dev/null
        echo -e "${GREEN}✅ 已終止佔用端口的進程${NC}"
        sleep 1
    fi
}

start_server() {
    export PYTHONPATH="$VENV_PATH/lib/python3.11/site-packages:$PYTHONPATH"
    
    echo -e "${GREEN}🚀 啟動伺服器...${NC}"
    echo "   專案目錄: $PROJECT_ROOT"
    echo "   Python:   $PYTHON_EXE"
    echo -e "   網址:     ${CYAN}$SERVER_URL${NC}"
    echo

    # 建立啟動資訊
    cat > "$PROJECT_ROOT/.launch_info.json" <<EOF
{"url":"$SERVER_URL","timestamp":"$(date '+%Y-%m-%d %H:%M:%S')","pid":$$}
EOF

    # 背景啟動伺服器
    cd "$PROJECT_ROOT"
    "$PYTHON_EXE" -m uvicorn app:app --host "$HOST" --port "$PORT" > server.log 2>&1 &
    SERVER_PID=$!
    echo $SERVER_PID > "$PROJECT_ROOT/.server.pid"
    
    echo -e "${GREEN}✅ 伺服器已啟動 (PID: $SERVER_PID)${NC}"
    echo
}

wait_for_server() {
    echo -e "${YELLOW}⏳ 等待伺服器就緒...${NC}"
    for i in {1..15}; do
        if curl -s -f "$SERVER_URL/health" >/dev/null 2>&1; then
            echo -e "${GREEN}✅ 伺服器就緒！${NC}"
            return 0
        fi
        echo -n "."
        sleep 1
    done
    echo
    echo -e "${RED}❌ 伺服器啟動超時${NC}"
    return 1
}

open_browser() {
    echo -e "${CYAN}🌐 正在開啟瀏覽器...${NC}"
    case "$(uname -s)" in
        Darwin) open "$SERVER_URL" ;;
        Linux)  xdg-open "$SERVER_URL" ;;
        CYGWIN*|MINGW*|MSYS*) start "" "$SERVER_URL" ;;
        *) echo "請手動開啟: $SERVER_URL" ;;
    esac
    echo -e "${GREEN}✅ 瀏覽器已開啟${NC}"
}

cleanup() {
    echo
    echo -e "${YELLOW}🛑 正在停止伺服器...${NC}"
    if [ -f "$PROJECT_ROOT/.server.pid" ]; then
        SERVER_PID=$(cat "$PROJECT_ROOT/.server.pid")
        kill $SERVER_PID 2>/dev/null
        rm -f "$PROJECT_ROOT/.server.pid"
    fi
    if [ -f "$PROJECT_ROOT/.launch_info.json" ]; then
        rm -f "$PROJECT_ROOT/.launch_info.json"
    fi
    echo -e "${YELLOW}🛑 伺服器已停止${NC}"
}

# 主流程
print_header
check_venv
check_deps
check_port
start_server

if wait_for_server; then
    open_browser
    echo
    echo -e "${CYAN}═══════════════════════════════════════════════════════════════${NC}"
    echo -e "  ScoreOCR Toolkit 正在運行中..."
    echo -e "  ${CYAN}訪問地址: $SERVER_URL${NC}"
    echo -e "  ${YELLOW}停止伺服器: 按 Ctrl+C${NC}"
    echo -e "${CYAN}═══════════════════════════════════════════════════════════════${NC}"
    echo
    
    # 等待 Ctrl+C
    trap cleanup INT TERM
    wait $SERVER_PID
else
    cleanup
    exit 1
fi