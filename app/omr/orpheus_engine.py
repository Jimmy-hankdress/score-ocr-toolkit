# -*- coding: utf-8 -*-
"""OrpheusNet 简谱 OMR 引擎封装。

提供 detect 与识别接口，供 pipeline 选用。OrpheusNet 是整图→MIDI 管线，
本模块封装：环境检测 → 自适应二值化 → 图像分割 → 音符识别 → 输出音符序列。

集成目标：替换 Tesseract 的简谱数字识别，提升简谱识别准确率。
"""
from __future__ import annotations

import os
import sys
import json
import subprocess
from dataclasses import dataclass, field
from pathlib import Path

# OrpheusNet 源码与独立 Python 3.11 环境（torch CPU）
ORPHEUS_DIR = Path(r"D:\OrpheusNet")
ORPHEUS_PY = Path(r"D:\SheetMusicOMR_torchenv\Scripts\python.exe")


@dataclass
class OrpheusStatus:
    available: bool = False
    mode: str = "orpheus-jianpu"
    python: str = ""
    version: str = ""
    note: str = ""


def detect_orpheus() -> OrpheusStatus:
    """检测 OrpheusNet 环境是否就绪（源码 + Python3.11 + torch）。"""
    status = OrpheusStatus()
    if not ORPHEUS_DIR.exists() or not (ORPHEUS_DIR / "main.py").exists():
        status.note = f"找不到 OrpheusNet 源码：{ORPHEUS_DIR}"
        return status
    if not ORPHEUS_PY.exists():
        status.note = f"找不到 OrpheusNet Python 环境：{ORPHEUS_PY}"
        return status
    # 检测 torch+torchvision 可用
    try:
        r = subprocess.run(
            [str(ORPHEUS_PY), "-c", "import torch, torchvision; print(torch.__version__)"],
            capture_output=True, text=True, timeout=60,
        )
        if r.returncode != 0:
            status.note = f"OrpheusNet 环境缺依赖：{(r.stderr or '').strip()[:200]}"
            return status
        status.version = (r.stdout or "").strip()
    except (OSError, subprocess.SubprocessError) as exc:
        status.note = f"OrpheusNet Python 无法执行：{exc}"
        return status
    status.available = True
    status.python = str(ORPHEUS_PY)
    return status


def recognize_score(image_path: str, out_index: str = "score") -> dict:
    """调用 OrpheusNet 识别一张简谱图，返回简谱数字 token 序列。

    通过子进程调用 orpheus_run.py，解析其输出的 JSON。
    返回 {lines, notes[{tok,dur,oct}], noteCount, midi}.
    """
    script = ORPHEUS_DIR / "orpheus_run.py"
    r = subprocess.run(
        [str(ORPHEUS_PY), str(script), image_path, out_index],
        capture_output=True, text=True, timeout=900,
        cwd=str(ORPHEUS_DIR),
    )
    if r.returncode != 0:
        raise RuntimeError(
            f"OrpheusNet 识别失败：{(r.stderr or '').strip()[-400:]}"
        )
    # stdout 末尾是 JSON 行（前面有模型加载信息）
    data = None
    for line in reversed((r.stdout or "").splitlines()):
        line = line.strip()
        if line.startswith("{"):
            try:
                data = json.loads(line)
                break
            except json.JSONDecodeError:
                continue
    if data is None:
        raise RuntimeError(f"OrpheusNet 未返回 JSON。原始输出尾部：{(r.stdout or '')[-300:]}")
    # midi 由 orpheus_run 生成（若有），确认路径
    midi_file = ORPHEUS_DIR / "output" / "midi" / f"output{out_index}.mid"
    data["midi"] = str(midi_file) if midi_file.exists() else ""
    return data
