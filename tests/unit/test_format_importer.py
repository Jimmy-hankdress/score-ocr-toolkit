"""
單元測試：多格式匯入器
測試 parse_txt_to_symbols、import_file_to_image_and_symbols 等功能
"""

import io

import pytest
from PIL import Image

from src.ocr.format_importer import (
    SUPPORTED_EXTENSIONS,
    SUPPORTED_IMAGE_EXTENSIONS,
    import_file_to_image_and_symbols,
    parse_txt_to_symbols,
    render_text_to_score_image,
)


class TestParseTxtToSymbols:
    """文字簡譜解析測試"""

    def test_basic_jianpu_numbers(self):
        """基本簡譜數字 1-7"""
        text = "1 2 3 4 5 6 7"
        symbols = parse_txt_to_symbols(text)
        assert len(symbols) == 7
        for i, sym in enumerate(symbols):
            assert sym.type == "note"
            assert sym.pitch == ["C4", "D4", "E4", "F4", "G4", "A4", "B4"][i]
            assert sym.duration == "quarter"

    def test_high_octave_dots(self):
        """高八度點"""
        text = "1̇ 2̇ 3̇"
        symbols = parse_txt_to_symbols(text)
        assert len(symbols) == 3
        for sym in symbols:
            assert sym.pitch.endswith("5")  # 高八度

    def test_low_octave_dots(self):
        """低八度點"""
        text = "1̣ 2̣ 3̣"
        symbols = parse_txt_to_symbols(text)
        assert len(symbols) == 3
        for sym in symbols:
            assert sym.pitch.endswith("3")  # 低八度

    def test_western_note_names(self):
        """西洋音名"""
        text = "C4 D4 E4 F4 G4 A4 B4"
        symbols = parse_txt_to_symbols(text)
        assert len(symbols) == 7
        for i, sym in enumerate(symbols):
            assert sym.pitch == ["C4", "D4", "E4", "F4", "G4", "A4", "B4"][i]

    def test_sharp_flat_notes(self):
        """升降號音名 (會標準化為大寫)"""
        text = "C#4 Eb4 F#4 G#4 Bb4"
        symbols = parse_txt_to_symbols(text)
        assert len(symbols) == 5
        expected = ["C#4", "EB4", "F#4", "G#4", "BB4"]
        for i, sym in enumerate(symbols):
            assert sym.pitch == expected[i]

    def test_rest_symbol(self):
        """休止符 0"""
        text = "1 0 2 0 3"
        symbols = parse_txt_to_symbols(text)
        # 0 被解析為 rest
        rest_symbols = [s for s in symbols if s.type == "rest"]
        assert len(rest_symbols) == 2

    def test_duration_extensions(self):
        """延長音與減時線"""
        text = "1- 2-- 3_ 4="
        symbols = parse_txt_to_symbols(text)
        assert len(symbols) == 4
        # 1- = half, 2-- = whole, 3_ = eighth, 4= = 16th
        assert symbols[0].duration == "half"
        assert symbols[1].duration == "whole"
        assert symbols[2].duration == "eighth"
        assert symbols[3].duration == "16th"

    def test_barlines_ignored(self):
        """小節線應被忽略"""
        text = "1 2 3 4 | 5 6 7 1 ||"
        symbols = parse_txt_to_symbols(text)
        assert len(symbols) == 8  # 只有 8 個音符

    def test_multiple_lines(self):
        """多行文字"""
        text = "1 2 3 4\n5 6 7 1"
        symbols = parse_txt_to_symbols(text)
        assert len(symbols) == 8
        # 第二行的 y 座標應該不同
        y_vals = {s.y for s in symbols}
        assert len(y_vals) == 2

    def test_empty_lines_skipped(self):
        """空行跳過"""
        text = "1 2 3\n\n4 5 6"
        symbols = parse_txt_to_symbols(text)
        assert len(symbols) == 6

    def test_unknown_tokens_skipped(self):
        """未知 token 跳過"""
        text = "1 2 xxx 3 4"
        symbols = parse_txt_to_symbols(text)
        assert len(symbols) == 4  # xxx 被忽略


class TestRenderTextToScoreImage:
    """文字轉圖片渲染測試"""

    def test_render_returns_pil_image(self):
        img = render_text_to_score_image("1 2 3")
        assert isinstance(img, Image.Image)
        assert img.mode == "RGB"
        assert img.width > 0
        assert img.height > 0

    def test_render_custom_dimensions(self):
        img = render_text_to_score_image("1 2 3", width=800, min_height=400)
        assert img.width == 800
        assert img.height >= 400


class TestImportFileToImageAndSymbols:
    """多格式匯入主函數測試"""

    def create_test_image(self, size=(200, 200), color=(255, 255, 255)):
        """建立測試用圖片 bytes"""
        img = Image.new("RGB", size, color)
        buf = io.BytesIO()
        img.save(buf, format="PNG")
        return buf.getvalue()

    def test_png_image(self):
        """PNG 圖片"""
        img_bytes = self.create_test_image()
        pil_img, symbols, fmt_type = import_file_to_image_and_symbols(img_bytes, "test.png")
        assert isinstance(pil_img, Image.Image)
        assert symbols == []
        assert fmt_type == "image"

    def test_jpg_image(self):
        """JPG 圖片"""
        img_bytes = self.create_test_image()
        pil_img, symbols, fmt_type = import_file_to_image_and_symbols(img_bytes, "test.jpg")
        assert fmt_type == "image"

    def test_bmp_image(self):
        """BMP 圖片"""
        img_bytes = self.create_test_image()
        pil_img, symbols, fmt_type = import_file_to_image_and_symbols(img_bytes, "test.bmp")
        assert fmt_type == "image"

    def test_txt_jianpu(self):
        """TXT 簡譜"""
        text = "1 2 3 4 5 6 7 1"
        txt_bytes = text.encode("utf-8")
        pil_img, symbols, fmt_type = import_file_to_image_and_symbols(txt_bytes, "test.txt")
        assert isinstance(pil_img, Image.Image)
        assert len(symbols) == 8
        assert fmt_type == "txt"
        for sym in symbols:
            assert sym.type == "note"

    def test_json_symbols(self):
        """JSON 符號格式"""
        json_data = {
            "symbols": [
                {"id": "1", "type": "note", "pitch": "C4", "duration": "quarter", "x": 100, "y": 100, "width": 20, "height": 18, "confidence": 1.0},
                {"id": "2", "type": "note", "pitch": "D4", "duration": "quarter", "x": 150, "y": 100, "width": 20, "height": 18, "confidence": 1.0},
            ]
        }
        import json
        json_bytes = json.dumps(json_data).encode("utf-8")
        pil_img, symbols, fmt_type = import_file_to_image_and_symbols(json_bytes, "test.json")
        assert fmt_type == "json"
        assert len(symbols) == 2
        assert symbols[0].pitch == "C4"
        assert symbols[1].pitch == "D4"

    def test_unsupported_extension_raises(self):
        """不支援副檔名拋出異常"""
        with pytest.raises(ValueError, match="不支援的檔案格式"):
            import_file_to_image_and_symbols(b"test", "test.xyz")

    def test_supported_extensions_constants(self):
        """支援格式常數檢查"""
        assert ".png" in SUPPORTED_IMAGE_EXTENSIONS
        assert ".jpg" in SUPPORTED_IMAGE_EXTENSIONS
        assert ".pdf" in SUPPORTED_EXTENSIONS
        assert ".docx" in SUPPORTED_EXTENSIONS
        assert ".txt" in SUPPORTED_EXTENSIONS
        assert ".json" in SUPPORTED_EXTENSIONS
        assert len(SUPPORTED_EXTENSIONS) == len(SUPPORTED_IMAGE_EXTENSIONS) + 4  # pdf, docx, txt, json


class TestEdgeCases:
    """邊界情況"""

    def test_txt_with_windows_line_endings(self):
        """Windows 換行符"""
        text = "1 2 3\r\n4 5 6"
        symbols = parse_txt_to_symbols(text)
        assert len(symbols) == 6

    def test_txt_with_extra_spaces(self):
        """多餘空白"""
        text = "  1   2  \t  3  "
        symbols = parse_txt_to_symbols(text)
        assert len(symbols) == 3
