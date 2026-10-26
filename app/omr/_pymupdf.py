"""PyMuPDF 匯入相容層。

PyMuPDF 1.24.3 起把模組名改成 `pymupdf`，舊的 `fitz` 雖然還能用，但每次匯入
都會印出棄用警告，在使用者的主控台看起來很像錯誤。這裡統一處理：
新版走 `pymupdf`，舊版才退回 `fitz`；兩者都沒有就讓 ImportError 往外拋，
由呼叫端決定改用 Poppler 或回報「引擎不可用」。
"""
from __future__ import annotations

try:  # PyMuPDF >= 1.24.3
    import pymupdf as fitz
except ImportError:  # 舊版 PyMuPDF 只有 fitz
    import fitz  # type: ignore[no-redef]

__all__ = ["fitz"]
