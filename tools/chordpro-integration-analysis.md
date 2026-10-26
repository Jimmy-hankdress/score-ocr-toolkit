# ChordPro 無法直接整合到 Score Studio 的原因分析

## 一、根本問題：兩種完全不同的數據模型

### 1.1 ChordPro 格式（文字導向）
```chordpro
#title: 歌名
#key: C
#time: 4/4
#bpm: 90

[verse]
[C]歌詞第一行 [G]歌詞第二行
[Am]歌詞第三行 [F]歌詞第四行

[chorus]
[C]副歌歌詞 [G]副歌歌詞
[Am]副歌歌詞 [F]副歌歌詞
```

**特點**：
- 純文字格式，和弦用 `[和弦名]` 包圍
- 和弦與歌詞在同一行，空間分隔
- 無明確小節線概念（依賴演奏者理解）
- 無音符資訊（只有歌詞）

### 1.2 Score Studio 格式（結構導向）
```javascript
{
  id: "doc_xxx",
  title: "歌名",
  key: "C",
  timeSignature: "4/4",
  tempo: 90,
  measures: [
    {
      number: 1,
      chordText: "C",
      noteText: "5 3 2 1",      // 簡譜音符
      lyricText: "歌詞第一行",
      lyricTicks: [0, 120, 240, 360],
      noteTicks: [0, 120, 240, 360],
      beats: [...],
      melodyEvents: [...],
      eventOverrides: {...}
    },
    // ... 更多小節
  ]
}
```

**特點**：
- 結構化 JSON 數據
- 每個小節獨立，有明確編號
- 和弦、音符、歌詞分離儲存
- 支援事件模型（melodyEvents/chordEvents）

---

## 二、技術障礙詳解

### 障礙 1：缺乏 ChordPro → Doc 解析器

**現況**：
- ✅ `renderChordProFromDoc(doc)` — Doc → ChordPro 文字（L878-893）
- ❌ **缺少** `parseChordProToDoc(text)` — ChordPro 文字 → Doc

**代碼證據**（app.js L926-932）：
```javascript
function applyChordProToDoc(doc, text) {
  // 只解析 metadata（標題、調性、速度、拍號）
  doc.title = (text.match(/^#title:\s*(.+)$/m) || ['','未命名樂譜'])[1].trim() || doc.title;
  var k = text.match(/^#key:\s*(\S+)$/m); if (k) doc.key = k[1];
  var b = text.match(/^#bpm:\s*(\d+)$/m); if (b) doc.tempo = parseInt(b[1], 10);
  var t = text.match(/^#time:\s*(\S+)$/m); if (t) doc.timeSignature = t[1];
  var a = text.match(/^#artist:\s*(.+)$/m); if (a) doc.composer = a[1].trim();
  // ❌ 沒有解析和弦/歌詞/小節的邏輯
}
```

### 障礙 2：語法映射困難

| ChordPro 語法 | Score Studio 對應 | 難度 |
|---|---|---|
| `[C]` 和弦標記 | `measure.chordText` | ⭐ 簡單 |
| `歌詞文字` | `measure.lyricText` | ⭐ 簡單 |
| 小節線 `\|` | `measure` 分割 | ⭐⭐ 中等 |
| 重複段落 `[repeat]` | 無對應概念 | ⭐⭐⭐ 困難 |
| 調性變更 `key: D` | 需重建所有和弦 | ⭐⭐⭐ 困難 |
| 臨時記號 `Csus4` | 需在 chordText 表達 | ⭐⭐ 中等 |
| 簡譜音符 `5 3 2 1` | **ChordPro 完全無此概念** | ⭐⭐⭐⭐ 無法映射 |

**關鍵衝突**：ChordPro 是「彈唱譜」格式（和弦+歌詞），Score Studio 是「簡譜」格式（音符+歌詞+和弦）。兩者資訊含量不同。

### 障礙 3：小節邊界不確定

**ChordPro 例子**：
```chordpro
[C]歌詞第一行 [G]歌詞第二行
```

**問題**：
- 這一行是 1 个小節？2 個小節？4 個小節？
- 無法從文字判斷拍號（雖然有 `#time: 4/4`）
- 無法判斷每個和弦佔幾拍
- 無法判斷歌詞長度對應幾拍

**Score Studio 需求**：
- 每個 measure 必须有明確的 `number`、`beats`、`noteTicks`
- 需要知道每個和弦、每個歌詞音節的精確時間位置

### 障礙 4：缺失音符資訊

**ChordPro 只有**：
- 和弦名稱（C, G, Am, F...）
- 歌詞文字
- 段落結構（verse, chorus...）

**ChordPro 沒有**：
- ❌ 簡譜音符（5 3 2 1）
- ❌ 節奏時值（全音符、二分音符...）
- ❌ 高低八度（點號標記）
- ❌ 連音線、延音線

**後果**：即使成功解析 ChordPro，也無法生成完整的簡譜編輯體驗。

---

## 三、現有的數據流向

```
┌─────────────────────────────────────────────────────────────┐
│                     現有數據流向                             │
├─────────────────────────────────────────────────────────────┤
│                                                             │
│   ChordPro 文字編輯器                    Score Studio       │
│   (chordpro-pane)                        (sola321-pane)     │
│         │                                      │            │
│         │ renderChordProFromDoc()              │            │
│         ▼                                      │            │
│   state3.doc (metadata only) ◄─────────────────┘            │
│         │                                      │            │
│         │ applyChordProToDoc()                 │            │
│         ▼                                      │            │
│   state3.doc (完整 measures)                   │            │
│         │                                      │            │
│         │ collectV3ToDoc()                     │            │
│         ▼                                      │            │
│   server.py (save) ──→ project.json            │            │
│                                                             │
└─────────────────────────────────────────────────────────────┘

❌ 斷點：ChordPro 文字 → measures 陣列 的解析器不存在
```

---

## 四、為什麼不能簡單「複製貼上」？

### 4.1 資料結構不兼容
```javascript
// ChordPro 一行文字
"[C]歌詞第一行 [G]歌詞第二行"

// 需要轉成什麼？
[
  { number: 1, chordText: "C", lyricText: "歌詞第一行" },
  { number: 2, chordText: "G", lyricText: "歌詞第二行" }
]
// ❓ 如何決定一個和弦對應幾個小節？
// ❓ 如何決定小節線位置？
// ❓ 如何處理跨小節的歌詞？
```

### 4.2 缺少節拍感知
ChordPro 不關心節拍，演奏者自行詮釋。但 Score Studio 需要：
- 每個音符的精確 tick 位置
- 每個歌詞音節的對齊位置
- 每小節的拍數驗證

### 4.3 缺少音符資訊
即使用戶提供完整 ChordPro 檔案，也無法生成簡譜（五線譜/數字譜），因為：
- ChordPro 根本沒有音符資訊
- 需要額外的 OMR 或手動輸入才能補全

---

## 五、可行的解決方案

### 方案 A：開發 ChordPro 解析器（推薦）

**實作內容**：
```javascript
function parseChordProToDoc(text, defaultTimeSignature = '4/4') {
  const doc = {
    title: '未命名樂譜',
    key: 'C',
    timeSignature: defaultTimeSignature,
    tempo: 90,
    measures: []
  };
  
  // 1. 解析 metadata
  parseMetadata(text, doc);
  
  // 2. 按小節線分割（假設每行 = 1 小節，或根據 | 分割）
  const lines = text.split('\n');
  let currentMeasure = { chordText: '', lyricText: '' };
  
  for (const line of lines) {
    if (line.startsWith('#') || line.startsWith('[') && line.endsWith(']')) continue;
    
    // 解析 [和弦]歌詞 模式
    const parts = line.match(/(\[[A-G][A-Za-z0-9#b\-()\/]*\]|[^\[\]]+)/g) || [];
    
    for (const part of parts) {
      if (part.startsWith('[') && part.endsWith(']')) {
        currentMeasure.chordText = part.slice(1, -1);
      } else {
        currentMeasure.lyricText = (currentMeasure.lyricText + ' ' + part.trim()).trim();
      }
    }
    
    doc.measures.push(currentMeasure);
    currentMeasure = { chordText: '', lyricText: '' };
  }
  
  return doc;
}
```

**限制**：
- 仍需手動調整小節線位置
- 無法生成音符（仍需 OMR 或手動輸入）
- 複雜排版（跨行歌詞、重複段落）處理困難

### 方案 B：雙向同步編輯器

**概念**：
- 在 Score Studio 中新增「ChordPro 檢視」分頁
- 編輯 ChordPro 文字時，即時同步到 measures 陣列
- 編輯 measures 時，即時同步回 ChordPro 文字

**優勢**：
- 用戶可以選擇喜歡的工作流
- 保持兩種格式的同步

**挑戰**：
- 需要完整的雙向解析器
- 處理衝突（兩邊同時編輯）

### 方案 C：導入嚮導（最簡單）

**流程**：
1. 用戶貼上 ChordPro 文字
2. 系統顯示預覽（估算的小節分割）
3. 用戶確認/調整小節線位置
4. 生成初始 doc，後續在 Score Studio 編輯

**優勢**：
- 實現簡單
- 用戶有控制權
- 不會自動誤判

---

## 六、結論

### 為什麼無法直接整合？

| 原因 | 說明 |
|---|---|
| **1. 缺少解析器** | 沒有 `parseChordProToDoc()` 函式 |
| **2. 資料模型不同** | ChordPro 是文字流，Score Studio 是結構化 measures 陣列 |
| **3. 資訊含量不同** | ChordPro 無音符，Score Studio 需要音符 |
| **4. 節拍不確定** | 無法從文字自動判斷小節線位置 |
| **5. 語法映射複雜** | 重複段落、調性變更、臨時記號等難以映射 |

### 建議行動

1. **短期**：實作方案 C（導入嚮導），讓用戶可以貼上 ChordPro 並手動調整
2. **中期**：實作方案 A（解析器），支援基本的小節分割
3. **長期**：實作方案 B（雙向同步），提供完整的工作流選擇

### 技術債

目前 `applyChordProToDoc()` 只解析 metadata，不解析和弦/歌詞/小節結構。這是導致 ChordPro 無法進入 Score Studio 編輯器的根本原因。

---

**報告完成**：2026-10-17
**相關檔案**：
- `web/index.html` L90-109（ChordPro 編輯器 UI）
- `web/assets/app.js` L878-932（ChordPro 轉換函式）
- `web/assets/app.js` L1645-1662（頁籤切換）
