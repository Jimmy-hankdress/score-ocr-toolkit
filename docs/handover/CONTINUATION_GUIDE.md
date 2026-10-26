# ScoreForge 專案對話延續說明

請將此內容貼入新對話框，可繼續交接與後續開發工作。

---

## 當前狀態（截至 2026-10-13）

### 交接文件已完成
位置：`D:\SheetMusicOMR_v3.00\docs\handover\`（共 12 檔，67 KB）
- 00_PROJECT_OVERVIEW.md ～ 10_HANDOVER_CHECKLIST.md
- FINAL_HANDOVER_SUMMARY.md（快速上手摘要）

### 伺服器狀態
- 埠號：8763
- 啟動命令：`.venv\Scripts\python.exe launcher.py --port 8763 --no-browser`
- 網址：http://127.0.0.1:8763/
- 健康檢查：`curl http://127.0.0.1:8763/api/health`

### 前端版本
- 主版本：v3.05.07（Legacy renderer，clean display）
- app.js SHA：a828db1b01c0094f
- styles.css SHA：a1992be8926f2866
- index.html SHA：dc46506250bcdc89

### 待驗證項目
- Phase A Event Session 預覽功能（架構已建立，需瀏覽器實測）
- 驗證腳本：`C:\Users\hankdress\HermesMemoryBank\cache\scratch\phase_a_verification_console.js`

### 核心阻塞（BUG-002~005）
Legacy 格式無 tick 座標，無法任意位置插入/移動音符、歌詞、和弦。
需決策：Schema 擴展（A）/ 雙格式儲存（B）/ 純 Event Model（C）。

### 測試通過率
- phase15 event_to_legacy_test.js：28/29 通過
- phase15 roundtrip_test.js：26/27 通過
- 伺服器健康檢查：通過

---

## 可直接複製的常用命令

```powershell
# 啟動伺服器
cd D:\SheetMusicOMR_v3.00
.venv\Scripts\python.exe launcher.py --port 8763 --no-browser

# 驗證健康
curl http://127.0.0.1:8763/api/health

# 列出專案
curl http://127.0.0.1:8763/api/projects

# 停止伺服器
netstat -ano | findstr :8763
taskkill /F /PID <PID>

# Phase15 測試
cd D:\SheetMusicOMR_v3.00\phase15
node event_to_legacy_test.js
node roundtrip_test.js

# 讀取交接文件
type docs\handover\FINAL_HANDOVER_SUMMARY.md
```

---

## 優先任務順序（P0-P5）

1. **P0**：驗證 Phase A 預覽功能
2. **P1**：決定 Schema 變更方案
3. **P2**：實作任意位置插入/移動（需 P1 決策）
4. **P3**：Save Gate 與持久化整合
5. **P4**：恢復和弦圖顯示
6. **P5**：回歸測試與優化

---

## 注意事項

- 專案根目錄：`D:\SheetMusicOMR_v3.00`
- 無 Git（依賴備份目錄管理版本）
- 勿刪除 `data/projects/`、`data/sheetmusic.sqlite3`、`data/tasks.db`
- 勿執行 `git reset --hard` 或 `git clean -fd`（無意義且可能遺失資料）
- 每次重大修改前請先建立備份（格式：`_backup_before_<階段>`）
