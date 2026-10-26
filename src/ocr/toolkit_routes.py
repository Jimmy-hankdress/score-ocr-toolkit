"""
ScoreOCR Toolkit API Routes
包含樂譜影像預處理、OMR 辨識、五線譜/簡譜互轉、MusicXML 匯出、專案管理與多格式匯入端點
"""

from __future__ import annotations

import io
import json
import logging
import re
import sys
import uuid
from pathlib import Path
from typing import Any

import cv2
import numpy as np
from fastapi import APIRouter, File, HTTPException, Response, UploadFile, status
from fastapi.responses import FileResponse, JSONResponse
from PIL import Image
from pydantic import BaseModel, Field, field_validator

from src.ocr.config import get_config
from src.ocr.format_importer import (
    import_file_to_image_and_symbols,
    import_pdf_pages,
)
from src.ocr.homr_recognizer import HomrRecognizer
from src.ocr.jianpu_converter import (
    pitch_to_jianpu,
    symbols_to_jianpu_text,
)
from src.ocr.musicxml_builder import symbols_to_musicxml
from src.ocr.note_extractor import extract_score_symbols
from src.ocr.recognizer import Symbol, symbols_to_dict

logger = logging.getLogger("scoreocr.toolkit_routes")
cfg = get_config()

router = APIRouter(tags=["toolkit"])

BASE_DIR = Path(__file__).resolve().parent.parent.parent
UPLOAD_DIR = cfg.upload_dir
PROCESSED_DIR = cfg.processed_dir
STATIC_DIR = cfg.static_dir

UPLOAD_DIR.mkdir(exist_ok=True)
PROCESSED_DIR.mkdir(exist_ok=True)
STATIC_DIR.mkdir(exist_ok=True)

# OMR 辨識器實例
recognizer = HomrRecognizer(python_executable=sys.executable)


# ========== Pydantic 模型定義 ==========

class ExportJianpuRequest(BaseModel):
    """簡譜匯出請求模型"""
    symbols: list[dict[str, Any]] = Field(..., min_length=1, description="音符符號列表")
    title: str = Field(default="ScoreOCR Jianpu Score", max_length=200)
    key: str = Field(default="C", pattern=r"^[A-G](?:b|#)?$")
    meter: str = Field(default="4/4", pattern=r"^(?:2|3|4|6)/(?:2|4|8)$")

    @field_validator("symbols")
    @classmethod
    def validate_symbols(cls, v):
        for i, s in enumerate(v):
            if not isinstance(s, dict):
                raise ValueError(f"symbols[{i}] 必須是物件")
            if "id" not in s:
                s["id"] = f"sym-{i+1}"
        return v


class ConvertToJianpuRequest(BaseModel):
    """即時轉簡譜請求模型"""
    symbols: list[dict[str, Any]] = Field(default_factory=list)
    key: str = Field(default="C", pattern=r"^[A-G](?:b|#)?$")
    meter: str = Field(default="4/4", pattern=r"^(?:2|3|4|6)/(?:2|4|8)$")


class ExportMusicXMLRequest(BaseModel):
    """MusicXML 匯出請求模型"""
    symbols: list[dict[str, Any]] = Field(..., min_length=1, description="音符符號列表")

    @field_validator("symbols")
    @classmethod
    def validate_symbols(cls, v):
        for i, s in enumerate(v):
            if not isinstance(s, dict):
                raise ValueError(f"symbols[{i}] 必須是物件")
            if "id" not in s:
                s["id"] = f"sym-{i+1}"
        return v


class RecognizeResponse(BaseModel):
    """辨識回應模型"""
    success: bool
    format_type: str | None = None
    filename: str
    image_url: str | None = None
    symbol_count: int = 0
    symbols: list[dict[str, Any]] = []
    musicxml: str | None = None
    jianpu_file: str | None = None
    jianpu_url: str | None = None
    jianpu_text: str = ""
    error_type: str | None = None
    error: str | None = None
    suggestion: str | None = None
    detail: str | None = None


class BatchRecognizeRequest(BaseModel):
    """批次辨識請求模型"""
    files: list[str] = Field(..., description="已上傳檔案的路徑列表")


class ProjectSaveRequest(BaseModel):
    """專案儲存請求模型"""
    project_name: str = Field(default="ScoreOCR Project", max_length=100)
    symbols: list[dict[str, Any]] = Field(default_factory=list)
    image_data: str | None = Field(default=None, description="Base64 編碼的影像資料")
    settings: dict[str, Any] = Field(default_factory=dict)


class ImportFromCanvasRequest(BaseModel):
    """從視覺化校對畫布直接匯入主工作台 SQLite 專案庫請求模型"""
    project_name: str = Field(default="畫布辨識樂譜", max_length=150)
    symbols: list[dict[str, Any]] = Field(default_factory=list)
    key: str = Field(default="C")
    meter: str = Field(default="4/4")
    tempo: int = Field(default=80, ge=20, le=280)
    image_data: str | None = Field(default=None, description="Base64 編碼的影像資料")
    image_url: str | None = Field(default=None, description="已存在的圖片 URL")


# ========== 工具函數 ==========

def preprocess_image(contents: bytes) -> np.ndarray:
    """影像預處理：灰階、高斯模糊、OTSU 二值化"""
    image = Image.open(io.BytesIO(contents)).convert("L")
    array = np.array(image)
    blurred = cv2.GaussianBlur(array, cfg.gaussian_blur_kernel, 0)
    _, binary = cv2.threshold(
        blurred,
        cfg.otsu_threshold,
        cfg.otsu_maxval,
        cv2.THRESH_BINARY + cv2.THRESH_OTSU,
    )
    return binary


def validate_file_size(contents: bytes, filename: str) -> None:
    """驗證檔案大小"""
    if len(contents) > cfg.max_upload_size_bytes:
        logger.warning("檔案過大: %s (%d bytes, 限制 %d bytes)", filename, len(contents), cfg.max_upload_size_bytes)
        raise HTTPException(
            status_code=413,
            detail=f"檔案過大: {len(contents) / 1024 / 1024:.1f} MB，上限 {cfg.max_upload_size_mb} MB",
        )


def validate_file_extension(filename: str) -> None:
    """驗證副檔名"""
    ext = Path(filename).suffix.lower()
    if ext not in cfg.supported_extensions:
        logger.warning("不支援的檔案格式: %s (%s)", filename, ext)
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"不支援的檔案格式: {ext}。支援格式: {', '.join(sorted(cfg.supported_extensions))}",
        )


def make_safe_filename(original: str) -> tuple[str, str]:
    """生成安全的檔名 (token, safe_base)"""
    safe_token = uuid.uuid4().hex[:8]
    safe_base = re.sub(r"[^a-zA-Z0-9_\-]", "_", Path(original).stem) or "score"
    return safe_token, safe_base


def save_image_and_get_url(pil_image: Image.Image, safe_token: str, safe_base: str) -> tuple[str, Path]:
    """儲存 PIL 圖片並回傳 (URL, 路徑)"""
    raw_filename = f"raw_{safe_token}_{safe_base}.png"
    raw_path = PROCESSED_DIR / raw_filename
    pil_image.save(raw_path, format="PNG")
    return f"/files/processed/{raw_filename}", raw_path


def build_success_response(
    fmt_type: str,
    filename: str,
    image_url: str,
    symbols: list[Symbol],
    xml_name: str | None = None,
    jianpu_name: str | None = None,
    jianpu_text: str = "",
) -> RecognizeResponse:
    """建立成功回應物件"""
    return RecognizeResponse(
        success=True,
        format_type=fmt_type,
        filename=filename,
        image_url=image_url,
        symbol_count=len(symbols),
        symbols=symbols_to_dict(symbols),
        musicxml=f"/download/{xml_name}" if xml_name else None,
        jianpu_file=f"/download/{jianpu_name}" if jianpu_name else None,
        jianpu_url=f"/download/{jianpu_name}" if jianpu_name else None,
        jianpu_text=jianpu_text,
    )


def build_error_response(
    fmt_type: str | None,
    filename: str,
    image_url: str | None,
    error_type: str,
    error: str,
    suggestion: str,
    detail: str = "",
    status_code: int = 200,
) -> JSONResponse:
    """建立錯誤回應"""
    return JSONResponse(
        {
            "success": False,
            "format_type": fmt_type,
            "filename": filename,
            "image_url": image_url,
            "error_type": error_type,
            "error": error,
            "suggestion": suggestion,
            "detail": detail,
            "symbol_count": 0,
            "symbols": [],
            "musicxml": None,
            "jianpu_file": None,
            "jianpu_text": "",
        },
        status_code=status_code,
    )


# ========== API 端點 ==========

@router.get("/health")
def health_check():
    """健康檢查端點（相容別名）"""
    return {
        "status": "ok",
        "version": "3.0.0",
        "supported_formats": sorted(cfg.supported_extensions),
    }


@router.get("/favicon.ico", include_in_schema=False)
def favicon():
    """提供網站圖示"""
    fav_path = STATIC_DIR / "favicon.ico"
    if fav_path.exists():
        return FileResponse(fav_path)
    return Response(status_code=204)


@router.get("/api/sample")
def get_sample_score():
    """載入示範樂譜 (tabi.png) 與已提取之音符框"""
    sample_img = BASE_DIR / "tabi.png"
    sample_xml = PROCESSED_DIR / "recognize_tabi.musicxml"

    if not sample_img.exists():
        logger.warning("示範樂譜不存在: %s", sample_img)
        return JSONResponse({"error": "Sample image not found"}, status_code=404)

    dest_img = PROCESSED_DIR / "sample_tabi.png"
    if not dest_img.exists():
        dest_img.write_bytes(sample_img.read_bytes())

    xml_path_str = str(sample_xml) if sample_xml.exists() else None
    symbols = extract_score_symbols(str(sample_img), xml_path_str)

    jianpu_text = symbols_to_jianpu_text(symbols, title="Tabi Sample Score")
    jianpu_name = "sample_tabi_jianpu.txt"
    (PROCESSED_DIR / jianpu_name).write_text(jianpu_text, encoding="utf-8")

    logger.info("載入示範樂譜: %d 個符號", len(symbols))

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


@router.post("/upload")
async def upload(file: UploadFile = File(...)) -> JSONResponse:
    """上傳檔案並預處理"""
    contents = await file.read()
    filename = file.filename or "unknown"
    validate_file_size(contents, filename)
    validate_file_extension(filename)

    ext = Path(filename).suffix.lower()
    is_image = ext in cfg.supported_image_extensions

    if is_image:
        binary = preprocess_image(contents)
    else:
        binary = None

    input_path = UPLOAD_DIR / filename
    output_path = PROCESSED_DIR / f"processed_{filename}"

    input_path.write_bytes(contents)
    if binary is not None:
        cv2.imwrite(str(output_path), binary)
    else:
        output_path.write_bytes(contents)

    logger.info("檔案上傳完成: %s (%d bytes)", file.filename, len(contents))

    return JSONResponse(
        {
            "filename": file.filename,
            "uploaded": str(input_path),
            "processed": str(output_path),
            "next_step": "OMR recognition",
        }
    )


@router.get("/download/{filename:path}")
def download_file(filename: str) -> FileResponse:
    """安全下載產生的檔案"""
    if ".." in filename or "/" in filename or "\\" in filename:
        raise HTTPException(status_code=404, detail="File not found")
    safe_filename = re.sub(r"[^a-zA-Z0-9_\-\.]", "_", filename)
    file_path = PROCESSED_DIR / safe_filename

    if not file_path.exists():
        logger.warning("下載檔案不存在: %s", filename)
        raise HTTPException(status_code=404, detail="File not found")

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

    return FileResponse(file_path, media_type=media_type, filename=safe_filename)


@router.post("/recognize")
async def recognize(file: UploadFile = File(...)) -> Any:
    """上傳樂譜檔案，執行影像預處理或文字語意解析，回傳辨識與簡譜結果"""
    contents = await file.read()
    filename = file.filename or "unknown"
    validate_file_size(contents, filename)
    validate_file_extension(filename)

    safe_token, safe_base = make_safe_filename(filename)

    try:
        pil_image, pre_symbols, fmt_type = import_file_to_image_and_symbols(
            contents, filename
        )
    except Exception as parse_err:
        logger.exception("檔案解析失敗: %s", filename)
        return build_error_response(
            fmt_type=None,
            filename=filename,
            image_url=None,
            error_type="FORMAT_PARSE_ERROR",
            error=f"解析檔案失敗: {str(parse_err)}",
            suggestion=f"目前支援格式包含: {', '.join(sorted(cfg.supported_extensions))}。請確認檔案內容或格式是否正確。",
            status_code=400,
        )

    image_url, raw_path = save_image_and_get_url(pil_image, safe_token, safe_base)

    if pre_symbols:
        xml_name = f"recognize_{safe_base}_{safe_token}.musicxml"
        target_xml = PROCESSED_DIR / xml_name
        xml_content = symbols_to_musicxml(symbols_to_dict(pre_symbols), title=Path(filename).stem)
        target_xml.write_text(xml_content, encoding="utf-8")

        jianpu_text = symbols_to_jianpu_text(pre_symbols, title=Path(filename).stem)
        jianpu_name = f"jianpu_{safe_base}_{safe_token}.txt"
        (PROCESSED_DIR / jianpu_name).write_text(jianpu_text, encoding="utf-8")

        logger.info("文字格式解析完成: %s, %d 個符號", filename, len(pre_symbols))
        return build_success_response(
            fmt_type=fmt_type,
            filename=filename,
            image_url=image_url,
            symbols=pre_symbols,
            xml_name=xml_name,
            jianpu_name=jianpu_name,
            jianpu_text=jianpu_text,
        )

    try:
        symbols = await recognizer.recognize(str(raw_path))
    except Exception as e:
        err_msg = str(e)
        logger.exception("OMR 辨識失敗: %s", filename)

        if "No staffs found" in err_msg:
            error_type = "NO_STAFFS_FOUND"
            friendly_error = "未在影像中檢測到標準五線譜線系統 (No staffs found)。"
            suggestion = (
                "目前 HOMR 辨識核心專為「標準五線譜 (Western Staff Notation)」設計；\n"
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
        elif "逾時" in err_msg or "timeout" in err_msg.lower():
            error_type = "OMR_TIMEOUT"
            friendly_error = "OMR 辨識逾時，請嘗試較小或較清晰的圖片。"
            suggestion = "建議使用解析度適中 (150-300 DPI) 的樂譜掃描圖。"
        else:
            error_type = "OMR_PROCESSING_ERROR"
            friendly_error = f"OMR 辨識過程發生異常: {err_msg[:200]}"
            suggestion = "請確認檔案為清晰的樂譜掃描圖、PDF 或照片。"

        return build_error_response(
            fmt_type=fmt_type,
            filename=filename,
            image_url=image_url,
            error_type=error_type,
            error=friendly_error,
            suggestion=suggestion,
            detail=err_msg,
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

    jianpu_text = symbols_to_jianpu_text(symbols, title=Path(filename).stem)
    jianpu_name = f"jianpu_{safe_base}_{safe_token}.txt"
    (PROCESSED_DIR / jianpu_name).write_text(jianpu_text, encoding="utf-8")

    logger.info("OMR 辨識完成: %s, %d 個符號", filename, len(symbols))

    return build_success_response(
        fmt_type=fmt_type,
        filename=filename,
        image_url=image_url,
        symbols=symbols,
        xml_name=xml_name if has_xml else None,
        jianpu_name=jianpu_name,
        jianpu_text=jianpu_text,
    )


@router.post("/api/export-jianpu")
@router.post("/export/jianpu")
async def export_jianpu(payload: ExportJianpuRequest) -> JSONResponse:
    """將校對後的音符列表編譯為簡譜格式"""
    symbols = [
        Symbol(
            id=s.get("id", f"sym-{i+1}"),
            type=s.get("type", "note"),
            pitch=s.get("pitch"),
            duration=s.get("duration", "quarter"),
            x=int(s.get("x", 0)),
            y=int(s.get("y", 0)),
            width=int(s.get("width", cfg.default_note_width)),
            height=int(s.get("height", cfg.default_note_height)),
            confidence=float(s.get("confidence", 1.0)),
        )
        for i, s in enumerate(payload.symbols)
    ]
    try:
        jianpu_text = symbols_to_jianpu_text(
            symbols, title=payload.title, key=payload.key, meter=payload.meter
        )
        output_filename = f"jianpu_{uuid.uuid4().hex[:8]}.txt"
        output_file = PROCESSED_DIR / output_filename
        output_file.write_text(jianpu_text, encoding="utf-8")

        logger.info("簡譜匯出完成: %s", output_filename)

        return JSONResponse(
            {
                "status": "ok",
                "message": "Jianpu score generated successfully",
                "download_url": f"/download/{output_file.name}",
                "jianpu_text": jianpu_text,
            }
        )
    except Exception as e:
        logger.exception("簡譜匯出失敗")
        return JSONResponse({"error": f"Failed to export Jianpu: {str(e)}"}, status_code=500)


@router.post("/api/convert-to-jianpu")
@router.post("/convert/format")
@router.post("/api/jianpu/convert")
async def convert_to_jianpu(payload: ConvertToJianpuRequest) -> JSONResponse:
    """即時轉換 Symbol 清單為簡譜純文字與標籤"""
    symbols = [
        Symbol(
            id=s.get("id", f"sym-{i+1}"),
            type=s.get("type", "note"),
            pitch=s.get("pitch"),
            duration=s.get("duration", "quarter"),
            x=int(s.get("x", 0)),
            y=int(s.get("y", 0)),
            width=int(s.get("width", cfg.default_note_width)),
            height=int(s.get("height", cfg.default_note_height)),
            confidence=float(s.get("confidence", 1.0)),
        )
        for i, s in enumerate(payload.symbols)
    ]

    tag_map = {
        s.id: pitch_to_jianpu(s.pitch, key=payload.key) if s.pitch else "0"
        for s in symbols
    }
    full_text = symbols_to_jianpu_text(symbols, title="Score", key=payload.key, meter=payload.meter)

    return JSONResponse(
        {
            "status": "ok",
            "tag_map": tag_map,
            "jianpu_text": full_text,
        }
    )


@router.post("/api/export-musicxml")
@router.post("/export/musicxml")
async def export_corrected_musicxml(payload: ExportMusicXMLRequest) -> JSONResponse:
    """將校對後的符號編譯為標準 MusicXML"""
    try:
        xml_content = symbols_to_musicxml(payload.symbols, title="ScoreOCR Edited Score")
        output_file = PROCESSED_DIR / "corrected_score.musicxml"
        output_file.write_text(xml_content, encoding="utf-8")

        logger.info("MusicXML 匯出完成: %s", output_file.name)

        return JSONResponse(
            {
                "status": "ok",
                "message": "Corrected MusicXML generated successfully",
                "download_url": f"/download/{output_file.name}",
            }
        )
    except Exception as e:
        logger.exception("MusicXML 匯出失敗")
        return JSONResponse({"error": f"Failed to export MusicXML: {str(e)}"}, status_code=500)


@router.post("/api/project/save")
async def save_project(payload: ProjectSaveRequest) -> JSONResponse:
    """儲存專案狀態為 JSON 檔案"""
    try:
        project_data = {
            "project_name": payload.project_name,
            "version": "1.1.0",
            "symbols": payload.symbols,
            "settings": payload.settings,
            "timestamp": str(__import__("datetime").datetime.now()),
        }

        if payload.image_data:
            import base64
            img_bytes = base64.b64decode(payload.image_data.split(",")[1] if "," in payload.image_data else payload.image_data)
            img_name = f"project_{uuid.uuid4().hex[:8]}.png"
            img_path = PROCESSED_DIR / img_name
            img_path.write_bytes(img_bytes)
            project_data["image_url"] = f"/files/processed/{img_name}"

        project_filename = f"project_{uuid.uuid4().hex[:8]}.json"
        project_path = PROCESSED_DIR / project_filename
        project_path.write_text(json.dumps(project_data, ensure_ascii=False, indent=2), encoding="utf-8")

        logger.info("專案儲存完成: %s", project_filename)

        return JSONResponse({
            "status": "ok",
            "message": "專案儲存成功",
            "download_url": f"/download/{project_filename}",
            "project": project_data,
        })
    except Exception as e:
        logger.exception("專案儲存失敗")
        return JSONResponse({"error": f"Failed to save project: {str(e)}"}, status_code=500)


def _symbol_to_studio_tokens(sym_dict: dict[str, Any], key: str = "C") -> tuple[list[str], float]:
    """將 Canvas Symbol 轉為 Score Studio (SheetMusicOMR) 原生簡譜 token 列表與拍數。"""
    from src.ocr.jianpu_converter import DURATION_BEATS, pitch_to_jianpu

    sym_type = str(sym_dict.get("type", "note")).lower()
    dur = str(sym_dict.get("duration") or "quarter").lower()
    beats = DURATION_BEATS.get(dur, 1.0)

    if sym_type == "rest":
        base = "0"
    else:
        pitch = str(sym_dict.get("pitch") or "C4")
        base = pitch_to_jianpu(pitch, key)
        if base == "?":
            base = "1"
        base = base.replace("\u0308", "\u0307\u0307").replace("\u0324", "\u0323\u0323")

    if dur == "whole":
        return [base, "-", "-", "-"], 4.0
    if dur == "half":
        return [base, "-"], 2.0
    if dur == "quarter":
        return [base], 1.0
    if dur == "eighth":
        return [f"{base}_"], 0.5
    if dur in ("16th", "sixteenth"):
        return [f"{base}__"], 0.25
    if dur in ("32nd", "thirty-second"):
        return [f"{base}___"], 0.125
    return [base], beats


@router.post("/api/import-from-canvas")
async def import_from_canvas(payload: ImportFromCanvasRequest) -> JSONResponse:
    """將視覺化校對畫布 (/canvas-editor) 的辨識與校對結果一鍵存入主工作台 SQLite 專案列表，並回傳 Score Studio 連結。"""
    try:
        from app import db as app_db
        from app import projects as app_projects
        from app.config import save_user_config
        from app.models import ScoreDocument, ScoreMeasure, blank_document

        title = (payload.project_name or "畫布辨識樂譜").strip() or "畫布辨識樂譜"
        key = (payload.key or "C").strip() or "C"
        meter = (payload.meter or "4/4").strip() or "4/4"
        try:
            beats_per_measure = float(int(meter.split("/")[0]))
        except Exception:
            beats_per_measure = 4.0

        # 依 y 行分組、x 由左至右排序（與簡譜轉換器一致）
        raw_syms = [dict(s) for s in (payload.symbols or []) if isinstance(s, dict)]
        sorted_syms = sorted(raw_syms, key=lambda s: (int(float(s.get("y", 0))) // 80, float(s.get("x", 0))))

        measures_data: list[dict[str, Any]] = []
        cur_notes: list[str] = []
        cur_chords: list[str] = []
        cur_chord_offsets: list[int] = []
        cur_lyrics: list[str] = []
        cur_beats = 0.0

        def flush_measure() -> None:
            nonlocal cur_notes, cur_chords, cur_chord_offsets, cur_lyrics, cur_beats
            if not cur_notes and not cur_chords and not cur_lyrics:
                return
            measures_data.append({
                "noteText": " ".join(cur_notes),
                "chordText": " ".join(cur_chords),
                "chordOffsets": list(cur_chord_offsets),
                "lyricText": " ".join(cur_lyrics),
            })
            cur_notes = []
            cur_chords = []
            cur_chord_offsets = []
            cur_lyrics = []
            cur_beats = 0.0

        for sym in sorted_syms:
            stype = str(sym.get("type", "note")).lower()
            if stype == "clef":
                continue
            if stype == "barline":
                flush_measure()
                continue
            if stype == "chord":
                chord_name = str(sym.get("chord") or sym.get("pitch") or sym.get("text") or "C").strip()
                if chord_name:
                    cur_chords.append(chord_name)
                    cur_chord_offsets.append(max(0, len(cur_notes)))
                continue
            if stype in ("note", "rest"):
                tokens, b = _symbol_to_studio_tokens(sym, key=key)
                if cur_beats + b > beats_per_measure + 0.01 and cur_notes:
                    flush_measure()
                cur_notes.extend(tokens)
                cur_beats += b
                lyric_val = str(sym.get("lyric") or sym.get("text") or "").strip()
                if lyric_val:
                    cur_lyrics.append(lyric_val)
                if cur_beats >= beats_per_measure - 0.01:
                    flush_measure()

        flush_measure()

        if not measures_data:
            doc = blank_document(title=title, measures=4)
            doc.key = key
            doc.timeSignature = meter
            doc.tempo = payload.tempo
            doc.engineMode = "canvas-editor"
        else:
            measures: list[ScoreMeasure] = []
            for idx, mdata in enumerate(measures_data):
                m = ScoreMeasure(
                    number=idx + 1,
                    lineIndex=idx // 3,
                    linePosition=(idx % 3) + 1,
                    noteText=mdata["noteText"],
                    chordText=mdata["chordText"],
                    chordOffsets=mdata["chordOffsets"],
                    lyricText=mdata["lyricText"],
                )
                m.beats = m.expand_beats(min_confidence=0.92)
                measures.append(m)
            doc = ScoreDocument(
                title=title,
                key=key,
                timeSignature=meter,
                tempo=payload.tempo,
                measures=measures,
                engineMode="canvas-editor",
            )
            doc.renumber()

        # 若有背景影像，寫入暫存檔並隨專案匯入
        source_file: Path | None = None
        if payload.image_data:
            try:
                import base64
                raw_b64 = payload.image_data.split(",")[1] if "," in payload.image_data else payload.image_data
                img_bytes = base64.b64decode(raw_b64)
                img_name = f"canvas_{uuid.uuid4().hex[:8]}.png"
                source_file = PROCESSED_DIR / img_name
                source_file.write_bytes(img_bytes)
                doc.sourceName = img_name
            except Exception as img_err:
                logger.warning("儲存畫布背景影像失敗（忽略並繼續匯入專案）: %s", img_err)
        elif payload.image_url and payload.image_url.startswith("/files/"):
            rel = payload.image_url.removeprefix("/files/")
            cand = DATA_DIR / rel
            if cand.exists():
                source_file = cand
                doc.sourceName = cand.name

        app_projects.import_document(doc, source_file=source_file)
        save_user_config({"lastProjectId": doc.id})

        # 同步建立一筆已完成的任務紀錄，讓工作台左側「任務歷史」也能直接點擊開啟
        try:
            task_id = f"task_{uuid.uuid4().hex[:10]}"
            app_db.create_task(task_id, f"{title} (畫布匯入)", str(source_file or ""))
            app_db.update_task(
                task_id,
                status="done",
                progress=100,
                message=f"由視覺校對畫布匯入（{len(doc.measures)} 小節）",
                project_id=doc.id,
            )
        except Exception as task_err:
            logger.warning("寫入工作台任務紀錄失敗: %s", task_err)

        logger.info("畫布結果已匯入主工作台 SQLite 專案庫: id=%s, title=%s, measures=%d", doc.id, doc.title, len(doc.measures))

        return JSONResponse({
            "status": "ok",
            "ok": True,
            "projectId": doc.id,
            "title": doc.title,
            "measureCount": len(doc.measures),
            "studioUrl": f"/?project={doc.id}",
            "standaloneStudioUrl": f"/editor/studio/{doc.id}",
        })
    except Exception as e:
        logger.exception("匯入主工作台失敗")
        return JSONResponse({"status": "error", "error": f"匯入主工作台失敗: {str(e)}"}, status_code=500)


@router.post("/api/project/load")
async def load_project(file: UploadFile = File(...)) -> JSONResponse:
    """載入專案 JSON 檔案"""
    try:
        contents = await file.read()
        project_data = json.loads(contents.decode("utf-8"))

        logger.info("專案載入完成: %s", file.filename)

        return JSONResponse({
            "status": "ok",
            "project_name": project_data.get("project_name", "ScoreOCR Project"),
            "symbols": project_data.get("symbols", []),
            "image_url": project_data.get("image_url"),
            "settings": project_data.get("settings", {}),
        })
    except Exception as e:
        logger.exception("專案載入失敗")
        return JSONResponse({"error": f"Failed to load project: {str(e)}"}, status_code=500)


@router.post("/api/pdf/page")
async def get_pdf_page(file: UploadFile = File(...), page: int = 0, dpi: int = 200) -> JSONResponse:
    """取得多頁 PDF 的指定頁面影像"""
    try:
        contents = await file.read()
        filename = file.filename or "unknown"
        validate_file_size(contents, filename)

        if not filename.lower().endswith(".pdf"):
            return JSONResponse({"error": "僅支援 PDF 檔案"}, status_code=400)

        pages = import_pdf_pages(contents, dpi=dpi)

        if page >= len(pages):
            return JSONResponse({"error": f"頁碼超出範圍 (總共 {len(pages)} 頁)"}, status_code=400)

        pil_image = pages[page]
        safe_token, safe_base = make_safe_filename(f"{filename}_page{page+1}")
        image_url, _ = save_image_and_get_url(pil_image, safe_token, safe_base)

        return JSONResponse({
            "page": page,
            "total_pages": len(pages),
            "image_url": image_url,
            "width": pil_image.width,
            "height": pil_image.height,
        })
    except Exception as e:
        logger.exception("PDF 頁面提取失敗")
        return JSONResponse({"error": f"Failed to extract PDF page: {str(e)}"}, status_code=500)


@router.post("/api/pdf/info")
async def get_pdf_info(file: UploadFile = File(...)) -> JSONResponse:
    """取得 PDF 檔案資訊 (頁數、尺寸等)"""
    try:
        contents = await file.read()
        filename = file.filename or "unknown"
        validate_file_size(contents, filename)

        if not filename.lower().endswith(".pdf"):
            return JSONResponse({"error": "僅支援 PDF 檔案"}, status_code=400)

        pages = import_pdf_pages(contents, dpi=72)

        page_infos = []
        for i, p in enumerate(pages):
            page_infos.append({
                "page": i,
                "width": p.width,
                "height": p.height,
            })

        return JSONResponse({
            "filename": filename,
            "total_pages": len(pages),
            "pages": page_infos,
        })
    except Exception as e:
        logger.exception("PDF 資訊取得失敗")
        return JSONResponse({"error": f"Failed to get PDF info: {str(e)}"}, status_code=500)
