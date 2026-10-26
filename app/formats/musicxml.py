"""簡譜（numbered notation）→ MusicXML 4.0 partwise 生成器。

規劃書 5.1／10.1：輸出單一合法 MusicXML，供 MuseScore／Finale／Dorico 交換。
簡譜 token 文法：
    [#|b]* digit(0-7) ['|,]* [_]* [.]*   例：1 #4 5' 3, 6_ 2.
    `0`  → 休止符
    `-`  → 延長前一音一拍（以 tie 表示）
和弦文字以 <harmony> 輸出，歌詞以 <lyric> 輸出。
"""
from __future__ import annotations

import re
from xml.etree import ElementTree as ET
from xml.dom import minidom

from ..models import NOTE_TOKEN, ScoreDocument, ScoreMeasure, split_lyrics

DIVISIONS = 4  # quarter = 4 → eighth=2, 16th=1

MAJOR_STEPS = [0, 2, 4, 5, 7, 9, 11]
PITCH_CLASS = {"C": 0, "D": 2, "E": 4, "F": 5, "G": 7, "A": 9, "B": 11}
SHARP_NAMES = [
    ("C", 0), ("C", 1), ("D", 0), ("D", 1), ("E", 0), ("F", 0),
    ("F", 1), ("G", 0), ("G", 1), ("A", 0), ("A", 1), ("B", 0),
]
FLAT_NAMES = [
    ("C", 0), ("D", -1), ("D", 0), ("E", -1), ("E", 0), ("F", 0),
    ("G", -1), ("G", 0), ("A", -1), ("A", 0), ("B", -1), ("B", 0),
]
FIFTHS = {
    "C": 0, "G": 1, "D": 2, "A": 3, "E": 4, "B": 5, "F#": 6, "C#": 7,
    "F": -1, "Bb": -2, "Eb": -3, "Ab": -4, "Db": -5, "Gb": -6, "Cb": -7,
}
DURATION_UNITS = {
    "whole": DIVISIONS * 4,
    "half": DIVISIONS * 2,
    "quarter": DIVISIONS,
    "eighth": DIVISIONS // 2,
    "16th": max(1, DIVISIONS // 4),
    "32nd": max(1, DIVISIONS // 8),
}
CHORD_RE = re.compile(
    r"^\(?([A-G])([#b]?)((?:maj|min|m|M|dim|aug|sus|add|no|[0-9+\-])+)?(?:/([#b]?[A-G][#b]?))?\)?$"
)


def normalize_key(key: str) -> str:
    """接受 `C`、`1=C`、`Key of G`、`bB` 等寫法。"""
    k = (key or "C").strip()
    if "=" in k:
        k = k.split("=", 1)[1].strip()
    k = k.replace("大調", "").replace("調", "").strip()
    m = re.match(r"^([b#]?)([A-Ga-g])([b#]?)", k)
    if not m:
        return "C"
    pre, letter, post = m.groups()
    acc = post or pre or ""
    return letter.upper() + acc.replace("＃", "#")


def key_fifths(key: str) -> int:
    return FIFTHS.get(normalize_key(key), 0)


def _tonic_pc(key: str) -> int:
    k = normalize_key(key)
    pc = PITCH_CLASS.get(k[0], 0)
    if len(k) > 1:
        pc += 1 if k[1] == "#" else -1
    return pc % 12


def parse_time_signature(sig: str) -> tuple[int, int]:
    m = re.match(r"^\s*(\d{1,2})\s*/\s*(\d{1,2})\s*$", sig or "")
    if not m:
        return 4, 4
    beats, beat_type = int(m.group(1)), int(m.group(2))
    return max(1, beats), beat_type if beat_type in (1, 2, 4, 8, 16) else 4


def token_to_pitch(token: str, key: str) -> dict | None:
    """回傳 {step, alter, octave, duration_name, dots} 或 None（休止／不可解析）。"""
    m = NOTE_TOKEN.match(token or "")
    if not m:
        return None
    acc_raw, degree, octave_raw, halvings, dots = m.groups()
    if degree == "0":
        return {"rest": True, "duration_name": _dur_name(halvings), "dots": len(dots)}
    alter = acc_raw.count("#") + acc_raw.count("\u266f") - acc_raw.count("b") - acc_raw.count("\u266d")
    octave_shift = (
        octave_raw.count("'")
        + octave_raw.count("\u2019")
        + octave_raw.count("\u0307")
        - octave_raw.count(",")
        - octave_raw.count("\u0323")
    )
    semitone = MAJOR_STEPS[int(degree) - 1] + alter
    midi = 60 + _tonic_pc(key) + semitone + 12 * octave_shift
    names = FLAT_NAMES if key_fifths(key) < 0 else SHARP_NAMES
    step, alt = names[midi % 12]
    return {
        "rest": False,
        "step": step,
        "alter": alt,
        "octave": midi // 12 - 1,
        "duration_name": _dur_name(halvings),
        "dots": len(dots),
    }


def _dur_name(halvings: str) -> str:
    return {0: "quarter", 1: "eighth", 2: "16th", 3: "32nd"}.get(len(halvings), "quarter")


def _units(duration_name: str, dots: int) -> int:
    base = DURATION_UNITS.get(duration_name, DIVISIONS)
    total = base
    add = base
    for _ in range(dots):
        add //= 2
        total += max(1, add)
    return max(1, total)


def _harmony(parent: ET.Element, chord: str) -> None:
    m = CHORD_RE.match((chord or "").strip())
    if not m:
        return
    root, acc, quality, bass = m.groups()
    harmony = ET.SubElement(parent, "harmony", {"print-frame": "no"})
    rt = ET.SubElement(harmony, "root")
    ET.SubElement(rt, "root-step").text = root
    if acc:
        ET.SubElement(rt, "root-alter").text = "1" if acc == "#" else "-1"
    kind_map = {
        None: "major", "maj": "major", "M7": "major-seventh", "maj7": "major-seventh",
        "m": "minor", "min": "minor", "m7": "minor-seventh", "min7": "minor-seventh",
        "7": "dominant", "6": "major-sixth", "9": "dominant-ninth", "11": "dominant-11th",
        "13": "dominant-13th", "dim": "diminished", "dim7": "diminished-seventh",
        "aug": "augmented", "sus": "suspended-fourth", "sus4": "suspended-fourth",
        "sus2": "suspended-second", "add9": "major",
    }
    ET.SubElement(harmony, "kind", {"text": (chord or "").strip()}).text = kind_map.get(quality, "other")
    if bass:
        if bass[0] in ("#", "b") and len(bass) > 1:
            bass = bass[1:] + bass[0]
        bs = ET.SubElement(harmony, "bass")
        ET.SubElement(bs, "bass-step").text = bass[0]
        if len(bass) > 1:
            ET.SubElement(bs, "bass-alter").text = "1" if bass[1] == "#" else "-1"


def _add_measure(part: ET.Element, measure: ScoreMeasure, doc: ScoreDocument, first: bool) -> list[str]:
    warnings: list[str] = []
    el = ET.SubElement(part, "measure", {"number": str(measure.number)})
    beats_n, beat_type = parse_time_signature(doc.timeSignature)

    if first:
        attrs = ET.SubElement(el, "attributes")
        ET.SubElement(attrs, "divisions").text = str(DIVISIONS)
        keyel = ET.SubElement(attrs, "key")
        ET.SubElement(keyel, "fifths").text = str(key_fifths(doc.key))
        time_el = ET.SubElement(attrs, "time")
        ET.SubElement(time_el, "beats").text = str(beats_n)
        ET.SubElement(time_el, "beat-type").text = str(beat_type)
        clef = ET.SubElement(attrs, "clef")
        ET.SubElement(clef, "sign").text = "G"
        ET.SubElement(clef, "line").text = "2"
        direction = ET.SubElement(el, "direction", {"placement": "above"})
        dtype = ET.SubElement(direction, "direction-type")
        metronome = ET.SubElement(dtype, "metronome")
        ET.SubElement(metronome, "beat-unit").text = "quarter"
        ET.SubElement(metronome, "per-minute").text = str(doc.tempo or 90)
        ET.SubElement(direction, "sound", {"tempo": str(doc.tempo or 90)})

    beats = measure.beats or measure.expand_beats()
    if measure.linePosition == 1 and measure.number > 1:
        # 每三小節一行：在行首小節標記換行，讓 MuseScore 依原稿版面斷行
        pr = ET.SubElement(el, "print", {"new-system": "yes"})
        pr.set("new-system", "yes")

    last_note_el: ET.Element | None = None
    last_chord_text = ""
    empty = True
    # 第 2～4 行歌詞：逐詞切分後依拍序對齊到同一音符（lyric number=2/3/4）
    extra_lyrics = {
        2: split_lyrics(measure.lyricText2),
        3: split_lyrics(measure.lyricText3),
        4: split_lyrics(measure.lyricText4),
    }

    for b in beats:
        raw_note = (b.note or "").strip()
        # P0-1: 同拍多音符 — 拆分處理
        note_tokens = raw_note.split() if raw_note else []
        if len(note_tokens) == 0:
            continue
        if len(note_tokens) > 1:
            # 多音符: 逐一建立 note element (同拍和弦)
            for _ni, _nt in enumerate(note_tokens):
                _pitch = token_to_pitch(_nt, doc.key)
                if _pitch is None:
                    continue
                _note_el = ET.SubElement(el, "note")
                if _ni > 0:
                    ET.SubElement(_note_el, "chord")
                if _pitch.get("rest"):
                    ET.SubElement(_note_el, "rest")
                else:
                    _p = ET.SubElement(_note_el, "pitch")
                    ET.SubElement(_p, "step").text = _pitch["step"]
                    if _pitch["alter"]:
                        ET.SubElement(_p, "alter").text = str(_pitch["alter"])
                    ET.SubElement(_p, "octave").text = str(_pitch["octave"])
                _units_val = _units(_pitch["duration_name"], _pitch["dots"])
                ET.SubElement(_note_el, "duration").text = str(_units_val)
                ET.SubElement(_note_el, "voice").text = "1"
                ET.SubElement(_note_el, "type").text = _pitch["duration_name"]
                for _ in range(_pitch["dots"]):
                    ET.SubElement(_note_el, "dot")
            continue
        token = note_tokens[0]
        empty = False
        if token in {"-", "\u2014", "\u2013"}:
            if last_note_el is None:
                warnings.append(f"小節 {measure.number}：延長線 '-' 前面沒有音符，已忽略。")
                continue
            dur_el = last_note_el.find("duration")
            if dur_el is not None:
                dur_el.text = str(int(dur_el.text or DIVISIONS) + DIVISIONS)
                type_el = last_note_el.find("type")
                total = int(dur_el.text)
                if type_el is not None:
                    type_el.text = _type_from_units(total)
                _fix_dots(last_note_el, total)
            continue

        pitch = token_to_pitch(token, doc.key)
        if pitch is None:
            warnings.append(f"小節 {measure.number} 第 {b.beat} 拍：無法解析簡譜符號 '{token}'，已跳過。")
            continue

        chord_text = (b.chord or "").strip()
        if chord_text and chord_text != last_chord_text:
            _harmony(el, chord_text)
            last_chord_text = chord_text

        note = ET.SubElement(el, "note")
        units = _units(pitch["duration_name"], pitch["dots"])
        if pitch.get("rest"):
            ET.SubElement(note, "rest")
        else:
            p = ET.SubElement(note, "pitch")
            ET.SubElement(p, "step").text = pitch["step"]
            if pitch["alter"]:
                ET.SubElement(p, "alter").text = str(pitch["alter"])
            ET.SubElement(p, "octave").text = str(pitch["octave"])
        ET.SubElement(note, "duration").text = str(units)
        ET.SubElement(note, "voice").text = "1"
        ET.SubElement(note, "type").text = pitch["duration_name"]
        for _ in range(pitch["dots"]):
            ET.SubElement(note, "dot")
        if b.confidence < 0.7:
            notations = ET.SubElement(note, "notations")
            tech = ET.SubElement(notations, "technical")
            ET.SubElement(tech, "other-technical").text = f"low-confidence:{b.confidence:.2f}"
        lyric_text = (b.lyric or "").strip()
        if lyric_text and not pitch.get("rest"):
            lyric = ET.SubElement(note, "lyric", {"number": "1"})
            ET.SubElement(lyric, "syllabic").text = "single"
            ET.SubElement(lyric, "text").text = lyric_text
        # verse 2/3/4：同一音符依拍序（b.beat-1）對齊第 2～4 行歌詞
        for num, words in extra_lyrics.items():
            idx = (b.beat or 1) - 1
            word = words[idx] if idx < len(words) else ""
            if word and not pitch.get("rest"):
                l2 = ET.SubElement(note, "lyric", {"number": str(num)})
                ET.SubElement(l2, "syllabic").text = "single"
                ET.SubElement(l2, "text").text = word
        last_note_el = note

    if empty:
        for ch_tok in (measure.chordText or "").split():
            if ch_tok and ch_tok != last_chord_text:
                _harmony(el, ch_tok)
                last_chord_text = ch_tok
        note = ET.SubElement(el, "note")
        ET.SubElement(note, "rest", {"measure": "yes"})
        ET.SubElement(note, "duration").text = str(DIVISIONS * beats_n * 4 // beat_type)
        ET.SubElement(note, "voice").text = "1"
        if (measure.lyricText or "").strip():
            lyric = ET.SubElement(note, "lyric", {"number": "1"})
            ET.SubElement(lyric, "syllabic").text = "single"
            ET.SubElement(lyric, "text").text = measure.lyricText.strip()
    return warnings


def _type_from_units(units: int) -> str:
    table = [
        (DIVISIONS * 4, "whole"), (DIVISIONS * 3, "half"), (DIVISIONS * 2, "half"),
        (DIVISIONS + DIVISIONS // 2, "quarter"), (DIVISIONS, "quarter"),
        (max(1, DIVISIONS // 2), "eighth"), (max(1, DIVISIONS // 4), "16th"),
    ]
    for u, name in table:
        if units >= u:
            return name
    return "16th"


def _fix_dots(note_el: ET.Element, units: int) -> None:
    for dot in note_el.findall("dot"):
        note_el.remove(dot)
    if units in (DIVISIONS * 3, DIVISIONS + DIVISIONS // 2):
        idx = list(note_el).index(note_el.find("type")) + 1
        note_el.insert(idx, ET.Element("dot"))


def build_musicxml(doc: ScoreDocument) -> tuple[str, list[str]]:
    root = ET.Element("score-partwise", {"version": "4.0"})
    work = ET.SubElement(root, "work")
    ET.SubElement(work, "work-title").text = doc.title or "未命名樂譜"

    ident = ET.SubElement(root, "identification")
    if doc.composer:
        ET.SubElement(ident, "creator", {"type": "composer"}).text = doc.composer
    if doc.lyricist:
        ET.SubElement(ident, "creator", {"type": "lyricist"}).text = doc.lyricist
    enc = ET.SubElement(ident, "encoding")
    ET.SubElement(enc, "software").text = "SheetMusicOMR 1.0 (local)"
    ET.SubElement(enc, "encoding-date").text = (doc.updatedAt or "")[:10]

    part_list = ET.SubElement(root, "part-list")
    sp = ET.SubElement(part_list, "score-part", {"id": "P1"})
    ET.SubElement(sp, "part-name").text = "Melody"
    ET.SubElement(sp, "part-abbreviation").text = "Mel."

    part = ET.SubElement(root, "part", {"id": "P1"})
    warnings: list[str] = []
    measures = doc.measures or [ScoreMeasure()]
    for i, measure in enumerate(measures):
        warnings.extend(_add_measure(part, measure, doc, first=(i == 0)))

    raw = ET.tostring(root, encoding="unicode")
    pretty = minidom.parseString(raw).toprettyxml(indent="  ")
    body = "\n".join(line for line in pretty.split("\n")[1:] if line.strip())
    # 刻意不輸出外部 DTD DOCTYPE：避免任何解析器嘗試連線 musicxml.org，
    # 以符合「全程本地、斷網可運行」的離線約束。MusicXML 4.0 允許省略 DOCTYPE。
    header = '<?xml version="1.0" encoding="UTF-8"?>\n'

    return header + body + "\n", warnings


def _misc_field(name: str, value: str) -> ET.Element:
    el = ET.Element("miscellaneous-field", {"name": name})
    el.text = value
    return el


def document_to_musicxml(doc: ScoreDocument) -> str:
    return build_musicxml(doc)[0]
