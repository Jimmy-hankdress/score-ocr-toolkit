# SheetMusicOMR v3.00 — 階段 4.2 Least Privilege 驗收：小節操作（一）新增／刪除／上移／下移

**狀態**：未提交 Git、未修改 server.py、未碰正式資料。tracked 變更僅 `web/assets/app.js` ＋ `web/assets/styles.css`。
**Git base**：`e127bfe refactor(flow): ...`
**測試環境**：localhost:8763（CPU）。Headless Chrome、獨立 `--user-data-dir`（不碰使用者既有 profile）。

---

## 1. git diff --stat + 目標檔案實際差異

```
 web/assets/app.js     | 238 +++--------- (tracked 修改)
 web/assets/styles.css |  50 ++++
 2 files changed, 278 insertions(+), 10 deletions(-)
```
`git diff --name-only` => 僅 `web/assets/app.js`、`web/assets/styles.css`（兩檔 tracked）。所有腳本為 untracked（另節）。

### styles.css — 全新增（未改既有規則）
直式 `.sola321-vmeasure`/`三車道`/`.sola321-v-toolbar`/`.sola321-v-opbtn`/`.sola321-v-empty-note`，第二批 `.sola321-v-opbtn-mv` 與 `.sola321-v-measurehead { display:flex }`。惟 `.sola321-v-measurehead` 在樣式表中出現兩次（原 `align-items:baseline` vs 新 `align-items:center`）——屬冗餘、無行為衝突，建議清理。

### app.js — 關鍵實際差異（git 核對）
- **Snapshot/Undo/Redo（additive，backward-compat）**：`solaSnapshot`（L2469）加 `cursor:{mi,nti}`；`solaRestore`（L2483）加游標還原（舊快照無 cursor 時走既有 clamp）；`solaUndo`/`solaRedo`（L2496/L2503）不變。
- **直式小節操作**：`solaDefaultMeasure`(L2516) → 依 `timeSignature` 動態建拍（3/4→3、4/4→4…）；
  `solaAddMeasure`(L2531)／`solaDeleteMeasure`(L2545) — Batch 1 — `solaMoveMeasure`(L2566) + `solaMoveUp`(L2586) + `solaMoveDown`(L2587) — Batch 2 — 皆「只動 `state3.doc.measures`＋renumber，絕不重跑 `parseMeasureToEvents/syncLegacyToEvents`」。
  - `solaMoveMeasure` 邊界（首節 up／末節 down）為 no-op：不入 undo、不清 redo、不改資料。
  - `solaDeleteMeasure` 游標重定位：刪空→0/0；刪游標所在→補位；刪之前→mi−1；刪之後→不變。
- **UI**：直式 `measure head` 加 `↑ 上移`/`↓ 下移`/`－ 刪除` 按鈕（`data-vop="up/down/del" data-mi`），data-vop 委派綁定；空文件「＋ 新增小節」入口；門控 probe `__solaProbe/SetCursor/MeasureAt/SetOverride` + `marks`（僅 `?probe=1`）。

---

## 2. 小節操作函式表（實作／未實作）

| 操作 | 函式 | 行 | 狀態 |
|---|---|---|---|
| 新增 | `solaAddMeasure` / `solaDefaultMeasure` | L2531 / L2516 | ✅ 已實作 |
| 刪除 | `solaDeleteMeasure(mi)` | L2545 | ✅ 已實作 |
| 上移 | `solaMoveUp(mi)` → `solaMoveMeasure(mi,'up')` | L2586 / L2566 | ✅ 已實作用 |
| 下移 | `solaMoveDown(mi)` → `solaMoveMeasure(mi,'down')` | L2587 / L2566 | ✅ 已實作用 |
| 複製 | — | — | ⏳ 未實作（第三批） |
| 剪下 | — | — | ⏳ 未實作（第三批） |
| 貼上 | — | — | ⏳ 未實作（第三批） |

---

## 3. Undo/Redo 結果一覽（真實應用程式函式，UI 按鈕驅動）

| 操作 | 測試指令 | Undo | Redo | 狀態 |
|---|---|---|---|---|
| **新增** | b1 T3 / T4（`solaAddMeasure`→undo→redo） | ✅ count 6/8、cursor 0/2、redoLen 2 | ✅ count 8、cursor 2 | PASS |
| **刪除** | del D4–D8（`solaDeleteMeasure`→undo→redo→undo） | ✅ M1 含 melodyEvents(4) uid+eventOverrides[uid]+marks 完整恢復；三節 source hash 全=before；數號 1,2,3；游標回 mi=1 | ✅ 再次回到刪除態（count=2，M0/M2 hash=before） | **11/11 PASS** |
| **上移/下移** | b2 M9（`solaMoveMeasure` undo×2） | ✅ marks 順序逐步還原 | —（redo 僅測 undo） | PASS |
| 複製/剪下/貼上 | — | 未實作 | 未實作 | ❌ 三批未到 |

> del 測試採「content hash」（排除 `number`，因 renumber 為預期行為）。刪除後 M1 旁的 M0/M2 source hash 完全不變；Undo 恢復 M1 的 `melodyEvents` uids + `eventOverrides[e1n0ct4i]={duration:'half'}` + `marks=M1`** 全檔 JSON 一致**；Redo 回到刪除狀態；再 Undo 可再恢復。

---

## 4. 全部測試 — 完整名稱、斷言與結果

### Suite b1 — 新增／刪除／空文件／三檢視（`tools/hermes-verify-phase4-b1.js`，專案 `doc_62821712c5e4`） — 13/13 PASS
| 項 | 名 | 主要斷言 | 結果 |
|---|---|---|---|
| T0 | baseline | count=6, numbers=1..6, ts=4/4 | PASS |
| T1 | add | count=7, renumber, cursor→新節(1), 未生成 eventModelVersion | PASS |
| **T1b** | beats-by-ts | **client** measures[1].beats=4（4/4）；⚠️ server 持久化=1（空節依文字重建=1，既有行為） | PASS（僅 client） |
| T2 | add-again | count=8, cursor=2 | PASS |
| T3 | undo-restore | undo×2→count=6, cursor=0, redoLen=2 | PASS |
| T4 | redo | redo→count=8, cursor=2 | PASS |
| T5 | del-first | count=7, cursor 索引−1 | PASS |
| T6 | empty-doc | count=0, mi=0, nti=0, api=0（無越界） | PASS |
| T7 | add-on-empty | 空檔加→count=1, cursor=0 | PASS |
| T8 | del-cursor-measure | 刪游標所在→count=1, cursor 落補位 | PASS |
| T9 | save-reload | `?project=&probe=1` 重載 count=1 一致 | PASS |
| T10 | 3view | grid/timeline/vertical model+DOM 各=1 | PASS |
| T11 | console | 無 `|svg`、無錯誤 | PASS |

### Suite b2 — 上移／下移（`tools/hermes-verify-phase4-b2.js`，專案 `doc_62821712c5e4`） — 12/12 PASS
| 項 | 名 | 主要斷言 | 結果 |
|---|---|---|---|
| M0 | baseline | 6 節 marks=A,B,MVMARK,D,E,F；MVMARK melodyUid 生成；覆寫值設上 | PASS |
| M1 | move-down | 順序→A,B,D,MVMARK,E,F；numbers=1..6 | PASS |
| M2 | move-up | 順序回A,B,MVMARK,D,E,F；numbers=1..6 | PASS |
| M3 | first-up-noop | 順序不變、undo/redo 不增清 | PASS |
| M4 | last-down-noop | 順序不變、undo/redo 不增清 | PASS |
| M5 | cursor-on-moved | mi 2→3（被移節跟隨） | PASS |
| M6 | cursor-on-moved-up | mi 3→2 | PASS |
| M7 | cursor-on-other | mi 0 不變 | PASS |
| M8 | uid-override-invariant | MVMARK 前後 JSON 完全相同（uids+覆寫值未重建） | PASS |
| M9 | undo-steps | 2 移後順序≠起，undo×2 回復原序 | PASS |
| M10 | save-reload | reload marks 順序一致（legacy） | PASS |
| M11 | console | 無 `.svg`（✙ 10 個 400，獨立報告） | PASS |

### Suite del — 刪除 Undo/Redo（`tools/hermes-verify-phase4-del.js`，專案 `doc_57c9d6eb921c`） — 11/11 PASS
D0 setup／D1 delete／D2 他節不變（hash對比）／D3 游標合理／D4 undo 三節+數號全還原／D5 被刪節**完整 JSON**（melodyEvents+uids+eventOverride+marks）恢復／D6 undo 游標／D7 redo=再次刪除／D8 再 undo 恢復／D9 stack/游標無異常／D10 server 持久化分開報告。

### 既有回歸
`node phase15/test_runner.js` → **24/24 PASS**。

---

## 5. beats 客戶端／伺服器正規化 — 方案（未修改 server）

**現象**：客製建 4 拍空小節（4/4）→存檔→伺服器依 `noteText` 重建 `beats`，空節(noteText='')→1 拍，覆蓋 client 值。**僅影響空小節；有 NoteText 的小範重建正確。**

**建議（皆為獨立 server 任務，不擴大至本批）**：
- **A（推薦，最小改動）**：`server.py` save/load：若 `measures[i].beats` 為非空陣列則**保留**；缺失/空才依 noteText 重建。4 拍空節即可持久。
- **B**：schema 明確 `beats` 為持久欄位、server 一律尊重。
- **C**：接受空小節 1 拍視覺差異（無音符→僅空轎顯示），記錯不治。
- **D（混合）**：noteText 非空時依文字重建；空時保留 client beats。

---

## 6. 正式資料／Git／產物再確認

- **正式資料**：YL（7）＋DC（4）＝11 個 `project.json`，mtime 全＝ `1791971212`（＝ session 基線，**未改**）。
- **Git**：**未 commit 也未 reset/clean/stash**；tracked 變更僅 `app.js`＋`styles.css`；最新 commit 仍 `e127bfe`。
- **測試產物保留**：`tools/hermes-verify-phase4-b1.js`／`-b1-base.json`／`-b1-result.json`／`-b2.js`／`-del.js`／`-del-result.json` + 專案 `doc_62821712c5e4`(b3)／`doc_57c9d6eb921c`／`hermes-verify-phase3-6c3bc5bd02e2` 皆留存。
- **_jsdom_test/／build/／.bak_***：預存未追蹤，未動。

---

## 🔴 發現：含 event-model 的 doc 存檔 400（既有，超出本批）

- `PUT /api/projects/{id}`（`saveCurrentDoc` 送完整 `state3.doc`，含 client 重建的 `melodyEvents`/`eventOverrides`/`eventModelVersion`）→ **400 「Invalid document structure: list index out of range」**。
- 證據：乾淨 doc（無 event model）做移動＝0 個 400（存檔正常）；MVMARK/刪測試 doc（有 event model）→存檔 400（4~10 次）。curl 以相同 event 欄位 PUT 反而 200 ⇒ 差異在**完整 client payload**（`collectV3ToDoc`/`applyFlowToDoc` 產出）被 server 驗證取走。
- **影響**：client 端 Add/Delete/Move 的 **Undo/Redo 完整驗證皆 PASS**（fire-and-forget save 不影響 client model）；惟**含 event-model doc 的伺服器持久化失敗**（順序/marks 僅靠前一次成功的 legacy save 殘留，不算持久化）。須另開 server 任務修 save 驗證；**不在本批改動**。
- **結論**：「客戶端小節操作邏輯 + Undo/Redo」**通過**；「event-model doc 之存檔重載」**見仁於此 400 先標示 BLOCKED**，待 server 修正。
