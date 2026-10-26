"""ScoreDocument → 匯出格式（§15）。MusicXML 不引外連 DTD；JSON/TSV/TXT 由 v1 轉換。"""
from __future__ import annotations

import json
from xml.sax.saxutils import escape

from . import ScoreDocument, DURATION_TICKS, duration_ticks

_MUSICXML_TYPE = {
    1920: "whole", 960: "half", 480: "quarter", 240: "eighth", 120: "sixteenth", 60: "32nd",
}
_KEY_FIFTHS = {"C": 0, "G": 1, "D": 2, "A": 3, "E": 4, "B": 5, "F#": 6,
               "F": -1, "Bb": -2, "Eb": -3, "Ab": -4, "Db": -5,
               "c": 0, "g": 1, "d": 2, "a": 3, "e": 4, "b": 5,
               "f": -1, "bb": -2, "eb": -3, "ab": -4, "db": -5}


def _note_type_name(dur: int) -> str:
    return _MUSICXML_TYPE.get(dur, "quarter")


def _syllabic_tag(syll: str) -> str:
    return {"single": "single", "begin": "begin", "middle": "middle", "end": "end"}.get(syll, "single")


def export_musicxml(doc: ScoreDocument) -> str:
    """§15.2：不引外連 DTD 的 score-partwise。"""
    s = doc.scoreSettings
    divisions = s.ticksPerQuarter
    p = doc.parts[0] if doc.parts else None
    ts = s.timeSignature
    part_id = "P" + (p.id.replace("-", "p") if p else "main")
    fifths = _KEY_FIFTHS.get(s.key.tonic, 0)
    lines = [
        '<?xml version="1.0" encoding="UTF-8"?>',
        '<!DOCTYPE score-partwise SYSTEM "score-partwise.dtd">',
        '<score-partwise version="4.0">',
        '<work><work-title>' + escape(doc.title or "未命名") + '</work-title></work>',
        '<part-list><score-part id="' + part_id + '">',
        '  <part-name>' + escape(p.name if p else "旋律") + '</part-name>',
        '</score-part></part-list>',
        '<part id="' + part_id + '">',
    ]
    if p:
        lines.append('  <attributes>')
        lines.append(f'    <divisions>{divisions}</divisions>')
        lines.append(f'    <time><beats>{ts.beats}</beats><beat-type>{ts.beatType}</beat-type></time>')
        lines.append(f'    <key><fifths>{fifths}</fifths></key>')
        lines.append('    <clef><sign>G</sign><line>2</line></clef>')
        lines.append('  </attributes>')
        lines.append(f'  <direction><direction-type><metronome><beat-unit>quarter</beat-unit>'
                     f'<per-minute>{s.tempo.bpm}</per-minute></metronome></direction-type></direction>')
        for m in p.measures:
            lines.append(f'  <measure number="{m.number}">')
            for e in m.events:
                if e.type == "note" and e.pitch:
                    typ = _note_type_name(e.durationTicks)
                    lines.append(f'    <note><pitch><step>{_step(e.pitch.degree)}</step>'
                                 + (f'<alter>{e.pitch.accidental}</alter>' if e.pitch.accidental else '')
                                 + f'<octave>{e.pitch.octave + 4}</octave></pitch>')
                    lines.append(f'      <duration>{e.durationTicks}</duration><type>{typ}</type>')
                    lines += ['      <dot/>' for _ in range(e.notation.dots)]
                    if e.notation.tieStop:
                        lines.append('      <tie type="stop"/>')
                    for lr in e.lyrics:
                        lines.append(f'      <lyric><syllabic>{_syllabic_tag(lr.syllabic)}</syllabic>'
                                     f'<text>{escape(lr.text)}</text></lyric>')
                    for c in e.chords:
                        if c.parsed:
                            lines.append(f'      <chord>{escape(c.parsed.root)}{escape(c.parsed.quality)}'
                                         + (f'/{escape(c.parsed.bass)}' if c.parsed.bass else '') + '</chord>')
                        else:
                            # §15.2 保底：解析失敗以文字 direction 輸出
                            lines.append(f'      <direction><direction-type><text>{escape(c.rawText)}</text></direction-type></direction>')
                    lines.append('    </note>')
                elif e.type == "rest":
                    lines.append(f'    <rest><duration>{e.durationTicks}</duration>'
                                 f'<type>{_note_type_name(e.durationTicks)}</type></rest>')
            lines.append('    <barline><bar-style>normal</bar-style></barline>')
            lines.append('  </measure>')
        # 終止小節
        last_num = p.measures[-1].number + 1 if p.measures else 1
        lines.append(f'  <measure number="{last_num}">')
        lines.append(f'    <backup><duration>{ts.beats * divisions * 4 // max(1, ts.beatType)}</duration></backup>')
        lines.append('    <rest><duration>1</duration></rest>')
        lines.append('    <barline><bar-style>end</bar-style></barline>')
        lines.append('  </measure>')
    lines.append('  </part>')
    lines.append('</score-partwise>')
    return "\n".join(lines)


_STEP = {1: "C", 2: "D", 3: "E", 4: "F", 5: "G", 6: "A", 7: "B"}


def _step(degree: int) -> str:
    return _STEP.get(degree % 7 or 7, "C")


def _alter(acc: int) -> str:
    if acc > 0:
        return f'<alter>{acc}</alter>'
    if acc < 0:
        return f'<alter>{acc}</alter>'
    return ""


def export_json(doc: ScoreDocument) -> str:
    return json.dumps(doc.save_dict(), ensure_ascii=False, indent=1)


def _row(doc: ScoreDocument) -> list[dict]:
    rows = []
    for part in doc.parts:
        for m in part.measures:
            for e in m.events:
                lyr = " ".join(lr.text for lr in e.lyrics)
                chord = " ".join(c.rawText for c in e.chords if c.rawText)
                if e.type == "note" and e.pitch:
                    n = ("#" * e.pitch.accidental if e.pitch.accidental > 0 else "b" * -e.pitch.accidental if e.pitch.accidental < 0 else "") + str(e.pitch.degree)
                    n += ("_" * 1 if e.notation.duration == "eighth" else "")
                    if e.pitch.octave:
                        n += ("'" * e.pitch.octave) if e.pitch.octave > 0 else ("," * -e.pitch.octave)
                else:
                    n = "0" if e.type == "rest" else e.unknownText
                rows.append({"measure": m.number, "note": n, "lyric": lyr, "chord": chord,
                             "duration": e.notation.duration, "status": e.durationStatus})
    return rows


def export_tsv(doc: ScoreDocument) -> str:
    rows = _row(doc)
    head = "measure\tnote\tlyric\tchord\tduration\tstatus"
    body = "\n".join(f"{r['measure']}\t{r['note']}\t{r['lyric']}\t{r['chord']}\t{r['duration']}\t{r['status']}" for r in rows)
    return head + "\n" + body + "\n"


def export_txt(doc: ScoreDocument) -> str:
    s = doc.scoreSettings
    out = [doc.title, f"1={s.key.tonic} {s.timeSignature.beats}/{s.timeSignature.beatType}  q={s.tempo.bpm}"]
    for part in doc.parts:
        for m in part.measures:
            notes = []
            for e in m.events:
                if e.type == "note" and e.pitch:
                    n = ("#" if e.pitch.accidental > 0 else "b" if e.pitch.accidental < 0 else "") + str(e.pitch.degree)
                    n += ("'" if e.pitch.octave > 0 else "," if e.pitch.octave < 0 else "")
                    if e.notation.dots:
                        n += "."
                elif e.type == "rest":
                    n = "0"
                else:
                    n = e.unknownText or "?"
                notes.append(n)
            chord = " ".join(dict.fromkeys(c.rawText for e in m.events for c in e.chords if c.rawText))
            lyrics = " ".join(lr.text for e in m.events for lr in e.lyrics)
            out.append(f"| {m.number} {chord:>6} | {' '.join(notes):<24} | {lyrics} |")
    return "\n".join(out)
