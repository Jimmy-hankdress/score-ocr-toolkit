# 目前功能狀態

## 一、功能矩陣

| 功能 | 實際狀態 | 程式位置 | 測試證據 | 未完成原因 |
|------|----------|----------|----------|------------|
| **新增音符** | ⚠️ 部分 | `app.js:L3091-3099` | 可追加到末尾 | 無法插入到任意位置 |
| **任意 tick 插入音符** | ✗ 未完成 | N/A | 無 | Legacy 格式無 tick |
| **新增歌詞** | ⚠️ 部分 | `app.js:L3185-3192` | 可新增行 | 無法插入到任意位置 |
| **任意 tick 插入歌詞** | ✗ 未完成 | N/A | 無 | Legacy 格式無 tick |
| **新增和弦** | ⚠️ 部分 | `app.js:L3056-3065` | 可新增槽 | 無法插入到任意位置 |
| **編輯和弦圖** | ✗ 未完成 | `app.js:L73-97` | SVG 存在但未整合 | renderV3ChordSlots 只輸出文字 |
| **刪除音符** | ✓ 基本 | `app.js:L3042-3047` | 可清空 token | 無法精確刪除單一字元 |
| **刪除歌詞** | ✓ 基本 | `app.js:L3172-3178` | 可清空字元 | 無法精確刪除單一字元 |
| **刪除和弦** | ✓ 完成 | `app.js:L3066-3082` | 可刪除槽 | - |
| **移動音符** | ✗ 未完成 | N/A | 無 | 無拖曳功能 |
| **移動歌詞** | ✗ 未完成 | N/A | 無 | 無拖曳功能 |
| **移動和弦** | ✗ 未完成 | N/A | 無 | 無拖曳功能 |
| **Undo** | ✓ 完成 | `app.js:L2344-2360` | Ctrl+Z 有效 | - |
| **Redo** | ✓ 完成 | `app.js:L2362+` | Ctrl+Y 有效 | - |
| **儲存** | ✓ 完成 | `app.js:L3326+` | PUT API 有效 | - |
| **重新載入** | ✓ 完成 | `app.js:L837+` | GET API 有效 | - |
| **PDF 匯出** | ✓ 完成 | `app/formats/` | 可匯出 | - |
| **MusicXML 匯出** | ✓ 完成 | `app/formats/musicxml.py` | 可匯出 | - |
| **MIDI 匯出** | ✓ 完成 | `app/formats/midi.py` | 可匯出 | - |
| **Word 匯出** | ✓ 完成 | `app/formats/word.py` | 可匯出 | - |
| **OMR 匯入** | ✓ 完成 | `app/omr/` | 可辨識 | - |
| **多段歌詞** | ✓ 完成 | `app.js:L2784-2830` | lyricText2-4 | - |
| **和弦位置調整** | ⚠️ 部分 | `chordOffsets` | 支援但未整合 | Event Model 未使用 |
| **節拍編輯** | ✓ 基本 | metadata input | 可修改 | - |
| **小節線編輯** | ✓ 完成 | barline 欄位 | 可開關 | - |
| **段落標記** | ✓ 完成 | marks 欄位 | 可新增/刪除 | - |

## 二、詳細狀態說明

### 2.1 音符編輯

**已完成**:
- ✓ 點擊音符進入 Active Note 模式
- ✓ overlay input 彈出
- ✓ 輸入數字更新音符
- ✓ 時值選擇 (A/S/D/F/G/H)
- ✓ 附點/三連音/升降記號
- ✓ Undo/Redo

**未完成**:
- ✗ 無法在空白位置插入新音符
- ✗ 無法移動音符到不同位置
- ✗ 無法精確刪除特定音符（只能清空整个 noteText）

**根因**: Legacy 格式以 token 序列儲存，無 tick 定位能力。

### 2.2 歌詞編輯

**已完成**:
- ✓ 點擊歌詞字元進入編輯
- ✓ overlay input 彈出
- ✓ 輸入文字更新歌詞
- ✓ 最多 4 段歌詞
- ✓ Undo/Redo

**未完成**:
- ✗ 無法在空白位置插入歌詞
- ✗ 無法移動歌詞到不同位置
- ✗ 無法精確刪除特定歌詞字元

**根因**: 同音符編輯。

### 2.3 和弦編輯

**已完成**:
- ✓ 和弦名稱顯示
- ✓ 和弦刪除
- ✓ chordOffsets 支援

**未完成**:
- ✗ 和弦圖 (SVG) 未在正文顯示
- ✗ 無法在空白位置插入和弦
- ✗ 無法移動和弦位置
- ✗ 和弦庫選取未整合

**根因**: renderV3ChordSlots 已改為純文字輸出；和弦圖功能未恢復。

### 2.4 Undo/Redo

**狀態**: ✓ 基本完成

**實現**:
- `solaEdit.undoStack` / `redoStack`
- `solaSnapshot()` 記錄完整 doc state
- `solaPushUndo()` 推入快照
- `solaUndo()` / `solaRedo()` 執行操作

**限制**:
- 僅記錄 Legacy doc，不記錄 Event operations
- 重新載入後 stack 清空

### 2.5 儲存/重新載入

**狀態**: ✓ 完成

**實現**:
- PUT /api/projects/{id} 儲存
- GET /api/projects/{id} 載入
- atomic backup 到 versions/

**限制**:
- Event Model 修改不會寫入 project.json
- 重新載入後 Event Model 重建

### 2.6 Phase A Event Session

**狀態**: ⚠️ 架構完成，待驗證

**已完成**:
- ✓ event_session.js 建立
- ✓ phase_a_integration.js 建立
- ✓ index.html 整合
- ✓ SVG Renderer 可渲染
- ✓ Insert Points 可視化

**未完成**:
- ✗ 未實際測試（伺服器啟動問題）
- ✗ 無編輯功能

## 三、Phase 完成度

| Phase | 名稱 | 狀態 | 完成度 |
|-------|------|------|--------|
| Phase 4 | Editor Core | ✓ 已完成 | 100% |
| Phase 1.5 | Event Model | ✓ 已完成 | 100% |
| Phase 2 | Layout Engine | ✓ 已完成 | 100% |
| Phase 3A | SVG Renderer | ✓ 已完成 | 100% |
| Phase 5 | Event→Legacy | ⚠️ 部分 | 60% |
| Phase 6 | Active Note | ✓ 已完成 | 90% |
| Phase 6B | Timeline | ⚠️ 已關閉 | 30% |
| Phase A | Event Preview | ⚠️ 新建 | 40% |

## 四、阻塞因素

### 技術阻塞
1. **Legacy 格式限制** — 無 tick 座標，無法精確定位
2. **Event Model 不持久化** — 重新載入後重建，ID 不穩定
3. **writeback 不安全** — Event → Legacy 轉換可能遺失資訊

### 資源阻塞
1. **伺服器啟動問題** — pydantic/docx 依賴需修復
2. **測試環境** — 需實際瀏覽器測試

### 決策阻塞
1. **Schema 變更** — 需決定是否擴展 Legacy 格式
2. **Phase A 驗證** — 需確認預覽功能是否正常

## 五、建議優先處理

1. **P0**: 驗證 Phase A 預覽功能（需先解決伺服器啟動）
2. **P1**: 決定 Legacy Schema 是否需擴展
3. **P2**: 若需擴展，設計新欄位 (tick, duration 等)
4. **P3**: 實作 Event Session 編輯功能
5. **P4**: 實作 Save Gate (Event → Legacy 轉換)
6. **P5**: 完整測試與整合
