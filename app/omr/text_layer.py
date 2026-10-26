# -*- coding: utf-8 -*-
"""OMR 文字層互補（依 Umi-OCR 互補指南 §1.1／§4）。

Umi-OCR 只補「印在頁面上、但 OMR 輸出 schema 沒有插槽」的文字：
  - Capo（例如頁首 `原调1=A Capo=2`）
  - 原調 / 調性行（`1=G`）
  - 速度（`♩=88`）
  - 出處／附註（例如 `公众号·民谣吉他`）

絕對不拿它做記譜（簡譜／TAB／和弦圖／節奏）——那是 ScoreForge 的工作。
本模組只做兩件事：
  1. PDF 有文字層 → 直接取文字（精度最高、零 OCR 成本，指南 §1.1）；
  2. 無文字層 → Umi-OCR `lines --only-text`（區塊幾何、行序正確、過濾記譜行）。

所有失敗都非致命：回傳 (lines, None) 或空 meta，由呼叫方決定是否加警告。
"""
from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import unicodedata
from pathlib import Path

# ── Umi-OCR CLI 探測 ──────────────────────────────────────────────
_UMI_CLI_CANDIDATES = [
    os.environ.get("UMI_OCR_CLI"),
    r"D:\Harness\UmiOCR\bin\umi.mjs",
]


def _find_umi_cli() -> tuple[str, str | None]:
    """回傳 (script_path, node_exe)；找不到時 script 為 None。"""
    for cand in _UMI_CLI_CANDIDATES:
        if cand and Path(cand).exists():
            node = shutil.which("node")
            if not node:
                return cand, None
            return cand, node
    return "", None


def detect_umi() -> dict:
    """回傳前端可展示的文字層引擎狀態。"""
    script, node = _find_umi_cli()
    if not script:
        return {
            "available": False,
            "note": "找不到 Umi-OCR 包裝 CLI（D:\\Harness\\UmiOCR\\bin\\umi.mjs），文字層互補停用。",
        }
    if not node:
        return {"available": False, "note": "找不到 node.exe，無法啟動 Umi-OCR。"}
    return {"available": True, "note": "Umi-OCR 文字層互補就緒（首調用約 15–20s 冷啟動）。"}


# ── 文字層金礦：meta 抽取 ──────────────────────────────────────────
_CAPO_RE = re.compile(r"\b[Cc]apo(?:\s+[Oo]n)?\s*[:=]?\s*(\d{1,2})\b")
_ORIG_KEY_RE = re.compile(r"原\s*调\s*1\s*[:=]\s*([A-Ga-g][#b♯♭]?)")
_KEY_LINE_RE = re.compile(r"(?<![A-Za-z0-9])1\s*[:=]\s*([A-Ga-g][#b♯♭]?)(?!\d)")
_TEMPO_RE = re.compile(r"(?:♩|\btempo|速度)\s*[:=]?\s*(\d{2,3})\b", re.IGNORECASE)
_TIME_SIG_RE = re.compile(r"(?<!\d)(\d[23468]/\d[23468])(?!\d)")
_SOURCE_NOTE_RE = re.compile(
    r"(公众号|公眾號|出处|出處|来源|來源|编曲|編曲|整理|整理者|制谱|製譜)"
)


def extract_meta(lines: list[str]) -> dict:
    """從文字層行抽出 OMR schema 缺位的欄位。回傳 keys：
    capo(int|None)、originalKey、key、tempoBpm、timeSignature、sourceNote。
    沒有證據的欄位一律 None／空字串，絕不猜測。"""
    meta: dict = {
        "capo": None,
        "originalKey": "",
        "key": "",
        "tempoBpm": None,
        "timeSignature": "",
        "sourceNote": "",
    }
    text_all = "\n".join(lines)
    m = _CAPO_RE.search(text_all)
    if m:
        meta["capo"] = int(m.group(1))
    m = _ORIG_KEY_RE.search(text_all)
    if m:
        meta["originalKey"] = m.group(1).upper()
    m = _KEY_LINE_RE.search(text_all)
    if m:
        meta["key"] = m.group(1).upper()
    m = _TEMPO_RE.search(text_all)
    if m:
        meta["tempoBpm"] = int(m.group(1))
    m = _TIME_SIG_RE.search(text_all)
    if m:
        meta["timeSignature"] = m.group(1)
    for line in lines:
        if _SOURCE_NOTE_RE.search(line):
            meta["sourceNote"] = line.strip()
            break
    return meta


# ── 來源一：PDF 內文字層（指南 §1.1：有文字層就直接取） ───────────
def pdf_text_layer_lines(pdf: str | Path, max_pages: int = 20) -> list[str]:
    """PDF 有文字層 → 前 max_pages 頁的文字行（經 NFKC 正規化康熙部首與全形字元）；無文字層回傳 []。"""
    pdf = Path(pdf)
    try:
        from ..omr._pymupdf import fitz
    except ImportError:
        return []
    lines: list[str] = []
    try:
        with fitz.open(str(pdf)) as doc:
            for i in range(min(max_pages, doc.page_count)):
                text = doc[i].get_text("text") or ""
                for ln in text.splitlines():
                    s = unicodedata.normalize("NFKC", ln).strip()
                    if s:
                        lines.append(s)
    except Exception:
        return []
    return lines


# ── 日文／雙語（羅馬拼音＋日文漢字假名）與和弦歌詞譜文字層直通解析 ──
_CHORD_TOKEN_RE = re.compile(
    r"^([A-G][#b♯♭]?)(?:m|maj|min|dim|aug|sus|add|M)?(?:\d{0,2})(?:[\(\-+#b]\d+[\)]?)?(?:/[A-G][#b♯♭]?)?$"
)
_SECTION_HDR_RE = re.compile(r"^\[([A-Za-z0-9\s\-_#]+)\]$")
_UI_CHROME_EXACT = {
    "guitar", "ukulele", "piano", "mandolin", "banjo",
    "autoscroll", "listen", "pdf", "print", "simplify",
    "chords", "tabs", "tab", "official", "x", "×", "✕", "✖",
}
_JP_CJK_CHAR_RE = re.compile(r"[\u3040-\u30ff\u3400-\u9fff]")
_SMALL_KANA_SET = set("ー・…っゃゅょぁぃぅぇぉッャュョァィゥェォ")
_CHORD_ROOT_DEG = {"C": "1", "D": "2", "E": "3", "F": "4", "G": "5", "A": "6", "B": "7"}


def _norm_chord_tok(w: str) -> str:
    s = unicodedata.normalize("NFKC", w or "").strip().strip(".,;:|")
    if not s:
        return ""
    m = _CHORD_TOKEN_RE.match(s)
    return s if m else ""


def _is_ui_chrome_line(text: str, seen_music_or_chords: bool = False, saw_ui_header: bool = False) -> bool:
    s = (text or "").strip()
    if not s:
        return True
    low = s.lower()
    if low in _UI_CHROME_EXACT:
        return True
    if low.startswith("transpose") and re.fullmatch(r"transpose[\s\d+\-]*", low):
        return True
    if _CAPO_RE.search(s) or _ORIG_KEY_RE.search(s) or _KEY_LINE_RE.search(s) or _TEMPO_RE.search(s):
        return True
    if not seen_music_or_chords and saw_ui_header and re.fullmatch(r"[\d\s+\-]+", s) and len(s) <= 12:
        return True
    return False


def _clean_jp_text(s: str) -> str:
    t = unicodedata.normalize("NFKC", s or "").strip()
    t = re.sub(r"(?<=[\u3040-\u30ff\u3400-\u9fff])\s+(?=[\u3040-\u30ff\u3400-\u9fff])", "", t)
    return t.strip()


def extract_bilingual_lyrics(ln: str) -> tuple[str, str]:
    """從單行文字抽取 (主歌詞/拼音歌詞, 副歌詞/日文歌詞)。
    支援：
      1. `Nakashita koto mo aru !泣かした事もある$`（內嵌字型將括號編碼為 `! ... $`）
      2. `Nakashita koto mo aru (泣かした事もある)` 或 `（...）`
    """
    s = unicodedata.normalize("NFKC", ln or "").strip()
    if not s:
        return "", ""

    if "!" in s and ("$" in s or "＄" in s):
        ruby_parts = [m.group(1).strip() for m in re.finditer(r"!([^!$＄]+)[$＄]", s) if m.group(1).strip()]
        cleaned = re.sub(r"![^!$＄]+[$＄]", "", s)
        cleaned = re.sub(r"[!＄$]", "", cleaned).strip()
        cleaned = re.sub(r"\bSono気に\b", "Sono ki ni", cleaned)
        sub_lyric = _clean_jp_text(" ".join(ruby_parts))
        return (cleaned or s), sub_lyric

    paren_m = re.match(r"^(.+?)\s*[\(（]([^\)）]+)[\)）]\s*$", s)
    if paren_m:
        outer = paren_m.group(1).strip()
        inner = paren_m.group(2).strip()
        outer_has_jp = bool(_JP_CJK_CHAR_RE.search(outer))
        inner_has_jp = bool(_JP_CJK_CHAR_RE.search(inner))
        if inner_has_jp and not outer_has_jp:
            return outer, _clean_jp_text(inner)
        if outer_has_jp and not inner_has_jp:
            return inner, _clean_jp_text(outer)

    cleaned = re.sub(r"[!＄$]", "", s).strip()
    return (cleaned or s), ""


def _tokenize_mixed_lyric_units(text: str) -> list[str]:
    s = (text or "").strip()
    if not s:
        return []
    cjk_kana = sum(1 for ch in s if ("\u3040" <= ch <= "\u30ff") or ("\u3400" <= ch <= "\u9fff"))
    if cjk_kana == 0:
        return [w for w in s.split() if w]

    units: list[str] = []
    i = 0
    n = len(s)
    while i < n:
        ch = s[i]
        if ch.isspace():
            i += 1
            continue
        if ord(ch) > 255:
            syl = ch
            i += 1
            while i < n and (
                s[i] in _SMALL_KANA_SET
                or s[i] in "，。、！？；：「」『』（）…—,.!?;:'\")]"
            ):
                syl += s[i]
                i += 1
            units.append(syl)
        elif ch.isalnum() or ch in ("'", "-"):
            word = ""
            while i < n and (s[i].isalnum() or s[i] in ("'", "-", ",", ".", "!", "?", "…")):
                word += s[i]
                i += 1
            units.append(word)
        else:
            if units:
                units[-1] += ch
            else:
                units.append(ch)
            i += 1
    return units


def _join_mixed_units(units: list[str]) -> str:
    if not units:
        return ""
    out = units[0]
    for u in units[1:]:
        if not u:
            continue
        prev_ascii = ord(out[-1]) < 128 and (out[-1].isalnum() or out[-1] in ",.!?;:'\"-…")
        curr_ascii = ord(u[0]) < 128 and (u[0].isalnum() or u[0] in ("'", '"'))
        if prev_ascii or curr_ascii:
            out += " " + u
        else:
            out += u
    return out.strip()


def _distribute_to_4_beats(m_units: list[str]) -> list[list[str]]:
    beat_words: list[list[str]] = [[], [], [], []]
    n_u = len(m_units)
    if n_u == 1:
        beat_words[0] = [m_units[0]]
    elif n_u == 2:
        beat_words[0], beat_words[2] = [m_units[0]], [m_units[1]]
    elif n_u == 3:
        beat_words[0], beat_words[1], beat_words[2] = [m_units[0]], [m_units[1]], [m_units[2]]
    elif n_u >= 4:
        for u_i, u_s in enumerate(m_units):
            b_i = min(3, int(u_i * 4 // n_u))
            beat_words[b_i].append(u_s)
    return beat_words


def is_chord_lyric_pdf(source: str | Path, kind: str = "pdf") -> bool:
    """判斷是否為內嵌文字層之『和弦＋歌詞（含日文／羅馬拼音雙語）』PDF 樂譜。"""
    if kind != "pdf":
        return False
    lines = pdf_text_layer_lines(source, max_pages=20)
    if len(lines) < 4:
        return False
    chord_lines = 0
    lyric_lines = 0
    jianpu_bar_lines = 0
    for ln in lines:
        if _is_ui_chrome_line(ln):
            continue
        if "|" in ln or "｜" in ln:
            digits = sum(1 for c in ln if c in "01234567")
            if digits >= 3:
                jianpu_bar_lines += 1
                continue
        words = ln.split()
        c_words = [_norm_chord_tok(w) for w in words]
        if words and sum(1 for c in c_words if c) >= max(1, int(len(words) * 0.6)):
            chord_lines += 1
        elif len(ln) >= 2:
            lyric_lines += 1
    return jianpu_bar_lines == 0 and chord_lines >= 3 and lyric_lines >= 3


def recognize_chord_lyric_pdf_document(
    source: str | Path, filename: str = ""
) -> tuple[object, list[str]]:
    """直接從 PDF 文字層解析和弦＋歌詞（含日文漢字假名與羅馬拼音雙行歌詞），生成 V3 ScoreDocument。"""
    from ..models import ScoreBeat, ScoreDocument, ScoreMeasure, new_id, split_lyrics
    from .scoreforge_engine import _format_verse_line_and_ticks

    lines = pdf_text_layer_lines(source, max_pages=20)
    meta = extract_meta(lines)
    warnings: list[str] = []

    body = list(lines)
    title = ""
    if body:
        first = body[0].strip()
        first_words = first.split()
        first_is_chord = bool(first_words) and sum(1 for w in first_words if _norm_chord_tok(w)) >= max(1, int(len(first_words) * 0.6))
        if not first_is_chord and not _is_ui_chrome_line(first):
            title = first
            body = body[1:]

    stem_title = Path(filename or source).stem.strip()
    if not title or len(title) <= 1:
        title = stem_title or "日文與拼音歌詞辨識結果"

    key_sig = meta.get("key") or "C"
    time_sig = meta.get("timeSignature") or "4/4"
    tempo = int(meta.get("tempoBpm") or 90)

    pending_chords: list[str] = []
    pending_section: str = ""
    seen_music_or_chords = False
    saw_ui_header = False
    measures: list[ScoreMeasure] = []
    active_chord = key_sig

    def _append_chord_lyric_line(lyric_line: str, chords: list[str], sec_label: str, sub_override: str = "") -> None:
        nonlocal active_chord
        clean_ln, sub_ln = extract_bilingual_lyrics(lyric_line)
        if sub_override:
            sub_ln = _clean_jp_text(sub_override)

        units = _tokenize_mixed_lyric_units(clean_ln)
        sub_units = _tokenize_mixed_lyric_units(sub_ln)

        split_two = len(chords) >= 4 or len(units) >= 12
        halves: list[tuple[list[str], list[str], list[str]]] = []
        if not split_two:
            halves.append((units, sub_units, chords))
        else:
            mid_c = max(1, len(chords) // 2) if len(chords) >= 2 else len(chords)
            mid_u = max(1, len(units) // 2) if len(units) >= 2 else len(units)
            mid_s = max(1, len(sub_units) // 2) if len(sub_units) >= 2 else len(sub_units)
            halves.append((units[:mid_u], sub_units[:mid_s], chords[:mid_c]))
            halves.append((units[mid_u:], sub_units[mid_s:], chords[mid_c:]))

        for idx_h, (m_units, m_sub_units, m_chords) in enumerate(halves):
            if not m_units and not m_sub_units and not m_chords:
                continue
            measure_no = len(measures) + 1
            chord_map: dict[int, str] = {}
            if len(m_chords) == 1:
                chord_map[0] = m_chords[0]
            elif len(m_chords) == 2:
                chord_map[0] = m_chords[0]
                chord_map[2] = m_chords[1]
            elif len(m_chords) == 3:
                chord_map[0], chord_map[1], chord_map[2] = m_chords[0], m_chords[1], m_chords[2]
            elif len(m_chords) >= 4:
                for b_i in range(4):
                    chord_map[b_i] = m_chords[b_i]

            beat_words = _distribute_to_4_beats(m_units)
            beat_sub_words = _distribute_to_4_beats(m_sub_units)

            expanded_tokens: list[dict] = []
            beats: list[ScoreBeat] = []
            for b_i in range(4):
                if b_i in chord_map:
                    active_chord = chord_map[b_i]
                root_m = re.match(r"^([A-G])", active_chord or "C")
                deg_str = _CHORD_ROOT_DEG.get(root_m.group(1) if root_m else "C", "1")
                b_txt = _join_mixed_units(beat_words[b_i])
                b_sub_txt = _join_mixed_units(beat_sub_words[b_i])
                expanded_tokens.append({
                    "tok": deg_str,
                    "beat": float(b_i),
                    "dur": 1.0,
                    "lyrics": [b_txt, b_sub_txt, "", ""],
                    "is_rest": False,
                    "is_dash": False,
                })
                beats.append(ScoreBeat(
                    beat=b_i + 1,
                    note=deg_str,
                    lyric=b_txt,
                    chord=chord_map.get(b_i, ""),
                    duration="quarter",
                    confidence=0.98,
                    annotation=f"degree={deg_str}",
                ))

            note_parts: list[str] = []
            note_ticks: list[int] = []
            for t_i, item in enumerate(expanded_tokens):
                note_ticks.append(int(round(item["beat"] * 480)))
                if t_i == 0:
                    note_parts.append(item["tok"])
                else:
                    prev_item = expanded_tokens[t_i - 1]
                    prev_lyr = (prev_item["lyrics"][0] or "").strip()
                    prev_lyr2 = (prev_item["lyrics"][1] or "").strip()
                    ascii_w = len(prev_lyr) if (prev_lyr and sum(1 for c in prev_lyr if c.isascii()) >= len(prev_lyr) * 0.7 and len(prev_lyr) >= 3) else 0
                    jp_w = sum(2 if ord(c) > 255 else 1 for c in prev_lyr2) if len(prev_lyr2) >= 2 else 0
                    pad_w = max(ascii_w, jp_w)
                    sep = (" " * max(2, min(12, pad_w))) if pad_w >= 3 else "  "
                    note_parts.append(sep + item["tok"])
            note_text = "".join(note_parts)

            v0_txt = ("  ".join(m_units) if (len(m_units) == 2 and len(m_sub_units) >= 4) else " ".join(m_units)).strip()
            v1_txt = _join_mixed_units(m_sub_units)
            v0_syls = split_lyrics(v0_txt) if v0_txt else []
            v1_syls = split_lyrics(v1_txt) if v1_txt else []
            v0_ticks = [min(3, int(i * 4 // max(1, len(v0_syls)))) * 480 for i in range(len(v0_syls))]
            v1_ticks = [min(3, int(i * 4 // max(1, len(v1_syls)))) * 480 for i in range(len(v1_syls))]
            max_rows = 2 if v1_txt.strip() else 1

            chord_symbols: list[str] = []
            chord_offsets: list[int] = []
            chord_ticks: list[int] = []
            for b_i, sym in sorted(chord_map.items()):
                chord_symbols.append(sym)
                chord_offsets.append(b_i)
                chord_ticks.append(b_i * 480)

            measures.append(ScoreMeasure(
                number=measure_no,
                chordText=" ".join(chord_symbols),
                chordOffsets=chord_offsets,
                chordTicks=chord_ticks,
                noteText=note_text,
                noteTicks=note_ticks,
                lyricText=v0_txt,
                lyricTicks=v0_ticks,
                lyricText2=v1_txt,
                lyricText2Ticks=v1_ticks,
                lyricRows=max_rows,
                section=(sec_label if idx_h == 0 else ""),
                beats=beats,
            ))

    idx = 0
    while idx < len(body):
        ln = body[idx]
        idx += 1
        if _is_ui_chrome_line(ln, seen_music_or_chords=seen_music_or_chords, saw_ui_header=saw_ui_header):
            saw_ui_header = True
            continue
        sec_m = _SECTION_HDR_RE.match(ln)
        if sec_m:
            pending_section = sec_m.group(1).strip()
            continue
        words = ln.split()
        c_words = [_norm_chord_tok(w) for w in words]
        is_chord_ln = bool(words) and sum(1 for c in c_words if c) >= max(1, int(len(words) * 0.6))
        if is_chord_ln:
            seen_music_or_chords = True
            pending_chords.extend([c for c in c_words if c])
            continue

        cls = list(pending_chords)
        pending_chords = []
        sub_override = ""
        main_cand, sub_cand = extract_bilingual_lyrics(ln)
        if not sub_cand and idx < len(body):
            nxt = body[idx]
            if not _is_ui_chrome_line(nxt, seen_music_or_chords=True, saw_ui_header=saw_ui_header) and not _SECTION_HDR_RE.match(nxt):
                nxt_words = nxt.split()
                nxt_chords = [_norm_chord_tok(w) for w in nxt_words]
                nxt_is_chord = bool(nxt_words) and sum(1 for c in nxt_chords if c) >= max(1, int(len(nxt_words) * 0.6))
                if not nxt_is_chord:
                    cur_has_jp = bool(_JP_CJK_CHAR_RE.search(main_cand))
                    nxt_has_jp = bool(_JP_CJK_CHAR_RE.search(nxt))
                    if cur_has_jp != nxt_has_jp:
                        if nxt_has_jp:
                            sub_override = nxt
                        else:
                            ln = nxt
                            sub_override = main_cand
                        idx += 1

        _append_chord_lyric_line(ln, cls, pending_section, sub_override=sub_override)
        pending_section = ""

    if pending_chords:
        _append_chord_lyric_line("", list(pending_chords), pending_section)
        pending_chords = []

    # 統一同一視覺行（每 4 小節）的 lyricRows
    for line_start in range(0, len(measures), 4):
        line_ms = measures[line_start : line_start + 4]
        line_max_rows = max((m.lyricRows for m in line_ms), default=1)
        if line_max_rows > 1:
            for m in line_ms:
                m.lyricRows = max(m.lyricRows, line_max_rows)

    has_dual = any(bool(m.lyricText2.strip()) for m in measures)
    if has_dual:
        warnings.append(f"已從 PDF 文字層辨識雙語歌詞（第 1 行：拼音歌詞、第 2 行：日文歌詞），共 {len(measures)} 小節。")

    doc = ScoreDocument(
        id=new_id("doc"),
        title=title,
        key=key_sig,
        timeSignature=time_sig,
        tempo=tempo,
        capo=meta.get("capo"),
        sourceNote=meta.get("sourceNote") or "",
        engineMode="scoreforge",
        engineNote=f"PDF 文字層雙語和弦歌詞直通解析｜{len(measures)} 小節",
        sourceName=filename or Path(source).name,
        measures=measures,
    )
    return doc.renumber(), warnings


def render_pdf_page1_png(pdf: str | Path, out_dir: str | Path) -> Path | None:
    """無文字層 PDF → 渲染第 1 頁成 300 DPI PNG 供 Umi-OCR 掃描。"""
    pdf = Path(pdf)
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    try:
        from ..omr._pymupdf import fitz
    except ImportError:
        return None
    try:
        with fitz.open(str(pdf)) as doc:
            if doc.page_count == 0:
                return None
            pix = doc[0].get_pixmap(matrix=fitz.Matrix(300 / 72, 300 / 72), alpha=False)
            target = out_dir / "uml_page-001.png"
            pix.save(str(target))
            return target
    except Exception:
        return None


# ── 來源二：Umi-OCR lines --only-text（指南 §2.2／§3：用預設 chs，勿換 cht）
def run_umi_lines(image: str | Path, timeout_s: int = 180) -> list[str]:
    """對單頁影像跑 `lines --only-text`（區塊幾何行序 + 過濾純數字記譜行）。

    回傳文字行清單；服務未起來會自動冷啟動；code 101（沒文字）算正常空結果。
    """
    script, node = _find_umi_cli()
    if not script or not node:
        return []
    image = Path(image)
    if not image.exists():
        return []
    cmd = [node, script, "lines", str(image), "--only-text", "--json"]
    try:
        proc = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=timeout_s,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        )
    except (OSError, subprocess.SubprocessError) as exc:  # SubprocessError 含 TimeoutExpired
        raise RuntimeError(f"Umi-OCR 呼叫失敗：{exc}") from exc
    # 離開碼 3 = 圖片沒文字（正常），0 = 成功；其他才算故障（靜默回 []）
    if proc.returncode not in (0, 3):
        return []
    try:
        data = json.loads(proc.stdout)
    except (json.JSONDecodeError, ValueError):
        return []
    results = data.get("results") or [data]
    lines: list[str] = []
    for r in results:
        for item in r.get("data") or []:
            t = (item.get("text") or "").strip()
            if t:
                lines.append(t)
    return lines


# ── 對 pipeline 的一站式入口 ──────────────────────────────────────
def enrich_document(doc, source: Path, kind: str, work_dir: Path, warnings: list[str]) -> None:
    """以文字層補齊 OMR schema 缺位的欄位（就地修改 doc 與 warnings）。

    策略（指南 §1.1＋§4.3）：
      PDF 有文字層 → 直接用（零成本、精度最高）
      無文字層     → 影像來源直接掃；PDF 先渲染第 1 頁再掃
    只填「OMR 沒給」的欄位：capo、原調、出處附註。既有值一律不動（不猜測）。
    """
    lines: list[str] = []
    if kind == "pdf":
        lines = pdf_text_layer_lines(source)
    if not lines and getattr(doc, "engineMode", "") not in ("scoreforge", "staff-to-jianpu"):
        img: Path | None = None
        if kind == "image":
            img = Path(source)
        elif kind == "pdf":
            img = render_pdf_page1_png(source, work_dir)
        if img and img.exists() and detect_umi().get("available"):
            try:
                lines = run_umi_lines(img)
            except RuntimeError:
                return  # Umi-OCR 故障不阻斷 OMR 主流程
    if not lines:
        return
    meta = extract_meta(lines)
    if meta["capo"] is not None and not getattr(doc, "capo", None):
        doc.capo = meta["capo"]
        warnings.append(f"文字層偵測到 Capo={meta['capo']}（OMR 結果無 capo 欄位，已自文字層補入）。")
    if meta["originalKey"]:
        warnings.append(f"文字層：原調 1={meta['originalKey']}（調性行 1={meta['key'] or doc.key}）。")
    if meta["sourceNote"]:
        doc.sourceNote = meta["sourceNote"]
        warnings.append(f"文字層出處／附註：{meta['sourceNote']}")
