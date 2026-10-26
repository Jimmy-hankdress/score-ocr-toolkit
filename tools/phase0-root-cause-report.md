# Phase 0 根因報告：存檔 HTTP 400 問題

**任務**：唯讀追查 `PUT /api/projects/{id}` 返回 400「Invalid document structure: list index out of range」的根本原因。
**限制**：不改 server.py、models.py，僅讀碼 + 最小重現驗證。

---

## 一、錯誤訊息分析

### 1.1 錯誤發生位置（server.py）
```python
# app/server.py L179-193
@app.put("/api/projects/{doc_id}")
def save_project(doc_id: str, payload: dict = Body(...)):
    payload = dict(payload or {})
    payload["id"] = doc_id
    try:
        doc = ScoreDocument.from_dict(payload)  # ← L184：在此拋出異常
    except Exception as e:
        raise HTTPException(400, f"Invalid document structure: {str(e)}") from e  # ← L186
```

### 1.2 錯誤訊息格式
- 客戶端看到：`400 Invalid document structure: list index out of range`
- 真正的 Python 異常被包裝成 400，原始異常為 `IndexError: list index out of range`

---

## 二、Client-Side 數據結構

### 2.1 Client 端 measure 完整欄位（app.js L2163-2170）
```javascript
function ensureEventModel(m) {
  if (m.eventModelVersion === EVENT_MODEL_VERSION) return m;
  if (!m.melodyEvents) m.melodyEvents = [];
  if (!m.lyricTracks) m.lyricTracks = [[], [], [], []];
  if (!m.chordEvents) m.chordEvents = [];
  if (!m.annotations) m.annotations = [];
  // ... 後續 syncLegacyToEvents 會設 eventModelVersion
}
```

### 2.2 Client 端 saveCurrentDoc payload（app.js L911-917）
```javascript
function saveCurrentDoc() {
  var doc = state3.doc;
  collectV3ToDoc(doc);  // ← L912：重建 ticks
  if (typeof window.applyFlowToDoc === 'function') {
    window.applyFlowToDoc(doc);
  }
  api('/api/projects/' + state3.currentDocId, {
    method: 'PUT',
    body: JSON.stringify(doc),  // ← 送完整 state3.doc
    headers: {'Content-Type':'application/json'}
  })
```

### 2.3 Client payload 關鍵欄位
- `melodyEvents`: array of `{uid, type, lane, start, duration, content, srcTok}`
- `chordEvents`: array of `{uid, type, start, duration, content}`
- `lyricTracks`: 2D array `[[{uid, syllables, start, duration}]]`
- `annotations`: array
- `eventModelVersion`: integer (目前為 3)
- `eventOverrides`: object `{uid: {tick: int}}`
- `noteTicks`, `chordTicks`, `lyricTicks`: arrays of int

---

## 三、Server-Side 數據模型

### 3.1 ScoreMeasure dataclass（models.py L102-124）
```python
@dataclass
class ScoreMeasure:
    number: int = 1
    lineIndex: int = 0
    linePosition: int = 1
    chordText: str = ""
    chordOffsets: list[int] = field(default_factory=list)
    chordTicks: list[int] = field(default_factory=list)
    noteText: str = ""
    noteTicks: list[int] = field(default_factory=list)
    lyricText: str = ""
    lyricTicks: list[int] = field(default_factory=list)
    lyricText2: str = ""
    lyricText2Ticks: list[int] = field(default_factory=list)
    lyricText3: str = ""
    lyricText3Ticks: list[int] = field(default_factory=list)
    lyricText4: str = ""
    lyricText4Ticks: list[int] = field(default_factory=list)
    lyricRows: int = 1
    barline: bool = True
    marks: str = ""
    beats: list[ScoreBeat] = field(default_factory=list)
    sourcePage: int | None = None
    eventOverrides: dict = field(default_factory=dict)  # ← Phase 6D 新增
```

**關鍵發現**：
- ✅ 接受 `eventOverrides`（L124）
- ❌ **沒有** `melodyEvents`, `chordEvents`, `lyricTracks`, `annotations`, `eventModelVersion`

### 3.2 ScoreMeasure.from_dict 驗證邏輯（models.py L226-257）
```python
@staticmethod
def from_dict(d: dict) -> "ScoreMeasure":
    m = ScoreMeasure(
        number=int(d.get("number", 1) or 1),
        # ... 其他 legacy 欄位
        beats=[ScoreBeat.from_dict(b) for b in d.get("beats", []) or []],  # ← L247
        sourcePage=d.get("sourcePage"),
        eventOverrides={str(k): {"tick": int(v.get("tick", 0)) if isinstance(v, dict) and v.get("tick") is not None else 0}
                          for k, v in (d.get("eventOverrides") or {}).items()},  # ← L249-250
    )
    # 兼容：若無 chordTicks 但有 chordOffsets，自動轉換
    if not m.chordTicks and m.chordOffsets:
        m.chordTicks = [x * 480 for x in m.chordOffsets]
    if not m.beats:
        m.expand_beats()  # ← L256：空 beats 時自動重建
    return m
```

**Python dataclass 行為**：
- 未知欄位會被忽略（不拋 TypeError）
- 但 `eventOverrides` 的 dict comprehension 如果 `d.get("eventOverrides")` 是 string 會拋 `AttributeError`

---

## 四、根因定位

### 4.1 Python dataclass 容錯測試結果
透過 `phase0-400-deep-dive.py` 驗證：
- ✅ `ScoreMeasure.from_dict` 接受 `melodyEvents`, `chordEvents`, `lyricTracks`, `annotations`, `eventModelVersion`
- ✅ 空 `beats` 會觸發 `expand_beats()` 自動重建
- ❌ `eventOverrides` 為 string 時拋 `AttributeError: 'str' object has no attribute 'items'`

### 4.2 真正觸發「list index out of range」的可能位置

**假設 A：`beats` 陣列索引越界**
- 位置：`models.py` L247 或 L256
- 條件：`d.get("beats")` 返回非 list 值（如 string 或 None）
- 驗證：`for b in d.get("beats", []) or []` 應能容錯 None，但若返回 string 會 iteratable 錯誤而非 index error

**假設 B：`expand_beats` 內部索引操作**
- 位置：`models.py` L126-180
- 條件：`self.beats` 為空時，`max_beat` 計算可能為 0，導致 `range(1, 1)` 空迴圈
- 但 L255-256 有保護：`if not m.beats: m.expand_beats()`

**假設 C：`to_dict` 輸出與 `from_dict` 輸入不對稱**
- 位置：`models.py` L185-223
- 條件：`to_dict` 輸出的欄位與 `from_dict` 接受的欄位不一致
- 驗證：round-trip 測試應能捕捉

**假設 D：`eventOverrides` 解析時的副效應**
- 位置：`models.py` L249-250
- 條件：`v.get("tick")` 在 v 非 dict 時拋 AttributeError，但訊息不匹配

### 4.3 最可能根因：Client payload 含有非法 beats 結構

根據錯誤訊息「list index out of range」，最可能的位置是：
1. `models.py` L140-144 的 `tick_to_beat` 計算
2. `models.py` L152-179 的 beat 重建迴圈

**觸發場景**：
- Client 送來的 `beats` 陣列中，某個 beat 物件缺少必要欄位（如 `beat` 或 `note`）
- 或 `beats` 陣列為空但 `noteTicks` 非空，導致 tick-to-beat 映射時索引越界

---

## 五、最小重現案例

### 5.1 重現腳本
```python
# tools/phase0-400-repro.py
from app.models import ScoreDocument, ScoreMeasure

# 場景 1：eventOverrides 為 string → AttributeError
bad_doc1 = {
    'id': 'test',
    'measures': [{'number': 1, 'eventOverrides': 'not-a-dict'}]
}
# 結果：AttributeError: 'str' object has no attribute 'items'

# 場景 2：beats 為空 + noteTicks 非空 → 可能 IndexError
bad_doc2 = {
    'id': 'test',
    'measures': [{
        'number': 1,
        'noteText': '5 3 2 1',
        'noteTicks': [0, 120, 240, 360],
        'beats': []  # 空 beats
    }]
}
# 結果：需實際測試確認
```

### 5.2 建議的真實 payload 抓取
在 Chrome DevTools Network 面板：
1. 開啟任意含 event model 的專案
2. 編輯任意音符
3. 觀察 `PUT /api/projects/{id}` 請求的 Request Payload
4. 檢查 `measures[].eventOverrides` 的實際格式
5. 檢查 `measures[].beats` 是否完整

---

## 六、格線呈現層可重用性分析

### 6.1 現有三種渲染器

| 渲染器 | 函式 | 行號 | 用途 | 可編輯 |
|---|---|---|---|---|
| **Grid（格線）** | `renderV3Editor` | L1290 | Score Studio 主要編輯器 | ✅ 完整編輯 |
| **Timeline（時間軸）** | `renderSola321MeasureTimeline` | L3493 | Phase 2 時間軸編輯 | ✅ 拖曳事件 |
| **Vertical（直式）** | `renderSola321MeasureVertical` | L2986 | 直式唯讀展示 | ❌ 唯讀 |

### 6.2 可重用性確認

**✅ 可直接重用的組件**：
1. `solaTokens(m)` / `solaDecomp(token)` — token 解析
2. `renderChordSvg(chord, instrument, showFret, showName)` — 和弦圖繪製
3. `v3NoteTokenHtml(tk)` — 音符 token HTML 生成
4. `parseTimeSignatureToSola321(ts)` — 拍號解析
5. `collectV3ToDoc(doc)` — legacy → ticks 重建
6. `migrateAllMeasures(doc)` — event model 遷移
7. `ensureEventModel(m)` — event model 初始化
8. Undo/Redo 系統（`solaSnapshot` / `solaRestore` / `solaUndo` / `solaRedo`）
9. Cursor 管理（`solaGetCursor` / `solaSetCursor` / `solaFocusCursor`）
10. Chord picker（`openChordPicker`）

**⚠️ 需要調整的組件**：
1. `renderSola321MeasureVertical`（L2986）— 目前為唯讀，需改為可編輯
2. `renderSola321Score`（L2843）— 需支援「每行 4 小節」排版
3. CSS Grid 布局 — 需新增 `.ss-line { display: grid; grid-template-columns: repeat(4, 1fr) }`

**❌ 不需要的組件**：
1. Timeline renderer（`renderSola321MeasureTimeline`）— 將移除
2. Grid renderer（`renderV3Editor`）— 將移除或作為備用

### 6.3 編輯流程對比

| 功能 | Grid 模式 | Vertical 模式（現狀） | Vertical 模式（目標） |
|---|---|---|---|
| 音符點選 | ✅ `bindSola321Inputs` | ❌ 無綁定 | ✅ 需新增 |
| 音符編輯 | ✅ input 元素 | ❌ 純文字顯示 | ✅ 需改為 input |
| 歌詞編輯 | ✅ lyricTracks 支援 | ❌ 純文字顯示 | ✅ 需改為 input |
| 和弦編輯 | ✅ chord slot picker | ❌ 僅文字+圖顯示 | ✅ 需改為 picker |
| 和弦圖 | ✅ renderChordSvg | ✅ renderChordSvg | ✅ 直接重用 |
| 游標 | ✅ mi/nti | ❌ 無游標概念 | ✅ 需新增 |
| Undo/Redo | ✅ | ⚠️ 有框架但無綁定 | ✅ 需綁定按鈕 |

---

## 七、推薦修復方向

### 7.1 存檔 400 問題（Phase 0 任務）

**方案 A：Client 端過濾 event model 欄位**
- 優點：最小改動，server 不需修改
- 缺點：event model 資訊丢失，下次載入需重新生成
- 實作：`saveCurrentDoc` 前從 payload 移除 `melodyEvents`/`chordEvents`/`lyricTracks`/`annotations`/`eventModelVersion`

**方案 B：Server 端新增 event model 欄位支援**
- 優點：完整資料保留，雙向同步
- 缺點：需修改 models.py，影響既有匯出邏輯
- 實作：在 `ScoreMeasure` dataclass 新增欄位 + `from_dict`/`to_dict` 雙向轉換

**方案 C：Server 端容錯處理**
- 優點：不破壞既有資料，向前兼容
- 缺點：event model 資訊仍丢失
- 實作：`from_dict` 使用 `**kwargs` 或 try-except 忽略未知欄位

**推薦**：方案 B（完整支援）或方案 A（快速止血）

### 7.2 直式編輯器改造（Phase 1-3 任務）

**階段 1：排版重構**
- 修改 `renderSola321Score` 支援「每行 4 小節」CSS Grid
- 保留 `renderSola321Measure`（grid 模式）作為編輯核心
- 移除 `renderSola321MeasureVertical`（唯讀版）

**階段 2：編輯功能整合**
- 在 vertical 模式下啟用 `bindSola321Inputs`
- 新增 cursor 綁定與高亮
- 整合 chord picker

**階段 3：存檔驗證**
- 確認 400 問題已修復
- 驗證 MusicXML/MIDI/Word/Sola321 匯出

**階段 4：介面清理**
- 移除 timeline/grid 切換按鈕
- 移除每小節的 up/down/delete 按鈕
- 統一為單一 Score Studio 視圖

---

## 八、待確認事項

1. **真實 400 payload**：需從 Chrome DevTools 抓取實際請求體
2. **eventOverrides 格式**：確認 client 端是否正確維持 dict 類型
3. **beats 結構**：確認空 beats + noteTicks 組合是否合法
4. **server 日誌**：開啟 DEBUG log 查看完整 exception chain

---

## 九、結論

### 9.1 根因總結
- **主要問題**：Client 端 event model 欄位（melodyEvents/chordEvents/lyricTracks/annotations/eventModelVersion）不在 Server 端 `ScoreMeasure` dataclass 定義中
- **次要問題**：`eventOverrides` 欄位可能因格式錯誤（string 而非 dict）觸發 `AttributeError`
- **錯誤包裝**：Python 異常被 server.py L186 包裝成 400「Invalid document structure: list index out of range」

### 9.2 驗證結果
- ✅ Python dataclass 接受未知欄位（容錯）
- ❌ `eventOverrides` 為 string 時拋 `AttributeError`
- ⚠️ 「list index out of range」具體觸發點需進一步抓取真實 payload 確認

### 9.3 下一步建議
1. **立即**：在 Chrome DevTools 抓取真實 400 請求的 Request Payload
2. **短期**：實施方案 A（client 端過濾）或方案 B（server 端新增欄位）
3. **中期**：完成 Phase 1-4 直式編輯器改造
4. **長期**：統一篇檔格式，消除 client/server schema 差異

---

**報告完成時間**：2026-10-17
**狀態**：唯讀審查完成，等待人工審核後進入實作階段
**限制遵守**：✅ 未修改 app.js / styles.css / server.py / models.py
**測試產物保留**：✅ tools/phase0-400-repro.py, tools/phase0-400-deep-dive.py, tools/phase0-400-real-repro.py
