"""SheetMusicOMR 啟動器（規劃書 9.1）。

職責：檢查資源與 runtime → 建立本地資料目錄 → 啟動只監聽 127.0.0.1 的本地服務
→ 自動開啟預設瀏覽器 → 優雅關閉。

使用方式：
    雙擊 SheetMusicOMR.exe            （打包後）
    python launcher.py                （開發環境）
    python launcher.py --port 8711 --no-browser
    python launcher.py --data-dir D:\\MyScores --check
"""
from __future__ import annotations

import argparse
import logging
import os
import socket
import sys
import threading
import time
import webbrowser
from logging.handlers import RotatingFileHandler
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

# --- Python 版本守衛 -------------------------------------------------------
# 必須在 import app.* 之前檢查：本專案使用 3.10+ 的 `X | None` 型別寫法，
# 舊版 Python 會直接抱 SyntaxError，使用者看不懂。這裡改成可讀的中文說明。
if sys.version_info < (3, 10):
    sys.stderr.write(
        f"\n[錯誤] 需要 Python 3.10 或更新版本，目前執行的是 "
        f"{sys.version_info.major}.{sys.version_info.minor}.{sys.version_info.micro}。\n"
        f"       執行檔位置：{sys.executable}\n"
        "       請到 https://www.python.org/downloads/ 安裝新版，"
        "安裝時務必勾選 Add python.exe to PATH。\n\n"
    )
    raise SystemExit(2)

# --- Windows 主控台編碼強化 -------------------------------------------------
# 繁中 Windows 預設 CP950，若輸出被重新導向檔案或管線，印出 ♪、／ 等
# 非 Big5 字元會抱 UnicodeEncodeError。統一改成 UTF-8 且不因編碼而中斷。
for _stream in (sys.stdout, sys.stderr):
    try:
        _stream.reconfigure(encoding="utf-8", errors="replace")
    except (AttributeError, ValueError, OSError):
        pass  # 被封裝或不支援時略過，不影響主流程

from app.config import APP_NAME, APP_VERSION, PATHS  # noqa: E402

DEFAULT_PORT = 8756
BANNER = f"""
  {APP_NAME} {APP_VERSION} — 樂譜數位化與本地化打譜工具
  全程本地執行，只監聽 127.0.0.1，不呼叫任何外部服務。
"""


def setup_logging(verbose: bool = False) -> Path:
    PATHS.ensure()
    log_file = PATHS.logs / "launcher.log"
    handlers: list[logging.Handler] = [
        RotatingFileHandler(log_file, maxBytes=2_000_000, backupCount=3, encoding="utf-8"),
        logging.StreamHandler(sys.stdout),
    ]
    logging.basicConfig(
        level=logging.DEBUG if verbose else logging.INFO,
        format="%(asctime)s %(levelname)-7s %(name)s | %(message)s",
        handlers=handlers,
        force=True,
    )
    return log_file


def pick_port(preferred: int) -> int:
    """優先使用指定 port，被佔用則自動找可用 port（只綁 127.0.0.1）。"""
    for candidate in [preferred, *range(preferred + 1, preferred + 25)]:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            try:
                s.bind(("127.0.0.1", candidate))
                return candidate
            except OSError:
                continue
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def preflight() -> list[str]:
    """啟動前資源檢查；回傳警告清單（缺 OMR 引擎不阻止啟動，但會明確標示）。"""
    log = logging.getLogger("launcher.preflight")
    warnings: list[str] = []

    if not (PATHS.web / "index.html").exists():
        raise SystemExit(
            f"缺少前端資源：{PATHS.web / 'index.html'}\n"
            "請確認安裝包內含 web/ 目錄（不可只複製執行檔）。"
        )

    try:
        import fastapi  # noqa: F401
        import uvicorn  # noqa: F401
    except ImportError as exc:  # 開發環境未安裝依賴
        raise SystemExit(
            f"缺少必要套件：{exc.name}。開發環境請先執行：pip install -r requirements.txt"
        ) from exc

    manifest = PATHS.models / "manifest.json"
    if manifest.exists():
        import hashlib
        import json

        try:
            data = json.loads(manifest.read_text(encoding="utf-8"))
            for item in data.get("files", []):
                target = PATHS.models / item["path"]
                if not target.exists():
                    warnings.append(f"模型檔缺少：{item['path']}")
                    continue
                if item.get("sha256"):
                    digest = hashlib.sha256(target.read_bytes()).hexdigest()
                    if digest != item["sha256"]:
                        warnings.append(f"模型 checksum 不符：{item['path']}")
        except (OSError, ValueError, KeyError) as exc:
            warnings.append(f"模型 manifest 無法讀取：{exc}")

    from app.omr.engine import detect_engine

    engine = detect_engine()
    if engine.available:
        log.info("OMR 引擎：%s（%s）語言 %s", engine.mode, engine.version, "+".join(engine.languages) or "?")
    else:
        warnings.append(engine.note or "OMR 引擎不可用；PDF／影像辨識會直接失敗。")
    if engine.note and engine.available:
        warnings.append(engine.note)
    if not engine.pdf_backend:
        warnings.append("找不到 PDF 轉圖後端（PyMuPDF 或 Poppler）。")

    free = 0
    try:
        import shutil

        free = shutil.disk_usage(PATHS.data).free
    except OSError:
        pass
    if 0 < free < 50 * 1024 * 1024:
        warnings.append(f"資料目錄可用空間僅 {free / 1048576:.0f} MB，建議清理後再使用。")
    return [w for w in warnings if w]


def open_browser_later(url: str, delay: float = 1.2) -> None:
    def _open() -> None:
        time.sleep(delay)
        try:
            webbrowser.open(url)
        except Exception as exc:  # noqa: BLE001 瀏覽器開啟失敗不可中斷服務
            logging.getLogger("launcher").warning("無法自動開啟瀏覽器：%s（請手動開啟 %s）", exc, url)

    threading.Thread(target=_open, daemon=True).start()


def cleanup_temporary() -> int:
    """每次啟動時清除上次的臨時任務檔案。

    只清兩類「可重建」的臨時資料，絕不動使用者保存的項目／匯出／資料庫：
      - data/work/     轉圖逐頁影像、辨識中間檔（任務暫存，可安全清除）
      - data/imports/  上傳來源的複本（原始檔已保留，可由項目重建）
    回傳清除的檔案數。
    """
    import shutil

    log = logging.getLogger("launcher.cleanup")
    removed = 0
    for sub in ("work", "imports"):
        base = PATHS.data / sub
        if not base.exists():
            continue
        for entry in base.iterdir():
            try:
                if entry.is_dir():
                    shutil.rmtree(entry, ignore_errors=True)
                else:
                    entry.unlink(missing_ok=True)
                removed += 1
            except OSError as exc:  # 被佔用等，略過不中斷啟動
                log.warning("無法清除 %s：%s", entry, exc)
    if removed:
        log.info("已清除 %d 個臨時任務項目（work/ 與 imports/）", removed)
    return removed


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog=APP_NAME, description="樂譜數位化與本地化打譜工具（本地啟動器）")
    parser.add_argument("--port", type=int, default=int(os.environ.get("SHEETMUSIC_PORT", DEFAULT_PORT)))
    parser.add_argument("--data-dir", help="自訂資料根目錄（預設 %%LOCALAPPDATA%%\\SheetMusicOMR\\data）")
    parser.add_argument("--no-browser", action="store_true", help="不自動開啟瀏覽器")
    parser.add_argument("--check", action="store_true", help="只做啟動前檢查後結束")
    parser.add_argument("--verbose", action="store_true")
    args = parser.parse_args(argv)

    if args.data_dir:
        PATHS.data = Path(args.data_dir).expanduser().resolve()

    log_file = setup_logging(args.verbose)
    log = logging.getLogger("launcher")
    print(BANNER)
    log.info("安裝目錄：%s", PATHS.install)
    log.info("資料目錄：%s", PATHS.data)
    log.info("日誌檔　：%s", log_file)

    warnings = preflight()
    for w in warnings:
        log.warning(w)

    # 每次啟動清除上次的臨時任務檔案（work/ 與 imports/）
    cleanup_temporary()

    if args.check:
        print("\n啟動前檢查完成。" + (f" 有 {len(warnings)} 則警告。" if warnings else " 無警告。"))
        return 0

    import uvicorn

    from app.server import create_app

    port = pick_port(args.port)
    url = f"http://127.0.0.1:{port}/"
    app = create_app()

    if not args.no_browser:
        open_browser_later(url)

    print(f"\n  本地網址：{url}")
    print("  若瀏覽器未自動開啟，請複製上面網址貼到瀏覽器。")
    print("  按 Ctrl+C 結束服務（資料不會被刪除）。\n")

    config = uvicorn.Config(
        app,
        host="127.0.0.1",  # 絕不綁 0.0.0.0
        port=port,
        log_level="debug" if args.verbose else "warning",
        access_log=args.verbose,
    )
    server = uvicorn.Server(config)
    try:
        server.run()
    except KeyboardInterrupt:
        pass
    finally:
        log.info("服務已停止，資料保留於 %s", PATHS.data)
        print("\n服務已停止。資料保留於：", PATHS.data)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
