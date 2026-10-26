# -*- coding: utf-8 -*-
"""SheetMusicOMR 安裝與啟動引導程式。

為什麼需要這支程式：
    Windows 的 .bat 只能寫純 ASCII（cmd.exe 用系統編碼逐位元組解析），
    因此把「建立虛擬環境 → 安裝依賴 → 啟動服務」的邏輯全部搬到 Python，
    才能給出完整的中文訊息、寫下記錄檔，並在失敗時自動嘗試備用方案。

刻意只使用 Python 3.4 就有的語法（不用 f-string、不用型別標註），
這樣即使使用者的 Python 太舊，也能正確印出「版本太舊」而不是 SyntaxError。

使用方式：
    py -3 bootstrap.py              建立環境後啟動
    py -3 bootstrap.py --check      只做環境檢查
    py -3 bootstrap.py --repair     刪掉 .venv 重新安裝
    py -3 bootstrap.py --no-browser --port 8711   參數會轉交 launcher.py
"""
import os
import shutil
import subprocess
import sys

MIN_VERSION = (3, 10)
IS_WINDOWS = os.name == "nt"


def _locate_project_root():
    """找出真正的專案根目錄（必須同時有 launcher.py 與 app 套件）。

    定位順序：
      1. 本檔所在目錄（正常情況）
      2. 往下一層的子目錄（壓縮檔解到上一層、或把 run.bat 放錯層級）
      3. 往上一層的父目錄
    都找不到就回傳本檔目錄，由主流程印出可讀的錯誤。
    """
    base = os.path.dirname(os.path.abspath(__file__))

    def looks_right(path):
        return os.path.isfile(os.path.join(path, "launcher.py")) and os.path.isdir(
            os.path.join(path, "app")
        )

    if looks_right(base):
        return base
    try:
        for name in sorted(os.listdir(base)):
            child = os.path.join(base, name)
            if os.path.isdir(child) and looks_right(child):
                return child
    except OSError:
        pass
    parent = os.path.dirname(base)
    if parent and parent != base and looks_right(parent):
        return parent
    return base


HERE = _locate_project_root()
LOG_PATH = os.path.join(HERE, "install-log.txt")

# ---------------------------------------------------------------- 輸出與記錄

_log_file = None


def _open_log():
    global _log_file
    try:
        _log_file = open(LOG_PATH, "w", encoding="utf-8")
    except Exception:
        _log_file = None  # 目錄唯讀時仍要能繼續跑，只是沒有記錄檔


def say(text=""):
    """印到畫面並寫入記錄檔；中文在 CP950 主控台也不會讓程式中斷。"""
    line = text if isinstance(text, str) else str(text)
    try:
        print(line)
    except UnicodeEncodeError:
        enc = getattr(sys.stdout, "encoding", None) or "ascii"
        print(line.encode(enc, "replace").decode(enc, "replace"))
    if _log_file is not None:
        try:
            _log_file.write(line + "\n")
            _log_file.flush()
        except Exception:
            pass


def die(*lines):
    say()
    for line in lines:
        say(line)
    say()
    say("完整記錄檔：" + LOG_PATH)
    say("把這個檔案的內容貼給我，就能知道是哪一步卡住。")
    say()
    _close_log()
    sys.exit(1)


def _close_log():
    if _log_file is not None:
        try:
            _log_file.close()
        except Exception:
            pass


# ------------------------------------------------------------ 版本與編碼準備


def prepare_console():
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8", errors="replace")
        except Exception:
            pass  # Python 3.6 以下沒有 reconfigure，交給 say() 的後援處理


def check_python_version():
    ver = sys.version_info
    say("Python 版本：{0}.{1}.{2}".format(ver[0], ver[1], ver[2]))
    say("Python 路徑：" + sys.executable)
    if ver[:2] < MIN_VERSION:
        die(
            "[錯誤] 需要 Python {0}.{1} 或更新版本，你目前這個是 {2}.{3}。".format(
                MIN_VERSION[0], MIN_VERSION[1], ver[0], ver[1]
            ),
            "",
            "解法：到 https://www.python.org/downloads/windows/ 下載安裝，",
            "安裝畫面最下方務必勾選「Add python.exe to PATH」，",
            "裝完後關掉這個視窗重新開一個再執行 run.bat。",
        )


# ------------------------------------------------------------------ 執行指令


def run(args, title):
    """執行外部指令，輸出同時進畫面與記錄檔。回傳結束碼。"""
    say()
    say("--- " + title + " ---")
    say("執行：" + " ".join(args))
    try:
        proc = subprocess.Popen(
            args,
            cwd=HERE,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            universal_newlines=True,
            bufsize=1,
        )
    except OSError as exc:
        say("無法啟動這個指令：" + str(exc))
        return 127
    assert proc.stdout is not None
    for raw in proc.stdout:
        say("    " + raw.rstrip())
    proc.stdout.close()
    return proc.wait()


# ------------------------------------------------------------ 虛擬環境管理


def venv_python(venv_dir):
    if IS_WINDOWS:
        return os.path.join(venv_dir, "Scripts", "python.exe")
    return os.path.join(venv_dir, "bin", "python")


def create_venv(venv_dir):
    say()
    say("[1/3] 建立虛擬環境：" + venv_dir)
    code = run([sys.executable, "-m", "venv", venv_dir], "python -m venv")
    if code == 0 and os.path.exists(venv_python(venv_dir)):
        return True

    # 部分 Windows 精簡安裝或 Linux 發行版缺 ensurepip，改用 --without-pip 再補 pip
    say()
    say("標準做法失敗，改用 --without-pip 再手動補 pip。")
    shutil.rmtree(venv_dir, ignore_errors=True)
    code = run(
        [sys.executable, "-m", "venv", "--without-pip", venv_dir],
        "python -m venv --without-pip",
    )
    if code != 0 or not os.path.exists(venv_python(venv_dir)):
        return False
    code = run([venv_python(venv_dir), "-m", "ensurepip", "--upgrade"], "ensurepip")
    return code == 0


def install_deps(py_exe, target_dir=None):
    """安裝 requirements.txt。先試線上，失敗再試同資料夾的 vendor 離線包。"""
    req = os.path.join(HERE, "requirements.txt")
    if not os.path.exists(req):
        say("[錯誤] 找不到 requirements.txt，壓縮檔可能沒有完整解壓。")
        return False

    base = [py_exe, "-m", "pip", "install"]
    extra = ["--target", target_dir] if target_dir else []

    run(base + ["--upgrade", "pip"], "更新 pip（失敗不影響後續）")

    code = run(base + extra + ["-r", req], "安裝依賴（線上）")
    if code == 0:
        return True

    vendor = os.path.join(HERE, "vendor")
    if os.path.isdir(vendor) and os.listdir(vendor):
        say()
        say("線上安裝失敗，改用 vendor 目錄離線安裝。")
        code = run(
            base + extra + ["--no-index", "--find-links", vendor, "-r", req],
            "安裝依賴（離線 vendor）",
        )
        return code == 0

    say()
    say("線上安裝失敗，而且沒有 vendor 離線套件目錄。")
    return False


def verify_imports(py_exe, env=None):
    # PyMuPDF 新舊版模組名不同（pymupdf / fitz），
    # python-multipart 也有 python_multipart / multipart 兩種，兩邊都要容錯。
    probe = (
        "import importlib, sys\n"
        "need = [('fastapi',), ('uvicorn',), ('PIL',),"
        " ('pymupdf', 'fitz'), ('python_multipart', 'multipart')]\n"
        "missing = []\n"
        "for names in need:\n"
        "    for n in names:\n"
        "        try:\n"
        "            m = importlib.import_module(n)\n"
        "            v = getattr(m, '__version__', '')\n"
        "            print('  OK  ' + n + (' ' + str(v) if v else ''))\n"
        "            break\n"
        "        except Exception:\n"
        "            continue\n"
        "    else:\n"
        "        missing.append('/'.join(names))\n"
        "if missing:\n"
        "    print('  MISSING: ' + ', '.join(missing))\n"
        "sys.exit(1 if missing else 0)\n"
    )
    say()
    say("--- 驗證依賴是否真的裝好 ---")
    try:
        out = subprocess.run(
            [py_exe, "-c", probe],
            cwd=HERE,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            universal_newlines=True,
            env=env,
        )
    except OSError as exc:
        say("無法執行驗證：" + str(exc))
        return False
    for raw in (out.stdout or "").splitlines():
        say("    " + raw.rstrip())
    return out.returncode == 0


# ---------------------------------------------------------------------- 主流程


def main():
    prepare_console()
    _open_log()

    args = sys.argv[1:]
    check_only = "--check-install" in args
    repair = "--repair" in args
    passthrough = [a for a in args if a not in ("--check-install", "--repair")]

    say("=" * 62)
    say("  SheetMusicOMR 安裝／啟動引導")
    say("  專案目錄：" + HERE)
    say("=" * 62)
    check_python_version()

    # 先確定檔案齊全，否則後面裝了依賴也是白忙一場
    missing_files = [
        name
        for name in ("launcher.py", "requirements.txt", "app", "web")
        if not os.path.exists(os.path.join(HERE, name))
    ]
    if missing_files:
        say()
        say("目前目錄內容：")
        try:
            for name in sorted(os.listdir(HERE)):
                say("    " + name)
        except OSError:
            pass
        die(
            "[錯誤] 這個目錄不是完整的專案根目錄，缺少：" + "、".join(missing_files),
            "",
            "壓縮檔解開後所有檔案都在 sheet-music-omr 這個資料夾裡面，",
            "請先進到那個資料夾，再執行裡面的 run.bat。",
            "",
            "資料夾裡應該同時看到：run.bat、bootstrap.py、launcher.py、",
            "requirements.txt、app\\、web\\、samples\\",
        )

    venv_dir = os.path.join(HERE, ".venv")
    if repair:
        say()
        say("--repair：移除舊的 .venv 重新安裝。")
        shutil.rmtree(venv_dir, ignore_errors=True)

    py_exe = venv_python(venv_dir)
    env = None

    if os.path.exists(py_exe):
        say()
        say("[1/3] 已有虛擬環境，跳過建立。")
    elif create_venv(venv_dir):
        say()
        say("[2/3] 安裝依賴（首次執行需要網路，之後就不用了）…")
        if not install_deps(py_exe):
            die(
                "[錯誤] 依賴安裝失敗。常見原因與解法：",
                "",
                "1. 沒有網路：在有網路的電腦執行",
                "       pip download -r requirements.txt -d vendor",
                "   把整個 vendor 資料夾複製到這裡，再重新執行 run.bat。",
                "2. 公司網路有 Proxy：先設定環境變數 HTTPS_PROXY 再重試。",
                "3. 防毒軟體攔截 pip：暫時關閉即時掃描後重試。",
                "4. 資料夾在 OneDrive 或網路磁碟：把整個資料夾複製到",
                "   C:\\SheetMusicOMR 這類本機路徑再重試。",
            )
    else:
        # Plan B：venv 完全建不起來時，直接把套件裝到 libs\ 並用 PYTHONPATH 掛載
        say()
        say("虛擬環境建立失敗，改用備用方案：把依賴裝到 libs 資料夾。")
        libs = os.path.join(HERE, "libs")
        if not install_deps(sys.executable, target_dir=libs):
            die(
                "[錯誤] 虛擬環境與 libs 備用方案都失敗了。",
                "",
                "請確認：",
                "1. 這個資料夾可寫入（不要放在 C:\\Program Files 底下）。",
                "2. Python 安裝時有包含 pip；可執行 python -m pip --version 確認。",
                "3. 若在公司電腦，可能被群組原則限制寫入。",
            )
        py_exe = sys.executable
        env = dict(os.environ)
        env["PYTHONPATH"] = libs + os.pathsep + env.get("PYTHONPATH", "")

    if not verify_imports(py_exe, env=env):
        die(
            "[錯誤] 依賴看起來裝了，但匯入時失敗。",
            "",
            "最快的解法是執行修復重裝：",
            "    py -3 bootstrap.py --repair",
        )

    say()
    say("環境就緒。")

    if check_only:
        say("（--check-install：只做安裝檢查，不啟動服務）")
        _close_log()
        return 0

    say()
    say("[3/3] 啟動本地服務…（在此視窗按 Ctrl+C 可停止）")
    say("記錄檔：" + LOG_PATH)
    say()
    _close_log()

    cmd = [py_exe, os.path.join(HERE, "launcher.py")] + passthrough
    try:
        return subprocess.call(cmd, cwd=HERE, env=env)
    except KeyboardInterrupt:
        return 0


if __name__ == "__main__":
    sys.exit(main())
