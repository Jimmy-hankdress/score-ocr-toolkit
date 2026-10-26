"""ScoreDocument 檔案服務（規格 §14）：讀寫 score.json、revision 衝突、快照、原圖定位。"""
from __future__ import annotations

import json
import re
import shutil
import time
import uuid
from pathlib import Path

from ..config import PATHS
from . import ScoreDocument, now_iso
from .omr_adapter import convert as omr_convert
from .legacy_adapter import v1_to_legacy

SCORR_DIR = "data/projects"


def _proj_dir(doc_id: str) -> Path:
    """doc_id = doc_XXXXXXXXXX → 目錄 `*-{後10hex}`。"""
    base = PATHS.projects
    tail = doc_id.split("_")[-1][:10] if doc_id.startswith("doc_") else doc_id[-10:]
    for p in base.iterdir():
        if p.is_dir() and p.name.endswith(f"-{tail}"):
            return p
    # fallback：全掃（目錄尾碼對不上時）
    if base.exists():
        for p in base.iterdir():
            if (p / "project.json").exists():
                try:
                    if json.loads((p / "project.json").read_text("utf-8")).get("id") == doc_id:
                        return p
                except Exception:
                    continue
    raise FileNotFoundError(f"找不到專案 {doc_id}")


def legacy_meta(doc_id: str) -> dict:
    d = _proj_dir(doc_id)
    return json.loads((d / "project.json").read_text("utf-8"))


def legacy_meta_raw(doc_id: str) -> dict:
    d = _proj_dir(doc_id)
    return json.loads((d / "project.json").read_text("utf-8"))


def load_score(doc_id: str) -> ScoreDocument:
    """讀 score.json；不存在則由 project.json 經 OMR Adapter 轉換（並落盤，快照一次）。"""
    d = _proj_dir(doc_id)
    p = d / "score.json"
    if p.exists():
        return ScoreDocument.from_dict(json.loads(p.read_text("utf-8")))
    legacy = legacy_meta_raw(doc_id)
    doc = omr_convert(legacy)
    p.write_text(json.dumps(doc.save_dict(), ensure_ascii=False, indent=1), "utf-8")
    _snapshot(doc_id, "legacy->scorestudio 轉換")
    return doc


def save_score(doc_id: str, doc: ScoreDocument, expected_revision: int | None = None) -> int:
    """寫 score.json；revision 不符 → raise RevisionConflict。同時鏡像 legacy（舊編輯器不壞）。"""
    d = _proj_dir(doc_id)
    cur = load_score(doc_id) if (d / "score.json").exists() else None
    if expected_revision is not None:
        if cur is None or cur.audit.revision != expected_revision:
            raise RevisionConflict(expected_revision, cur.audit.revision if cur else 0)
    doc.audit.revision = (cur.audit.revision + 1) if cur else 1
    doc.audit.updatedAt = now_iso()
    (d / "score.json").write_text(json.dumps(doc.save_dict(), ensure_ascii=False, indent=1), "utf-8")
    # 鏡像 legacy project.json（T13：未知欄位保留於 extensions）
    meta = legacy_meta_raw(doc_id)
    legacy = v1_to_legacy(doc, meta)
    legacy["id"] = doc.projectId or doc_id
    (d / "project.json").write_text(json.dumps(legacy, ensure_ascii=False, indent=1), "utf-8")
    return doc.audit.revision


class RevisionConflict(Exception):
    def __init__(self, expected: int, actual: int):
        self.expected, self.actual = expected, actual
        super().__init__(f"revision 衝突：預期 {expected}、實際 {actual}")


def _snapshot(doc_id: str, note: str) -> str:
    d = _proj_dir(doc_id)
    snaps = d / "snapshots"
    snaps.mkdir(exist_ok=True)
    ts = time.strftime("%Y%m%d_%H%M%S")
    # Windows 非法檔名字元（<>:"/\|?*）一律換成 _；註解含「->」（如
    # "legacy->scorestudio"）或使用者手動快照名都可能帶到這些字元，否則
    # copy2 會 WinError 123 讓首次 GET /score 回 500、前端只剩標題。
    label = re.sub(r'[<>:"/\\|?*]', '_', note[:20].replace(' ', '_') or 'auto')
    name = f"snap_{ts}_{label}.json"
    p = snaps / name
    if (d / "score.json").exists():
        shutil.copy2(d / "score.json", p)
    else:
        shutil.copy2(d / "project.json", p.with_suffix(".legacy.json"))
    return str(p)


def list_snapshots(doc_id: str) -> list[dict]:
    d = _proj_dir(doc_id)
    snaps = d / "snapshots"
    if not snaps.exists():
        return []
    return sorted([{"name": p.name, "ts": p.stat().st_mtime} for p in snaps.iterdir() if p.is_file()],
                  key=lambda x: x["ts"])


def restore_snapshot(doc_id: str, name: str) -> int:
    d = _proj_dir(doc_id)
    p = d / "snapshots" / name
    if not p.exists():
        raise FileNotFoundError(name)
    _snapshot(doc_id, "還原前")  # 還原前再快照（§14.3）
    if p.suffix == ".json" and not p.name.endswith(".legacy.json"):
        data = json.loads(p.read_text("utf-8"))
        doc = ScoreDocument.from_dict(data)
        return save_score(doc_id, doc)
    # legacy 快照 → 重新經 adapter 轉 v1
    legacy = json.loads(p.read_text("utf-8"))
    doc = omr_convert(legacy)
    doc.projectId = doc_id
    return save_score(doc_id, doc)


def import_omr(doc_id: str, omr_payload: dict) -> int:
    """§14.3：匯入 OMR 前快照，再轉 v1 存檔。"""
    _snapshot(doc_id, "匯入 OMR 前")
    doc = omr_convert(omr_payload)
    doc.projectId = doc_id
    return save_score(doc_id, doc)


def source_page_files(doc_id: str) -> list[dict]:
    """§5.2 GET /source-pages：原圖清單（source 目錄）。"""
    d = _proj_dir(doc_id)
    src = d / "source"
    if not src.exists():
        return []
    return [{"name": p.name, "path": str(p.relative_to(PATHS.projects)), "size": p.stat().st_size}
            for p in src.iterdir() if p.is_file()]


def source_map(event_id: str, doc_id: str) -> dict:
    """§5.2 /source-map/{event_id}：事件 → 原圖定位（bbox 缺失時誠實標 unresolved）。"""
    doc = load_score(doc_id)
    for part in doc.parts:
        for m in part.measures:
            for e in m.events:
                if e.id == event_id:
                    pr = e.provenance
                    return {
                        "eventId": event_id,
                        "measure": m.number,
                        "page": pr.page,
                        "bbox": pr.bbox,
                        "hasBbox": bool(pr.bbox),
                        "rawToken": pr.rawToken,
                        "confidence": pr.confidence,
                        "reviewStatus": pr.reviewStatus,
                        "note": "無 bbox（既有 OMR 暫存已清，依規格不補造）" if not pr.bbox else "",
                    }
    return {"eventId": event_id, "hasBbox": False, "note": "找不到事件"}
