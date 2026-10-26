# Score Studio「直式自由編輯」報告書

| 欄位 | 內容 |
|---|---|
| 專案 | SheetMusicOMR v3.00（`D:\SheetMusicOMR_v3.00`） |
| 版本 | 報告書 v1.0（待核准） |
| 日期 | 2026-10-16 |
| 狀態 | **尚未編程**——本檔僅為「修改計劃＋測試與驗收標準」，經你核准後才動工 |
| 範圍紅線 | 只改 `#sola321-score` 中間白底黑字編輯區的內層；所有既有功能鍵一律不動；不新增功能區；資料模型與匯出格式不動 |

---

## 1. 專案原始需求（完整）

### 1.1 產品定位
把**紙本／PDF／圖片樂譜與各種文字譜檔**，轉成**可編輯的簡譜原稿**與**標準 MusicXML**，並提供**線上編輯**與**多格式匯出**。**全程本地化**：只監聽 `127.0.0.1`，不呼叫雲端、不上傳檔案、不做遙測。

### 1.2 輸入
| 路徑 | 說明 |
|---|---|
| PDF／圖片（OMR） | Tesseract `jianpu2` 幾何分析（**預設**；`ocrMode=jianpu2`）。只認**簡譜數字、歌詞、和弦記號，不做五線譜符頭**。標準答案測試譜 36/36 完全正確。 |
| 文字譜檔 | CSV／TSV／TXT／JSON／SON，不需 Tesseract。 |

### 1.3 輸出／匯出（`app/formats/`）
| 格式 | 檔案 | 說明 |
|---|---|---|
| Sola321 | `sola321.py` | 三行平文（和弦／簡譜／歌詞）、`｜` 小節線、等寬對齊、和弦紅色粗體 Consolas；保留轉位和弦、連音線、休止符、延音點、三連音；無表格框線、無段落標題 |
| MusicXML | `musicxml.py` | 標準匯出 |
| MIDI | `midi.py` | 同拍多音同時發聲（各音依自身 duration 結束） |
| Word | `word.py` | 樂譜文件 |
| 文字 | `text_export.py`／`text_import.py` | ChordPro 等文字譜 |

### 1.4 編輯器（現有三個＋和弦庫）
| 編輯器 | 定位 | 現況 |
|---|---|---|
| **ChordPro 文字**（`#chordpro-pane`） | 純文字檢視＋標頭編輯 | doc→文字自由；但存檔**只回寫 `#` 標頭**，小節內容不寫回；無結構功能鍵 |
| **簡譜格線**（`#score-pane`／`#v3-rows`） | 網格逐小節輸入 | 三層分層清楚；但**和弦、音符編輯有問題，只有歌詞自由** |
| **Score Studio**（`#sola321-pane`／`#sola321-score`） | 時間軸 SVG／Legacy 視覺編輯（圖2 目標） | 功能鍵最全；但**水平時間軸重疊、逐音符 overlay、試過 100+ 次** |
| **和弦庫**（右欄 `#chord-panel`） | 調性＋根音＋變體＋指法圖 | 點和弦→同時插入 ChordPro 游標＋選定小節 |

### 1.5 資料模型（三編輯器共用，**不可動**）
```
doc = { id, title, key, timeSignature, tempo, lyricist, composer, measures[] }
measure（legacy 欄）= { number, chordText, noteText, lyricText..4,
                        chordTicks, chordOffsets, noteTicks, lyricTicks,
                        beats, marks }
measure（event model 欄）= { melodyEvents, chordEvents, lyricTracks[4],
                        annotations, eventModelVersion }
雙向橋：syncLegacyToEvents / eventsToEvents→legacy / migrateAllMeasures
```
- 單位：`480 ticks = 1 四分音符拍`（`models.py expand_beats` 同單位）。
- 匯出/存檔全讀這套 `doc`；`Save` 只寫 `project.json`（atomic 備份於 `versions/`）。

### 1.6 環境约束
- GPU `GTX 860M`（Maxwell CC5.0，新版 PyTorch CUDA 不支援）→ **一律 CPU 模式**。
- 已停用 DeepSeek 付費；僅本地 ollama＋OpenRouter 免費模型。
- 固定埠 `8763`（`launcher.py --port 8763`）；健康檢查 `/api/health`。

---

## 2. 目前遇到的困難（完整）

### 2.1 各編輯器的「編輯性天花板」
| 編輯器 | 能做到 | 做不到（困難） |
|---|---|---|
| ChordPro 文字 | 複製/剪下/貼上/任意移動/新增下一行/刪除（純文字手感） | ① 存檔只回寫 `#` 標頭，小節行不會寫回 measures；② 無和弦圖/時值/段落/小節線等結構功能；③ 純文字看不出節拍位置 |
| 簡譜格線 | 三層分層、歌詞自由改 | **和弦、音符編輯有問題**：和弦要靠右欄和弦庫點、音符靠逐格 input；整行複製/移動/貼上做不到 |
| Score Studio 時間軸 | 功能鍵最全（時值/附點/三連音/臨時記號/八度/休止/刪除/段落/小節線/警示線/複撤銷/鍵盤/和弦庫） | **水平時間軸**：和弦行、歌詞行用**絕對定位疊在**音符行上（`layoutSola321ChordRows`＋`.sola321-ow`），內容多時**水平擠撞＝重疊**；編輯是**逐音符 overlay**（`openSolaNoteOverlay`），**無整行自由操作**；你已試過 **100+ 次**仍不理想 |

### 2.2 長期不變式（invariant）與它的衝突
- 目標布局是**三層垂直分層**：`chordTop < noteTop < lyricTop`（和弦在上、簡譜在中、歌詞在下，見 `HANDOFF.md` 驗收預期）。
- 但現有 Score Studio 是用**水平排 measure 盒＋垂直疊放**來滿足「三層」；一旦拍數/事件變多，水平方向就擠，疊放層就撞車 → **不變式難以穩定維持**，這正是 100+ 次嘗試仍卡住的核心。

### 2.3 版本演化與反覆（git 16 commits 佐證）
| commit | 內容 | 問題 |
|---|---|---|
| `f327d6e` SolaFlow 文字流排版 | 想把「文字流」做成排版 | 太複雜 |
| `6e4b61a` Flow 主編輯介面整合 | 以 Flow 為主 | — |
| `bacf576` 多事件資料模型 | noteText/noteTicks 平行陣列 | 資料一致性難保 |
| `86fd621`/`e8722cd`/`051e7ae`/`f445e25` | 連串 P0 資料完整性修復（多事件保留、跨小節、匯出修正、tick 排序、MIDI 同拍多音） | **資料層反覆出錯** |
| `8ad2323` | 6/8 拍號 measure tick 長度修正 | 拍號特例 |
| `35bc729`/`c602019`/`218fe5d` Phase A | 非破壞性候選修復引擎＋逐小節採用預覽 | 為 Flow 而建、複雜 |
| `4b2e188` | 簡譜格線**三層重疊**修復：`.v3-chord-slot` 絕對定位改 scope 到 Score Studio | **重疊問題再次出現** |
| `e127bfe`（今日） | **移除 Flow＋Phase A**，預設視圖改 Score Studio | 放棄文字流路線 |

### 2.4 困難總結（決策依據）
1. 把「**水平時間軸**」做成自由編輯，會持續撞車（重疊＋資料複雜），100+ 次無解。
2. 純文字（ChordPro）自由，但**缺結構功能**、且小節行不寫回。
3. 折衷需求：要 **「文字的自由」（複製/剪下/貼上/移動/增刪行）** ＋ **「結構功能可調用」（和弦圖/時值/段落/小節線等）** ＋ **「三層不重疊」**。
4. ⇒ **新方案不走水平時間軸，改走「直式、一行一小節、三層分車道」**：垂直分層從結構上杜絕重疊；保留既有功能鍵；拿到文字的自由。

---

## 3. 新方案完整計劃：Score Studio「直式自由編輯」

### 3.1 目標
在 Score Studio 中間編輯區（`#sola321-score`）**新增第三視圖「直式自由」**（與既有「格線／時間軸」並列，**保留格線/時間軸**）：
- 樂譜排成**直式、一行一小節**；每小節＝**三條垂直堆疊的車道**（上：和弦軌｜中：簡譜音符軌｜下：歌詞軌）。
- 三車道**物理分層、不用絕對定位疊放** → **結構上不可能重疊**（滿足 `chordTop<noteTop<lyricTop` 不變式）。
- 每個「小節行」可**複製／剪下／貼上／拖曳上下移動／新增下一行／刪除**（Word 式自由）。
- **既有功能鍵一字不改**，且能照常調用（靠既有游標/目標模型＋DOM 契約）。

### 3.2 範圍紅線（照你指示）
| 做 | 不做 |
|---|---|
| 只改 `#sola321-score` 內層渲染＋編輯方式 | 不改資料模型／event model |
| 加「直式」視圖＋行操作 | 不改匯出格式（Sola321/MusicXML/MIDI/Word） |
| 保留所有功能鍵 | 不新增工具列／面板／功能區 |
| 格線/時間軸**保留可用** | 暫不碰 ActiveNote／混合預覽（維持 disabled） |

### 3.3 中間區結構（「直式」視圖）
```
#sola321-score
 ├─ .sola321-score-header   ← 既有（標題/作詞作曲/1=調/拍號/♩ 速度）不改
 ├─ .sola321-viewtoggle     ← 既有「格線／時間軸」＋新增「直式」一鈕
 └─ .sola321-vertical-body  ← 新：直式三車道
      └─ .sola321-vmeasure[data-mi]  ×N（每小節一行）
           ├─ .sola321-v-chordlane   和弦軌：指法圖（renderChordSvg + chords/{inst}/*.svg）＋和弦槽 picker
           ├─ .sola321-v-notelane    簡譜軌：數字＋上/下點＋下劃線＋附點＋三連（車道格內打字）
           ├─ .sola321-v-lyriclane   歌詞軌：最多 4 子行
           └─ .sola321-v-rowops      行操作鈕（複製/剪下/貼上/上移/下移/新增下一行/刪除，懸停顯示）
```
- 行操作作用於 `doc.measures`（整小節为单位複製/移動），走 `solaPushUndo` → **可複撤銷**。
- 三車道用 **flex/block 垂直堆疊**（非 `position:absolute` 疊放）→ 重疊從源頭消失。

### 3.4 功能鍵如何照舊被調用（**不改它們**）
| 既有機制 | 直式視圖如何接（不改函式、只保契約） |
|---|---|
| `solaApplyOp(op,key)`：時值/附點/三連音/臨時記號/八度/休止/刪除/小節線 | 照舊對 `solaGetCursor()`（mi/nti）下指令；游標落在**直式車道格**上即可生效 |
| `solaToggleSection`/`solaToggleMark`：段落/結構記號 | 照舊對 `solaGetTargetMI()`（目標小節）寫 `m.marks` |
| 和弦庫 `insertChordIntoScoreGrid` | 照舊對 target 小節 `m.chordText` 插入；顯示改為「和弦軌」指法圖 |
| 鍵盤快捷（A/. R E Q W 0 ↑↓ Del、數字） | 照舊；focus 在直式區時對應同游標 |
| DOM 契約 `.sola321-measure[data-mi]`／`.sola321-note-char[data-mi][data-nti]`／`.sola321-cursor`／`.sola321-measure-target` | **直式行也產出這批 class＋data 屬性**，讓既有綁定/高亮/游標零改動沿用 |
| 複撤銷 `solaPushUndo`／↶↷、保存、匯出、轉調 | **完全不碰** |

### 3.5 檔案層級修改清單（只列要動的）
| 檔案 | 改動 | 不動 |
|---|---|---|
| `web/assets/app.js` | `renderSola321Score` 加「直式」分支；新增 `renderSola321MeasureVertical`＋`solaRowCopy/Cut/Paste/MoveUp/MoveDown/Add/Delete`；行操作綁定 | `solaApplyOp`/`solaToggleMark`/`solaToggleSection`/`solaGetCursor`/`solaGetTargetMI`/`insertChordIntoScoreGrid`/`bindChordSlotPickers`/鍵盤快捷/格線與時間軸分支 |
| `web/index.html` | `.sola321-viewtoggle` 加「直式」鈕＋行操作鈕 | 其餘 HTML、其他 tab、和弦庫、工具列 |
| `web/assets/styles.css` | 新增 `.sola321-vertical-*`（三車道白底黑字） | 既有 `.sola321-*`／`.v3-*`／和弦庫樣式 |

---

## 4. 測試與驗收標準

### 4.0 總則（你的驗證鐵律）
- **ad-hoc 驗證**：用 `tempfile`＋`hermes-verify-` 前綴檔案，**跑完即清理**。
- **逐項對照原稿**：歌詞關鍵詞、和弦完整、簡譜特徵碼，不可用單一指標或模擬結果替代。
- 全部驗收門（§4.6）**全綠**才算完成。

### 4.1 功能鍵回归矩阵（切「直式」視圖後逐項）
| 功能鍵 | 操作 | 期望 | 驗證方法 |
|---|---|---|---|
| 和弦圖 | 右欄和弦庫點 C | 插入 target 小節「和弦軌」、指法圖正確 | `.sola321-v-chordlane` 含 C＋`chords/guitar/C.svg` 存在 |
| 時值 D/F/G | 選音符按 D/F/G | 該音符 `under`＝0/1/2 | `solaDecomp` 反解 `under` |
| 附點 / 三連音 | 選音符按 `.`/`R` | `dotted`/`triplet` 翻轉 | `solaDecomp` 反解 |
| 臨時記號 ♯/♭/♮ | 選音符按 | `acc`＝# / b / 清空 | `solaDecomp` 反解 |
| 八度 ↑/↓ | 選音符按 | `above`/`below` 點增減 | `solaDecomp` 反解 |
| 休止 0 | 選音符按 | 該音＝`0` | noteText |
| 刪除 ⌫ | 選音符按 | 該 token 移除 | `solaTokens` 長度 -1 |
| 段落（副歌） | 選 target 小節選副歌 | `m.marks` 含「副歌」 | `m.marks` |
| 小節線 ＋│/－│ | 游標拆/併 | 小節數 +1/-1、音符分組正確 | `measures.length`＋noteText 分組 |
| 警示線 ⚠ | 開關 | 短小節紅線開/關 | CSS class 切換 |
| 複撤銷 ↶/↷ | 做 5 步→復原→重做 | 還原/重做正確 | doc 快照比對 |
| 鍵盤快捷 | A/. R E Q W 0 ↑↓ Del 數字 | 同對應功能鍵 | 同 § 各欄 |
| 轉調 | 目標調 | 和弦/音符移調 | 同既有 `/transpose` |
| 保存 | `btn-sola321-save` | `project.json` 更新 | 檔 diff |
| 匯出 SoLa321/MusicXML/MIDI | 各跑 | 三格式內容正確 | 與原稿逐項對照 |

### 4.2 不重疊驗證（核心驗收）
1. **結構層**：直式視圖下**不 call `layoutSola321ChordRows`、無 `.sola321-ow` 覆蓋**（`grep` 直式分支不引用這兩者）→ 重疊從源頭消失。
2. **幾何層**：量測同小節「和弦軌／簡譜軌／歌詞軌」三車道 `getBoundingClientRect`，**同 y 區段不相交**（車道垂直堆疊，`chordTop < noteTop < lyricTop`）。
3. **極端層**：塞滿 4 拍全音符＋4 行歌詞＋3 個並列和弦，三車道仍不重疊（水平變寬即可捲，垂直絕不疊）。

### 4.3 Word 行操作驗證
- 複製／剪下／貼上／上移／下移／新增下一行／刪除 各測一次：
  - `doc.measures` 順序與內容正確；
  - 每步走 `solaPushUndo` → **↶ 可逆**；
  - 重繪後游標（`sola321-cursor`）與目標小節（`sola321-measure-target`）落在正確行。

### 4.4 資料回圈（存檔可還原）
- 直式視圖改完 → 存檔 → 重新載入 → 匯出 SoLa321/MusicXML/MIDI；與改前**逐項一致**（**除你故意改的**），歌詞關鍵詞／和弦完整／簡譜特徵碼全對。

### 4.5 回归（不影響既有）
- 簡譜格線／ChordPro 頁籤逐項照舊；格線／時間軸視圖照舊；OMR 導入照舊。
- `node --check web/assets/app.js`＋保留模組通過；`create_app()` 建路由通過；HTTP `/api/health` 200。

### 4.6 驗收門（全綠＝完成）
| 門 | 判定 |
|---|---|
| **A 不重疊** | §4.2 三項（結構/幾何/極端）全過 |
| **B 行操作可逆** | §4.3 全操作可複撤銷、順序內容正確 |
| **C 功能鍵全通** | §4.1 矩阵每一列 PASS |
| **D 資料回圈一致** | §4.4 三格式逐項一致 |
| **E 無回归** | §4.5 既有編輯器/匯出/OMR 全照舊 |

### 4.7 執行方式（PowerShell 一鍵，你的偏好）
- 驗證腳本統一 `hermes-verify-*` 前綴＋tempfile，**跑完自清**；我用 Windows 格式路徑（`C:\...`／`D:\...`）給一鍵指令，不給複雜 bash。

---

## 5. 風險與「不做」邊界
1. **暫不碰** ActiveNote／混合預覽（維持 disabled），避免範圍膨脹。
2. 行操作只做**小節級**（整小節複製/移動）；**不做** beat 級拖拽改時值——時值仍靠功能鍵 `A/S/D/F/G/H`。
3. 直式視圖的「直式車道」是**新視覺分支**；格線/時間軸**原封保留**，兩者可互切，資料同一份。
4. 所有改動集中在 3 檔（app.js 加分支＋新函式、index.html 加鈕、styles.css 加 `.sola321-vertical-*`），**每檔都能 `git revert` 單筆回溯**。

---

## 6. 待你核准的決策點（4 點）
| # | 決策 | 我的預設 |
|---|---|---|
| 1 | 加「直式」為第 3 視圖、**保留格線/時間軸**？ | 是（保留） |
| 2 | 「行」的單位＝**一小節**（和弦＋簡譜＋歌詞整列可複製/移動）？ | 是（一小節） |
| 3 | 行操作鈕放**中間區懸停顯示**（不另開獨立工具列）？ | 是（懸停顯示） |
| 4 | 這版只做「**直式自由編輯＋不重疊**」，暫不碰 ActiveNote/混合預覽？ | 是 |

---

## 附錄：關鍵函式／檔案索引（供核准後動工對照）
| 主題 | 位置 |
|---|---|
| 中間區渲染（兩分支） | `app.js: renderSola321Score`(2728)、`renderSola321Measure`(2836) |
| 游標/目標模型 | `solaGetCursor`(2457)、`solaGetTargetMI`(2544)、`solaHighlightTarget`(2550) |
| 功能鍵下指令 | `solaApplyOp`(2570)、`solaToggleMark`(2672)、`solaToggleSection`(2698) |
| 和弦插入 | `insertChordIntoScoreGrid`(668)、`renderV3ChordSlots`(389)、`bindChordSlotPickers`(445) |
| WYSIWYG 逐音符 | `openSolaNoteOverlay`(3400)、`bindSola321Inputs`(3466) |
| 重疊源（不改，直式避開） | `layoutSola321ChordRows`(202)＋`.sola321-ow` 絕對定位 |
| 簡譜 token | `solaTokens`(1687)、`solaDecomp`(1751)、`solaRecomp`(1771)、`solaBuildToken`(1705) |
| 複撤銷 | `solaSnapshot`/`solaPushUndo`/`solaUndo`/`solaRedo`(2469–2502) |
| 和弦圖/資料庫 | `renderChordSvg`(73)、`loadChords`(62)→`chords.json`＋`chords/{guitar,ukulele}/*.svg`（337/141 張） |
| 匯出 | `app/formats/{sola321,musicxml,midi,word}.py` |
| OMR | `app/omr/`（預設 `jianpu2` 幾何分析） |

> 核准 §6 四點後，我依 §3 動工、依 §4 驗證；未核准前**不寫任何程式碼**。
