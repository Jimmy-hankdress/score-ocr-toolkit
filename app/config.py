"""執行環境與路徑設定。

規劃書第 7 章：程式安裝目錄（唯讀 runtime／模型／web 靜態檔）與
使用者資料目錄（可寫入、可備份）必須分離，且全部使用相對路徑或
明確的資料根目錄設定，不得依賴當前工作目錄或系統 PATH。
"""
from __future__ import annotations

import json
import os
import sys
from dataclasses import dataclass, field
from pathlib import Path

APP_NAME = "SheetMusicOMR"
APP_VERSION = "3.0.0"

# 允許導入的副檔名白名單（規劃書 3. 可攜性／安全性）
ALLOWED_IMPORT_EXT = {
    ".pdf",
    ".jpg",
    ".jpeg",
    ".png",
    ".webp",
    ".tif",
    ".tiff",
    ".bmp",
    ".heic",
    ".son",
    ".csv",
    ".tsv",
    ".txt",
    ".json",
}
IMAGE_EXT = {".jpg", ".jpeg", ".png", ".webp", ".tif", ".tiff", ".bmp", ".heic"}
TEXTUAL_EXT = {".son", ".csv", ".tsv", ".txt", ".json"}

MAX_IMPORT_BYTES = 200 * 1024 * 1024  # 200 MB 上限

def install_root() -> Path:
    """程式安裝目錄（唯讀）。PyInstaller 打包後為執行檔所在目錄。"""
    if getattr(sys, "frozen", False):
        return Path(sys.executable).resolve().parent
    return Path(__file__).resolve().parent.parent

def _portable_marker() -> bool:
    return (install_root() / "portable.txt").exists() or os.environ.get(
        "SHEETMUSIC_PORTABLE", ""
    ).lower() in {"1", "true", "yes"}

def default_data_root() -> Path:
    """使用者資料根目錄。

    V2.01 強制修改：永遠使用本地資料目錄 `<安裝目錄>/data`，
    確保與 V1.00 的 `C:\\Users\\...\\AppData\\Local\\SheetMusicOMR\\data` 分離。
    """
    return install_root() / "data"

@dataclass
class Paths:
    """所有執行期路徑集中管理，避免各層自行拼接。"""

    install: Path = field(default_factory=install_root)
    data: Path = field(default_factory=default_data_root)

    # --- 安裝目錄（唯讀） ---
    @property
    def web(self) -> Path:
        return self.install / "web"

    @property
    def runtime(self) -> Path:
        return self.install / "runtime"

    @property
    def models(self) -> Path:
        return self.install / "models"

    # --- 使用者資料目錄（可寫入） ---
    @property
    def projects(self) -> Path:
        return self.data / "projects"

    @property
    def imports(self) -> Path:
        return self.data / "imports"

    @property
    def exports(self) -> Path:
        return self.data / "exports"

    @property
    def backups(self) -> Path:
        return self.data / "backups"

    @property
    def drafts(self) -> Path:
        """使用者編輯中途按下「立即儲存」的固定暫存資料夾（以歌名命名）。"""
        return self.install / "暫存樂譜"

    @property
    def work(self) -> Path:
        """任務暫存（轉圖輸出等），可安全清除。"""
        return self.data / "work"

    @property
    def logs(self) -> Path:
        return self.data.parent / "logs"

    @property
    def config_dir(self) -> Path:
        return self.data.parent / "config"

    @property
    def db_file(self) -> Path:
        return self.data / "sheetmusic.sqlite3"

    @property
    def user_config_file(self) -> Path:
        return self.config_dir / "user-config.json"

    def ensure(self) -> None:
        for p in (
            self.data,
            self.projects,
            self.imports,
            self.exports,
            self.backups,
            self.drafts,
            self.work,
            self.logs,
            self.config_dir,
        ):
            p.mkdir(parents=True, exist_ok=True)

    def describe(self) -> dict:
        return {
            "installRoot": str(self.install),
            "dataRoot": str(self.data),
            "projects": str(self.projects),
            "imports": str(self.imports),
            "exports": str(self.exports),
            "backups": str(self.backups),
            "drafts": str(self.drafts),
            "logs": str(self.logs),
            "config": str(self.config_dir),
            "database": str(self.db_file),
            "portable": _portable_marker(),
        }

# --- 使用者設定 ---
DEFAULT_USER_CONFIG = {
    "autoSaveSeconds": 20,
    "lastProjectId": None,
    "keepVersions": 20,
    "ocrLanguages": "chi_tra+eng",
    "ocrMode": "scoreforge",
    "measuresPerLine": 3,
    "theme": "dark",
    "warnShortMeasures": False,
    "removeRedInk": True,
}

def load_user_config() -> dict:
    """載入使用者設定 (若不存在則使用預設值)"""
    cfg = dict(DEFAULT_USER_CONFIG)
    try:
        if PATHS.user_config_file.exists():
            with open(PATHS.user_config_file, "r", encoding="utf-8") as f:
                stored = json.load(f)
            if isinstance(stored, dict):
                cfg.update(stored)
    except (OSError, json.JSONDecodeError):
        pass
    return cfg

def save_user_config(cfg: dict) -> dict:
    from .storage import atomic_write_text  # 延遲載入避免循環引用

    merged = load_user_config()
    merged.update(cfg or {})
    PATHS.config_dir.mkdir(parents=True, exist_ok=True)
    atomic_write_text(
        PATHS.user_config_file,
        json.dumps(merged, ensure_ascii=False, indent=2),
    )
    return merged

PATHS = Paths()
