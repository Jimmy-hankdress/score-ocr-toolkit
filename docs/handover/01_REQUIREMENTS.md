# 需求清單與驗收標準

## 需求總覽

| 編號 | 需求 | 狀態 | 完成度 |
|------|------|------|--------|
| REQ-001 | 簡譜音符編輯 | ⚠️ 部分完成 | 40% |
| REQ-002 | 歌詞逐音節編輯 | ⚠️ 部分完成 | 30% |
| REQ-003 | 和弦名稱編輯 | ✓ 已完成 | 90% |
| REQ-004 | 和弦圖顯示 | ✗ 未完成 | 10% |
| REQ-005 | 獨立時間軸定位 | ✗ 未完成 | 0% |
| REQ-006 | 任意位置插入事件 | ✗ 未完成 | 0% |
| REQ-007 | 事件移動/刪除 | ⚠️ 部分完成 | 20% |
| REQ-008 | Undo/Redo | ✓ 已完成 | 80% |
| REQ-009 | 儲存/重新載入 | ✓ 已完成 | 85% |
| REQ-010 | PDF 匯出 | ✓ 已完成 | 70% |
| REQ-011 | OMR 匯入 | ✓ 已完成 | 75% |
| REQ-012 | 多段歌詞 | ⚠️ 部分完成 | 50% |
| REQ-013 | 和弦位置編輯 | ✗ 未完成 | 10% |
| REQ-014 | 節拍/時值編輯 | ⚠️ 部分完成 | 60% |
| REQ-015 | 小節線編輯 | ✓ 已完成 | 80% |

---

## 詳細需求清單

### REQ-001: 簡譜音符編輯

**需求描述**: 使用者可在簡譜中新增、修改、刪除音符，支援數字 0-7、附點、高低八度點、升降記號。

**來源**: 使用者需求 + Legacy renderer 既有功能

**目前狀態**: ⚠️ 部分完成

**完成項目**:
- ✓ 音符顯示 (renderSola321Measure)
- ✓ 音符點擊進入 Active Note 模式
- ✓ 音符輸入 overlay
- ✓ 時值選擇 (全/二分/四分/八分...)
- ✓ 附點/三連音/升降記號按鈕
- ✓ Undo/Redo

**未完成項目**:
- ✗ 無法在任意 tick 位置插入音符
- ✗ 無法移動音符到不同位置
- ✗ 無法自由刪除音符（只能清空）
- ✗ 音符座標以 token index 為主，非 tick

**對應檔案**:
- `web/assets/app.js` L2670-2840 (renderSola321Measure)
- `web/assets/app.js` L3040-3100 (bindSola321Inputs)
- `web/assets/app.js` L2330-2360 (solaPushUndo/solaUndo)

**驗收方法**:
1. 開啟 Last Dance 專案
2. 點擊任意音符，應彈出 Active Note overlay
3. 輸入數字，按 Enter，音符應更新
4. 按 Ctrl+Z，應復原

**實際測試結果**: 
- 點擊音符 → ✓ 彈出 overlay
- 輸入數字 → ✓ 更新顯示
- Ctrl+Z → ✓ 復原
- 插入新音符到空白位置 → ✗ 失敗（只能追加到末尾）
- 移動音符位置 → ✗ 失敗（無此功能）

---

### REQ-002: 歌詞逐音節編輯

**需求描述**: 使用者可編輯歌詞，支援多段歌詞、空白歌詞段落、音節對齊。

**來源**: 使用者需求 + Legacy renderer 既有功能

**目前狀態**: ⚠️ 部分完成

**完成項目**:
- ✓ 歌詞顯示 (lyricText/lyricText2/3/4)
- ✓ 歌詞字元點擊編輯
- ✓ 最多 4 段歌詞
- ✓ overlay input 編輯

**未完成項目**:
- ✗ 無法在任意 tick 插入歌詞
- ✗ 歌詞與音符的對齊依賴 token index，非時間位置
- ✗ 無法自由移動歌詞位置
- ✗ 無法刪除特定歌詞音節（只能清空整行）

**對應檔案**:
- `web/assets/app.js` L2800-2830 (render lyric rows)
- `web/assets/app.js` L3170-3200 (bind lyric inputs)
- `web/assets/app.js` L3100-3170 (openSolaLyricOverlay)

**驗收方法**:
1. 點擊歌詞字元，應彈出 input overlay
2. 輸入文字，按 Enter，歌詞應更新
3. 切換到 lyricText2，應顯示第二段落詞

**實際測試結果**:
- 點擊歌詞 → ✓ 彈出 overlay
- 輸入文字 → ✓ 更新顯示
- 切換段落 → ✓ 正常
- 插入新歌詞到空白位置 → ✗ 失敗

---

### REQ-003: 和弦名稱編輯

**需求描述**: 使用者可新增、修改、刪除和弦名稱，和弦顯示在音符上方。

**來源**: 使用者需求 + Legacy renderer 既有功能

**目前狀態**: ✓ 基本完成

**完成項目**:
- ✓ 和弦顯示 (chordText)
- ✓ 和弦名稱編輯
- ✓ chordOffsets 支援（位置對齊）
- ✓ 和弦刪除

**未完成項目**:
- ✗ 和弦圖 (SVG diagram) 未在正文顯示
- ✗ 和弦庫選取功能未完全整合
- ✗ 無法在任意 tick 插入和弦

**對應檔案**:
- `web/assets/app.js` L100-200 (chord rendering)
- `web/assets/app.js` L430-540 (bindChordSlotPickers)
- `web/assets/app.js` L2690 (renderV3ChordSlots)

**驗收方法**:
1. 開啟專案，檢查和弦是否顯示
2. 點擊和弦，應可編輯
3. 刪除和弦，應移除

**實際測試結果**:
- 和弦顯示 → ✓ 正常
- 和弦編輯 → ✓ 部分（需透過 v3-chord-slot）
- 和弦刪除 → ✓ 正常

---

### REQ-004: 和弦圖顯示

**需求描述**: 和弦庫應提供和弦指法圖（SVG），使用者可選取並套用到樂譜。

**來源**: 使用者需求

**目前狀態**: ✗ 未完成

**問題**:
- 和弦圖 SVG 檔案存在於 `web/assets/chords/` (guitar/ukulele)
- 但 renderV3ChordSlots 目前只輸出純文字
- 和弦庫選取功能未整合到主編輯器

**對應檔案**:
- `web/assets/app.js` L73-97 (renderChordSvg)
- `web/assets/chords/guitar/` (332 個 SVG)
- `web/assets/chords/ukulele/` (136 個 SVG)

**建議修復**:
1. 恢復 renderV3ChordSlots 的 SVG 輸出
2. 整合和弦庫選取器
3. 確保和弦圖可點擊選取

---

### REQ-005: 獨立時間軸定位

**需求描述**: 音符、歌詞、和弦應有獨立的時間軸定位（tick），可精確控制每個事件的時間位置。

**來源**: Architecture Audit 發現的核心需求

**目前狀態**: ✗ 未完成

**問題**:
- Legacy 格式使用 token 序列 (noteText/chordText/lyricText)
- 無 tick 座標欄位
- Event Model 有 tick，但無法寫回 Legacy

**Event Model 現況** (phase15/event_model.js):
```javascript
{
  id: 'ev-note-001',
  type: 'note',
  start: 0,        // tick 位置
  duration: 1,     // 時值（拍數）
  pitch: '1',      // 音高
  octave: null,    // 八度偏移
  accidental: null // 升降記號
}
```

**Legacy 格式現況**:
```javascript
{
  noteText: '1 2 3 4',  // 空格分隔的 token 序列
  chordText: 'C G Am',  // 空格分隔的和弦
  lyricText: '我 愛 你' // 空格分隔的歌詞
}
```

**關鍵限制**:
- Legacy 無 tick 欄位
- 位置由 array index 隱式決定
- 無法表達「在第 2.5 拍插入音符」

**對應檔案**:
- `phase15/event_model.js` — Event Model 定義
- `phase15/layout_engine.js` — tick → X 轉換
- `web/assets/app.js` L2038-2110 — ensureEventModel / parseMeasureToEvents

**建議方案**:
1. **短期**: 限制編輯到現有 token 位置（不可任意插入）
2. **中期**: 擴展 Legacy schema 新增 tick 欄位
3. **長期**: 全面改用 Event Model 儲存

---

### REQ-006: 任意位置插入事件

**需求描述**: 使用者可點擊時間軸空白處，在任意 tick 位置插入新事件。

**目前狀態**: ✗ 未完成

**問題**:
- Legacy renderer 只能追加到 noteText/chordText/lyricText 末尾
- 無「空白位置」概念
- Insert Points 僅可視化（Phase A），不可點擊

**對應檔案**:
- `web/assets/phase_a_integration.js` — Insert Points 可視化
- `phase15/svg_renderer.js` L181-202 — renderInserts()

**建議實現**:
1. 在 Legacy renderer 產生可點擊的空白區域
2. 計算點擊位置的 tick
3. 在正確位置插入 event
4. 重新排序 token 序列

---

### REQ-007: 事件移動/刪除

**需求描述**: 使用者可拖曳移動事件，或選取後刪除。

**目前狀態**: ⚠️ 部分完成

**完成項目**:
- ✓ 音符刪除（清空 token）
- ✓ 和弦刪除（移除 slot）
- ✓ 歌詞刪除（清空字元）

**未完成項目**:
- ✗ 音符移動（無拖曳功能）
- ✗ 和弦移動（無拖曳功能）
- ✗ 歌詞移動（無拖曳功能）
- ✗ 選取後批量操作

**對應檔案**:
- `web/assets/app.js` L3066-3082 (chord delete binder)
- `web/assets/app.js` L3084-3099 (note add binder)

---

### REQ-008: Undo/Redo

**需求描述**: 使用者的編輯操作應可復原/重做。

**目前狀態**: ✓ 基本完成

**完成項目**:
- ✓ solaEdit.undoStack / redoStack
- ✓ solaPushUndo() 推入快照
- ✓ solaUndo() / solaRedo() 執行操作
- ✓ Ctrl+Z / Ctrl+Y 快捷鍵

**限制**:
- 僅記錄 Legacy doc state
- 不記錄 Event operations
- 重新載入後 undo stack 清空

**對應檔案**:
- `web/assets/app.js` L1554 (solaEdit initialization)
- `web/assets/app.js` L2333-2360 (undo/redo functions)

**驗收方法**:
1. 編輯音符 → 按 Ctrl+Z → 應復原

**實際測試結果**: ✓ 通過

---

### REQ-009: 儲存/重新載入

**需求描述**: 使用者可儲存專案，重新載入後資料一致。

**目前狀態**: ✓ 基本完成

**完成項目**:
- ✓ PUT /api/projects/{id} 儲存
- ✓ GET /api/projects/{id} 載入
- ✓ project.json 持久化
- ✓ atomic backup (versions/)

**限制**:
- Event Model 修改不會寫入 project.json
- 重新載入後 Event Model 重建（非持久化）

**對應檔案**:
- `app/projects.py` — 專案 CRUD
- `app/scorestudio/score_document_service.py` — 文件服務

**驗收方法**:
1. 編輯樂譜 → 點擊保存 → 重新載入 → 資料應一致

**實際測試結果**: ✓ 通過（Legacy 資料）

---

### REQ-010: PDF 匯出

**需求描述**: 使用者可匯出 PDF 格式的樂譜。

**目前狀態**: ✓ 完成

**完成項目**:
- ✓ PDF 匯出功能
- ✓ 使用 PyMuPDF 渲染

**對應檔案**:
- `app/formats/` — 匯出格式模組
- `web/assets/app.js` — 匯出按鈕

**驗收方法**:
1. 點擊「匯出」→ PDF
2. 檢查匯出檔案

**實際測試結果**: ✓ 通過

---

### REQ-011: OMR 匯入

**需求描述**: 使用者可上傳 PDF/圖片，系統自動辨識生成樂譜。

**目前狀態**: ✓ 完成

**完成項目**:
- ✓ PDF/圖片上傳
- ✓ Tesseract OCR 辨識
- ✓ 簡譜幾何分析
- ✓ 生成 Legacy doc

**支援引擎**:
- scoreforge (整譜+和弦+歌詞)
- jianpu2 (逐頁幾何分析)
- jpeditor (MusicXML 直連)
- orpheus (CNN 純簡譜)

**對應檔案**:
- `app/omr/` — OMR 引擎
- `web/assets/app.js` — 上傳 UI

**驗收方法**:
1. 上傳 Last Dance.pdf
2. 檢查辨識結果

**實際測試結果**: ✓ 通過

---

## 未完成需求總結

| 需求 | 狀態 | 阻塞原因 |
|------|------|----------|
| REQ-004 和弦圖顯示 | ✗ | renderV3ChordSlots 已改為純文字 |
| REQ-005 獨立時間軸定位 | ✗ | Legacy 格式無 tick 欄位 |
| REQ-006 任意位置插入 | ✗ | 同上 + 無 click handler |
| REQ-007 事件移動 | ✗ | 無拖曳功能 |
| REQ-013 和弦位置編輯 | ✗ | chordOffsets 未整合 |

**核心問題**: Legacy 格式限制，需 Schema 變更才能完整實現自由編輯。
