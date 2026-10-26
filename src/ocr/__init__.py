"""
ScoreOCR Toolkit - OCR 核心模組套件
"""

from src.ocr.config import AppConfig, config, get_config
from src.ocr.format_importer import (
    SUPPORTED_EXTENSIONS,
    SUPPORTED_IMAGE_EXTENSIONS,
    import_file_to_image_and_symbols,
    parse_txt_to_symbols,
    render_text_to_score_image,
)
from src.ocr.homr_recognizer import HomrRecognizer
from src.ocr.jianpu_converter import (
    DURATION_BEATS,
    KEY_OFFSETS,
    PITCH_SEMITONES,
    SEMITONE_TO_JIANPU,
    parse_pitch,
    pitch_to_jianpu,
    symbol_to_jianpu_notation,
    symbols_to_jianpu_text,
)
from src.ocr.musicxml_builder import symbols_to_musicxml
from src.ocr.note_extractor import extract_score_symbols, parse_musicxml_notes
from src.ocr.recognizer import BaseRecognizer, PlaceholderRecognizer, Symbol, symbols_to_dict

__all__ = [
    # Config
    "AppConfig",
    "config",
    "get_config",
    # Logging
    "setup_logging",
    "get_logger",
    "logger",
    # Recognizer
    "Symbol",
    "BaseRecognizer",
    "PlaceholderRecognizer",
    "symbols_to_dict",
    # HOMR Recognizer
    "HomrRecognizer",
    # Format Importer
    "import_file_to_image_and_symbols",
    "parse_txt_to_symbols",
    "render_text_to_score_image",
    "SUPPORTED_EXTENSIONS",
    "SUPPORTED_IMAGE_EXTENSIONS",
    # Jianpu Converter
    "pitch_to_jianpu",
    "symbol_to_jianpu_notation",
    "symbols_to_jianpu_text",
    "parse_pitch",
    "PITCH_SEMITONES",
    "KEY_OFFSETS",
    "SEMITONE_TO_JIANPU",
    "DURATION_BEATS",
    # Note Extractor
    "extract_score_symbols",
    "parse_musicxml_notes",
    # MusicXML Builder
    "symbols_to_musicxml",
]
