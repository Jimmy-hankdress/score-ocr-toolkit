#!/usr/bin/env bash
# SheetMusicOMR 啟動腳本（Ubuntu／WSL／macOS）
# 實際的安裝與啟動邏輯都在 bootstrap.py，與 Windows 的 run.bat 共用同一套流程。
set -euo pipefail
cd "$(dirname "$0")"

export PYTHONUTF8=1
export PYTHONIOENCODING=utf-8

BOOT=""
for candidate in python3 python; do
  if command -v "$candidate" >/dev/null 2>&1; then
    BOOT="$candidate"
    break
  fi
done

if [ -z "$BOOT" ]; then
  cat <<'MSG'

[錯誤] 找不到 Python。請先安裝 Python 3.10 或更新版本：

  Ubuntu／WSL : sudo apt install python3 python3-venv python3-pip
  macOS       : brew install python@3.12

MSG
  exit 1
fi

echo "使用的 Python：$BOOT ($($BOOT -V 2>&1))"
exec "$BOOT" bootstrap.py "$@"
