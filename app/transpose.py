"""自由轉調（V3.00 新增）。

簡譜數字是相對調音階（1..7），轉調時：
* `doc.key` 改為目標調。
* 所有和弦符號依半音差移到目標調音階。
* 小節／拍位結構完全不動。
"""
from __future__ import annotations

import re

from .models import ScoreDocument
from .lilypond import transpose_key

_CH = re.compile(r"^(?P<acc1>[#b♯♭]*)(?P<root>[A-G])(?P<acc2>[#b♯♭]*)(?P<rest>.*?)(?P<bass>(?:/[#b♯♭]*[A-G][#b♯♭]{0,2})?)$")
_ACC_SHARP = 1
_ACC_FLAT = -1
_PC = {"C": 0, "D": 2, "E": 4, "F": 5, "G": 7, "A": 9, "B": 11}
_PC_NAMES = ["C", "C#", "D", "D#", "E", "F", "F#", "G", "G#", "A", "A#", "B"]
_FLAT_PC_NAMES = ["C", "Db", "D", "Eb", "E", "F", "Gb", "G", "Ab", "A", "Bb", "B"]
_FLAT_KEYS = {"F", "Bb", "Eb", "Ab", "Db", "Gb", "Dm", "Gm", "Cm", "Fm"}
_FLAT_ALIAS = {"Cb": "B", "Fb": "E", "Bb": "A#"}  # 取近似寫法

_SUFFIX_TABLE = {
    "maj7": "maj7", "M7": "M7", "m7": "m7", "m": "m", "min": "m",
    "dim": "dim", "dim7": "dim7", "aug": "aug", "sus2": "sus2",
    "sus4": "sus4", "sus": "sus", "add9": "add9", "6": "6", "7": "7",
    "9": "9", "11": "11", "13": "13", "": "",
}


def _shift_pc(pc: int, semi: int) -> int:
    return (pc + semi) % 12


def shift_chord(sym: str, semi: int, prefer_flats: bool = False) -> str:
    """單個和弦符號轉調（支援 F#m、Bb、D/F#、G/B、Em7/D 等根音後綴升降與轉位低音）。"""
    s = sym.strip().replace("♯", "#").replace("♭", "b")
    m = _CH.match(s)
    if not m:
        return sym
    acc1 = m.group("acc1") or ""
    acc2 = m.group("acc2") or ""
    rest = m.group("rest") or ""
    # 避免 m7b5 / B5 的 b5 被誤認為根音升降號
    if acc2 and rest.startswith("5"):
        rest = acc2 + rest
        acc2 = ""
    accs = acc1 + acc2
    start = _PC[m.group("root")] + _ACC_SHARP * accs.count("#") + _ACC_FLAT * accs.count("b")
    new_pc = _shift_pc(start, semi)
    names = _FLAT_PC_NAMES if prefer_flats else _PC_NAMES
    new_root = names[new_pc]
    bass = m.group("bass") or ""
    if bass:
        b = re.match(r"^/([#b]*)([A-G])([#b]*)$", bass)
        if b:
            b_accs = (b.group(1) or "") + (b.group(3) or "")
            bpc = _PC[b.group(2)] + _ACC_SHARP * b_accs.count("#") + _ACC_FLAT * b_accs.count("b")
            bass = "/" + names[_shift_pc(bpc, semi)]
    return new_root + rest + bass


def transpose_document(doc: ScoreDocument, target_key: str) -> dict:
    """回傳 {changed, warnings, chordCount}；原地修改 doc。"""
    src = doc.key
    semi = transpose_key(src, target_key)
    if semi == 0:
        return {"changed": False, "warnings": [], "chordCount": 0}
    prefer_flats = target_key.strip() in _FLAT_KEYS
    count = 0
    warnings: list[str] = []
    for m in doc.measures:
        chords = [t for t in re.split(r"\s+", m.chordText or "") if t]
        if chords:
            m.chordText = " ".join(shift_chord(c, semi, prefer_flats) for c in chords)
            count += len(chords)
        for b in m.beats:
            if b.chord:
                b.chord = shift_chord(b.chord, semi, prefer_flats)
    doc.key = target_key
    return {
        "changed": True,
        "fromKey": src,
        "toKey": target_key,
        "semi": semi,
        "chordCount": count,
        "warnings": warnings,
    }
