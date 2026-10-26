"""
SheetMusicOMR & ScoreOCR Toolkit Application Package
"""

from .server import create_app

app = create_app()

__all__ = ["create_app", "app"]
