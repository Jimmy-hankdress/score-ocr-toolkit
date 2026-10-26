"""ScoreStudio — ScoreDocument v1（唯一標準可編輯資料格式）。

依整合規格 §6：文件根物件 / 聲部 / 小節 / 音樂事件 / 歌詞 / 和弦 / 溯源。
Pydantic v2 寫法；UUID 用 uuid5（固定 namespace + 結構路徑）→ 重新載入後 UUID 穩定一致。
"""
from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any, Literal, Optional

from pydantic import BaseModel, Field

# ticks 固定制（規格 §9.2）：ticksPerQuarter = 480
TICKS_PER_QUARTER = 480
DURATION_TICKS = {
    "whole": 1920,
    "half": 960,
    "quarter": 480,
    "eighth": 240,
    "sixteenth": 120,
    "thirtysecond": 60,
}
NOTATION_NAME_BY_TICKS = {1920: "whole", 960: "half", 480: "quarter",
                           240: "eighth", 120: "sixteenth", 60: "thirtysecond"}

# 簡譜 1=C major：Do=60（C4）。degree 1..7 → MIDI（不含 accidental/octave）
_DEGREE_SEMITONE = {1: 0, 2: 2, 3: 4, 4: 5, 5: 7, 6: 9, 7: 11}
_TONIC_TO_MIDI = {"C": 60, "G": 62, "D": 64, "A": 66, "E": 68, "B": 70,
                  "F#": 64, "F": 59, "Bb": 66, "Eb": 63, "Ab": 58, "Db": 56,
                  "c": 60, "g": 62, "d": 64, "a": 66, "e": 68, "b": 70,
                  "f": 59, "bb": 66, "eb": 63, "ab": 58, "db": 56}
_TONIC_TO_SHIFT = {"C": 0, "G": 2, "D": 4, "A": 7, "E": 9, "B": 11,
                   "F": -1, "F#": 6, "Bb": -2, "Eb": -3, "Ab": -5, "Db": -6}


def _ns() -> uuid.UUID:
    return uuid.UUID("8f010203-0405-4a6b-8c0d-010203040506")


def stable_uuid(scope: str, *parts: str) -> str:
    """同一路徑輸入 → 同一 UUID（重新載入一致）。"""
    return str(uuid.uuid5(_ns(), f"{scope}::{'::'.join(parts)}"))


def now_iso() -> str:
    return datetime.now().astimezone().isoformat(timespec="seconds")


class Key(BaseModel):
    tonic: str = "C"
    mode: Literal["major", "minor"] = "major"
    display: str = "1=C"


class TimeSignature(BaseModel):
    beats: int = 4
    beatType: int = 4


class Tempo(BaseModel):
    bpm: int = 80
    beatUnit: str = "quarter"
    text: str = ""


class ScoreSettings(BaseModel):
    notationMode: str = "jianpu"
    key: Key = Field(default_factory=Key)
    timeSignature: TimeSignature = Field(default_factory=TimeSignature)
    tempo: Tempo = Field(default_factory=Tempo)
    pickupTicks: int = 0
    ticksPerQuarter: int = TICKS_PER_QUARTER
    displayTransposeSemitones: int = 0
    rhythmGrouping: str = "byTimeSignature"
    showKey: bool = True
    showTimeSignature: bool = True
    showTempo: bool = True

    def measure_ticks(self) -> int:
        """預期小節 ticks = beats × tpq × 4 / beatType（§9.3）。"""
        ts = self.timeSignature
        return ts.beats * self.ticksPerQuarter * 4 // max(1, ts.beatType)


class Provenance(BaseModel):
    """§6.7：原始來源與人工修正（不可刪 rawToken/bbox）。"""
    source: Literal["omr", "manual", "omr+manual", "imported_musicxml", "legacy"] = "omr"
    page: Optional[int] = None
    bbox: Optional[list[int]] = None          # [x, y, width, height]
    rawToken: str = ""
    confidence: float = 1.0
    reviewStatus: Literal["verified", "needs_review", "unresolved"] = "verified"
    reviewReason: Optional[str] = None        # low_confidence|ambiguous_duration|lyric_alignment|unknown_symbol|manual
    correctedValue: Optional[str] = None
    reviewedByUser: bool = False
    reviewedAt: Optional[str] = None


class Pitch(BaseModel):
    degree: int = 1
    accidental: int = 0          # +升 / -降（§9.1：n 還原=0）
    octave: int = 0
    midi: Optional[int] = None

    @staticmethod
    def compute_midi(degree: int, accidental: int, octave: int,
                     tonic: str, mode: str) -> int:
        """簡譜級數 → MIDI。major 音階；minor MVP 先按同調級半音（不造假音高）。"""
        tonic_midi = _TONIC_TO_MIDI.get(tonic, 60)
        deg = 1 if degree not in _DEGREE_SEMITONE else degree
        base = _DEGREE_SEMITONE.get(deg, 0)
        return tonic_midi + base + accidental + octave * 12


class Tuplet(BaseModel):
    actual: int = 3
    normal: int = 2


class Notation(BaseModel):
    duration: str = "quarter"
    dots: int = 0
    tieStart: bool = False
    tieStop: bool = False
    slurStart: bool = False
    slurStop: bool = False
    tuplet: Optional[Tuplet] = None
    articulations: list[str] = Field(default_factory=list)


def duration_ticks(name: str, dots: int = 0) -> int:
    base = DURATION_TICKS.get(name, DURATION_TICKS["quarter"])
    total = base
    for _ in range(dots):
        total += total // 2
    return total


class LyricsRef(BaseModel):
    """事件上的歌詞（§6.5）。"""
    id: str
    verse: int = 1
    label: str = ""
    text: str = ""
    syllabic: Literal["single", "begin", "middle", "end"] = "single"
    extend: bool = False
    provenance: Provenance = Field(default_factory=Provenance)


class ChordParsed(BaseModel):
    root: str = ""
    quality: str = ""
    bass: str = ""
    extensions: list[str] = Field(default_factory=list)


class ChordRef(BaseModel):
    """§6.6：解析失敗 parsed=None，rawText 永不丟。"""
    id: str
    anchorType: str = "event"
    anchorId: str = ""
    offsetTick: int = 0
    rawText: str = ""
    parsed: Optional[ChordParsed] = None
    position: Literal["above", "below"] = "above"
    transposeWithScore: bool = True
    provenance: Provenance = Field(default_factory=Provenance)


class MusicEvent(BaseModel):
    """§6.4。type: note | rest | unknown | direction | barline-anchor。"""
    id: str
    type: Literal["note", "rest", "unknown", "direction", "barline-anchor"] = "note"
    startTick: int = 0
    durationTicks: int = DURATION_TICKS["quarter"]
    durationStatus: Literal["verified", "unknown", "reviewed"] = "verified"
    pitch: Optional[Pitch] = None
    notation: Notation = Field(default_factory=Notation)
    unknownText: str = ""
    lyrics: list[LyricsRef] = Field(default_factory=list)
    chords: list[ChordRef] = Field(default_factory=list)
    annotations: list[str] = Field(default_factory=list)
    provenance: Provenance = Field(default_factory=Provenance)


class Barline(BaseModel):
    left: str = "single"
    right: str = "single"
    repeatStart: bool = False
    repeatEnd: bool = False
    final: bool = False


class MeasureProvenance(BaseModel):
    source: str = "omr"
    page: Optional[int] = None
    bbox: Optional[list[int]] = None
    confidence: float = 1.0


class Measure(BaseModel):
    """§6.3。"""
    id: str
    number: int = 1
    timeSignatureOverride: Optional[TimeSignature] = None
    keyOverride: Optional[Key] = None
    rhythmGroupingOverride: Optional[str] = None
    events: list[MusicEvent] = Field(default_factory=list)
    barline: Barline = Field(default_factory=Barline)
    provenance: MeasureProvenance = Field(default_factory=MeasureProvenance)

    def measure_ticks(self, settings: ScoreSettings) -> int:
        ts = self.timeSignatureOverride or settings.timeSignature
        return ts.beats * settings.ticksPerQuarter * 4 // max(1, ts.beatType)


class Part(BaseModel):
    """§6.2。第一階段單聲部。"""
    id: str
    name: str = "旋律"
    shortName: str = "Mel."
    instrument: dict = Field(default_factory=lambda: {"id": "voice", "name": "人聲", "midiProgram": 0})
    notationMode: str = "jianpu"
    muted: bool = False
    solo: bool = False
    volume: float = 0.85
    transposeSemitones: int = 0
    measures: list[Measure] = Field(default_factory=list)


class Section(BaseModel):
    id: str
    name: str = ""
    startMeasure: int = 1
    endMeasure: int = 1


class SourcePage(BaseModel):
    id: str
    index: int = 1
    file: str = ""
    width: int = 0
    height: int = 0


class Metadata(BaseModel):
    composer: str = ""
    lyricist: str = ""
    arranger: str = ""
    copyright: str = ""
    language: str = "zh-Hant"


class Audit(BaseModel):
    createdAt: str = Field(default_factory=now_iso)
    updatedAt: str = Field(default_factory=now_iso)
    revision: int = 1


class ScoreDocument(BaseModel):
    """§6.1 文件根物件。"""
    schemaVersion: str = "1.0.0"
    projectId: str = ""
    title: str = "未命名樂譜"
    metadata: Metadata = Field(default_factory=Metadata)
    scoreSettings: ScoreSettings = Field(default_factory=ScoreSettings)
    parts: list[Part] = Field(default_factory=list)
    sections: list[Section] = Field(default_factory=list)
    sourcePages: list[SourcePage] = Field(default_factory=list)
    extensions: dict[str, Any] = Field(default_factory=dict)
    audit: Audit = Field(default_factory=Audit)

    def save_dict(self) -> dict:
        return self.model_dump(by_alias=False)

    @staticmethod
    def from_dict(d: dict) -> "ScoreDocument":
        return ScoreDocument.model_validate(d)


# ---------- 和弦解析（§10.2；失敗回 None 保 rawText） ----------
_CHORD_QUALITIES = ("maj7", "m7", "sus4", "add9", "dim", "m", "7", "")
_ROOTS = ["C", "C#", "D", "Eb", "E", "F", "F#", "G", "Ab", "A", "Bb", "B"]


def parse_chord(raw: str) -> Optional[ChordParsed]:
    s = (raw or "").strip()
    if not s:
        return None
    bass = ""
    m = s
    if "/" in s:
        head, bass = s.split("/", 1)
        m = head
        if bass not in _ROOTS:
            return ChordParsed(root=_ROOTS[0] if m in _ROOTS else "", quality="",
                               bass=bass, extensions=[]) if m in _ROOTS else None
    root = ""
    for r in sorted(_ROOTS, key=len, reverse=True):
        if m.startswith(r):
            root = r
            m = m[len(r):]
            break
    if not root:
        return None
    quality = ""
    for q in _CHORD_QUALITIES:
        if m.startswith(q):
            quality = q
            m = m[len(q):]
            break
    extensions = [e for e in ("9", "11", "13", "5", "b9") if e in m]
    if m:
        return None  # 殘留無法解析
    return ChordParsed(root=root, quality=quality, bass=bass, extensions=extensions)


def blank_document(project_id: str, title: str = "未命名樂譜") -> ScoreDocument:
    part = Part(id=stable_uuid("part", project_id, "main"), measures=[
        Measure(id=stable_uuid("measure", project_id, "1", "1"), number=1)
    ])
    return ScoreDocument(
        projectId=project_id, title=title,
        parts=[part],
        audit=Audit(createdAt=now_iso(), updatedAt=now_iso(), revision=1),
    )
