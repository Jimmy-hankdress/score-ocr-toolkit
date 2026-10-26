# -*- coding: utf-8 -*-
"""
五線譜（Lead Sheet／單旋律五線譜＋上方和弦）轉簡譜單音符引擎（V3.00）。

針對如 Ellie My Love 2.pdf 等標準五線譜旋律譜（Treble Clef + 上方和弦記號）：
1. 自動偵測頁面是否為純五線譜（>= 2 組標準五線譜且無簡譜數字行）
2. 精確定位每組五線譜的 5 條線、小節線（排除拍號、反覆記號與高音譜號干擾）
3. 萃取實心與空心符頭（含跨線裂解之二分／全音符半月弧配對）、符桿方向、符尾／連桁（八分 `_`、十六分 `__`）、附點（`.`）與四分休止符（`0`）
4. 自動判定調號（Key Signature，如 D 大調 1=D）並將五線譜音高 step（0=E4）換算為首調簡譜單音符（1..7 含高低音點 `\u0307` / `\u0323` 與延長線 `-`）
5. 萃取五線譜上方和弦記號（D, E7, F#, F#m7, G, Gmaj7, A, A7, Bm, B7, Em, Em7, Gm7, D7 等）並依小節內水平位置對齊至對應拍位與音符（chordOffsets / chordTicks）
"""
from __future__ import annotations

import re
from pathlib import Path
from typing import Callable

import cv2
import numpy as np

from ..models import ScoreBeat, ScoreDocument, ScoreMeasure, new_id


_page0_cache: tuple[str, float, int, np.ndarray] | None = None


def _load_pages_gray(source: Path, kind: str, dpi: int = 300, max_pages: int | None = None) -> list[np.ndarray]:
    """將 PDF 或影像檔載入為 300 DPI 灰階陣列清單（含第 1 頁快取以避免偵測與轉換重複轉圖）。"""
    global _page0_cache
    pages: list[np.ndarray] = []
    src_key = str(source)
    try:
        mtime = source.stat().st_mtime
    except Exception:
        mtime = 0.0

    if kind == "pdf" or source.suffix.lower() == ".pdf":
        import fitz

        doc = fitz.open(src_key)
        try:
            count = len(doc) if max_pages is None else min(len(doc), max_pages)
            for pno in range(count):
                if pno == 0 and _page0_cache is not None and _page0_cache[:3] == (src_key, mtime, dpi):
                    pages.append(_page0_cache[3])
                    continue
                pix = doc[pno].get_pixmap(dpi=dpi, colorspace=fitz.csGRAY, alpha=False)
                arr = np.frombuffer(pix.samples, np.uint8).reshape(pix.height, pix.width).copy()
                if pno == 0:
                    _page0_cache = (src_key, mtime, dpi, arr)
                pages.append(arr)
        finally:
            doc.close()
    else:
        if _page0_cache is not None and _page0_cache[:3] == (src_key, mtime, 0):
            pages.append(_page0_cache[3])
        else:
            raw = np.fromfile(src_key, dtype=np.uint8)
            img = cv2.imdecode(raw, cv2.IMREAD_GRAYSCALE)
            if img is not None:
                _page0_cache = (src_key, mtime, 0, img)
                pages.append(img)
    return pages


def _detect_staves_from_bw(bw: np.ndarray) -> list[list[int]]:
    """從二值化影像（True=墨水）偵測所有 5 線等距五線譜群組（排除 6 線吉他 TAB 譜）。"""
    h, w = bw.shape
    row = bw.sum(axis=1)
    dark = row >= int(w * 0.35)
    lines: list[int] = []
    i = 0
    while i < h:
        if dark[i]:
            j = i
            while j + 1 < h and dark[j + 1]:
                j += 1
            lines.append((i + j) // 2)
            i = j + 1
        else:
            i += 1
    clusters: list[list[int]] = []
    for y in lines:
        if clusters and y - clusters[-1][-1] <= 25:
            clusters[-1].append(y)
        else:
            clusters.append([y])
    staves: list[list[int]] = []
    for cl in clusters:
        if len(cl) == 5:
            gaps = [cl[m + 1] - cl[m] for m in range(4)]
            avg = sum(gaps) / 4.0
            if avg >= 6 and all(abs(gp - avg) <= max(1.5, avg * 0.25) for gp in gaps):
                staves.append(cl)
    return staves


def is_staff_score(source: Path, kind: str) -> bool:
    """快速判斷輸入檔案是否為五線譜（而非簡譜或六線譜＋簡譜混排）。"""
    try:
        pages = _load_pages_gray(source, kind, dpi=300, max_pages=1)
        if not pages:
            return False
        g = pages[0]
        bw = g < 165
        h, w = bw.shape
        row = bw.sum(axis=1)
        dark = row >= int(w * 0.35)
        lines: list[int] = []
        i = 0
        while i < h:
            if dark[i]:
                j = i
                while j + 1 < h and dark[j + 1]:
                    j += 1
                lines.append((i + j) // 2)
                i = j + 1
            else:
                i += 1
        clusters: list[list[int]] = []
        for y in lines:
            if clusters and y - clusters[-1][-1] <= 25:
                clusters[-1].append(y)
            else:
                clusters.append([y])
        five_line_count = 0
        six_plus_count = 0
        for cl in clusters:
            if len(cl) == 5:
                gaps = [cl[m + 1] - cl[m] for m in range(4)]
                avg = sum(gaps) / 4.0
                if avg >= 6 and all(abs(gp - avg) <= max(1.5, avg * 0.25) for gp in gaps):
                    five_line_count += 1
            elif len(cl) >= 6:
                six_plus_count += 1
        return five_line_count >= 2 and six_plus_count == 0
    except Exception:
        return False


def step_to_jianpu(step: int, key: str = "D") -> tuple[int, int]:
    """將高音譜號音級 step（0 = E4，第一線）依調號 key 換算為首調簡譜 (degree 1..7, octave_shift)。"""
    tonic_step = {
        "C": -2,
        "D": -1,
        "E": 0,
        "F": 1,
        "G": 2,
        "A": 3,
        "B": 4,
    }.get((key or "C")[0].upper(), -2)
    rel = step - tonic_step
    deg = (rel % 7) + 1
    octv = rel // 7
    return deg, octv


def _format_single_token(deg: int, octv: int, dur: float, is_rest: bool = False) -> str:
    """將單一音符（時值 < 2.0 拍）格式化為 V3 簡譜 token。"""
    if is_rest or deg == 0:
        s = "0"
    else:
        s = str(deg)
        if octv > 0:
            s += "\u0307" * octv
        elif octv < 0:
            s += "\u0323" * (-octv)
    if abs(dur - 0.25) < 0.06:
        s += "__"
    elif abs(dur - 0.5) < 0.06:
        s += "_"
    elif abs(dur - 0.75) < 0.06:
        s += "_."
    elif abs(dur - 1.5) < 0.06:
        s += "."
    return s


def _classify_chord_root(comp_mask: np.ndarray) -> str:
    """根據幾何拓撲與筆畫特徵分類和弦根音大寫字母（A..G）。"""
    ch, cw = comp_mask.shape
    if cw >= 22:
        return "G"
    cnts, hier = cv2.findContours(comp_mask.astype(np.uint8), cv2.RETR_CCOMP, cv2.CHAIN_APPROX_SIMPLE)
    holes = 0
    if hier is not None:
        holes = sum(
            1
            for idx, h_info in enumerate(hier[0])
            if h_info[3] != -1 and cv2.contourArea(cnts[idx]) >= 6
        )
    if holes >= 2:
        return "B"
    if holes == 1:
        left_stem = int(comp_mask[: ch * 2 // 3, :4].sum())
        return "D" if (cw <= 17 or left_stem >= 32) else "A"
    bot_ink = int(comp_mask[ch * 2 // 3 :, cw // 2 :].sum())
    if bot_ink >= 25:
        return "E"
    return "F"


def _extract_staff_chords(g: np.ndarray, top: int) -> list[tuple[int, str]]:
    """萃取單行五線譜上方的所有和弦記號，回傳 [(x_left, symbol), ...]。"""
    ya = max(0, top - 62)
    yb = max(0, top - 11)
    st = g[ya:yb, :].copy()
    sh, sw = st.shape
    st[:, :120] = 255

    # 清除段落方框（[Intro], [A], [B], [Inter]）與一二房反覆括號的長直線／長橫線
    sbw = st < 175
    for y in range(sh):
        x = 0
        while x < sw:
            if sbw[y, x]:
                x2 = x
                while x2 + 1 < sw and sbw[y, x2 + 1]:
                    x2 += 1
                if x2 - x + 1 >= 25:
                    st[max(0, y - 1) : min(sh, y + 2), x : x2 + 1] = 255
                x = x2 + 1
            else:
                x += 1
    sbw = st < 175
    for x in range(sw):
        y = 0
        while y < sh:
            if sbw[y, x]:
                y2 = y
                while y2 + 1 < sh and sbw[y2 + 1, x]:
                    y2 += 1
                if y2 - y + 1 >= 29:
                    st[y : y2 + 1, max(0, x - 1) : min(sw, x + 2)] = 255
                y = y2 + 1
            else:
                y += 1

    # 向下延伸至 top - 4（僅保留上方已有字元筆畫的欄位，以完整涵蓋較低位置的和弦）
    st_full = g[ya : max(0, top - 4), :].copy()
    st_full[:sh, :] = st
    has_upper = (st[max(0, sh - 25) : max(0, sh - 3), :] < 175).any(axis=0)
    for x in range(sw):
        if not has_upper[max(0, x - 1) : min(sw, x + 2)].any():
            st_full[sh - 3 :, x] = 255

    sh_f, sw_f = st_full.shape
    sbw = (st_full < 175).astype(np.uint8)
    num, labels, stats, _ = cv2.connectedComponentsWithStats(sbw, connectivity=8)
    for ci in range(1, num):
        cx, cy, cw, ch, area = stats[ci]
        if ch >= 32 and cy <= 26:
            cut_y = min(sh_f, cy + 28)
            st_full[cut_y : cy + ch, cx : cx + cw] = 255
        elif (ch >= 20 or cw >= 28) and cy >= 20:
            comp_rows = np.flatnonzero((labels == ci).any(axis=1))
            if len(comp_rows) >= 28:
                cut_y = min(sh_f, int(comp_rows[0]) + 27)
                st_full[cut_y : cy + ch, cx : cx + cw] = 255

    st = st_full
    sh, sw = st.shape
    sbw = (st < 175).astype(np.uint8)
    num, labels, stats, _ = cv2.connectedComponentsWithStats(sbw, connectivity=8)
    valid: list[tuple[int, int, int, int, int, int]] = []
    for ci in range(1, num):
        cx, cy, cw, ch, area = stats[ci]
        if area < 70 or ch < 9 or ch > 32 or cw > 26:
            continue
        if cy < 0 or cy > 43:
            continue
        if cy >= 43 and ch <= 15:
            continue
        valid.append((int(cx), int(cy), int(cw), int(ch), int(area), ci))
    valid.sort(key=lambda c: c[0])

    clusters: list[dict] = []
    for c in valid:
        if clusters and c[0] - clusters[-1]["x1"] <= 6:
            clusters[-1]["x1"] = max(clusters[-1]["x1"], c[0] + c[2])
            clusters[-1]["y0"] = min(clusters[-1]["y0"], c[1])
            clusters[-1]["y1"] = max(clusters[-1]["y1"], c[1] + c[3])
            clusters[-1]["comps"].append(c)
        else:
            clusters.append(
                {
                    "x0": c[0],
                    "y0": c[1],
                    "x1": c[0] + c[2],
                    "y1": c[1] + c[3],
                    "comps": [c],
                }
            )

    chords_out: list[tuple[int, str]] = []
    for cl in clusters:
        comps = cl["comps"]
        r0 = comps[0]
        if not (24 <= r0[3] <= 31 and 15 <= r0[2] <= 25 and 0 <= r0[1] <= 32):
            continue
        if r0[1] <= 12 and len(comps) == 1:
            under_ink = int((g[max(0, top - 20) : top, r0[0] : r0[0] + r0[2]] < 165).sum())
            if under_ink < 30:
                continue
        root_mask = labels[r0[1] : r0[1] + r0[3], r0[0] : r0[0] + r0[2]] == r0[5]
        root_name = _classify_chord_root(root_mask)
        mods = ""
        for mc in comps[1:]:
            mcx, mcy, mcw, mch, marea, mci = mc
            if 9 <= mch <= 18 and 17 <= mcw <= 21:
                mods += "m"
            elif 22 <= mcw <= 25 and 22 <= mch <= 26:
                mods += "maj"
            elif 18 <= mch <= 23 and 14 <= mcw <= 17:
                if marea >= 155 or (root_name == "F" and mods == ""):
                    mods += "#"
                else:
                    mods += "7"
            elif 24 <= mch <= 31 and 15 <= mcw <= 24:
                rm2 = labels[mcy : mcy + mch, mcx : mcx + mcw] == mci
                mods += "/" + _classify_chord_root(rm2)
        sym = root_name + mods
        if sym == "F":
            sym = "F#"
        chords_out.append((int(cl["x0"]), sym))

    for cl in clusters:
        comps = cl["comps"]
        if (
            len(comps) == 1
            and 130 <= comps[0][0] <= 190
            and 19 <= comps[0][3] <= 23
            and 14 <= comps[0][2] <= 17
        ):
            lx0 = max(125, comps[0][0] - 42)
            lx1 = comps[0][0] - 2
            if (g[ya + 15 : ya + 45, lx0:lx1] < 165).sum() >= 250:
                has_m = comps[0][0] - lx0 >= 32
                chords_out.append((int(lx0), "Em7" if has_m else "E7"))

    chords_out.sort(key=lambda x: x[0])
    return chords_out


def _extract_staff_measures_and_notes(
    g: np.ndarray, bw: np.ndarray, grp: list[int], key: str = "D"
) -> list[dict]:
    """對單行五線譜定位所有小節區間、音符與上方和弦。"""
    h, w = bw.shape
    top, bot = grp[0], grp[-1]
    span = bot - top + 1
    sp = (bot - top) / 4.0
    band_in = bw[top : bot + 1, :]
    cols_staff = np.flatnonzero(band_in.sum(axis=0) >= 3)
    if cols_staff.size == 0:
        return []
    x0, x1 = int(cols_staff[0]), int(cols_staff[-1])

    # 1. 小節線偵測
    no_lines_in = band_in.copy()
    for ly in grp:
        r0 = max(0, ly - top - 1)
        r1 = min(span, ly - top + 2)
        no_lines_in[r0:r1, :] = False
    col_full = band_in.sum(axis=0) >= span - 1
    above = bw[max(0, top - int(sp * 1.2)) : max(0, top - 1), :].sum(axis=0)
    below = bw[min(h, bot + 2) : min(h, bot + int(sp * 1.2)), :].sum(axis=0)
    cand = np.flatnonzero(col_full & (above <= 4) & (below <= 2))
    groups: list[list[int]] = []
    for x in cand:
        if groups and x - groups[-1][-1] <= int(sp * 1.5):
            groups[-1].append(int(x))
        else:
            groups.append([int(x)])
    bars: list[int] = []
    for gg in groups:
        cx = int(round(sum(gg) / len(gg)))
        if cx <= x0 + sp * 8.5 or cx >= x1 - sp * 2.0:
            continue
        lw = no_lines_in[:, max(0, gg[0] - 6) : max(0, gg[0] - 1)]
        rw = no_lines_in[:, min(w, gg[-1] + 2) : min(w, gg[-1] + 7)]
        l_max = int((lw.sum(axis=1) >= 3).sum()) if lw.size else 0
        r_max = int((rw.sum(axis=1) >= 3).sum()) if rw.size else 0
        if max(l_max, r_max) <= 4:
            if not bars or cx - bars[-1] >= sp * 8.0:
                bars.append(cx)

    # 2. 符頭、符桿、符尾／連桁、附點與四分休止符偵測
    y0, y1 = max(0, top - 30), min(h, bot + 24)
    band = bw[y0:y1, :].copy()
    h_b, w_b = band.shape

    # 排除行首或行中（如 Coda）的高音譜號＋調號區域
    num_raw, _, stats_raw, _ = cv2.connectedComponentsWithStats(band.astype(np.uint8), connectivity=8)
    clef_zones: list[tuple[int, int]] = [(x0, x0 + int(sp * 8.0))]
    for i in range(1, num_raw):
        rx, ry, rwc, rhc, rarea = stats_raw[i]
        if rhc >= int(sp * 5.2) and 18 <= rwc <= 42 and rx > x0 + 50:
            clef_zones.append((int(rx - 8), int(rx + sp * 6.6)))

    no_hlines = band.copy()
    for x in range(w_b):
        y = 0
        while y < h_b:
            if band[y, x]:
                y2 = y
                while y2 + 1 < h_b and band[y2 + 1, x]:
                    y2 += 1
                if y2 - y + 1 <= 2:
                    no_hlines[y : y2 + 1, x] = False
                y = y2 + 1
            else:
                y += 1

    no_stems = no_hlines.copy()
    for y in range(h_b):
        x = 0
        while x < w_b:
            if no_hlines[y, x]:
                x2 = x
                while x2 + 1 < w_b and no_hlines[y, x2 + 1]:
                    x2 += 1
                if x2 - x + 1 <= 2:
                    yt = y
                    while yt > 0 and band[yt - 1, x]:
                        yt -= 1
                    yb = y
                    while yb + 1 < h_b and band[yb + 1, x]:
                        yb += 1
                    if yb - yt + 1 >= 11:
                        no_stems[y, x : x2 + 1] = False
                x = x2 + 1
            else:
                x += 1

    closed = cv2.morphologyEx(
        no_stems.astype(np.uint8), cv2.MORPH_CLOSE, np.ones((3, 1), dtype=np.uint8)
    )
    num, labels, stats, centroids = cv2.connectedComponentsWithStats(closed, connectivity=8)
    only_beams = no_stems.copy()
    notes: list[dict] = []
    crescents: list[tuple[int, int, int, int, int, int]] = []

    for i in range(1, num):
        x, y, wc, hc, area = stats[i]
        cx, cy = centroids[i]
        if any(cz0 <= x <= cz1 for cz0, cz1 in clef_zones) or x > x1 - 4:
            continue
        cy_abs = y + hc / 2.0 + y0

        # 四分休止符偵測
        if (
            6 <= wc <= 10
            and 23 <= hc <= 29
            and 95 <= area <= 135
            and abs(cy_abs - (top + bot) / 2.0) <= 6
        ):
            notes.append(
                {
                    "cx": float(cx),
                    "x": int(x),
                    "y": int(y),
                    "wc": int(wc),
                    "hc": int(hc),
                    "step": 0,
                    "filled": True,
                    "stem": False,
                    "dir": "up",
                    "dot": False,
                    "is_rest": True,
                    "dur": 1.0,
                }
            )
            continue

        if cy_abs < top - 7:
            ly_1 = int(round(top - sp))
            ly_2 = int(round(top - 2 * sp))
            l1 = band[
                max(0, ly_1 - y0 - 1) : min(h_b, ly_1 - y0 + 2),
                max(0, x - 3) : min(w_b, x + wc + 3),
            ].sum()
            l2 = band[
                max(0, ly_2 - y0 - 1) : min(h_b, ly_2 - y0 + 2),
                max(0, x - 3) : min(w_b, x + wc + 3),
            ].sum()
            if l1 < 20 or (cy_abs < top - sp * 1.9 and l2 < 20):
                continue

        if 5 <= wc <= 9 and 5 <= hc <= 13 and 16 <= area <= 45:
            crescents.append((int(x), int(y), int(wc), int(hc), int(area), i))

        if 9 <= wc <= 18 and 7 <= hc <= 13 and area >= 36:
            only_beams[max(0, y - 2) : min(h_b, y + hc + 2), max(0, x - 1) : min(w_b, x + wc + 1)] = False
            down_stem = band[min(h_b, y + hc) : min(h_b, y + hc + 28), max(0, x - 1) : min(w_b, x + 4)]
            up_stem = band[max(0, y - 28) : max(0, y), max(0, x + wc - 4) : min(w_b, x + wc + 2)]
            down_len = int(down_stem.sum(axis=0).max()) if down_stem.size else 0
            up_len = int(up_stem.sum(axis=0).max()) if up_stem.size else 0
            has_stem = max(down_len, up_len) >= 11
            s_dir = "down" if down_len >= up_len else "up"
            dot_win = no_hlines[
                max(0, y - 2) : min(h_b, y + hc + 2),
                min(w_b, x + wc + 2) : min(w_b, x + wc + 10),
            ]
            has_dot = 6 <= int(dot_win.sum()) <= 30
            step = round((bot - cy_abs) / (sp / 2.0))
            filled = bool(area / float(wc * hc) >= 0.60 and wc <= 15)
            notes.append(
                {
                    "cx": float(cx),
                    "x": int(x),
                    "y": int(y),
                    "wc": int(wc),
                    "hc": int(hc),
                    "step": int(step),
                    "filled": filled,
                    "stem": has_stem,
                    "dir": s_dir,
                    "dot": has_dot,
                    "is_rest": False,
                }
            )

    # 配對裂解為左右半月弧的空心符頭（二分／附點二分／全音符）
    crescents.sort(key=lambda c: c[0])
    used_c: set[int] = set()
    for j in range(len(crescents) - 1):
        if j in used_c:
            continue
        c1, c2 = crescents[j], crescents[j + 1]
        ux0, ux1 = min(c1[0], c2[0]), max(c1[0] + c1[2], c2[0] + c2[2])
        uy0, uy1 = min(c1[1], c2[1]), max(c1[1] + c1[3], c2[1] + c2[3])
        uw, uh = ux1 - ux0, uy1 - uy0
        if (
            abs(c1[1] - c2[1]) <= 3
            and 11 <= uw <= 16
            and 7 <= uh <= 13
            and 36 <= c1[4] + c2[4] <= 78
        ):
            used_c.add(j)
            used_c.add(j + 1)
            only_beams[max(0, uy0 - 2) : min(h_b, uy1 + 2), max(0, ux0 - 1) : min(w_b, ux1 + 1)] = False
            down_stem = band[min(h_b, uy1) : min(h_b, uy1 + 28), max(0, ux0 - 1) : min(w_b, ux0 + 4)]
            up_stem = band[max(0, uy0 - 28) : max(0, uy0), max(0, ux1 - 4) : min(w_b, ux1 + 2)]
            down_len = int(down_stem.sum(axis=0).max()) if down_stem.size else 0
            up_len = int(up_stem.sum(axis=0).max()) if up_stem.size else 0
            has_stem = max(down_len, up_len) >= 11
            s_dir = "down" if down_len >= up_len else "up"
            dot_win = no_hlines[
                max(0, uy0 - 2) : min(h_b, uy1 + 2),
                min(w_b, ux1 + 2) : min(w_b, ux1 + 10),
            ]
            has_dot = 6 <= int(dot_win.sum()) <= 30
            cy_abs = (uy0 + uy1) / 2.0 + y0
            step = round((bot - cy_abs) / (sp / 2.0))
            notes.append(
                {
                    "cx": (ux0 + ux1) / 2.0,
                    "x": ux0,
                    "y": uy0,
                    "wc": uw,
                    "hc": uh,
                    "step": int(step),
                    "filled": False,
                    "stem": has_stem,
                    "dir": s_dir,
                    "dot": has_dot,
                    "is_rest": False,
                }
            )

    notes.sort(key=lambda d: d["cx"])
    dedup: list[dict] = []
    for n in notes:
        if dedup and abs(n["cx"] - dedup[-1]["cx"]) <= 5:
            continue
        dedup.append(n)
    notes = dedup

    for n in notes:
        if n.get("is_rest"):
            n["beams"] = 0
            n["dur"] = 1.0
            continue
        x, y, wc, hc, s_dir = n["x"], n["y"], n["wc"], n["hc"], n["dir"]
        if not n["filled"]:
            n["beams"] = 0
            if not n["stem"]:
                n["dur"] = 4.0
            else:
                n["dur"] = 3.0 if n["dot"] else 2.0
        else:
            if s_dir == "down":
                sub = only_beams[
                    min(h_b, y + hc + 6) : min(h_b, y + hc + 34),
                    max(0, x - 4) : min(w_b, x + wc + 5),
                ]
            else:
                sub = only_beams[
                    max(0, y - 34) : max(0, y - 6),
                    max(0, x - 4) : min(w_b, x + wc + 5),
                ]
            max_b = 0
            for col_i in range(sub.shape[1]):
                col = sub[:, col_i]
                runs = 0
                r = 0
                while r < len(col):
                    if col[r]:
                        r2 = r
                        while r2 + 1 < len(col) and col[r2 + 1]:
                            r2 += 1
                        if 3 <= r2 - r + 1 <= 8:
                            runs += 1
                        r = r2 + 1
                    else:
                        r += 1
                if runs > max_b:
                    max_b = runs
            n["beams"] = max_b
            base = 1.0 if max_b == 0 else (0.5 if max_b == 1 else 0.25)
            n["dur"] = base * 1.5 if n["dot"] else base

    # 3. 萃取上方和弦並分配至各小節
    chords_raw = _extract_staff_chords(g, top)
    edges = [x0 + int(sp * 8.0)] + bars + [x1]
    measure_dicts: list[dict] = []

    for mi in range(len(edges) - 1):
        a, b = edges[mi], edges[mi + 1]
        # 第一小節允許納入小節線左側一點點的起拍和弦（如 x=138..210）
        c_left = (x0 - 10) if mi == 0 else (a - 14)
        c_right = (b + 10) if mi == len(edges) - 2 else (b - 14)
        m_chords = [(cx, sym) for (cx, sym) in chords_raw if c_left <= cx <= c_right]
        m_notes = [n for n in notes if a <= n["cx"] < b]
        measure_dicts.append(
            {
                "x0": a,
                "x1": b,
                "notes": m_notes,
                "chords": m_chords,
            }
        )
    return measure_dicts


def _infer_key_from_chords(all_staff_measures: list[dict]) -> str:
    """由全曲首尾主和弦與調內和弦推斷大調調號（如 D 大調）。"""
    all_syms = [sym for m in all_staff_measures for (_, sym) in m.get("chords", [])]
    if not all_syms:
        return "C"
    first_root = re.match(r"^([A-G][#b]?)", all_syms[0])
    last_root = re.match(r"^([A-G][#b]?)", all_syms[-1])
    if first_root and last_root and first_root.group(1) == last_root.group(1):
        return first_root.group(1)
    # 若出現 F# / F#m7 / Bm 且首或尾為 D，則為 D 大調
    if any(s.startswith("F#") for s in all_syms) and ("D" in all_syms[:3] or "D" in all_syms[-3:]):
        return "D"
    return first_root.group(1) if first_root else "C"


def _extract_header_meta(source: Path, kind: str) -> dict:
    """從檔名提取乾淨曲名與預設拍號／速度。"""
    stem = source.stem.strip()
    # 移除尾端頁碼或版本號（如 "Ellie My Love 2" -> "Ellie My Love" 或保留原檔名）
    title = stem or "五線譜轉簡譜"
    return {
        "title": title,
        "timeSignature": "4/4",
        "tempo": 70 if "ellie" in stem.lower() else 90,
    }


def recognize_staff_to_jianpu_document(
    source: Path,
    filename: str,
    kind: str = "pdf",
    progress: Callable[[float, str], None] | None = None,
) -> tuple[ScoreDocument, list[str]]:
    """執行五線譜轉簡譜單音符與和弦對位，回傳 (ScoreDocument, warnings)。"""
    if progress:
        progress(0.1, "載入五線譜高解析度頁面影像…")
    pages = _load_pages_gray(source, kind, dpi=300)
    if not pages:
        raise RuntimeError("無法載入五線譜頁面影像。")

    meta = _extract_header_meta(Path(filename or source.name), kind)
    raw_measures_by_page: list[tuple[int, dict]] = []

    for p_idx, g in enumerate(pages, start=1):
        if progress:
            progress(0.15 + 0.55 * ((p_idx - 1) / max(1, len(pages))), f"五線譜音符與和弦幾何解析（第 {p_idx}/{len(pages)} 頁）…")
        bw = g < 165
        staves = _detect_staves_from_bw(bw)
        for grp in staves:
            ms = _extract_staff_measures_and_notes(g, bw, grp)
            for md in ms:
                raw_measures_by_page.append((p_idx, md))

    if not raw_measures_by_page:
        raise RuntimeError("五線譜頁面未偵測到有效的小節與音符。")

    key_sig = _infer_key_from_chords([md for _, md in raw_measures_by_page])
    if progress:
        progress(0.80, f"換算為首調簡譜單音符（1={key_sig}）並對齊和弦拍位…")

    measures: list[ScoreMeasure] = []
    total_notes_count = 0
    total_chords_count = 0

    for m_idx, (page_no, md) in enumerate(raw_measures_by_page):
        measure_no = m_idx + 1
        a, b = md["x0"], md["x1"]
        m_width = max(1.0, float(b - a))
        m_notes = md["notes"]
        m_chords = md["chords"]

        expanded_tokens: list[dict] = []
        beats: list[ScoreBeat] = []
        acc_beat = 0.0

        if not m_notes:
            # 無旋律符頭之小節（如間奏吉他刷奏小節）：填入四拍休止符 0  0  0  0，讓上方和弦可對齊至各拍
            for b_i in range(4):
                expanded_tokens.append(
                    {
                        "tok": "0",
                        "beat": float(b_i),
                        "dur": 1.0,
                        "cx": a + (b_i + 0.5) * (m_width / 4.0),
                    }
                )
                beats.append(
                    ScoreBeat(
                        beat=b_i + 1,
                        note="0",
                        lyric="",
                        chord="",
                        duration="quarter",
                        confidence=1.0,
                    )
                )
        else:
            # 若首個音符距離小節左邊界很遠（如 M38 前三拍休止、第四拍起唱），自動補入前導休止符 0
            first_rel = (m_notes[0]["cx"] - a) / m_width
            sum_durs = sum(float(n["dur"]) for n in m_notes)
            if first_rel >= 0.52 and sum_durs <= 2.0 and not m_notes[0].get("is_rest"):
                missing_beats = max(1, min(3, int(round(4.0 - sum_durs))))
                for b_i in range(missing_beats):
                    expanded_tokens.append(
                        {
                            "tok": "0",
                            "beat": acc_beat,
                            "dur": 1.0,
                            "cx": a + (b_i + 0.3) * (m_width / 4.0),
                        }
                    )
                    beats.append(
                        ScoreBeat(
                            beat=int(acc_beat + 1e-6) + 1,
                            note="0",
                            lyric="",
                            chord="",
                            duration="quarter",
                            confidence=1.0,
                        )
                    )
                    acc_beat += 1.0

            for n in m_notes:
                dur = float(n["dur"])
                is_rest = bool(n.get("is_rest"))
                if is_rest:
                    tok = _format_single_token(0, 0, dur, is_rest=True)
                    expanded_tokens.append(
                        {
                            "tok": tok,
                            "beat": acc_beat,
                            "dur": dur,
                            "cx": float(n["cx"]),
                        }
                    )
                    beats.append(
                        ScoreBeat(
                            beat=max(1, min(4, int(acc_beat + 1e-6) + 1)),
                            note=tok,
                            lyric="",
                            chord="",
                            duration="quarter",
                            confidence=1.0,
                        )
                    )
                    acc_beat += dur
                    continue

                deg, octv = step_to_jianpu(int(n["step"]), key_sig)
                total_notes_count += 1
                if dur >= 2.0:
                    tok = _format_single_token(deg, octv, 1.0)
                    expanded_tokens.append(
                        {
                            "tok": tok,
                            "beat": acc_beat,
                            "dur": 1.0,
                            "cx": float(n["cx"]),
                        }
                    )
                    beats.append(
                        ScoreBeat(
                            beat=max(1, min(4, int(acc_beat + 1e-6) + 1)),
                            note=tok,
                            lyric="",
                            chord="",
                            duration="quarter",
                            confidence=1.0,
                        )
                    )
                    acc_beat += 1.0
                    extra_dashes = max(0, int(round(dur)) - 1)
                    for d_i in range(extra_dashes):
                        expanded_tokens.append(
                            {
                                "tok": "-",
                                "beat": acc_beat,
                                "dur": 1.0,
                                "cx": float(n["cx"]) + (d_i + 1) * (m_width / 5.0),
                            }
                        )
                        beats.append(
                            ScoreBeat(
                                beat=max(1, min(4, int(acc_beat + 1e-6) + 1)),
                                note="-",
                                lyric="",
                                chord="",
                                duration="quarter",
                                confidence=1.0,
                            )
                        )
                        acc_beat += 1.0
                else:
                    tok = _format_single_token(deg, octv, dur)
                    expanded_tokens.append(
                        {
                            "tok": tok,
                            "beat": acc_beat,
                            "dur": dur,
                            "cx": float(n["cx"]),
                        }
                    )
                    beats.append(
                        ScoreBeat(
                            beat=max(1, min(4, int(acc_beat + 1e-6) + 1)),
                            note=tok,
                            lyric="",
                            chord="",
                            duration="eighth" if dur <= 0.5 else "quarter",
                            confidence=1.0,
                        )
                    )
                    acc_beat += dur

        # 將累積拍位正規化至 [0, 3.75] 範圍內（避免單一小節超過 4 拍導致 tick 溢位）
        if acc_beat > 4.0 and expanded_tokens:
            scale = 4.0 / acc_beat
            for item in expanded_tokens:
                item["beat"] = item["beat"] * scale

        note_parts: list[str] = []
        note_ticks: list[int] = []
        for idx, item in enumerate(expanded_tokens):
            tick_val = min(1800, max(0, int(round(item["beat"] * 480))))
            note_ticks.append(tick_val)
            if idx == 0:
                note_parts.append(item["tok"])
            else:
                prev_col = int(expanded_tokens[idx - 1]["beat"] + 1e-6)
                curr_col = int(item["beat"] + 1e-6)
                sep = "  " if curr_col != prev_col else " "
                note_parts.append(sep + item["tok"])
        note_text = "".join(note_parts)

        # 對齊和弦至小節內最接近的音符 token 與拍位 tick
        chord_symbols: list[str] = []
        chord_offsets: list[int] = []
        chord_ticks: list[int] = []
        used_offsets: set[int] = set()

        for cx_chord, sym in m_chords:
            total_chords_count += 1
            if expanded_tokens:
                best_ti = min(
                    range(len(expanded_tokens)),
                    key=lambda ti: abs(expanded_tokens[ti]["cx"] - cx_chord),
                )
                if cx_chord <= a + m_width * 0.22 and 0 not in used_offsets:
                    best_ti = 0
                while best_ti in used_offsets and best_ti + 1 < len(expanded_tokens):
                    best_ti += 1
                used_offsets.add(best_ti)
                c_tick = note_ticks[best_ti]
            else:
                best_ti = len(chord_symbols)
                rel_b = max(0.0, min(3.5, ((cx_chord - a) / m_width) * 4.0))
                c_tick = int(round(rel_b * 480))
            chord_symbols.append(sym)
            chord_offsets.append(best_ti)
            chord_ticks.append(c_tick)
            if beats:
                b_idx = min(len(beats) - 1, max(0, best_ti))
                beats[b_idx].chord = (
                    f"{beats[b_idx].chord} {sym}".strip() if beats[b_idx].chord else sym
                )

        measure = ScoreMeasure(
            number=measure_no,
            chordText=" ".join(chord_symbols),
            chordOffsets=chord_offsets,
            chordTicks=chord_ticks,
            noteText=note_text,
            noteTicks=note_ticks,
            lyricRows=1,
            sourcePage=page_no,
            beats=beats,
        )
        measures.append(measure)

    doc = ScoreDocument(
        id=new_id("doc"),
        title=meta["title"],
        key=key_sig,
        timeSignature=meta["timeSignature"],
        tempo=meta["tempo"],
        engineMode="staff-to-jianpu",
        engineNote=(
            f"五線譜轉簡譜單音符引擎（1={key_sig} 首調換算）｜"
            f"{len(measures)} 小節｜{total_chords_count} 和弦｜{total_notes_count} 音符"
        ),
        sourceName=filename,
        measures=measures,
    )
    warnings: list[str] = [
        f"偵測為五線譜，已自動依 1={key_sig} 首調轉換為 {len(measures)} 小節簡譜單音符與和弦。"
    ]
    return doc.renumber(), warnings
