"""ScoreStudio API（規格 §5.2）。掛到既有 FastAPI app，不改既有路由。"""
from __future__ import annotations

import json
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from typing import Optional

from . import ScoreDocument
from . import score_document_service as svc
from . import omr_adapter
from .score_validator import validate
from .formats_export import export_musicxml, export_json, export_tsv, export_txt

router = APIRouter(prefix="/api/projects/{doc_id}", tags=["scorestudio"])


class ScoreBody(BaseModel):
    expectedRevision: Optional[int] = None
    document: dict


@router.get("/score")
def get_score(doc_id: str):
    try:
        doc = svc.load_score(doc_id)
    except FileNotFoundError:
        raise HTTPException(404, "找不到專案")
    return doc.save_dict()


@router.put("/score")
def put_score(doc_id: str, body: ScoreBody):
    try:
        doc = ScoreDocument.from_dict(body.document)
    except Exception as exc:
        raise HTTPException(400, f"schema 驗證失敗：{exc}")
    try:
        rev = svc.save_score(doc_id, doc, body.expectedRevision)
    except svc.RevisionConflict as exc:
        raise HTTPException(409, {"expectedRevision": exc.expected, "actualRevision": exc.actual})
    except FileNotFoundError:
        raise HTTPException(404, "找不到專案")
    report = validate(doc)
    return {"ok": True, "revision": rev, "validation": report.summary()}


@router.post("/score/validate")
def post_validate(doc_id: str):
    doc = svc.load_score(doc_id)
    rep = validate(doc)
    return {
        "ok": rep.ok,
        "summary": rep.summary(),
        "checks": [{"measure": c.measure, "measureId": c.measureId, "status": c.status,
                    "expectedTicks": c.expectedTicks, "usedTicks": c.usedTicks,
                    "issues": c.issues} for c in rep.checks],
        "exportWarnings": rep.exportWarnings,
    }


@router.post("/score/snapshot")
def post_snapshot(doc_id: str, note: str = ""):
    try:
        name = svc._snapshot(doc_id, note or "手動快照")
        return {"ok": True, "snapshot": name.split("/")[-1]}
    except FileNotFoundError:
        raise HTTPException(404, "找不到專案")


@router.get("/score/history")
def get_history(doc_id: str):
    return {"snapshots": svc.list_snapshots(doc_id)}


@router.post("/score/restore/{name}")
def post_restore(doc_id: str, name: str):
    try:
        rev = svc.restore_snapshot(doc_id, name)
        return {"ok": True, "revision": rev}
    except FileNotFoundError:
        raise HTTPException(404, "找不到快照")


@router.post("/score/import-omr")
def post_import_omr(doc_id: str, omr_payload: dict):
    try:
        rev = svc.import_omr(doc_id, omr_payload)
        return {"ok": True, "revision": rev}
    except FileNotFoundError:
        raise HTTPException(404, "找不到專案")


@router.post("/score/import-musicxml")
def post_import_musicxml(doc_id: str, xml_text: str = ""):
    """MVP：保留端點；完整 MusicXML 匯入解析歸 M5/之後（誠實標記）。"""
    return {"ok": False, "note": "MusicXML 匯入未實作（M5 之後）；目前僅匯出。"}


@router.get("/source-pages")
def get_source_pages(doc_id: str):
    try:
        return {"pages": svc.source_page_files(doc_id)}
    except FileNotFoundError:
        raise HTTPException(404, "找不到專案")


@router.get("/source-map/{event_id}")
def get_source_map(doc_id: str, event_id: str):
    try:
        return svc.source_map(event_id, doc_id)
    except FileNotFoundError:
        raise HTTPException(404, "找不到專案")


# ---- 匯出（§15：由 ScoreDocument 優先轉換，保留既有格式）----
@router.get("/export/musicxml")
def get_export_musicxml(doc_id: str):
    doc = svc.load_score(doc_id)
    return {"format": "musicxml", "content": export_musicxml(doc)}


@router.get("/export/json")
def get_export_json(doc_id: str):
    doc = svc.load_score(doc_id)
    return {"format": "json", "content": json.dumps(doc.save_dict(), ensure_ascii=False)}


@router.get("/export/tsv")
def get_export_tsv(doc_id: str):
    doc = svc.load_score(doc_id)
    return {"format": "tsv", "content": export_tsv(doc)}


@router.get("/export/txt")
def get_export_txt(doc_id: str):
    doc = svc.load_score(doc_id)
    return {"format": "txt", "content": export_txt(doc)}
