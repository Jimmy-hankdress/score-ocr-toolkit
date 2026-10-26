"""LilyPond 排版引擎整合（V3.00 新增）。

把 ScoreDocument 轉為 LilyPond .ly 文字檔，調用本機
`D:\\lilypond-2.26.0\\bin\\lilypond.exe` 編譯出 PDF 與 MIDI。

簡譜數字（1..7）是「相對於調性」的音級：
* 數字依目標調的大音階換算成實際音名（1=G 調時，1→G、2→A…）。
* 每個小節的總時值自動補齊（不足補休止符），避免 bar check 失敗。
* 和弦以獨立 ChordNames 對齊，品質記號轉成 LilyPond `root:quality` 形式。
* 歌詞以 \\addlyrics 順序對齊。

全程本地：只調命令列；LilyPond 有警告（rc=1）但 PDF 有產出時仍視為成功。
"""
from __future__ import annotations

import re
import shutil
import subprocess
from pathlib import Path

from .models import ScoreDocument, split_lyrics
from .formats.musicxml import NOTE_TOKEN, normalize_key

# LilyPond 可執行檔的已知位置（使用者已下載到 D:\lilypond-2.26.0）
_LILY_CANDIDATES = [
    Path("D:/lilypond-2.26.0/bin/lilypond.exe"),
    Path("C:/Program Files/LilyPond/bin/lilypond.exe"),
]


def find_lilypond() -> Path | None:
    """依順序找 LilyPond 執行檔：先固定路徑、再找 PATH。"""
    for p in _LILY_CANDIDATES:
        if p.exists():
            return p
    exe = shutil.which("lilypond")
    if exe:
        return Path(exe)
    return None


# 十二個音級（C=0 起算）
_PC_MAP = {
    "C": 0, "C#": 1, "Db": 1, "D": 2, "D#": 3, "Eb": 3, "E": 4, "F": 5,
    "F#": 6, "Gb": 6, "G": 7, "G#": 8, "Ab": 8, "A": 9, "A#": 10, "Bb": 10, "B": 11,
}


def transpose_key(src: str, dst: str) -> int:
    """回傳由 src 調到 dst 調的半音差（簡譜數字不變、音高位移）。"""
    a = normalize_key(src)
    b = normalize_key(dst)
    if a == b:
        return 0
    s = _PC_MAP.get(a, 0)
    t = _PC_MAP.get(b, 0)
    diff = (t - s) % 12
    return diff - 12 if diff > 6 else diff


# 各調大音階的 7 個 LilyPond 音名（度數 1..7）
_KEY_SCALES: dict[str, list[str]] = {
    "C":  ["c", "d", "e", "f", "g", "a", "b"],
    "G":  ["g", "a", "b", "c", "d", "e", "fis"],
    "D":  ["d", "e", "fis", "g", "a", "b", "cisis"],
    "A":  ["a", "b", "cisis", "d", "e", "fis", "gis"],
    "E":  ["e", "fis", "gis", "a", "b", "cisis", "dis"],
    "B":  ["b", "cisis", "dis", "e", "fis", "gis", "ais"],
    "F":  ["f", "g", "a", "bes", "c", "d", "e"],
    "Bb": ["bes", "c", "d", "es", "f", "g", "a"],
    "Eb": ["es", "f", "g", "as", "bes", "c", "d"],
    "Ab": ["as", "bes", "c", "des", "es", "f", "g"],
    "Db": ["des", "es", "f", "ges", "as", "bes", "c"],
    "Cb": ["bes", "es", "f", "ges", "as", "bes", "c"],
}
# C#/F# 等升調音階
_KEY_SCALES["C#"] = ["cisis", "dis", "eisis", "fisis", "gisis", "ais", "bis"]
_KEY_SCALES["F#"] = ["fisis", "gisis", "ais", "bisis", "cisis", "dis", "eisis"]


def _scale_for(key: str) -> list[str]:
    return _KEY_SCALES.get(normalize_key(key), _KEY_SCALES["C"])


def _lily_key(key: str) -> str:
    r"""調性 → `\key X \major`。"""
    k = normalize_key(key)
    letter = {
        "C": "c", "G": "g", "D": "d", "A": "a", "E": "e", "F": "f",
        "F#": "fis", "C#": "cisis", "Bb": "bes", "Eb": "es",
        "Ab": "ges", "Db": "des",
    }.get(k, "c")
    return f"{letter} \\major"


# ── 和弦記號 ────────────────────────────────────────────

_QUALITY_MAP = {
    "": "", "maj": "", "": "",
    "m": "m", "min": "m",
    "m7": "m7", "min7": "m7",
    "dim": "dim", "dim7": "dim7",
    "aug": "aug",
    "maj7": "maj7", "M7": "maj7",
    "sus": "sus4", "sus2": "sus2", "sus4": "sus4",
    "add9": "add9",
    "6": "6", "7": "7", "9": "9", "11": "11", "13": "13",
}


def _lily_note_name(letter: str, sharp: bool = False) -> str:
    base = "b" if letter.upper() == "B" else letter.lower()
    if sharp:
        base = {"b": "h"}.get(base, base + "is")
    return base


def _lily_chord(sym: str, dur: str) -> str | None:
    """`Am7`、`D/F#` → LilyPond `a:m74` 形式：root＋時值＋:品質＋/bass。失敗回 None。"""
    m = re.match(
        r"^([A-Ga-g])([#b]?)([a-z0-9]*)(?:/([A-Ga-g])([#b]?))?$",
        sym.strip(),
    )
    if not m:
        return None
    root, acc, qual, bass, bass_acc = m.groups()
    out = _lily_note_name(root, acc == "#")
    out += dur  # 時值跟根音（g4）
    q = _QUALITY_MAP.get((qual or "").strip())
    if q is None:
        return None
    if q:
        out += f":{q}"
    if bass:
        out += f"/{_lily_note_name(bass, bass_acc == '#')}"
    return out


# ── 時值工具 ────────────────────────────────────────────

_DUR_VALUES = [(4, "1"), (2, "2"), (1, "4"), (0.5, "8"), (0.25, "16")]
_DOTTED = {3.0: "2.", 1.5: "4.", 0.75: "8.", 0.375: "16."}


def _note_beats(halvings: int, dots: int) -> float:
    base = 1.0 / (2 ** max(0, min(halvings, 3)))
    return base * (1.5 ** max(0, dots))


def _lily_dur(quarter_beats: float, dotted_ok: bool = True) -> str:
    for val, name in _DUR_VALUES:
        if quarter_beats >= val - 1e-9:
            if abs(quarter_beats - val) < 1e-9:
                return name
            if dotted_ok and quarter_beats in _DOTTED:
                return _DOTTED[quarter_beats]
            return name
    return "16"


def _rest_tokens(quarter_beats: float) -> list[str]:
    """剩餘拍數 → 休止記號串（含附點）。"""
    out: list[str] = []
    remaining = round(quarter_beats, 6)
    if remaining in _DOTTED:
        return [f"r{_DOTTED[remaining]}"]
    for val, name in _DUR_VALUES:
        while remaining >= val - 1e-9:
            out.append(f"r{name}")
            remaining = round(remaining - val, 6)
    if remaining > 1e-9:
        six = int(round(remaining / 0.25))
        out.extend(["r16"] * max(1, six))
    return out or ["r1"]


# ── 音符記號 ────────────────────────────────────────────

def _note_to_lily(token: str, scale: list[str]) -> tuple[str | None, float]:
    """簡譜 token → (LilyPond 音符記號, 四分拍數)。

    支援：數字 1-7、0 休止、`'`/`,` 八度、`_` 減半、`.` 附點、
    前綴 `#`/`b` 升降、`-` 增時線（視為與前音相同的延長拍）。
    """
    tok = (token or "").strip()
    if not tok:
        return None, 0.0
    # 純增時線「-」：視為一拍休止（LilyPond 沒有真正的「延長」，以最穩妥方式處理）
    if tok == "-":
        return "r4", 1.0
    # 附點前綴的數字：如 `2.` 已被 NOTE_TOKEN 涵蓋
    m = NOTE_TOKEN.match(tok)
    if not m:
        return None, 0.0
    acc_raw, degree, octave_raw, halvings, dots = m.groups()
    beats = _note_beats(len(halvings), len(dots))
    if degree == "0":
        return " ".join(_rest_tokens(beats)), beats
    letter = scale[int(degree) - 1]
    alter = (
        acc_raw.count("#") + acc_raw.count("\u266f")
        - acc_raw.count("b") - acc_raw.count("\u266d")
    )
    if alter > 0:
        letter += "is" * min(alter, 2)
    elif alter < 0:
        letter += "es" * min(-alter, 2)
    o = octave_raw.count("'") + octave_raw.count("\u2019") - octave_raw.count(",")
    if o > 0:
        letter += "'" * o
    elif o < 0:
        letter += "," * -o
    return f"{letter}{_lily_dur(beats)}", beats


# ── 主轉換 ──────────────────────────────────────────────

def document_to_ly(doc: ScoreDocument) -> tuple[str, list[str]]:
    """ScoreDocument → LilyPond 文字檔內容。"""
    warnings: list[str] = []
    m = re.match(r"^\s*(\d{1,2})\s*/\s*(\d{1,2})\s*$", doc.timeSignature or "")
    num, den = (int(m.group(1)), int(m.group(2))) if m else (4, 4)
    measure_beats = num * 4.0 / max(den, 1)
    scale = _scale_for(doc.key)

    staff_lines: list[str] = []
    chord_lines: list[str] = []
    lyric_lines: list[str] = []

    for measure in doc.measures or [ScoreMeasure()]:
        notes = [t for t in re.split(r"\s+", measure.noteText or "") if t]
        chords = [t for t in re.split(r"\s+", measure.chordText or "") if t]
        # 拍位層（含時值/八度記號）優先
        beat_notes = [b.note for b in measure.beats if b.note] if measure.beats else []
        tokens = beat_notes if len(beat_notes) >= len(notes) else notes

        events: list[str] = []
        used = 0.0
        for tok in tokens:
            ev, beats = _note_to_lily(tok, scale)
            if ev is None:
                warnings.append(f"小節 {measure.number}：token 「{tok}」無法解析")
                ev, beats = "r4", 1.0
            events.append(ev)
            used = round(used + beats, 6)
            if used > measure_beats + 1e-9:
                warnings.append(f"小節 {measure.number}：時值超過拍號，採用溢出記號")
                break
        if used < measure_beats - 1e-9:
            events.extend(_rest_tokens(measure_beats - used))
        elif not events:
            events = _rest_tokens(measure_beats)
        staff_lines.append(" ".join(events))

        # 和弦對齊：依拍位分配；和弦數 != 音符數時均勻切小節
        c_ev: list[str] = []
        if chords:
            per = measure_beats / len(chords)
            for i, ch in enumerate(chords):
                dur = _lily_dur(min(per, measure_beats - per * i), dotted_ok=True)
                # 空和弦：用 s（silence）讓 ChordNames 有事件與 Staff 時值對齊，不顯示任何符號
                if not (ch or "").strip():
                    c_ev.append(f"s{_lily_dur(measure_beats)}")
                    continue
                name = _lily_chord(ch, dur)
                if name is None:
                    warnings.append(f"小節 {measure.number}：和弦 「{ch}」無法解析")
                    c_ev.append(f"s{_lily_dur(measure_beats)}")
                else:
                    c_ev.append(name)
        else:
            # 空和弦小節：整小節靜默（s + 整小節時值），讓 ChordNames 與 Staff 時值對齊
            c_ev = [f"s{_lily_dur(measure_beats)}"]
        chord_lines.append(" ".join(c_ev))

        ly = split_lyrics(measure.lyricText or "")
        lyric_lines.append(" ".join(ly) if ly else " ")

    key_ly = _lily_key(doc.key)
    tempo = int(doc.tempo or 90)
    parts = [
        '\\version "2.26.0"',
        "\\score {",
        "  <<",
        "    \\new ChordNames {",
        "      \\chordmode {",
    ]
    for cl in chord_lines:
        parts.append(f"        {cl}")
    parts.extend([
        "      }",
        "    }",
        "    \\new Staff {",
        "      \\time " + f"{num}/{den}",
        f"      \\key {key_ly}",
        f"      \\tempo 4={tempo}",
        "      \\clef treble",
        "      \\relative c'' {",
    ])
    for sl in staff_lines:
        parts.append(f"        {sl}")
    parts.extend([
        "      }",
        "    }",
        "    \\addlyrics {",
    ])
    for ll in lyric_lines:
        parts.append(f"      {ll}")
    parts.extend([
        "    }",
        "  >>",
        "  \\layout { }",
        "  \\midi { }",
        "}",
    ])
    return "\n".join(parts), warnings


# ── 編譯 ────────────────────────────────────────────────

def _compile_ly(ly_path: Path, out_dir: Path, cleanup_ly: bool) -> dict:
    """共用的 LilyPond 編譯核心：跑 lilypond.exe、收集 PDF/MIDI、回傳結果 dict。"""
    exe = find_lilypond()
    result = {"pdf": None, "midi": None, "ly": str(ly_path), "warnings": [], "error": None}
    if exe is None:
        result["error"] = "找不到 lilypond.exe（已嘗試 D:\\lilypond-2.26.0 與 PATH）"
        return result
    out_dir.mkdir(parents=True, exist_ok=True)
    try:
        proc = subprocess.run(
            [str(exe), str(ly_path)],
            cwd=str(out_dir),
            capture_output=True,
            text=True,
            timeout=120,
            # 避免編譯期間彈出 PDF/MIDI 視窗、也避免終端閃動（GUI 環境下重要）
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        )
    except subprocess.TimeoutExpired:
        result["error"] = "LilyPond 編譯超時（120 秒）"
        return result
    base = ly_path.with_suffix("")
    pdf = base.with_suffix(".pdf")
    if pdf.exists():
        result["pdf"] = str(pdf)
        for cand in (base.with_suffix(".mid"), base.with_suffix(".midi")):
            if cand.exists():
                result["midi"] = str(cand)
                break
    else:
        tail = (proc.stderr or proc.stdout or "")[-600:]
        result["error"] = f"LilyPond 編譯失敗（rc={proc.returncode}）：{tail}"
    if cleanup_ly and pdf.exists():
        try:
            ly_path.unlink(missing_ok=True)
            result["ly"] = None
        except OSError:
            pass
    return result


def render_ly_file(ly_path: Path, out_dir: Path, cleanup_ly: bool = False) -> dict:
    """編譯「已落盤的 .ly 檔」（客戶端提供的來源）。回傳 {pdf, midi, ly, error}。"""
    return _compile_ly(ly_path, out_dir, cleanup_ly)


def render(doc: ScoreDocument, out_dir: Path, cleanup_ly: bool = True) -> dict:
    """ScoreDocument → 編譯 PDF + MIDI。回傳 {pdf, midi, ly, warnings, error}。"""
    ly_text, warnings = document_to_ly(doc)
    out_dir.mkdir(parents=True, exist_ok=True)
    safe = re.sub(r"[^A-Za-z0-9_]", "_", doc.title or "score")[:40] or "score"
    base = out_dir / safe
    ly_path = base.with_suffix(".ly")
    ly_path.write_text(ly_text, encoding="utf-8")
    result = _compile_ly(ly_path, out_dir, cleanup_ly)
    result["warnings"] = warnings
    return result
