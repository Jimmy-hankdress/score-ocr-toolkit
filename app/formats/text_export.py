"""JSON／TSV／純文字匯出（規劃書 2.2 P0：本機保存與匯出）。"""
from __future__ import annotations

import json

from ..models import MEASURES_PER_LINE, ScoreDocument

TSV_HEADER = ["measure", "beat", "note", "lyric", "chord", "duration", "confidence"]


def document_to_json(doc: ScoreDocument) -> str:
    payload = {
        "format": "sheetmusic-omr/score",
        "version": 1,
        "metadata": {
            "title": doc.title,
            "lyricist": doc.lyricist,
            "composer": doc.composer,
            "key": doc.key,
            "timeSignature": doc.timeSignature,
            "tempo": doc.tempo,
            "engineMode": doc.engineMode,
            "engineNote": doc.engineNote,
            "sourceName": doc.sourceName,
            "updatedAt": doc.updatedAt,
        },
        "rows": [
            {
                "measure": m.number,
                "lineIndex": m.lineIndex,
                "linePosition": m.linePosition,
                "chordText": m.chordText,
                "noteText": m.noteText,
                "lyricText": m.lyricText,
                "beats": [b.to_dict() for b in m.beats],
            }
            for m in doc.measures
        ],
    }
    return json.dumps(payload, ensure_ascii=False, indent=2)


def document_to_tsv(doc: ScoreDocument) -> str:
    lines = ["\t".join(TSV_HEADER)]
    for m in doc.measures:
        beats = m.beats or m.expand_beats()
        for b in beats:
            lines.append(
                "\t".join(
                    [
                        str(m.number),
                        str(b.beat),
                        b.note,
                        b.lyric,
                        b.chord,
                        b.duration,
                        f"{b.confidence:.2f}",
                    ]
                )
            )
    return "\n".join(lines) + "\n"


def document_to_plain_text(doc: ScoreDocument) -> str:
    """原稿式純文字：每行三小節，和弦／簡譜／歌詞三列對齊。"""
    out = [doc.title or "未命名樂譜"]
    meta = []
    if doc.lyricist:
        meta.append(f"作詞：{doc.lyricist}")
    if doc.composer:
        meta.append(f"作曲：{doc.composer}")
    meta.append(f"1={doc.key}")
    meta.append(doc.timeSignature)
    meta.append(f"♩={doc.tempo}")
    out.append("　".join(meta))
    out.append("")

    for start in range(0, len(doc.measures), MEASURES_PER_LINE):
        row = doc.measures[start : start + MEASURES_PER_LINE]
        width = 26
        chord = " | ".join((m.chordText or "").ljust(width) for m in row)
        note = " | ".join((m.noteText or "").ljust(width) for m in row)
        lyric = " | ".join((m.lyricText or "").ljust(width) for m in row)
        numbers = " | ".join(f"[{m.number}]".ljust(width) for m in row)
        out.extend([numbers.rstrip(), chord.rstrip(), note.rstrip(), lyric.rstrip(), ""])
    return "\n".join(out) + "\n"
