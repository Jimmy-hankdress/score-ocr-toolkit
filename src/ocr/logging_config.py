"""
ScoreOCR Toolkit - 日誌配置模組
統一管理應用程式日誌，支援結構化輸出與不同等級控制。
"""

import logging
import sys
from pathlib import Path

from src.ocr.config import get_config


def setup_logging(
    level: str | None = None,
    log_file: Path | None = None,
    json_format: bool = False,
) -> None:
    """
    設定全域日誌配置。

    Args:
        level: 日誌等級 (DEBUG, INFO, WARNING, ERROR, CRITICAL)
        log_file: 可選的日誌檔案路徑
        json_format: 是否使用 JSON 格式輸出（生產環境建議開啟）
    """
    cfg = get_config()
    log_level = level or cfg.log_level

    # 建立格式化器
    if json_format:
        try:
            import pythonjsonlogger.jsonlogger as jsonlogger  # type: ignore[import-not-found]

            formatter = jsonlogger.JsonFormatter(
                fmt="%(asctime)s %(levelname)s %(name)s %(message)s",
                datefmt=cfg.log_date_format,
            )
        except ImportError:
            # 回退到標準格式
            formatter = logging.Formatter(
                fmt=cfg.log_format, datefmt=cfg.log_date_format
            )
    else:
        formatter = logging.Formatter(
            fmt=cfg.log_format, datefmt=cfg.log_date_format
        )

    # 根日誌器設定
    root_logger = logging.getLogger()
    root_logger.setLevel(log_level)

    # 清除現有 handlers 避免重複
    root_logger.handlers.clear()

    # Console handler
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setFormatter(formatter)
    console_handler.setLevel(log_level)
    root_logger.addHandler(console_handler)

    # File handler (可選)
    if log_file:
        log_file.parent.mkdir(parents=True, exist_ok=True)
        file_handler = logging.FileHandler(log_file, encoding="utf-8")
        file_handler.setFormatter(formatter)
        file_handler.setLevel(log_level)
        root_logger.addHandler(file_handler)

    # 降低第三方庫的日誌噪音
    logging.getLogger("uvicorn.access").setLevel(logging.WARNING)
    logging.getLogger("uvicorn.error").setLevel(logging.INFO)
    logging.getLogger("httpx").setLevel(logging.WARNING)
    logging.getLogger("httpcore").setLevel(logging.WARNING)


def get_logger(name: str) -> logging.Logger:
    """取得指定名稱的日誌器"""
    return logging.getLogger(name)


# 模組級日誌器（各模組可直接 import 使用）
logger = get_logger(__name__)
