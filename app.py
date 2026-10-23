from fastapi import FastAPI, UploadFile, File, Body, Response
from fastapi.responses import JSONResponse, FileResponse
from fastapi.staticfiles import StaticFiles
from pathlib import Path
import cv2
import numpy as np
from PIL import Image
import io
import sys
import re
import uuid
from typing import List, Dict, Any

from src.ocr.recognizer import Symbol, symbols_to_dict
from src.ocr.homr_recognizer import HomrRecognizer
from src.ocr.note_extractor import extract_score_symbols
from src.ocr.musicxml_builder import symbols_to_musicxml
from src.ocr.format_importer import (
    import_file_to_image_and_symbols,
    SUPPORTED_EXTENSIONS,
)
from src.ocr.jianpu_converter import (
    pitch_to_jianpu,
    symbols_to_jianpu_text,
    symbol_to_jianpu_notation,
)

app = FastAPI(title="ScoreOCR Toolkit")

BASE_DIR = Path(__file__).resolve().parent
UPLOAD_DIR = BASE_DIR / "uploads"
PROCESSED_DIR = BASE_DIR / "processed"
STATIC_DIR = BASE_DIR / "static"

UPLOAD_DIR.mkdir(exist_ok=True)
PROCESSED_DIR.mkdir(exist_ok=True)
STATIC_DIR.mkdir(exist_ok=True)

# 掛載靜態資源與圖片路徑
app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")
app.mount("/files/processed", StaticFiles(directory=str(PROCESSED_DIR)), name="processed_files")
app.mount("/files/uploads", StaticFiles(directory=str(UPLOAD_DIR)), name="upload_files")


def preprocess_image(contents: bytes) -> np.ndarray:
    image = Image.open(io.BytesIO(contents)).convert("L")
    array = np.array(image)
    blurred = cv2.GaussianBlur(array, (3, 3), 0)
    _, binary = cv2.threshold(
        blurred, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU
    )
    return binary


recognizer = HomrRecognizer(python_executable=sys.executable)


@app.get("/")
@app.get("/ui")
def index_ui():
    index_file = STATIC_DIR / "index.html"
    if index_file.exists():
        return FileResponse(index_file)
    return {
        "name": "ScoreOCR Toolkit",
        "status": "MVP",
        "endpoints": {
            "ui": "/ui",
            "upload": "/upload",
            "recognize": "/recognize",
            "download": "/download/{filename}",
            "health": "/health",
        },
    }


@app.get("/health")
def health():
    return {"status": "ok"}


@app.get("/favicon.ico")
def get_favicon():
    favicon_path = STATIC_DIR / "favicon.ico"
    if favicon_path.exists():
        return FileResponse(favicon_path, media_type="image/x-icon")
    return Response(status_code=204)


@app.get("/api/sample")
def get_sample_score():
    """載入內建模範樂譜 (tabi.png) 與已提取之音符框，供視覺化畫布快速示範與測試。"""
    sample_img = BASE_DIR / "tabi.png"
    sample_xml = PROCESSED_DIR / "recognize_tabi.musicxml"

    if not sample_img.exists():
        return JSONResponse({"error": "Sample image not found"}, status_code=404)

    # 確保 processed 內有一份可供瀏覽器存取
    dest_img = PROCESSED_DIR / "sample_tabi.png"
    if not dest_img.exists():
        dest_img.write_bytes(sample_img.read_bytes())

    xml_path_str = str(sample_xml) if sample_xml.exists() else None
    symbols = extract_score_symbols(str(sample_img), xml_path_str)

    jianpu_text = symbols_to_jianpu_text(symbols, title="Tabi Sample Score")
    jianpu_name = "sample_tabi_jianpu.txt"
    (PROCESSED_DIR / jianpu_name).write_text(jianpu_text, encoding="utf-8")

    return {
        "filename": "tabi.png",
        "image_url": f"/files/processed/{dest_img.name}",
        "symbol_count": len(symbols),
        "symbols": symbols_to_dict(symbols),
        "musicxml": f"/download/{sample_xml.name}" if sample_xml.exists() else None,
        "jianpu_file": f"/download/{jianpu_name}",
        "jianpu_url": f"/download/{jianpu_name}",
        "jianpu_text": jianpu_text,
    }


@app.post("/upload")
async def upload(file: UploadFile = File(...)):
    contents = await file.read()
    binary = preprocess_image(contents)

    input_path = UPLOAD_DIR / file.filename
    output_path = PROCESSED_DIR / f"processed_{file.filename}"

    input_path.write_bytes(contents)
    cv2.imwrite(str(output_path), binary)

    return JSONResponse(
        {
            "filename": file.filename,
            "uploaded": str(input_path),
            "processed": str(output_path),
            "next_step": "OMR recognition",
        }
    )


@app.get("/download/{filename}")
def download_file(filename: str):
    file_path = PROCESSED_DIR / filename
    if not file_path.exists():
        return JSONResponse(
            {"error": "File not found"},
            status_code=404,
        )

    ext = file_path.suffix.lower()
    media_types = {
        ".musicxml": "application/vnd.recordare.musicxml+xml",
        ".xml": "application/xml",
        ".txt": "text/plain; charset=utf-8",
        ".jianpu": "text/plain; charset=utf-8",
        ".json": "application/json",
        ".png": "image/png",
        ".jpg": "image/jpeg",
        ".jpeg": "image/jpeg",
    }
    media_type = media_types.get(ext, "application/octet-stream")
    return FileResponse(
        file_path,
        media_type=media_type,
        filename=filename,
    )


@app.post("/recognize")
async def recognize(file: UploadFile = File(...)):
    contents = await file.read()

    # 安全路徑命名：保留原本名稱作為標題，同時生成 ASCII/UUID 安全磁碟檔名
    safe_token = uuid.uuid4().hex[:8]
    safe_base = re.sub(r"[^a-zA-Z0-9_\-]", "_", Path(file.filename).stem) or "score"

    # 多格式相容解析 (支援 PDF, DOCX, TXT, JSON, BMP, WEBP, TIFF, PNG, JPG)
    try:
        pil_image, pre_symbols, fmt_type = import_file_to_image_and_symbols(
            contents, file.filename
        )
    except Exception as parse_err:
        return JSONResponse(
            {
                "success": False,
                "filename": file.filename,
                "error_type": "FORMAT_PARSE_ERROR",
                "error": f"解析檔案失敗: {str(parse_err)}",
                "suggestion": f"目前支援格式包含: {', '.join(sorted(SUPPORTED_EXTENSIONS))}。請確認檔案內容或格式是否正確。",
                "symbol_count": 0,
                "symbols": [],
                "musicxml": None,
                "jianpu_file": None,
                "jianpu_text": "",
            },
            status_code=400,
        )

    # 統一將渲染或提取出的樂譜影像存為標準 PNG 供畫布與 OMR 讀取
    raw_filename = f"raw_{safe_token}_{safe_base}.png"
    raw_path = PROCESSED_DIR / raw_filename
    pil_image.save(raw_path, format="PNG")

    # 若為 TXT、JSON 或 Word 文字簡譜，已在 importer 中成功提取音符符號
    if pre_symbols:
        xml_name = f"recognize_{safe_base}_{safe_token}.musicxml"
        target_xml = PROCESSED_DIR / xml_name
        xml_content = symbols_to_musicxml(pre_symbols, title=Path(file.filename).stem)
        target_xml.write_text(xml_content, encoding="utf-8")

        jianpu_text = symbols_to_jianpu_text(pre_symbols, title=Path(file.filename).stem)
        jianpu_name = f"jianpu_{safe_base}_{safe_token}.txt"
        (PROCESSED_DIR / jianpu_name).write_text(jianpu_text, encoding="utf-8")

        return {
            "success": True,
            "format_type": fmt_type,
            "filename": file.filename,
            "image_url": f"/files/processed/{raw_filename}",
            "symbol_count": len(pre_symbols),
            "symbols": symbols_to_dict(pre_symbols),
            "musicxml": f"/download/{xml_name}",
            "jianpu_file": f"/download/{jianpu_name}",
            "jianpu_url": f"/download/{jianpu_name}",
            "jianpu_text": jianpu_text,
        }

    # 否則進入神經網路 OMR 引擎 (支援標準五線譜影像：PDF 渲染圖、Word 樂譜插圖、BMP/PNG/JPG 等)
    try:
        symbols = recognizer.recognize(str(raw_path))
    except Exception as e:
        err_msg = str(e)
        if "No staffs found" in err_msg:
            error_type = "NO_STAFFS_FOUND"
            friendly_error = "未在影像中檢測到標準五線譜線系統 (No staffs found)。"
            suggestion = (
                "目前 HOMR 辨識核心專為「標準五線譜 (Western Staff Notation)」設計；"
                "若您上傳的是「簡譜 / 數字譜 (1 2 3...)」、「吉他六線譜 (TAB)」或「純歌詞和弦譜」，AI 尚無法自動辨識。\n\n"
                "建議：\n"
                "1. 若為簡譜文本，可直接儲存為 .txt 或 .docx 文字檔上傳，系統將自動解析為簡譜！\n"
                "2. 若為樂譜圖片，您可利用畫布的「新增音符」工具直接手動標註並即時轉為簡譜！"
            )
        elif "No noteheads found" in err_msg:
            error_type = "NO_NOTEHEADS_FOUND"
            friendly_error = "五線譜中未檢測到清晰音符頭 (No noteheads found)。"
            suggestion = "請確認樂譜圖片解析度足夠且未過度模糊、過暗或曝光過度。"
        elif "No clefs found" in err_msg:
            error_type = "NO_CLEFS_FOUND"
            friendly_error = "未檢測到譜號 (Clef)。"
            suggestion = "請確認樂譜影像開頭包含清楚的高音譜號或低音譜號。"
        else:
            error_type = "OMR_PROCESSING_ERROR"
            friendly_error = f"OMR 辨識過程發生異常: {err_msg[:200]}"
            suggestion = "請確認檔案為清晰的樂譜掃描圖、PDF 或照片。"

        return JSONResponse(
            {
                "success": False,
                "format_type": fmt_type,
                "filename": file.filename,
                "image_url": f"/files/processed/{raw_filename}",
                "error_type": error_type,
                "error": friendly_error,
                "suggestion": suggestion,
                "detail": err_msg,
                "symbol_count": 0,
                "symbols": [],
                "musicxml": None,
                "jianpu_file": None,
                "jianpu_text": "",
            },
            status_code=200,
        )

    xml_name = f"recognize_{safe_base}_{safe_token}.musicxml"
    xml_path = raw_path.with_suffix(".musicxml")
    target_xml = PROCESSED_DIR / xml_name

    has_xml = False
    if xml_path.exists():
        if xml_path.resolve() != target_xml.resolve():
            if target_xml.exists():
                target_xml.unlink()
            xml_path.rename(target_xml)
        has_xml = True
    elif target_xml.exists():
        has_xml = True

    # 同時產生簡譜音符文字檔 (.txt)
    jianpu_text = symbols_to_jianpu_text(symbols, title=Path(file.filename).stem)
    jianpu_name = f"jianpu_{safe_base}_{safe_token}.txt"
    (PROCESSED_DIR / jianpu_name).write_text(jianpu_text, encoding="utf-8")

    return {
        "success": True,
        "format_type": fmt_type,
        "filename": file.filename,
        "image_url": f"/files/processed/{raw_filename}",
        "symbol_count": len(symbols),
        "symbols": symbols_to_dict(symbols),
        "musicxml": f"/download/{xml_name}" if has_xml else None,
        "jianpu_file": f"/download/{jianpu_name}",
        "jianpu_url": f"/download/{jianpu_name}",
        "jianpu_text": jianpu_text,
    }


@app.post("/api/export-jianpu")
async def export_jianpu(payload: Dict[str, Any] = Body(...)):
    """將畫布校對修改後的音符列表編譯為簡譜文字格式 (.txt) 供下載與複製。"""
    raw_symbols = payload.get("symbols", [])
    if not raw_symbols:
        return JSONResponse({"error": "No symbols provided"}, status_code=400)

    title = payload.get("title", "ScoreOCR Jianpu Score")
    key = payload.get("key", "C")
    meter = payload.get("meter", "4/4")

    symbols = [
        Symbol(
            id=s.get("id", f"sym-{i+1}"),
            type=s.get("type", "note"),
            pitch=s.get("pitch"),
            duration=s.get("duration", "quarter"),
            x=int(s.get("x", 0)),
            y=int(s.get("y", 0)),
            width=int(s.get("width", 20)),
            height=int(s.get("height", 18)),
            confidence=float(s.get("confidence", 1.0)),
        )
        for i, s in enumerate(raw_symbols)
    ]

    try:
        jianpu_text = symbols_to_jianpu_text(symbols, title=title, key=key, meter=meter)
        output_filename = f"jianpu_{uuid.uuid4().hex[:8]}.txt"
        output_file = PROCESSED_DIR / output_filename
        output_file.write_text(jianpu_text, encoding="utf-8")

        return {
            "status": "ok",
            "message": "Jianpu score generated successfully",
            "download_url": f"/download/{output_file.name}",
            "jianpu_text": jianpu_text,
        }
    except Exception as e:
        return JSONResponse({"error": f"Failed to export Jianpu: {str(e)}"}, status_code=500)


@app.post("/api/convert-to-jianpu")
async def convert_to_jianpu(payload: Dict[str, Any] = Body(...)):
    """即時轉換 Symbol 清單為簡譜純文字與個別音符之簡譜標籤 (供畫布即時渲染與面板預覽)"""
    raw_symbols = payload.get("symbols", [])
    key = payload.get("key", "C")
    meter = payload.get("meter", "4/4")

    symbols = [
        Symbol(
            id=s.get("id", f"sym-{i+1}"),
            type=s.get("type", "note"),
            pitch=s.get("pitch"),
            duration=s.get("duration", "quarter"),
            x=int(s.get("x", 0)),
            y=int(s.get("y", 0)),
            width=int(s.get("width", 20)),
            height=int(s.get("height", 18)),
            confidence=float(s.get("confidence", 1.0)),
        )
        for i, s in enumerate(raw_symbols)
    ]

    tag_map = {
        s.id: pitch_to_jianpu(s.pitch, key=key) if s.pitch else "0"
        for s in symbols
    }
    full_text = symbols_to_jianpu_text(symbols, title="Score", key=key, meter=meter)

    return {
        "status": "ok",
        "tag_map": tag_map,
        "jianpu_text": full_text,
    }


@app.post("/api/export-musicxml")
async def export_corrected_musicxml(payload: Dict[str, Any] = Body(...)):
    """將畫布校對修改後的 Symbol 列表編譯為標準 MusicXML 供下載。"""
    symbols = payload.get("symbols", [])
    if not symbols:
        return JSONResponse({"error": "No symbols provided"}, status_code=400)

    try:
        xml_content = symbols_to_musicxml(symbols, title="ScoreOCR Edited Score")
        output_file = PROCESSED_DIR / "corrected_score.musicxml"
        output_file.write_text(xml_content, encoding="utf-8")

        return {
            "status": "ok",
            "message": "Corrected MusicXML generated successfully",
            "download_url": f"/download/{output_file.name}",
        }
    except Exception as e:
        return JSONResponse({"error": f"Failed to export MusicXML: {str(e)}"}, status_code=500)
