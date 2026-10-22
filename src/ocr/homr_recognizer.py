import shutil
import subprocess
import sys
from pathlib import Path
from typing import List
from src.ocr.recognizer import BaseRecognizer, Symbol
from src.ocr.note_extractor import extract_score_symbols


class HomrRecognizer(BaseRecognizer):
    """透過外部 homr CLI 產生 MusicXML 並提取音符外框 (Bounding Box)。
    homr 採 AGPL-3.0，請由使用者另行安裝：
    pip install "homr[cpu]"
    """

    def __init__(self, python_executable: str | None = None):
        self.python_executable = python_executable or sys.executable or "python"

    def recognize(self, image_path: str) -> List[Symbol]:
        image = Path(image_path)
        output_xml = image.with_suffix(".musicxml")

        # 優先嘗試 python -m homr.main，若無則嘗試 homr 執行檔
        command = [
            self.python_executable,
            "-m",
            "homr.main",
            str(image),
        ]
        result = subprocess.run(
            command,
            capture_output=True,
            text=True,
            check=False,
        )
        if result.returncode != 0:
            homr_bin = shutil.which("homr") or str(
                Path(self.python_executable).parent / "homr.exe"
            )
            if Path(homr_bin).exists():
                result = subprocess.run(
                    [homr_bin, str(image)],
                    capture_output=True,
                    text=True,
                    check=False,
                )

        if result.returncode != 0:
            raise RuntimeError(
                "HOMR failed.\n"
                f"stdout:\n{result.stdout}\n"
                f"stderr:\n{result.stderr}"
            )
        if not output_xml.exists():
            raise FileNotFoundError(
                f"HOMR did not create expected MusicXML file: {output_xml}"
            )

        # 從辨識圖與產生的 MusicXML 中提取音符座標外框與音高資訊
        symbols = extract_score_symbols(str(image), str(output_xml))
        if not symbols:
            # 回退佔位符號
            return [
                Symbol(
                    id="doc-1",
                    type="musicxml_document",
                    pitch=None,
                    duration=None,
                    x=0,
                    y=0,
                    width=30,
                    height=30,
                    confidence=1.0,
                )
            ]

        return symbols
