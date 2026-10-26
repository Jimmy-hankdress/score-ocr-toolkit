# PRE_SCORE_STUDIO_AUDIT — SheetMusicOMR V3.00 盤點（只讀分析）

> 依《ScoreStudio 離線編輯器整合總規格》第 2 節產出。
> 產出時刻：整合 ScoreStudio **之前**。本階段未修改任何程式檔。
> 專案：`D:\SheetMusicOMR_v3.00`（Windows 11 本機離線工具）。

---

## 1. 專案目錄樹（排除 .venv / node_modules / __pycache__ / 暫存 / 輸出 / 大型二進位）

```
D:\SheetMusicOMR_v3.00\
├─ app\                          # 後端（Python + FastAPI）
│  ├─ __init__.py               # 空（package 標記）
│  ├─ config.py                 # 路徑設定 PATHS、user-config、離線根目錄邏輯
│  ├─ db.py                     # SQLite（projects / tasks / project_files 三表）
│  ├─ models.py                 # ScoreDocument / ScoreMeasure / ScoreBeat（dataclass）
│  ├─ lilypond.py              # 轉調用 LilyPond（保留 /api/lilypond/status）
│  ├─ projects.py              # 專案 CRUD + EXPORTERS/匯出 + 版本快照/還原
│  ├─ server.py                # FastAPI create_app（全部 API 路由 + 靜態掛載）
│  ├─ storage.py               # 檔案 IO
│  ├─ transpose.py             # 移調
│  ├─ formats\                 # 匯出格式 registry
│  │  ├─ __init__.py           # EXPORTERS（musicxml/json/tsv/txt/sola321/midi/word）
│  │  ├─ midi.py  musicxml.py  sola321.py  text_export.py  text_import.py
│  │  ├─ validation.py  word.py
│  └─ omr\                     # OMR/OCR 引擎
│     ├─ engine.py             # Tesseract 偵測、OcrLine、run_ocr_lines
│     ├─ pipeline.py           # 任務流水線 start_task/run_task（匯入→OCR→專案）
│     ├─ jianpu.py  jianpu2_patch.py  layout.py  rasterize.py
│     ├─ scoreforge_engine.py  jpeditor_engine.py  orpheus_engine.py
│     └─ _pymupdf.py
├─ web\                         # 前端（Vanilla JS，Legacy Editor 在此）
│  ├─ index.html               # 單頁 SPA（3 頁籤：ChordPro / 簡譜格線 / SoLa321）
│  └─ assets\
│     ├─ app.js                # 主邏輯（1696 行；IIFE；state3.doc 為資料源）
│     ├─ app-v2.js             # 獨立簡譜八度腳本（未掛 index.html，僅殘留）
│     ├─ jianpu-render.js      # 簡譜排版渲染（ASCII→標準點符號）
│     ├─ styles.css            # 全部樣式（含 .sola321-* 可編輯簡譜）
│     ├─ chords.json  icon.svg
│     └─ app.js.bak-*          # 備份殘檔（應清理）
├─ config\user-config.json      # 預設設定（run.bat 首次拷貝到 data\config\）
├─ data\                        # 使用者資料（可寫、可備份）
│  ├─ projects\               # 105 個專案，各含 project.json + source\ + exports\
│  ├─ imports\  exports\  work\  logs\  backups\
│  ├─ config\user-config.json
│  └─ sheetmusic.sqlite3(-wal/-shm)   # db
├─ models\  runtime\            # 離線模型/執行檔（大型二進位，排除盤點）
├─ launcher.py  run.bat  run_server.py  bootstrap.py
├─ tools\  build\  samples\  skills\  jpeditor-repo\  jpeditor_*.exe
├─ _jsdom_test\                 # 前端 jsdom 驗證腳本（node）
├─ docs\                        # 本盤點文件所在
└─ requirements.txt  README.md  HERMES_PROMPT.md  VERSION_V2.0x.md
```

---

## 2. Python／FastAPI 入口與啟動方式

- **ASGI 入口**：`app/server.py` 的 `create_app()`（factory，無模組層 `app` 實體）。
- **正式啟動**：`run.bat` → `.venv\Scripts\python.exe launcher.py --port 8763 --no-browser`。
  - `launcher.py`：檢查 venv/依賴、找可用 port（**只綁 127.0.0.1**）、開 log、`uvicorn` 跑 `create_app`、可選開瀏覽器。
- **手動啟動**：`python -m uvicorn app.server:create_app --factory --host 127.0.0.1 --port 8763`。
  - 注意：`app.server:app`（無 factory）會報 `Attribute "app" not found`，必須 `--factory`。
- **離線根目錄**：`app/config.py` `default_data_root()` 永遠用 `<安裝目錄>\data`（V2.01 強制，與 AppData 分離）。
- **監聽**：預設 `127.0.0.1:8763`（規格書 1.1 寫的 8756 是 V2.01；V3.00 實際 8763，以現況為準）。

---

## 3. 全部既有 API 路由與用途（server.py，共 30 個）

### 引擎/設定
- `GET /api/health` — 健康檢查
- `POST /api/engine/refresh` — 重掃 OMR 引擎狀態
- `GET /api/config` · `POST /api/config` — 讀/寫 user-config
- `GET /api/lilypond/status` — LilyPond 偵測（轉調用，保留）

### 匯入任務（OMR/OCR 流水線）
- `POST /api/tasks`（UploadFile）— 建立匯入任務（離線排程 OCR）
- `GET /api/tasks` · `GET /api/tasks/{task_id}` — 列舉/查詢
- `POST /api/tasks/{task_id}/cancel` · `/retry` — 取消/重試

### 專案（Legacy Editor 資料源）
- `GET/POST /api/projects`、`GET/PUT/DELETE /api/projects/{doc_id}`
- `POST .../duplicate`、`GET .../versions`、`POST .../versions/{name}/restore`
- `POST .../backup`、`POST .../export`（依 format 走 EXPORTERS）
- `GET .../preview`、`POST /api/preview`
- `POST .../measures/insert` · `POST .../measures/delete`
- `POST .../transpose`

### 檔案
- `GET /api/files/download` · `GET /api/files/preview`（PDF 內嵌）

### 靜態前端
- `GET /` → `web/index.html`；`GET /{path:path}` → SPA 回退（找不到檔回 index.html）
- `app.mount("/assets", StaticFiles(web/assets))`

---

## 4. 靜態檔案與舊編輯器位置

| 物件 | 位置 |
|---|---|
| Legacy Editor SPA | `web/index.html` + `web/assets/app.js`（主） |
| 輔助渲染 | `web/assets/jianpu-render.js`、`web/assets/app-v2.js`（殘留未掛） |
| 樣式 | `web/assets/styles.css`（含 `.sola321-*` 可編輯簡譜） |
| 和弦字典 | `web/assets/chords.json` |
| 前端狀態模型 | `state3.doc`（`app.js` IIFE 內），資料源=`project.json` |

**現況注意**：上一輪已把「LilyPond 頁籤」改成「SoLa321 可編輯簡譜」（`#sola321-pane`）。
ScoreStudio 依規格應另起 `static/score-studio/`（或等價 `web/score-studio/`）**並存**，不取代此 Legacy。

---

## 5. OMR 結果的實際資料格式與儲存位置

- **儲存**：`data/projects/{Title}-{10hex}/project.json`（`doc_XXXX`）。
- **格式**（`models.py` `ScoreDocument`）：
  ```
  { id, title, lyricist, composer, key, timeSignature, tempo,
    engineMode (scoreforge/tesseract-ocr/text-import/manual),
    engineNote, sourceName, createdAt, updatedAt,
    measures: [ { number, lineIndex, linePosition,
                  chordText, noteText, lyricText, sourcePage,
                  beats: [ { beat, note, lyric, chord,
                             duration (quarter|eighth|16th|...),
                             confidence, annotation } ] } ] }
  ```
- **原始 OCR 中間產物**：`data/work/{task_id}/`（暫存；每頁 PNG、OcrLine JSON、bbox）。
  - `OcrLine` 帶 `page / text / bbox(x,y,w,h) / confidence`。
  - 注意：`project.json` 的 beats **目前只有 confidence + annotation，未保留 bbox / rawToken**
    → ScoreDocument v1 要求保留 bbox/rawToken，**需在 OMR Adapter 由 work\ 暫存或重導取得**，
    或標 `reviewStatus=unresolved`（絕不憑空補造）。
- **原圖**：`data/projects/…/source/{原始檔}`（如 `白鷺鷥.JPG`）＋ PDF 轉圖在 `work\`。

---

## 6. PDF/JPG 匯入 → OCR → 任務完成 → 跳轉編輯器 流程

1. 前端 `#dropzone`/上傳 → `POST /api/tasks`（`pipeline.start_task` 存原檔到 `data\imports`、建 work\、排程）。
2. `pipeline.run_task`（離線 thread）：PDF 先 `rasterize`→高解析 PNG；`engine.detect_engine`→Tesseract/ScoreForge/jpeditor。
3. `run_ocr_lines`→`OcrLine`（帶 bbox/confidence）；`jianpu.py` 幾何分 band、`_looks_like_tab` 跳六線譜、`find_bands` 切小節。
4. 組 `ScoreDocument`（`expand_beats`、`duration_from_token`），`sourcePage` 標頁碼，`confidence` 落 beats。
5. `projects.save_document`（建目錄 + 快照 + `db.upsert_project`）。
6. 前端 3 秒輪詢 `GET /api/tasks/{id}`（`pollTask`），`status=done` 時 `openProject(newDocId)` 自動載入樂譜。

---

## 7. JSON / TSV / TXT / MusicXML 讀寫位置

- **讀**：`formats/text_import.py`（csv/tsv/txt/son/json → ScoreDocument）；`omr/pipeline._run_text`。
- **寫**：`formats/__init__.py` `EXPORTERS`：
  - `json`→`text_export.document_to_json`、`tsv`→`document_to_tsv`、`txt`→`document_to_plain_text`
  - `musicxml`→`musicxml.document_to_musicxml`、`sola321`→`sola321.export_score_to_sola321`、`midi`、`word`
- **路由**：`POST /api/projects/{id}/export?format=…` 走 `projects.export_document`。

---

## 8. 專案 / 原圖 / 快取 / 備份 / 輸出 資料夾位置

| 類別 | 路徑 |
|---|---|
| 專案 | `data/projects/{Title}-{10hex}/`（`project.json` + `source\` + `exports\`） |
| 原圖/匯入 | `data/projects/…/source/`、`data/imports/` |
| OMR 暫存快取 | `data/work/{task_id}/` |
| 備份（版本快照） | `data/backups/`、專案内 `versions`（`projects.list_versions/restore_version`） |
| 輸出匯出 | `data/exports/` + `data/projects/…/exports/` |
| 日誌 | `data/logs/`（+ 頂層 `logs/`） |
| DB | `data/sheetmusic.sqlite3` |

> 盤點排除項：`.venv`、`node_modules`、`__pycache__`、`data/work`、`data/exports`、`models/`、`runtime/`、`jpeditor_*.exe`。

---

## 9. 既有測試、啟動 BAT、PowerShell 腳本

- **測試**：`_jsdom_test/hermes-verify-sola321-frontend.js`（jsdom，23 項）；`tools/test_regression.py`、`tools/gen_test_jianpu.py`。
- **啟動**：`run.bat`（一鍵，port 8763）、`run_server.py`（殘留、指向 V2.01 8756，**應清或更新**）、`launcher.py`。
- **PowerShell**：專案**無** `.ps1`；`scripts/` 目錄不存在 → 依規格需**新增** `scripts/verify_score_studio.ps1` 等。
- `build/build.bat`（PyInstaller 打包，與本次無關）。

---

## 10. 可能受此次整合影響的檔案清單

**新增（不改舊）**：
- `app/models/score_document.py`、`score_events.py`、`score_provenance.py`、`score_validation.py`
- `app/services/omr_adapter.py`、`score_document_service.py`、`score_validator.py`、`score_history_service.py`、`score_autosave_service.py`、`legacy_score_adapter.py`
- `app/api/score_studio_routes.py`
- `app/tests/test_score_document.py`、`test_omr_adapter.py`、`test_score_validator.py`、`test_musicxml_roundtrip.py` + `fixtures/`
- `static/score-studio/*`（`index.html`、`score-studio.js`、`score-api.js`、`score-store.js`、`score-renderer-svg.js`、`score-layout.js`、`score-interaction.js`、`score-keyboard.js`、`score-playback.js`、`score-history.js`、`score-source-panel.js`、`score-validation-ui.js`、`score-studio.css`、`local-assets/`）
- `data/autosave/`、`data/snapshots/`、`data/source-pages/`
- `docs/SCORE_DOCUMENT_SCHEMA.md`、`SCORE_STUDIO_MIGRATION.md`、`SCORE_STUDIO_TEST_CASES.md`、`CHANGELOG_SCORE_STUDIO.md`
- `scripts/start.bat`、`verify_score_studio.ps1`、`backup_before_upgrade.ps1`

**輕量修改（需回歸測試全綠才動）**：
- `app/server.py`：掛載新 `score_studio_routes`、加 `/editor/{legacy|studio|default}` 路由、Feature Flag。
- `app/config.py`：新增 `SCORE_STUDIO_ENABLED/DEFAULT` 設定（預設 false，不動既有）。
- `app/formats/*`：匯出改由 ScoreDocument 轉換（保留舊輸出不進化）。

**絕不碰**：`app/omr/*` 主流程（高八度點修正、中文雙尺寸 OCR）、Tesseract、PDF 轉圖。

---

## 盤點結論
- 現有系統 = **單一 `project.json` 資料模型 + 離線 OMR 流水線 + 30 條 API + SPA 前端**。
- ScoreStudio 的核心工作是：在其上**加一層 `ScoreDocument v1`（唯一可編輯標準格式）＋ OMR Adapter ＋ SVG 前端 ＋ 並存路由/Feature Flag**，
  舊 Legacy 全數保留可切回。
- 最大風險點：`project.json` 未存 bbox/rawToken → Adapter 需由 `data/work` 暫存補，缺失即標 `unresolved`，**不可補造**。
- 備份（`_backup_before_scorestudio`）必須在 M0 完成、進 M1 之前。

**→ 盤點完成，停止於此。備份建立並驗證後，才可進入 M1。**
