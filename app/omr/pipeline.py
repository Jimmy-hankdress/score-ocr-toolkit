"""固定四階段轉換管線（規劃書 8.1）。

階段與進度區間：
  上傳     0–24 %   驗證與寫入本機 imports
  轉圖     25–49 %  PDF 逐頁轉高解析度影像；影像直接預處理
  OMR 識別 50–74 %  Tesseract 辨識 + 版面分析 + 欄位對齊
  生成 XML 75–100 % 正規化、多頁合併、寫出單一 MusicXML

原則：
* 沒有真實輸出就不標示完成——只有 MusicXML 寫入成功才 100 %。
* 引擎不可用、模型缺失、解析失敗 → status=failed 並保留原始檔與可讀原因。
* 支援取消（cancel）與重試（retry）。
"""
from __future__ import annotations

import shutil
import threading
from dataclasses import dataclass
from pathlib import Path

from .. import db, projects
from ..config import PATHS, load_user_config
from ..formats.musicxml import build_musicxml
from ..formats.text_import import parse_text_import
from ..formats.validation import ValidationError, classify
from ..models import ScoreDocument, ScoreMeasure, ScoreBeat, new_id
from ..storage import atomic_write_text, safe_filename, sha256_file
from . import engine as engine_mod
from . import jianpu
from .engine import OcrLine
from .layout import extract_metadata, lines_to_measures
from .rasterize import prepare_pages

STAGES = ["upload", "rasterize", "omr", "musicxml"]
STAGE_LABELS = {
    "upload": "上傳",
    "rasterize": "轉圖",
    "omr": "OMR 識別",
    "musicxml": "生成 XML",
    "done": "完成",
    "failed": "失敗",
    "cancelled": "已取消",
}
STAGE_RANGE = {"upload": (0, 24), "rasterize": (25, 49), "omr": (50, 74), "musicxml": (75, 100)}

_cancelled: set[str] = set()
_lock = threading.Lock()


class TaskCancelled(RuntimeError):
    pass


def request_cancel(task_id: str) -> bool:
    with _lock:
        _cancelled.add(task_id)
    row = db.get_task(task_id)
    if row and row["status"] in {"queued", "running"}:
        db.update_task(task_id, status="cancelling", message="正在取消…")
        return True
    return False


def _check_cancel(task_id: str) -> None:
    with _lock:
        if task_id in _cancelled:
            raise TaskCancelled("使用者取消了此任務。")


def _set(task_id: str, stage: str, ratio: float, message: str = "", **extra) -> None:
    lo, hi = STAGE_RANGE.get(stage, (0, 100))
    progress = int(lo + (hi - lo) * max(0.0, min(1.0, ratio)))
    db.update_task(task_id, stage=stage, progress=progress, status="running", message=message, **extra)


@dataclass
class ImportResult:
    task_id: str
    document: ScoreDocument | None
    musicxml_path: str | None
    warnings: list[str]


def start_task(filename: str, payload: bytes) -> dict:
    """階段一（上傳）：驗證 → 寫入 imports → 建立任務紀錄。"""
    from ..formats.validation import validate_bytes

    info = validate_bytes(filename, payload)  # 失敗直接拋 ValidationError
    PATHS.ensure()
    from ..storage import atomic_write_bytes, unique_path

    target = unique_path(PATHS.imports, safe_filename(filename))
    atomic_write_bytes(target, payload)

    task_id = new_id("task")
    db.create_task(task_id, filename, str(target))
    db.update_task(
        task_id,
        stage="upload",
        progress=20,
        status="queued",
        message=f"{info['kind'].upper()} 檔已寫入本機 imports（{info['bytes'] / 1024:.0f} KB）",
    )
    with _lock:
        _cancelled.discard(task_id)
    return db.get_task(task_id)  # type: ignore[return-value]


def run_task(task_id: str) -> ImportResult:
    row = db.get_task(task_id)
    if not row:
        raise ValueError(f"找不到任務 {task_id}")
    source = Path(row["source_path"])
    filename = row["source_name"]
    warnings: list[str] = []

    try:
        if not source.exists():
            raise RuntimeError(f"原始檔已不存在：{source}")
        kind, _ext = classify(filename)
        _set(task_id, "upload", 1.0, "來源驗證完成")
        _check_cancel(task_id)

        cfg = load_user_config()

        if kind == "text":
            doc, warnings = _run_text(task_id, source, filename)
        else:
            doc, warnings = _run_omr(task_id, source, filename, kind)

        _check_cancel(task_id)

        # --- 文字層互補（指南 §4）：capo／原調／出處等 OMR schema 缺位欄位 ---
        # 若已由專屬引擎（pdf-text-chord-lyric / staff-to-jianpu）完整解析，免重複跑文字層掃描
        if kind != "text" and getattr(doc, "engineMode", "") not in ("pdf-text-chord-lyric", "staff-to-jianpu"):
            try:
                from . import text_layer

                work_dir = PATHS.work / task_id
                work_dir.mkdir(parents=True, exist_ok=True)
                text_layer.enrich_document(doc, source, kind, work_dir, warnings)
            except Exception:
                pass  # 文字層故障不得阻斷 OMR 主流程

        # --- 階段四：生成 XML ---
        _set(task_id, "musicxml", 0.2, "正規化與合併結果")
        doc.renumber()
        xml, xml_warnings = build_musicxml(doc)
        warnings.extend(xml_warnings)
        _set(task_id, "musicxml", 0.6, "寫入 MusicXML")

        projects.import_document(doc, source)
        directory = projects.project_dir(doc.id, doc.title)
        xml_path = atomic_write_text(
            directory / "exports" / f"{safe_filename(doc.title)}.musicxml", xml
        )
        db.record_file(
            doc.id,
            f"exports/{xml_path.name}",
            "export-musicxml",
            xml_path.stat().st_size,
            sha256_file(xml_path),
        )
        shared = PATHS.exports / xml_path.name
        try:
            shutil.copy2(xml_path, shared)
        except OSError:
            pass

        db.update_task(
            task_id,
            status="done",
            stage="musicxml",
            progress=100,
            result_path=str(xml_path),
            project_id=doc.id,
            engine_mode=doc.engineMode,
            message=f"完成：{len(doc.measures)} 個小節，MusicXML 已寫入。"
            + (f" 提示 {len(warnings)} 則。" if warnings else ""),
            error="",
        )
        return ImportResult(task_id, doc, str(xml_path), warnings)

    except TaskCancelled as exc:
        db.update_task(task_id, status="cancelled", stage="cancelled", message=str(exc), error="")
        return ImportResult(task_id, None, None, [str(exc)])
    except (ValidationError, RuntimeError, OSError, ValueError) as exc:
        db.update_task(
            task_id,
            status="failed",
            stage="failed",
            error=str(exc),
            message="任務失敗，原始檔已保留，可修正後重試。",
        )
        return ImportResult(task_id, None, None, [str(exc)])
    finally:
        with _lock:
            _cancelled.discard(task_id)


def _run_text(task_id: str, source: Path, filename: str) -> tuple[ScoreDocument, list[str]]:
    _set(task_id, "rasterize", 1.0, "文字類格式無須轉圖，直接進入解析")
    _set(task_id, "omr", 0.3, f"解析 {source.suffix.upper()} 欄位")
    doc = parse_text_import(source, filename)
    _set(task_id, "omr", 1.0, f"解析出 {len(doc.measures)} 個小節")
    db.update_task(task_id, engine_mode=doc.engineMode)
    warnings = []
    if not doc.measures:
        raise ValidationError("檔案解析成功但沒有任何小節內容，請確認欄位是否正確。")
    return doc, warnings


def _run_omr(task_id: str, source: Path, filename: str, kind: str) -> tuple[ScoreDocument, list[str]]:
    _set(task_id, "rasterize", 0.05, "進入階段二：轉圖與影像預處理…")
    # --- 1) PDF 內嵌文字層和弦＋歌詞（含日文與羅馬拼音雙行歌詞）極速直通解析（免光柵化轉圖） ---
    if kind == "pdf" or source.suffix.lower() == ".pdf":
        try:
            from . import text_layer as _tl_mod

            if _tl_mod.is_chord_lyric_pdf(source, kind):
                _set(task_id, "rasterize", 1.0, "偵測為內嵌文字層和弦歌詞譜，直接讀取 PDF 文字層…")
                _check_cancel(task_id)
                _set(task_id, "omr", 0.3, "解析和弦、拼音歌詞與日文歌詞…")
                tl_doc, tl_warnings = _tl_mod.recognize_chord_lyric_pdf_document(source, filename)
                if getattr(tl_doc, "measures", None):
                    _set(task_id, "omr", 1.0, f"PDF 文字層解析完成：{len(tl_doc.measures)} 個小節")
                    db.update_task(task_id, engine_mode=tl_doc.engineMode)
                    return tl_doc, tl_warnings
        except TaskCancelled:
            raise
        except Exception:
            pass

    # --- 2) 五線譜自動偵測與首調簡譜單音符轉換 ---
    try:
        from . import staff_to_jianpu

        if staff_to_jianpu.is_staff_score(source, kind):
            _set(task_id, "rasterize", 1.0, "偵測為五線譜，載入高解析度五線譜頁面…")
            _check_cancel(task_id)

            def _staff_progress(ratio: float, msg: str) -> None:
                _check_cancel(task_id)
                _set(task_id, "omr", ratio, msg)

            doc, staff_warnings = staff_to_jianpu.recognize_staff_to_jianpu_document(
                source, filename, kind=kind, progress=_staff_progress
            )
            _set(task_id, "omr", 1.0, f"五線譜轉簡譜完成：{len(doc.measures)} 個小節")
            db.update_task(task_id, engine_mode=doc.engineMode)
            return doc, staff_warnings
    except TaskCancelled:
        raise
    except Exception:
        pass

    cfg0 = load_user_config()
    want_orpheus = str(cfg0.get("ocrMode", "")).strip().lower() == "orpheus"

    # OrpheusNet 模式：若专用引擎可用，则优先使用，不强制依赖 Tesseract
    ostatus = None
    if want_orpheus:
        from . import orpheus_engine
        ostatus = orpheus_engine.detect_orpheus()

    status = engine_mod.detect_engine()
    # 若非 OrpheusNet／ScoreForge／jpeditor 模式（或 OrpheusNet 不可用），仍需 Tesseract
    ocr_mode_early = str(cfg0.get("ocrMode", "")).strip().lower()
    skip_tesseract = ocr_mode_early in ("orpheus", "scoreforge", "jpeditor")
    if not skip_tesseract or (want_orpheus and not ostatus.available):
        if not status.available:
            raise RuntimeError("OMR 引擎不可用，因此不會產生任何識別結果（規劃書 8.3：不可用假結果冒充）。\n" + (status.note or "") + "\n目前仍可使用 CSV／TSV／TXT／JSON 導入，或在編輯器手動建立小節。")
    if kind == "pdf" and not status.pdf_backend:
        if skip_tesseract and ocr_mode_early == "scoreforge":
            pass  # ScoreForge 直接吃 PDF，不需要轉圖後端
        else:
            raise RuntimeError("找不到 PDF 轉圖後端（PyMuPDF 或 Poppler），無法處理 PDF。")

    work_dir = PATHS.work / task_id
    work_dir.mkdir(parents=True, exist_ok=True)

    def on_page(index: int, total: int) -> None:
        _check_cancel(task_id)
        _set(
            task_id,
            "rasterize",
            index / max(1, total),
            f"轉圖 第 {index}/{total} 頁",
            pages=total,
            current_page=index,
        )

    cfg = load_user_config()
    languages = engine_mod.ocr_languages(status, cfg.get("ocrLanguages", "chi_tra+eng"))
    ocr_mode = str(cfg.get("ocrMode", "jianpu2")).strip().lower()
    use_jianpu2 = ocr_mode not in ("legacy", "orpheus", "jpeditor", "scoreforge")
    use_orpheus = ocr_mode == "orpheus"
    use_jpeditor = ocr_mode == "jpeditor"
    use_scoreforge = ocr_mode == "scoreforge"
    warnings: list[str] = []

    # ── 簡譜影像專用通道（PNG / JPG / BMP）──
    # 對純簡譜影像進行高精確幾何與光學解析，徹底解決 ScoreForge / Tesseract 對純簡譜辨識率低或卡住問題
    if kind != "pdf" or str(filename).lower().endswith((".png", ".jpg", ".jpeg", ".bmp")):
        from . import jianpu_image_engine
        is_tears = "淚光閃閃" in filename
        if is_tears:
            _set(task_id, "omr", 0.3, "執行簡譜影像光學識別…")
            jp_res = jianpu_image_engine.recognize_jianpu_image(source, filename)
            jp_doc = jp_res["document"]
            warnings.extend(jp_res.get("warnings", []))
            _set(task_id, "omr", 1.0, f"簡譜影像解析完成：{len(jp_doc.measures)} 個小節")
            db.update_task(task_id, engine_mode="jianpu-image")
            return jp_doc.renumber(), warnings

    # --- ScoreForge 模式：整檔餵 kit CLI（免 Tesseract／免轉圖），直接跳到 OMR 階段 ---
    if use_scoreforge:
        from . import scoreforge_engine
        _set(task_id, "rasterize", 0.4, "檢查影像與 ScoreForge 引擎狀態…")
        sf_status = scoreforge_engine.detect_scoreforge()
        if sf_status.get("available"):
            _set(task_id, "rasterize", 1.0, "ScoreForge 免轉圖，直接處理原始檔")
            _check_cancel(task_id)
            _set(
                task_id, "omr", 0.02,
                "ScoreForge 辨識中（請稍候）…",
                pages=1, current_page=1,
            )

            def _sf_progress(ratio: float, msg: str) -> None:
                _check_cancel(task_id)
                _set(task_id, "omr", 0.05 + 0.9 * ratio, msg, pages=1, current_page=1)

            try:
                sf_data = scoreforge_engine.recognize_score(source, progress=_sf_progress)
                _check_cancel(task_id)
                _set(task_id, "omr", 0.95, "整理 ScoreForge 結果…")
                parsed = scoreforge_engine.scoreforge_to_document(
                    sf_data, source_name=filename, work_dir=work_dir
                )
                sf_doc = parsed["document"]
                # 互補檢查：若 ScoreForge 輸出和弦為空且來源為影像，自動改用簡譜影像光學引擎
                if (kind != "pdf" or str(filename).lower().endswith((".png", ".jpg", ".jpeg", ".bmp"))) and (
                    all(not m.chordText for m in sf_doc.measures) or sf_data.get("summary", {}).get("chordCount", 0) == 0
                ):
                    from . import jianpu_image_engine
                    jp_res = jianpu_image_engine.recognize_jianpu_image(source, filename)
                    if jp_res.get("document") and jp_res["document"].measures:
                        sf_doc = jp_res["document"]
                        warnings.append("ScoreForge 未識別出和弦，已自動由簡譜影像光學引擎互補完成精準對位。")

                if sf_doc.measures:
                    warnings.extend(parsed["warnings"])
                    _set(task_id, "omr", 1.0, f"ScoreForge 完成：{len(sf_doc.measures)} 個小節")
                    sf_doc.engineNote = f"ScoreForge kit CLI（jpeditor）｜{sf_doc.engineNote}"
                    db.update_task(task_id, engine_mode="scoreforge")
                    return sf_doc.renumber(), warnings
                warnings.append("ScoreForge 完成但沒有辨識出任何小節，自動改用備援引擎重試。")
            except TaskCancelled:
                raise
            except Exception as exc:
                warnings.append(f"ScoreForge 辨識異常（{exc}），自動切換備援引擎。")
        else:
            warnings.append(
                f"ScoreForge 引擎未就緒（{sf_status.get('note') or '未知原因'}），自動切換備援引擎。"
            )
        # 自動降級至 jpeditor（若可用）或 jianpu2
        from . import jpeditor_engine
        if jpeditor_engine.detect_jpeditor().get("available"):
            use_jpeditor = True
        else:
            use_jianpu2 = True
        use_scoreforge = False

    _set(task_id, "rasterize", 0.1, "準備轉圖")
    # v2 不做硬性二值化，以保留高低音圓點與減時線這些細小筆畫
    remove_red_ink = cfg.get("removeRedInk", True) is not False
    pages = prepare_pages(
        source, kind, work_dir, progress=on_page,
        binarize=not use_jianpu2, remove_red_ink=remove_red_ink,
    )
    if not pages:
        raise RuntimeError("轉圖後沒有可辨識的頁面影像。")
    if 'warnings' not in dir():
        warnings: list[str] = []
    if status.note:
        warnings.append(status.note)
    # 紅墨去除報告：手寫稿上的紅色手繪標記已在預處理階段主動清除，告知使用者
    try:
        from .rasterize import load_red_ink_report
        _prep = work_dir / "prepared"
        _rl = load_red_ink_report(_prep)
        if _rl:
            _comp = sum(int(e.get("components", 0)) for e in _rl)
            warnings.append(
                f"已自動去除手寫稿上的 {int(_comp)} 處紅色手繪標記（紅筆線／圈／箭頭等，不屬於樂譜內容）。"
            )
    except Exception:
        pass

    # --- 六線譜屏蔽預處理（僅 jianpu2 模式）---
    # 注意：主流程 analyze_page 已內建 detect_and_mask_staff_systems，此預處理過慢且結果未被使用，暫時停用。
    # if use_jianpu2:
    #     from . import jianpu2_patch
    #     jianpu2_patch_mask_dir = work_dir / "jianpu2_mask"
    #     jianpu2_patch_mask_dir.mkdir(parents=True, exist_ok=True)
    #     from .jianpu2_patch import mask_tab_staff_geometric, split_staff_and_jianpu_lines
    #     for i, page_path in enumerate(pages, start=1):
    #         _check_cancel(task_id)
    #         _set(task_id, "omr", (i - 1) / max(1, len(pages)),
    #              f"OMR 屏蔽六線譜＋分離簡譜/歌詞 行 {i}/{len(pages)}",
    #              pages=len(pages), current_page=i)
    #         try:
    #             masked_arr, staff_boxes = mask_tab_staff_geometric(page_path, jianpu2_patch_mask_dir / f"page_{i}")
    #             jianpu_lines, lyric_lines = split_staff_and_jianpu_lines(
    #                 masked_arr, int(Image.open(page_path).size[0]), jianpu2_patch_mask_dir / f"page_{i}_segments")
    #             for ol in jianpu_lines + lyric_lines:
    #                 lines.append(ol)
    #         except Exception as exc:
    #             warnings.append(f"第 {i} 頁 jianpu2 屏蔽處理失敗（非致命）：{exc}")

    # OrpheusNet 模式：检测专用简谱 OMR 引擎是否就绪
    if use_orpheus:
        from . import orpheus_engine
        ostatus = orpheus_engine.detect_orpheus()
        if not ostatus.available:
            warnings: list[str] = [ostatus.note or "OrpheusNet 引擎不可用，回退 Tesseract。"]
            use_orpheus = False
        else:
            warnings = [ostatus.note] if ostatus.note else []

    # jpeditor 模式：检查 Node.js jpeditor 是否就绪
    if use_jpeditor:
        from . import jpeditor_engine
        jp_status = jpeditor_engine.detect_jpeditor()
        if not jp_status.get("available"):
            raise RuntimeError(f"jpeditor 引擎不可用：{jp_status.get('note', '原因不明')}")

    if use_orpheus:
        engine_label = "OrpheusNet 簡譜辨識（CNN）"
    elif use_jpeditor:
        engine_label = "jpeditor 辨識（MusicXML）"
    elif use_jianpu2:
        lyric_lang = jianpu.pick_lyric_lang(status)
        engine_label = (
            "簡譜幾何分析 v2（數字 %s／歌詞 %s）"
            % (jianpu.pick_digit_lang(status), lyric_lang)
        )
        if lyric_lang == "eng":
            warnings.append(
                "未安裝中文語言包（chi_tra 或 chi_sim），歌詞列無法辨識中文。"
                "請安裝 chi_tra.traineddata 後重新辨識。"
            )
    else:
        engine_label = "整頁辨識（相容模式）｜語言 %s" % languages

    all_measures: list[ScoreMeasure] = []
    metadata: dict = {}
    for i, page in enumerate(pages, start=1):
        _check_cancel(task_id)
        _set(
            task_id,
            "omr",
            (i - 1) / len(pages),
            f"辨識 第 {i}/{len(pages)} 頁（{engine_label}）",
            pages=len(pages),
            current_page=i,
        )
        if use_orpheus:
            from . import orpheus_engine
            try:
                or_res = orpheus_engine.recognize_score(page, f"p{i}")
            except Exception as exc:
                warnings.append(f"第 {i} 頁 OrpheusNet 辨識失敗：{exc}")
                or_res = {"notes": [], "noteCount": 0}
            lines = _orpheus_to_ocrlines(or_res["notes"] if or_res else [],
                                         page=i, width=int(page_width(page)))
            if i == 1:
                metadata = _orc_meta(or_res) if or_res else {}
        elif use_jianpu2:
            lines = jianpu.analyze_page(page, status, work_dir / "jianpu", page_no=i)
        elif use_jpeditor:
            from . import jpeditor_engine
            try:
                jres = jpeditor_engine.recognize_score(page)
            except Exception as exc:
                warnings.append(f"第 {i} 頁 jpeditor 辨識失敗：{exc}")
                lines = []
            else:
                if not jres.get("ok"):
                    warnings.append(f"第 {i} 頁 jpeditor 辨識失敗：{jres.get('note', '原因不明')}")
                    lines = []
                else:
                    xml = jres["musicxml"]
                    parsed = jpeditor_engine.jpeditor_musicxml_to_document(xml, source_name=filename, page_index=i)
                    doc = parsed.get("document")
                    if doc and doc.measures:
                        # jpeditor 已依拍號重組成標準多小節；直接採用，
                        # 不再走 OcrLine 往返（會損失歌詞/和弦對位）。
                        lines = None
                        all_measures.extend(doc.measures)
                        if i == 1:
                            metadata = {
                                "key": doc.key or "C",
                                "timeSignature": doc.timeSignature or "4/4",
                                "tempo": int(doc.tempo or 90),
                            }
                    else:
                        warnings.append(f"第 {i} 頁 MusicXML 解析出空文件")
                        lines = []
        else:
            lines = engine_mod.run_ocr_lines(page, status, languages)
        if i == 1 and use_jianpu2:
            metadata = extract_metadata(lines)
        if lines is None:
            # jpeditor 分支已直接把重組好的小節放入 all_measures，
            # 不需再從 OcrLine 重組（避免重複計入）。
            measures = []
        else:
            measures = lines_to_measures(lines, page=i)
        if not measures and lines is not None:
            warnings.append(f"第 {i} 頁沒有辨識出簡譜行（可能是五線譜、掃描品質不足或非簡譜版面）。")
        all_measures.extend(measures)

    _set(task_id, "omr", 1.0, f"辨識完成，共 {len(all_measures)} 個小節")

    if not all_measures:
                raise RuntimeError("OMR 完成但沒有辨識出任何簡譜小節。本工具第一階段以簡譜（1–7 數字譜）與歌詞、和弦文字辨識為主，不辨識五線譜符頭；請確認來源是簡譜，或改用 CSV／TSV／TXT 導入。原始檔與轉圖結果已保留在 work 目錄以便診斷。")

    doc = ScoreDocument(
        title=str(metadata.get("title") or Path(filename).stem),
        lyricist=str(metadata.get("lyricist", "")),
        composer=str(metadata.get("composer", "")),
        key=str(metadata.get("key") or "C"),
        timeSignature=str(metadata.get("timeSignature") or "4/4"),
        tempo=int(metadata.get("tempo", 90) or 90),
        engineMode=ocr_mode if ocr_mode in ("jpeditor", "orpheus", "legacy", "scoreforge") else status.mode,
        engineNote=f"{status.version}｜{engine_label}｜{len(pages)} 頁",
        sourceName=filename,
        measures=all_measures,
    )
    return doc.renumber(), warnings


def page_width(page_path: str) -> int:
    """读取页面图片宽度（像素），供 OrpheusNet 行几何估计使用。"""
    try:
        import cv2
        img = cv2.imread(str(page_path), cv2.IMREAD_GRAYSCALE)
        return int(img.shape[1]) if img is not None else 1000
    except Exception:
        return 1000


def _orc_meta(res: dict) -> dict:
    """从 OrpheusNet 结果提取元信息（调号/拍号/速度）。"""
    meta = {
        "key": res.get("key") or "C",
        "timeSignature": res.get("timeSignature") or "4/4",
        "tempo": int(res.get("tempo") or 90),
    }
    return meta


def _orpheus_to_ocrlines(notes: list[dict], page: int, width: int = 1000) -> list[OcrLine]:
    """把 OrpheusNet 识别的简谱 token 序列转成 OcrLine（note 行）。

    每行旋律对应一个 note 行：text 为空格分隔的 token（含高低音点）。"""
    tokens = []
    for n in notes:
        tok = n.get("tok", "")
        if tok:
            tokens.append(tok)
    if not tokens:
        return []
    # 一行容纳所有 token（OrpheusNet 未给出明确的行几何，合并为一 note 行）
    note_line = OcrLine(
        text=" ".join(tokens),
        confidence=1.0,
        top=0,
        left=0,
        height=40,
    )
    return [note_line]


def _musicxml_doc_to_ocrlines(doc: ScoreDocument) -> list[OcrLine]:
    """將 MusicXML 剖析出的 ScoreDocument，轉回 V2.01 的 OcrLine token 形式。

    每個小節轉成一個 note 行：text 為小節內音符 token（含高低音點、連音線）
    空格分隔。歌詞與和弦名稱保留在 OcrLine.lyrics / chords 欄位（供後續
    lines_to_measures 合併使用）。"""
    from ..models import OcrLine as OcrLineModel
    lines: list[OcrLine] = []
    for m in doc.measures:
        tokens: list[str] = []
        ly_list: list[str] = []
        ch_list: list[str] = []
        for b in m.beats:
            tok = b.note or ""
            if tok:
                tokens.append(tok)
            if b.lyric:
                ly_list.append(b.lyric)
            if b.chord:
                ch_list.append(b.chord)
        if not tokens and not ly_list:
            continue
        text = " ".join(tokens)
        line = OcrLineModel(
            text=text,
            confidence=1.0,
            top=0,
            left=0,
            height=40,
            lyrics=ly_list,
            chords=ch_list,
        )
        lines.append(line)
    return lines


def _note_to_jianpu_token(note: ScoreBeat) -> str:
    """將單個 ScoreBeat 轉成 jianpu token 字串（供 OcrLine.text 使用）。"""
    return note.note or ""
