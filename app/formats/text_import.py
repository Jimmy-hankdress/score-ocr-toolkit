"""文字類導入 adapter：JSON／CSV／TSV／TXT／SON（規劃書 5.2）。

策略：
1. JSON → 支援本工具自身的 rows+metadata，也支援通用陣列。
2. CSV／TSV → 依標題列或欄位順序解析 measure/beat/note/lyric/chord/...
3. TXT／SON → 先嘗試表格式；不成則以「原稿式文字區塊」解析
   （和弦列／簡譜列／歌詞列三行一組）。
4. 無法解析時拋出 ValidationError，明確顯示「格式無法解析」，不建立假結果。
"""
from __future__ import annotations

import csv
import io
import json
import re
from pathlib import Path

from ..models import (
    MEASURES_PER_LINE,
    ScoreBeat,
    ScoreDocument,
    ScoreMeasure,
    split_lyrics,
    split_notes,
)
from .validation import ValidationError, decode_text_or_none

HEADER_ALIASES = {
    "measure": {"measure", "小節", "bar", "measurenumber", "measure_number", "小节"},
    "beat": {"beat", "拍", "beatindex", "beat_index", "拍位"},
    "note": {"note", "notes", "簡譜", "简谱", "notetext", "note_text", "音符", "唱名"},
    "lyric": {"lyric", "lyrics", "歌詞", "歌词", "lyrictext", "lyric_text", "字"},
    "chord": {"chord", "chords", "和弦", "chordtext", "chord_text"},
    "duration": {"duration", "時值", "时值", "dur"},
    "confidence": {"confidence", "信心值", "信心", "conf", "score"},
    "line": {"line", "lineindex", "行", "行號"},
    "position": {"position", "lineposition", "行內位置", "pos"},
}
CHORD_TOKEN_RE = re.compile(
    r"^\(?([A-G][#b\u266f\u266d＃♭]?(?:(?:maj|min|m|M|dim|aug|sus|add|no)[0-9#b+\-]*|[0-9]+|[+\-][0-9]+)*(?:/(?:[#b\u266f\u266d＃♭]?[A-G][#b\u266f\u266d＃♭]?))?)\)?$"
)
CHORD_LINE_RE = re.compile(r"^[\s|]*([A-G][#b]?(?:maj7|maj|min7|min|m7|m|dim7|dim|aug|sus[24]?|add9|[679]|11|13|M7)?(?:/[A-G][#b]?)?[\s|]*)+$")
NOTE_LINE_RE = re.compile(r"^[\s|0-7#b'’,._\-\u2014\u2013\u266f\u266d()]+$")
SECTION_LINE_RE = re.compile(
    r"^\s*(前奏|間奏|间奏|尾奏|尾聲|尾声|主歌|副歌|橋段|桥段|導歌|导歌|Intro|Verse|Pre-?Chorus|Chorus|Bridge|Interlude|Outro|Coda|Ending|Fine|D\.?C\.?|D\.?S\.?)\s*[:：]?\s*$",
    re.I,
)
ZHUYIN_SOLFEGE_MAP = {
    "ㄉㄡ": "1", "ㄉㄛ": "1",
    "ㄖㄨㄟ": "2", "ㄖㄟ": "2",
    "ㄇㄧ": "3", "ㄇ一": "3",
    "ㄈㄚ": "4",
    "ㄙㄡ": "5", "ㄙㄛ": "5",
    "ㄌㄚ": "6",
    "ㄒㄧ": "7", "ㄒ一": "7",
}
META_PATTERNS = [
    (re.compile(r"^\s*(?:歌名|曲名|title)\s*[:：]\s*(.+)$", re.I), "title"),
    (re.compile(r"^\s*(?:作詞|作词|填詞|lyricist)\s*[:：]\s*(.+)$", re.I), "lyricist"),
    (re.compile(r"^\s*(?:作曲|音樂人|音乐人|演唱|歌手|藝人|艺人|原唱|編曲|编曲|composer|artist|singer)\s*[:：]\s*(.+)$", re.I), "composer"),
    (re.compile(r"^\s*(?:調|调|key)\s*[:：]?\s*(?:1\s*=\s*)?([A-G][#b]?)\s*$", re.I), "key"),
    (re.compile(r"^\s*1\s*=\s*([A-G][#b]?)\s*$"), "key"),
    (re.compile(r"^\s*(?:拍號|拍号|time)\s*[:：]?\s*(\d{1,2}\s*/\s*\d{1,2})\s*$", re.I), "timeSignature"),
    (re.compile(r"^\s*(\d{1,2}/\d{1,2})\s*$"), "timeSignature"),
    (re.compile(r"^\s*(?:速度|tempo|bpm)\s*[:：]?\s*(\d{2,3})\s*$", re.I), "tempo"),
    (re.compile(r"^\s*[♩J♪]\s*=\s*(\d{2,3})\s*$"), "tempo"),
]


def _canon(name: str) -> str | None:
    key = re.sub(r"[\s_\-]", "", (name or "").strip().lower())
    for canon, aliases in HEADER_ALIASES.items():
        if key in {re.sub(r"[\s_\-]", "", a.lower()) for a in aliases}:
            return canon
    return None


def parse_text_import(path: Path, filename: str | None = None) -> ScoreDocument:
    payload = path.read_bytes()
    text = decode_text_or_none(payload)
    if text is None:
        raise ValidationError(
            f"{path.suffix} 格式無法解析：內容不是可辨識的文字結構。"
            "若這是二進位 .SON 檔，請先用原程式匯出 CSV／TSV／JSON 再導入；"
            "本工具不會為未知格式建立假的識別結果。"
        )
    name = filename or path.name
    ext = path.suffix.lower()
    title_default = Path(name).stem

    if ext == ".json" or text.lstrip().startswith(("{", "[")):
        try:
            return _from_json(json.loads(text), title_default, name)
        except json.JSONDecodeError as exc:
            if ext == ".json":
                raise ValidationError(f"JSON 格式無法解析：{exc.msg}（第 {exc.lineno} 行）") from exc

    doc = _from_table(text, title_default, name)
    if doc is not None:
        return doc
    doc = _from_manuscript_text(text, title_default, name)
    if doc is not None:
        return doc
    raise ValidationError(
        f"{ext} 格式無法解析：找不到可辨識的欄位標題、分隔欄位或原稿式（和弦／簡譜／歌詞）結構。"
        "請參考說明文件附錄 A 的欄位格式，或改用 JSON 匯入。"
    )


# ---------------- JSON ----------------


def _from_json(data, title_default: str, source_name: str) -> ScoreDocument:
    if isinstance(data, dict) and isinstance(data.get("measures"), list) and data.get("rows") is None:
        doc = ScoreDocument.from_dict(data)
        doc.sourceName = source_name
        doc.engineMode = "text-import"
        doc.engineNote = "由 JSON 專案檔導入"
        return doc

    meta = {}
    rows = data
    if isinstance(data, dict):
        meta = data.get("metadata") or data.get("meta") or {}
        rows = data.get("rows") or data.get("measures") or data.get("data") or []
    if not isinstance(rows, list) or not rows:
        raise ValidationError("JSON 格式無法解析：找不到 rows／measures 陣列內容。")

    doc = ScoreDocument(
        title=str(meta.get("title") or title_default),
        lyricist=str(meta.get("lyricist", "") or ""),
        composer=str(meta.get("composer", "") or ""),
        key=str(meta.get("key") or "C"),
        timeSignature=str(meta.get("timeSignature") or meta.get("time") or "4/4"),
        tempo=int(meta.get("tempo", 90) or 90),
        engineMode="text-import",
        engineNote="由 JSON 導入（未經 OMR 辨識）",
        sourceName=source_name,
    )
    buckets: dict[int, ScoreMeasure] = {}
    for i, row in enumerate(rows):
        if not isinstance(row, dict):
            continue
        norm = { _canon(k) or k: v for k, v in row.items() }
        number = int(norm.get("measure", i + 1) or i + 1)
        measure = buckets.setdefault(number, ScoreMeasure(number=number))
        note = str(norm.get("note", norm.get("noteText", "")) or "")
        lyric = str(norm.get("lyric", norm.get("lyricText", "")) or "")
        chord = str(norm.get("chord", norm.get("chordText", "")) or "")
        conf = float(norm.get("confidence", 1.0) or 1.0)
        if "beats" in row and isinstance(row["beats"], list) and row["beats"]:
            measure.chordText = chord or measure.chordText
            measure.noteText = note or measure.noteText
            measure.lyricText = lyric or measure.lyricText
            measure.beats = [ScoreBeat.from_dict(b) for b in row["beats"]]
            if not measure.noteText:
                measure.noteText = " ".join(b.note for b in measure.beats if b.note)
                measure.lyricText = "".join(b.lyric for b in measure.beats)
                measure.chordText = " ".join(dict.fromkeys(b.chord for b in measure.beats if b.chord))
            continue
        _append_cell(measure, note, lyric, chord, conf)
    doc.measures = [buckets[k] for k in sorted(buckets)]
    for m in doc.measures:
        m.expand_beats(min_confidence=_measure_conf(m))
    return doc.renumber()


def _measure_conf(m: ScoreMeasure) -> float:
    return min([b.confidence for b in m.beats], default=1.0)


def _append_cell(measure: ScoreMeasure, note: str, lyric: str, chord: str, conf: float) -> None:
    """把一列資料併入小節整句（規劃書 8.2：小節保留完整句子）。"""
    if note:
        measure.noteText = f"{measure.noteText} {note}".strip()
    if lyric:
        sep = "" if not measure.lyricText or _is_cjk(lyric) else " "
        measure.lyricText = f"{measure.lyricText}{sep}{lyric}".strip()
    if chord:
        measure.chordText = f"{measure.chordText} {chord}".strip()
    tokens = split_notes(measure.noteText)
    lyrics = split_lyrics(measure.lyricText)
    chords = [c for c in measure.chordText.split() if c]
    measure.beats = [
        ScoreBeat(
            beat=i + 1,
            note=tokens[i] if i < len(tokens) else "",
            lyric=lyrics[i] if i < len(lyrics) else "",
            chord=chords[i] if i < len(chords) else "",
            confidence=conf,
        )
        for i in range(max(len(tokens), len(lyrics), len(chords), 1))
    ]


def _is_cjk(text: str) -> bool:
    return bool(re.search(r"[\u4e00-\u9fff]", text or ""))


# ---------------- CSV / TSV / 表格式 TXT、SON ----------------


def _sniff_delimiter(text: str) -> str | None:
    """偵測表格分隔符。

    注意：`|` 不可作為分隔符候選——在原稿式簡譜中它是小節線，
    若當成欄位分隔會把整行譜錯切成欄位。
    """
    lines = [l for l in text.splitlines()[:40] if l.strip() and not l.lstrip().startswith("#")]
    if len(lines) < 2:
        return None
    for delim in ("\t", ",", ";"):
        hit = [l for l in lines if delim in l]
        if len(hit) < max(2, len(lines) * 0.6):
            continue  # 只有少數行含此字元 → 可能是簡譜的低八度逗點，不是欄位分隔
        fields = [len(l.split(delim)) for l in hit]
        if min(fields) >= 3:
            return delim
    return None


def _from_table(text: str, title_default: str, source_name: str) -> ScoreDocument | None:
    delim = _sniff_delimiter(text)
    if not delim:
        return None
    meta: dict = {}
    body_lines: list[str] = []
    for line in text.splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            _collect_meta(stripped.lstrip("#").strip(), meta)
            continue
        if delim not in line:
            if not _collect_meta(stripped, meta):
                body_lines.append(line)
            continue
        body_lines.append(line)
    if not body_lines:
        return None

    reader = csv.reader(io.StringIO("\n".join(body_lines)), delimiter=delim)
    rows = [r for r in reader if any((c or "").strip() for c in r)]
    if not rows:
        return None

    header = [_canon(c) for c in rows[0]]
    has_header = sum(1 for h in header if h) >= 2
    if has_header:
        columns = header
        data_rows = rows[1:]
    else:
        # 附錄 A 預設欄位順序
        columns = ["measure", "beat", "note", "lyric", "chord", "duration", "confidence"]
        data_rows = rows
    if not data_rows:
        return None

    doc = ScoreDocument(
        title=str(meta.get("title") or title_default),
        lyricist=str(meta.get("lyricist", "")),
        composer=str(meta.get("composer", "")),
        key=str(meta.get("key") or "C"),
        timeSignature=str(meta.get("timeSignature") or "4/4"),
        tempo=int(meta.get("tempo", 90) or 90),
        engineMode="text-import",
        engineNote=f"由 {source_name} 表格導入（未經 OMR 辨識）",
        sourceName=source_name,
    )
    buckets: dict[int, ScoreMeasure] = {}
    fallback_number = 0
    for row in data_rows:
        cells = {}
        for i, col in enumerate(columns):
            if col and i < len(row):
                cells[col] = (row[i] or "").strip()
        if not any(cells.get(k) for k in ("note", "lyric", "chord")):
            continue
        raw_measure = cells.get("measure", "")
        if raw_measure.isdigit():
            number = int(raw_measure)
        else:
            fallback_number += 1
            number = fallback_number
        measure = buckets.setdefault(number, ScoreMeasure(number=number))
        conf_raw = cells.get("confidence", "")
        try:
            conf = float(conf_raw) if conf_raw else 1.0
        except ValueError:
            conf = 1.0
        _append_cell(measure, cells.get("note", ""), cells.get("lyric", ""), cells.get("chord", ""), conf)
    if not buckets:
        return None
    doc.measures = [buckets[k] for k in sorted(buckets)]
    return doc.renumber()


def _collect_meta(line: str, meta: dict) -> bool:
    for pattern, field in META_PATTERNS:
        m = pattern.match(line)
        if m:
            value = m.group(1).strip()
            meta[field] = int(value) if field == "tempo" else value
            return True
    return False


# ---------------- 原稿式文字（和弦／簡譜／歌詞三列，或和弦／歌詞吉他彈唱譜） ----------------


def _normalize_chord_token(tok: str) -> str:
    """正規化和弦代號（例如 `(Dsus4)` → `Dsus4`、`D/#F` → `D/F#`）。"""
    t = (tok or "").strip()
    if t.startswith("(") and t.endswith(")"):
        t = t[1:-1].strip()
    t = t.replace("＃", "#").replace("♯", "#").replace("♭", "b")
    # 將轉位根音前置升降號正規化為後置（例如 D/#F -> D/F#）
    t = re.sub(r"/([#b])([A-G])$", r"/\2\1", t)
    return t


def _is_chord_line(s: str) -> bool:
    if CHORD_LINE_RE.match(s):
        return True
    tokens = [t for t in re.split(r"[\s\u3000|]+", s.strip()) if t]
    if not tokens:
        return False
    return all(bool(CHORD_TOKEN_RE.match(t)) for t in tokens)


def _extract_zhuyin_notes(s: str) -> list[str] | None:
    """若整行皆為注音唱名（如 `ㄖㄨㄟ ㄙㄡ ㄙㄡ ㄒ一 ㄉㄡ`），轉為簡譜音級清單。"""
    tokens = [t.strip() for t in re.split(r"[\s\u3000|]+", s.strip()) if t.strip()]
    if len(tokens) < 2:
        return None
    if all(t in ZHUYIN_SOLFEGE_MAP for t in tokens):
        return [ZHUYIN_SOLFEGE_MAP[t] for t in tokens]
    return None


def _display_col(s: str) -> int:
    col = 0
    for ch in s:
        col += 2 if (ord(ch) > 255 or ch == "\u3000") else 1
    return col


def _line_kind(line: str) -> str:
    s = line.strip()
    if not s:
        return "blank"
    if SECTION_LINE_RE.match(s):
        return "section"
    if NOTE_LINE_RE.match(s) and re.search(r"[0-7]", s):
        return "note"
    if _is_chord_line(s):
        return "chord"
    return "lyric"


def _from_manuscript_text(text: str, title_default: str, source_name: str) -> ScoreDocument | None:
    meta: dict = {}
    lines: list[tuple[str, str]] = []
    seen_music = False
    for raw in text.splitlines():
        s = raw.rstrip()
        stripped = s.strip()
        if not stripped:
            lines.append(("blank", ""))
            continue
        if _collect_meta(stripped, meta):
            continue
        kind = _line_kind(s)
        # 在尚未遇到和弦／音符／段落標題前，第一行一般文字視為曲名（例如「晴天」）
        if not seen_music and not meta.get("title") and kind == "lyric":
            meta["title"] = stripped
            continue
        if kind in ("note", "chord", "section"):
            seen_music = True
        lines.append((kind, s))

    has_note = any(k == "note" for k, _ in lines)
    has_chord = any(k == "chord" for k, _ in lines)
    if not has_note and not has_chord:
        return None
    if not meta.get("title"):
        for kind, value in list(lines):
            if kind == "lyric" and value.strip():
                meta["title"] = value.strip()
                lines.remove((kind, value))
                break

    doc = ScoreDocument(
        title=str(meta.get("title") or title_default),
        lyricist=str(meta.get("lyricist", "")),
        composer=str(meta.get("composer", "")),
        key=str(meta.get("key") or "C"),
        timeSignature=str(meta.get("timeSignature") or "4/4"),
        tempo=int(meta.get("tempo", 90) or 90),
        engineMode="text-import",
        engineNote=f"由 {source_name} 原稿式文字導入（未經 OMR 辨識）",
        sourceName=source_name,
    )

    measures: list[ScoreMeasure] = []
    pending_section = ""
    i = 0
    while i < len(lines):
        kind, value = lines[i]
        if kind == "blank":
            i += 1
            continue
        if kind == "section":
            sec = value.strip().rstrip(":：").strip()
            if sec.lower() in ("fine", "d.c.", "dc", "d.s.", "ds", "coda") and measures:
                existing = measures[-1].marks.split() if measures[-1].marks else []
                if sec not in existing:
                    existing.append(sec)
                    measures[-1].marks = " ".join(existing)
            else:
                pending_section = sec
            i += 1
            continue

        new_measures: list[ScoreMeasure] = []
        if kind == "note":
            chord_line = ""
            if i > 0 and lines[i - 1][0] == "chord":
                chord_line = lines[i - 1][1]
            lyric_line = ""
            if i + 1 < len(lines) and lines[i + 1][0] == "lyric":
                lyric_line = lines[i + 1][1]
                i += 1
            new_measures = _split_line_into_measures(value, lyric_line, chord_line)
            i += 1
        elif kind == "chord":
            # 若下一行是簡譜數字行，交由 kind == "note" 分支一併處理（三行式）
            if i + 1 < len(lines) and lines[i + 1][0] == "note":
                i += 1
                continue
            # 若下一行是歌詞或注音唱名（和弦＋歌詞彈唱譜雙行一組）
            if i + 1 < len(lines) and lines[i + 1][0] == "lyric":
                lyric_line = lines[i + 1][1]
                new_measures = _split_chord_lyric_into_measures(value, lyric_line)
                i += 2
            else:
                # 獨立和弦小節行（如前奏／尾奏 `|Em Cmaj7 |G D/#F |`）
                new_measures = _split_chord_only_into_measures(value)
                i += 1
        elif kind == "lyric":
            zhuyin_notes = _extract_zhuyin_notes(value)
            if zhuyin_notes:
                new_measures = _split_line_into_measures(" ".join(zhuyin_notes), value, "")
            else:
                new_measures = _split_line_into_measures("", value, "")
            i += 1
        else:
            i += 1
            continue

        if new_measures and pending_section:
            new_measures[0].section = pending_section
            pending_section = ""
        measures.extend(new_measures)

    if not measures:
        return None
    doc.measures = measures
    for m in doc.measures:
        m.expand_beats()
    return doc.renumber()


def _split_chord_only_into_measures(chord_line: str) -> list[ScoreMeasure]:
    """解析獨立和弦行（如 `|Em Cmaj7 |G D/#F |` 或 `|G |Cadd9 |Am7 |Dsus4 D ||`）。"""
    raw = (chord_line or "").strip()
    if not raw:
        return []
    has_double_bar = raw.endswith("||")
    if "|" in raw:
        segments = [seg.strip() for seg in raw.split("|") if seg.strip()]
        out: list[ScoreMeasure] = []
        for idx, seg in enumerate(segments):
            chords = [_normalize_chord_token(t) for t in re.split(r"[\s\u3000]+", seg) if t]
            if not chords:
                continue
            out.append(ScoreMeasure(number=idx + 1, chordText=" ".join(chords)))
        if has_double_bar and out:
            out[-1].marks = "‖"
        return out
    tokens = [_normalize_chord_token(t) for t in re.split(r"[\s\u3000]+", raw) if t]
    step = 2 if len(tokens) >= 4 else 1
    return [
        ScoreMeasure(number=(j // step) + 1, chordText=" ".join(tokens[j : j + step]))
        for j in range(0, len(tokens), step)
    ]


def _split_chord_lyric_into_measures(chord_line: str, lyric_line: str) -> list[ScoreMeasure]:
    """解析吉他／彈唱譜的「上行和弦＋下行歌詞（或注音唱名）」雙行結構。"""
    if "|" in (chord_line or "") or "|" in (lyric_line or ""):
        norm_chords = re.sub(
            r"[^\s\u3000|]+",
            lambda m: _normalize_chord_token(m.group(0)),
            chord_line or "",
        )
        zhuyin = _extract_zhuyin_notes(lyric_line or "")
        note_str = " ".join(zhuyin) if zhuyin else ""
        return _split_line_into_measures(note_str, lyric_line, norm_chords)

    chord_items: list[dict] = []
    for m in re.finditer(r"[^\s\u3000]+", chord_line or ""):
        chord_items.append({
            "chord": _normalize_chord_token(m.group(0)),
            "start_col": _display_col(chord_line[: m.start()]),
            "end_col": _display_col(chord_line[: m.end()]),
        })

    if not chord_items:
        return _split_line_into_measures("", lyric_line, "")

    # 依和弦數量與水平間距切分為 1 或 2 小節（彈唱譜每行通常對應 2 小節）
    if len(chord_items) == 1:
        chord_groups = [chord_items]
    elif len(chord_items) == 2:
        chord_groups = [[chord_items[0]], [chord_items[1]]]
    elif len(chord_items) == 3:
        gap1 = chord_items[1]["start_col"] - chord_items[0]["end_col"]
        gap2 = chord_items[2]["start_col"] - chord_items[1]["end_col"]
        if gap1 > gap2:
            chord_groups = [[chord_items[0]], [chord_items[1], chord_items[2]]]
        else:
            chord_groups = [[chord_items[0], chord_items[1]], [chord_items[2]]]
    else:
        chord_groups = [chord_items[:2], chord_items[2:]]

    num_measures = len(chord_groups)
    zhuyin_notes = _extract_zhuyin_notes(lyric_line or "")
    if zhuyin_notes:
        zhuyin_syllables = [t.strip() for t in re.split(r"[\s\u3000]+", (lyric_line or "").strip()) if t.strip()]
        if num_measures == 1:
            return [
                ScoreMeasure(
                    number=1,
                    chordText=" ".join(c["chord"] for c in chord_groups[0]),
                    noteText=" ".join(zhuyin_notes),
                    lyricText=" ".join(zhuyin_syllables),
                )
            ]
        mid = (len(zhuyin_notes) + 1) // 2
        return [
            ScoreMeasure(
                number=1,
                chordText=" ".join(c["chord"] for c in chord_groups[0]),
                noteText=" ".join(zhuyin_notes[:mid]),
                lyricText=" ".join(zhuyin_syllables[:mid]),
            ),
            ScoreMeasure(
                number=2,
                chordText=" ".join(c["chord"] for c in chord_groups[1]),
                noteText=" ".join(zhuyin_notes[mid:]),
                lyricText=" ".join(zhuyin_syllables[mid:]),
            ),
        ]

    clauses: list[dict] = []
    for m in re.finditer(r"[^\s\u3000]+", lyric_line or ""):
        clauses.append({
            "text": m.group(0),
            "start_col": _display_col(lyric_line[: m.start()]),
        })

    if num_measures == 1:
        return [
            ScoreMeasure(
                number=1,
                chordText=" ".join(c["chord"] for c in chord_groups[0]),
                lyricText=" ".join(c["text"] for c in clauses),
            )
        ]

    if not clauses:
        lyric_parts = ["", ""]
    elif len(clauses) == 1:
        lyric_parts = [clauses[0]["text"], ""]
    elif len(clauses) == 2:
        lyric_parts = [clauses[0]["text"], clauses[1]["text"]]
    else:
        split_col = chord_groups[1][0]["start_col"]
        first_clauses: list[str] = []
        second_clauses: list[str] = []
        for idx, cl in enumerate(clauses):
            if idx == 0 or (idx < len(clauses) - 1 and cl["start_col"] < split_col - 4):
                first_clauses.append(cl["text"])
            else:
                second_clauses.append(cl["text"])
        lyric_parts = [" ".join(first_clauses), " ".join(second_clauses)]

    return [
        ScoreMeasure(
            number=1,
            chordText=" ".join(c["chord"] for c in chord_groups[0]),
            lyricText=lyric_parts[0],
        ),
        ScoreMeasure(
            number=2,
            chordText=" ".join(c["chord"] for c in chord_groups[1]),
            lyricText=lyric_parts[1],
        ),
    ]


def _split_line_into_measures(note_line: str, lyric_line: str, chord_line: str) -> list[ScoreMeasure]:
    """以 `|` 切小節；沒有小節線時每 4 個 token 視為一小節。"""
    def chunks(raw: str, is_lyric: bool) -> list[str]:
        raw = (raw or "").strip()
        if "|" in raw:
            return [c.strip() for c in raw.split("|") if c.strip()]
        if not raw:
            return []
        if is_lyric:
            items = split_lyrics(raw)
        else:
            items = [t for t in re.split(r"\s+", raw) if t]
        return [" ".join(items[j : j + 4]) if not is_lyric else "".join(items[j : j + 4])
                for j in range(0, len(items), 4)]

    norm_chord_line = re.sub(
        r"[^\s\u3000|]+",
        lambda m: _normalize_chord_token(m.group(0)),
        chord_line or "",
    )
    note_chunks = chunks(note_line, False)
    lyric_chunks = chunks(lyric_line, True)
    chord_chunks = chunks(norm_chord_line, False)
    # 和弦行常是「每小節一個和弦」的排列，若數量剛好等於小節數就一對一配
    chord_tokens = [t for t in re.split(r"[\s|]+", norm_chord_line.strip()) if t]
    if note_chunks and len(chord_tokens) == len(note_chunks):
        chord_chunks = chord_tokens
    count = max(len(note_chunks), len(lyric_chunks), len(chord_chunks))
    out = []
    for k in range(count):
        out.append(
            ScoreMeasure(
                number=k + 1,
                noteText=note_chunks[k] if k < len(note_chunks) else "",
                lyricText=lyric_chunks[k] if k < len(lyric_chunks) else "",
                chordText=chord_chunks[k] if k < len(chord_chunks) else "",
            )
        )
    return out
