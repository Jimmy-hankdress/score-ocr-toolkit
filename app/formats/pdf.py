# -*- coding: utf-8 -*-
"""
app/formats/pdf.py

將 ScoreDocument 匯出為與 Score Studio 視覺一致的列印級 A4 向量 PDF 檔案（bytes）。
採用 PyMuPDF (pymupdf) 原生向量繪圖與系統繁體中文字型（微軟正黑體 msjh.ttc / msjhbd.ttc）內嵌，
無須依賴外部瀏覽器子行程，毫秒級生成且 100% 杜絕中文亂碼（???）與折行問題。
"""

from __future__ import annotations
import os
import re
from typing import Any, Dict, List, Optional, Tuple

try:
    import pymupdf
except ImportError:
    try:
        import fitz as pymupdf  # type: ignore[no-redef]
    except ImportError:
        pymupdf = None  # type: ignore[assignment]


SECTION_LABELS = {
    "intro": "前奏",
    "verse": "主歌",
    "prechorus": "導歌",
    "chorus": "副歌",
    "bridge": "橋段",
    "interlude": "間奏",
    "solo": "間奏/Solo",
    "outro": "尾奏",
    "coda": "尾聲",
}


def _find_cjk_font_paths() -> Tuple[Optional[str], Optional[str]]:
    """尋找 Windows / 系統繁體中文字型（一般與粗體）。"""
    reg_candidates = [
        r"C:\Windows\Fonts\msjh.ttc",
        r"C:\Windows\Fonts\msjh.ttf",
        r"C:\Windows\Fonts\mingliu.ttc",
        r"C:\Windows\Fonts\kaiu.ttf",
        r"C:\Windows\Fonts\simsun.ttc",
    ]
    bold_candidates = [
        r"C:\Windows\Fonts\msjhbd.ttc",
        r"C:\Windows\Fonts\msjhbd.ttf",
        r"C:\Windows\Fonts\msjh.ttc",
    ]
    reg_path = next((p for p in reg_candidates if os.path.isfile(p)), None)
    bold_path = next((p for p in bold_candidates if os.path.isfile(p)), reg_path)
    return reg_path, bold_path


def _extract_measure_texts(m: Dict[str, Any]) -> Tuple[str, str, List[str]]:
    chord_text = str(m.get("chordText") or "").strip()
    if not chord_text and isinstance(m.get("chords"), list):
        ch_list = []
        for c in m.get("chords", []):
            if isinstance(c, dict):
                sym = str(c.get("symbol") or c.get("chord") or c.get("text") or "").strip()
                if sym:
                    ch_list.append(sym)
            elif isinstance(c, str) and c.strip():
                ch_list.append(c.strip())
        chord_text = "  ".join(ch_list)

    note_text = str(m.get("noteText") or "").rstrip()
    if not note_text and isinstance(m.get("notes"), list):
        n_list = []
        for n in m.get("notes", []):
            if isinstance(n, dict):
                tok = str(n.get("token") or n.get("pitch") or n.get("text") or "").strip()
                if tok:
                    n_list.append(tok)
            elif isinstance(n, str) and n.strip():
                n_list.append(n.strip())
        note_text = " ".join(n_list)

    lyric_lines: List[str] = []
    if isinstance(m.get("lyricLines"), list) and m["lyricLines"]:
        lyric_lines = [str(line or "").rstrip() for line in m["lyricLines"]]
    else:
        lt = str(m.get("lyricText") or "").rstrip()
        if not lt and isinstance(m.get("lyrics"), list):
            l_list = []
            for l_item in m.get("lyrics", []):
                if isinstance(l_item, dict):
                    txt = str(l_item.get("text") or "").strip()
                    if txt:
                        l_list.append(txt)
                elif isinstance(l_item, str):
                    l_list.append(l_item)
            lt = "".join(l_list)
        if lt:
            lyric_lines = [lt]

    return chord_text, note_text, lyric_lines


def _visual_width_units(text: str) -> float:
    s = re.sub(r"[\u0307\u0323]", "", text or "")
    w = 0.0
    for ch in s:
        code = ord(ch)
        if code == 32:
            w += 0.55
        elif code > 255:
            w += 1.95
        else:
            w += 0.9
    return w


class _ParsedNoteToken:
    def __init__(
        self,
        is_space: bool = False,
        space_len: int = 1,
        acc: str = "",
        digit: str = "",
        up_dots: int = 0,
        down_dots: int = 0,
        uline: int = 0,
        aug_dot: bool = False,
        has_tie: bool = False,
        has_slur: bool = False,
        is_triplet: bool = False,
    ):
        self.is_space = is_space
        self.space_len = space_len
        self.acc = acc
        self.digit = digit
        self.up_dots = up_dots
        self.down_dots = down_dots
        self.uline = uline
        self.aug_dot = aug_dot
        self.has_tie = has_tie
        self.has_slur = has_slur
        self.is_triplet = is_triplet


def _parse_jianpu_tokens(note_text: str) -> List[_ParsedNoteToken]:
    s = re.sub(r" {3,}", "  ", (note_text or "").strip())
    if not s:
        s = "0  -  -  -"

    raw_parts = re.split(r"(\s+)", s)
    result: List[_ParsedNoteToken] = []
    for part in raw_parts:
        if not part:
            continue
        if part.isspace():
            result.append(_ParsedNoteToken(is_space=True, space_len=len(part)))
            continue

        t = part
        is_triplet = "(3)" in t
        t = t.replace("(3)", "")
        has_tie = "^" in t
        has_slur = "~" in t
        t = t.replace("^", "").replace("~", "")

        eq_count = t.count("=")
        us_count = t.count("_")
        uline = 2 if (eq_count > 0 or us_count >= 2) else (1 if us_count == 1 else 0)
        t = t.replace("_", "").replace("=", "")

        up_dots = min(2, t.count("'"))
        down_dots = min(2, t.count(","))
        aug_dot = "." in t
        t = t.replace("'", "").replace(",", "").replace(".", "")

        m = re.match(r"^([#b♯♭]?)([0-7\-xX])(.*)$", t)
        if m:
            acc = m.group(1).replace("♯", "#").replace("♭", "b")
            digit = m.group(2) + m.group(3)
        else:
            acc = ""
            digit = t or "0"

        result.append(
            _ParsedNoteToken(
                is_space=False,
                acc=acc,
                digit=digit,
                up_dots=up_dots,
                down_dots=down_dots,
                uline=uline,
                aug_dot=aug_dot,
                has_tie=has_tie,
                has_slur=has_slur,
                is_triplet=is_triplet,
            )
        )
    return result


def _measure_tokens_width(tokens: List[_ParsedNoteToken], font_bold: pymupdf.Font, fontsize: float) -> float:
    total = 0.0
    space_w = font_bold.text_length(" ", fontsize=fontsize) * 1.15
    for tk in tokens:
        if tk.is_space:
            total += space_w * tk.space_len
        else:
            if tk.acc:
                total += font_bold.text_length(tk.acc, fontsize=fontsize * 0.75) + 0.8
            total += font_bold.text_length(tk.digit, fontsize=fontsize) + 1.2
            if tk.aug_dot:
                total += 3.5
            if tk.is_triplet:
                total += 4.0
    return total


def _draw_jianpu_tokens(
    page: pymupdf.Page,
    tokens: List[_ParsedNoteToken],
    x_start: float,
    y_baseline: float,
    fontsize: float,
    font_bold: pymupdf.Font,
    fontname_bold: str,
    color_ink: Tuple[float, float, float] = (0.07, 0.09, 0.15),
):
    cur_x = x_start
    space_w = font_bold.text_length(" ", fontsize=fontsize) * 1.15
    note_centers: List[Tuple[float, _ParsedNoteToken]] = []

    for tk in tokens:
        if tk.is_space:
            cur_x += space_w * tk.space_len
            continue

        # 1. 升降記號 (# / b)
        if tk.acc:
            acc_fs = fontsize * 0.75
            acc_w = font_bold.text_length(tk.acc, fontsize=acc_fs)
            page.insert_text(
                pymupdf.Point(cur_x, y_baseline - fontsize * 0.25),
                tk.acc,
                fontname=fontname_bold,
                fontsize=acc_fs,
                color=color_ink,
            )
            cur_x += acc_w + 0.8

        # 2. 主音符數字
        digit_w = font_bold.text_length(tk.digit, fontsize=fontsize)
        digit_cx = cur_x + digit_w / 2.0
        page.insert_text(
            pymupdf.Point(cur_x, y_baseline),
            tk.digit,
            fontname=fontname_bold,
            fontsize=fontsize,
            color=color_ink,
        )

        # 3. 高八度點（在數字正上方垂直疊加，不受附點影響）
        if tk.up_dots > 0:
            base_top_y = y_baseline - fontsize * 1.05
            for d_i in range(tk.up_dots):
                dot_y = base_top_y - d_i * 3.6
                page.draw_circle(
                    pymupdf.Point(digit_cx, dot_y),
                    1.15,
                    color=color_ink,
                    fill=color_ink,
                )

        # 4. 減時線底線（單底線 _ / 雙底線 =）
        bottom_beam_y = y_baseline + 2.4
        if tk.uline >= 1:
            page.draw_line(
                pymupdf.Point(cur_x - 0.5, bottom_beam_y),
                pymupdf.Point(cur_x + digit_w + 0.5, bottom_beam_y),
                color=color_ink,
                width=1.0,
            )
        if tk.uline >= 2:
            bottom_beam_y2 = y_baseline + 4.4
            page.draw_line(
                pymupdf.Point(cur_x - 0.5, bottom_beam_y2),
                pymupdf.Point(cur_x + digit_w + 0.5, bottom_beam_y2),
                color=color_ink,
                width=1.0,
            )
            bottom_beam_y = bottom_beam_y2

        # 5. 低八度點（在數字正下方垂直排列）
        if tk.down_dots > 0:
            base_bot_y = (bottom_beam_y + 2.8) if tk.uline > 0 else (y_baseline + 3.8)
            for d_i in range(tk.down_dots):
                dot_y = base_bot_y + d_i * 3.6
                page.draw_circle(
                    pymupdf.Point(digit_cx, dot_y),
                    1.15,
                    color=color_ink,
                    fill=color_ink,
                )

        note_centers.append((digit_cx, tk))
        cur_x += digit_w + 1.2

        # 6. 附點 (.)
        if tk.aug_dot:
            page.draw_circle(
                pymupdf.Point(cur_x + 1.2, y_baseline - fontsize * 0.28),
                1.15,
                color=color_ink,
                fill=color_ink,
            )
            cur_x += 3.5

        # 7. 三連音記號
        if tk.is_triplet:
            page.insert_text(
                pymupdf.Point(cur_x, y_baseline - fontsize * 0.45),
                "3",
                fontname=fontname_bold,
                fontsize=fontsize * 0.62,
                color=color_ink,
            )
            cur_x += 4.0

    # 8. 繪製連音線（數字正上方弧線）與圓滑線（數字正下方弧線）
    for idx, (cx, tk) in enumerate(note_centers):
        next_cx = note_centers[idx + 1][0] if idx + 1 < len(note_centers) else (cx + fontsize * 1.1)
        if tk.has_tie:
            y_arc = y_baseline - fontsize * 1.12 - (3.8 if tk.up_dots > 0 else 0.0)
            p1 = pymupdf.Point(cx, y_arc)
            p4 = pymupdf.Point(next_cx, y_arc)
            c1 = pymupdf.Point(cx + (next_cx - cx) * 0.25, y_arc - 4.5)
            c2 = pymupdf.Point(cx + (next_cx - cx) * 0.75, y_arc - 4.5)
            page.draw_bezier(p1, c1, c2, p4, color=color_ink, width=0.9)
        if tk.has_slur:
            y_arc = y_baseline + 5.0 + (3.8 if tk.down_dots > 0 else 0.0)
            p1 = pymupdf.Point(cx, y_arc)
            p4 = pymupdf.Point(next_cx, y_arc)
            c1 = pymupdf.Point(cx + (next_cx - cx) * 0.25, y_arc + 4.5)
            c2 = pymupdf.Point(cx + (next_cx - cx) * 0.75, y_arc + 4.5)
            page.draw_bezier(p1, c1, c2, p4, color=color_ink, width=0.9)


def export_score_to_pdf(doc_data: Dict[str, Any]) -> bytes:
    """接收 ScoreDocument dict，使用 PyMuPDF 直接繪製高解析度繁體中文簡譜 PDF（bytes）。"""
    reg_path, bold_path = _find_cjk_font_paths()
    font_reg = pymupdf.Font(fontfile=reg_path) if reg_path else pymupdf.Font("helv")
    font_bold = pymupdf.Font(fontfile=bold_path) if bold_path else font_reg

    pdf_doc = pymupdf.open()
    page_w, page_h = 595.28, 841.89  # A4 portrait (pt)
    margin_x = 28.0
    margin_top = 34.0
    margin_bottom = 34.0
    usable_w = page_w - margin_x * 2

    def new_page_with_fonts() -> pymupdf.Page:
        p = pdf_doc.new_page(width=page_w, height=page_h)
        if reg_path:
            p.insert_font(fontname="FReg", fontfile=reg_path)
        if bold_path:
            p.insert_font(fontname="FBold", fontfile=bold_path)
        return p

    fn_reg = "FReg" if reg_path else "helv"
    fn_bold = "FBold" if bold_path else fn_reg

    page = new_page_with_fonts()
    cur_y = margin_top

    title = str(doc_data.get("title") or "未命名樂譜").strip()
    subtitle = str(doc_data.get("subtitle") or "").strip()
    key_sig = str(doc_data.get("key") or "C").strip()
    time_sig = str(doc_data.get("timeSignature") or "4/4").strip()
    tempo = doc_data.get("tempo") or 80
    lyricist = str(doc_data.get("lyricist") or doc_data.get("author") or "").strip()
    composer = str(doc_data.get("composer") or doc_data.get("arranger") or "").strip()
    title_scale = float(doc_data.get("titleFontScale") or 1.0)

    # 1. 標題（置中）
    title_fs = max(14.0, min(28.0, 18.0 * title_scale))
    title_w = font_bold.text_length(title, fontsize=title_fs)
    cur_y += title_fs
    page.insert_text(
        pymupdf.Point((page_w - title_w) / 2.0, cur_y),
        title,
        fontname=fn_bold,
        fontsize=title_fs,
        color=(0.07, 0.09, 0.15),
    )
    cur_y += 6.0

    if subtitle:
        sub_fs = 10.5
        sub_w = font_reg.text_length(subtitle, fontsize=sub_fs)
        cur_y += sub_fs
        page.insert_text(
            pymupdf.Point((page_w - sub_w) / 2.0, cur_y),
            subtitle,
            fontname=fn_reg,
            fontsize=sub_fs,
            color=(0.30, 0.34, 0.40),
        )
        cur_y += 5.0

    # 2. 標頭左方（1=C  4/4  ♩=80）與右方（作詞  作曲）
    cur_y += 13.0
    left_part1 = f"1 = {key_sig}    {time_sig}    "
    page.insert_text(
        pymupdf.Point(margin_x, cur_y),
        left_part1,
        fontname=fn_bold,
        fontsize=10.5,
        color=(0.12, 0.16, 0.22),
    )
    q_x = margin_x + font_bold.text_length(left_part1, fontsize=10.5) + 3.0
    # 繪製向量四分音符 ♩
    page.draw_oval(
        pymupdf.Rect(q_x - 2.4, cur_y - 3.6, q_x + 2.4, cur_y + 0.4),
        color=(0.12, 0.16, 0.22),
        fill=(0.12, 0.16, 0.22),
    )
    page.draw_line(
        pymupdf.Point(q_x + 2.0, cur_y - 1.6),
        pymupdf.Point(q_x + 2.0, cur_y - 9.5),
        color=(0.12, 0.16, 0.22),
        width=1.1,
    )
    page.insert_text(
        pymupdf.Point(q_x + 5.5, cur_y),
        f"= {tempo}",
        fontname=fn_bold,
        fontsize=10.5,
        color=(0.12, 0.16, 0.22),
    )

    credits_parts = []
    if lyricist:
        credits_parts.append(f"作詞：{lyricist}")
    if composer:
        credits_parts.append(f"作曲：{composer}")
    if not credits_parts:
        credits_parts.append("作詞：______    作曲：______")
    right_meta = "    ".join(credits_parts)
    right_w = font_reg.text_length(right_meta, fontsize=10.0)
    page.insert_text(
        pymupdf.Point(page_w - margin_x - right_w, cur_y),
        right_meta,
        fontname=fn_reg,
        fontsize=10.0,
        color=(0.22, 0.25, 0.32),
    )

    cur_y += 6.0
    page.draw_line(
        pymupdf.Point(margin_x, cur_y),
        pymupdf.Point(page_w - margin_x, cur_y),
        color=(0.25, 0.28, 0.35),
        width=1.0,
    )
    cur_y += 10.0

    measures = doc_data.get("measures") or []
    if not isinstance(measures, list) or len(measures) == 0:
        page.insert_text(
            pymupdf.Point(margin_x, cur_y + 16.0),
            "（尚無小節內容）",
            fontname=fn_reg,
            fontsize=11.0,
            color=(0.4, 0.4, 0.4),
        )
    else:
        cols_per_row = 4
        for row_start in range(0, len(measures), cols_per_row):
            row_measures = measures[row_start : row_start + cols_per_row]

            # 計算本行最高歌詞行數與各欄內容權重
            weights: List[float] = []
            parsed_row = []
            max_lyric_rows = 1
            for col_idx in range(cols_per_row):
                if col_idx < len(row_measures) and isinstance(row_measures[col_idx], dict):
                    m = row_measures[col_idx]
                    ch_t, nt_t, lyr_lines = _extract_measure_texts(m)
                    lyr_clean = [re.sub(r" {2,}", " ", line.strip()) for line in lyr_lines if line.strip()]
                    if len(lyr_clean) > max_lyric_rows:
                        max_lyric_rows = len(lyr_clean)
                    tokens = _parse_jianpu_tokens(nt_t)
                    w_u = max(
                        [_visual_width_units(nt_t), _visual_width_units(ch_t)]
                        + [_visual_width_units(line) for line in lyr_clean]
                        + [8.0]
                    ) + 2.5
                    weights.append(w_u)
                    parsed_row.append((m, ch_t, tokens, lyr_clean))
                else:
                    weights.append(10.0)
                    parsed_row.append(None)

            row_height = 54.0 + max_lyric_rows * 15.0
            if cur_y + row_height > page_h - margin_bottom:
                page = new_page_with_fonts()
                cur_y = margin_top

            sum_w = sum(weights) or 40.0
            col_widths = [max(85.0, usable_w * (w / sum_w)) for w in weights]
            scale_fix = usable_w / sum(col_widths)
            col_widths = [w * scale_fix for w in col_widths]

            x_cursor = margin_x
            for col_idx in range(cols_per_row):
                col_w = col_widths[col_idx]
                item = parsed_row[col_idx]
                if item is None:
                    x_cursor += col_w
                    continue

                m, ch_t, tokens, lyr_clean = item
                m_idx = row_start + col_idx
                pad_x = 8.0
                inner_w = max(40.0, col_w - pad_x * 2)

                # 第一行：小節號 + 段落記號
                y_head = cur_y + 9.0
                num_str = str(m_idx + 1)
                page.insert_text(
                    pymupdf.Point(x_cursor + 2.0, y_head),
                    num_str,
                    fontname=fn_bold,
                    fontsize=8.0,
                    color=(0.42, 0.45, 0.50),
                )
                sec_raw = str(m.get("section") or "").strip()
                sec_label = SECTION_LABELS.get(sec_raw.lower(), sec_raw) if sec_raw else ""
                if sec_label:
                    num_w = font_bold.text_length(num_str, fontsize=8.0)
                    page.insert_text(
                        pymupdf.Point(x_cursor + 5.0 + num_w, y_head),
                        f"[{sec_label}]",
                        fontname=fn_bold,
                        fontsize=8.5,
                        color=(0.12, 0.25, 0.68),
                    )

                # 第二行：藍色和弦行
                y_chord = cur_y + 21.0
                if ch_t:
                    ch_fs = 9.5
                    ch_w = font_bold.text_length(ch_t, fontsize=ch_fs)
                    if ch_w > inner_w and ch_w > 0:
                        ch_fs = max(7.5, ch_fs * (inner_w / ch_w))
                    page.insert_text(
                        pymupdf.Point(x_cursor + pad_x, y_chord),
                        ch_t,
                        fontname=fn_bold,
                        fontsize=ch_fs,
                        color=(0.10, 0.46, 0.82),
                    )

                # 第三行：共用單一小節線 + 簡譜音符行
                y_note = cur_y + 37.0
                # 左側共用小節線
                page.draw_line(
                    pymupdf.Point(x_cursor, y_note - 11.0),
                    pymupdf.Point(x_cursor, y_note + 4.0),
                    color=(0.15, 0.18, 0.24),
                    width=1.15,
                )
                # 若為該行最後一小節或全曲最後一小節，繪製右側收尾小節線
                if col_idx == cols_per_row - 1 or m_idx == len(measures) - 1:
                    page.draw_line(
                        pymupdf.Point(x_cursor + col_w, y_note - 11.0),
                        pymupdf.Point(x_cursor + col_w, y_note + 4.0),
                        color=(0.15, 0.18, 0.24),
                        width=1.15,
                    )

                note_fs = 11.5
                req_note_w = _measure_tokens_width(tokens, font_bold, note_fs)
                if req_note_w > inner_w and req_note_w > 0:
                    note_fs = max(8.0, note_fs * (inner_w / req_note_w))

                _draw_jianpu_tokens(
                    page=page,
                    tokens=tokens,
                    x_start=x_cursor + pad_x,
                    y_baseline=y_note,
                    fontsize=note_fs,
                    font_bold=font_bold,
                    fontname_bold=fn_bold,
                )

                # 第四行起：單行不折行歌詞
                y_lyr = cur_y + 53.0
                for lyr_line in lyr_clean:
                    lyr_fs = 10.5
                    lyr_w = font_reg.text_length(lyr_line, fontsize=lyr_fs)
                    if lyr_w > inner_w and lyr_w > 0:
                        lyr_fs = max(7.5, lyr_fs * (inner_w / lyr_w))
                    page.insert_text(
                        pymupdf.Point(x_cursor + pad_x, y_lyr),
                        lyr_line,
                        fontname=fn_reg,
                        fontsize=lyr_fs,
                        color=(0.12, 0.16, 0.22),
                    )
                    y_lyr += 14.0

                x_cursor += col_w

            cur_y += row_height + 6.0

    try:
        pdf_doc.subset_fonts()
    except Exception:
        pass
    pdf_bytes = pdf_doc.tobytes(garbage=3, deflate=True)
    pdf_doc.close()
    return pdf_bytes
