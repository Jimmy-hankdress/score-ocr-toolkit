"""PDF／影像 → 高解析度頁面影像（規劃書 8.1 第二階段「轉圖」）。

後端優先序：PyMuPDF（隨 Python 套件，無需 Poppler）→ 隨包 Poppler pdftoppm。
影像預處理：灰階、放大到適合 OCR 的解析度、自動對比與二值化。
"""
from __future__ import annotations

import json
import shutil
import subprocess
import sys
from pathlib import Path

from ..config import PATHS

TARGET_DPI = 300
MIN_OCR_WIDTH = 1600

# 註冊 HEIC 解碼器（若已安裝 pillow-heif），讓 PIL 能開啟 .heic 檔
try:
    import pillow_heif as _pillow_heif

    _pillow_heif.register_heif_opener()
except ImportError:
    pass


def _exe(name: str) -> str:
    return f"{name}.exe" if sys.platform.startswith("win") else name


def pdf_page_count(pdf: Path) -> int:
    try:
        from ._pymupdf import fitz

        with fitz.open(str(pdf)) as doc:
            return doc.page_count
    except ImportError:
        pass
    tool = PATHS.runtime / "poppler" / "bin" / _exe("pdfinfo")
    exe = str(tool) if tool.exists() else shutil.which("pdfinfo")
    if not exe:
        return 0
    proc = subprocess.run([exe, str(pdf)], capture_output=True, text=True, timeout=120)
    for line in (proc.stdout or "").splitlines():
        if line.lower().startswith("pages:"):
            try:
                return int(line.split(":", 1)[1].strip())
            except ValueError:
                return 0
    return 0


def pdf_to_images(pdf: Path, out_dir: Path, dpi: int = TARGET_DPI, progress=None) -> list[Path]:
    out_dir.mkdir(parents=True, exist_ok=True)
    try:
        from ._pymupdf import fitz

        pages: list[Path] = []
        with fitz.open(str(pdf)) as doc:
            total = doc.page_count
            if total == 0:
                raise RuntimeError("PDF 沒有可轉換的頁面。")
            zoom = dpi / 72.0
            matrix = fitz.Matrix(zoom, zoom)
            for index, page in enumerate(doc, start=1):
                pix = page.get_pixmap(matrix=matrix, alpha=False)
                target = out_dir / f"page-{index:03d}.png"
                pix.save(str(target))
                pages.append(target)
                if progress:
                    progress(index, total)
        return pages
    except ImportError:
        pass

    tool = PATHS.runtime / "poppler" / "bin" / _exe("pdftoppm")
    exe = str(tool) if tool.exists() else shutil.which("pdftoppm")
    if not exe:
        raise RuntimeError(
            "找不到 PDF 轉圖後端。請確認安裝包已內含 PyMuPDF 或 runtime/poppler/bin/pdftoppm。"
        )
    prefix = out_dir / "page"
    proc = subprocess.run(
        [exe, "-r", str(dpi), "-png", str(pdf), str(prefix)],
        capture_output=True,
        text=True,
        timeout=1800,
    )
    if proc.returncode != 0:
        raise RuntimeError(f"PDF 轉圖失敗：{(proc.stderr or '').strip()[:400]}")
    pages = sorted(out_dir.glob("page-*.png"))
    if not pages:
        raise RuntimeError("PDF 轉圖後找不到輸出影像。")
    if progress:
        progress(len(pages), len(pages))
    return pages


def _remove_red_ink(rgb):
    """去除手寫稿上的所有「紅色手繪標記」（直線、圓、箭頭、短劃、紅筆圈等）。

    這些紅墨與簡譜／歌詞／和弦無關，若不清除會被 OMR 誤讀成符號。
    偵測策略：HSV 顏色空間取「色相在紅區（0-12 ∪ 168-180）＋ 飽和度 ≥ 40
    ＋ 亮度 ≥ 60」的像素——能抓到鮮紅、朱紅筆跡，同時排除灰白紙張（低飽和）
    與純黑數字（低亮度）。對抓到的每個紅色連通區塊（面積 ≥ min_area）整區
    填白，因此無論標記是長線、短劃、圓圈或箭頭都會被移除。

    回傳 (清除後的 RGB PIL image, 移除的標記數, 移除的像素數)。
    """
    try:
        import cv2
        import numpy as np
        from PIL import Image as _Image
    except ImportError:  # cv2 不可用時跳過此步驟，維持既有行為
        return rgb, 0, 0

    arr = np.array(rgb).astype(np.uint8)
    bgr = cv2.cvtColor(arr, cv2.COLOR_RGB2BGR)
    hsv = cv2.cvtColor(bgr, cv2.COLOR_BGR2HSV)
    h = hsv[:, :, 0].astype(np.int16)
    s = hsv[:, :, 1].astype(np.int16)
    v = hsv[:, :, 2].astype(np.int16)
    # 紅色色相在 HSV 兩個端點（0 與 180），分兩段取
    red_hue = ((h <= 12) | (h >= 168)) & (s >= 40) & (v >= 60)
    if not red_hue.any():
        return rgb, 0, 0
    mask = (red_hue.astype(np.uint8)) * 255
    # 小 dilation 把抗鋸齒的粉紅邊緣一併清掉
    mask = cv2.dilate(mask, np.ones((3, 3), np.uint8))
    n, labels, stats, _ = cv2.connectedComponentsWithStats(mask, connectivity=8)
    min_area = 12  # 過濾 JPEG 雜訊小點；手繪筆跡遠大於此
    removed_px = 0
    removed_cnt = 0
    out = arr.copy()
    for i in range(1, n):
        area = int(stats[i, cv2.CC_STAT_AREA])
        if area >= min_area:
            out[labels == i] = 255
            removed_px += area
            removed_cnt += 1
    if removed_cnt == 0:
        return rgb, 0, 0
    return _Image.fromarray(out), removed_cnt, removed_px


def _log_red_ink_removed(out_dir: Path, components: int, pixels: int) -> None:
    """把「已去除紅墨標記」記到預處理目錄的 sidecar JSON，供 pipeline 汇入警告。"""
    if components <= 0:
        return
    log_file = out_dir / "red_ink_removed.json"
    try:
        entries = json.loads(log_file.read_text(encoding="utf-8")) if log_file.exists() else []
        entries.append({"components": int(components), "pixels": int(pixels)})
        log_file.write_text(json.dumps(entries, ensure_ascii=False, indent=2), encoding="utf-8")
    except (OSError, json.JSONDecodeError):
        pass


def load_red_ink_report(prep_dir: Path) -> list:
    """讀取預處理時產生的紅墨去除報告（[{components, pixels}, ...]）。"""
    p = Path(prep_dir) / "red_ink_removed.json"
    if not p.exists():
        return []
    try:
        data = json.loads(p.read_text(encoding="utf-8"))
        return data if isinstance(data, list) else []
    except (OSError, json.JSONDecodeError):
        return []


def preprocess_image(src: Path, out_dir: Path, binarize: bool = True, remove_red_ink: bool = True) -> Path:
    """灰階 → 放大 → 自動對比（→ 二值化）。

    `binarize=False` 是給簡譜幾何分析用的，實測出兩件事：

    1. 固定門檻的硬性二值化會把高低音圓點與減時線這些只有幾個像素的
       細小筆畫消掉，改由分析模組自己的 Otsu 自適應門檻處理。
    2. **`autocontrast` 對幾何分析是有害的**。樂譜頁面絕大多數是白底，
       拉對比會把 JPEG 壓縮的暗暈（ringing）一併拉成墨色，墨點數從
       2.1 萬暴增到 3.7 萬，造出大量假圓點（實測從全對掉到幾乎全錯）。
       因此這條路徑只做灰階、必要放大，加上一層中值濾波去除掃描雜點。
    """
    out_dir.mkdir(parents=True, exist_ok=True)
    suffix = "-prep" if binarize else "-gray"
    target = out_dir / f"{src.stem}{suffix}.png"
    try:
        from PIL import Image, ImageOps
    except ImportError:
        shutil.copy2(src, target)
        return target
    with Image.open(src) as im:
        # 去除手寫稿上的紅色手繪標記（紅筆直線、圓、箭頭、短劃等）：
        # 這些紅墨與簡譜／歌詞／和弦無關，清掉後才不會被 OMR 誤讀成符號。
        if im.mode != "L" and remove_red_ink:
            im, _comp, _px = _remove_red_ink(im)
            if _comp:
                _log_red_ink_removed(out_dir, _comp, _px)
        im = im.convert("L")
        # 簡譜幾何分析（binarize=False）不做強制放大：
        # 幾何參數（圓點像素數、減時線、字高、active 門檻 width*0.012）都是為原始
        # 掃描解析度校準的；放大到 1600px 會把緊密排列的行併成超大 band、字團黏連，
        # 破壞行切分與符號識別。只用中值濾波去雜點。
        if binarize and im.width < MIN_OCR_WIDTH:
            scale = MIN_OCR_WIDTH / im.width
            im = im.resize((int(im.width * scale), int(im.height * scale)), Image.LANCZOS)
        if binarize:
            im = ImageOps.autocontrast(im, cutoff=1)
            im = im.point(lambda px: 255 if px > 165 else 0, mode="1")
        # binarize=False（簡譜幾何分析）：只轉灰階，不做任何濾波/放大/對比。
        # 濾波會改變墨跡密度分布、放大會改變行列與字團尺寸，都破壞行切分與符號識別。
        im.save(target)
    return target


def prepare_pages(
    source: Path,
    kind: str,
    work_dir: Path,
    progress=None,
    binarize: bool = True,
    remove_red_ink: bool = True,
) -> list[Path]:
    """回傳已預處理、可直接送 OCR 的頁面影像清單。"""
    raw_dir = work_dir / "pages"
    prep_dir = work_dir / "prepared"
    if kind == "pdf":
        raw_pages = pdf_to_images(source, raw_dir, progress=progress)
    else:
        raw_dir.mkdir(parents=True, exist_ok=True)
        copied = raw_dir / f"page-001{source.suffix.lower()}"
        shutil.copy2(source, copied)
        raw_pages = [copied]
        if progress:
            progress(1, 1)
    return [
        preprocess_image(p, prep_dir, binarize=binarize, remove_red_ink=remove_red_ink)
        for p in raw_pages
    ]
