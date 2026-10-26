# -*- coding: utf-8 -*-
"""
jpeditor OMR 引擎封裝（Node.js + dist-cli/omr.js）。
輸出 MusicXML 字串，由 V2.01 內部 musicxml.py 轉成 ScoreDocument。

責任：
- detect_jpeditor()：回報 jpeditor 是否就緒（Node、omr.js、模型）
- recognize_score(path)：呼叫 node wrapper，回傳 MusicXML 字串 + 型別
- jpeditor_musicxml_to_document(xml, page)：把 MusicXML 轉成 ScoreDocument，
  供 pipeline 後端的 lines_to_measures / build_musicxml 不需改
"""
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

# jpeditor 倉庫與 wrapper（固定絕對路徑，避免 cwd 攪錯）
JPEDITOR_REPO = Path(r"C:\Users\hankdress\HermesMemoryBank\jpeditor-repo")
JPEDITOR_WRAPPER = JPEDITOR_REPO / "jpeditor_omr_wrapper.mjs"
JPEDITOR_OMR_JS = JPEDITOR_REPO / "dist-cli" / "omr.js"


def detect_jpeditor() -> dict:
    """回傳可給前端展示的 jpeditor 引擎狀態。"""
    status: dict = {
        "available": False,
        "mode": "jpeditor-unavailable",
        "version": "",
        "path": "",
        "note": "",
    }
    if not JPEDITOR_WRAPPER.exists():
        status["note"] = f"jpeditor wrapper 不存在：{JPEDITOR_WRAPPER}"
        return status

    if not JPEDITOR_OMR_JS.exists():
        status["note"] = f"jpeditor dist-cli/omr.js 不存在：{JPEDITOR_OMR_JS}"
        return status

    # Node.js 是否可用
    try:
        proc = subprocess.run(
            ["node", "--version"],
            capture_output=True, text=True, timeout=10,
        )
        if proc.returncode != 0:
            status["note"] = "Node.js 不可用"
            return status
        status["version"] = proc.stdout.strip()
    except (OSError, subprocess.SubprocessError) as exc:
        status["note"] = f"無法執行 Node.js：{exc}"
        return status

    status["available"] = True
    status["mode"] = "jpeditor"
    status["path"] = str(JPEDITOR_WRAPPER)
    status["note"] = ""
    return status


def recognize_score(image_path: Path) -> dict:
    """
    用 jpeditor 辨識一張圖片，回傳 MusicXML 字串。
    回傳格式：
        {
          "ok": bool,
          "format": "musicxml",            # 固定為 musicxml
          "musicxml": str | None,           # 成功時的 MusicXML 內容
          "note": str | None,               # 失敗時的說明
          "raw": dict | None,               # wrapper 原始回應（除錯用）
        }
    """
    if not image_path.exists():
        return {"ok": False, "format": "musicxml", "note": f"圖片不存在：{image_path}"}

    try:
            proc = subprocess.run(
                [
                    "node",
                    str(JPEDITOR_WRAPPER),
                    str(image_path.resolve()),
                    "musicxml",
                ],
                capture_output=True,
                text=True,
                timeout=300,
                cwd=JPEDITOR_REPO,
            )
    except (OSError, subprocess.SubprocessError) as exc:
        return {"ok": False, "format": "musicxml", "note": f"執行 Node.js 失敗：{exc}"}

    raw: dict = {}
    try:
        raw = json.loads(proc.stdout)
    except (json.JSONDecodeError, ValueError) as exc:
        return {
            "ok": False,
            "format": "musicxml",
            "note": f"jpeditor 輸出不是有效 JSON（{exc}）：\n{proc.stdout[:1000]}",
            "raw": {"stdout_head": proc.stdout[:1000], "stderr": proc.stderr[:500]},
        }

    # 判斷 jpeditor 實際回的格式
    fmt = str(raw.get("format") or "musicxml").lower()
    if fmt not in ("musicxml", "jpwabc", "pu", "musicxml3"):
        return {
            "ok": False,
            "format": fmt or "unknown",
            "note": f"jpeditor 回了未知格式 '{fmt}'，預期 musicxml / jpwabc / pu",
            "raw": raw,
        }

    # jpeditor wrapper 成功時不設 ok=true，只在失敗時帶 error/message。
    # 因此以明確的 error 旗標判斷成敗，而非「沒有 ok」。
    if raw.get("error"):
        return {
            "ok": False,
            "format": fmt,
            "note": raw.get("message") or "jpeditor 辨識失敗",
            "raw": raw,
        }

    # jpeditor 的 musicxml 可能放在頂層 "musicxml"／"text"，或 detail["musicxml"]
    detail = raw.get("detail") or {}
    musicxml = (
        raw.get("musicxml")
        or raw.get("text")
        or (detail.get("musicxml") if isinstance(detail, dict) else None)
        or ""
    )
    if not musicxml or not str(musicxml).strip().startswith("<?xml"):
        return {
            "ok": False,
            "format": fmt,
            "note": "jpeditor 回的 musicxml 空白或不是 XML（可能模型未載入）：",
            "raw": {k: v for k, v in raw.items() if k not in ("musicxml", "text")},
        }

    return {
        "ok": True,
        "format": "musicxml",
        "musicxml": str(musicxml),
        "raw": raw,
    }


def _fifths_to_key_name(fifths: int) -> str:
    """將 MusicXML 的 key/fifths 轉為簡譜調號名稱。"""
    sharp_keys = ["C", "G", "D", "A", "E", "B", "F#", "C#"]
    flat_keys  = ["C", "F", "Bb", "Eb", "Ab", "Db", "Gb", "Cb"]
    if fifths >= 0:
        return sharp_keys[fifths] if fifths < len(sharp_keys) else "C"
    else:
        return flat_keys[-fifths] if -fifths < len(flat_keys) else "C"


def _parse_musicxml_meta(xml: str, source_name: str) -> tuple[str, str, str, str, str, int, list[str]]:
    """從 MusicXML 字串提取 title、作曲、作詞、key、timeSignature、tempo。"""
    import xml.etree.ElementTree as ET
    warnings: list[str] = []
    try:
        root = ET.fromstring(xml)
    except ET.ParseError as exc:
        warnings.append(f"MusicXML 剖析失敗：{exc}")
        return source_name, "", "", "C", "4/4", 90, warnings

    def find_text(tag_path: str) -> str:
        el = root.find(tag_path)
        if el is not None and el.text:
            return el.text.strip()
        return ""

    title = find_text("work/work-title") or source_name
    composer = ""
    lyricist = ""
    for creator in root.iter("creator"):
        t = (creator.get("type") or "").lower()
        v = (creator.text or "").strip()
        if t == "composer":
            composer = v
        elif t == "lyricist":
            lyricist = v

    key = "C"
    key_el = root.find(".//key/fifths")
    if key_el is not None and key_el.text:
        try:
            fifths = int(key_el.text)
            key = _fifths_to_key_name(fifths)
        except ValueError:
            pass

    timeSig = "4/4"
    time_el = root.find(".//time")
    if time_el is not None:
        beats_el = time_el.find("beats")
        beat_type_el = time_el.find("beat-type")
        if beats_el is not None and beat_type_el is not None:
            b = beats_el.text.strip()
            bt = beat_type_el.text.strip()
            if b.isdigit() and bt.isdigit():
                timeSig = f"{b}/{bt}"

    tempo = 90
    direction = root.find(".//direction/direction-type/metronome")
    if direction is not None:
        pm = direction.find("per-minute")
        if pm is not None and pm.text:
            try:
                tempo = int(pm.text)
            except ValueError:
                pass

    return title, composer, lyricist, key, timeSig, tempo, warnings


def jpeditor_musicxml_to_document(
    xml: str,
    source_name: str = "",
    page_index: int = 0,
) -> dict:
    """
    把 jpeditor 輸出的 MusicXML 字串轉成 ScoreDocument（字典），
    並附帶 musicxml 字串（供 pipeline 直接寫入 exports）。

    回傳：
        {
          "document": ScoreDocument,
          "musicxml": str,          # 原始 musicxml 字串（直接寫入檔案）
          "warnings": list[str],
        }
    若無法剖析，document 為最小可用的文件並附帶警告。
    """
    import xml.etree.ElementTree as ET
    from ..models import ScoreDocument, ScoreMeasure, ScoreBeat, new_id

    warnings: list[str] = []
    if not xml.strip().startswith("<?xml"):
        return {
            "document": None,
            "musicxml": xml,
            "warnings": ["jpeditor musicxml 不是有效 XML"]
        }

    # 剖析 MusicXML
    try:
        root = ET.fromstring(xml)
    except ET.ParseError as exc:
        warnings.append(f"MusicXML 剖析失敗：{exc}")
        doc = ScoreDocument(
            id=new_id("doc"),
            title=source_name or "jpeditor-辨識結果",
            engineMode="jpeditor",
            sourceName=source_name,
            measures=[ScoreMeasure(number=1, beats=[])],
        )
        return {"document": doc, "musicxml": xml, "warnings": warnings}

    # 提取 basic metadata
    def _find_text(path: str) -> str:
        el = root.find(path)
        return el.text.strip() if el is not None and el.text else ""

    title = _find_text("work/work-title") or source_name or "jpeditor-辨識結果"
    composer = ""
    lyricist = ""
    for creator in root.iter("creator"):
        ctype = (creator.get("type") or "").lower()
        ctext = (creator.text or "").strip()
        if ctype == "composer":
            composer = ctext
        elif ctype == "lyricist":
            lyricist = ctext

    # 提取 key（fifths → 調號名稱）
    key = "C"
    key_el = root.find(".//key/fifths")
    if key_el is not None and key_el.text:
        try:
            fifths = int(key_el.text)
            sharp_keys = ["C", "G", "D", "A", "E", "B", "F#", "C#"]
            flat_keys = ["C", "F", "Bb", "Eb", "Ab", "Db", "Gb", "Cb"]
            key = sharp_keys[fifths] if fifths >= 0 and fifths < len(sharp_keys) else (
                flat_keys[-fifths] if fifths < 0 and -fifths < len(flat_keys) else "C"
            )
        except ValueError:
            pass

    # 提取 timeSignature
    timeSig = "4/4"
    time_el = root.find(".//time")
    if time_el is not None:
        beats_el = time_el.find("beats")
        beat_type_el = time_el.find("beat-type")
        if beats_el is not None and beat_type_el is not None:
            b = beats_el.text.strip()
            bt = beat_type_el.text.strip()
            if b.isdigit() and bt.isdigit():
                timeSig = f"{b}/{bt}"

    # 提取 tempo
    tempo = 90
    for direction in root.iter("direction"):
        metronome = direction.find("direction-type/metronome")
        if metronome is not None:
            per_minute = metronome.find("per-minute")
            if per_minute is not None and per_minute.text:
                try:
                    tempo = int(per_minute.text)
                except ValueError:
                    pass
                break

    # 提取 measures 與 beats
    measures: list[ScoreMeasure] = []
    part = root.find("part")
    if part is not None:
        for measure_el in part.findall("measure"):
            m_number = int(measure_el.get("number", str(len(measures) + 1)))
            beats_list: list[ScoreBeat] = []
            beat_counter = 1

            # 取得 divisions 屬性（若有的話）
            divisions_el = measure_el.find("attributes/divisions")
            divisions = 16
            if divisions_el is not None and divisions_el.text:
                try:
                    divisions = int(divisions_el.text)
                except ValueError:
                    pass

            for note_el in measure_el.findall("note"):
                # 和弦
                harmony_el = note_el.find("harmony")
                chord = ""
                if harmony_el is not None:
                    root_step_el = harmony_el.find("root/root-step")
                    if root_step_el is not None and root_step_el.text:
                        chord = root_step_el.text
                        alter_el = harmony_el.find("root/root-alter")
                        if alter_el is not None:
                            if alter_el.text == "1":
                                chord += "#"
                            elif alter_el.text == "-1":
                                chord += "b"
                        kind_el = harmony_el.find("kind")
                        if kind_el is not None and kind_el.text:
                            kind_text = kind_el.text.strip()
                            if kind_text and kind_text not in ("major", ""):
                                chord += kind_text

                # 歌詞
                lyric_text = ""
                lyric_el = note_el.find("lyric")
                if lyric_el is not None:
                    text_el = lyric_el.find("text")
                    if text_el is not None and text_el.text:
                        lyric_text = text_el.text.strip()

                # 休止符
                rest_el = note_el.find("rest")
                if rest_el is not None:
                    dur_el = note_el.find("duration")
                    dur = int(dur_el.text) if dur_el is not None and dur_el.text else 16
                    dur_name = _divisions_to_duration_name(dur, divisions)
                    beats_list.append(ScoreBeat(
                        beat=beat_counter,
                        note="0",
                        lyric=lyric_text,
                        chord=chord,
                        duration=dur_name,
                        confidence=1.0,
                    ))
                    beat_counter += 1
                    continue

                # 音符
                pitch_el = note_el.find("pitch")
                if pitch_el is None:
                    continue

                step_el = pitch_el.find("step")
                alter_el = pitch_el.find("alter")
                octave_el = pitch_el.find("octave")

                if step_el is None or octave_el is None:
                    continue

                step = (step_el.text or "C").upper()
                alter = alter_el.text if alter_el is not None else "0"
                octave = int(octave_el.text or "4")

                # 轉成簡譜 token
                note_token = _pitch_to_jianpu_token(step, alter, octave)

                dur_el = note_el.find("duration")
                dur = int(dur_el.text) if dur_el is not None and dur_el.text else 16
                dur_name = _divisions_to_duration_name(dur, divisions)

                beats_list.append(ScoreBeat(
                    beat=beat_counter,
                    note=note_token,
                    lyric=lyric_text,
                    chord=chord,
                    duration=dur_name,
                    confidence=1.0,
                ))
                beat_counter += 1

            measures.append(ScoreMeasure(
                number=m_number,
                beats=beats_list,
            ))

    # jpeditor 把所有音符塞進單一 <measure>；依拍號重新切分，
    # 讓編輯器顯示標準多小節結構。
    measures = _resplit_measures_by_time_signature(measures, timeSig)

    doc = ScoreDocument(
        id=new_id("doc"),
        title=title,
        composer=composer,
        lyricist=lyricist,
        key=key,
        timeSignature=timeSig,
        tempo=tempo,
        engineMode="jpeditor",
        engineNote="jpeditor MusicXML 輸出",
        sourceName=source_name or title,
        measures=measures,
        updatedAt="",
        createdAt="",
    )
    return {"document": doc, "musicxml": xml, "warnings": warnings}


def _divisions_to_duration_name(dur: int, divisions: int = 16) -> str:
    """將 MusicXML 的 duration（除以 divisions 後的 FourField 單位）轉為 V2.01 的 duration 名稱。"""
    q = dur / divisions if divisions else 1.0
    if q >= 4.0:
        return "whole" if q < 6.0 else "whole"
    if q >= 2.0:
        return "half"
    if q >= 1.0:
        return "quarter"
    if q >= 0.5:
        return "eighth"
    if q >= 0.25:
        return "16th"
    if q >= 0.125:
        return "32nd"
    return "64th"


def _pitch_to_jianpu_token(step: str, alter: str, octave: int) -> str:
    """
    將 MusicXML 的 <pitch>（step/alter/octave）轉為 V3.00 簡譜 token。
    例如 C4 → "1"，D4 → "2"，…，B4 → "7"，高八度加組合高音點 \\u0307，低八度加組合低音點 \\u0323。
    """
    step_map = {"C": 1, "D": 2, "E": 3, "F": 4, "G": 5, "A": 6, "B": 7}
    digit = step_map.get(step.upper(), 1)
    token = str(digit)
    if alter == "1":
        token = f"#{token}"
    elif alter == "-1":
        token = f"b{token}"
    if octave > 4:
        token += "\u0307" * (octave - 4)
    elif octave < 4:
        token += "\u0323" * (4 - octave)
    return token


def _populate_measure_fields(m) -> None:
    """將 ScoreMeasure.beats 同步填入 noteText、lyricText、chordText 與 ticks。"""
    dur_to_quarter = {
        "whole": 4.0, "half": 2.0, "quarter": 1.0, "eighth": 0.5,
        "16th": 0.25, "32nd": 0.125, "64th": 0.0625,
    }
    dur_suffix = {
        "eighth": "_", "16th": "__", "32nd": "___", "64th": "___",
    }
    note_tokens: list[str] = []
    note_ticks: list[int] = []
    lyric_parts: list[str] = []
    lyric_ticks: list[int] = []
    chord_symbols: list[str] = []
    chord_offsets: list[int] = []
    chord_ticks: list[int] = []

    acc_q = 0.0
    for b in m.beats:
        q = dur_to_quarter.get(getattr(b, "duration", "quarter"), 1.0)
        base_note = (b.note or "0").strip()
        suffix = dur_suffix.get(getattr(b, "duration", "quarter"), "")
        tok = base_note + suffix
        tick = int(round(acc_q * 480))
        idx = len(note_tokens)
        note_tokens.append(tok)
        note_ticks.append(tick)

        if (b.lyric or "").strip():
            lyric_parts.append(b.lyric.strip())
            lyric_ticks.append(tick)
        if (b.chord or "").strip():
            chord_symbols.append(b.chord.strip())
            chord_offsets.append(idx)
            chord_ticks.append(tick)

        if q >= 2.0 and base_note != "0":
            extra = max(0, int(round(q)) - 1)
            acc_q += 1.0
            for _ in range(extra):
                note_tokens.append("-")
                note_ticks.append(int(round(acc_q * 480)))
                acc_q += 1.0
        else:
            acc_q += q

    m.noteText = " ".join(note_tokens)
    m.noteTicks = note_ticks
    m.lyricText = "".join(lyric_parts)
    m.lyricTicks = lyric_ticks
    m.chordText = " ".join(chord_symbols)
    m.chordOffsets = chord_offsets
    m.chordTicks = chord_ticks


def _resplit_measures_by_time_signature(measures, time_sig: str):
    """把 jpeditor 扁平化的單一 measure 依拍號重新切成標準多小節。

    jpeditor 的 MusicXML 把所有音符塞在一個 <measure> 裡，
    這裡依拍號與時值把 beats 重新分配到合理的小節。
    若本來就有多個小節則原樣回傳。
    """
    from ..models import ScoreMeasure

    if not measures:
        return measures
    if len(measures) > 1:
        for m in measures:
            _populate_measure_fields(m)
        return measures

    try:
        num_s, den_s = time_sig.split("/")
        beats_per_measure = int(num_s)
        beat_denom = int(den_s)
    except (ValueError, AttributeError):
        for m in measures:
            _populate_measure_fields(m)
        return measures

    # 一拍等於幾個 quarter：4/4→1、2/4→1、3/4→1、4/8→0.5、6/8→0.5
    quarter_per_beat = 4 / beat_denom
    target_quarter_per_measure = beats_per_measure * quarter_per_beat

    dur_to_quarter = {
        "whole": 4, "half": 2, "quarter": 1, "eighth": 0.5,
        "16th": 0.25, "32nd": 0.125, "64th": 0.0625,
    }

    all_beats = [b for m in measures for b in m.beats]
    if not all_beats:
        return measures

    new_measures = []
    current = []
    acc = 0.0
    for b in all_beats:
        q = dur_to_quarter.get(getattr(b, "duration", "quarter"), 1.0)
        # 若加入此音會讓小節超過目標（且非首音），先結算目前小節
        if acc + q > target_quarter_per_measure + 1e-6 and current:
            new_measures.append(ScoreMeasure(number=len(new_measures) + 1, beats=current))
            current = []
            acc = 0.0
        current.append(b)
        acc += q
        if abs(acc - target_quarter_per_measure) <= 1e-6:
            new_measures.append(ScoreMeasure(number=len(new_measures) + 1, beats=current))
            current = []
            acc = 0.0
    if current:
        new_measures.append(ScoreMeasure(number=len(new_measures) + 1, beats=current))

    for i, m in enumerate(new_measures, 1):
        m.number = i
        for j, b in enumerate(m.beats, 1):
            b.beat = j
        _populate_measure_fields(m)
    return new_measures
