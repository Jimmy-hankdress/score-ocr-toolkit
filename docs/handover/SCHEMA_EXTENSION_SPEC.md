# Legacy Schema 擴展規格 — 支援任意位置編輯

## 版本
v3.06.00 (Schema v2)

## 目標
在**不破壞既有專案**前提下，為 `ScoreMeasure` 新增三個選擇性 tick 陣列欄位，使前端能表達「任意位置插入/移動/刪除」。

---

## 1. 新增欄位定義

### ScoreMeasure（後端 `app/models.py`）
```python
# 現有
chordOffsets: list[int] = field(default_factory=list)  # 已存在，和弦在第幾拍（token index）

# 新增 —— 皆為「以 tick 為單位」的絕對位置（480 ticks = 1 quarter note = 1 拍）
noteTicks: list[int] = field(default_factory=list)     # 第 i 個音符的 tick 位置
lyricTicks: list[int] = field(default_factory=list)    # 第 j 個歌詞音節的 tick 位置
chordTicks: list[int] = field(default_factory=list)    # 第 k 個和弦的 tick 位置（替代 chordOffsets）
```

| 欄位 | 單位 | 對應 | 兼容策略 |
|------|------|------|----------|
| `noteTicks[]` | tick (480/quarter) | `noteText` tokens | 缺失時：`[0, 480, 960...]` 推算 |
| `lyricTicks[]` | tick | `lyricText` syllables | 缺失時：`[0, 480, 960...]` 推算 |
| `chordTicks[]` | tick | `chordText` tokens | 缺失時：回退 `chordOffsets[i] * 480` |

### ScoreBeat（保留）
現有 `beat` (1-based)、`duration` 字串維持不變，供 OCR/MusicXML 用。

---

## 2. 序列化規則

### 寫入 (`to_dict`)
```python
# 只輸出非空陣列，避免污染舊檔
if self.noteTicks:   d["noteTicks"]   = list(self.noteTicks)
if self.lyricTicks:  d["lyricTicks"]  = list(self.lyricTicks)
if self.chordTicks:  d["chordTicks"]  = list(self.chordTicks)
```

### 讀取 (`from_dict`)
```python
self.noteTicks   = [int(x) for x in (d.get("noteTicks")   or [])]
self.lyricTicks  = [int(x) for x in (d.get("lyricTicks")  or [])]
self.chordTicks  = [int(x) for x in (d.get("chordTicks")  or [])]
# 兼容舊欄位
if not self.chordTicks and d.get("chordOffsets"):
    self.chordTicks = [int(x) * 480 for x in d["chordOffsets"]]
```

---

## 3. 邏輯約束

1. **長度一致性**
   - `len(noteTicks) == len(split_notes(noteText))`
   - `len(lyricTicks) == len(split_lyrics(lyricText))`
   - `len(chordTicks) == len(split_chords(chordText))`

2. **單調遞增**
   - 同小節內 tick 必須遞增（允許相同時值表達連音/和弦疊放）

3. **範圍**
   - 4/4 拍：`0 <= tick < 1920`（4 拍 × 480）
   - 未來擴展支援變拍：由 `timeSignature` 決定上限

4. **缺失時的預設行為**（向後相容）
   ```python
   def default_ticks(count: int, start: int = 0, step: int = 480) -> list[int]:
       return [start + i * step for i in range(count)]
   ```

---

## 4. Event Model 對應更新

### `phase15/event_model.js` → `legacyToEvents()`
```javascript
// 音符
var notes = String(m.noteText || '').split(/\s+/).filter(Boolean);
var noteTicks = (m.noteTicks || []).map(Number);
notes.forEach(function(tok, i) {
    var start = (noteTicks[i] != null ? noteTicks[i] : i * 480) / 480; // 轉回 beat
    // ... 建立 noteEvent
});

// 歌詞
var lyrics = String(m.lyricText || '').split(/\s+/).filter(Boolean);
var lyricTicks = (m.lyricTicks || []).map(Number);
lyrics.forEach(function(txt, j) {
    var start = (lyricTicks[j] != null ? lyricTicks[j] : j * 480) / 480;
    // ... 建立 lyricEvent
});

// 和弦
var chords = String(m.chordText || '').split(/\s+/).filter(Boolean);
var chordTicks = (m.chordTicks || m.chordOffsets || []).map(Number);
chords.forEach(function(txt, k) {
    var start = (chordTicks[k] != null ? chordTicks[k] : k * 480) / 480;
    // ... 建立 chordEvent
});
```

---

## 5. 前端渲染更新點

| 檔案 | 函數 | 修改內容 |
|------|------|----------|
| `web/assets/app.js` | `renderSola321Measure()` | 讀取 `noteTicks/lyricTicks/chordTicks` 計算 X 座標 |
| `web/assets/app.js` | `bindSola321Inputs()` | 插入/移動時更新對應 ticks 陣列 |
| `web/assets/app.js` | `collectV3ToDoc()` | 將編輯器狀態的 tick 寫回 doc |
| `phase15/event_to_legacy.js` | `eventsToLegacy()` | Event → Legacy 時輸出 tick 陣列 |

---

## 6. 遷移腳本規格

### `tools/migrate_schema_v2.py`
```python
#!/usr/bin/env python3
"""Schema v1 → v2 遷移：為所有專案補齊 noteTicks/lyricTicks/chordTicks"""
# 1. 掃描 data/projects/*/project.json
# 2. 讀取 ScoreDocument
# 3. 對每個 measure：
#    - 解析 noteText/lyricText/chordText token 數量
#    - 若缺 tick 陣列 → 用 default_ticks() 補齊
#    - 若有 chordOffsets 無 chordTicks → chordOffsets * 480
# 4. 原子寫回（先備份到 versions/）
# 5. 驗證：round-trip load → to_dict → from_dict → 比對
```

### 執行流程
```bash
# 1. 完整備份
cp -r D:\SheetMusicOMR_v3.00\data\projects D:\SheetMusicOMR_v3.00\_backup_v306_schema_$(date +%Y%m%d)

# 2. 執行遷移
python tools/migrate_schema_v2.py --dry-run   # 預覽
python tools/migrate_schema_v2.py --execute   # 實際執行

# 3. 驗證
python tools/verify_schema_v2.py
```

---

## 7. 測試矩陣

| 測試案例 | 預期結果 |
|----------|----------|
| 舊專案（無 tick 陣列）載入 | 自動補齊預設 ticks，渲染不變 |
| 新專案（有 tick 陣列）載入 | 精確對齊渲染 |
| 在 tick=720 插入音符 | `noteTicks` 插入 720，`noteText` 插入 token，重排序 |
| 拖曳音符從 tick=480 → 960 | `noteTicks[i]` 更新，`noteText` 重排序 |
| 刪除第 2 個歌詞音節 | `lyricTicks` 移除對應元素，`lyricText` 移除 token |
| 匯出 MusicXML | 使用 `beats`（由 `expand_beats()` 依 tick 重建） |
| Undo/Redo | tick 陣列隨 token 陣列同步快照 |

---

## 8. 風險與緩解

| 風險 | 等級 | 緩解 |
|------|------|------|
| 既有專案 `chordOffsets` 與新 `chordTicks` 不一致 | 中 | 讀取時優先用 `chordTicks`，缺才回退 `chordOffsets*480`；遷移腳本同步修正 |
| 前端編輯器未同步更新 tick 陣列 | 高 | `collectV3ToDoc()` 必須在每次編輯後重建所有三組 ticks |
| `expand_beats()` 邏輯與 tick 衝突 | 中 | `expand_beats()` 改為「若有 tick 陣列則依 tick 分配拍位，否則均勻分配」 |
| ID 不穩定（Event Model `seq`） | 中 | 另開 ticket（P3）改用 `m{mi}.note.{index}` 格式 |

---

## 9. 完成定義

- [ ] `app/models.py` 新增三欄位 + 序列化
- [ ] `phase15/event_model.js` 讀取新欄位
- [ ] `web/assets/app.js` 渲染/編輯/收集支援 tick
- [ ] `tools/migrate_schema_v2.py` 通過 80+ 專案遷移
- [ ] `tools/verify_schema_v2.py` round-trip 全綠
- [ ] 手動測試：插入/移動/刪除在任意 tick 位置正常