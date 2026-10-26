"""
ScoreOCR Toolkit - 配置管理模組
集中管理所有魔術數字、預設值與環境變數配置。
"""

import os
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class AppConfig:
    """應用程式核心配置"""

    # 伺服器設定
    host: str = "127.0.0.1"
    port: int = 8000
    reload: bool = True

    # 檔案上傳限制
    max_upload_size_mb: int = 50
    max_upload_size_bytes: int = 50 * 1024 * 1024  # 50 MB

    # 目錄路徑
    base_dir: Path = Path(__file__).resolve().parent.parent.parent
    upload_dir: Path = base_dir / "uploads"
    processed_dir: Path = base_dir / "processed"
    static_dir: Path = base_dir / "static"

    # 圖片處理參數
    gaussian_blur_kernel: tuple[int, int] = (3, 3)
    otsu_threshold: int = 0
    otsu_maxval: int = 255

    # HOMR 設定
    homr_timeout_seconds: int = 120

    # OpenCV 音符提取參數
    staff_line_len_ratio: int = 40  # w_img // 40
    min_staff_line_len: int = 20
    blob_kernel_size: tuple[int, int] = (3, 3)
    min_notehead_area: int = 12
    max_notehead_area: int = 450
    min_notehead_dim: int = 6
    max_notehead_dim: int = 36
    row_height_ratio: int = 15  # h_img // 15
    min_row_height: int = 50

    # 文字轉圖片渲染參數
    text_render_width: int = 1200
    text_render_min_height: int = 800
    text_line_height: int = 36
    text_margin: int = 50
    text_header_height: int = 60

    # 預設音符外框尺寸
    default_note_width: int = 18
    default_note_height: int = 16
    default_confidence: float = 1.0

    # 簡譜預設值
    default_key: str = "C"
    default_meter: str = "4/4"
    default_title: str = "ScoreOCR Score"

    # MusicXML 預設值
    musicxml_divisions: int = 4
    musicxml_default_key_fifths: int = 0
    musicxml_default_time_beats: int = 4
    musicxml_default_time_beat_type: int = 4
    musicxml_default_clef_sign: str = "G"
    musicxml_default_clef_line: int = 2

    # JSON 匯入畫布參數
    json_canvas_min_width: int = 1000
    json_canvas_min_height: int = 700
    json_canvas_padding: int = 100
    json_default_x_offset: int = 50
    json_default_y_offset: int = 100
    json_grid_col_width: int = 45
    json_grid_row_height: int = 60
    json_grid_cols: int = 16

    # 日誌設定
    log_level: str = "INFO"
    log_format: str = "%(asctime)s | %(levelname)-8s | %(name)s | %(message)s"
    log_date_format: str = "%Y-%m-%d %H:%M:%S"

    # 支援格式
    supported_image_extensions: frozenset[str] = frozenset(
        {".png", ".jpg", ".jpeg", ".bmp", ".webp", ".tiff", ".tif"}
    )
    supported_extensions: frozenset[str] = frozenset(
        supported_image_extensions | {".pdf", ".docx", ".txt", ".json"}
    )

    @classmethod
    def from_env(cls) -> "AppConfig":
        """從環境變數建立配置（可覆寫預設值）"""
        return cls(
            host=os.getenv("SCOREOCR_HOST", "127.0.0.1"),
            port=int(os.getenv("SCOREOCR_PORT", "8000")),
            reload=os.getenv("SCOREOCR_RELOAD", "true").lower() == "true",
            max_upload_size_mb=int(os.getenv("SCOREOCR_MAX_UPLOAD_MB", "50")),
            log_level=os.getenv("SCOREOCR_LOG_LEVEL", "INFO"),
        )


# 全域單例配置實例
config = AppConfig.from_env()


def get_config() -> AppConfig:
    """取得配置實例（供依賴注入使用）"""
    return config
