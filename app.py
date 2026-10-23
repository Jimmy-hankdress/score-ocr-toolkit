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

from src.ocr.recognizer import symbols_to_dict
from src.ocr.homr_recognizer import HomrRecognizer
from src.ocr.note_extractor import extract_score_symbols
from src.ocr.musicxml_builder import symbols_to_musicxml

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

    return {
        "filename": "tabi.png",
        "image_url": f"/files/processed/{dest_img.name}",
        "symbol_count": len(symbols),
        "symbols": symbols_to_dict(symbols),
        "musicxml": f"/download/{sample_xml.name}" if sample_xml.exists() else None,
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
def download_musicxml(filename: str):
    xml_path = PROCESSED_DIR / filename
    if not xml_path.exists():
        return JSONResponse(
            {"error": "MusicXML file not found"},
            status_code=404,
        )
    return FileResponse(
        xml_path,
        media_type="application/vnd.recordare.musicxml+xml",
        filename=filename,
    )


@app.post("/recognize")
async def recognize(file: UploadFile = File(...)):
    contents = await file.read()
    binary = preprocess_image(contents)

    # 安全路徑命名：保留原本名稱作為標題，同時生成 ASCII/UUID 安全磁碟檔名
    ext = Path(file.filename).suffix.lower() or ".png"
    safe_token = uuid.uuid4().hex[:8]
    safe_base = re.sub(r"[^a-zA-Z0-9_\-]", "_", Path(file.filename).stem) or "score"
    raw_filename = f"raw_{safe_token}_{safe_base}{ext}"
    proc_filename = f"proc_{safe_token}_{safe_base}.png"

    raw_path = PROCESSED_DIR / raw_filename
    proc_path = PROCESSED_DIR / proc_filename

    # 保存原始未二值化檔案 (HOMR 深度學習模型在原始自然照片/掃描圖上表現最佳)
    raw_path.write_bytes(contents)

    # 安全寫入二值化圖 (避免 Windows 非 ASCII 檔名在 OpenCV 中寫入失敗)
    success, encoded_img = cv2.imencode(".png", binary)
    if success:
        encoded_img.tofile(str(proc_path))

    # 執行辨識
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
                "建議：請改為上傳標準五線譜圖片 (如鋼琴、管弦樂譜)；或者您仍可利用畫布的「新增音符」工具直接手動標註！"
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
            suggestion = "請確認圖片為清晰的樂譜掃描圖或照片。"

        return JSONResponse(
            {
                "success": False,
                "filename": file.filename,
                "image_url": f"/files/processed/{raw_filename}",
                "error_type": error_type,
                "error": friendly_error,
                "suggestion": suggestion,
                "detail": err_msg,
                "symbol_count": 0,
                "symbols": [],
                "musicxml": None,
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

    return {
        "success": True,
        "filename": file.filename,
        "image_url": f"/files/processed/{raw_filename}",
        "symbol_count": len(symbols),
        "symbols": symbols_to_dict(symbols),
        "musicxml": f"/download/{xml_name}" if has_xml else None,
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
