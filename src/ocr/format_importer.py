import io
import json
import re
from pathlib import Path

from PIL import Image, ImageDraw

from src.ocr.recognizer import Symbol

# 支援的副檔名清單
SUPPORTED_IMAGE_EXTENSIONS = {".png", ".jpg", ".jpeg", ".bmp", ".webp", ".tiff", ".tif"}
SUPPORTED_EXTENSIONS = (
    SUPPORTED_IMAGE_EXTENSIONS | {".pdf", ".docx", ".txt", ".json"}
)


def render_text_to_score_image(
    text: str, width: int = 1200, min_height: int = 800
) -> Image.Image:
    """將文字簡譜、代碼或註解排版渲染為乾淨的白底黑字樂譜影像，供畫布展示與互動。"""
    lines = text.strip().splitlines()
    line_height = 36
    margin = 50
    header_height = 60

    total_height = max(min_height, margin * 2 + header_height + len(lines) * line_height)
    img = Image.new("RGB", (width, total_height), color=(255, 255, 255))
    draw = ImageDraw.Draw(img)

    # 繪製五線譜裝飾背景或淺灰格線
    for y in range(margin + header_height, total_height - margin, line_height):
        draw.line([(margin, y + 26), (width - margin, y + 26)], fill=(240, 240, 240), width=1)

    # 繪製標題與內容
    y = margin
    draw.text((margin, y), "ScoreOCR Text Score Document", fill=(70, 70, 70))
    y += header_height

    for line in lines:
        draw.text((margin, y), line, fill=(20, 20, 20))
        y += line_height

    return img


def parse_txt_to_symbols(text: str) -> list[Symbol]:
    """解析文字格式（支援簡譜 1 2 3 5 6、音名 C4 D4 E4 等）為 Symbol 物件"""
    symbols: list[Symbol] = []
    lines = text.strip().splitlines()

    # 簡譜字元正則 (如 1, 1., 1-, 0, 等)
    jianpu_map = {
        "1": "C4", "2": "D4", "3": "E4", "4": "F4", "5": "G4", "6": "A4", "7": "B4",
        "1̇": "C5", "2̇": "D5", "3̇": "E5", "4̇": "F5", "5̇": "G5", "6̇": "A5", "7̇": "B5",
        "1̣": "C3", "2̣": "D3", "3̣": "E3", "4̣": "F3", "5̣": "G3", "6̣": "A3", "7̣": "B3",
    }

    start_y = 110
    line_spacing = 60
    char_spacing = 38
    sym_idx = 1

    for row_idx, line in enumerate(lines):
        # 濾除非樂譜行（如標題、空行）
        tokens = line.strip().split()
        col_x = 60
        for token in tokens:
            if token == "|" or token == "||":
                col_x += 20
                continue

            pitch = None
            duration = "quarter"
            stype = "note"

            # 判斷是否為西洋音名，例如 C4, G#5, Bb3
            western_match = re.match(r"^([A-Ga-g][#bB]?\d?)$", token)
            if western_match:
                pitch = western_match.group(1).upper()
            elif token == "0":
                stype = "rest"
            elif token in jianpu_map:
                pitch = jianpu_map[token]
            elif token.startswith("1-") or token.endswith("-"):
                # 延長音
                base_char = token.replace("-", "")
                pitch = jianpu_map.get(base_char, "C4")
                duration = "half" if token.count("-") == 1 else "whole"
            else:
                # 嘗試提取第一個數字
                clean_t = re.sub(r"[^\d]", "", token)
                if clean_t and clean_t[0] in jianpu_map:
                    pitch = jianpu_map[clean_t[0]]
                    if "_" in token:
                        duration = "eighth"
                    elif "=" in token:
                        duration = "16th"

            if pitch or stype == "rest":
                symbols.append(
                    Symbol(
                        id=f"txt-{sym_idx}",
                        type=stype,
                        pitch=pitch,
                        duration=duration,
                        x=col_x,
                        y=start_y + row_idx * line_spacing,
                        width=24,
                        height=28,
                        confidence=1.0,
                    )
                )
                sym_idx += 1
            col_x += char_spacing

    return symbols


def import_file_to_image_and_symbols(
    file_bytes: bytes, filename: str
) -> tuple[Image.Image, list[Symbol], str]:
    """多格式上傳核心函式：
    輸入檔案位元組與副檔名，回傳：
    (PIL.Image, List[Symbol], format_type)
    """
    ext = Path(filename).suffix.lower()

    # 1. 點陣圖片格式 (.png, .jpg, .bmp, .webp, .tiff)
    if ext in SUPPORTED_IMAGE_EXTENSIONS:
        img = Image.open(io.BytesIO(file_bytes)).convert("RGB")
        return img, [], "image"

    # 2. PDF 文件格式 (.pdf)
    if ext == ".pdf":
        try:
            import pypdfium2 as pdfium  # type: ignore[import-untyped]
            pdf = pdfium.PdfDocument(file_bytes)
            if len(pdf) == 0:
                raise ValueError("PDF 檔案為空")
            # 渲染第 1 頁 (scale=2.5 約為 180~200 DPI，兼顧速度與清晰度)
            page = pdf[0]
            bitmap = page.render(scale=2.5)
            pil_image = bitmap.to_pil().convert("RGB")
            return pil_image, [], "pdf"
        except Exception as e:
            raise RuntimeError(f"解析 PDF 失敗: {str(e)}") from e

    # 3. Word 文檔格式 (.docx)
    if ext == ".docx":
        try:
            from docx import Document
            doc = Document(io.BytesIO(file_bytes))
            # 優先搜尋嵌入的圖片
            images = []
            for rel in doc.part.rels.values():
                if "image" in rel.target_ref:
                    try:
                        img_bytes = rel.target_part.blob
                        img = Image.open(io.BytesIO(img_bytes)).convert("RGB")
                        images.append(img)
                    except Exception:
                        pass

            if images:
                # 選擇面積最大的圖片（通常是樂譜掃描圖）
                best_img = max(images, key=lambda im: im.width * im.height)
                return best_img, [], "docx_image"

            # 若無嵌入圖片，則讀取內文簡譜/樂譜文字
            paragraphs = [p.text for p in doc.paragraphs if p.text.strip()]
            full_text = "\n".join(paragraphs)
            if not full_text.strip():
                raise ValueError("Word 文檔中無可讀取的圖片或文字")

            rendered_img = render_text_to_score_image(full_text)
            symbols = parse_txt_to_symbols(full_text)
            return rendered_img, symbols, "docx_text"
        except Exception as e:
            raise RuntimeError(f"解析 Word (.docx) 失敗: {str(e)}") from e

    # 4. TXT 文字譜 (.txt)
    if ext == ".txt":
        try:
            text = file_bytes.decode("utf-8", errors="replace")
            rendered_img = render_text_to_score_image(text)
            symbols = parse_txt_to_symbols(text)
            return rendered_img, symbols, "txt"
        except Exception as e:
            raise RuntimeError(f"解析 TXT 文字譜失敗: {str(e)}") from e

    # 5. JSON 格式 (.json)
    if ext == ".json":
        try:
            data = json.loads(file_bytes.decode("utf-8", errors="replace"))
            json_symbols: list[Symbol] = []
            raw_symbols = data.get("symbols", data) if isinstance(data, dict) else data

            if isinstance(raw_symbols, list):
                for idx, s in enumerate(raw_symbols):
                    if isinstance(s, dict):
                        json_symbols.append(
                            Symbol(
                                id=s.get("id", f"json-{idx+1}"),
                                type=s.get("type", "note"),
                                pitch=s.get("pitch"),
                                duration=s.get("duration", "quarter"),
                                x=int(s.get("x", 50 + (idx % 16) * 45)),
                                y=int(s.get("y", 100 + (idx // 16) * 60)),
                                width=int(s.get("width", 20)),
                                height=int(s.get("height", 18)),
                                confidence=float(s.get("confidence", 1.0)),
                            )
                        )

            # 若 JSON 內無提供影像，生成一張包含音符外框的預覽底圖
            max_x = max([s.x + s.width for s in json_symbols], default=800) + 100
            max_y = max([s.y + s.height for s in json_symbols], default=600) + 100
            canvas_img = Image.new("RGB", (max(1000, max_x), max(700, max_y)), (250, 250, 250))
            draw = ImageDraw.Draw(canvas_img)
            draw.text((40, 40), f"JSON Imported Score: {filename}", fill=(100, 100, 100))

            return canvas_img, json_symbols, "json"
        except Exception as e:
            raise RuntimeError(f"解析 JSON 符號失敗: {str(e)}") from e

    raise ValueError(f"不支援的檔案格式: {ext}。支援格式包含: {', '.join(sorted(SUPPORTED_EXTENSIONS))}")


def import_pdf_pages(
    file_bytes: bytes, dpi: int = 200
) -> list[Image.Image]:
    """解析 PDF 並回傳所有頁面的 PIL Image 列表"""
    import pypdfium2 as pdfium  # type: ignore[import-untyped]

    pdf = pdfium.PdfDocument(file_bytes)
    pages = []
    scale = dpi / 72.0

    for i in range(len(pdf)):
        page = pdf[i]
        bitmap = page.render(scale=scale)
        pil_image = bitmap.to_pil().convert("RGB")
        pages.append(pil_image)

    return pages
