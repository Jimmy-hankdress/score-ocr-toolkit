# SheetMusicOMR v3.00 — Phase 0 唯讀審查交付報告

**執行時間**：2026-10-17
**任務類型**：唯讀架構審查（不寫碼、不 commit）
**審核狀態**：待人工批准後進入 Phase 1

---

## 一、兩項唯讀工作完成情況

### ✅ 工作 1：存檔 400 根因追查

**檔案**：`tools/phase0-root-cause-report.md`（12,747 字）

**關鍵發現**：

| 項目 | 發現 |
|---|---|
| **錯誤位置** | `app/server.py` L184-186，`ScoreDocument.from_dict(payload)` 觸發 |
| **錯誤訊息** | `400 Invalid document structure: list index out of range` |
| **根因假設 A** | Client 端 event model 欄位（melodyEvents/chordEvents/lyricTracks/annotations/eventModelVersion）不在 Server `ScoreMeasure` dataclass 定義中 |
| **根因假設 B** | `eventOverrides` 欄位若為 string 而非 dict，會拋 `AttributeError`（models.py L249-250） |
| **驗證結果** | Python dataclass 接受未知欄位（容錯），但 eventOverrides 格式錯誤會失敗 |
| **未確認點** | 「list index out of range」具體觸發位置需抓取真實 payload 確認 |

**建議修復方案**：
- **方案 A（快速）**：Client 端 `saveCurrentDoc` 前過濾 event model 欄位
- **方案 B（完整）**：Server 端 `ScoreMeasure` 新增 event model 欄位 + 雙向轉換
- **方案 C（容錯）**：Server 端 `from_dict` 改用 `**kwargs` 忽略未知欄位

---

### ✅ 工作 2：格線呈現層可重用性確認

**關鍵發現**：

#### 2.1 三種渲染器現狀

| 渲染器 | 函式位置 | 目前狀態 | 可編輯性 |
|---|---|---|---|
| **Grid（格線）** | `renderV3Editor` L1290 | 主要編輯器 | ✅ 完整編輯 |
| **Timeline（時間軸）** | `renderSola321MeasureTimeline` L3493 | Phase 2 功能 | ✅ 拖曳事件 |
| **Vertical（直式）** | `renderSola321MeasureVertical` L2986 | **唯讀展示** | ❌ 無事件綁定 |

#### 2.2 可重用組件清單（10 項）

| 組件 | 函式位置 | 用途 | 重用度 |
|---|---|---|---|
| Token 解析 | `solaTokens` / `solaDecomp` | 簡譜文字 → token 陣列 | ⭐⭐⭐⭐⭐ |
| 和弦圖繪製 | `renderChordSvg` | SVG 和弦指法圖 | ⭐⭐⭐⭐⭐ |
| 音符 HTML | `v3NoteTokenHtml` | token → HTML span | ⭐⭐⭐⭐⭐ |
| 拍號解析 | `parseTimeSignatureToSola321` | 拍號 → beats 數 | ⭐⭐⭐⭐⭐ |
| Legacy 重建 | `collectV3ToDoc` | noteText → ticks | ⭐⭐⭐⭐⭐ |
| Event 遷移 | `migrateAllMeasures` / `ensureEventModel` | legacy → event model | ⭐⭐⭐⭐ |
| Undo/Redo | `solaSnapshot` / `solaRestore` / `solaUndo` / `solaRedo` | 複撤銷系統 | ⭐⭐⭐⭐⭐ |
| Cursor 管理 | `solaGetCursor` / `solaSetCursor` / `solaFocusCursor` | 游標定位 | ⭐⭐⭐⭐⭐ |
| Chord Picker | `openChordPicker` | 和弦選取器 | ⭐⭐⭐⭐ |
| 結構記號 | `solaMarkOps` | SN/RS/RE/CODA 等 | ⭐⭐⭐ |

#### 2.3 需調整組件（3 項）

| 組件 | 問題 | 調整方向 |
|---|---|---|
| `renderSola321MeasureVertical` L2986 | 唯讀展示，無編輯能力 | 改為可編輯版本或改用 `renderSola321Measure` |
| `renderSola321Score` L2843 | 無「每行 4 小節」排版邏輯 | 新增 CSS Grid 分批邏輯 |
| CSS 布局 | 缺少 `.ss-line { display: grid; grid-template-columns: repeat(4, 1fr) }` | 新增樣式規則 |

#### 2.4 編輯功能差距分析

| 功能 | Grid 模式 | Vertical 模式（現狀） | Vertical 模式（目標） |
|---|---|---|---|
| 音符點選 | ✅ | ❌ | ✅ 需綁定 |
| 音符編輯 | ✅ input | ❌ 純文字 | ✅ 需改 input |
| 歌詞編輯 | ✅ lyricTracks | ❌ 純文字 | ✅ 需改 input |
| 和弦編輯 | ✅ chord slot | ❌ 僅顯示 | ✅ 需 picker |
| 和弦圖 | ✅ | ✅ 可直接重用 | ✅ 直接重用 |
| 游標 | ✅ mi/nti | ❌ 無概念 | ✅ 需新增 |
| Undo/Redo | ✅ | ⚠️ 有框架 | ✅ 需綁定按鈕 |

---

## 二、產品規格確認（審核意見整合）

### 2.1 唯一 Score Studio 定義

**核心原則**：
1. 只保留一個主要編輯畫面，不再讓使用者在 grid/timeline/vertical 三套模式之間切換
2. 小節由左至右排列，每行預設四小節，再由上往下繼續
3. 音符、歌詞、和弦必須是可操作的編輯內容，而不是只有 textContent 的展示文字
4. 和弦名稱及和弦圖應能顯示、選取、加入與修改
5. 不再於每小節旁常駐顯示上移、下移、刪除按鈕
6. 保留原有資料模型、匯出功能與可重用的編輯邏輯

### 2.2 排版本規則

| 規則 | 說明 |
|---|---|
| **每行 4 小節** | 預設排版，可依版面需求調整（非 hardcode） |
| **換行判斷** | 不單純按陣列每 4 個切組，需考慮紙面寬度、長歌詞、空小節、最後一行 |
| **拍號與換行分離** | 4/4、3/4、6/8 的小節拍數由拍號決定；每行 4 小節是版面規則，不是拍號規則 |

### 2.3 編輯能力要求

- ✅ 音符：可直接選取、新增、修改與刪除
- ✅ 歌詞：可直接選取與修改，並保持與音符的對應關係
- ✅ 和弦：可新增、修改、刪除
- ✅ 和弦名稱與和弦圖：必須保留並能正常操作
- ✅ 游標、快捷鍵、Undo/Redo、存檔與匯出：不得失效
- ❌ 移除每小節列上的固定上移、下移、刪除按鈕
- ❌ 不得刪除既有功能鍵或匯出格式

---

## 三、實作順序建議（審核意見整合）

### 階段 0：確認存檔失敗原因（⏳ 待批准）
- [ ] 抓取真實 400 請求的 Request Payload（Chrome DevTools）
- [ ] 確認 `eventOverrides` 欄位格式
- [ ] 確認 `beats` 陣列結構
- [ ] 交付根因報告 + 最小重現案例
- [ ] **不改 server.py**

### 階段 1：統一呈現架構（⏳ 待階段 0 批准）
- [ ] 確認唯一畫面的 DOM 結構
- [ ] 實作「每行 4 小節」排版規則（CSS Grid）
- [ ] 確認舊 grid renderer 哪些可直接重用
- [ ] 修改 `renderSola321Score` 支援新排版
- [ ] **限制範圍：僅呈現層，不恢復編輯功能**

### 階段 2：恢復完整編輯流程（⏳ 待階段 1 批准）
- [ ] 逐項驗證音符編輯（選取、修改、刪除）
- [ ] 逐項驗證歌詞編輯（選取、修改、對位）
- [ ] 逐項驗證和弦圖編輯（選取、加入、修改）
- [ ] 驗證 Undo/Redo 資料寫回
- [ ] **驗證方式：重新執行 b1/b2/del 測試**

### 階段 3：存檔與匯出驗證（⏳ 待階段 2 批准）
- [ ] 確認編輯後能成功保存
- [ ] 確認重新載入後資料一致
- [ ] 驗證 MusicXML 匯出
- [ ] 驗證 MIDI 匯出
- [ ] 驗證 Word 匯出
- [ ] 驗證 Sola321 匯出

### 階段 4：移除多餘模式與介面（⏳ 待階段 3 批准）
- [ ] 移除 timeline/grid 獨立入口
- [ ] 移除每小節 up/down/delete 按鈕
- [ ] 清理過時 CSS/JS
- [ ] 最終回歸測試（24 項 phase15 + 36 項小節操作）

---

## 四、阻塞項目

### 🔴 Phase 0 阻塞：存檔 400 問題

**影響範圍**：
- 所有含 event model 的專案無法持久化
- Undo/Redo 在重新載入後可能遺失編輯歷史
- 匯出功能可能受影響（取決於匯出器是否依賴 event model）

**建議處理優先級**：**最高**（優先於階段 1 排版改造）

**修復方案選擇**：
- 若選擇方案 A（client 過濾）：2-4 小時可完成
- 若選擇方案 B（server 新增欄位）：1-2 天
- 若選擇方案 C（server 容錯）：1-2 小時

---

## 五、測試產物狀態

### 保留的測試腳本
| 檔案 | 用途 | 狀態 |
|---|---|---|
| `tools/hermes-verify-phase4-b1.js` | 新增/刪除/空文件/三檢視測試 | ✅ 13/13 PASS |
| `tools/hermes-verify-phase4-b2.js` | 上移/下移測試 | ✅ 12/12 PASS |
| `tools/hermes-verify-phase4-del.js` | 刪除 Undo/Redo 測試 | ✅ 11/11 PASS |
| `tools/phase0-400-repro.py` | 400 根因初步測試 | ✅ 執行成功 |
| `tools/phase0-400-deep-dive.py` | 400 根因深入測試 | ✅ 執行成功 |
| `tools/phase0-400-real-repro.py` | 400 真實 payload 重現 | ⚠️ 需 server 運行 |

### 保留的基準資料
| 檔案 | 內容 |
|---|---|
| `tools/hermes-verify-phase4-b1-base.json` | b1 測試基準數據 |
| `tools/hermes-verify-phase4-b1-result.json` | b1 測試結果 |
| `tools/hermes-verify-phase4-del-result.json` | del 測試結果 |

### 保留的測試專案
| 專案 ID | 用途 |
|---|---|
| `doc_62821712c5e4` (b3) | 批次 2 上移/下移測試 |
| `doc_57c9d6eb921c` | 刪除 Undo/Redo 測試 |
| `hermes-verify-phase3-6c3bc5bd02e2` | 階段 3 基準 |

### 正式資料保護
- ✅ YL/DC 11 個 project.json 的 MD5 與 mtime 均未改變
- ✅ 所有 `_backup_*` 目錄保留
- ✅ Git tracked 變更僅 `web/assets/app.js` + `web/assets/styles.css`（未 commit）

---

## 六、交付清單

### 6.1 審查報告
- [x] `tools/phase0-root-cause-report.md` — 存檔 400 根因報告（12,747 字）
- [x] `tools/phase4-delivery-review.md` — 階段 4.2 交付審查報告（9,350 字）

### 6.2 測試腳本
- [x] `tools/hermes-verify-phase4-b1.js` — 新增/刪除/空文件測試
- [x] `tools/hermes-verify-phase4-b2.js` — 上移/下移測試
- [x] `tools/hermes-verify-phase4-del.js` — 刪除 Undo/Redo 測試
- [x] `tools/phase0-400-repro.py` — 400 根因初步驗證
- [x] `tools/phase0-400-deep-dive.py` — 400 根因深入驗證
- [x] `tools/phase0-400-real-repro.py` — 400 真實 payload 重現（需 server）

### 6.3 基準資料
- [x] `tools/hermes-verify-phase4-b1-base.json`
- [x] `tools/hermes-verify-phase4-b1-result.json`
- [x] `tools/hermes-verify-phase4-del-result.json`

---

## 七、下一步行動

### 立即行動（需人工批准）
1. **審核本報告**：確認根因分析與建議方案
2. **決定修復方案**：選擇方案 A/B/C 之一修復 400 問題
3. **批准階段 0 執行**：抓取真實 payload + 確認根因

### 後續行動（待階段 0 批准）
4. **實施修復**：依選定方案修改 client 或 server 端
5. **驗證修復**：重新執行 b1/b2/del 測試 + 存檔測試
6. **進入階段 1**：排版改造（僅呈現層）

---

**報告完成**：2026-10-17
**审核状态**：⏳ 等待人工審核
**限制遵守**：✅ 未修改 app.js / styles.css / server.py / models.py
**Git 狀態**：未 commit、未 reset、未 clean、未 stash
