"""Legacy Score Adapter（規格 §4/§13 T13）：ScoreDocument v1 ⇄ 既有 project.json。

- v1 → legacy：讓舊編輯器繼續讀寫（未知欄位留在 extensions，不靜默刪除）。
- 保留原 OMR 資料：legacy beats 的 rawToken 映射存於 extensions.legacyBeats。
"""
from __future__ import annotations

from typing import Any

from . import DURATION_TICKS

_TICKS_TO_LEGACY = {v: k for k, v in DURATION_TICKS.items()}


def _dotted_base(dur: int) -> str:
    """480*1.5=720 → quarter+dotted。"""
    for base_name, base in DURATION_TICKS.items():
        if dur == base:
            return base_name
        if dur == base + base // 2:
            return base_name
    # 附點連用（720+360=1080 等）回四分散值
    return _TICKS_TO_LEGACY.get(dur, "quarter")


def _event_to_note_token(ev) -> str:
    if ev.type == "rest":
        n = "0"
    elif ev.type == "note" and ev.pitch is not None:
        deg = ev.pitch.degree
        n = str(deg)
        if ev.pitch.accidental > 0:
            n = "#" + n
        elif ev.pitch.accidental < 0:
            n = "b" + n
        # 減時線（legacy 用 _ 表示分音符）
        ticks = ev.durationTicks
        base_ticks = DURATION_TICKS["quarter"]
        halvings = 0
        rem = ticks
        # 附點部分先扣除
        if ev.notation.dots:
            rem -= ticks // 2
        while rem < base_ticks and rem > 0:
            halvings += 1
            rem *= 2
            base_ticks //= 2
        n += "_" * halvings
        if ev.notation.dots:
            n += "."
        if ev.pitch.octave > 0:
            n += "'" * ev.pitch.octave
        elif ev.pitch.octave < 0:
            n += "," * (-ev.pitch.octave)
    else:
        # unknown / direction：保留原文，絕不補造
        return ev.unknownText or ""
    return n


def v1_to_legacy(doc, legacy_meta: dict | None = None) -> dict:
    """v1 → 既有 project.json 結構（供舊編輯器 / 舊匯出使用）。"""
    legacy_meta = legacy_meta or {}
    s = doc.scoreSettings
    measures: list[dict] = []
    ext_beats: dict[str, Any] = {}
    for part in doc.parts:
        for m in part.measures:
            note_text_parts: list[str] = []
            lyric_parts: list[str] = []
            chord_parts_all: list[str] = []
            beats: list[dict] = []
            for e in m.events:
                tok = _event_to_note_token(e)
                note_text_parts.append(tok)
                lyr = "".join(lr.text for lr in e.lyrics)
                lyric_parts.append(lyr)
                ev_chord_txt = " ".join(c.rawText for c in e.chords if c.rawText)
                if ev_chord_txt:
                    chord_parts_all.append(ev_chord_txt)
                p = e.provenance
                beats.append({
                    "beat": len(beats) + 1,
                    "note": tok,
                    "lyric": lyr,
                    "chord": ev_chord_txt,
                    "duration": _dotted_base(e.durationTicks),
                    "confidence": p.confidence,
                    "annotation": f"degree={e.pitch.degree if e.pitch else '?'}",
                })
                ext_beats.setdefault(str(m.number), []).append({
                    "eventId": e.id, "rawToken": p.rawToken, "duration": e.notation.duration,
                })
            chord_text = " ".join(dict.fromkeys(chord_parts_all))  # 多和弦並列、保序去重
            measures.append({
                "number": m.number,
                "lineIndex": (len(measures)) // int(legacy_meta.get("measuresPerLine", 4)),
                "linePosition": ((len(measures)) % int(legacy_meta.get("measuresPerLine", 4))) + 1,
                "chordText": chord_text,
                "noteText": " ".join(t for t in note_text_parts if t != "" or True),
                "lyricText": " ".join(lyric_parts),
                "beats": beats,
                "sourcePage": m.provenance.page,
            })
    out = {
        "id": legacy_meta.get("id", doc.projectId),
        "title": doc.title,
        "lyricist": doc.metadata.lyricist,
        "composer": doc.metadata.composer,
        "key": s.key.tonic,
        "timeSignature": f"{s.timeSignature.beats}/{s.timeSignature.beatType}",
        "tempo": s.tempo.bpm,
        "engineMode": legacy_meta.get("engineMode", "manual"),
        "engineNote": legacy_meta.get("engineNote", ""),
        "sourceName": legacy_meta.get("sourceName", ""),
        "createdAt": legacy_meta.get("createdAt", doc.audit.createdAt),
        "updatedAt": doc.audit.updatedAt,
        "measures": measures,
        "extensions": {"scoreStudio": {"revision": doc.audit.revision,
                                        "legacyBeats": ext_beats}},
    }
    return out


def legacy_to_v1(legacy: dict) -> dict:
    """僅供 import-omr / snapshot 用（正式轉換走 omr_adapter）。"""
    from . import omr_adapter
    return omr_adapter.convert(legacy).save_dict()
