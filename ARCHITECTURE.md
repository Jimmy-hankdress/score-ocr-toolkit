# ScoreForge SolaFlow 架構圖

```mermaid
flowchart TB
    %% ===== DATA LAYER =====
    subgraph DataLayer [資料層]
        SD[ScoreDocument\n(models.py)]
        SM[ScoreMeasure]
        SB[ScoreBeat]
        EO[eventOverrides]
        FD[SolaFlowDoc\n(新增)]
        FE[SolaFlowEvent[]\n扁平事件流]
        MB[MeasureBounds[]\n小節邊界 tick]
    end

    %% ===== PERSISTENCE =====
    subgraph PersistLayer [持久化層]
        PS[projects.py\nsave/load_document]
        DB[(db.sqlite\n專案索引)]
        FS[檔案系統\nproject.json + versions/]
        EXP[7 格式匯出器\nmusicxml/midi/word/...]
    end

    %% ===== LAYOUT ENGINE =====
    subgraph LayoutEngine [版面引擎 (新)]
        FL[flow-layout.js]
        TK[tokenize()\n簡譜/歌詞/和弦解析]
        CM[computeMeasureBounds()\n小節邊界計算]
        LF[layoutFlow()\n文字流排版 + 插入小節線]
        CC[collisionResolution()\n視覺碰撞微調\n不改 tick]
    end

    %% ===== EDITOR =====
    subgraph Editor [編輯器 (新)]
        FE2[flow-editor.js]
        SL[selection\n點選/範選]
        DR[drag\n拖曳重排 → 新 tick]
        ED[edit\n就地編輯 contenteditable]
        UD[undo/redo\nFlowEvents 深拷貝堆疊]
        KB[keyboard\nEnter/Delete/Arrow]
    end

    %% ===== RENDERER =====
    subgraph Renderer [渲染器 (新)]
        FR[flow-renderer.js]
        HTML[單一 HTML 字串\ninline spans]
        CSS[flow.css\n單一樣式表]
    end

    %% ===== LEGACY (保留) =====
    subgraph Legacy [既有模組 (唯讀/輸出)]
        OM[OMR Pipeline\napp/omr/, app/scorestudio/]
        SV[syncLegacyToEvents\nparseMeasureToEvents]
        MR[measureToTimeline]
        LR[layoutMeasureEvents]
        RR[renderSola321Score\n雙模式]
    end

    %% ===== FLOWS =====
    SD -->|to_dict| PS
    PS -->|atomic write| FS
    PS -->|upsert| DB
    FS -->|load| PS
    PS -->|from_dict| SD
    SD -->|餵入匯出器| EXP

    %% New flow
    SD -->|migrateToFlow()| FD
    FD -->|events + bounds| FL
    TK --> FL
    CM --> FL
    LF --> FR
    CC --> LF
    FR -->|HTML string| HTML
    HTML -->|注入| DOM[瀏覽器 DOM]

    %% Editor interaction
    DOM -->|事件| FE2
    SL --> FE2
    DR -->|計算新 tick| FE2
    ED -->|更新 content| FE2
    UD --> FE2
    KB --> FE2
    FE2 -->|mutate FlowEvents| FD
    FE2 -->|push undo| UD
    FD -->|重新排版| FL

    %% Legacy sync (單向：Legacy → Flow，不回寫)
    SD -.->|syncLegacyToEvents| SV
    SV -.->|Event Model| LR
    LR -.->|renderX/Y| RR
    RR -.->|HTML| DOM

    %% Styling
    classDef new fill:#e8f5e9,stroke:#2e7d32,stroke-width:2px;
    classDef legacy fill:#fff3e0,stroke:#ef6c00,stroke-width:1px,stroke-dasharray: 5 5;
    classDef data fill:#e3f2fd,stroke:#1565c0;
    classDef persist fill:#fce4ec,stroke:#c2185b;

    class FD,FE,MB,FL,LF,CC,FE2,SL,DR,ED,UD,KB,FR,HTML,CSS new;
    class SV,MR,LR,RR,OM legacy;
    class SD,SM,SB,EO data;
    class PS,DB,FS,EXP persist;
```

---

## 關鍵資料流說明

### 1. 單向遷移：Legacy → Flow（啟動時）
```
ScoreDocument.measures[]
    → parseMeasureToEvents() (既有邏輯)
    → Event Model (melodyEvents, lyricTracks, chordEvents)
    → flattenToFlowEvents() (新)
    → SolaFlowDoc { events[], measureBounds[] }
```
- **不回寫** Legacy 欄位，避免雙主源
- `eventOverrides` 直接合併進 `FlowEvent.tick`

### 2. 編輯迴路：Flow → Layout → DOM → Editor → Flow
```
FlowEvents (按 tick 排序)
    → layoutFlow() 計算每個 span 的視寬
    → 插入小節線 span (每 measureBounds tick)
    → 產出單一 HTML 字串
    → DOM 更新 (單次 innerHTML 或細粒度 diff)
    → 使用者操作 → 產生新 tick / 新內容
    → 更新 FlowEvents → push undo → 重新 layoutFlow()
```

### 3. 匯出：Flow → Legacy → Exporter
```
FlowEvents
    → eventsToLegacy() (既有邏輯)
    → ScoreDocument (含 beats[] 重建)
    → 7 格式匯出器 (零修改)
```

### 4. 持久化：Flow → project.json
```
SolaFlowDoc.to_dict()
    → { flowVersion, events[], measureBounds[] }
    → 合併進 ScoreDocument (新增欄位)
    → projects.save_document() (原子寫入、版本備份)
```

---

## 檔案對應表

| 新檔案 | 對應既有模組 | 職責 |
|--------|--------------|------|
| `app/models.py` (擴充) | `ScoreMeasure.eventOverrides` | 新增 `SolaFlowDoc`, `SolaFlowEvent` dataclass |
| `app/projects.py` (擴充) | `save/load_document` | 新增 `load_flow`, `save_flow`，雙向同步 |
| `web/assets/flow.js` | `app.js` 中 Timeline 相關 | **單一** 渲染/編輯/排版入口 |
| `web/assets/flow-layout.js` | `layoutMeasureEvents`, `layoutSystems` | 文字流排版 + 小節線插入 |
| `web/assets/flow-editor.js` | Phase 6D 選取/拖曳/刪除/Undo | 選取、拖曳、就地編輯、鍵盤 |
| `web/assets/flow.css` | `styles.css` 中 Timeline 樣式 | 單一樣式表，無軌道、無 absolute |
| `web/flow.html` | — | 獨立原型頁面 (可直接開啟驗證) |

---

## 介面契約 (供並行開發)

### SolaFlowEvent (TypeScript)
```typescript
type FlowEventType = 'chord' | 'note' | 'lyric' | 'barline';

interface SolaFlowEvent {
  uid: string;              // 穩定 ID：fnv36(type|tick|content|#seq)
  type: FlowEventType;
  content: string;          // 和弦名 / 簡譜 token / 歌詞字 / '|'
  tick: number;             // 絕對 tick (0 起算，480 = 1 quarter)
  // 視覺輔助 (layout 產出，不持久化)
  renderX?: number;         // px, 相對容器左緣
  renderWidth?: number;     // px
  lineIndex?: number;       // 換行後所在行
}
```

### SolaFlowDoc
```typescript
interface SolaFlowDoc {
  flowVersion: number;      // 1
  timeSignature: string;    // '4/4'
  ticksPerBeat: number;     // 480
  events: SolaFlowEvent[];  // 已按 tick 排序
  measureBounds: number[];  // 每小節起始 tick (含第 0 小節 = 0)
  // Legacy 同步欄位 (選填，供舊匯出器)
  legacy?: ScoreDocument;
}
```

### Layout Engine API
```typescript
// 入口
function layoutFlow(doc: SolaFlowDoc, containerWidth: number): FlowLayoutResult;

// 輸出
interface FlowLayoutResult {
  html: string;                    // 完整單一 HTML 字串
  eventPositions: Map<string, {    // uid → 視覺位置
    x: number, y: number, 
    width: number, height: number,
    line: number
  }>;
  measureLines: number[];          // 每小節落在哪一行
}
```

---

## 回滾機制

| 階段 | 回滾指令 | 影響範圍 |
|------|----------|----------|
| Phase A (靜態渲染) | `git checkout master -- app/models.py web/assets/app.js` | 僅新檔，舊編輯器不受影響 |
| Phase B (編輯器) | 同上 + 刪除 `flow*.js` | 同上 |
| Phase C (匯出/遷移) | `git checkout master` | 完整回滾，`project.json` 相容 |

**關鍵**：`project.json` 格式**不破壞** — 新欄位 `flowVersion/events/measureBounds` 僅在新編輯器啟用時寫入，舊編輯器載入時忽略。