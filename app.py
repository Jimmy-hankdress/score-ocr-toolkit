from fastapi import FastAPI, UploadFile, File
from fastapi.responses import JSONResponse, FileResponse
from fastapi.staticfiles import StaticFiles
from pathlib import Path
import cv2
import numpy as np
from PIL import Image
import io
import sys

from src.ocr.recognizer import symbols_to_dict
from src.ocr.homr_recognizer import HomrRecognizer

app = FastAPI(title="ScoreOCR Toolkit")

UPLOAD_DIR = Path("uploads")
PROCESSED_DIR = Path("processed")
UPLOAD_DIR.mkdir(exist_ok=True)
PROCESSED_DIR.mkdir(exist_ok=True)


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
def index():
    return {
        "name": "ScoreOCR Toolkit",
        "status": "MVP",
        "endpoints": {
            "upload": "/upload",
            "health": "/health",
            "recognize": "/recognize",
            "download": "/download/{filename}",
        },
    }


@app.get("/health")
def health():
    return {"status": "ok"}


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
        "symbol_count": len(symbols),
        "symbols": symbols_to_dict(symbols),
        "musicxml": f"/download/{xml_name}" if has_xml else None,
    }
