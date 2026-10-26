"""版面分析：OCR 行 → 和弦／簡譜／歌詞分類 → 小節（規劃書 8.1 第三階段）。

分類規則：
* 簡譜行：以 0-7、升降記號、八度點、延長線與小節線為主。
* 和弦行：token 幾乎都符合和弦文法（C、Am7、F#m、G/B…）。
* 歌詞行：其餘含中文或拉丁字母的行。
分組：依垂直順序把「和弦 → 簡譜 → 歌詞」視為一組譜行；缺任一列仍可成立。
"""
from __future__ import annotations

import re

from ..models import ScoreBeat, ScoreMeasure, split_lyrics
from .engine import CHORD_TOKEN, CJK, OcrLine

NOTE_CLEAN = re.compile(r"[^0-7#b'’,._|\-\s\u2014\u2013]")
# OCR 常把相鄰數字黏成一團（1235），因此以 token 正則掃描而非只靠空白切分
NOTE_TOKEN_SCAN = re.compile(r"[#b]*[0-7]['’,]*_*\.*|[-\u2014\u2013]|\|")
META_LINE = re.compile(r"(1\s*=\s*[A-G])|(\d\s*/\s*\d)|([♩J]\s*=\s*\d)|(=\s*\d{2,3})")
META_KEY = re.compile(r"1\s*=\s*([A-G][#b]?)")
META_TIME = re.compile(r"\b(\d{1,2}\s*/\s*\d{1,2})\b")
META_TEMPO = re.compile(r"(?:♩|J)\s*=\s*(\d{2,3})")
LYRICIST = re.compile(r"(?:作詞|作词|詞|填詞)\s*[:：]?\s*([^\s：:]{1,20})")
COMPOSER = re.compile(r"(?:作曲|曲)\s*[:：]?\s*([^\s：:]{1,20})")


def is_meta_line(text: str) -> bool:
    """判斷是否為調號／拍號／速度等標頭行。"""
    return bool(META_LINE.search(text)) and len(text) <= 40


def classify_line(line: OcrLine) -> str:
    text = line.text.strip()
    if not text:
        return "blank"
    tokens = [t for t in re.split(r"\s+", text) if t]
    if not tokens:
        return "blank"
    # 調號／拍號／速度等標頭行不可當成簡譜行，否則會多出假小節
    if is_meta_line(text):
        return "meta"

    digits = len(re.findall(r"[0-7]", text))
    letters = len(re.findall(r"[A-Za-z]", text))
    cjk = len(CJK.findall(text))
    noise = len(NOTE_CLEAN.sub("", text))

    chord_hits = sum(1 for t in tokens if CHORD_TOKEN.match(t.strip("|")))
    if chord_hits >= max(1, len(tokens) * 0.6) and cjk == 0 and digits <= letters:
        return "chord"
    if digits >= 2 and cjk == 0 and digits >= letters and noise >= len(text) * 0.5:
        return "note"
    if cjk or letters:
        return "lyric"
    return "other"


def extract_metadata(lines: list[OcrLine]) -> dict:
    """從前幾行抓歌名、作詞、作曲、調號、拍號、速度。"""
    meta: dict = {}
    head = lines[: min(8, len(lines))]
    for line in head:
        text = line.text.strip()
        if (m := META_KEY.search(text)) and "key" not in meta:
            meta["key"] = m.group(1)
        if (m := META_TIME.search(text)) and "timeSignature" not in meta:
            meta["timeSignature"] = m.group(1).replace(" ", "")
        if (m := META_TEMPO.search(text)) and "tempo" not in meta:
            meta["tempo"] = int(m.group(1))
        if (m := LYRICIST.search(text)) and "lyricist" not in meta:
            meta["lyricist"] = m.group(1)
        if (m := COMPOSER.search(text)) and "composer" not in meta:
            meta["composer"] = m.group(1)
    for line in head:
        text = line.text.strip()
        if (
            "title" not in meta
            and classify_line(line) == "lyric"
            and 1 <= len(text) <= 30
            and not LYRICIST.search(text)
            and not COMPOSER.search(text)
            and not META_KEY.search(text)
            and _plausible_title(text)
            and (CJK.search(text) or line.confidence >= 0.50)
        ):
            meta["title"] = text
            break
    return meta


def _plausible_title(text: str) -> bool:
    """標題必須看起來像標題，不能是 OCR 雜訊。

    未安裝中文語言包時，漢字標題會被英文模型讀成類似
    `A¥ JRL HSU BE aoe EY` 的一堆碎片。這種字串寫進標題比空白更糟，
    因此寧可留空（上層會回退用檔名）。
    """
    if CJK.search(text):
        return True
    words = text.split()
    if len(words) >= 3 and sum(1 for w in words if len(w) <= 2) >= len(words) * 0.5:
        return False  # 一堆一到兩字碎片 → 雜訊
    letters = [c for c in text if c.isalnum()]
    if not letters:
        return False
    # 全大寫碎片混在正常字詞裡（例如 `SEW YE Pag AIT`）→ 雜訊。
    caps = [w for w in words if len(w) >= 2 and w.isupper()]
    if caps and not text.isupper() and len(caps) >= max(1, len(words) * 0.34):
        return False
    odd = sum(1 for c in text if not (c.isalnum() or c.isspace() or c in "-'’.,()、（）"))
    return odd <= len(text) * 0.15


def _clean_note_text(text: str) -> str:
    """正規化 OCR 常見誤判字元，並把黏在一起的數字拆成獨立 token。"""
    text = text.replace("O", "0").replace("o", "0").replace("l", "1").replace("I", "1")
    text = NOTE_CLEAN.sub(" ", text)
    tokens: list[str] = []
    for raw in re.split(r"\s+", text.strip()):
        if not raw:
            continue
        found = NOTE_TOKEN_SCAN.findall(raw)
        tokens.extend(found if found else [])
    return " ".join(tokens).strip()


def _is_bar_only(line: OcrLine) -> bool:
    """判斷是否為「純小節線」行：token 過半是 |"""
    tokens = [t for t in re.split(r"\s+", line.text.strip()) if t]
    if not tokens:
        return False
    bar_count = sum(1 for t in tokens if t == "|")
    return bar_count >= len(tokens) * 0.5


def group_lines(lines: list[OcrLine]) -> list[dict]:
    """把 OCR 行組成譜行 (chord/note/lyric) 三元組。"""
    # 先合併「純小節線」行到相鄰的 note 行：把 | 併入上方或下方的 note text
    merged: list[OcrLine] = []
    for line in lines:
        if _is_bar_only(line):
            if merged and classify_line(merged[-1]) == "note":
                merged[-1] = OcrLine(
                    text=(merged[-1].text + " " + line.text).strip(),
                    confidence=max(merged[-1].confidence, line.confidence),
                    top=merged[-1].top,
                    left=merged[-1].left,
                    height=merged[-1].height,
                )
            elif merged:
                # 暫存到下一行 note 會處理
                merged.append(line)
            else:
                merged.append(line)
        else:
            merged.append(line)

    tagged = [(classify_line(l), l) for l in merged]
    groups: list[dict] = []
    i = 0
    while i < len(tagged):
        kind, line = tagged[i]
        if kind != "note":
            i += 1
            continue
        # 跳過低信心垃圾音符行，避免產生空白／雜訊小節
        if line.confidence < 0.20:
            i += 1
            continue
        chord = None
        if i > 0 and tagged[i - 1][0] == "chord":
            chord = tagged[i - 1][1]
        lyric = None
        if i + 1 < len(tagged) and tagged[i + 1][0] == "lyric":
            lyric = tagged[i + 1][1]
        groups.append({"chord": chord, "note": line, "lyric": lyric})
        i += 2 if lyric else 1
    return groups


def group_to_measures(group: dict, page: int) -> list[ScoreMeasure]:
    note_line: OcrLine = group["note"]
    note_text = _clean_note_text(note_line.text)
    if not note_text:
        return []
    chord_line: OcrLine | None = group.get("chord")
    lyric_line: OcrLine | None = group.get("lyric")

    note_cells = _split_cells(note_text, beats_per_measure=4)
    lyric_cells = _split_lyric_cells(lyric_line.text if lyric_line else "", len(note_cells), note_cells)
    chord_cells = _distribute_chords(chord_line.text if chord_line else "", len(note_cells))

    measures: list[ScoreMeasure] = []
    for idx, cell in enumerate(note_cells):
        measure = ScoreMeasure(
            number=idx + 1,
            noteText=cell,
            lyricText=lyric_cells[idx] if idx < len(lyric_cells) else "",
            chordText=chord_cells[idx] if idx < len(chord_cells) else "",
            sourcePage=page,
        )
        confidences = [note_line.confidence]
        if lyric_line and measure.lyricText:
            confidences.append(lyric_line.confidence)
        if chord_line and measure.chordText:
            confidences.append(chord_line.confidence)
        measure.expand_beats(min_confidence=round(min(confidences), 3))
        measures.append(measure)
    return measures


def _distribute_chords(text: str, measure_count: int) -> list[str]:
    """和弦行分配：有小節線就照切；token 數等於小節數則一對一；否則按 4 拍分組。"""
    text = (text or "").strip()
    if not text or measure_count <= 0:
        return []
    if "|" in text:
        cells = [c.strip() for c in text.split("|") if c.strip()]
        if len(cells) == measure_count:
            return cells
    tokens = [t for t in re.split(r"[\s|]+", text) if t]
    if len(tokens) == measure_count:
        return tokens
    return _split_cells(text, beats_per_measure=4)


def _split_cells(text: str, beats_per_measure: int = 4) -> list[str]:
    text = (text or "").strip()
    if not text:
        return []
    if "|" in text:
        cells = [c.strip() for c in text.split("|") if c.strip()]
        # 過濾純 0 (全休止符) 的小節 — 在雜訊帶中很常見，真正的樂譜不會有連續整小節全 0
        cells = [c for c in cells if any(t for t in c.split() if t and t[0] not in ("0", "_"))]
        return cells
    tokens = [t for t in re.split(r"\s+", text) if t]
    return [
        " ".join(tokens[i : i + beats_per_measure])
        for i in range(0, len(tokens), beats_per_measure)
    ]


def _split_lyric_cells(text: str, measure_count: int, note_cells: list[str]) -> list[str]:
    """歌詞依各小節音符數分配，避免整行擠進第一小節。

    當音符數識別不準（常有漏字）時，改以「音節總數 ⇢ 各小節均分＋餘數順序分配」，
    這樣簡譜與歌詞不會因某小節漏音符而整體錯位。
    """
    text = (text or "").strip()
    if not text or measure_count == 0:
        return []
    if "|" in text:
        cells = [c.strip() for c in text.split("|") if c.strip()]
        if len(cells) == measure_count:
            return cells
    syllables = split_lyrics(text)
    total = len(syllables)
    if total == 0:
        return [""] * measure_count
    # 若自然切分（按音符數）能與小節數匹配，優先使用，較貼近原譜
    note_counts = [
        len([t for t in re.split(r"\s+", c) if t and t not in {"-", "0"}])
        for c in note_cells
    ]
    sum_counts = sum(note_counts) or 1
    if sum_counts >= measure_count:
        out: list[str] = []
        cursor = 0
        for cnt in note_counts:
            take = max(1, round(total * cnt / sum_counts))
            chunk = syllables[cursor : cursor + take]
            cursor += take
            out.append(
                "".join(chunk)
                if chunk and CJK.search("".join(chunk))
                else " ".join(chunk)
            )
        if cursor < total and out:
            remainder = syllables[cursor:]
            joiner = "" if CJK.search("".join(remainder)) else " "
            out[-1] = (out[-1] + joiner + joiner.join(remainder)).strip()
        return out
    # 備援：依小節數均分＋餘數順序
    base = total // measure_count
    rem = total % measure_count
    out = []
    cursor = 0
    for i in range(measure_count):
        take = base + (1 if i < rem else 0)
        chunk = syllables[cursor : cursor + take]
        cursor += take
        out.append("".join(chunk) if chunk and CJK.search("".join(chunk)) else " ".join(chunk))
    return out


def lines_to_measures(lines: list[OcrLine], page: int) -> list[ScoreMeasure]:
    measures: list[ScoreMeasure] = []
    for group in group_lines(lines):
        measures.extend(group_to_measures(group, page))
    return measures
