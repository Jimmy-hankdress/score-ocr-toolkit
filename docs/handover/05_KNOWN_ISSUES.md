# 已知問題清單

## BUG-001: 和弦圖無法顯示

### 問題現象
- 和弦庫有 332 個吉他 SVG 和 136 個烏克麗麗 SVG
- 但正文中的和弦只顯示純文字，無指法圖
- 點擊和弦無選取圖示功能

### 重現步驟
1. 開啟 Last Dance 專案
2. 查看和弦列
3. 預期：每個和弦上方有指法圖
4. 實際：只有文字（如 "B", "G", "D/F"）

### 預期結果 vs 實際結果
- **預期**: 和弦名稱 + 指法圖 SVG
- **實際**: 僅和弦名稱文字

### 影響範圍
- 所有使用和弦編輯的使用者
- 嚴重度: **中**（功能未斷裂，但體驗差）

### 根因分析
**已確認根因**:
- `renderV3ChordSlots()` 函數（app.js L2690+）已改為純文字輸出
- 原始設計使用 `v3ChordSlotHtml()` 產生 SVG
- v3.05.07 為保持畫面乾淨，移除了 SVG 輸出

**涉及檔案**:
- `web/assets/app.js` L73-97 (renderChordSvg)
- `web/assets/app.js` L2690-2700 (renderV3ChordSlots)
- `web/assets/app.js` L125-130 (v3ChordSlotHtml)

**已嘗試修復**:
- v3.05.08 嘗試恢復按鈕，但使用者要求回退

**建議修復方向**:
1. 恢復 renderV3ChordSlots 的 SVG 輸出
2. 保留 hover 顯示控制（不預設顯示）
3. 或新增獨立和弦庫面板

---

## BUG-002: 音符無法在任意位置插入

### 問題現象
- 只能追加音符到 noteText 末尾
- 無法在兩個既有音符之間插入新音符
- 無法在空白拍位置插入音符

### 重現步驟
1. 開啟 Last Dance 專案
2. Measure 1 有 8 個音符
3. 嘗試在第 4 拍後插入新音符
4. 預期：新音符出現在第 5 位置
5. 實際：無此功能，只能點擊「＋」追加到末尾

### 預期結果 vs 實際結果
- **預期**: 可在任意 tick 插入音符
- **實際**: 只能追加到末尾

### 影響範圍
- 所有需要編輯樂譜結構的使用者
- 嚴重度: **高**（核心功能缺失）

### 根因分析
**已確認根因**:
- Legacy 格式以 token 序列儲存 (`noteText: '3 2 3 2...'`)
- 無 tick 座標欄位
- 位置由 array index 隱式決定

**涉及檔案**:
- `web/assets/app.js` L3091-3099 (sola321-note-add binder)
- `phase15/event_model.js` (Event Model 有 start 欄位，但無法寫回)

**Legacy 格式限制**:
```javascript
// 現有格式
{ noteText: '1 2 3 4' }

// 需要新增（但未實現）
{ noteText: '1 2 3 4', noteTicks: [0, 1, 2, 3] }
```

**建議修復方向**:
1. **短期**: 限制編輯到既有 token 位置
2. **中期**: 擴展 Legacy schema 新增 tick 欄位
3. **長期**: 全面改用 Event Model 儲存

---

## BUG-003: 歌詞無法在任意位置插入

### 問題現象
- 同 BUG-002，歌詞也只能追加

### 重現步驟
1. 開啟 Last Dance 專案
2. 嘗試在第 3 個音節後插入新歌詞
3. 預期：新歌詞出現在正確位置
4. 實際：無此功能

### 影響範圍
- 同 BUG-002

### 根因分析
- 同 BUG-002，Legacy 格式限制

---

## BUG-004: 和弦無法在任意位置插入

### 問題現象
- 和弦槽只能追加，無法插入到中間位置

### 重現步驟
1. 開啟 Last Dance 專案
2. Measure 1 有 3 個和弦 (B G D/F)
3. 嘗試在第 2 個和弦前插入新和弦
4. 預期：新和弦出現在第 2 位置
5. 實際：只能追加到末尾

### 影響範圍
- 和弦編輯功能不完整

### 根因分析
- 同 BUG-002

---

## BUG-005: 事件無法移動

### 問題現象
- 無拖曳功能
- 無法將音符/歌詞/和弦移動到不同位置

### 重現步驟
1. 開啟 Last Dance 專案
2. 嘗試拖曳某個音符到不同位置
3. 預期：音符移動到新位置
4. 實際：無拖曳功能

### 影響範圍
- 所有需要調整事件位置的場景

### 根因分析
**已確認根因**:
- 無 drag handler 實作
- Legacy 格式無位置變動機制

**建議修復方向**:
1. 實作 drag-and-drop
2. 或提供「剪切/貼上」功能
3. 或提供「移動到指定 tick」UI

---

## BUG-006: Timeline Renderer 與 Legacy 混用風險

### 問題現象
- app.js 同時包含 Legacy 和 Timeline renderer
- 切換時可能產生視覺混亂
- v3.05.06 已將 Timeline 設為非預設，但未完全移除

### 重現步驟
1. 開啟頁面
2. 檢查 console，確認 useTimeline = false
3. 點擊「混合預覽」按鈕（應啟用 Phase A）
4. 觀察是否有 Timeline DOM 出現

### 預期結果 vs 實際結果
- **預期**: 僅 Legacy 或僅 Phase A SVG
- **實際**: 需驗證

### 影響範圍
- 視覺一致性
- 嚴重度: **中**

### 根因分析
**可能根因**:
- 兩個 renderer 同時存在於 app.js
- CSS 可能有衝突
- bindSola321Inputs 和 bindSola321TimelineInputs 可能同時綁定

**涉及檔案**:
- `web/assets/app.js` L2837+ (renderSola321MeasureTimeline)
- `web/assets/app.js` L3221+ (bindSola321TimelineInputs)

**建議修復方向**:
1. 明確分離 Legacy 和 Timeline 程式碼
2. 或完全移除 Timeline renderer（若不再使用）
3. 或建立明確的切換機制

---

## BUG-007: Event Model ID 不穩定

### 問題現象
- 重新載入專案後，Event ID 會變化
- 影響 Undo/Redo 和 Session 狀態

### 重現步驟
1. 開啟 Last Dance 專案
2. 檢查 Event Model 的 ID
3. 重新載入專案
4. 檢查 Event Model 的 ID
5. 預期：ID 應保持一致
6. 實際：ID 已變化

### 影響範圍
- Session 狀態持久化
- 嚴重度: **中**

### 根因分析
**已確認根因**:
- `nextId()` 使用全局 seq 計數器
- 重新載入後 seq 重置為 0
- 導致 ID 重新編排

**涉及檔案**:
- `phase15/event_model.js` L28-29
```javascript
var seq = 0;
function nextId(prefix) { seq += 1; return prefix + '-' + String(seq).padStart(3, '0'); }
```

**建議修復方向**:
1. 使用 UUID 或 hash 生成穩定 ID
2. 或從 Legacy data 派生 ID（如 `m{measure}.note.{index}`）

---

## BUG-008: Server 啟動依賴問題

### 問題現象
- 使用系統 Python 啟動時，缺少 python-docx 套件
- 需使用專案自有 venv

### 重現步驟
1. 執行 `python launcher.py --port 8763 --no-browser`
2. 錯誤：`ModuleNotFoundError: No module named 'docx'`
3. 改用 `.venv\Scripts\python.exe launcher.py`
4. 正常啟動

### 影響範圍
- 部署和啟動流程
- 嚴重度: **低**（有 workaround）

### 根因分析
**已確認根因**:
- 系統 Python 與專案 venv 分離
- launcher.py 使用 `sys.executable`，可能指向錯誤 Python

**建議修復方向**:
1. 在 launcher.py 中明確指定使用 .venv Python
2. 或在文件中标註正確啟動方式

---

## BUG-009: Phase A 未實際測試

### 問題現象
- Phase A 架構已建立，但未在實際瀏覽器中驗證
- 需伺服器啟動後才能測試

### 影響範圍
- 新功能驗證
- 嚴重度: **低**（架構完成，待測試）

### 建議修復方向
1. 啟動伺服器
2. 開啟瀏覽器
3. 執行驗證腳本
4. 確認 SVG 渲染和 Insert Points 可視化

---

## BUG-010: 備份目錄過多

### 問題現象
- 專案根目錄有多個備份目錄
- 可能混淆正式檔案與備份

### 影響範圍
- 專案整潔性
- 嚴重度: **低**

### 建議修復方向
1. 建立 `_archived_backups/` 目錄
2. 將舊備份移入
3. 保留最近 3 個備份

---

## 問題優先次序

| 編號 | 問題 | 嚴重度 | 優先級 | 建議處理 |
|------|------|--------|--------|----------|
| BUG-002 | 音符無法任意插入 | 高 | P1 | 需 Schema 變更 |
| BUG-003 | 歌詞無法任意插入 | 高 | P1 | 需 Schema 變更 |
| BUG-004 | 和弦無法任意插入 | 高 | P1 | 需 Schema 變更 |
| BUG-005 | 事件無法移動 | 高 | P2 | 需實作拖曳 |
| BUG-001 | 和弦圖無法顯示 | 中 | P2 | 可恢復 SVG |
| BUG-006 | Timeline 混用風險 | 中 | P3 | 需清理程式碼 |
| BUG-007 | Event ID 不穩定 | 中 | P3 | 需修復 nextId() |
| BUG-008 | Server 啟動依賴 | 低 | P4 | 文件說明 |
| BUG-009 | Phase A 未測試 | 低 | P4 | 待驗證 |
| BUG-010 | 備份目錄過多 | 低 | P5 | 可整理 |
