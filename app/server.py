"""本地 API 層：FastAPI，只監聽 127.0.0.1（規劃書 3. 安全性、4.1 架構）。

安全約束：
* 不綁 0.0.0.0；middleware 再次檢查 Host 只允許 localhost。
* 無 OAuth、無外部服務、無 CDN；靜態資源全部來自安裝目錄 web/。
* 檔案存取一律經 storage.resolve_inside() 驗證，禁止路徑穿越。
"""
from __future__ import annotations

import logging
import os
import re
import sys
import threading
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

if __name__ == "__main__" and not __package__:
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
    __package__ = "app"

from fastapi import FastAPI, HTTPException, Request, UploadFile, File, Body
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse, PlainTextResponse
from fastapi.staticfiles import StaticFiles

from . import db, projects
from .config import APP_NAME, APP_VERSION, PATHS, load_user_config, save_user_config
from .formats.validation import ValidationError
from .models import ScoreDocument
from .omr import engine as engine_mod
from .omr import pipeline
from .storage import resolve_inside

# ---- ScoreStudio（並存新編輯器；Feature Flag 預設關閉，不影響舊路徑）----
from .scorestudio import score_studio_routes as ss_routes


def _score_studio_flags() -> dict:
    """§5.1：SCORE_STUDIO_ENABLED / SCORE_STUDIO_DEFAULT（user-config，預設 false）。"""
    cfg = load_user_config()
    enabled = bool(cfg.get("scoreStudioEnabled", False))
    default = bool(cfg.get("scoreStudioDefault", False))
    # 環境變數可覆寫（離線、無雲端設定服務）
    import os
    if os.environ.get("SCORE_STUDIO_ENABLED") in {"1", "true", "yes"}:
        enabled = True
    if os.environ.get("SCORE_STUDIO_DEFAULT") in {"1", "true", "yes"}:
        default = True
    return {"enabled": enabled, "default": default}

ALLOWED_HOSTS = {"127.0.0.1", "localhost", "[::1]", "::1", "testserver"}

log = logging.getLogger("sheetmusic.server")
_executor = ThreadPoolExecutor(max_workers=2, thread_name_prefix="omr")
_engine_cache: dict = {}
_engine_lock = threading.Lock()


def engine_status(refresh: bool = False) -> dict:
    from .omr import scoreforge_engine

    with _engine_lock:
        if refresh or "status" not in _engine_cache:
            _engine_cache["status"] = engine_mod.detect_engine().to_dict()
            _engine_cache["status"]["scoreforge"] = scoreforge_engine.detect_scoreforge()
        return _engine_cache["status"]


def create_app() -> FastAPI:
    PATHS.ensure()
    db.init_db()
    orphans = db.reset_orphan_tasks()
    if orphans:
        log.info("已把 %d 個中斷的任務標記為可重試", orphans)

    app = FastAPI(title=f"{APP_NAME} / ScoreOCR Toolkit 本地服務", version=APP_VERSION, docs_url="/docs", redoc_url="/redoc")

    @app.middleware("http")
    async def local_only(request: Request, call_next):
        host = (request.headers.get("host") or "").split(":")[0].strip("[]")
        if host and host not in {h.strip("[]") for h in ALLOWED_HOSTS}:
            return JSONResponse(
                {"error": f"僅允許本機存取（收到 Host: {host}）"}, status_code=403
            )
        origin = request.headers.get("origin")
        if origin and not any(origin.startswith(f"http://{h}") for h in ("127.0.0.1", "localhost")):
            return JSONResponse({"error": "拒絕外部來源的跨域請求"}, status_code=403)
        response = await call_next(request)
        response.headers["Cache-Control"] = "no-store"
        response.headers["X-Content-Type-Options"] = "nosniff"
        return response

    @app.exception_handler(ValidationError)
    async def _validation_handler(_request: Request, exc: ValidationError):
        return JSONResponse({"error": str(exc)}, status_code=400)

    # ---------------- 系統 ----------------

    @app.get("/api/health")
    def health():
        return {
            "status": "ok",
            "app": APP_NAME,
            "version": APP_VERSION,
            "offline": True,
            "paths": PATHS.describe(),
            "engine": engine_status(),
            "config": load_user_config(),
        }

    @app.post("/api/engine/refresh")
    def refresh_engine():
        return engine_status(refresh=True)

    @app.get("/api/config")
    def get_config():
        return load_user_config()

    @app.post("/api/config")
    def set_config(payload: dict = Body(default={})):
        return save_user_config(payload)

    # ---------------- 自我學習曲線記憶庫 ----------------

    @app.get("/api/learn/stats")
    def get_learn_stats():
        store = projects._get_learn_store()
        if store is None:
            return {"total": 0, "learningCurve": {"maturityScore": 0.0, "stage": "unavailable"}}
        return store.stats()

    @app.post("/api/learn/correction")
    def post_learn_correction(payload: dict = Body(default={})):
        store = projects._get_learn_store()
        if store is None:
            raise HTTPException(503, "自我學習記憶庫尚未就緒")
        return store.record(dict(payload or {}))

    @app.post("/api/learn/bootstrap")
    def post_learn_bootstrap():
        return projects.bootstrap_learning_from_all_projects()

    # ---------------- 任務 ----------------

    @app.post("/api/tasks")
    async def create_task(file: UploadFile = File(...)):
        payload = await file.read()
        try:
            task = pipeline.start_task(file.filename or "unnamed", payload)
        except ValidationError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        _executor.submit(pipeline.run_task, task["id"])
        return _task_view(task)

    @app.post("/api/import-url")
    def import_from_url(payload: dict = Body(...)):
        url = str((payload or {}).get("url") or "").strip()
        if not url:
            raise HTTPException(400, "請輸入歌譜網址")
        import shutil
        from .formats.musicxml import build_musicxml
        from .formats.url_import import import_score_from_url
        from .models import new_id
        from .storage import atomic_write_text, safe_filename, sha256_file
        try:
            res = import_score_from_url(url)
        except Exception as exc:
            raise HTTPException(400, f"網址歌譜抓取失敗：{exc}") from exc

        doc: ScoreDocument = res["document"]
        warnings = list(res.get("warnings") or [])
        doc.renumber()

        PATHS.imports.mkdir(parents=True, exist_ok=True)
        raw_txt_path = PATHS.imports / f"{safe_filename(doc.title or 'url_score')}.txt"
        try:
            atomic_write_text(raw_txt_path, res.get("rawText") or url)
        except Exception:
            raw_txt_path = None

        projects.import_document(doc, raw_txt_path if raw_txt_path and raw_txt_path.exists() else None)
        directory = projects.project_dir(doc.id, doc.title)
        xml, xml_warnings = build_musicxml(doc)
        warnings.extend(xml_warnings)
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
        projects.save_document(doc, snapshot=False)

        task_id = new_id("task")
        db.create_task(task_id, f"[網址] {doc.title}", str(raw_txt_path or url))
        db.update_task(
            task_id,
            status="done",
            stage="musicxml",
            progress=100,
            result_path=str(xml_path),
            project_id=doc.id,
            engine_mode=doc.engineMode,
            message=f"網址抓取完成：{doc.title}（{len(doc.measures)} 個小節）",
            error="",
        )
        return {
            "taskId": task_id,
            "projectId": doc.id,
            "document": doc.to_dict(),
            "warnings": warnings,
        }

    @app.get("/api/tasks")
    def list_tasks(limit: int = 30):
        return [_task_view(t) for t in db.list_tasks(limit)]

    @app.get("/api/tasks/{task_id}")
    def get_task(task_id: str):
        task = db.get_task(task_id)
        if not task:
            raise HTTPException(404, "找不到任務")
        return _task_view(task)

    @app.post("/api/tasks/{task_id}/cancel")
    def cancel_task(task_id: str):
        if not db.get_task(task_id):
            raise HTTPException(404, "找不到任務")
        pipeline.request_cancel(task_id)
        return _task_view(db.get_task(task_id))

    @app.post("/api/tasks/{task_id}/retry")
    def retry_task(task_id: str):
        task = db.get_task(task_id)
        if not task:
            raise HTTPException(404, "找不到任務")
        if task["status"] in {"running", "queued"}:
            raise HTTPException(409, "任務正在執行中")
        if not Path(task["source_path"]).exists():
            raise HTTPException(410, "原始檔已不存在，請重新導入檔案")
        db.update_task(task_id, status="queued", stage="upload", progress=10, error="", message="重新開始")
        _executor.submit(pipeline.run_task, task_id)
        return _task_view(db.get_task(task_id))

    # ---------------- 暫存樂譜 (.json) ----------------

    @app.get("/api/drafts")
    def list_drafts():
        return projects.list_drafts()

    @app.post("/api/drafts/load")
    def load_draft(payload: dict = Body(default={})):
        filename = str((payload or {}).get("filename") or "").strip()
        if not filename:
            raise HTTPException(400, "請提供暫存檔名稱")
        try:
            doc = projects.load_draft_file(filename)
            return doc.to_dict()
        except projects.ProjectError as exc:
            raise HTTPException(404, str(exc)) from exc

    @app.post("/api/drafts/open-folder")
    def open_drafts_folder(payload: dict = Body(default={})):
        import subprocess
        PATHS.drafts.mkdir(parents=True, exist_ok=True)
        filename = str((payload or {}).get("filename") or "").strip()
        target_file = (PATHS.drafts / Path(filename).name) if filename else None
        try:
            if os.name == "nt":
                if target_file and target_file.exists():
                    subprocess.Popen(["explorer.exe", f"/select,{str(target_file)}"])
                else:
                    os.startfile(str(PATHS.drafts))  # type: ignore[attr-defined]
        except Exception as exc:
            raise HTTPException(500, f"無法開啟資料夾：{exc}") from exc
        return {"ok": True, "folder": str(PATHS.drafts)}

    # ---------------- 專案 ----------------

    @app.get("/api/projects")
    def list_projects():
        return db.list_projects()

    @app.post("/api/projects")
    def create_project(payload: dict = Body(default={})):
        payload = dict(payload or {})
        raw_measures = payload.get("measures", 6)
        if isinstance(raw_measures, list):
            doc = ScoreDocument.from_dict(payload)
            projects.save_document(doc, snapshot=False)
            return doc.to_dict()
        doc = projects.create_project(
            payload.get("title") or "未命名樂譜", int(raw_measures or 6)
        )
        return doc.to_dict()

    @app.get("/api/projects/{doc_id}")
    def get_project(doc_id: str):
        try:
            return projects.load_document(doc_id).to_dict()
        except projects.ProjectError as exc:
            raise HTTPException(404, str(exc)) from exc

    @app.put("/api/projects/{doc_id}")
    def save_project(doc_id: str, payload: dict = Body(...)):
        payload = dict(payload or {})
        payload["id"] = doc_id
        try:
            doc = ScoreDocument.from_dict(payload)
        except Exception as e:
            raise HTTPException(400, f"Invalid document structure: {str(e)}") from e
        try:
            result = projects.save_document(doc)
        except projects.ProjectError as exc:
            raise HTTPException(507, str(exc)) from exc
        except Exception as exc:
            raise HTTPException(502, f"Save failed: {str(exc)}") from exc
        return {**result, "document": doc.to_dict()}

    @app.post("/api/projects/{doc_id}/duplicate")
    def duplicate_project(doc_id: str, payload: dict = Body(default={})):
        return projects.duplicate_project(doc_id, payload.get("title")).to_dict()

    @app.delete("/api/projects/{doc_id}")
    def delete_project(doc_id: str, removeFiles: bool = False):
        projects.delete_project(doc_id, remove_files=removeFiles)
        return {"deleted": doc_id}

    @app.get("/api/projects/{doc_id}/versions")
    def list_versions(doc_id: str):
        return projects.list_versions(doc_id)

    @app.post("/api/projects/{doc_id}/versions/{name}/restore")
    def restore_version(doc_id: str, name: str):
        try:
            return projects.restore_version(doc_id, name).to_dict()
        except projects.ProjectError as exc:
            raise HTTPException(404, str(exc)) from exc

    @app.post("/api/projects/{doc_id}/backup")
    def backup_project(doc_id: str):
        return projects.backup_project(doc_id)

    @app.post("/api/projects/{doc_id}/export")
    def export_project(doc_id: str, payload: dict = Body(default={})):
        fmt = (payload or {}).get("format", "musicxml")
        try:
            return projects.export_document(doc_id, fmt)
        except projects.ProjectError as exc:
            raise HTTPException(400, str(exc)) from exc

    @app.get("/api/projects/{doc_id}/preview")
    def preview_export(doc_id: str, format: str = "musicxml"):
        doc = projects.load_document(doc_id)
        renderer = projects.EXPORTERS.get(format.lower())
        if not renderer:
            raise HTTPException(400, f"不支援的格式：{format}")
        mime = renderer[1]
        content = renderer[2](doc)
        if isinstance(content, bytes):
            from fastapi.responses import Response
            return Response(content=content, media_type=mime)
        return PlainTextResponse(content, media_type=mime)

    @app.post("/api/preview")
    def preview_draft(payload: dict = Body(...)):
        """以尚未保存的草稿即時預覽輸出，不寫入任何檔案。"""
        fmt = str((payload or {}).get("format", "musicxml")).lower()
        renderer = projects.EXPORTERS.get(fmt)
        if not renderer:
            raise HTTPException(400, f"不支援的格式：{fmt}")
        mime = renderer[1]
        doc = ScoreDocument.from_dict((payload or {}).get("document") or {})
        content = renderer[2](doc)
        if isinstance(content, bytes):
            from fastapi.responses import Response
            return Response(content=content, media_type=mime)
        return PlainTextResponse(content, media_type=mime)

    # ---------------- V3.00：小節增刪 / 轉調 / LilyPond 排版 ----------------

    @app.post("/api/projects/{doc_id}/measures/insert")
    def insert_measures(doc_id: str, payload: dict = Body(default={})):
        doc = projects.load_document(doc_id)
        at = int((payload or {}).get("index", 0))
        count = int((payload or {}).get("count", 1))
        from .models import ScoreMeasure
        new_measures = [ScoreMeasure() for _ in range(max(1, count))]
        at = max(0, min(at, len(doc.measures)))
        doc.measures = doc.measures[:at] + new_measures + doc.measures[at:]
        result = projects.save_document(doc)
        return {**result, "document": doc.to_dict()}

    @app.post("/api/projects/{doc_id}/measures/delete")
    def delete_measures(doc_id: str, payload: dict = Body(default={})):
        doc = projects.load_document(doc_id)
        nums = [int(n) for n in (payload or {}).get("measures", [])]
        if not nums:
            raise HTTPException(400, "請指定要刪除的小節編號")
        doc.measures = [m for m in doc.measures if m.number not in nums]
        result = projects.save_document(doc)
        return {**result, "document": doc.to_dict()}

    @app.post("/api/projects/{doc_id}/transpose")
    def transpose_project(doc_id: str, payload: dict = Body(...)):
        target = str((payload or {}).get("key", "")).strip().upper()
        if not target:
            raise HTTPException(400, "請指定目標調性 key")
        doc = projects.load_document(doc_id)
        from .transpose import transpose_document
        from_key = doc.key
        info = transpose_document(doc, target)
        if not info.get("changed"):
            doc.key = target
            info = {"changed": from_key != target, "fromKey": from_key, "toKey": target, "semi": 0, "chordCount": 0}
        result = projects.save_document(doc)
        return {**result, "document": doc.to_dict(), "transpose": info}

    @app.get("/api/lilypond/status")
    def lilypond_status():
        from . import lilypond as lily_mod
        exe = lily_mod.find_lilypond()
        if exe is None:
            return {"installed": False}
        import subprocess as _sp
        try:
            out = _sp.run([str(exe), "--version"], capture_output=True, text=True, timeout=30)
            ver = (out.stdout or out.stderr or "").splitlines()[0] if (out.stdout or out.stderr) else ""
        except Exception:
            ver = "unknown"
        return {"installed": True, "path": str(exe), "version": ver}

    @app.get("/api/files/download")
    def download(path: str):
        """只允許下載資料根目錄內的檔案（防路徑穿越）。"""
        try:
            candidate = Path(path)
            # 統一轉為相對於 data.parent 的相對路徑，再交給 resolve_inside
            if candidate.is_absolute():
                try:
                    relative = str(candidate.relative_to(PATHS.data.parent)).replace("\\", "/")
                except ValueError:
                    raise HTTPException(403, "檔案不在允許的資料目錄內")
            else:
                relative = str(candidate).replace("\\", "/")
            target = resolve_inside(PATHS.data.parent, relative)
        except ValueError as exc:
            raise HTTPException(403, str(exc)) from exc
        if not target.exists() or not target.is_file():
            raise HTTPException(404, "找不到檔案")
        return FileResponse(target, filename=target.name)

    @app.get("/api/files/preview")
    def preview(path: str):
        """PDF 內嵌預覽：Content-Disposition: inline，讓 iframe 顯示 PDF 而非觸發下載。"""
        try:
            candidate = Path(path)
            if candidate.is_absolute():
                try:
                    relative = str(candidate.relative_to(PATHS.data.parent)).replace("\\", "/")
                except ValueError:
                    raise HTTPException(403, "檔案不在允許的資料目錄內")
            else:
                relative = str(candidate).replace("\\", "/")
            target = resolve_inside(PATHS.data.parent, relative)
        except ValueError as exc:
            raise HTTPException(403, str(exc)) from exc
        if not target.exists() or not target.is_file():
            raise HTTPException(404, "找不到檔案")
        return FileResponse(target, media_type="application/pdf", headers={"Content-Disposition": "inline"})

    # ---------------- ScoreOCR Toolkit 端點與掛載 ----------------
    from src.ocr.toolkit_routes import (
        router as toolkit_router,
        UPLOAD_DIR,
        PROCESSED_DIR,
        STATIC_DIR,
        upload as toolkit_upload,
    )
    app.include_router(toolkit_router)
    app.mount("/files/processed", StaticFiles(directory=str(PROCESSED_DIR)), name="processed_files")
    app.mount("/files/uploads", StaticFiles(directory=str(UPLOAD_DIR)), name="upload_files")

    @app.post("/preprocess")
    async def legacy_preprocess(file: UploadFile = File(...)):
        return await toolkit_upload(file)

    # ---------------- 靜態前端 ----------------

    web_dir = PATHS.web
    if web_dir.exists():
        app.mount("/assets", StaticFiles(directory=str(web_dir / "assets")), name="assets")

        studio_dir = web_dir / "score-studio"
        if studio_dir.exists():
            app.mount("/score-studio", StaticFiles(directory=str(studio_dir)), name="score-studio")

        if STATIC_DIR.exists():
            app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")

            @app.get("/canvas-editor")
            def canvas_editor():
                return FileResponse(STATIC_DIR / "index.html")

            @app.get("/visual-editor")
            def visual_editor():
                return FileResponse(STATIC_DIR / "index.html")

        @app.get("/")
        def index():
            return FileResponse(web_dir / "index.html")

        # ---- ScoreStudio 並存路由（§5.2；Feature Flag 未開時新路由直接可用，舊路徑不變）----
        app.include_router(ss_routes.router)

        @app.get("/api/flags/score-studio")
        def get_score_studio_flags():
            return _score_studio_flags()

        @app.post("/api/flags/score-studio")
        def set_score_studio_flags(payload: dict = Body(default={})):
            for k in ("scoreStudioEnabled", "scoreStudioDefault"):
                if k in payload:
                    save_user_config({k: bool(payload[k])})
            return _score_studio_flags()

        @app.get("/editor/studio/{doc_id}")
        def editor_studio(doc_id: str):
            studio_dir = web_dir / "score-studio"
            page = studio_dir / "index.html"
            if page.exists():
                return FileResponse(page)
            return HTMLResponse(
                "<h1>ScoreStudio 尚未安裝</h1><p>web/score-studio/index.html 不存在。</p>"
                f'<a href="/editor/legacy/{doc_id}">以舊版編輯器開啟</a>', status_code=501)

        @app.get("/editor/legacy/{doc_id}")
        def editor_legacy(doc_id: str):
            return FileResponse(web_dir / "index.html")

        @app.get("/editor/{doc_id}")
        def editor_default(doc_id: str):
            """依 Feature Flag 導向（§5.2）。"""
            from fastapi.responses import RedirectResponse
            flags = _score_studio_flags()
            target = "/editor/studio" if (flags["enabled"] and flags["default"]) else "/editor/legacy"
            return RedirectResponse(f"{target}/{doc_id}", status_code=302)

        @app.get("/{path:path}")
        def spa(path: str):
            if ".." in path or path.startswith(("api/", "download/", "etc/")):
                raise HTTPException(status_code=404, detail="Not found")
            candidate = (web_dir / path).resolve()
            if candidate.is_file() and str(candidate).startswith(str(web_dir.resolve())):
                return FileResponse(candidate)
            return FileResponse(web_dir / "index.html")
    else:

        @app.get("/")
        def missing_web():
            return HTMLResponse(
                f"<h1>找不到前端資源</h1><p>預期路徑：{web_dir}</p>", status_code=500
            )

    return app


def _task_view(task: dict) -> dict:
    if not task:
        return {}
    return {
        "id": task["id"],
        "sourceName": task["source_name"],
        "status": task["status"],
        "stage": task["stage"],
        "stageLabel": pipeline.STAGE_LABELS.get(task["stage"], task["stage"]),
        "progress": task["progress"],
        "message": task["message"],
        "error": task["error"],
        "engineMode": task["engine_mode"],
        "pages": task["pages"],
        "currentPage": task["current_page"],
        "resultPath": task["result_path"],
        "projectId": task["project_id"],
        "createdAt": task["created_at"],
        "updatedAt": task["updated_at"],
    }


if __name__ == "__main__":
    import uvicorn

    port = int(os.environ.get("SHEETMUSIC_PORT", "8763"))
    uvicorn.run(create_app(), host="127.0.0.1", port=port, log_level="info")

