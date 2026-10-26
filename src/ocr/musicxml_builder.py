import xml.etree.ElementTree as ET
from typing import Any
from xml.dom import minidom

import src.ocr.jianpu_converter as jianpu_converter
from src.ocr.config import get_config
from src.ocr.logging_config import get_logger

logger = get_logger(__name__)

# 從配置取得 MusicXML 預設值
_cfg = get_config()
# 使用 divisions=8 確保 32nd note = 1 (最小單位)
# whole=32, half=16, quarter=8, eighth=4, 16th=2, 32nd=1
_DIVISIONS = 8
DURATION_MAP = {
    "whole": _DIVISIONS * 4,    # 32
    "half": _DIVISIONS * 2,     # 16
    "quarter": _DIVISIONS,      # 8
    "eighth": _DIVISIONS // 2,  # 4
    "16th": _DIVISIONS // 4,    # 2
    "32nd": _DIVISIONS // 8,    # 1
}

MEASURE_DIVISIONS = _DIVISIONS * 4  # 32 (4 quarter notes per measure)


def _parse_pitch_for_musicxml(pitch_str: str | None) -> tuple[str, int, int]:
    """
    解析音高字串為 MusicXML 所需的 (step, alter, octave)。

    Args:
        pitch_str: 音高字串，如 "C4", "F#5", "Bb3", "C##4", "Dbb3"

    Returns:
        (step, alter, octave) - step: A-G, alter: 半音調整(-2..2), octave: 整數
    """
    if not pitch_str:
        return "C", 0, 4

    parsed = jianpu_converter.parse_pitch(pitch_str)
    if not parsed:
        logger.warning("無法解析音高 '%s'，使用預設值 C4", pitch_str)
        return "C", 0, 4

    step, acc, octave = parsed

    # 將臨時記號轉換為 MusicXML alter 值
    alter_map = {
        "": 0,
        "#": 1,
        "##": 2,
        "b": -1,
        "bb": -2,
    }
    alter = alter_map.get(acc, 0)

    return step, alter, octave


def symbols_to_musicxml(
    symbols: list[dict[str, Any]],
    title: str = "ScoreOCR Corrected Score",
    key_fifths: int = 0,
    time_beats: int = 4,
    time_beat_type: int = 4,
    clef_sign: str = "G",
    clef_line: int = 2,
) -> str:
    """
    將校對後的 Symbol 列表組裝為標準 MusicXML 4.0 格式字串。

    Args:
        symbols: 音符符號列表（dict 或 Symbol dataclass）
        title: 樂譜標題
        key_fifths: 調號（五度圈位置，正為升號、負為降號）
        time_beats: 拍號分子
        time_beat_type: 拍號分母
        clef_sign: 譜號類型 (G, F, C)
        clef_line: 譜號所在線

    Returns:
        格式化的 MusicXML 字串
    """
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
    divisions.text = str(_DIVISIONS)

    key = ET.SubElement(attributes, "key")
    fifths = ET.SubElement(key, "fifths")
    fifths.text = str(key_fifths)

    time = ET.SubElement(attributes, "time")
    beats = ET.SubElement(time, "beats")
    beats.text = str(time_beats)
    beat_type = ET.SubElement(time, "beat-type")
    beat_type.text = str(time_beat_type)

    clef = ET.SubElement(attributes, "clef")
    sign = ET.SubElement(clef, "sign")
    sign.text = clef_sign
    line = ET.SubElement(clef, "line")
    line.text = str(clef_line)

    measure_beats = 0

    for item in symbols:
        # 兼容 dict 或 Symbol dataclass 物件
        if hasattr(item, "__dataclass_fields__"):
            sym = {k: getattr(item, k) for k in item.__dataclass_fields__}
        elif isinstance(item, dict):
            sym = item
        else:
            sym = getattr(item, "__dict__", {})

        dur_name = sym.get("duration", "quarter")
        dur_val = DURATION_MAP.get(dur_name, _cfg.musicxml_divisions)

        if measure_beats + dur_val > MEASURE_DIVISIONS:
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
            # 使用統一的音高解析函數
            p_str = sym.get("pitch", "C4")
            step, alter, octave = _parse_pitch_for_musicxml(p_str)

            pitch_elem = ET.SubElement(note_elem, "pitch")
            step_elem = ET.SubElement(pitch_elem, "step")
            step_elem.text = step

            if alter != 0:
                alter_elem = ET.SubElement(pitch_elem, "alter")
                alter_elem.text = str(alter)

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
