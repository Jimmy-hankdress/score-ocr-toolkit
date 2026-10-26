"""本機檔案服務：原子寫入、checksum、路徑安全與備份輪替。

規劃書第 11 章：保存先寫暫存檔再原子 rename；保存前建立上一版本備份；
檔案路徑不得穿越資料根目錄。
"""
from __future__ import annotations

import hashlib
import os
import re
import shutil
import time
import unicodedata
import zipfile
from datetime import datetime
from pathlib import Path

from .config import PATHS

_UNSAFE = re.compile(r'[<>:"/\\|?*\x00-\x1f]')


def timestamp_slug() -> str:
    return datetime.now().strftime("%Y%m%d-%H%M%S")


def safe_filename(name: str, fallback: str = "untitled") -> str:
    """保留中文與空白，移除路徑分隔字元與控制字元（規劃書：中文檔名須正確處理）。"""
    name = unicodedata.normalize("NFC", (name or "").strip())
    name = name.replace("\u3000", " ")
    name = _UNSAFE.sub("_", name)
    name = name.strip(" .")
    if not name:
        name = fallback
    return name[:120]


def unique_path(directory: Path, filename: str) -> Path:
    directory.mkdir(parents=True, exist_ok=True)
    candidate = directory / filename
    if not candidate.exists():
        return candidate
    stem, suffix = candidate.stem, candidate.suffix
    for i in range(1, 10000):
        candidate = directory / f"{stem}({i}){suffix}"
        if not candidate.exists():
            return candidate
    return directory / f"{stem}-{int(time.time())}{suffix}"


def resolve_inside(root: Path, relative: str) -> Path:
    """把相對路徑解析到 root 之內，拒絕路徑穿越。

    採「明確拒絕」而非「默默改寫」：絕對路徑、`..`、空位元組，
    以及 Windows 磁碟標記（C:）一律直接拒絕，不推測使用者意圖。
    最後再以 resolve() 的實際路徑確認仍在 root 內（防 symlink 逃逸）。
    """
    raw = str(relative).replace("\\", "/").strip()
    if not raw:
        raise ValueError("路徑不可為空。")
    if raw.startswith("/") or re.match(r"^[A-Za-z]:", raw):
        raise ValueError(f"不接受絕對路徑：{relative}")
    parts = [seg for seg in raw.split("/") if seg not in ("", ".")]
    if any(seg == ".." for seg in parts):
        raise ValueError(f"路徑含上層目錄符號，已拒絕：{relative}")
    if any("\x00" in seg for seg in parts):
        raise ValueError("路徑含非法字元。")
    if not parts:
        raise ValueError("路徑不可為空。")

    root = root.resolve()
    target = root.joinpath(*parts).resolve()
    if target != root and root not in target.parents:
        raise ValueError(f"路徑不在允許的資料目錄內：{relative}")
    return target


def atomic_write_bytes(target: Path, payload: bytes) -> Path:
    target.parent.mkdir(parents=True, exist_ok=True)
    tmp = target.with_name(f".{target.name}.{os.getpid()}.tmp")
    with open(tmp, "wb") as fh:
        fh.write(payload)
        fh.flush()
        os.fsync(fh.fileno())
    os.replace(tmp, target)
    return target


def atomic_write_text(target: Path, text: str, encoding: str = "utf-8") -> Path:
    return atomic_write_bytes(target, text.encode(encoding))


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def sha256_bytes(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def snapshot_version(project_dir: Path, keep: int = 20) -> Path | None:
    """保存前把現有 project.json 複製到 versions/ 作為上一版本備份。"""
    current = project_dir / "project.json"
    if not current.exists():
        return None
    versions = project_dir / "versions"
    versions.mkdir(parents=True, exist_ok=True)
    dest = versions / f"project-{timestamp_slug()}-{int(time.time() * 1000) % 1000:03d}.json"
    shutil.copy2(current, dest)
    existing = sorted(versions.glob("project-*.json"))
    for old in existing[:-keep] if keep > 0 else []:
        try:
            old.unlink()
        except OSError:
            pass
    return dest


def make_backup_zip(project_dir: Path, title: str) -> Path:
    """備份專案為 ZIP，內含 project.json、原始檔、輸出與 checksum 清單。"""
    PATHS.backups.mkdir(parents=True, exist_ok=True)
    zip_path = unique_path(
        PATHS.backups, f"{safe_filename(title, 'project')}-{timestamp_slug()}.zip"
    )
    manifest_lines = [f"# {title}", f"# created: {datetime.now().isoformat(timespec='seconds')}"]
    with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as zf:
        for path in sorted(project_dir.rglob("*")):
            if path.is_file() and not path.name.startswith("."):
                rel = path.relative_to(project_dir)
                zf.write(path, str(rel))
                manifest_lines.append(f"{sha256_file(path)}  {rel.as_posix()}  {path.stat().st_size}")
        zf.writestr("CHECKSUMS.txt", "\n".join(manifest_lines) + "\n")
    return zip_path


def disk_free_bytes(path: Path) -> int:
    try:
        return shutil.disk_usage(path).free
    except OSError:
        return -1
