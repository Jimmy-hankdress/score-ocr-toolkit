"""OMR 引擎偵測與辨識（規劃書 8.3：必須清楚標示引擎模式，不可用假結果冒充）。

引擎探測順序（全部使用相對路徑，不依賴系統 PATH）：
  1. <install>/runtime/tesseract/tesseract(.exe)   ← 隨包版本
  2. 環境變數 TESSERACT_CMD
  3. 系統 PATH 上的 tesseract（開發環境）
找不到時 `available` 為 False，任務會以可讀錯誤失敗，不會產生假的識別結果。
"""
from __future__ import annotations

import os
import re
import shutil
import subprocess
import sys
from dataclasses import dataclass, field
from pathlib import Path

from ..config import PATHS

CHORD_TOKEN = re.compile(
    r"^[A-G][#b]?(?:maj7|maj|min7|min|m7|m|dim7|dim|aug|sus[24]?|add9|[679]|11|13|M7)?(?:/[A-G][#b]?)?$"
)
CJK = re.compile(r"[\u3400-\u4dbf\u4e00-\u9fff]")
NOTE_CHARS = re.compile(r"[0-7]")


def _exe(name: str) -> str:
    return f"{name}.exe" if sys.platform.startswith("win") else name


def find_tesseract() -> Path | None:
    bundled = PATHS.runtime / "tesseract" / _exe("tesseract")
    if bundled.exists():
        return bundled
    env = os.environ.get("TESSERACT_CMD")
    if env and Path(env).exists():
        return Path(env)
    found = shutil.which("tesseract")
    return Path(found) if found else None


def find_tessdata() -> Path | None:
    bundled = PATHS.runtime / "tesseract" / "tessdata"
    if bundled.exists():
        return bundled
    env = os.environ.get("TESSDATA_PREFIX")
    if env and Path(env).exists():
        return Path(env)
    return None


@dataclass
class EngineStatus:
    available: bool = False
    mode: str = "unavailable"
    version: str = ""
    path: str = ""
    languages: list[str] = field(default_factory=list)
    tessdata: str = ""
    note: str = ""
    pdf_backend: str = ""

    def to_dict(self) -> dict:
        return {
            "available": self.available,
            "mode": self.mode,
            "version": self.version,
            "path": self.path,
            "languages": self.languages,
            "tessdata": self.tessdata,
            "note": self.note,
            "pdfBackend": self.pdf_backend,
        }


def _pdf_backend() -> str:
    try:
        from ._pymupdf import fitz  # noqa: F401  PyMuPDF

        return "pymupdf"
    except ImportError:
        pass
    bundled = PATHS.runtime / "poppler" / "bin" / _exe("pdftoppm")
    if bundled.exists() or shutil.which("pdftoppm"):
        return "poppler"
    return ""


def detect_engine() -> EngineStatus:
    status = EngineStatus(pdf_backend=_pdf_backend())
    exe = find_tesseract()
    if exe is None:
        status.note = (
            "找不到 Tesseract OCR 引擎。請把 Tesseract 放到 "
            f"{PATHS.runtime / 'tesseract'}（隨包模式），或設定環境變數 TESSERACT_CMD。"
            "在引擎就緒前，PDF／影像辨識會直接失敗，不會產生假的識別結果。"
        )
        return status
    env = dict(os.environ)
    tessdata = find_tessdata()
    if tessdata:
        env["TESSDATA_PREFIX"] = str(tessdata.parent if tessdata.name == "tessdata" else tessdata)
        status.tessdata = str(tessdata)
    try:
        ver = subprocess.run(
            [str(exe), "--version"], capture_output=True, text=True, timeout=20, env=env
        )
        langs = subprocess.run(
            [str(exe), "--list-langs"], capture_output=True, text=True, timeout=20, env=env
        )
    except (OSError, subprocess.SubprocessError) as exc:
        status.note = f"Tesseract 無法執行：{exc}"
        return status

    status.available = ver.returncode == 0
    status.mode = "tesseract-ocr" if status.available else "unavailable"
    status.version = (ver.stdout or ver.stderr or "").splitlines()[0].strip() if ver.stdout or ver.stderr else ""
    status.path = str(exe)
    status.languages = [
        line.strip()
        for line in (langs.stdout or "").splitlines()[1:]
        if line.strip() and " " not in line.strip()
    ]
    missing_cjk = not any(l.startswith("chi") for l in status.languages)
    notes = []
    if not status.pdf_backend:
        notes.append("找不到 PDF 轉圖後端（PyMuPDF 或 Poppler），PDF 導入會失敗。")
    if missing_cjk:
        notes.append(
            "未安裝中文語言資料（chi_tra／chi_sim），中文歌詞辨識會不準；"
            "請把 chi_tra.traineddata 放入 tessdata 目錄。"
        )
    status.note = " ".join(notes)
    return status


def ocr_languages(status: EngineStatus, requested: str) -> str:
    """只保留實際存在的語言，避免 Tesseract 因缺語言直接失敗。"""
    wanted = [w for w in re.split(r"[+,\s]+", requested or "") if w]
    have = [w for w in wanted if w in status.languages]
    if not have:
        have = ["eng"] if "eng" in status.languages else (status.languages[:1] or ["eng"])
    return "+".join(dict.fromkeys(have))


@dataclass
class OcrLine:
    text: str
    confidence: float
    top: int
    left: int
    height: int
    lyrics: list[str] = field(default_factory=list)
    chords: list[str] = field(default_factory=list)


def run_ocr_lines(
    image_path: Path, status: EngineStatus, languages: str, psm: int = 6
) -> list[OcrLine]:
    """執行 Tesseract 並以 TSV 輸出重建「行」與逐行平均信心值。"""
    if not status.available:
        raise RuntimeError(status.note or "OMR 引擎不可用。")
    env = dict(os.environ)
    if status.tessdata:
        td = Path(status.tessdata)
        env["TESSDATA_PREFIX"] = str(td.parent if td.name == "tessdata" else td)
    cmd = [
        status.path,
        str(image_path),
        "stdout",
        "-l",
        languages,
        "--psm",
        str(psm),
        "-c",
        "preserve_interword_spaces=1",
        "tsv",
    ]
    proc = subprocess.run(cmd, capture_output=True, text=True, timeout=600, env=env)
    if proc.returncode != 0:
        raise RuntimeError(
            f"Tesseract 辨識失敗（exit {proc.returncode}）：{(proc.stderr or '').strip()[:400]}"
        )
    words: dict[tuple, list] = {}
    for row in (proc.stdout or "").splitlines()[1:]:
        cols = row.split("\t")
        if len(cols) < 12:
            continue
        try:
            block, par, line = int(cols[2]), int(cols[3]), int(cols[4])
            left, top, height = int(cols[6]), int(cols[7]), int(cols[9])
            conf = float(cols[10])
        except ValueError:
            continue
        text = cols[11].strip()
        if not text or conf < 0:
            continue
        words.setdefault((block, par, line), []).append((left, top, height, conf, text))

    lines: list[OcrLine] = []
    for key in sorted(words, key=lambda k: min(w[1] for w in words[k])):
        items = sorted(words[key], key=lambda w: w[0])
        text = " ".join(w[4] for w in items).strip()
        if not text:
            continue
        confs = [w[3] for w in items]
        lines.append(
            OcrLine(
                text=text,
                confidence=round(sum(confs) / len(confs) / 100.0, 3),
                top=min(w[1] for w in items),
                left=min(w[0] for w in items),
                height=max(w[2] for w in items),
            )
        )
    return lines
