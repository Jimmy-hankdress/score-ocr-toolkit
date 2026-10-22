import shutil
import subprocess
import sys
from pathlib import Path
from typing import List
from src.ocr.recognizer import BaseRecognizer, Symbol


class HomrRecognizer(BaseRecognizer):
    """透過外部 homr CLI 產生 MusicXML。
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

        # HOMR 已輸出 MusicXML；此處先回傳管線狀態。
        # 後續再解析 MusicXML，轉為可校對的 Symbol 清單。
        return [
            Symbol(
                type="musicxml_document",
                pitch=None,
                duration=None,
                x=0,
                y=0,
                confidence=1.0,
            )
        ]
