from fastapi import FastAPI, UploadFile, File
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles
from pathlib import Path
import cv2
import numpy as np
from PIL import Image
import io

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


@app.get("/")
def index():
    return {
        "name": "ScoreOCR Toolkit",
        "status": "MVP",
        "endpoints": {
            "upload": "/upload",
            "health": "/health",
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
