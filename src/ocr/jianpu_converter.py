import re
from typing import Any

# 西洋音名到半音階數 (以 C 為 0)
PITCH_SEMITONES = {
    "C": 0, "B#": 0,
    "C#": 1, "Db": 1,
    "C##": 2, "Dbb": 0,
    "D": 2,
    "D#": 3, "Eb": 3,
    "D##": 4, "Ebb": 2,
    "E": 4, "Fb": 4,
    "E#": 5, "F": 5,
    "F#": 6, "Gb": 6,
    "F##": 7, "Gbb": 5,
    "G": 7,
    "G#": 8, "Ab": 8,
    "G##": 9, "Abb": 7,
    "A": 9,
    "A#": 10, "Bb": 10,
    "A##": 11, "Bbb": 9,
    "B": 11, "Cb": 11, "Cbb": 10,
}

# 1=key 調號偏移半音
KEY_OFFSETS = {
    "C": 0, "1=C": 0,
    "C#": 1, "Db": 1, "1=Db": 1, "1=C#": 1,
    "D": 2, "1=D": 2,
    "D#": 3, "Eb": 3, "1=Eb": 3,
    "E": 4, "1=E": 4,
    "F": 5, "1=F": 5,
    "F#": 6, "Gb": 6, "1=F#": 6, "1=Gb": 6,
    "G": 7, "1=G": 7,
    "G#": 8, "Ab": 8, "1=Ab": 8,
    "A": 9, "1=A": 9,
    "A#": 10, "Bb": 10, "1=Bb": 10,
    "B": 11, "1=B": 11,
}

# 半音階階數 (0~11) 相對於大調主音的簡譜數字與臨時升降號
SEMITONE_TO_JIANPU = {
    0: ("1", ""),
    1: ("1", "#"),   # 升1 或 降2
    2: ("2", ""),
    3: ("3", "b"),   # 降3
    4: ("3", ""),
    5: ("4", ""),
    6: ("4", "#"),   # 升4
    7: ("5", ""),
    8: ("5", "#"),   # 升5 或 降6
    9: ("6", ""),
    10: ("7", "b"),  # 降7
    11: ("7", ""),
}

# 時值對應四分音符拍數 (Quarter = 1.0)
DURATION_BEATS = {
    "whole": 4.0,
    "half": 2.0,
    "quarter": 1.0,
    "eighth": 0.5,
    "16th": 0.25,
    "32nd": 0.125,
}


def parse_pitch(pitch_str: str | None) -> tuple[str, str, int] | None:
    """解析標準音名，如 'C4', 'F#5', 'Bb3', 'F##5', 'Dbb2' -> (step, accidental, octave)

    支援單升/降 (#, b) 與雙升/降 (##, bb)。
    """
    if not pitch_str:
        return None
    # 修正正則：支援 0-2 個臨時記號字元 (#, b, ♯, ♭)
    match = re.match(r"^([A-Ga-g])([#bB♯♭]{0,2})(\d)?$", pitch_str.strip())
    if not match:
        return None
    step = match.group(1).upper()
    acc = match.group(2)
    # 正規化臨時記號
    acc = acc.replace("♯", "#").replace("♭", "b").replace("B", "b")
    # 限制最多雙升/雙降
    if acc.count("#") > 2 or acc.count("b") > 2:
        return None
    octave = int(match.group(3)) if match.group(3) else 4
    return step, acc, octave


def pitch_to_jianpu(pitch_str: str | None, key: str = "C") -> str:
    """將單一西洋音名轉為簡譜音符字串 (包含高低音點)，如 'C4' -> '1', 'G4' -> '5', 'C5' -> '1̇'"""
    if not pitch_str:
        return "0"
    parsed = parse_pitch(pitch_str)
    if not parsed:
        return "?"
    step, acc, octave = parsed
    note_name = f"{step}{acc}"
    if note_name not in PITCH_SEMITONES:
        return "?"

    note_semi = PITCH_SEMITONES[note_name]
    key_semi = KEY_OFFSETS.get(key, 0)

    # 計算在大調音階中的相對半音
    diff = (note_semi - key_semi) % 12
    num_str, accidental = SEMITONE_TO_JIANPU.get(diff, ("?", ""))

    # 八度計算：以中央八度 octave 4 為基準
    # 結合調號微調八度
    octave_offset = octave - 4
    if note_semi < key_semi:
        # 當音高低於調號主音時，八度調整
        octave_offset -= 1

    # 高音點（上方結合點 U+0307）與低音點（下方結合點 U+0323）
    core = f"{accidental}{num_str}"
    if octave_offset == 1:
        core = f"{core}\u0307"       # 高八度
    elif octave_offset >= 2:
        core = f"{core}\u0308"       # 倍高八度 (雙點)
    elif octave_offset == -1:
        core = f"{core}\u0323"       # 低八度
    elif octave_offset <= -2:
        core = f"{core}\u0324"       # 倍低八度 (雙點)

    return core


def symbol_to_jianpu_notation(sym: Any, key: str = "C") -> str:
    """轉換單一符號為包含時值的簡譜格式，支援 Symbol 物件或 dict"""
    if isinstance(sym, dict):
        stype = (sym.get("type") or "note").lower()
        duration = (sym.get("duration") or "quarter").lower()
        pitch = sym.get("pitch")
    else:
        stype = (getattr(sym, "type", "note") or "note").lower()
        duration = (getattr(sym, "duration", "quarter") or "quarter").lower()
        pitch = getattr(sym, "pitch", None)

    if stype == "rest" or not pitch:
        base = "0"
    else:
        base = pitch_to_jianpu(pitch, key=key)

    if duration == "whole":
        return f"{base} - - -"
    elif duration == "half":
        return f"{base} -"
    elif duration == "quarter":
        return base
    elif duration == "eighth":
        return f"{base}_"
    elif duration == "16th":
        return f"{base}="
    elif duration == "32nd":
        return f"{base}≡"
    return base


def symbols_to_jianpu_text(
    symbols: list[Any],
    title: str = "ScoreOCR Jianpu Score",
    key: str = "C",
    meter: str = "4/4",
) -> str:
    """將符號清單編排為標準格式的簡譜純文字譜 (含調號、拍號、小節線與換行)"""
    lines = []
    lines.append(f"《{title}》")
    lines.append(f"1={key}   {meter}\n")

    def get_sym_val(s: Any, field: str, default: Any = 0) -> Any:
        if isinstance(s, dict):
            return s.get(field, default)
        return getattr(s, field, default)

    # 按讀取順序排序 (y 座標分行，x 座標分列)
    sorted_syms = sorted(symbols, key=lambda s: (get_sym_val(s, "y", 0) // 40, get_sym_val(s, "x", 0)))

    measures = []
    current_measure = []
    current_beats = 0.0
    beats_per_measure = 4.0
    if meter == "3/4":
        beats_per_measure = 3.0
    elif meter == "2/4":
        beats_per_measure = 2.0
    elif meter == "6/8":
        beats_per_measure = 3.0

    for sym in sorted_syms:
        stype = get_sym_val(sym, "type", "note")
        # 跳過非音符/休止符（例如純小節線/譜號）
        if (stype or "").lower() in ("barline", "clef"):
            continue

        jp = symbol_to_jianpu_notation(sym, key=key)
        dur = (get_sym_val(sym, "duration", "quarter") or "quarter").lower()
        beats = DURATION_BEATS.get(dur, 1.0)

        current_measure.append(jp)
        current_beats += beats

        if current_beats >= beats_per_measure - 0.01:
            measures.append("  ".join(current_measure))
            current_measure = []
            current_beats = 0.0

    if current_measure:
        measures.append("  ".join(current_measure))

    # 每 4 小節一行
    chunk_size = 4
    for i in range(0, len(measures), chunk_size):
        chunk = measures[i : i + chunk_size]
        row_str = "|  " + "  |  ".join(chunk) + "  |"
        if i + chunk_size >= len(measures):
            row_str += "|"  # 結尾終止線
        lines.append(row_str)

    return "\n".join(lines)
