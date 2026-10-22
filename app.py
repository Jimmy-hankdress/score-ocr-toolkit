from fastapi import FastAPI, UploadFile, File, Body
from fastapi.responses import JSONResponse, FileResponse
from fastapi.staticfiles import StaticFiles
from pathlib import Path
import cv2
import numpy as np
from PIL import Image
import io
import sys
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

    temp_path = PROCESSED_DIR / f"recognize_{file.filename}"
    cv2.imwrite(str(temp_path), binary)

    try:
        symbols = recognizer.recognize(str(temp_path))
    except Exception as e:
        return JSONResponse(
            {
                "filename": file.filename,
                "error": str(e),
                "symbol_count": 0,
                "symbols": [],
                "musicxml": None,
            },
            status_code=422,
        )

    xml_name = f"recognize_{Path(file.filename).stem}.musicxml"
    xml_path = temp_path.with_suffix(".musicxml")
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
        "filename": file.filename,
        "image_url": f"/files/processed/{temp_path.name}",
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
