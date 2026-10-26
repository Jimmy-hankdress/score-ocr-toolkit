# 檔案清單與用途

## 一、主要入口檔案

| 相對路徑 | 絕對路徑 | 用途 | 正式使用 |
|----------|----------|------|----------|
| `web/index.html` | `D:\SheetMusicOMR_v3.00\web\index.html` | 主頁面入口 | ✓ |
| `web/assets/app.js` | `D:\SheetMusicOMR_v3.00\web\assets\app.js` | 主應用邏輯 (4200+ 行) | ✓ |
| `web/assets/styles.css` | `D:\SheetMusicOMR_v3.00\web\assets\styles.css` | 樣式表 | ✓ |
| `launcher.py` | `D:\SheetMusicOMR_v3.00\launcher.py` | 伺服器啟動器 | ✓ |

## 二、前端資產 (web/assets/)

### 正式使用檔案
| 檔案 | 用途 | 版本/SHA |
|------|------|----------|
| `app.js` | 主應用邏輯 | v3.05.07, OMR-SOLA-7 |
| `app.js.bak-1790093139` | 備份 | - |
| `app.js.bak_v304_timeline_attempt` | 備份 | - |
| `app.js.test` | 測試用 | - |
| `app-v2.js` | 舊版 | - |
| `styles.css` | 樣式表 | v3.05.07 |
| `event_model.js` | Event Model (phase15) | phase1.5.0 |
| `layout_engine.js` | 排版引擎 (phase15) | phase2.0.0 |
| `svg_renderer.js` | SVG 渲染器 (phase15) | phase3a.0.0 |
| `event_session.js` | Phase A Session 管理器 | phase-a.0.0.1 |
| `event_session.css` | Phase A 樣式 | phase-a.0.0.1 |
| `phase_a_integration.js` | Phase A 頁面整合 | phase-a.0.0.1 |
| `score_studio_timeline_model.js` | Timeline Model | - |
| `score_studio_timeline_bridge.js` | Timeline Bridge | - |
| `score_studio_active_note_bridge.js` | Active Note Bridge | - |
| `score_studio_command_history.js` | Command History | - |
| `editor.js` | Editor Core (phase4) | - |
| `command_stack.js` | Command Stack (phase4) | - |
| `measure_validation.js` | Measure Validation (phase4) | - |

### 和弦圖 (web/assets/chords/)
| 目錄 | 檔案數 | 用途 |
|------|--------|------|
| `chords/guitar/` | 332 | 吉他指法圖 SVG |
| `chords/ukulele/` | 136 | 烏克麗麗指法圖 SVG |

### 不建議修改的檔案
- 所有 `*_backup*.js` / `*_backup*.css` — 歷史備份
- `app.js.test` — 測試檔案，非正式使用

## 三、後端模組 (app/)

### 核心模組
| 檔案 | 用途 | 主要函數/類別 |
|------|------|---------------|
| `app/config.py` | 設定 | APP_NAME, APP_VERSION, PATHS |
| `app/db.py` | 資料庫 | SQLite 操作 |
| `app/projects.py` | 專案管理 | CRUD API |
| `app/server.py` | FastAPI 主伺服器 | create_app(), 路由註冊 |
| `app/lilypond.py` | LilyPond 匯出 | export_score_to_lilypond() |

### 匯出格式 (app/formats/)
| 檔案 | 用途 |
|------|------|
| `formats/midi.py` | MIDI 匯出 |
| `formats/musicxml.py` | MusicXML 匯出 |
| `formats/sola321.py` | Sola321 匯出 |
| `formats/word.py` | Word (.docx) 匯出 |
| `formats/text_export.py` | 文字匯出 |
| `formats/text_import.py` | 文字匯入 |

### OMR 引擎 (app/omr/)
| 檔案 | 用途 |
|------|------|
| `omr/engine.py` | OMR 主引擎 |
| `omr/jianpu.py` | 簡譜辨識 |
| `omr/jianpu2_patch.py` | jianpu2 修正 |
| `omr/jpeditor_engine.py` | jpeditor 引擎 |
| `omr/layout.py` | 版面分析 |
| `omr/orpheusnet.py` | OrpheusNet CNN |
| `omr/scoreforge.py` | ScoreForge 整譜辨識 |

### Score Studio (app/scorestudio/)
| 檔案 | 用途 |
|------|------|
| `scorestudio/formats_export.py` | 匯出格式 |
| `scorestudio/legacy_adapter.py` | Legacy 適配器 |
| `scorestudio/omr_adapter.py` | OMR 適配器 |
| `scorestudio/score_document_service.py` | 文件服務 |
| `scorestudio/score_studio_routes.py` | API 路由 |

## 四、階段檔案

### phase15/ (Event Model 階段)
| 檔案 | 用途 | 正式使用 |
|------|------|----------|
| `event_model.js` | Legacy → Event 轉換 | ✓ (複製到 web/assets/) |
| `layout_engine.js` | tick → X 座標轉換 | ✓ (複製到 web/assets/) |
| `svg_renderer.js` | Layout → SVG 渲染 | ✓ (複製到 web/assets/) |
| `event_to_legacy.js` | Event → Legacy 轉換 | ⚠️ 部分使用 |
| `event_to_legacy_test.js` | 轉換測試 | ✗ |
| `layout_test_runner.js` | 排版測試 | ✗ |
| `preview.html` | 預覽頁面 | ✗ |
| `preview_demo.js` | 預覽示範 | ✗ |
| `preview_test.js` | 預覽測試 | ✗ |
| `roundtrip_test.js` | 往返測試 | ✗ |
| `svg_renderer_test.js` | 渲染器測試 | ✗ |
| `test_runner.js` | 測試運行器 | ✗ |
| `results.txt` | 測試結果 | ✗ |

### phase4/ (Editor Core)
| 檔案 | 用途 | 正式使用 |
|------|------|----------|
| `editor.js` | Editor 核心 | ✓ (複製到 web/assets/) |
| `command_stack.js` | Command Stack | ✓ (複製到 web/assets/) |
| `measure_validation.js` | 小節驗證 | ✓ (複製到 web/assets/) |
| `editor_preview.html` | 預覽頁面 | ✗ |
| `editor_preview_demo.js` | 示範 | ✗ |
| `editor_preview_test.js` | 測試 | ✗ |

### phase6/ (Active Note 整合)
| 檔案 | 用途 | 正式使用 |
|------|------|----------|
| `score_studio_active_note_bridge.js` | Bridge | ✓ (複製到 web/assets/) |
| `score_studio_timeline_model.js` | Timeline Model | ✓ (複製到 web/assets/) |
| `score_studio_timeline_bridge.js` | Timeline Bridge | ✓ (複製到 web/assets/) |
| `score_studio_command_history.js` | Command History | ✓ (複製到 web/assets/) |
| `legacy_event_readiness_audit.js` | Audit | ✗ |
| `legacy_event_readiness_audit_test.js` | Audit 測試 | ✗ |
| `legacy_to_event_adapter.js` | Adapter | ✗ |
| `legacy_to_event_adapter_test.js` | Adapter 測試 | ✗ |

## 五、資料目錄

### data/projects/
- 存放所有專案的 `project.json`
- 每個專案有獨立目錄: `{標題}-{UUID}/project.json`
- Last Dance 專案: `data/projects/Last Dance-5be87fa46594/project.json`

### data/exports/
- 匯出檔案存放處
- 包含 MusicXML, MIDI, Word, Sola321 等格式

### data/import/
- 上傳的原始檔案存放處

### data/logs/
- 伺服器日誌
- `launcher.log` — 主要日誌
- `restart.log` — 重啟記錄

### data/backups/
- 專案備份

## 六、備份目錄 (請保留)

| 目錄 | 內容 | 用途 |
|------|------|------|
| `web_backup_before_v305_20261001_164845/` | v3.05 前備份 | 恢復用 |
| `_backup_before_chordslider/` | 和弦滑塊前備份 | 恢復用 |
| `_backup_before_legacy_ui/` | Legacy UI 前備份 | 恢復用 |
| `_backup_before_phase5/` | Phase 5 前備份 | 恢復用 |
| `_backup_before_phase6b4/` | Phase 6b4 前備份 | 恢復用 |
| `_backup_before_phase6b4_cleanup/` | 清理前備份 | 恢復用 |
| `_backup_before_phase6b5/` | Phase 6b5 前備份 | 恢復用 |

## 七、測試檔案

### Node.js 測試
- `phase15/*_test.js` — Event Model 測試
- `phase4/*_test.js` — Editor 測試
- `phase6/*_test.js` — Active Note 測試
- `tools/test_regression.py` — Python 回歸測試

### 執行方式
```powershell
cd D:\SheetMusicOMR_v3.00\phase15
node event_to_legacy_test.js
node roundtrip_test.js
```

## 八、範例檔案

### samples/
- `Last Dance.pdf` — 測試用 PDF 樂譜
- `IMG_5203.JPG` — 測試用圖片
- 其他範例檔案...

## 九、模型檔案

### models/
- `manifest.json.example` — 模型清單位範例

## 十、工具腳本

### tools/
| 檔案 | 用途 |
|------|------|
| `debug_page.py` | 除錯頁面 |
| `gen_test_jianpu.py` | 生成測試簡譜 |
| `score_jianpu.py` | 簡譜評分 |
| `test_regression.py` | 回歸測試 |

## 十一、配置文件

### config/
- `user-config.json` — 使用者設定

### data/config/
- `user-config.json` — 伺服器端使用者設定

## 十二、保護檔案 (勿修改)

- `data/projects/*/project.json` — 使用者資料
- `data/sheetmusic.sqlite3` — 資料庫
- `data/tasks.db` — 任務佇列
- 所有備份目錄
