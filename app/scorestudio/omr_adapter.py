"""OMR Adapter（§7）：既有 project.json（legacy ScoreDocument）→ ScoreDocument v1。

規則（§7.1）：
- 1–7 → 簡譜音符事件；0 → 休止符。
- 無法可靠確認的 token → type=unknown，絕不補造時值。
- 高/低八度點沿用既有記法（' 與 ,），存 pitch.octave，標記 provenance。
- 時值未知 → durationStatus=unknown（不可自動補成四分音符）。
- 低信心（<0.9）→ reviewStatus=needs_review；空/亂碼 → unresolved。
- 和弦解析失敗保 rawText（parsed=None）。
- 原始 OMR 完整結果存於 extensions.rawOmr（指向 project.json 相對路徑）。
- legacy 資料放 extensions.legacyDocument（舊編輯器讀寫不受影響）。
"""
from __future__ import annotations

import re
from typing import Any, Optional

from . import (ScoreDocument, Part, Measure, MusicEvent, LyricsRef, ChordRef,
               Provenance, Pitch, Notation, stable_uuid,
               parse_chord, DURATION_TICKS, now_iso, Audit, SourcePage,
               Metadata, Key, Tempo, TimeSignature, ScoreSettings,
               TICKS_PER_QUARTER, blank_document)

_TOKEN_RE = re.compile(r"^(?P<acc>[#bn])?(?P<digit>[0-7])(?P<tail>['',.\-_]*)$")
_DURATION_NAME = {0: "quarter", 1: "eighth", 2: "sixteenth", 3: "thirtysecond"}
# legacy beats[].duration 字串 → ticks（models.duration_from_token 的命名）
_LEGACY_DUR_TICKS = {
    "whole": 1920, "half": 960, "quarter": 480, "eighth": 240, "16th": 120, "32nd": 60,
}


def _legacy_beat_ticks(b: dict) -> tuple[int, bool] | None:
    """legacy beat 的 authoritative 時值（優於 token 推導）；沒有則 None。
    回傳 (ticks, is_known)。"""
    d = str(b.get("duration") or "").strip()
    if not d:
        return None
    dotted = d.startswith("dotted-")
    base = d[len("dotted-"):] if dotted else d
    if base not in _LEGACY_DUR_TICKS:
        return None
    ticks = _LEGACY_DUR_TICKS[base]
    total = ticks + (ticks // 2 if dotted else 0)
    return total, True


def _parse_token(tok: str) -> dict:
    """拆簡譜 token：音級/升記/減時線/附點/八度。拆不出 → unknown。
    尾巴（高低八度點、附點、減時線）順序不固定（如 2'. 5_. 3_.），一律各自計數。"""
    t = (tok or "").strip()
    if not t:
        return {"ok": False}
    if t in ("-", "--", "tie"):
        return {"ok": False, "raw": t, "dash": True}
    m = _TOKEN_RE.match(t)
    if not m:
        return {"ok": False, "raw": t}
    g = m.groupdict()
    digit = g["digit"]
    tail = g["tail"]
    acc = {"#": 1, "b": -1, "n": 0, "": 0}.get(g.get("acc") or "", 0)
    if g.get("acc") == "n":
        acc = 0
    oct_up = tail.count("'")
    oct_dn = tail.count(",")
    dotted = "." in tail
    halvings = tail.count("_")
    return {
        "ok": True,
        "acc": acc,
        "digit": digit,
        "isRest": digit == "0",
        "octave": oct_up - oct_dn,
        "halvings": halvings,
        "dotted": dotted,
        "raw": t,
    }


def _legacy_duration_name(halvings: int, dotted: bool) -> tuple[str, bool]:
    name = _DURATION_NAME.get(halvings)
    if name is None:
        return "quarter", False   # 未知減時 → 回傳 verified=False
    return name, True


def convert(omr_result: dict[str, Any]) -> ScoreDocument:
    """omr_result = legacy project.json dict（含 measures/beats/confidence）。"""
    project_id = str(omr_result.get("id") or omr_result.get("docId") or "unknown")
    key = omr_result.get("key") or "C"
    ts = (omr_result.get("timeSignature") or "4/4").split("/")
    ts_beats = int(ts[0]) if ts and ts[0].isdigit() else 4
    ts_type = int(ts[1]) if len(ts) > 1 and ts[1].isdigit() else 4
    tempo = int(omr_result.get("tempo") or 80)
    engine_mode = omr_result.get("engineMode") or "manual"
    src = "omr" if engine_mode not in ("manual", "text-import") else "legacy"

    settings = ScoreSettings(
        key=Key(tonic=key, mode="major", display=f"1={key}"),
        timeSignature=TimeSignature(beats=ts_beats, beatType=ts_type),
        tempo=Tempo(bpm=tempo, beatUnit="quarter"),
        ticksPerQuarter=TICKS_PER_QUARTER,
    )
    doc = blank_document(project_id, omr_result.get("title") or "未命名樂譜")
    doc.scoreSettings = settings
    doc.metadata = Metadata(
        composer=omr_result.get("composer") or "",
        lyricist=omr_result.get("lyricist") or "",
        language="zh-Hant")

    legacy_measures = omr_result.get("measures") or []
    part = doc.parts[0]
    part.name = "旋律"
    part.measures = []  # 清掉 blank_document 預建的空小節，避免多出一個節

    tick = settings.pickupTicks or 0
    midx = 0
    for m in legacy_measures:
        midx += 1
        mi = int(m.get("number") or midx)
        beats = m.get("beats") or []
        if not beats:
            # 由文字重建拍位（沿用既有 expand 邏輯產出的 beats）
            note_text = m.get("noteText") or ""
            beats = [{"beat": i + 1, "note": n, "lyric": (m.get("lyricText") or "").split()[i] if i < len((m.get("lyricText") or "").split()) else "", "chord": "", "duration": "quarter", "confidence": 1.0, "annotation": ""}
                     for i, n in enumerate([x for x in note_text.split() if x])]

        measure = Measure(
            id=stable_uuid("measure", project_id, part.id, str(mi)),
            number=mi,
            provenance={"source": src, "page": m.get("sourcePage"), "confidence": 1.0},
        )
        ev_tick = 0
        for b in beats:
            tok_raw = str(b.get("note") or "")
            conf = float(b.get("confidence") or 1.0)
            p = _parse_token(tok_raw)
            ev_id = stable_uuid("event", project_id, part.id, str(mi), str(b.get("beat")))
            page = b.get("page") or m.get("sourcePage")
            legacy_d = _legacy_beat_ticks(b)

            # 延音線「-」（§9.1：tie 不可用重複音替代）：併入前一音符，延長時值
            dash_run = tok_raw.strip()
            if dash_run and set(dash_run) == {"-"} and measure.events:
                ext_count = len(dash_run)
                prev = measure.events[-1]
                add = DURATION_TICKS["quarter"] * ext_count
                prev.durationTicks += add
                prev.notation.tieStop = True
                # 延音拍若帶歌詞/和弦，歸併到前一音（延音本即長音）
                lyr = str(b.get("lyric") or "").strip()
                if lyr:
                    prev.lyrics.append(LyricsRef(
                        id=stable_uuid("lyric", project_id, part.id, str(mi),
                                       str(b.get("beat")), "v1ext"),
                        verse=1, label="", text=lyr, syllabic="single",
                        extend=True,
                        provenance=Provenance(source=src, page=page, rawToken=lyr,
                                              confidence=conf)))
                ev = None
                ev_tick += add
                measure.events.pop()
                measure.events.append(prev)
                continue
            elif not p["ok"]:
                # 拆不出 → unknown，保留 raw，不補造時值（§7.1）
                ev = MusicEvent(
                    id=ev_id, type="unknown", startTick=ev_tick,
                    durationTicks=DURATION_TICKS["quarter"],
                    durationStatus="unknown",
                    unknownText=tok_raw,
                    provenance=Provenance(source=src, page=page, rawToken=tok_raw,
                                          confidence=conf,
                                          reviewStatus="unresolved",
                                          reviewReason="unknown_symbol"),
                )
            elif p["isRest"]:
                if legacy_d:
                    dur, known = legacy_d
                    name = "quarter"
                    if p["dotted"]:
                        name = "dotted-quarter"
                else:
                    name, known = _legacy_duration_name(p["halvings"], p["dotted"])
                    dur = (DURATION_TICKS[name] + DURATION_TICKS[name] // 2) if p["dotted"] else DURATION_TICKS[name]
                ev = MusicEvent(
                    id=ev_id, type="rest", startTick=ev_tick, durationTicks=dur,
                    durationStatus="verified" if known else "unknown",
                    notation=Notation(duration="quarter" if known else name, dots=1 if p["dotted"] else 0),
                    provenance=Provenance(source=src, page=page, rawToken=tok_raw,
                                          confidence=conf,
                                          reviewStatus="verified" if conf >= 0.9 else "needs_review",
                                          reviewReason=None if conf >= 0.9 else "low_confidence"),
                )
            else:
                if legacy_d:
                    dur, known = legacy_d
                    name = "quarter"
                    if p["dotted"]:
                        name = "dotted-quarter"
                else:
                    name, known = _legacy_duration_name(p["halvings"], p["dotted"])
                    dur = (DURATION_TICKS[name] + DURATION_TICKS[name] // 2) if p["dotted"] else DURATION_TICKS[name]
                deg = int(p["digit"])
                midi = Pitch.compute_midi(deg, p["acc"], p["octave"], settings.key.tonic, "major")
                review = "verified" if (conf >= 0.9 and known) else "needs_review"
                reason = None
                if conf < 0.9:
                    reason = "low_confidence"
                elif not known:
                    reason = "ambiguous_duration"
                ev = MusicEvent(
                    id=ev_id, type="note", startTick=ev_tick, durationTicks=dur,
                    durationStatus="verified" if known else "unknown",
                    pitch=Pitch(degree=deg, accidental=p["acc"], octave=p["octave"], midi=midi),
                    notation=Notation(duration=name, dots=1 if p["dotted"] else 0),
                    provenance=Provenance(source=src, page=page, rawToken=tok_raw,
                                          confidence=conf, reviewStatus=review,
                                          reviewReason=reason),
                )
                # 歌詞附著（§10.1：中文一字一音、休止跳過）
                lyr = str(b.get("lyric") or "").strip()
                if lyr:
                    lp = Provenance(source=src, page=page, rawToken=lyr, confidence=conf,
                                    reviewStatus="verified" if conf >= 0.9 else "needs_review",
                                    reviewReason=None if conf >= 0.9 else "lyric_alignment")
                    ev.lyrics.append(LyricsRef(
                        id=stable_uuid("lyric", project_id, part.id, str(mi), str(b.get("beat")), "v1"),
                        verse=1, label="", text=lyr, syllabic="single",
                        provenance=lp))
            # 和弦（§6.6/§10.2：解析失敗保 rawText；拍位無和弦時，小節首拍用 chordText 兜底）
            chord_src = (b.get("chord") or (m.get("chordText") if ev_tick == 0 else "") or "").strip()
            if chord_src:
                # 小節級 chordText 可能是「一整行多和弦並列」（如 "C G Am"）→ 拆開各成一個槽；
                # 拍級 chord 單一 → 一個槽。位置未知 → 全挂首拍事件（誠實：不補造時值）。
                names = chord_src.split()
                for j, cname in enumerate(names):
                    parsed = parse_chord(cname)
                    ev.chords.append(ChordRef(
                        id=stable_uuid("chord", project_id, part.id, str(mi), str(b.get("beat")),
                                       str(j) if len(names) > 1 else "0"),
                        anchorType="event", anchorId=ev.id, offsetTick=0,
                        rawText=cname, parsed=parsed,
                        provenance=Provenance(source=src, page=page, rawToken=cname,
                                                confidence=conf,
                                                reviewStatus="verified" if parsed else "needs_review",
                                                reviewReason=None if parsed else "unknown_symbol")))
            ev_tick += ev.durationTicks
            measure.events.append(ev)
        part.measures.append(measure)

    # 原圖頁（§6.1 sourcePages）
    sp = omr_result.get("sourcePage")
    src_name = omr_result.get("sourceName") or ""
    if src_name:
        doc.sourcePages.append(SourcePage(
            id=stable_uuid("page", project_id, "1"), index=1, file=src_name))

    # 溯源保留（§3.2/§7.1）
    doc.extensions["rawOmr"] = f"data/projects/{project_id}/project.json"
    doc.extensions["legacyDocument"] = {
        "key": key, "timeSignature": f"{ts_beats}/{ts_type}", "tempo": tempo,
        "engineMode": engine_mode, "sourceName": src_name,
    }
    doc.audit = Audit(createdAt=now_iso(), updatedAt=now_iso(), revision=1)
    return doc
