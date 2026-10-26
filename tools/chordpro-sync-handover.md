# SheetMusicOMR v3.00 — ChordPro 雙向同步系統交接報告書

**版本**：v1.0
**日期**：2026-10-17
**狀態**：待審批 → 實施階段
**負責人**：原開發團隊 → 新接手團隊

---

## 一、執行摘要

### 1.1 專案背景

SheetMusicOMR v3.00 是一個本地化的樂譜數位化工具，核心功能包含：
- OMR（光学音符辨識）導入 PDF/影像檔
- ChordPro 文字編輯器（和弦+歌詞）
- Score Studio 簡譜編輯器（和弦+簡譜+歌詞三軌對齊）

**當前問題**：ChordPro 編輯器與 Score Studio 之間缺乏雙向同步機制，導致：
- 用戶在 ChordPro 編輯的文字無法自動轉換為 Score Studio 的 measures 結構
- Score Studio 的編輯結果無法反向生成 ChordPro 格式
- 兩種工作流孤立，用戶需手動複製貼上

### 1.2 解決方案：方案 C（雙向同步）

**目標**：建立完整的 ChordPro ↔ Score Studio 雙向轉換引擎，提供：
- 即時同步：一處編輯，另一處自動更新
- 衝突處理：偵測並提示兩端不一致
- 損耗最小化：保留結構化資訊（節拍、小節線、段落標記）

### 1.3 預期效益

| 指標 | 現狀 | 目標 |
|---|---|---|
| ChordPro → Score Studio 轉換成功率 | 0%（無法轉換） | ≥95%（基本格式） |
| Score Studio → ChordPro 還原成功率 | 60%（仅 metadata） | ≥90%（含和弦/歌詞） |
| 同步延遲 | N/A | <100ms（同頁籤） |
| 用戶操作步驟 | 手動複製貼上 | 自動同步 |

---

## 二、目前狀況詳細說明

### 2.1 現有架構概覽

```
┌─────────────────────────────────────────────────────────────────────┐
│                        SheetMusicOMR v3.00 架構                      │
├─────────────────────────────────────────────────────────────────────┤
│                                                                     │
│  ┌──────────────┐    ┌──────────────┐    ┌──────────────┐          │
│  │  ChordPro    │    │  Score       │    │  SoLa321     │          │
│  │  Editor      │    │  Studio      │    │  (Timeline)  │          │
│  │  (L90-109)   │    │  (L151-293)  │    │  (L3493+)    │          │
│  └──────┬───────┘    └──────┬───────┘    └──────┬───────┘          │
│         │                   │                   │                   │
│         └───────────────────┼───────────────────┘                   │
│                             │                                       │
│                    ┌────────▼────────┐                              │
│                    │  state3.doc     │                              │
│                    │  (共享資料模型)  │                              │
│                    └────────┬────────┘                              │
│                             │                                       │
│         ┌───────────────────┼───────────────────┐                  │
│         │                   │                   │                  │
│  ┌──────▼──────┐    ┌───────▼──────┐    ┌──────▼──────┐             │
│  │ render      │    │ collectV3    │    │ migrateAll  │             │
│  │ ChordPro     │    │ ToDoc        │    │ Measures    │             │
│  │ FromDoc      │    │ (L912)       │    │ (L2237)     │             │
│  │ (L878)       │    │              │    │             │             │
│  └─────────────┘    └──────────────┘    └─────────────┘             │
│                                                                     │
└─────────────────────────────────────────────────────────────────────┘
```

### 2.2 現有程式碼位置

#### 2.2.1 HTML 結構（web/index.html）

| 元素 ID | 行號 | 用途 | 目前狀態 |
|---|---|---|---|
| `tab-chordpro` | L90 | ChordPro 頁籤按鈕 | ✅ 運作中 |
| `chordpro-pane` | L96-109 | ChordPro 編輯面板 | ✅ 運作中 |
| `chordpro-editor` | L107-108 | `<textarea>` 編輯器 | ✅ 運作中 |
| `tab-score` | L91 | 簡譜格線頁籤 | ⚠️ 已棄用（保留） |
| `score-pane` | L110-150 | 簡譜格線面板 | ⚠️ 已棄用（保留） |
| `tab-sola321` | L92 | Score Studio 頁籤 | ✅ 預設啟用 |
| `sola321-pane` | L151-293 | Score Studio 面板 | ✅ 運作中 |

**關鍵 HTML 片段**（L90-109）：
```html
<div class="editor-tabs">
  <button type="button" class="editor-tab" id="tab-chordpro">ChordPro 文字</button>
  <button type="button" class="editor-tab" id="tab-score">簡譜格線</button>
  <button type="button" class="editor-tab active" id="tab-sola321">Score Studio</button>
</div>

<!-- ChordPro 編輯器 -->
<div id="chordpro-pane" class="editor-pane">
  <textarea id="chordpro-editor" class="chordpro-editor" spellcheck="false"
    placeholder="#title: 歌名&#10;#key: C&#10;[C]歌詞..."></textarea>
</div>

<!-- Score Studio 編輯器 -->
<div id="sola321-pane" class="editor-pane pane-active">
  <div id="sola321-score"></div>
</div>
```

#### 2.2.2 JavaScript 邏輯（web/assets/app.js）

| 函式 | 行號 | 用途 | 完成度 |
|---|---|---|---|
| `switchTab()` | L1645-1662 | 頁籤切換 | ✅ 完整 |
| `renderChordProFromDoc()` | L878-893 | Doc → ChordPro 文字 | ⚠️ 僅 metadata |
| `applyChordProToDoc()` | L926-932 | ChordPro → Doc | ❌ 僅 metadata |
| `saveCurrentDoc()` | L895-924 | 存檔 | ✅ 完整 |
| `collectV3ToDoc()` | L1518-1615 | 重建 ticks | ✅ 完整 |
| `migrateAllMeasures()` | L2237-2240 | Event model 遷移 | ✅ 完整 |
| `ensureEventModel()` | L2163-2170 | 初始化 event model | ✅ 完整 |
| `renderSola321Score()` | L2843-2979 | Score Studio 渲染 | ✅ 完整 |
| `renderSola321Measure()` | L3054-3490 | 單一小節渲染 | ✅ 完整 |
| `renderSola321MeasureVertical()` | L2986-3044 | 直式唯讀渲染 | ✅ 完整 |

**關鍵缺口**：
```javascript
// ❌ 缺失：ChordPro 文字 → measures 陣列 的解析器
// function parseChordProToDoc(text) { ... }

// ⚠️ 現有：只解析 metadata，不解析和弦/歌詞/小節結構
function applyChordProToDoc(doc, text) {
  doc.title = ...;
  doc.key = ...;
  // 沒有 measures 解析邏輯！
}
```

### 2.3 資料模型現狀

#### 2.3.1 Client-side（app.js）

```javascript
var state3 = {
  currentDocId: null,
  doc: {
    id: "doc_xxx",
    title: "歌名",
    key: "C",
    timeSignature: "4/4",
    tempo: 90,
    measures: [
      {
        number: 1,
        chordText: "C",           // 和弦名稱
        noteText: "5 3 2 1",      // 簡譜音符
        lyricText: "歌詞第一行",
        lyricText2: "",            // 第 2 行歌詞
        lyricText3: "",
        lyricText4: "",
        lyricRows: 1,
        beats: [...],             // 拍位陣列
        melodyEvents: [...],      // 事件模型
        chordEvents: [...],
        lyricTracks: [[...]],
        eventOverrides: {...},
        eventModelVersion: 3,
        noteTicks: [0, 120, 240, 360],
        chordTicks: [0],
        lyricTicks: [0, 120, 240, 360]
      }
      // ... 更多 measures
    ]
  }
};
```

#### 2.3.2 Server-side（app/models.py）

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
    eventOverrides: dict = field(default_factory=dict)  # Phase 6D 新增

@dataclass
class ScoreDocument:
    id: str
    title: str = "未命名樂譜"
    measures: list[ScoreMeasure] = field(default_factory=list)
    # ... 其他欄位
```

**重要發現**：Server-side `ScoreMeasure` **沒有** `melodyEvents`/`chordEvents`/`lyricTracks`/`annotations`/`eventModelVersion` 欄位！

這導致了 **Phase 0 存檔 400 問題**（詳見 `tools/phase0-root-cause-report.md`）。

### 2.4 現有轉換邏輯分析

#### 2.4.1 Doc → ChordPro（renderChordProFromDoc）

**位置**：app.js L878-893

```javascript
function renderChordProFromDoc(doc) {
  var ed = $('#chordpro-editor');
  if (!ed) return;
  var lines = ['#title: ' + (doc.title || ''), '#key: ' + (doc.key || 'C'),
    '#bpm: ' + (doc.tempo || 90), '#time: ' + (doc.timeSignature || '4/4')];
  if (doc.composer) lines.push('#artist: ' + doc.composer);
  lines.push('');
  (doc.measures || []).forEach(function(m) {
    var l = (m.chordText || '').trim();
    var note = cleanNoteText(m.noteText || '').trim();
    var lyric = (m.lyricText || '').trim();
    if (l || note || lyric) lines.push((l ? l + ' ' : '') + (note ? note + ' ' : '') + lyric);
  });
  ed.value = lines.join('\n');
}
```

**問題**：
1. 輸出格式不符合標準 ChordPro（缺少段落標記 `[verse]`、重複標記 `[repeat]`）
2. 簡譜音符（noteText）被包含在輸出中，但標準 ChordPro 無此概念
3. 多行歌詞（lyricText2-4）未被處理

#### 2.4.2 ChordPro → Doc（applyChordProToDoc）

**位置**：app.js L926-932

```javascript
function applyChordProToDoc(doc, text) {
  doc.title = (text.match(/^#title:\s*(.+)$/m) || ['','未命名樂譜'])[1].trim() || doc.title;
  var k = text.match(/^#key:\s*(\S+)$/m); if (k) doc.key = k[1];
  var b = text.match(/^#bpm:\s*(\d+)$/m); if (b) doc.tempo = parseInt(b[1], 10);
  var t = text.match(/^#time:\s*(\S+)$/m); if (t) doc.timeSignature = t[1];
  var a = text.match(/^#artist:\s*(.+)$/m); if (a) doc.composer = a[1].trim();
}
```

**問題**：
1. **完全缺少 measures 解析邏輯**
2. 不處理和弦標記 `[C]`、`[G]` 等
3. 不處理歌詞文字
4. 不處理段落標記 `[verse]`、`[chorus]` 等
5. 不處理小節線 `|`

---

## 三、技術架構設計

### 3.1 雙向同步系統架構

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                        ChordPro 雙向同步系統架構                              │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                             │
│  ┌──────────────────┐              ┌──────────────────┐                     │
│  │  ChordPro        │              │  Score Studio    │                     │
│  │  Editor          │              │  (Sola321)       │                     │
│  │                  │              │                  │                     │
│  │  <textarea>     │              │  <div>#sola321   │                     │
│  │  #chordpro-     │              │  -score</div>    │                     │
│  │  editor         │              │                  │                     │
│  └────────┬─────────┘              └────────┬─────────┘                     │
│           │                                 │                               │
│           │  event: 'input'                 │  event: 'measure-change'      │
│           ▼                                 ▼                               │
│  ┌────────────────────────────────────────────────────────────────┐        │
│  │                    Sync Engine (新模組)                         │        │
│  │                                                                │        │
│  │  ┌─────────────────┐    ┌─────────────────┐                   │        │
│  │  │ ChordPro Parser │    │ Score Studio    │                   │        │
│  │  │ (新)            │    │ Renderer        │                   │        │
│  │  │                 │    │ (修改)          │                   │        │
│  │  │ parseChordPro() │    │ renderSynced()  │                   │        │
│  │  └────────┬────────┘    └────────┬────────┘                   │        │
│  │           │                      │                             │        │
│  │           └──────────┬───────────┘                             │        │
│  │                      ▼                                         │        │
│  │  ┌─────────────────────────────────────────────────────────┐  │        │
│  │  │             Conflict Detector (新)                       │  │        │
│  │  │                                                         │  │        │
│  │  │ detectConflicts()                                       │  │        │
│  │  │ resolveConflict()                                       │  │        │
│  │  └─────────────────────────────────────────────────────────┘  │        │
│  │                                                              │        │
│  │  ┌─────────────────────────────────────────────────────────┐  │        │
│  │  │             Version Tracker (新)                         │  │        │
│  │  │                                                         │  │        │
│  │  │ trackVersion(format, contentHash)                       │  │        │
│  │  │ isStale(format, version)                                │  │        │
│  │  └─────────────────────────────────────────────────────────┘  │        │
│  └────────────────────────────────────────────────────────────────┘        │
│                                                                             │
│  ┌────────────────────────────────────────────────────────────────┐        │
│  │                      state3.doc (共享資料模型)                   │        │
│  │                                                                │        │
│  │  - measures[]                                                  │        │
│  │  - key, timeSignature, tempo                                   │        │
│  │  - metadata (title, composer, etc.)                            │        │
│  └────────────────────────────────────────────────────────────────┘        │
│                                                                             │
└─────────────────────────────────────────────────────────────────────────────┘
```

### 3.2 核心模組規格

#### 3.2.1 ChordPro Parser（新增）

**檔案位置**：`web/assets/chordpro-parser.js`（新檔案）

**主要函式**：
```javascript
/**
 * 解析 ChordPro 文字為 ScoreDocument 結構
 * @param {string} text - ChordPro 格式文字
 * @param {object} options - 解析選項
 * @returns {object} partial Doc（僅包含解析出的結構，不含 metadata）
 */
function parseChordProToDoc(text, options = {}) {
  return {
    measures: [],      // 解析出的小節陣列
    sections: [],      // 段落標記（verse, chorus, etc.）
    metadata: {}       // 從文字解析的 metadata
  };
}

/**
 * 將 ChordPro 文字轉換為 measures 陣列
 * @param {string} text
 * @returns {Array<{chordText, lyricText, noteText}>}
 */
function parseMeasures(text) { ... }

/**
 * 解析段落標記
 * @param {string} text
 * @returns {Array<{type, startMeasure, endMeasure}>}
 */
function parseSections(text) { ... }

/**
 * 解析 metadata
 * @param {string} text
 * @returns {object}
 */
function parseMetadata(text) { ... }
```

**解析規則**：
```
輸入：
#title: 歌名
#key: C
#time: 4/4
#bpm: 90

[verse]
[C]歌詞第一行 [G]歌詞第二行
[Am]歌詞第三行 [F]歌詞第四行

[chorus]
[C]副歌歌詞 [G]副歌歌詞

輸出：
{
  metadata: { title: '歌名', key: 'C', timeSignature: '4/4', tempo: 90 },
  sections: [
    { type: 'verse', startMeasure: 0, endMeasure: 3 },
    { type: 'chorus', startMeasure: 4, endMeasure: 5 }
  ],
  measures: [
    { chordText: 'C', lyricText: '歌詞第一行 歌詞第二行' },
    { chordText: 'Am', lyricText: '歌詞第三行 歌詞第四行' },
    ...
  ]
}
```

#### 3.2.2 Score Studio Renderer（修改）

**修改位置**：`web/assets/app.js`

**新增函式**：
```javascript
/**
 * 將 measures 陣列轉換為 ChordPro 文字
 * @param {Array} measures
 * @param {Array} sections
 * @returns {string} ChordPro 格式文字
 */
function renderDocToChordPro(measures, sections) {
  var lines = [];
  
  // 匯出 metadata
  lines.push('#title: ' + (state3.doc.title || ''));
  lines.push('#key: ' + (state3.doc.key || 'C'));
  lines.push('#time: ' + (state3.doc.timeSignature || '4/4'));
  lines.push('#bpm: ' + (state3.doc.tempo || 90));
  lines.push('');
  
  // 匯出段落標記
  var currentSection = null;
  measures.forEach(function(m, i) {
    var section = findSectionForMeasure(sections, i);
    if (section && section !== currentSection) {
      lines.push('[' + section.type + ']');
      currentSection = section;
    }
    
    // 匯出和弦+歌詞
    var chord = m.chordText ? '[' + m.chordText + ']' : '';
    var lyric = m.lyricText || '';
    lines.push(chord + lyric);
  });
  
  return lines.join('\n');
}

/**
 * 同步更新 ChordPro 編輯器內容
 */
function syncChordProEditor() {
  var chordproText = renderDocToChordPro(
    state3.doc.measures,
    state3.doc.sections || []
  );
  var editor = $('#chordpro-editor');
  if (editor) {
    editor.value = chordproText;
  }
}
```

#### 3.2.3 Conflict Detector（新增）

**檔案位置**：`web/assets/sync-conflict.js`（新檔案）

**主要函式**：
```javascript
/**
 * 偵測 ChordPro 與 Score Studio 之間的內容差異
 * @param {string} chordproText
 * @param {Array} measures
 * @returns {object} conflict report
 */
function detectConflicts(chordproText, measures) {
  return {
    hasConflict: boolean,
    type: 'measure-mismatch' | 'content-diff' | 'section-mismatch',
    details: [...]
  };
}

/**
 * 計算內容雜湊（用於版本追蹤）
 * @param {string} text
 * @returns {string} MD5 hash
 */
function computeContentHash(text) {
  var hash = 0;
  for (var i = 0; i < text.length; i++) {
    hash = ((hash << 5) - hash) + text.charCodeAt(i);
    hash = hash & hash;
  }
  return hash.toString(16);
}
```

#### 3.2.4 Version Tracker（新增）

**檔案位置**：`web/assets/sync-version.js`（新檔案）

**主要函式**：
```javascript
/**
 * 記錄各格式的當前版本
 */
var versionTracker = {
  chordpro: { version: 0, hash: null, timestamp: null },
  scoreStudio: { version: 0, hash: null, timestamp: null }
};

/**
 * 更新版本
 */
function trackVersion(format, content) {
  var hash = computeContentHash(content);
  versionTracker[format] = {
    version: versionTracker[format].version + 1,
    hash: hash,
    timestamp: Date.now()
  };
}

/**
 * 檢查是否過時
 */
function isStale(format, expectedHash) {
  return versionTracker[format].hash !== expectedHash;
}
```

### 3.3 事件驅動同步機制

```
┌─────────────────┐     input event      ┌─────────────────┐
│ ChordPro        │ ──────────────────→ │ Sync Engine     │
│ Editor          │                     │                 │
│ (textarea)      │                     │ 1. Parse        │
└─────────────────┘                     │ 2. Detect       │
                                        │ 3. Update       │
┌─────────────────┐                     │ 4. Render       │
│ Score Studio    │ ←────────────────── │ 5. Track        │
│ (DOM)           │     sync event      └─────────────────┘
└─────────────────┘                              │
       ▲                                         │
       │                                     input event
       └───────────────────────────────────────┘
              measure edit event
```

**同步流程**：
1. 用戶在 ChordPro 編輯器輸入文字
2. `input` 事件觸發 → Sync Engine
3. Sync Engine 解析文字 → 產生 measures
4. 比對現有 measures → 偵測衝突
5. 更新 state3.doc.measures
6. 觸發 Score Studio 重新渲染
7. 記錄版本資訊

---

## 四、實施計畫與分工

### 4.1 階段劃分

```
┌─────────────────────────────────────────────────────────────────────┐
│                        實施階段路線圖                                 │
├─────────────────────────────────────────────────────────────────────┤
│                                                                     │
│  Phase 0: 基礎設施（1 週）                                           │
│  ├── 修復存檔 400 問題                                               │
│  ├── 建立新模組檔案結構                                               │
│  └── 單元測試框架                                                    │
│                                                                     │
│  Phase 1: ChordPro Parser（1.5 週）                                 │
│  ├── 實作 parseChordProToDoc()                                      │
│  ├── 支援基本語法（metadata、和弦、歌詞）                             │
│  ├── 支援段落標記（verse、chorus）                                   │
│  └── 單元測試 + 邊界案例                                             │
│                                                                     │
│  Phase 2: Score Studio 擴充（1.5 週）                               │
│  ├── 修改 renderChordProFromDoc() → renderDocToChordPro()           │
│  ├── 支援段落標記輸出                                                │
│  ├── 支援多行歌詞輸出                                                │
│  └── 整合測試                                                        │
│                                                                     │
│  Phase 3: 雙向同步引擎（2 週）                                       │
│  ├── 實作 Conflict Detector                                         │
│  ├── 實作 Version Tracker                                           │
│  ├── 建立事件驅動同步機制                                             │
│  ├── UI 衝突提示                                                      │
│  └── 整合測試                                                        │
│                                                                     │
│  Phase 4: UI/UX 優化（1 週）                                         │
│  ├── 同步狀態指示器                                                  │
│  ├── 手動同步按鈕                                                    │
│  ├── 歷史版本回復                                                    │
│  └── 使用者手冊                                                      │
│                                                                     │
│  Phase 5: 測試與驗證（1 週）                                         │
│  ├── 回歸測試（24 項 phase15 + 36 項小節操作）                        │
│  ├── 效能測試                                                        │
│  ├── 相容性測試                                                      │
│  └── 文件完善                                                        │
│                                                                     │
└─────────────────────────────────────────────────────────────────────┘
```

### 4.2 詳細任務清單

#### Phase 0: 基礎設施（預估：5 天）

| 任務 ID | 任務名稱 | 負責組 | 預估工時 |  Dependencies |
|---|---|---|---|---|
| 0.1 | 修復存檔 400 問題 | Backend | 1 天 | 無 |
| 0.2 | 建立 chordpro-parser.js | Frontend | 0.5 天 | 無 |
| 0.3 | 建立 sync-conflict.js | Frontend | 0.5 天 | 無 |
| 0.4 | 建立 sync-version.js | Frontend | 0.5 天 | 無 |
| 0.5 | 設定測試框架 | QA | 1 天 | 0.2-0.4 |
| 0.6 | 編寫單元測試模板 | QA | 1 天 | 0.5 |
| 0.7 | Git branch 建立與設定 | DevOps | 0.5 天 | 無 |

**任務 0.1 詳細規格**（存檔 400 修復）：

問題：Server-side `ScoreMeasure` dataclass 缺少 event model 欄位

解決方案（選定方案 B）：
```python
# app/models.py 修改
@dataclass
class ScoreMeasure:
    # ... 既有欄位 ...
    
    # 新增 event model 欄位
    melodyEvents: list = field(default_factory=list)
    chordEvents: list = field(default_factory=list)
    lyricTracks: list = field(default_factory=list)
    annotations: list = field(default_factory=list)
    eventModelVersion: int = 3
    eventOverrides: dict = field(default_factory=dict)
    
    def to_dict(self):
        d = { ...既有欄位... }
        # 新增 event model 輸出
        if self.melodyEvents:
            d['melodyEvents'] = self.melodyEvents
        if self.eventModelVersion:
            d['eventModelVersion'] = self.eventModelVersion
        return d
    
    @staticmethod
    def from_dict(d):
        # 新增 event model 解析
        return ScoreMeasure(
            # ... 既有欄位...
            melodyEvents=d.get('melodyEvents', []),
            chordEvents=d.get('chordEvents', []),
            lyricTracks=d.get('lyricTracks', [[], [], [], []]),
            annotations=d.get('annotations', []),
            eventModelVersion=d.get('eventModelVersion', 3),
            eventOverrides=d.get('eventOverrides', {}),
        )
```

#### Phase 1: ChordPro Parser（預估：7.5 天）

| 任務 ID | 任務名稱 | 負責組 | 預估工時 | Dependencies |
|---|---|---|---|---|
| 1.1 | 實作 parseMetadata() | Frontend | 1 天 | 0.2 |
| 1.2 | 實作 parseMeasures() 基本版 | Frontend | 2 天 | 1.1 |
| 1.3 | 實作 parseSections() | Frontend | 1.5 天 | 1.2 |
| 1.4 | 支援複雜語法（重複、轉調） | Frontend | 2 天 | 1.3 |
| 1.5 | 單元測試 - 基本案例 | QA | 1 天 | 1.2 |
| 1.6 | 單元測試 - 邊界案例 | QA | 1 天 | 1.4 |

**parseMeasures() 核心邏輯**：
```javascript
function parseMeasures(text) {
  const lines = text.split('\n');
  const measures = [];
  let currentChord = '';
  let currentLyric = '';
  
  for (const line of lines) {
    // 跳過空行與 metadata
    if (!line.trim() || line.startsWith('#')) continue;
    // 跳過段落標記
    if (line.match(/^\[[a-z]+\]$/)) continue;
    
    // 解析 [和弦]歌詞 模式
    const parts = line.match(/(\[[A-G][A-Za-z0-9#b\-()\/]*\]|[^\[\]]+)/g) || [];
    
    for (const part of parts) {
      if (part.startsWith('[') && part.endsWith(']')) {
        currentChord = part.slice(1, -1);
      } else {
        currentLyric = (currentLyric + ' ' + part.trim()).trim();
      }
    }
    
    // 每行視為一個 measure（可調整為每 N 行）
    if (currentChord || currentLyric) {
      measures.push({
        chordText: currentChord,
        lyricText: currentLyric,
        noteText: ''  // ChordPro 無音符資訊
      });
      currentChord = '';
      currentLyric = '';
    }
  }
  
  return measures;
}
```

#### Phase 2: Score Studio 擴充（預估：7.5 天）

| 任務 ID | 任務名稱 | 負責組 | 預估工時 | Dependencies |
|---|---|---|---|---|
| 2.1 | 修改 renderChordProFromDoc → renderDocToChordPro | Frontend | 2 天 | 無 |
| 2.2 | 支援段落標記輸出 | Frontend | 1.5 天 | 2.1 |
| 2.3 | 支援多行歌詞輸出 | Frontend | 1.5 天 | 2.2 |
| 2.4 | 整合 syncChordProEditor() | Frontend | 1 天 | 2.3 |
| 2.5 | 單元測試 | QA | 1.5 天 | 2.4 |

#### Phase 3: 雙向同步引擎（預估：10 天）

| 任務 ID | 任務名稱 | 負責組 | 預估工時 | Dependencies |
|---|---|---|---|---|
| 3.1 | 實作 detectConflicts() | Frontend | 2 天 | Phase 1, 2 |
| 3.2 | 實作 trackVersion() | Frontend | 1 天 | 3.1 |
| 3.3 | 建立事件監聽機制 | Frontend | 2 天 | 3.2 |
| 3.4 | 實作同步循環（防抖） | Frontend | 2 天 | 3.3 |
| 3.5 | UI 衝突提示元件 | Frontend | 2 天 | 3.4 |
| 3.6 | 整合測試 | QA | 1 天 | 3.5 |

#### Phase 4: UI/UX 優化（預估：5 天）

| 任務 ID | 任務名稱 | 負責組 | 預估工時 | Dependencies |
|---|---|---|---|---|
| 4.1 | 同步狀態指示器 | Frontend | 1 天 | Phase 3 |
| 4.2 | 手動同步按鈕 | Frontend | 0.5 天 | 4.1 |
| 4.3 | 歷史版本回復功能 | Frontend | 2 天 | 4.2 |
| 4.4 | 使用者手冊 | Docs | 1.5 天 | 4.3 |

#### Phase 5: 測試與驗證（預估：5 天）

| 任務 ID | 任務名稱 | 負責組 | 預估工時 | Dependencies |
|---|---|---|---|---|
| 5.1 | 回歸測試（phase15） | QA | 1 天 | Phase 4 |
| 5.2 | 回歸測試（小節操作） | QA | 1 天 | Phase 4 |
| 5.3 | 效能測試 | QA | 1 天 | Phase 4 |
| 5.4 | 相容性測試 | QA | 1 天 | Phase 4 |
| 5.5 | 最終驗收報告 | PM | 1 天 | 5.1-5.4 |

### 4.3 總工時估計

| 階段 | 工時（人天） | 進度 |
|---|---|---|
| Phase 0 | 5 天 | 第 1 週 |
| Phase 1 | 7.5 天 | 第 2 週 |
| Phase 2 | 7.5 天 | 第 3 週 |
| Phase 3 | 10 天 | 第 4-5 週 |
| Phase 4 | 5 天 | 第 6 週 |
| Phase 5 | 5 天 | 第 7 週 |
| **總計** | **40 人天** | **約 8 週** |

---

## 五、潛在困難與解決方案

### 5.1 技術困難

#### 困難 1：ChordPro 語法多樣性

**問題**：ChordPro 有豐富語法（重複段落、調性變更、轉調、結束記號等），標準化解析困難。

**影響**：parser 可能無法處理所有格式，導致資訊丟失。

**解決方案**：
- 階段性支援：Phase 1 僅支援基本語法（metadata、和弦、歌詞、段落標記）
- 擴展機制：設計 plugin 架構，允許後續補充複雜語法解析
- 明確限制：在 UI 中標示「支援的 ChordPro 語法子集」

**風險等級**：中

---

#### 困難 2：雙向同步的原子性

**問題**：同步過程中若發生錯誤（如 parser 失敗），可能導致資料不一致。

**影響**：ChordPro 文字與 Score Studio 內容不同步。

**解決方案**：
- 使用 optimistic update + rollback 機制
- 所有修改先在 staging area 驗證，確認無誤後才寫入 state3.doc
- 保留前一版本的完整快照（利用既有 undo stack）

**風險等級**：高

---

#### 困難 3：衝突檢測的準確性

**問題**：如何判斷「兩端編輯了相同內容」vs「兩端編輯了不同內容」？

**影響**：錯誤的衝突偵測會導致不必要的提示或遺漏真正的衝突。

**解決方案**：
- 使用 content hash + timestamp 雙重驗證
- 區分「結構性變更」（小節增刪）與「內容性變更」（歌詞修改）
- 提供「查看差異」功能，讓用戶手動決議

**風險等級**：中

---

#### 困難 4：簡譜音符的缺失

**問題**：ChordPro 格式不包含簡譜音符資訊，雙向同步後 Score Studio 的 noteText 會為空。

**影響**：同步後的樂譜缺少音符，無法直接用於簡譜編輯。

**解決方案**：
- 明確告知用戶：ChordPro 僅支援和弦+歌詞同步
- 提供「生成簡譜」功能（未來整合 OMR 或手動輸入）
- 在 UI 中標示哪些欄位無法從 ChordPro 推導

**風險等級**：高（需產品決策）

---

### 5.2 工程困難

#### 困難 5：既有代碼的相容性

**問題**：修改 app.js 可能影響現有功能（格線編輯器、時間軸渲染器等）。

**影響**：回歸測試失敗率上升。

**解決方案**：
- 建立獨立模組（chordpro-parser.js、sync-conflict.js、sync-version.js）
- 最小化 app.js 修改範圍
- 完整的回歸測試（phase15 24 項 + 小節操作 36 項）

**風險等級**：中

---

#### 困難 6：存檔 400 問題的連鎖影響

**問題**：Phase 0 的存檔 400 問題若未修復，雙向同步後的修改無法持久化。

**影響**：所有同步成果可能丢失。

**解決方案**：
- **優先處理**：Phase 0 必須先完成存檔修復
- 實施方案 B（server 端新增 event model 欄位）
- 增加存檔成功率的監控告警

**風險等級**：高

---

### 5.3 協作困難

#### 困難 7：多人同時編輯

**問題**：若多個用戶同時編輯同一專案，可能產生衝突。

**影響**：資料損壞或不一致。

**解決方案**：
- 本階段不支援多用戶併發（本機工具定位）
- 明確文件：單一用戶、單一工作階段
- 未來可扩展為 WebSocket 即時協作（不在本階段範圍）

**風險等級**：低

---

#### 困難 8：版本遷移

**問題**：既有專案的 data 可能不包含 event model 欄位，新系統的遷移處理。

**影響**：舊專案可能無法正確顯示。

**解決方案**：
- 利用既有 `migrateAllMeasures()` 函式自動遷移
- 增加遷移日誌，方便除錯
- 提供「重新載入專案」按鈕觸發遷移

**風險等級**：低

---

## 六、文件與依附明細

### 6.1 現有檔案清單

#### 6.1.1 核心應用程式檔案

| 檔案路徑 | 大小 | 修改次數 | 說明 |
|---|---|---|---|
| `web/index.html` | 19 KB | 150+ | 主 HTML 頁面，定義 UI 結構 |
| `web/assets/app.js` | 258 KB | 500+ | 主要 JavaScript 邏輯 |
| `web/assets/styles.css` | 45 KB | 100+ | 樣式表 |
| `app/server.py` | 17 KB | 50+ | FastAPI 伺服器 |
| `app/models.py` | 27 KB | 80+ | 資料模型定義 |
| `app/projects.py` | 8 KB | 30+ | 專案管理邏輯 |

#### 6.1.2 測試與驗證檔案

| 檔案路徑 | 說明 |
|---|---|
| `phase15/test_runner.js` | 24 項回歸測試 |
| `tools/hermes-verify-phase4-b1.js` | 新增/刪除/空文件測試 |
| `tools/hermes-verify-phase4-b2.js` | 上移/下移測試 |
| `tools/hermes-verify-phase4-del.js` | 刪除 Undo/Redo 測試 |
| `tools/phase0-400-repro.py` | 400 根因初步測試 |
| `tools/phase0-400-deep-dive.py` | 400 根因深入測試 |
| `tools/phase0-400-real-repro.py` | 400 真實 payload 重現 |

#### 6.1.3 報告與文檔

| 檔案路徑 | 說明 |
|---|---|
| `tools/phase0-root-cause-report.md` | 存檔 400 根因報告 |
| `tools/phase0-delivery-report.md` | Phase 0 交付報告 |
| `tools/phase4-delivery-review.md` | 階段 4.2 交付審查報告 |
| `tools/chordpro-integration-analysis.md` | ChordPro 整合分析 |
| `ARCHITECTURE.md` | 系統架構圖 |
| `docs/handover/FINAL_HANDOVER_SUMMARY.md` | 過往交接摘要 |

### 6.2 新增檔案清單（本專案）

| 檔案路徑 | 預計大小 | 說明 |
|---|---|---|
| `web/assets/chordpro-parser.js` | 8-12 KB | ChordPro 解析器模組 |
| `web/assets/sync-conflict.js` | 4-6 KB | 衝突偵測模組 |
| `web/assets/sync-version.js` | 2-4 KB | 版本追蹤模組 |
| `web/assets/sync-engine.js` | 6-10 KB | 雙向同步引擎 |
| `tools/chordpro-sync-test.js` | 5-8 KB | 同步功能測試 |
| `tools/chordpro-sync-baseline.json` | 2-4 KB | 測試基準數據 |
| `docs/chordpro-sync-spec.md` | 5-8 KB | 同步系統規格書 |
| `docs/chordpro-sync-handover.md` | 3-5 KB | 本交接報告 |

### 6.3 外部依賴

#### 6.3.1 前端依賴

| 依賴 | 版本 | 用途 |
|---|---|---|
| Puppeteer | 21.x | Headless Chrome 自動化測試 |
| Node.js | 20.x | JavaScript 運行環境 |

#### 6.3.2 後端依賴

| 依賴 | 版本 | 用途 |
|---|---|---|
| Python | 3.11+ | 伺服器運行環境 |
| FastAPI | 0.100+ | Web framework |
| Pydantic | 2.x | 資料驗證 |

#### 6.3.3 測試框架

| 框架 | 用途 |
|---|---|
| Jest（可選） | JavaScript 單元測試 |
| pytest（可選） | Python 單元測試 |

---

## 七、測試策略

### 7.1 測試層級

```
┌─────────────────────────────────────────────────────────────────┐
│                        測試金字塔                                 │
├─────────────────────────────────────────────────────────────────┤
│                                                                 │
│                          ┌───────┐                              │
│                          │E2E 測試│  ← 完整工作流測試            │
│                          └───┬───┘                              │
│                              │                                  │
│                    ┌─────────▼─────────┐                        │
│                    │ 整合測試          │  ← 模組間協作測試       │
│                    └─────────┬─────────┘                        │
│                              │                                  │
│              ┌───────────────▼───────────────┐                  │
│              │ 單元測試                      │  ← 函式級別測試   │
│              │ - parseChordProToDoc()        │                  │
│              │ - renderDocToChordPro()       │                  │
│              │ - detectConflicts()           │                  │
│              │ - trackVersion()              │                  │
│              └───────────────────────────────┘                  │
│                                                                 │
└─────────────────────────────────────────────────────────────────┘
```

### 7.2 測試案例清單

#### 7.2.1 ChordPro Parser 測試

| 測試 ID | 測試案例 | 輸入 | 預期輸出 |
|---|---|---|---|
| P-001 | 基本 metadata 解析 | `#title: Test\n#key: C` | `{ title: 'Test', key: 'C' }` |
| P-002 | 基本 and 歌詞解析 | `[C]歌詞` | `{ measures: [{ chordText: 'C', lyricText: '歌詞' }] }` |
| P-003 | 多和弦同小節 | `[C][G]歌詞` | `{ chordText: 'C G', lyricText: '歌詞' }` |
| P-004 | 段落標記解析 | `[verse]\n[C]歌詞` | `{ sections: [{ type: 'verse' }], measures: [...] }` |
| P-005 | 空行處理 | `[C]歌詞\n\n[G]歌詞` | 兩個 measure，無空 measure |
| P-006 | 特殊和弦 | `[Cmaj7][Dm7-G7][C]歌詞` | 正確解析和弦名稱 |
| P-007 | 長歌詞換行 | `[C]這是一句很長的歌詞...` | 單一小節，歌詞完整 |
| P-008 | 無和弦行 | `純歌詞文字` | `{ chordText: '', lyricText: '純歌詞文字' }` |

#### 7.2.2 Score Studio 匯出測試

| 測試 ID | 測試案例 | 輸入 | 預期輸出 |
|---|---|---|---|
| E-001 | 基本匯出 | measures: [{chordText:'C', lyricText:'歌詞'}] | `[C]歌詞` |
| E-002 | 多行匯出 | 3 個 measures | 3 行文字 |
| E-003 | 段落標記匯出 | sections: [{type:'verse'}] | `[verse]` 標記 |
| E-004 | 空 measure 處理 | measures: [{chordText:'', lyricText:''}] | 跳過或輸出空行 |

#### 7.2.3 同步功能測試

| 測試 ID | 測試案例 | 預期行為 |
|---|---|---|
| S-001 | ChordPro → Score Studio | 編輯 ChordPro，Score Studio 自動更新 |
| S-002 | Score Studio → ChordPro | 編輯 Score Studio，ChordPro 自動更新 |
| S-003 | 同步延遲 | 編輯後 <100ms 內完成同步 |
| S-004 | 衝突偵測 | 兩端同時編輯，正確偵測衝突 |
| S-005 | 版本追蹤 | 每次同步正確增加版本號 |
| S-006 | 錯誤恢復 | Parser 失敗時，保留原有內容 |

#### 7.2.4 回歸測試（延續既有）

| 測試套件 | 測試項目數 | 通過標準 |
|---|---|---|
| phase15 | 24 項 | 24/24 PASS |
| 小節操作 b1 | 13 項 | 13/13 PASS |
| 小節操作 b2 | 12 項 | 12/12 PASS |
| 小節操作 del | 11 項 | 11/11 PASS |
| **總計** | **60 項** | **60/60 PASS** |

---

## 八、風險管理

### 8.1 風險登記冊

| 風險 ID | 風險描述 | 機率 | 影響 | 等級 | 緩解措施 |
|---|---|---|---|---|---|
| R1 | ChordPro 語法多樣性導致解析失敗 | 高 | 中 | 高 | 分階段支援，明確限制範圍 |
| R2 | 雙向同步導致無限迴圈 | 中 | 高 | 高 | 實現防抖（debounce）+ 編輯鎖 |
| R3 | 存檔 400 問題未修復導致資料丢失 | 中 | 高 | 高 | Phase 0 優先處理 |
| R4 | 簡譜音符缺失影響使用體驗 | 高 | 中 | 中 | 明確文件限制，提供未來擴充路徑 |
| R5 | 回歸測試失敗率超過 20% | 低 | 中 | 中 | 增量修改，持續整合 |
| R6 | 專案時程延誤超過 2 週 | 中 | 中 | 中 | 每週進度檢討，動態調整資源 |

### 8.2 應急計畫

**若 Phase 0 存檔修復延誤**：
- 暫停雙向同步開發
- 先完成 parser 與 renderer 模組（離線測試）
- 等待存檔修復後再整合

**若 ChordPro 語法支援不及**：
- 提供「基本模式」與「進階模式」切換
- 在 UI 中顯示不支援的語法警告
- 允許用戶手動修正解析結果

**若同步衝突頻繁**：
- 暫時禁用自動同步，改為手動同步按鈕
- 增加「查看差異」功能
- 提供「保留兩端」的合併策略

---

## 九、成功標準與驗收條件

### 9.1 功能性標準

| 編號 | 標準 | 驗收方式 |
|---|---|---|
| F1 | ChordPro → Score Studio 轉換成功率 ≥95% | 測試案例 P-001 ~ P-008 |
| F2 | Score Studio → ChordPro 還原率 ≥90% | 測試案例 E-001 ~ E-004 |
| F3 | 雙向同步延遲 <100ms | 效能測試 |
| F4 | 衝突偵測準確率 ≥95% | 測試案例 S-004 |
| F5 | 所有回歸測試通過（60/60） | phase15 + b1 + b2 + del |

### 9.2 非功能性標準

| 編號 | 標準 | 驗收方式 |
|---|---|---|
| N1 | 新增程式碼不超過 50 KB | 程式碼審查 |
| N2 | app.js 修改不超過 200 行 | 程式碼審查 |
| N3 | 記憶體佔用增加 <10 MB | 效能測試 |
| N4 | 瀏覽器相容性（Chrome 90+、Edge 90+） | 相容性測試 |

### 9.3 文件標準

| 編號 | 標準 | 驗收方式 |
|---|---|---|
| D1 | 完整的使用者手冊 | 文件審查 |
| D2 | API 文件（內部模組） | 文件審查 |
| D3 | 部署指南 | 文件審查 |
| D4 | 故障排除指南 | 文件審查 |

---

## 十、後續維護建議

### 10.1 技術債清單

| 債項 | 說明 | 優先級 | 建議處理時間 |
|---|---|---|---|
| TV1 | ChordPro 語法支援不完整 | 中 | Phase 6+ |
| TV2 | 缺少多用戶協作支援 | 低 | 未來版本 |
| TV3 | 同步錯誤日誌不完善 | 中 | Phase 6 |
| TV4 | 缺少自動化端到端測試 | 高 | Phase 6 |

### 10.2 未來擴展方向

1. **簡譜生成**：整合 OMR 或手動輸入，補全 noteText 欄位
2. **多用戶協作**：WebSocket 即時同步
3. **雲端儲存**：支援 Google Drive / Dropbox 匯入匯出
4. **AI 輔助**：基於和弦進行推薦歌詞節奏

### 10.3 團隊建議

- **前端開發**：2 人（JavaScript/TypeScript 熟練）
- **後端開發**：1 人（Python/FastAPI）
- **測試工程師**：1 人（自動化測試經驗）
- **產品經理**：0.5 人（需求確認與驗收）
- **技術文檔**：0.5 人（手冊與 API 文件）

---

## 十一、附錄

### 附錄 A：ChordPro 語法參考

```
# 元數據標記
#title: 歌曲標題
#key: C              # 調性
#time: 4/4           # 拍號
#bpm: 90             # 速度
#artist: 藝術家       # 藝術家

# 段落標記
[verse]              # 主歌
[chorus]             # 副歌
[intro]              # 前奏
[bridge]             # 橋段
[outro]              # 尾奏

# 和弦標記
[C] [G] [Am] [F]     # 和弦名稱
[Cmaj7] [Dm7] [G7]   # 複雜和弦
[C/sus4] [G/b]       # 轉位和弦

# 重複標記
[repeat] ... [end repeat]
[repeat 2]          # 重複 2 次
[repeat 4]          # 重複 4 次

# 結尾標記
[coda]
[D.S.] [D.C.]       # 回溯記號
```

### 附錄 B：資料結構詳細規格

#### B.1 Measure 物件

```javascript
{
  number: 1,                    // 小節號
  chordText: 'C',               // 和弦名稱
  noteText: '5 3 2 1',          // 簡譜音符（ChordPro 無此欄位）
  lyricText: '歌詞第一行',       // 第 1 行歌詞
  lyricText2: '',               // 第 2 行歌詞
  lyricText3: '',               // 第 3 行歌詞
  lyricText4: '',               // 第 4 行歌詞
  lyricRows: 1,                 // 歌詞行數
  beats: [...],                 // 拍位陣列
  melodyEvents: [...],          // 事件模型（Phase 6D）
  chordEvents: [...],
  lyricTracks: [[...]],
  annotations: [],
  eventModelVersion: 3,
  eventOverrides: {...},
  noteTicks: [0, 120, 240, 360],
  chordTicks: [0],
  lyricTicks: [0, 120, 240, 360]
}
```

#### B.2 Section 物件

```javascript
{
  type: 'verse',                // 段落類型
  startMeasure: 0,              // 起始小節（0-based）
  endMeasure: 3                 // 結束小節（exclusive）
}
```

### 附錄 C：Git 分支策略

```
main
  │
  ├─ feature/chordpro-sync        # 本專案開發分支
  │   ├─ feat/parser              # Phase 1
  │   ├─ feat/renderer            # Phase 2
  │   ├─ feat/sync-engine         # Phase 3
  │   └─ feat/ui-ux               # Phase 4
  │
  └─ release/v3.06                # 發佈分支（完成後合併到 main）
```

### 附錄 D：環境設定

#### D.1 開發環境

```bash
# Python 環境
cd D:\SheetMusicOMR_v3.00
.venv\Scripts\activate
pip install -r requirements.txt
python app/server.py

# Node.js 環境
cd D:\SheetMusicOMR_v3.00
npm install
# 測試
node phase15/test_runner.js
node tools/hermes-verify-phase4-b1.js
```

#### D.2 測試環境

- Chrome 120+（Headless）
- Puppeteer 21.x
- Node.js 20.x
- Python 3.11+

---

## 十二、簽核區

| 角色 | 姓名 | 簽名 | 日期 |
|---|---|---|---|
| 原開發負責人 | | | |
| 新團隊負責人 | | | |
| 產品經理 | | | |
| QA 負責人 | | | |

---

**報告完成時間**：2026-10-17
**報告版本**：v1.0
**下次更新**：Phase 0 完成後

---

## 附件清單

1. `tools/phase0-root-cause-report.md` — 存檔 400 根因報告
2. `tools/phase0-delivery-report.md` — Phase 0 交付報告
3. `tools/chordpro-integration-analysis.md` — ChordPro 整合分析
4. `tools/phase4-delivery-review.md` — 階段 4.2 交付審查報告
5. `tools/hermes-verify-phase4-b1.js` — 新增/刪除測試
6. `tools/hermes-verify-phase4-b2.js` — 移動測試
7. `tools/hermes-verify-phase4-del.js` — 刪除 Undo/Redo 測試
8. `phase15/test_runner.js` — 回歸測試套件
9. `ARCHITECTURE.md` — 系統架構圖

---

**結束**
