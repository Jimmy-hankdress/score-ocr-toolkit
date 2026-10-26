# -*- coding: utf-8 -*-
"""
ScoreForge OMR 引擎封裝（V3.00 整合版）。

呼叫本機 ScoreForge OMR kit 的 CLI（scoreforge.cmd → node scoreforge.mjs json）：
- 自動啟動引擎、等模型載入、輪詢進度（CLI 內建，不用自己寫 HTTP）
- 全譜一次辨識（含多頁合併、歌詞去重／繁體轉換、和弦對位），
  輸出精簡 JSON 後轉成 V3 內部 ScoreDocument
- 離線、不需 API key

與 jianpu2（Tesseract 逐頁幾何分析）相比的差異：
- 不依賴 Tesseract／PDF 轉圖，PDF 直接餵引擎
- 和弦、簡譜、歌詞完整對齊到小節
- 慢：3 頁印刷譜約 4–7 分鐘（首次多 20–40 秒引擎啟動），
  所以 timeout 取 1500s、任務訊息明確提示「辨識中」

kit 路徑依序探測：
  1. 環境變數 SCOREFORGE_KIT
  2. D:\\Harness\\ScoreForge\\dist\\ScoreForge-OMR-kit\\cli\\scoreforge.cmd
  3. D:\\Harness\\ScoreForge\\cli\\scoreforge.cmd（開發版）
  4. PATH 上的 scoreforge.cmd
"""
from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import tempfile
from pathlib import Path
from typing import Any

# ── kit CLI 路徑探測 ──────────────────────────────────────────────
_KIT_CLI_CANDIDATES = [
    os.environ.get("SCOREFORGE_KIT"),
    r"D:\ScoreForge-App\cli\scoreforge.cmd",
    r"D:\ScoreForge-App\dist\ScoreForge-OMR-kit\cli\scoreforge.cmd",
    r"D:\Harness\ScoreForge\cli\scoreforge.cmd",
    r"D:\Harness\ScoreForge\dist\ScoreForge-OMR-kit\cli\scoreforge.cmd",
    r"D:\ScoreForge-OMR\cli\scoreforge.cmd",
    r"D:\ScoreForge-OMR\sf.cmd",
]


def _sf_env(cli: str | None = None) -> dict[str, str]:
    env = dict(os.environ)
    extra_paths = [
        r"D:\Program Files\nodejs",
        r"C:\Program Files\nodejs",
        r"D:\ScoreForge-OMR\node",
    ]
    cur_path = env.get("PATH", "")
    prepend = [
        p for p in extra_paths
        if Path(p).is_dir() and p.lower() not in cur_path.lower()
    ]
    if prepend:
        env["PATH"] = os.pathsep.join(prepend + ([cur_path] if cur_path else []))

    cli_lower = (cli or "").lower()
    if "scoreforge-omr" in cli_lower and "scoreforge-app" not in cli_lower:
        env.setdefault("SCOREFORGE_URL", "http://127.0.0.1:8799")
        env.setdefault("SCOREFORGE_TOKEN", "devtoken")
        env.setdefault("SCOREFORGE_DATA", r"D:\ScoreForge-OMR-data")
    return env


def _find_cli() -> str | None:
    for cand in _KIT_CLI_CANDIDATES:
        if cand and Path(cand).exists():
            return cand
    found = shutil.which("scoreforge") or shutil.which("scoreforge.cmd")
    return found


# ── 偵測 ─────────────────────────────────────────────────────────
def detect_scoreforge() -> dict:
    """回傳可給前端展示的 ScoreForge 引擎狀態。"""
    status: dict[str, Any] = {
        "available": False,
        "mode": "scoreforge-unavailable",
        "version": "",
        "path": "",
        "note": "",
        "timeoutSeconds": 1500,
    }
    cli = _find_cli()
    if not cli:
        status["note"] = "找不到 ScoreForge kit CLI（試過：\n" + "\n".join(
            c for c in _KIT_CLI_CANDIDATES if c
        ) + "\n也可設定環境變數 SCOREFORGE_KIT 指向 cli\\scoreforge.cmd）"
        return status

    status["path"] = cli
    # 快速探測：health --json 約 2 秒（引擎已開時）；引擎沒開 CLI 會自動拉起來
    try:
        proc = subprocess.run(
            [cli, "health", "--json"],
            capture_output=True, text=True, timeout=90,
            env=_sf_env(cli),
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        )
        if proc.returncode == 0:
            try:
                data = json.loads(proc.stdout)
            except (json.JSONDecodeError, ValueError):
                data = {}
            ok = bool(data.get("ok"))
            status["version"] = str(data.get("version", ""))
            checks = data.get("checks") or {}
            jpe = checks.get("jpeditor_omr") or {}
            status["available"] = ok and bool(jpe.get("ok"))
            if ok and not jpe.get("ok", True):
                status["note"] = "引擎在運行但 jpeditor 簡譜 OMR 未就緒：" + str(jpe.get("message", ""))
                return status
            if not ok:
                status["note"] = "引擎健康檢查未通過，辨識時會再嘗試自動啟動。"
        else:
            status["note"] = f"health 回傳非零（{proc.returncode}），辨識時會自動重試。"
            # 不因此判定不可用：CLI 會自動啟動引擎
            status["available"] = True
    except (OSError, subprocess.SubprocessError):
        status["available"] = True
        status["note"] = "無法快測引擎狀態，辨識時會自動啟動。"

    status["mode"] = "scoreforge"
    status.setdefault("note", "")
    return status


# ── 簡譜 token 產生 ─────────────────────────────────────────────
def _note_token(
    degree: int | None,
    octave: int,
    accidental: str | None,
    dotted: bool,
    dur: float = 1.0,
    tie: bool = False,
    slur: bool = False,
) -> str:
    """degree(0-7) + octaveShift + accidental + dur + dotted → V3 簡譜 token。

    - 組合高低音點（\\u0307 高八度、\\u0323 低八度）緊接在數字之後，確保附點或底線時仍位於數字正上方／正下方
    - 時值減半線 `_`（八分 `_`、十六分 `__`、三十二分 `___`）
    - 附點加 `.`、連音線加 `~`、圓滑線加 `^`
    """
    if degree is None:
        return ""
    tok = str(degree)
    if accidental == "#":
        tok = "#" + tok
    elif accidental == "b":
        tok = "b" + tok
    if octave and octave > 0:
        tok += "\u0307" * int(octave)
    elif octave and octave < 0:
        tok += "\u0323" * abs(int(octave))

    try:
        q = float(dur)
    except (TypeError, ValueError):
        q = 1.0
    base_q = (q / 1.5) if dotted else q
    if base_q <= 0.19:
        tok += "___"
    elif base_q <= 0.4:
        tok += "__"
    elif base_q < 0.9:
        tok += "_"

    if dotted:
        tok += "."
    if tie:
        tok += "~"
    if slur:
        tok += "^"
    return tok


# 時值（beats 單位）→ V3 duration 名稱
def _duration_name(dur: Any, dotted: bool) -> str:
    try:
        q = float(dur)
    except (TypeError, ValueError):
        q = 1.0
    names = {
        0.125: "32nd",
        0.25: "16th",
        0.5: "eighth",
        1.0: "quarter",
        1.5: "dotted-quarter",
        2.0: "half",
        3.0: "dotted-half",
        4.0: "whole",
        6.0: "dotted-whole",
    }
    if dotted and q in names:
        return f"dotted-{names[q]}"
    return names.get(q, "quarter")


# ── 辨識 ─────────────────────────────────────────────────────────
def recognize_score(source: str | Path, progress=None) -> dict:
    """
    執行 ScoreForge CLI `json <source> --full --out <tmp>`，回傳精簡 JSON dict。
    source 可以是 PDF／JPG／PNG／DOCX 或 .sfz/.json（引擎端既有結果）。

    progress(ratio: float, message: str) 可選回撥（供 pipeline 更新任務進度）。
    失敗時拋 RuntimeError（訊息可讀）。
    """
    cli = _find_cli()
    if not cli:
        raise RuntimeError(detect_scoreforge()["note"] or "找不到 ScoreForge kit CLI")
    source = Path(source)
    if not source.exists():
        raise RuntimeError(f"來源檔案不存在：{source}")

    tmp_dir = Path(tempfile.mkdtemp(prefix="sfkit-"))
    out_json = tmp_dir / "result.json"

    cmd = [
        cli, "json", str(source.resolve()),
        "--full", "--out", str(out_json),
    ]

    try:
        proc = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=1500,
            env=_sf_env(cli),
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        )
    except subprocess.TimeoutExpired:
        raise RuntimeError("ScoreForge 辨識逾時（>1500s），請重試或改用 jianpu2 引擎。")
    except (OSError, subprocess.SubprocessError) as exc:
        raise RuntimeError(f"無法執行 ScoreForge CLI：{exc}")

    if proc.returncode != 0:
        tail = (proc.stderr or proc.stdout or "").strip()[-600:]
        raise RuntimeError(f"ScoreForge CLI 回傳 {proc.returncode}：{tail}")

    if not out_json.exists():
        stdout = (proc.stdout or "").strip()
        if stdout.startswith("{"):
            data = json.loads(stdout)
        else:
            raise RuntimeError(
                f"ScoreForge 未產生 JSON 輸出（stderr 尾部：{(proc.stderr or '')[-400:]!r}）"
            )
    else:
        data = json.loads(out_json.read_text(encoding="utf-8"))

    if isinstance(data, list):
        if not data:
            raise RuntimeError("ScoreForge 未回傳任何結果")
        data = data[0]
    if "summary" not in data and "sections" not in data:
        raise RuntimeError("ScoreForge 回傳格式不符預期（缺少 summary/sections）")
    return data


def _format_verse_line_and_ticks(
    expanded_tokens: list[dict[str, Any]],
    verse_idx: int,
    split_lyrics_fn,
) -> tuple[str, list[int]]:
    """將單一段落歌詞（verse 0..3）依小節內音符拍位與休止／延長線位置對齊輸出：
    - 同拍內音節緊鄰（如八分音符「隨著」）
    - 跨拍邊界自動加空白間距（如「隨著 我的 步伐 輕輕」），與 noteText 的雙空白拍群視覺對齊
    - 前導或中間遇到休止符 `0`／延長線 `-`／無詞音符時，補入對位空白，使歌詞落在正確音符正下方
    - 同時回傳每個歌詞音節對應的精確 tick 列表（480 ticks = 1 拍）
    """
    last_non_empty = -1
    for idx, item in enumerate(expanded_tokens):
        syl = (item["lyrics"][verse_idx] or "").strip()
        if syl:
            last_non_empty = idx
    if last_non_empty < 0:
        return "", []

    parts: list[str] = []
    ticks: list[int] = []
    for idx in range(last_non_empty + 1):
        item = expanded_tokens[idx]
        if idx > 0:
            prev_col = int(expanded_tokens[idx - 1]["beat"] + 1e-6)
            curr_col = int(item["beat"] + 1e-6)
            if curr_col != prev_col:
                parts.append(" ")
        syl = (item["lyrics"][verse_idx] or "").strip()
        if syl:
            # 若上一個同拍也是純拉丁字，加空白避免黏連
            if (
                parts
                and not parts[-1].endswith(" ")
                and syl[0].isascii()
                and parts[-1][-1].isascii()
            ):
                parts.append(" ")
            parts.append(syl)
            sub_syls = split_lyrics_fn(syl) or [syl]
            tick_val = int(round(item["beat"] * 480))
            for _ in sub_syls:
                ticks.append(tick_val)
        else:
            # 空音位（如前導休止符 0、延長線 - 或過門音）：補入視覺佔位空白
            parts.append("  ")

    text = "".join(parts).rstrip()
    return text, ticks


# ── 轉換成 V3 內部文件 ───────────────────────────────────────────
def scoreforge_to_document(
    data: dict,
    source_name: str = "",
    work_dir: str | Path | None = None,
) -> dict:
    """
    把 ScoreForge 精簡 JSON 轉成 V3 pipeline 可直接採用的文件：

        {
          "document": ScoreDocument,   # 已填入 chordText/noteText/lyricText..lyricText4 + ticks + beats
          "warnings": list[str],       # 品質提示（measuresNotFull、recognitionNotes…）
          "sfzJson": str,             # 原始 JSON 字串（存檔供複審／再匯出）
        }
    """
    from ..models import ScoreBeat, ScoreDocument, ScoreMeasure, new_id, split_lyrics

    summary = data.get("summary") or {}
    sections = data.get("sections") or []
    warnings: list[str] = []

    not_full = summary.get("measuresNotFull") or []
    if not_full:
        shown = ", ".join(str(x) for x in not_full[:8])
        warnings.append(
            f"第 {shown} 小節拍數不等於拍號，可能辨識有誤，請核對。"
            + (f"（共 {len(not_full)} 節）" if len(not_full) > 8 else "")
        )
    if summary.get("recognitionNotes"):
        warnings.append("引擎自動修正：" + str(summary["recognitionNotes"]))

    time_sig = str(summary.get("timeSignature") or "4/4")
    try:
        tempo = int(float(summary.get("tempoBpm") or 90))
    except (TypeError, ValueError):
        tempo = 90

    measures: list[ScoreMeasure] = []
    for sec in sections:
        sec_label = str(sec.get("label") or "").strip()
        sec_measures = sec.get("measures") or []
        for m_idx, m in enumerate(sec_measures):
            measure_no = len(measures) + 1
            chords = m.get("chords") or []
            notes = m.get("notes") or []

            expanded_tokens: list[dict[str, Any]] = []
            beats: list[ScoreBeat] = []
            acc_beat = 0.0

            for n in notes:
                try:
                    raw_dur = float(n.get("durationBeats") or 1.0)
                except (TypeError, ValueError):
                    raw_dur = 1.0
                if raw_dur <= 0:
                    raw_dur = 1.0
                dotted = bool(n.get("dotted"))
                is_rest = bool(n.get("rest"))
                is_dash = bool(n.get("dash"))
                tie = bool(n.get("tie"))
                slur = bool(n.get("slur"))

                raw_lyrics = n.get("lyrics") if isinstance(n.get("lyrics"), list) else []
                v_lyrics: list[str] = []
                for vi in range(4):
                    key_name = "lyric" if vi == 0 else f"lyric{vi + 1}"
                    val = str(
                        n.get(key_name)
                        or (raw_lyrics[vi] if vi < len(raw_lyrics) else "")
                        or ""
                    ).strip()
                    v_lyrics.append(val)

                if is_dash:
                    if raw_dur >= 2.0:
                        whole_beats = max(1, int(round(raw_dur)))
                        for _ in range(whole_beats):
                            expanded_tokens.append({
                                "tok": "-",
                                "beat": acc_beat,
                                "dur": 1.0,
                                "lyrics": ["", "", "", ""],
                                "is_rest": False,
                                "is_dash": True,
                            })
                            beats.append(ScoreBeat(
                                beat=max(1, int(acc_beat + 1e-6) + 1),
                                note="-",
                                lyric="",
                                chord="",
                                duration="quarter",
                                confidence=1.0,
                            ))
                            acc_beat += 1.0
                    else:
                        tok = "-"
                        base_q = (raw_dur / 1.5) if dotted else raw_dur
                        if base_q <= 0.19:
                            tok += "___"
                        elif base_q <= 0.4:
                            tok += "__"
                        elif base_q < 0.9:
                            tok += "_"
                        if dotted:
                            tok += "."
                        expanded_tokens.append({
                            "tok": tok,
                            "beat": acc_beat,
                            "dur": raw_dur,
                            "lyrics": ["", "", "", ""],
                            "is_rest": False,
                            "is_dash": True,
                        })
                        beats.append(ScoreBeat(
                            beat=max(1, int(acc_beat + 1e-6) + 1),
                            note=tok,
                            lyric="",
                            chord="",
                            duration=_duration_name(raw_dur, dotted),
                            confidence=1.0,
                        ))
                        acc_beat += raw_dur
                    continue

                if is_rest:
                    if raw_dur >= 2.0:
                        whole_beats = max(1, int(round(raw_dur)))
                        for b_i in range(whole_beats):
                            tok = "0"
                            expanded_tokens.append({
                                "tok": tok,
                                "beat": acc_beat,
                                "dur": 1.0,
                                "lyrics": ["", "", "", ""],
                                "is_rest": True,
                                "is_dash": False,
                            })
                            beats.append(ScoreBeat(
                                beat=max(1, int(acc_beat + 1e-6) + 1),
                                note=tok,
                                lyric="",
                                chord="",
                                duration="quarter",
                                confidence=1.0,
                            ))
                            acc_beat += 1.0
                    else:
                        tok = _note_token(0, 0, None, dotted, dur=raw_dur)
                        expanded_tokens.append({
                            "tok": tok,
                            "beat": acc_beat,
                            "dur": raw_dur,
                            "lyrics": ["", "", "", ""],
                            "is_rest": True,
                            "is_dash": False,
                        })
                        beats.append(ScoreBeat(
                            beat=max(1, int(acc_beat + 1e-6) + 1),
                            note=tok,
                            lyric="",
                            chord="",
                            duration=_duration_name(raw_dur, dotted),
                            confidence=1.0,
                        ))
                        acc_beat += raw_dur
                    continue

                deg = n.get("degree")
                octv = int(n.get("octave") or 0)
                acc = n.get("accidental")

                if raw_dur >= 2.0:
                    # 二分／附點二分／全音符：首拍為四分音符 token，後續拍以延長線 `-` 還原原稿拍距
                    tok = _note_token(deg, octv, acc, False, dur=1.0, tie=tie, slur=slur)
                    expanded_tokens.append({
                        "tok": tok,
                        "beat": acc_beat,
                        "dur": 1.0,
                        "lyrics": v_lyrics,
                        "is_rest": False,
                        "is_dash": False,
                    })
                    beats.append(ScoreBeat(
                        beat=max(1, int(acc_beat + 1e-6) + 1),
                        note=tok,
                        lyric=v_lyrics[0],
                        chord="",
                        duration=_duration_name(1.0, False),
                        confidence=1.0,
                        annotation=f"degree={deg}" if deg is not None else "",
                    ))
                    acc_beat += 1.0
                    extra_dashes = max(0, int(round(raw_dur)) - 1)
                    for _ in range(extra_dashes):
                        expanded_tokens.append({
                            "tok": "-",
                            "beat": acc_beat,
                            "dur": 1.0,
                            "lyrics": ["", "", "", ""],
                            "is_rest": False,
                            "is_dash": True,
                        })
                        beats.append(ScoreBeat(
                            beat=max(1, int(acc_beat + 1e-6) + 1),
                            note="-",
                            lyric="",
                            chord="",
                            duration="quarter",
                            confidence=1.0,
                        ))
                        acc_beat += 1.0
                else:
                    tok = _note_token(deg, octv, acc, dotted, dur=raw_dur, tie=tie, slur=slur)
                    expanded_tokens.append({
                        "tok": tok,
                        "beat": acc_beat,
                        "dur": raw_dur,
                        "lyrics": v_lyrics,
                        "is_rest": False,
                        "is_dash": False,
                    })
                    beats.append(ScoreBeat(
                        beat=max(1, int(acc_beat + 1e-6) + 1),
                        note=tok,
                        lyric=v_lyrics[0],
                        chord="",
                        duration=_duration_name(raw_dur, dotted),
                        confidence=1.0,
                        annotation=f"degree={deg}" if deg is not None else "",
                    ))
                    acc_beat += raw_dur

            # 組裝拍群分組的 noteText 與 noteTicks（同拍內 1 個空白，跨拍 2 個空白；若前一音為英文長字則按字長自動加寬拍距，讓音符與上方和弦對齊英文單字）
            note_parts: list[str] = []
            note_ticks: list[int] = []
            for idx, item in enumerate(expanded_tokens):
                note_ticks.append(int(round(item["beat"] * 480)))
                if idx == 0:
                    note_parts.append(item["tok"])
                else:
                    prev_item = expanded_tokens[idx - 1]
                    prev_col = int(prev_item["beat"] + 1e-6)
                    curr_col = int(item["beat"] + 1e-6)
                    prev_lyr = (prev_item["lyrics"][0] or "").strip() if prev_item.get("lyrics") else ""
                    prev_lyr2 = (
                        (prev_item["lyrics"][1] or "").strip()
                        if prev_item.get("lyrics") and len(prev_item["lyrics"]) > 1
                        else ""
                    )
                    ascii_w = (
                        len(prev_lyr)
                        if (
                            prev_lyr
                            and sum(1 for c in prev_lyr if c.isascii()) >= len(prev_lyr) * 0.7
                            and len(prev_lyr) >= 3
                        )
                        else 0
                    )
                    jp_w = sum(2 if ord(c) > 255 else 1 for c in prev_lyr2) if len(prev_lyr2) >= 2 else 0
                    pad_w = max(ascii_w, jp_w)
                    if pad_w >= 3:
                        pad_n = max(2, min(12, pad_w))
                        sep = " " * pad_n
                    else:
                        sep = "  " if curr_col != prev_col else " "
                    note_parts.append(sep + item["tok"])
            note_text = "".join(note_parts)

            # 多行歌詞（1..4 段）與其對應 ticks
            verse_texts: list[str] = []
            verse_ticks: list[list[int]] = []
            max_verse_row = 1
            for vi in range(4):
                v_txt, v_tks = _format_verse_line_and_ticks(expanded_tokens, vi, split_lyrics)
                verse_texts.append(v_txt)
                verse_ticks.append(v_tks)
                if v_txt.strip():
                    max_verse_row = vi + 1

            # 和弦：依拍位對應到最接近的音符 token 索引（chordOffsets）與精確 tick（chordTicks）
            chord_symbols: list[str] = []
            chord_offsets: list[int] = []
            chord_ticks: list[int] = []
            used_offsets: set[int] = set()
            for c in chords:
                sym = str(c.get("symbol") or "").strip()
                if not sym:
                    continue
                cb = float(c.get("beat") or 0.0)
                if cb < 0.65 and 0 not in used_offsets:
                    cb = 0.0
                c_tick = max(0, int(round(cb * 480)))
                if expanded_tokens:
                    best_ti = min(
                        range(len(expanded_tokens)),
                        key=lambda ti: abs(expanded_tokens[ti]["beat"] - cb),
                    )
                    while best_ti in used_offsets and best_ti + 1 < len(expanded_tokens):
                        best_ti += 1
                    used_offsets.add(best_ti)
                    c_tick = int(round(expanded_tokens[best_ti]["beat"] * 480))
                else:
                    best_ti = len(chord_symbols)
                chord_symbols.append(sym)
                chord_offsets.append(best_ti)
                chord_ticks.append(c_tick)
                if beats:
                    b_idx = min(len(beats) - 1, max(0, best_ti))
                    beats[b_idx].chord = (
                        f"{beats[b_idx].chord} {sym}".strip() if beats[b_idx].chord else sym
                    )

            chord_text = " ".join(chord_symbols)

            measure = ScoreMeasure(
                number=measure_no,
                chordText=chord_text,
                chordOffsets=chord_offsets,
                chordTicks=chord_ticks,
                noteText=note_text,
                noteTicks=note_ticks,
                lyricText=verse_texts[0],
                lyricTicks=verse_ticks[0],
                lyricText2=verse_texts[1],
                lyricText2Ticks=verse_ticks[1],
                lyricText3=verse_texts[2],
                lyricText3Ticks=verse_ticks[2],
                lyricText4=verse_texts[3],
                lyricText4Ticks=verse_ticks[3],
                lyricRows=max_verse_row,
                section=(sec_label if (m_idx == 0 and sec_label) else ""),
                beats=beats,
            )
            measures.append(measure)

    # 統一同一視覺行（每行 4 小節）的 lyricRows，確保多段歌詞在同行小節輸入框對齊顯示
    for line_start in range(0, len(measures), 4):
        line_ms = measures[line_start : line_start + 4]
        line_max_rows = max((m.lyricRows for m in line_ms), default=1)
        if line_max_rows > 1:
            for m in line_ms:
                m.lyricRows = max(m.lyricRows, line_max_rows)

    # 存一份原始 JSON 到 work_dir 供複審
    sfz_json = ""
    if work_dir is not None:
        try:
            p = Path(work_dir) / "scoreforge.json"
            p.write_text(json.dumps(data, ensure_ascii=False, indent=1), encoding="utf-8")
            sfz_json = p.read_text(encoding="utf-8")
        except OSError:
            pass

    raw_title = str(summary.get("title") or "").strip()
    stem_title = Path(source_name).stem.strip() if source_name else ""
    _ui_bad_titles = ("transpose", "guitar", "autoscroll", "listen", "pdf", "ukulele")
    if (
        not raw_title
        or any(b in raw_title.lower() for b in _ui_bad_titles)
        or (len(raw_title) <= 2 and stem_title and raw_title not in stem_title)
    ):
        final_title = stem_title or raw_title or "ScoreForge-辨識結果"
    else:
        final_title = raw_title

    raw_key = str(summary.get("key") or "C").strip()
    if raw_key in ("", "C") and measures:
        # 當 CLI 未能從表頭辨識出 1=X（預設退回 C）時，由小節內辨識出的和弦進行推算實際主調
        all_chords: list[str] = []
        for m_item in measures:
            if m_item.chordText:
                all_chords.extend(t for t in m_item.chordText.split() if t)
        if all_chords:
            _pc = {"C": 0, "D": 2, "E": 4, "F": 5, "G": 7, "A": 9, "B": 11}
            _sharp_names = ["C", "C#", "D", "D#", "E", "F", "F#", "G", "G#", "A", "A#", "B"]
            _flat_names = ["C", "Db", "D", "Eb", "E", "F", "Gb", "G", "Ab", "A", "Bb", "B"]
            _deg_specs = [(0, "M", 3.0), (2, "m", 2.0), (4, "m", 2.0), (5, "M", 2.5), (7, "M", 3.0), (9, "m", 2.5), (11, "dim", 1.5)]
            best_k = raw_key or "C"
            best_sc = -999.0
            for c_pc, c_name in enumerate(_sharp_names):
                sc = 0.0
                for ch_sym in all_chords:
                    base_c = ch_sym.split("/")[0]
                    mm = re.match(r"^([#b]*)([A-G])([#b]*)(.*)$", base_c)
                    if not mm:
                        continue
                    accs = (mm.group(1) or "") + (mm.group(3) or "")
                    suf = mm.group(4) or ""
                    if mm.group(3) and suf.startswith("5"):
                        accs = mm.group(1) or ""
                        suf = mm.group(3) + suf
                    ch_pc = (_pc[mm.group(2)] + accs.count("#") - accs.count("b")) % 12
                    is_dim = ("dim" in suf) or ("m7b5" in suf) or ("m7-5" in suf)
                    is_min = (not is_dim) and suf.startswith("m") and (not suf.startswith("maj"))
                    qual = "dim" if is_dim else ("m" if is_min else "M")
                    matched = False
                    for d_semi, d_qual, d_w in _deg_specs:
                        if (c_pc + d_semi) % 12 == ch_pc and d_qual == qual:
                            sc += d_w
                            matched = True
                            break
                    if not matched:
                        sc -= 1.0
                for edge_idx, edge_ch in enumerate((all_chords[0], all_chords[-1])):
                    base_c = edge_ch.split("/")[0]
                    mm = re.match(r"^([#b]*)([A-G])([#b]*)(.*)$", base_c)
                    if mm:
                        accs = (mm.group(1) or "") + (mm.group(3) or "")
                        suf = mm.group(4) or ""
                        ch_pc = (_pc[mm.group(2)] + accs.count("#") - accs.count("b")) % 12
                        is_min = suf.startswith("m") and (not suf.startswith("maj")) and ("m7b5" not in suf)
                        if ch_pc == c_pc and not is_min:
                            sc += 5.0 if edge_idx == 1 else 4.0
                        elif ch_pc == (c_pc + 9) % 12 and is_min:
                            sc += 2.0
                if sc > best_sc:
                    best_sc = sc
                    best_k = _flat_names[c_pc] if c_pc in (3, 5, 8, 10) else c_name
            raw_key = best_k

    doc = ScoreDocument(
        id=new_id("doc"),
        title=final_title,
        composer=str(summary.get("composer") or ""),
        lyricist=str(summary.get("lyricist") or ""),
        key=raw_key or "C",
        timeSignature=time_sig,
        tempo=tempo,
        engineMode="scoreforge",
        engineNote=(
            f"ScoreForge kit CLI（jpeditor 引擎，離線）｜"
            f"{summary.get('measureCount', len(measures))} 小節｜"
            f"{summary.get('chordCount', 0)} 和弦｜{summary.get('noteCount', 0)} 音符"
        ),
        sourceName=source_name,
        measures=measures,
    )
    return {"document": doc, "warnings": warnings, "sfzJson": sfz_json}
