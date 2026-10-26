"""
jianpu2_patch.py — 六線譜幾何屏蔽與行分離

原理：
- 使用 OpenCV HoughLinesP 偵測水平譜線
- 將譜線密集區域視為六線譜 staff → 建立遮罩 mask
- mask 遮住 staff 區域，留下簡譜行 + 歌詞行
- 將分離出的行轉為 OcrLine 格式，回傳給 pipeline 合併處理

回傳格式：
- masked_image: ndarray — 帶遮罩的影像
- ocr_lines: list[OcrLine] — 簡譜與歌詞行的 token 清單
"""

from __future__ import annotations
import re
from pathlib import Path

import numpy as np
import cv2


# ----------------------------------------------------------------------
# Hough 譜線偵測
# ----------------------------------------------------------------------

def _hough_staff_lines(gray_img):
    """
    回傳一組水平譜線的 y 座標 (大致)。
    - Canny edge + HoughLinesP
    - 濾掉非水平線 (|Δx| < |Δy| 反向排除)
    - 合併相近 y 座標
    """
    if gray_img is None or gray_img.size == 0:
        return []

    blur = cv2.GaussianBlur(gray_img, (3, 3), 0)
    edges = cv2.Canny(blur, 50, 150)

    lines = cv2.HoughLinesP(
        edges,
        rho=1,
        theta=np.pi / 180,
        threshold=50,
        minLineLength=30,
        maxLineGap=8,
    )
    if lines is None:
        return []

    ys = []
    for ln in lines:
        x1, y1, x2, y2 = ln[0]
        dx = abs(x2 - x1)
        dy = abs(y2 - y1)
        # 幾乎水平 → 接受
        if dx > dy:
            ys.append((y1 + y2) / 2)

    if not ys:
        return []

    ys.sort()
    #合併相近 (5px內)
    merged = [ys[0]]
    for y in ys[1:]:
        if y - merged[-1] < 5:
            merged[-1] = (merged[-1] + y) / 2
        else:
            merged.append(y)
    return merged


def mask_tab_staff_geometric(image_path, output_mask_dir=None):
    """
    對單一頁面影像做六線譜遮罩。

    Args:
        image_path: str | Path — 要處理的影像路徑
        output_mask_dir: Path | None — 若提供，將遮罩結果存為 PNG 於該目錄

    Returns:
        masked_img: ndarray (BGR) — 帶遮罩的影像 (staff 區域為白色)
        staff_boxes: list[tuple[int,int]] — (top, bottom) y 座標對
    """
    img = cv2.imread(str(image_path), cv2.IMREAD_COLOR)
    if img is None:
        raise FileNotFoundError(f"無法讀取影像：{image_path}")

    h, w = img.shape[:2]
    if h < 40 or w < 40:
        return img, []

    gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
    staff_ys = _hough_staff_lines(gray)

    mask = np.zeros((h, w), dtype=np.uint8)

    staff_boxes = []
    if len(staff_ys) >= 3:
        # 每 3 條線為一組 staff (五線譜 / 六線譜皆可)
        i = 0
        while i + 2 < len(staff_ys):
            y0 = max(0, int(staff_ys[i] - 8))
            y1 = min(h, int(staff_ys[i + 2] + 8))
            if y1 > y0:
                mask[y0:y1, :] = 255
                staff_boxes.append((y0, y1))
            i += 3
    else:
        # 譜線不足 3 條 → 不屏蔽
        pass

    masked_img = img.copy()
    masked_img[mask == 255] = (255, 255, 255)

    if output_mask_dir is not None:
        output_mask_dir.mkdir(parents=True, exist_ok=True)
        mask_path_name = Path(image_path).stem + '_mask.png'
        cv2.imwrite(str(output_mask_dir / mask_path_name), mask)

    return masked_img, staff_boxes


# ----------------------------------------------------------------------
# 行分離與 OcrLine 轉換（返回給 pipeline 的格式）
# ----------------------------------------------------------------------

from .engine import OcrLine


# 簡譜數字 + 特殊符號的 regex（供 lyrics/chord 過濾使用）
DIGIT_OR_SYMBOL = re.compile(r"[0-9#*b/\-+.,]|[a-gA-G][m7M0-9#b]")


def _estimate_line_top_bottom(y_center, h_img, line_height_ratio=0.25):
    """估算一行的上下邊界"""
    top = max(0, int(y_center - h_img * line_height_ratio / 2))
    bottom = min(h_img, int(y_center + h_img * line_height_ratio / 2))
    return top, bottom


def split_staff_and_jianpu_lines(masked_img, page_width_px, work_dir=None):
    """
    將帶遮罩的影像中，非 staff 區域的行，轉為 OcrLine 列表。

    Args:
        masked_img: ndarray (BGR) — 已遮掉 staff 區域的影像
        page_width_px: int — 頁面寬度（像素），用於幾何估算
        work_dir: Path | None — 若提供，可儲存中間切割圖（除錯用）

    Returns:
        jianpu_lines: list[OcrLine] — 簡譜數字行
        lyric_lines: list[OcrLine] — 歌詞行
    """
    if masked_img is None or masked_img.size == 0:
        return [], []

    h, w = masked_img.shape[:2]
    if h < 40 or w < 40:
        return [], []

    gray = cv2.cvtColor(masked_img, cv2.COLOR_BGR2GRAY)

    staff_ys = _hough_staff_lines(gray)

    staff_lines_set = set()
    if len(staff_ys) >= 3:
        i = 0
        while i + 2 < len(staff_ys):
            y0 = max(0, int(staff_ys[i] - 8))
            y1 = min(h, int(staff_ys[i + 2] + 8))
            if y1 > y0:
                for y in range(y0, y1):
                    staff_lines_set.add(y)
            i += 3

    # 找所有水平 pixel-row：哪些 row 完全不在 staff？
    all_rows_h = h
    non_staff_rows_mask = np.ones(all_rows_h, dtype=bool)
    for y in range(all_rows_h):
        if y in staff_lines_set:
            non_staff_rows_mask[y] = False

    # 找連續 non_staff 區域 → 行 candidate
    row_segments = []
    in_seg = False
    start_y = None
    for y in range(all_rows_h):
        if non_staff_rows_mask[y] and not in_seg:
            start_y = y
            in_seg = True
        elif (not non_staff_rows_mask[y]) and in_seg:
            row_segments.append((start_y, y))
            in_seg = False
    if in_seg:
        row_segments.append((start_y, all_rows_h))

    if not row_segments:
        return [], []

    jianpu_lines = []
    lyric_lines = []

    for top_y, bottom_y in row_segments:
        row_height = bottom_y - top_y
        if row_height < 12:
            continue
        # 裁剪該行 ROI
        roi_color = masked_img[top_y:bottom_y, :]
        roi_gray = gray[top_y:bottom_y, :]

        # 辨識文字 (簡譜 / 和弦 / 歌詞)
        # 這裡直接呼叫 Tesseract — 保留原本 jianpu2 邏輯（不做固定座標）
        import pytesseract
        text = pytesseract.image_to_string(roi_gray, lang='chi_tra+eng', config='--psm 6 -c tessedit_char_whitelist=0123456789#*.-+ abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ')

        if not text.strip():
            continue

        # 判斷是否為歌詞行（CJK 比例高）
        cjk_matches = len(re.findall(r'[\u4e00-\u9fff]', text))
        total_chars = len(text.strip())
        ratio_cjk = cjk_matches / max(total_chars, 1)

        line_confidence = 0.85
        tokens = text.strip().split()

        line_info = {
            'text': text.strip(),
            'tokens': tokens,
            'confidence': line_confidence,
            'top': top_y,
            'bottom': bottom_y,
            'left': 0,
            'right': w,
        }

        if ratio_cjk > 0.15:
            # 歌詞行
            lyric_lines.append(OcrLine(**line_info))
        else:
            # 簡譜數字行
            jianpu_lines.append(OcrLine(**line_info))

    if work_dir is not None:
        work_dir.mkdir(parents=True, exist_ok=True)
        for idx, (top_y, bottom_y) in enumerate(row_segments):
            roi = masked_img[top_y:bottom_y, :]
            cv2.imwrite(str(work_dir / f"row_{idx:03d}_top{top_y}.png"), roi)

    return jianpu_lines, lyric_lines


# ----------------------------------------------------------------------
# CLI 除錯（直接執行 python -m app.omr.jianpu2_patch <image>）
# ----------------------------------------------------------------------

if __name__ == '__main__':
    import argparse

    ap = argparse.ArgumentParser()
    ap.add_argument('image', type=str, help='輸入影像 (PDF 轉 PNG 或 JPG)')
    ap.add_argument('--maskdir', type=str, default=None, help='儲存遮罩圖的目錄')
    args = ap.parse_args()

    masked, boxes = mask_tab_staff_geometric(args.image, output_mask_dir=args.maskdir)
    print(f'Staff boxes: {boxes}')

    jianpu, lyric = split_staff_and_jianpu_lines(masked, 1200)
    print(f'\n Jianpu ({len(jianpu)} 行):')
    for ln in jianpu:
        print(f'  [{ln.top}-{ln.bottom}] {ln.text[:80]!r}'[:120])

    print(f'\n Lyrics ({len(lyric)} 行):')
    for ln in lyric:
        print(f'  [{ln.top}-{ln.bottom}] {ln.text[:80]!r}'[:120])
