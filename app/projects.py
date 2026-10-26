"""專案服務：每首歌一個目錄，內含 project.json、原始檔、輸出與版本備份。"""
from __future__ import annotations

import json
import shutil
from pathlib import Path

from . import db
from .config import PATHS, load_user_config
from .formats.musicxml import document_to_musicxml
from .formats.text_export import document_to_json, document_to_tsv, document_to_plain_text
from .formats.sola321 import export_score_to_sola321
from .formats.midi import export_score_to_midi
from .models import ScoreDocument, blank_document, now_iso
from .storage import (
    atomic_write_bytes,
    atomic_write_text,
    disk_free_bytes,
    make_backup_zip,
    safe_filename,
    sha256_file,
    snapshot_version,
    unique_path,
)


class ProjectError(RuntimeError):
    pass


def _get_learn_store():
    """取得跨程序共用的 ScoreForge 自我學習曲線記憶庫（LearnStore）。"""
    import sys
    sf_engine_dir = r"D:\Harness\ScoreForge\engine"
    if sf_engine_dir not in sys.path and Path(sf_engine_dir).exists():
        sys.path.insert(0, sf_engine_dir)
    try:
        from scoreforge_engine.learn import shared_learn_store
        return shared_learn_store()
    except Exception:
        return None


def project_dir(doc_id: str, title: str = "") -> Path:
    row = db.get_project(doc_id)
    if row and row.get("directory"):
        return Path(row["directory"])
    name = f"{safe_filename(title or '未命名樂譜')}-{doc_id.split('_')[-1]}"
    return PATHS.projects / name


_last_snapshot_ts: dict[str, float] = {}


def _async_post_save(
    doc_id: str,
    directory: Path,
    target: Path,
    song_name: str,
    payload: str,
    do_snapshot: bool,
    before_dict: dict | None,
    after_dict: dict,
) -> None:
    """背景執行次要鏡像寫入、檔案雜湊紀錄與自我學習曲線差集分析，避免阻塞前端編輯儲存回應。"""
    try:
        atomic_write_text(directory / f"{song_name}.json", payload)
    except Exception:
        pass
    try:
        PATHS.exports.mkdir(parents=True, exist_ok=True)
        atomic_write_text(PATHS.exports / f"{song_name}.json", payload)
    except Exception:
        pass
    try:
        ws_drafts = Path(r"D:\樂譜自動生成系統\暫存樂譜")
        if ws_drafts.parent.exists():
            ws_drafts.mkdir(parents=True, exist_ok=True)
            atomic_write_text(ws_drafts / f"{song_name}.json", payload)
    except Exception:
        pass
    try:
        if target.exists():
            db.record_file(doc_id, "project.json", "project", target.stat().st_size, sha256_file(target))
    except Exception:
        pass
    try:
        store = _get_learn_store()
        if store is not None:
            if do_snapshot and before_dict is not None:
                store.learn_from_sheetmusic_doc_diff(before_dict, after_dict)
            elif not do_snapshot and len(after_dict.get("measures") or []) >= 4:
                has_notes = any(_measure_has_content(m) for m in (after_dict.get("measures") or []))
                if has_notes:
                    store.ingest_sheetmusic_doc_positives(after_dict)
    except Exception:
        pass


def save_document(doc: ScoreDocument, *, snapshot: bool = True, force_snapshot: bool = False) -> dict:
    """原子保存：節流建立版本備份 → 寫入主檔與暫存檔 → 背景同步次要鏡像與自我學習曲線。"""
    import threading
    import time

    cfg = load_user_config()
    doc.renumber()
    doc.updatedAt = now_iso()
    directory = project_dir(doc.id, doc.title)
    directory.mkdir(parents=True, exist_ok=True)

    free = disk_free_bytes(directory)
    if 0 <= free < 5 * 1024 * 1024:
        raise ProjectError("磁碟可用空間不足 5 MB，為避免覆蓋既有版本已中止保存。")

    now_sec = time.monotonic()
    last_snap = _last_snapshot_ts.get(doc.id, 0.0)
    should_snapshot = snapshot and (force_snapshot or (now_sec - last_snap >= 60.0))

    # 在覆寫前讀取舊版 project.json，供自我學習曲線比較人工修正差集
    before_dict: dict | None = None
    proj_file = directory / "project.json"
    if should_snapshot and proj_file.exists():
        try:
            before_dict = json.loads(proj_file.read_text(encoding="utf-8"))
        except Exception:
            before_dict = None

    version = None
    if should_snapshot:
        version = snapshot_version(directory, keep=int(cfg.get("keepVersions", 20)))
        _last_snapshot_ts[doc.id] = now_sec

    after_dict = doc.to_dict()
    payload = json.dumps(after_dict, ensure_ascii=False, indent=2)
    try:
        target = atomic_write_text(proj_file, payload)
    except OSError as exc:
        raise ProjectError(f"保存失敗（{exc.strerror or exc}）；既有版本未被覆蓋。") from exc

    # 同步寫入固定暫存資料夾 D:\SheetMusicOMR_v3.00\暫存樂譜\<歌名>.json，方便下次直接開啟繼續編輯
    draft_file: Path | None = None
    song_name = safe_filename(doc.title or "未命名樂譜")
    try:
        PATHS.drafts.mkdir(parents=True, exist_ok=True)
        draft_file = PATHS.drafts / f"{song_name}.json"
        atomic_write_text(draft_file, payload)
    except Exception:
        draft_file = None

    db.upsert_project(doc, directory)

    threading.Thread(
        target=_async_post_save,
        args=(doc.id, directory, target, song_name, payload, should_snapshot, before_dict, after_dict),
        daemon=True,
    ).start()

    return {
        "id": doc.id,
        "directory": str(directory),
        "draftFile": str(draft_file) if draft_file else None,
        "savedAt": doc.updatedAt,
        "versionBackup": str(version) if version else None,
        "stats": doc.stats(),
        "learned": None,
    }


def _measure_has_content(m: dict) -> bool:
    return bool(
        str(m.get("noteText") or "").strip()
        or str(m.get("lyricText") or "").strip()
        or str(m.get("lyricText2") or "").strip()
        or str(m.get("chordText") or "").strip()
        or m.get("notes")
        or m.get("lyrics")
        or m.get("chords")
    )


def bootstrap_learning_from_all_projects() -> dict:
    """掃描現有專案與歷史版本，為自我學習曲線建立初始跨曲目先驗記憶。"""
    store = _get_learn_store()
    if store is None:
        return {"ok": False, "error": "LearnStore unavailable"}
    projects_scanned = 0
    version_diffs = 0
    seen_signatures: set[str] = set()
    if PATHS.projects.exists():
        for pdir in sorted(PATHS.projects.iterdir()):
            if not pdir.is_dir():
                continue
            if any(pdir.name.startswith(pfx) for pfx in ("hermes-verify-", "debug-", "Phase0-", "P0-1", "x-mv3")):
                continue
            pfile = pdir / "project.json"
            if not pfile.exists():
                continue
            try:
                cur_doc = json.loads(pfile.read_text(encoding="utf-8"))
            except Exception:
                continue
            title = str(cur_doc.get("title") or "").strip()
            if title in {"未命名樂譜", "測試專案", "測試匯出曲"}:
                continue
            ms = cur_doc.get("measures") or []
            if len(ms) < 4 or not any(_measure_has_content(m) for m in ms):
                continue
            # 避免同一首重複測試匯入的曲目無限累加正樣本，對相同曲目內容去重
            sig_head = "|".join(
                f"{m.get('chordText','')}:{m.get('noteText','')}:{m.get('lyricText','')}"
                for m in ms[:8]
            )
            content_sig = f"{title}::{len(ms)}::{sig_head}"
            is_duplicate_import = content_sig in seen_signatures
            seen_signatures.add(content_sig)

            # 若有歷史版本 versions/*.json，依時間序比較相鄰版本差集
            vdir = pdir / "versions"
            if vdir.exists():
                vfiles = sorted(vdir.glob("*.json"))
                prev_v = None
                for vf in vfiles:
                    try:
                        vdoc = json.loads(vf.read_text(encoding="utf-8"))
                        if prev_v is not None:
                            store.learn_from_sheetmusic_doc_diff(prev_v, vdoc)
                            version_diffs += 1
                        prev_v = vdoc
                    except Exception:
                        continue
                if prev_v is not None:
                    store.learn_from_sheetmusic_doc_diff(prev_v, cur_doc)
                    version_diffs += 1
                elif not is_duplicate_import:
                    store.ingest_sheetmusic_doc_positives(cur_doc)
            elif not is_duplicate_import:
                store.ingest_sheetmusic_doc_positives(cur_doc)
            projects_scanned += 1

    # 同步掃描 ScoreForge 既有真實樣本的 .jpjson 座標，抽取真實曲調水平間距原型
    try:
        from scoreforge_engine.recognize.jpjson_import import jpjson_to_doc
        sf_samples = Path(r"D:\Harness\ScoreForge\samples")
        if sf_samples.exists():
            for jp in sorted(sf_samples.glob("*.jpjson")):
                try:
                    jpjson_to_doc(jp)
                except Exception:
                    continue
    except Exception:
        pass

    return {
        "ok": True,
        "projectsScanned": projects_scanned,
        "uniqueSongsLearned": len(seen_signatures),
        "versionDiffsLearned": version_diffs,
        "stats": store.stats(),
    }


def load_document(doc_id: str) -> ScoreDocument:
    row = db.get_project(doc_id)
    if not row:
        raise ProjectError(f"找不到專案：{doc_id}")
    f = Path(row["directory"]) / "project.json"
    if not f.exists():
        raise ProjectError(f"專案檔遺失：{f}")
    return ScoreDocument.from_dict(json.loads(f.read_text(encoding="utf-8")))


def create_project(title: str = "未命名樂譜", measures: int = 6) -> ScoreDocument:
    doc = blank_document(title, measures)
    save_document(doc, snapshot=False)
    return doc


def import_document(doc: ScoreDocument, source_file: Path | None = None) -> ScoreDocument:
    """把識別／解析結果建成專案，並把原始檔複製進專案目錄保留。"""
    save_document(doc, snapshot=False)
    if source_file and source_file.exists():
        directory = project_dir(doc.id, doc.title)
        src_dir = directory / "source"
        src_dir.mkdir(parents=True, exist_ok=True)
        dest = unique_path(src_dir, safe_filename(source_file.name))
        shutil.copy2(source_file, dest)
        db.record_file(
            doc.id,
            f"source/{dest.name}",
            "source",
            dest.stat().st_size,
            sha256_file(dest),
        )
    return doc


def duplicate_project(doc_id: str, new_title: str | None = None) -> ScoreDocument:
    doc = load_document(doc_id)
    data = doc.to_dict()
    data["id"] = None
    clone = ScoreDocument.from_dict({**data, "id": None})
    clone.title = new_title or f"{doc.title} 副本"
    clone.createdAt = now_iso()
    save_document(clone, snapshot=False)
    return clone


def delete_project(doc_id: str, remove_files: bool = False) -> None:
    row = db.get_project(doc_id)
    db.delete_project(doc_id)
    if remove_files and row and row.get("directory"):
        shutil.rmtree(Path(row["directory"]), ignore_errors=True)


from .formats.midi import export_score_to_midi
from .formats.word import export_score_to_word
from .formats.pdf import export_score_to_pdf

EXPORTERS = {
    "musicxml": ("musicxml", "application/vnd.recordare.musicxml+xml", document_to_musicxml),
    "json": ("json", "application/json", document_to_json),
    "tsv": ("tsv", "text/tab-separated-values", document_to_tsv),
    "txt": ("txt", "text/plain", document_to_plain_text),
    "sola321": ("sola321", "application/json", export_score_to_sola321),
    "midi": ("midi", "audio/midi", export_score_to_midi),
    "word": ("docx", "application/vnd.openxmlformats-officedocument.wordprocessingml.document", export_score_to_word),
    "pdf": ("pdf", "application/pdf", export_score_to_pdf),
}


def export_document(doc_id: str, fmt: str) -> dict:
    fmt = (fmt or "musicxml").lower()
    if fmt not in EXPORTERS:
        raise ProjectError(f"不支援的匯出格式：{fmt}")
    doc = load_document(doc_id)
    ext, mime, renderer = EXPORTERS[fmt]
    content = renderer(doc)

    directory = project_dir(doc.id, doc.title)
    out_dir = directory / "exports"
    filename = f"{safe_filename(doc.title)}.{ext}"
    out_path = out_dir / filename
    out_dir.mkdir(parents=True, exist_ok=True)

    if isinstance(content, bytes):
        target = atomic_write_bytes(out_path, content)
    else:
        target = atomic_write_text(out_path, content)
        content = content.encode("utf-8")

    # 同步一份到共用 exports 目錄，方便直接取用
    shared = unique_path(PATHS.exports, filename)
    atomic_write_bytes(shared, content)

    db.record_file(doc.id, f"exports/{filename}", f"export-{fmt}", target.stat().st_size, sha256_file(target))
    return {
        "format": fmt,
        "mime": mime,
        "path": str(target),
        "sharedPath": str(shared),
        "bytes": target.stat().st_size,
        "filename": filename,
    }


def backup_project(doc_id: str) -> dict:
    doc = load_document(doc_id)
    directory = project_dir(doc.id, doc.title)
    zip_path = make_backup_zip(directory, doc.title)
    db.record_file(doc.id, f"../../backups/{zip_path.name}", "backup", zip_path.stat().st_size, sha256_file(zip_path))
    return {"path": str(zip_path), "bytes": zip_path.stat().st_size, "filename": zip_path.name}


def list_versions(doc_id: str) -> list[dict]:
    directory = project_dir(doc_id)
    versions = directory / "versions"
    if not versions.exists():
        return []
    return [
        {"name": p.name, "bytes": p.stat().st_size, "modifiedAt": now_iso_from(p)}
        for p in sorted(versions.glob("project-*.json"), reverse=True)
    ]


def now_iso_from(path: Path) -> str:
    from datetime import datetime

    return datetime.fromtimestamp(path.stat().st_mtime).isoformat(timespec="seconds")


def restore_version(doc_id: str, version_name: str) -> ScoreDocument:
    directory = project_dir(doc_id)
    src = (directory / "versions" / version_name).resolve()
    if not src.exists() or (directory / "versions").resolve() not in src.parents:
        raise ProjectError(f"找不到版本檔：{version_name}")
    doc = ScoreDocument.from_dict(json.loads(src.read_text(encoding="utf-8")))
    doc.id = doc_id
    save_document(doc)
    return doc


def list_drafts() -> dict:
    """列出固定暫存資料夾 (D:\\SheetMusicOMR_v3.00\\暫存樂譜) 內的所有 .json 暫存檔。"""
    PATHS.drafts.mkdir(parents=True, exist_ok=True)
    items: list[dict] = []
    for p in sorted(PATHS.drafts.glob("*.json"), key=lambda x: x.stat().st_mtime, reverse=True):
        try:
            raw = json.loads(p.read_text(encoding="utf-8"))
            title = raw.get("title") or p.stem
            doc_id = raw.get("id") or ""
            measures_count = len(raw.get("measures") or [])
        except Exception:
            title = p.stem
            doc_id = ""
            measures_count = 0
        items.append(
            {
                "filename": p.name,
                "title": title,
                "id": doc_id,
                "measures": measures_count,
                "bytes": p.stat().st_size,
                "modifiedAt": now_iso_from(p),
                "path": str(p),
            }
        )
    return {
        "folder": str(PATHS.drafts),
        "items": items,
    }


def load_draft_file(filename: str) -> ScoreDocument:
    """從固定暫存資料夾讀取指定的 .json 暫存檔並同步回專案資料庫。"""
    PATHS.drafts.mkdir(parents=True, exist_ok=True)
    safe_name = Path(filename).name
    src = (PATHS.drafts / safe_name).resolve()
    if not src.exists() or PATHS.drafts.resolve() not in src.parents:
        raise ProjectError(f"找不到暫存檔：{safe_name}")
    data = json.loads(src.read_text(encoding="utf-8"))
    if isinstance(data.get("document"), dict):
        data = data["document"]
    doc = ScoreDocument.from_dict(data)
    save_document(doc, snapshot=False)
    return doc
