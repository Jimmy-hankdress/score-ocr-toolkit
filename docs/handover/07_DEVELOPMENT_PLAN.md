# 後續開發計畫

## 一、優先次序

### P0: 驗證與準備（1-2 天）

**目標**: 確認 Phase A 功能正常，為後續開發奠定基礎

**任務**:
1. ✓ 伺服器啟動（已完成，PID 32376）
2. □ 瀏覽器驗證 Phase A 預覽功能
3. □ 確認 SVG 渲染正確
4. □ 確認 Insert Points 可視化
5. □ 記錄測試結果

**涉及檔案**:
- `web/assets/phase_a_integration.js`
- `web/assets/event_session.js`
- `web/index.html`

**完成定義**:
- Phase A preview container 正確顯示
- 39 個 SVG 小節渲染正確
- Insert Points 可見

**風險**:
- 低（架構已完成，僅需驗證）

---

### P1: Schema 決策（1 天）

**目標**: 決定如何解決 Legacy 格式限制

**選項**:

| 方案 | 說明 | 優點 | 缺點 |
|------|------|------|------|
| **A. 擴展 Legacy** | 新增 tick/duration 欄位 | 向後相容 | 需 migrat 既有資料 |
| **B. 雙格式儲存** | 同時存 Legacy + Event | 完整功能 | 複雜度高 |
| **C. 純 Event Model** | 完全改用 Event Model | 最靈活 | 需全面重寫 |

**建議**: **方案 A**（最小變更，向後相容）

**任務**:
1. 設計新欄位 (`noteTicks[]`, `chordOffsets[]`, `lyricTicks[]`)
2. 撰寫 migration 腳本
3. 更新 renderSola321Measure 支援新欄位
4. 更新 eventsToLegacy 寫回新欄位

**涉及檔案**:
- `app/models.py` (如需後端變更)
- `web/assets/app.js`
- `phase15/event_to_legacy.js`

**完成定義**:
- Schema 文檔完成
- Migration 腳本通過測試
- 新欄位可正確讀寫

**風險**:
- 中（需測試 backward compatibility）

---

### P2: 核心編輯功能（3-5 天）

**目標**: 實現任意位置插入、移動、刪除

**任務**:

#### 2.1 音符編輯
- [ ] 實作 click-to-insert（點擊空白處插入）
- [ ] 實作 drag-to-move（拖曳移動）
- [ ] 更新 noteText + noteTicks
- [ ] 更新 Event Model

#### 2.2 歌詞編輯
- [ ] 實作 click-to-insert
- [ ] 實作 drag-to-move
- [ ] 更新 lyricText + lyricTicks
- [ ] 更新 Event Model

#### 2.3 和弦編輯
- [ ] 恢復和弦圖顯示
- [ ] 實作 click-to-insert
- [ ] 實作 drag-to-move
- [ ] 更新 chordOffsets
- [ ] 整合和弦庫選取

**涉及檔案**:
- `web/assets/app.js` (主要修改)
- `web/assets/styles.css` (UI 樣式)
- `phase15/event_model.js` (可能需要調整)

**完成定義**:
- 可在任意 tick 插入音符
- 可拖曳移動音符
- 可刪除音符
- 歌詞、和弦同上

**風險**:
- 高（核心功能，需充分測試）

---

### P3: Save Gate 與持久化（2-3 天）

**目標**: 確保 Event 操作可安全寫入

**任務**:
1. [ ] 實作 Event → Legacy 轉換（增強版）
2. [ ] 實作 Legacy → Event 還原
3. [ ] 測試 round-trip 完整性
4. [ ] 實作 Save Gate（僅在明確 Save 時寫入）
5. [ ] 測試 Undo/Redo 與 Save 整合

**涉及檔案**:
- `phase15/event_to_legacy.js`
- `web/assets/app.js`
- `app/projects.py` (可能需調整)

**完成定義**:
- Save 後 Reload 資料一致
- Undo/Redo 在 Save 前後正確運作
- Event ID 穩定

**風險**:
- 中（轉換邏輯需謹慎實現）

---

### P4: 和弦圖與庫整合（1-2 天）

**目標**: 恢復和弦圖顯示與選取功能

**任務**:
1. [ ] 恢復 renderV3ChordSlots 的 SVG 輸出
2. [ ] 整合和弦庫選取器
3. [ ] 實作點擊選取和弦圖
4. [ ] 測試和弦更新

**涉及檔案**:
- `web/assets/app.js`
- `web/assets/chords/` (已有 332+136 SVG)

**完成定義**:
- 和弦旁顯示指法圖
- 點擊可選取和弦庫中的和弦
- 選取後更新樂譜

**風險**:
- 低（功能已部分實現，只需恢復）

---

### P5: 回歸測試與優化（2-3 天）

**目標**: 確保新功能不破壞既有功能

**任務**:
1. [ ] 執行所有 phase15 測試
2. [ ] 執行瀏覽器 UI 測試
3. [ ] 性能測試（39+ measures）
4. [ ] 記憶體洩漏檢查
5. [ ] 介面優化

**涉及檔案**:
- `phase15/*_test.js`
- `tools/test_regression.py`

**完成定義**:
- 所有測試通過
- 无明显性能問題
- 介面整潔

**風險**:
- 低（標準 QA 流程）

---

## 二、依賴關係

```
P0 (驗證) 
    ↓
P1 (Schema 決策)
    ↓
P2 (核心編輯) ←──┐
    ↓            │
P3 (Save Gate)  │
    ↓            │
P4 (和弦圖) ──────┘
    ↓
P5 (回歸測試)
```

## 三、資源需求

| 資源 | 需求 | 說明 |
|------|------|------|
| 時間 | 10-15 天 | 依優先次序 |
| 人力 | 1 人 | 全職開發 |
| 測試環境 | Chrome + FastAPI | 已有 |
| 測試資料 | Last Dance.pdf | 已有 |

## 四、風險與緩解

| 風險 | 影響 | 緩解措施 |
|------|------|----------|
| Schema 變更破壞既有資料 | 高 | 保留 backward compatibility |
| Event Model 轉換遺失資訊 | 高 | 充分測試 round-trip |
| 瀏覽器相容性問題 | 中 | 多瀏覽器測試 |
| 效能退化 | 中 | 性能監控 |

## 五、驗收標準

### 階段性驗收
- P0: Phase A 預覽功能正常
- P1: Schema 文檔完成，migration 測試通過
- P2: 可任意插入/移動/刪除事件
- P3: Save/Reload 資料一致
- P4: 和弦圖顯示正常
- P5: 所有測試通過

### 最終驗收
- [ ] 所有需求 REQ-001 ~ REQ-015 完成度 > 90%
- [ ] 所有已知問題 BUG-001 ~ BUG-010 已解決或標記為 wont-fix
- [ ] 使用者.acceptance testing 通過
- [ ] 文件完整且準確
