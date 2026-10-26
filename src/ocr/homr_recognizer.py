import asyncio
import os
import shutil
import subprocess
import sys
from pathlib import Path

from src.ocr.config import get_config
from src.ocr.logging_config import get_logger
from src.ocr.note_extractor import extract_score_symbols
from src.ocr.recognizer import BaseRecognizer, Symbol

logger = get_logger(__name__)
_cfg = get_config()


def _run_homr_sync(command: list[str], timeout: int) -> subprocess.CompletedProcess:
    """同步執行 HOMR 命令（供 thread pool 使用）"""
    # 清除 Hermes kernel 注入的 PYTHONPATH，避免子進程載入 broken numpy
    env = {k: v for k, v in os.environ.items() if k not in ('PYTHONPATH', 'PYTHONHOME')}
    env['PYTHONUNBUFFERED'] = '1'
    return subprocess.run(
        command,
        capture_output=True,
        text=True,
        check=False,
        timeout=timeout,
        env=env,
    )


class HomrRecognizer(BaseRecognizer):
    """透過外部 homr CLI 產生 MusicXML 並提取音符外框 (Bounding Box)。
    homr 採 AGPL-3.0，請由使用者另行安裝：
    pip install "homr[cpu]"
    """

    def __init__(self, python_executable: str | None = None):
        self.python_executable = python_executable or sys.executable or "python"

    async def recognize(self, image_path: str) -> list[Symbol]:
        """非同步辨識介面，避免阻塞事件循環"""
        return await asyncio.to_thread(self._recognize_sync, image_path)

    def _recognize_sync(self, image_path: str) -> list[Symbol]:
        """同步版本的辨識邏輯"""
        image = Path(image_path)
        output_xml = image.with_suffix(".musicxml")

        # 優先嘗試 python -m homr.main，若無則嘗試 homr 執行檔
        command = [
            self.python_executable,
            "-m",
            "homr.main",
            str(image),
        ]
        logger.debug("執行 HOMR 命令: %s", " ".join(command))

        try:
            result = _run_homr_sync(command, _cfg.homr_timeout_seconds)
        except subprocess.TimeoutExpired:
            logger.error("HOMR 執行逾時 (%ds)", _cfg.homr_timeout_seconds)
            raise RuntimeError(f"HOMR 執行逾時 ({_cfg.homr_timeout_seconds}s)") from None

        if result.returncode != 0:
            logger.warning("python -m homr.main 失敗 (code=%d)，嘗試 homr 執行檔", result.returncode)
            homr_bin = shutil.which("homr") or str(
                Path(self.python_executable).parent / "homr.exe"
            )
            if Path(homr_bin).exists():
                logger.debug("執行 HOMR 執行檔: %s %s", homr_bin, image)
                try:
                    result = _run_homr_sync([homr_bin, str(image)], _cfg.homr_timeout_seconds)
                except subprocess.TimeoutExpired:
                    logger.error("HOMR 執行檔執行逾時 (%ds)", _cfg.homr_timeout_seconds)
                    raise RuntimeError(f"HOMR 執行檔執行逾時 ({_cfg.homr_timeout_seconds}s)") from None

        if result.returncode != 0:
            logger.error("HOMR 失敗: stdout=%s, stderr=%s", result.stdout[:500], result.stderr[:500])
            raise RuntimeError(
                "HOMR failed.\n"
                f"stdout:\n{result.stdout}\n"
                f"stderr:\n{result.stderr}"
            )

        if not output_xml.exists():
            logger.error("HOMR 未產生預期的 MusicXML 檔案: %s", output_xml)
            raise FileNotFoundError(
                f"HOMR did not create expected MusicXML file: {output_xml}"
            )

        logger.info("HOMR 辨識完成，產生 MusicXML: %s", output_xml)

        # 從辨識圖與產生的 MusicXML 中提取音符座標外框與音高資訊
        symbols = extract_score_symbols(str(image), str(output_xml))
        if not symbols:
            logger.warning("未從 MusicXML 提取到音符符號，回退佔位符號")
            # 回退佔位符號
            return [
                Symbol(
                    id="doc-1",
                    type="musicxml_document",
                    pitch=None,
                    duration=None,
                    x=0,
                    y=0,
                    width=_cfg.default_note_width,
                    height=_cfg.default_note_height,
                    confidence=1.0,
                )
            ]

        return symbols
