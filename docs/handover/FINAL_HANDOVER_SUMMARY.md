# ScoreForge 技術交接摘要

## 1. 專案根目錄
```
D:\SheetMusicOMR_v3.00
```

## 2. 正確啟動命令
```powershell
cd D:\SheetMusicOMR_v3.00
.venv\Scripts\python.exe launcher.py --port 8763 --no-browser
```

## 3. 網址
```
http://127.0.0.1:8763/
```

## 4. 目前狀態
- **伺服器**: 運行中 (PID 32376)
- **版本**: v3.05.07 (前端) / 3.0.0 (後端)
- **Git**: 無（依賴備份目錄）
- **專案**: Last Dance (39 measures) 可載入

## 5. 最重要的 10 個檔案

| # | 檔案 | 用途 |
|---|------|------|
| 1 | `web/index.html` | 主頁面入口 |
| 2 | `web/assets/app.js` | 主應用邏輯 (4200+ 行) |
| 3 | `web/assets/styles.css` | 樣式表 |
| 4 | `app/server.py` | FastAPI 主伺服器 |
| 5 | `app/projects.py` | 專案管理 API |
| 6 | `phase15/event_model.js` | Event Model 定義 |
| 7 | `phase15/layout_engine.js` | 排版引擎 |
| 8 | `phase15/svg_renderer.js` | SVG 渲染器 |
| 9 | `web/assets/phase_a_integration.js` | Phase A 整合 |
| 10 | `launcher.py` | 伺服器啟動器 |

## 6. 尚未完成的核心需求

| 需求 | 狀態 | 阻塞原因 |
|------|------|----------|
| 任意 tick 插入事件 | ✗ | Legacy 格式無 tick 欄位 |
| 事件拖曳移動 | ✗ | 無實作 |
| 和弦圖顯示 | ✗ | renderV3ChordSlots 已改為純文字 |
| Event Model 持久化 | ✗ | ID 不穩定，重新載入重建 |

## 7. 最嚴重的 5 個問題

| # | 問題 | 嚴重度 |
|---|------|--------|
| 1 | BUG-002: 音符無法任意插入 | 🔴 高 |
| 2 | BUG-003: 歌詞無法任意插入 | 🔴 高 |
| 3 | BUG-004: 和弦無法任意插入 | 🔴 高 |
| 4 | BUG-005: 事件無法移動 | 🔴 高 |
| 5 | BUG-001: 和弦圖無法顯示 | 🟡 中 |

## 8. 新工程師應優先閱讀的文件

1. **00_PROJECT_OVERVIEW.md** — 了解專案全貌
2. **05_KNOWN_ISSUES.md** — 了解現有問題
3. **07_DEVELOPMENT_PLAN.md** — 了解後續計畫
4. **01_REQUIREMENTS.md** — 了解需求與完成度

## 9. 新工程師接手後的第一個可執行任務

```
1. 啟動伺服器
   cd D:\SheetMusicOMR_v3.00
   .venv\Scripts\python.exe launcher.py --port 8763 --no-browser

2. 開啟瀏覽器
   http://127.0.0.1:8763/

3. 載入 Last Dance 專案
   - 點擊「Score Studio」標籤
   - 選擇「Last Dance」

4. 執行 Phase A 驗證
   - 按 F12 → Console
   - 貼上驗證腳本
   C:\Users\hankdress\HermesMemoryBank\cache\scratch\phase_a_verification_console.js

5. 回報結果
   - Console 輸出
   - 截圖
   - PASS/FAIL 判定
```

## 10. 尚未完成的交接項目

| 項目 | 原因 |
|------|------|
| Phase A 實際驗證 | 需使用者協助開啟瀏覽器測試 |
| 編輯功能實際測試 | Legacy 限制，部分功能無法實現 |
| Schema 變更決策 | 需使用者確認方向 |

---

**交接完成日期**: 2026-10-13
**交接者**: Agnes (Hermes Agent)
**狀態**: 文件完成，待驗證
