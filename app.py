"""
ScoreOCR Toolkit & SheetMusicOMR v3.00 - 主應用程式進入點
結合本地優先的 SheetMusicOMR 數位化打譜工作台、Score Studio 直式/橫式編輯器與 Canvas AI 視覺標註校對畫布
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

# 將專案根目錄加入 sys.path
BASE_DIR = Path(__file__).resolve().parent
if str(BASE_DIR) not in sys.path:
    sys.path.insert(0, str(BASE_DIR))

from app.server import create_app
from src.ocr.config import get_config
from src.ocr.homr_recognizer import HomrRecognizer
from src.ocr.toolkit_routes import (
    ExportJianpuRequest,
    ConvertToJianpuRequest,
    ExportMusicXMLRequest,
    RecognizeResponse,
    BatchRecognizeRequest,
    ProjectSaveRequest,
    preprocess_image,
    validate_file_size,
    validate_file_extension,
    make_safe_filename,
    save_image_and_get_url,
    build_success_response,
    build_error_response,
    recognizer,
)

# 建立統整 FastAPI 應用程式實例
app = create_app()

if __name__ == "__main__":
    import uvicorn
    port = int(os.environ.get("SHEETMUSIC_PORT", os.environ.get("PORT", "8000")))
    uvicorn.run("app:app", host="127.0.0.1", port=port, reload=True)
