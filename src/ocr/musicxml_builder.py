import xml.etree.ElementTree as ET
from xml.dom import minidom
from pathlib import Path
from typing import List, Dict, Any


def symbols_to_musicxml(symbols: List[Dict[str, Any]], title: str = "ScoreOCR Corrected Score") -> str:
    """將校對後的 Symbol 列表組裝為標準 MusicXML 4.0 格式字串。"""
    root = ET.Element("score-partwise", version="4.0")
    
    # 標題
    work = ET.SubElement(root, "work")
    work_title = ET.SubElement(work, "work-title")
    work_title.text = title

    # 軟體標記
    identification = ET.SubElement(root, "identification")
    encoding = ET.SubElement(identification, "encoding")
    software = ET.SubElement(encoding, "software")
    software.text = "ScoreOCR Toolkit Visual Editor"

    # 聲部列表
    part_list = ET.SubElement(root, "part-list")
    score_part = ET.SubElement(part_list, "score-part", id="P1")
    part_name = ET.SubElement(score_part, "part-name")
    part_name.text = "Music"

    part = ET.SubElement(root, "part", id="P1")

    # 依每小節約 4 個四分音符分小節
    measure_num = 1
    measure = ET.SubElement(part, "measure", number=str(measure_num))

    # 第一小節設定屬性 (譜號與調號)
    attributes = ET.SubElement(measure, "attributes")
    divisions = ET.SubElement(attributes, "divisions")
    divisions.text = "4"
    
    key = ET.SubElement(attributes, "key")
    fifths = ET.SubElement(key, "fifths")
    fifths.text = "0"

    time = ET.SubElement(attributes, "time")
    beats = ET.SubElement(time, "beats")
    beats.text = "4"
    beat_type = ET.SubElement(time, "beat-type")
    beat_type.text = "4"

    clef = ET.SubElement(attributes, "clef")
    sign = ET.SubElement(clef, "sign")
    sign.text = "G"
    line = ET.SubElement(clef, "line")
    line.text = "2"

    measure_beats = 0
    duration_map = {
        "whole": 16,
        "half": 8,
        "quarter": 4,
        "eighth": 2,
        "16th": 1,
        "32nd": 0.5
    }

    for sym in symbols:
        dur_name = sym.get("duration", "quarter")
        dur_val = duration_map.get(dur_name, 4)

        if measure_beats + dur_val > 16:
            # 建立新小節
            measure_num += 1
            measure = ET.SubElement(part, "measure", number=str(measure_num))
            measure_beats = 0

        note_elem = ET.SubElement(measure, "note")

        if sym.get("type") == "chord":
            ET.SubElement(note_elem, "chord")

        if sym.get("type") == "rest" or not sym.get("pitch"):
            ET.SubElement(note_elem, "rest")
        else:
            # 解析音高 C#4, Bb3 等
            p_str = sym.get("pitch", "C4")
            step = p_str[0] if p_str else "C"
            accidental = ""
            octave = "4"
            
            rest_str = p_str[1:]
            if rest_str.startswith("#"):
                accidental = "1"
                octave = rest_str[1:] if len(rest_str) > 1 else "4"
            elif rest_str.startswith("b"):
                accidental = "-1"
                octave = rest_str[1:] if len(rest_str) > 1 else "4"
            else:
                octave = rest_str if rest_str else "4"

            pitch_elem = ET.SubElement(note_elem, "pitch")
            step_elem = ET.SubElement(pitch_elem, "step")
            step_elem.text = step

            if accidental:
                alter_elem = ET.SubElement(pitch_elem, "alter")
                alter_elem.text = accidental

            octave_elem = ET.SubElement(pitch_elem, "octave")
            octave_elem.text = str(octave)

        dur_elem = ET.SubElement(note_elem, "duration")
        dur_elem.text = str(int(dur_val))

        type_elem = ET.SubElement(note_elem, "type")
        type_elem.text = dur_name

        measure_beats += dur_val

    # 輸出 XML 字串
    xml_str = ET.tostring(root, encoding="utf-8")
    reparsed = minidom.parseString(xml_str)
    return reparsed.toprettyxml(indent="  ")
