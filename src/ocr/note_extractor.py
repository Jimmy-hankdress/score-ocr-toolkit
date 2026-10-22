import cv2
import numpy as np
import xml.etree.ElementTree as ET
from pathlib import Path
from typing import List, Optional
from src.ocr.recognizer import Symbol


def parse_musicxml_notes(xml_path: str) -> List[dict]:
    """從 MusicXML 檔案中解析音符資訊（音高、時值、小節等）。"""
    path = Path(xml_path)
    if not path.exists():
        return []

    notes = []
    try:
        tree = ET.parse(str(path))
        root = tree.getroot()
        measure_idx = 0
        for measure in root.iter("measure"):
            measure_idx += 1
            for note in measure.findall("note"):
                # 檢查是否為休止符
                is_rest = note.find("rest") is not None
                is_chord = note.find("chord") is not None

                pitch_elem = note.find("pitch")
                pitch_str = None
                if pitch_elem is not None:
                    step = pitch_elem.findtext("step", "")
                    octave = pitch_elem.findtext("octave", "")
                    alter = pitch_elem.findtext("alter", "0")
                    accidental = "#" if alter == "1" else ("b" if alter == "-1" else "")
                    pitch_str = f"{step}{accidental}{octave}"

                dur_type = note.findtext("type", "quarter")
                note_type = "rest" if is_rest else ("chord" if is_chord else "note")

                notes.append(
                    {
                        "type": note_type,
                        "pitch": pitch_str,
                        "duration": dur_type,
                        "measure": measure_idx,
                    }
                )
    except Exception as e:
        print(f"Error parsing MusicXML notes: {e}")
    return notes


def extract_score_symbols(
    image_path: str,
    musicxml_path: Optional[str] = None,
) -> List[Symbol]:
    """利用 OpenCV 形態學運算去除五線譜線並提取音符外框 (Bounding Box)，
    並與 MusicXML 解析的音高／時值進行對齊。
    """
    img = cv2.imread(str(image_path), cv2.IMREAD_GRAYSCALE)
    if img is None:
        return []

    h_img, w_img = img.shape
    # 二值化反轉 (音符與線條變白，背景黑)
    _, thresh = cv2.threshold(
        img, 0, 255, cv2.THRESH_BINARY_INV + cv2.THRESH_OTSU
    )

    # 水平形態學核心去除五線譜橫線
    line_len = max(20, w_img // 40)
    horiz_kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (line_len, 1))
    staff_lines = cv2.morphologyEx(thresh, cv2.MORPH_OPEN, horiz_kernel)
    notes_only = cv2.subtract(thresh, staff_lines)

    # 濾波去噪以凸顯音符頭
    blob_kernel = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (3, 3))
    cleaned = cv2.morphologyEx(notes_only, cv2.MORPH_OPEN, blob_kernel)

    # 尋找音符輪廓
    contours, _ = cv2.findContours(
        cleaned, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE
    )

    boxes = []
    for c in contours:
        x, y, w, h = cv2.boundingRect(c)
        area = cv2.contourArea(c)
        # 篩選合理音符頭面積與寬高
        if 12 < area < 450 and 6 <= w <= 36 and 6 <= h <= 36:
            boxes.append((x, y, w, h))

    # 依照人類讀譜順序排序 (分行依 y 座標區間群組，同群組再依 x 由左至右)
    row_height = max(50, h_img // 15)
    boxes.sort(key=lambda b: (b[1] // row_height, b[0]))

    # 若有 MusicXML，載入已解析的音符
    xml_notes = parse_musicxml_notes(musicxml_path) if musicxml_path else []

    symbols: List[Symbol] = []
    total_boxes = len(boxes)

    for i, (x, y, w, h) in enumerate(boxes):
        sym_id = f"sym-{i+1}"
        sym_type = "note"
        pitch = None
        duration = "quarter"
        confidence = 0.92

        if i < len(xml_notes):
            n_data = xml_notes[i]
            pitch = n_data.get("pitch")
            duration = n_data.get("duration", "quarter")
            sym_type = n_data.get("type", "note")
            confidence = 0.95

        symbols.append(
            Symbol(
                id=sym_id,
                type=sym_type,
                pitch=pitch,
                duration=duration,
                x=int(x),
                y=int(y),
                width=int(w),
                height=int(h),
                confidence=confidence,
            )
        )

    return symbols
