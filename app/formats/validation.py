"""導入驗證：副檔名白名單、大小上限與檔案 signature（規劃書 11 檔案錯誤）。

失敗時立即拒絕並回報可讀原因，絕不進入管線。
"""
from __future__ import annotations

from pathlib import Path

from ..config import ALLOWED_IMPORT_EXT, IMAGE_EXT, MAX_IMPORT_BYTES, TEXTUAL_EXT

PDF_MAGIC = b"%PDF-"
JPEG_MAGIC = b"\xff\xd8\xff"
PNG_MAGIC = b"\x89PNG\r\n\x1a\n"
TIFF_MAGICS = (b"II*\x00", b"MM\x00*")
WEBP_MAGIC = b"RIFF"  # 第 8-12 字元為 WEBP
BMP_MAGIC = b"BM"
HEIC_FTYP = b"ftyp"   # ISO BMFF：偏移 4 起為 ftyp，brand 含 heic/mif1/heix


def _is_webp(payload: bytes) -> bool:
    return payload[:4] == WEBP_MAGIC and len(payload) > 12 and payload[8:12] == b"WEBP"


def _is_heic(payload: bytes) -> bool:
    return payload[4:8] == HEIC_FTYP and (
        b"heic" in payload[:40] or b"mif1" in payload[:40] or b"heix" in payload[:40]
    )


class ValidationError(ValueError):
    """使用者可讀的驗證錯誤。"""


def classify(filename: str) -> tuple[str, str]:
    """回傳 (kind, ext)；kind ∈ pdf / image / text。"""
    ext = Path(filename).suffix.lower()
    if ext not in ALLOWED_IMPORT_EXT:
        allowed = "、".join(sorted(ALLOWED_IMPORT_EXT))
        raise ValidationError(f"不支援的副檔名 {ext or '(無)'}；目前支援：{allowed}")
    if ext == ".pdf":
        return "pdf", ext
    if ext in IMAGE_EXT:
        return "image", ext
    if ext in TEXTUAL_EXT:
        return "text", ext
    raise ValidationError(f"無法判斷檔案類型：{filename}")


def validate_bytes(filename: str, payload: bytes) -> dict:
    if not payload:
        raise ValidationError("檔案內容為空，請確認來源檔案。")
    if len(payload) > MAX_IMPORT_BYTES:
        raise ValidationError(
            f"檔案大小 {len(payload) / 1048576:.1f} MB 超過上限 {MAX_IMPORT_BYTES // 1048576} MB。"
        )
    kind, ext = classify(filename)
    head = payload[:16]

    if kind == "pdf":
        if not head.startswith(PDF_MAGIC):
            raise ValidationError("PDF signature 驗證失敗：檔案開頭不是 %PDF-，可能副檔名不符或檔案損壞。")
    elif kind == "image":
        if ext in {".jpg", ".jpeg"}:
            if not head.startswith(JPEG_MAGIC):
                raise ValidationError("JPEG signature 驗證失敗：檔案開頭不是 FF D8 FF。")
        elif ext == ".png":
            if not head.startswith(PNG_MAGIC):
                raise ValidationError("PNG signature 驗證失敗。")
        elif ext in {".tif", ".tiff"}:
            if not head.startswith(TIFF_MAGICS):
                raise ValidationError("TIFF signature 驗證失敗。")
        elif ext == ".webp":
            if not _is_webp(payload):
                raise ValidationError("WEBP signature 驗證失敗：檔案開頭不是 RIFF/WEBP。")
        elif ext == ".bmp":
            if not head.startswith(BMP_MAGIC):
                raise ValidationError("BMP signature 驗證失敗：檔案開頭不是 BM。")
        elif ext == ".heic":
            if not _is_heic(payload):
                raise ValidationError("HEIC signature 驗證失敗：不是 ISO BMFF (ftyp) 結構。")
            try:
                import pillow_heif  # noqa: F401  # 需要啟始化 HEIF 開啟器
            except ImportError:
                raise ValidationError(
                    "HEIC 解碼器（pillow-heif）未安裝，無法處理 .heic 檔，請改用 JPG／PNG。"
                )
    else:
        # 文字類：必須能以 UTF-8 / UTF-8-SIG / UTF-16 / Big5 解碼，否則視為未知二進位結構
        text = decode_text_or_none(payload)
        if text is None:
            raise ValidationError(
                f"{ext} 格式無法解析：內容不是可辨識的 UTF-8／UTF-16／Big5 文字結構。"
                "本版不會為未知二進位格式建立假結果，請改用 CSV／TSV／TXT／JSON 匯出後再導入。"
            )
    return {"kind": kind, "ext": ext, "bytes": len(payload)}


def decode_text_or_none(payload: bytes) -> str | None:
    for enc in ("utf-8-sig", "utf-8", "utf-16", "big5", "cp950", "gb18030"):
        try:
            text = payload.decode(enc)
        except (UnicodeDecodeError, LookupError):
            continue
        # 控制字元比例過高視為二進位
        control = sum(1 for ch in text[:4000] if ord(ch) < 9 or 14 <= ord(ch) < 32)
        if control > max(4, len(text[:4000]) * 0.02):
            continue
        return text
    return None
