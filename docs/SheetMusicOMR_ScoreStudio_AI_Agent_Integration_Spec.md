\# SheetMusicOMR v3.00：ScoreStudio 離線編輯器整合總規格



> \*\*任務模式：非破壞式升級。\*\*

>

> 本文件是交給本機 AI Coding Agent 的唯一主規格。請依序執行、逐階段驗證、保留舊版，禁止自行縮減核心需求、捏造 OMR 結果，或將尚未通過測試的功能宣稱為完成。



\---



\## 0. 任務摘要



請在下列既有專案中新增一套現代化、離線可用、可與舊版並存的樂譜編輯器：



```text

D:\\SheetMusicOMR\_v3.00

```



新編輯器名稱：`ScoreStudio`。



目標是將既有 OMR 匯入後的簡譜、和弦、歌詞資料，載入為可視化、可鍵盤快速輸入、可滑鼠選取、可播放、可校正、可匯出的樂譜專案；整體互動要接近現代網頁樂譜編輯器的低摩擦體驗，但不得複製任何第三方網站的原始碼、素材或受保護內容。



系統必須保留並持續支援舊版編輯器；新版僅能在通過驗收後成為預設入口。



\---



\## 1. 絕對約束



\### 1.1 既有系統事實



以下是既有 SheetMusicOMR v3.00 的已知條件，任何實作都必須相容：



\- 專案為 Windows 11 本機離線工具。

\- 後端使用 Python + FastAPI。

\- 前端以 Vanilla JavaScript 為主。

\- 預設僅監聽 `127.0.0.1:8756`。

\- 支援 PDF、JPG、PNG、CSV、TSV、TXT、JSON、SON 等來源；PDF 可能先轉為高解析影像。

\- 使用 Tesseract 進行簡譜數字、歌詞和文字 OCR。

\- 可輸出 MusicXML、JSON、TSV、TXT。

\- 已有簡譜、和弦、歌詞的可編輯流程，但舊編輯器互動較簡單。

\- 系統必須完全離線：無 CDN、無登入、無雲端 API、無遙測、無背景外連。

\- OMR 無法辨識或結果不確定時，絕不可憑空補造音符、歌詞、時值、和弦或五線譜資料。

\- 高八度點的 OCR 已使用特定穩定修正邏輯；中文歌詞 OCR 需比較原尺寸與放大尺寸的結果。不得為了 UI 升級而替換或弱化這些既有 OMR 邏輯。



\### 1.2 禁止事項



禁止：



\- 刪除、覆寫或破壞現有 Legacy Editor。

\- 直接修改既有 OMR／Tesseract／PDF 轉圖主流程，除非該階段有明確測試證明必要且回歸測試全數通過。

\- 以單一 `<textarea>`、HTML 表格或純絕對定位文字假裝樂譜編輯器。

\- 將一張圖片、PDF 預覽或 Canvas 截圖當成可編輯樂譜。

\- 對未知 OMR 結果自動假定為四分音符、常見旋律、常見和弦或猜測歌詞。

\- 將歌詞、和弦只儲存為畫面 X/Y 座標；它們必須與時間事件或拍點結構化關聯。

\- 讓新模組從網路下載 CDN、字型、JavaScript、CSS、音色或其他執行資源。

\- 只做「看起來可以」的假按鈕或 mock 資料。

\- 未完成 MusicXML 實測匯出前宣稱匯出功能完成。

\- 新版失敗時沒有回到 Legacy Editor 的方法。



\### 1.3 成功標準



完成後，使用者可在本機：



1\. 匯入既有 OMR 專案或 PDF/JPG 辨識結果。

2\. 於新 ScoreStudio 查看簡譜、歌詞、和弦及原圖對照。

3\. 用鍵盤與滑鼠修正音符、節奏、歌詞、和弦、小節與段落。

4\. 看到未知、低信心、未滿拍、超拍等明確警告。

5\. 播放旋律並以游標高亮確認。

6\. 自動儲存、復原、重做、建立快照並回復版本。

7\. 匯出 JSON、TSV、TXT、MusicXML。

8\. 需要時安全切回 Legacy Editor。

9\. 在斷網狀態下完整使用所有承諾的功能。



\---



\## 2. 先執行盤點：禁止立刻修改



\### 2.1 第一階段只讀分析



首先，請對 `D:\\SheetMusicOMR\_v3.00` 進行完整盤點，但這個階段\*\*不得修改任何程式檔\*\*。



排除：



```text

.venv

node\_modules

\_\_pycache\_\_

暫存資料夾

輸出資料夾

大型二進位模型

```



請建立：



```text

D:\\SheetMusicOMR\_v3.00\\docs\\PRE\_SCORE\_STUDIO\_AUDIT.md

```



內容至少包括：



1\. 專案目錄樹。

2\. Python／FastAPI 的入口檔案與啟動方式。

3\. 全部既有 API 路由與用途。

4\. 靜態檔案與舊編輯器 HTML/JS/CSS 位置。

5\. OMR 結果的實際資料格式與儲存位置。

6\. PDF/JPG 匯入、OCR、任務完成、跳轉編輯器的程式流程。

7\. JSON、TSV、TXT、MusicXML 的讀寫程式位置。

8\. 專案、原圖、快取、備份、輸出檔的資料夾位置。

9\. 既有測試、啟動 BAT、PowerShell 腳本的位置。

10\. 所有可能受此次整合影響的檔案清單。



盤點完成後，停止並輸出報告；確認無誤後才可進入下一階段。



\### 2.2 建立完整備份



建立完整備份：



```text

D:\\SheetMusicOMR\_v3.00\_backup\_before\_scorestudio

```



建立下列批次檔：



```bat

@echo off

setlocal

set "SRC=D:\\SheetMusicOMR\_v3.00"

set "DST=D:\\SheetMusicOMR\_v3.00\_backup\_before\_scorestudio"



if not exist "%SRC%" (

&#x20; echo ERROR: source project does not exist.

&#x20; echo %SRC%

&#x20; pause

&#x20; exit /b 1

)



if exist "%DST%" (

&#x20; echo ERROR: backup directory already exists.

&#x20; echo %DST%

&#x20; pause

&#x20; exit /b 1

)



robocopy "%SRC%" "%DST%" /E /COPY:DAT /DCOPY:DAT /R:1 /W:1 /XD .venv node\_modules \_\_pycache\_\_

set "RC=%ERRORLEVEL%"



if %RC% GEQ 8 (

&#x20; echo ERROR: backup failed. Robocopy code=%RC%

&#x20; pause

&#x20; exit /b %RC%

)



echo Backup completed successfully.

echo Destination: %DST%

pause

endlocal

```



儲存為：



```text

D:\\backup\_sheetmusicomr\_before\_scorestudio.bat

```



備份完成後，請報告備份目錄、檔案數、失敗清單與 Robocopy 結果碼。



\---



\## 3. 整體架構



\### 3.1 正確資料流



```text

PDF / JPG / PNG / TXT / TSV / JSON

&#x20;             │

&#x20;             ▼

既有 OMR / OCR / 匯入流程（保留）

&#x20;             │

&#x20;             ├── 原始結果 raw

&#x20;             ├── source pages / 原圖

&#x20;             ├── bbox / confidence / 原始 token

&#x20;             ▼

&#x20;       OMR Adapter（新增）

&#x20;             ▼

&#x20;     ScoreDocument v1（唯一標準可編輯模型）

&#x20;             │

&#x20;     ┌───────┼───────────────────────┐

&#x20;     ▼       ▼                       ▼

Legacy Editor ScoreStudio         Export Services

（保留）      （新增）               JSON / TSV / TXT / MusicXML

&#x20;             │

&#x20;             ▼

&#x20;      Local Web Audio Playback

```



\### 3.2 核心原則



\- `ScoreDocument` 是唯一的標準可編輯資料格式。

\- OMR 原始輸出不可直接被 UI 當作唯一資料來源。

\- 舊編輯器和新編輯器都應能讀取 `ScoreDocument`。

\- 若舊編輯器無法理解進階欄位，必須保留在 `extensions`，不可靜默刪除。

\- 視覺排版是資料模型的渲染結果，不是資料本身。

\- 音符、歌詞、和弦、標注、小節、聲部都必須具備穩定 UUID。



\---



\## 4. 建議目錄與模組



請先以盤點結果為準。若實際專案結構不同，應在不破壞既有檔案的前提下，建立等價目錄。



```text

D:\\SheetMusicOMR\_v3.00\\

├─ app\\

│  ├─ main.py

│  ├─ api\\

│  │  ├─ score\_studio\_routes.py        # 新增

│  │  └─ ...既有 route 保留

│  ├─ models\\

│  │  ├─ score\_document.py             # 新增

│  │  ├─ score\_events.py               # 新增

│  │  ├─ score\_provenance.py           # 新增

│  │  └─ score\_validation.py           # 新增

│  ├─ services\\

│  │  ├─ omr\_adapter.py                # 新增

│  │  ├─ score\_document\_service.py     # 新增

│  │  ├─ score\_validator.py            # 新增

│  │  ├─ score\_history\_service.py      # 新增

│  │  ├─ score\_autosave\_service.py     # 新增

│  │  ├─ legacy\_score\_adapter.py       # 新增

│  │  └─ ...既有匯出服務保留並調整

│  └─ tests\\

│     ├─ fixtures\\

│     ├─ test\_score\_document.py

│     ├─ test\_omr\_adapter.py

│     ├─ test\_score\_validator.py

│     └─ test\_musicxml\_roundtrip.py

│

├─ static\\

│  ├─ legacy-editor\\                   # 原有編輯器，保留

│  └─ score-studio\\                    # 新增

│     ├─ index.html

│     ├─ score-studio.js

│     ├─ score-api.js

│     ├─ score-store.js

│     ├─ score-renderer-svg.js

│     ├─ score-layout.js

│     ├─ score-interaction.js

│     ├─ score-keyboard.js

│     ├─ score-playback.js

│     ├─ score-history.js

│     ├─ score-source-panel.js

│     ├─ score-validation-ui.js

│     ├─ score-studio.css

│     └─ local-assets\\

│

├─ data\\

│  ├─ projects\\

│  ├─ autosave\\

│  ├─ snapshots\\

│  └─ source-pages\\

│

├─ docs\\

│  ├─ PRE\_SCORE\_STUDIO\_AUDIT.md

│  ├─ SCORE\_DOCUMENT\_SCHEMA.md

│  ├─ SCORE\_STUDIO\_MIGRATION.md

│  └─ SCORE\_STUDIO\_TEST\_CASES.md

│

└─ scripts\\

&#x20;  ├─ start.bat

&#x20;  ├─ verify\_score\_studio.ps1

&#x20;  └─ backup\_before\_upgrade.ps1

```



\---



\## 5. Feature Flag 與並存路由



\### 5.1 必須加入的設定



新增本機設定，預設不影響既有使用者：



```env

SCORE\_STUDIO\_ENABLED=false

SCORE\_STUDIO\_DEFAULT=false

```



若專案使用 JSON、Python 設定物件或 `.env`，依現有慣例整合；不可額外導入雲端設定服務。



\### 5.2 路由要求



新舊版必須並存：



```text

/editor/legacy/{project\_id}    # 既有編輯器

/editor/studio/{project\_id}    # 新 ScoreStudio

/editor/{project\_id}           # 依 Feature Flag 導向

```



新增 API：



```text

GET    /api/projects/{project\_id}/score

PUT    /api/projects/{project\_id}/score

POST   /api/projects/{project\_id}/score/validate

POST   /api/projects/{project\_id}/score/snapshot

GET    /api/projects/{project\_id}/score/history

POST   /api/projects/{project\_id}/score/restore/{revision}

POST   /api/projects/{project\_id}/score/import-omr

POST   /api/projects/{project\_id}/score/import-musicxml

GET    /api/projects/{project\_id}/export/musicxml

GET    /api/projects/{project\_id}/export/json

GET    /api/projects/{project\_id}/export/tsv

GET    /api/projects/{project\_id}/export/txt

GET    /api/projects/{project\_id}/source-pages

GET    /api/projects/{project\_id}/source-map/{event\_id}

```



新版發生載入、轉換、渲染、驗證或儲存錯誤時，畫面必須顯示具體錯誤訊息，並提供：



```text

以舊版編輯器開啟

```



按鈕。



\---



\## 6. ScoreDocument v1：唯一資料契約



\### 6.1 文件根物件



新增 `app/models/score\_document.py`；若使用 Pydantic，請採 Pydantic v2 的寫法並建立完整驗證。



```json

{

&#x20; "schemaVersion": "1.0.0",

&#x20; "projectId": "project-uuid",

&#x20; "title": "未命名樂譜",

&#x20; "metadata": {

&#x20;   "composer": "",

&#x20;   "lyricist": "",

&#x20;   "arranger": "",

&#x20;   "copyright": "",

&#x20;   "language": "zh-Hant"

&#x20; },

&#x20; "scoreSettings": {

&#x20;   "notationMode": "jianpu",

&#x20;   "key": {

&#x20;     "tonic": "C",

&#x20;     "mode": "major",

&#x20;     "display": "1=C"

&#x20;   },

&#x20;   "timeSignature": {

&#x20;     "beats": 4,

&#x20;     "beatType": 4

&#x20;   },

&#x20;   "tempo": {

&#x20;     "bpm": 80,

&#x20;     "beatUnit": "quarter",

&#x20;     "text": ""

&#x20;   },

&#x20;   "pickupTicks": 0,

&#x20;   "ticksPerQuarter": 480,

&#x20;   "displayTransposeSemitones": 0,

&#x20;   "rhythmGrouping": "byTimeSignature",

&#x20;   "showKey": true,

&#x20;   "showTimeSignature": true,

&#x20;   "showTempo": true

&#x20; },

&#x20; "parts": \[],

&#x20; "sections": \[],

&#x20; "sourcePages": \[],

&#x20; "extensions": {},

&#x20; "audit": {

&#x20;   "createdAt": "2026-09-24T00:00:00+08:00",

&#x20;   "updatedAt": "2026-09-24T00:00:00+08:00",

&#x20;   "revision": 1

&#x20; }

}

```



\### 6.2 聲部模型



```json

{

&#x20; "id": "part-main",

&#x20; "name": "旋律",

&#x20; "shortName": "Mel.",

&#x20; "instrument": {

&#x20;   "id": "voice",

&#x20;   "name": "人聲",

&#x20;   "midiProgram": 0

&#x20; },

&#x20; "notationMode": "jianpu",

&#x20; "muted": false,

&#x20; "solo": false,

&#x20; "volume": 0.85,

&#x20; "transposeSemitones": 0,

&#x20; "measures": \[]

}

```



\### 6.3 小節模型



```json

{

&#x20; "id": "measure-001",

&#x20; "number": 1,

&#x20; "timeSignatureOverride": null,

&#x20; "keyOverride": null,

&#x20; "rhythmGroupingOverride": null,

&#x20; "events": \[],

&#x20; "barline": {

&#x20;   "left": "single",

&#x20;   "right": "single",

&#x20;   "repeatStart": false,

&#x20;   "repeatEnd": false,

&#x20;   "final": false

&#x20; },

&#x20; "provenance": {

&#x20;   "source": "omr",

&#x20;   "page": 1,

&#x20;   "bbox": ,

&#x20;   "confidence": 0.92

&#x20; }

}

```



\### 6.4 音樂事件模型



```json

{

&#x20; "id": "event-001",

&#x20; "type": "note",

&#x20; "startTick": 0,

&#x20; "durationTicks": 480,

&#x20; "durationStatus": "verified",

&#x20; "pitch": {

&#x20;   "degree": 1,

&#x20;   "accidental": 0,

&#x20;   "octave": 0,

&#x20;   "midi": 60

&#x20; },

&#x20; "notation": {

&#x20;   "duration": "quarter",

&#x20;   "dots": 0,

&#x20;   "tieStart": false,

&#x20;   "tieStop": false,

&#x20;   "slurStart": false,

&#x20;   "slurStop": false,

&#x20;   "tuplet": null,

&#x20;   "articulations": \[]

&#x20; },

&#x20; "lyrics": \[],

&#x20; "chords": \[],

&#x20; "annotations": \[],

&#x20; "provenance": {

&#x20;   "source": "omr",

&#x20;   "page": 1,

&#x20;   "bbox": ,

&#x20;   "rawToken": "1",

&#x20;   "confidence": 0.87,

&#x20;   "reviewStatus": "needs\_review",

&#x20;   "reviewReason": "low\_confidence"

&#x20; }

}

```



事件 `type` 至少支援：



```text

note | rest | unknown | direction | barline-anchor

```



\### 6.5 歌詞模型



```json

{

&#x20; "id": "lyric-v1-e12",

&#x20; "verse": 1,

&#x20; "label": "主歌",

&#x20; "text": "你",

&#x20; "syllabic": "single",

&#x20; "extend": false,

&#x20; "provenance": {

&#x20;   "source": "omr",

&#x20;   "page": 1,

&#x20;   "bbox": ,

&#x20;   "rawToken": "你",

&#x20;   "confidence": 0.93,

&#x20;   "reviewStatus": "verified"

&#x20; }

}

```



\### 6.6 和弦模型



```json

{

&#x20; "id": "chord-001",

&#x20; "anchorType": "event",

&#x20; "anchorId": "event-001",

&#x20; "offsetTick": 0,

&#x20; "rawText": "F#m7/C#",

&#x20; "parsed": {

&#x20;   "root": "F#",

&#x20;   "quality": "minor7",

&#x20;   "bass": "C#",

&#x20;   "extensions": \[]

&#x20; },

&#x20; "position": "above",

&#x20; "transposeWithScore": true,

&#x20; "provenance": {

&#x20;   "source": "omr",

&#x20;   "page": 1,

&#x20;   "bbox": ,

&#x20;   "rawToken": "F#m7/C#",

&#x20;   "confidence": 0.89,

&#x20;   "reviewStatus": "verified"

&#x20; }

}

```



若和弦解析失敗，必須保留 `rawText`，`parsed` 可為 `null`；不得丟棄文字。



\### 6.7 原始來源與人工修正



每個 OMR 來源元素必須保留：



```text

source        = omr | manual | omr+manual | imported\_musicxml | legacy

page          = 原始頁碼

bbox          = \[x, y, width, height]

rawToken      = 原始辨識字串

confidence    = 0.0 到 1.0

reviewStatus  = verified | needs\_review | unresolved

reviewReason  = low\_confidence | ambiguous\_duration | lyric\_alignment | unknown\_symbol | manual

```



人工修正時，不可刪掉 `rawToken` 或原始 bbox；須建立新欄位：



```json

{

&#x20; "correctedValue": "3",

&#x20; "reviewedByUser": true,

&#x20; "reviewedAt": "ISO-8601"

}

```



\---



\## 7. OMR Adapter 規格



建立：



```text

app/services/omr\_adapter.py

```



範例介面：



```python

from typing import Any



class OmrToScoreDocumentAdapter:

&#x20;   def convert(

&#x20;       self,

&#x20;       omr\_result: dict\[str, Any],

&#x20;       source\_pages: list\[dict\[str, Any]]

&#x20;   ) -> dict\[str, Any]:

&#x20;       """Convert existing OMR/OCR output to ScoreDocument.



&#x20;       Rules:

&#x20;       - Never fabricate missing music information.

&#x20;       - Preserve raw OCR data, bbox and confidence.

&#x20;       - Use unknown/unresolved status for ambiguous data.

&#x20;       - Keep import data inside extensions when not representable.

&#x20;       """

&#x20;       raise NotImplementedError

```



\### 7.1 轉換規則



\- `1` 到 `7`：建立簡譜音符事件。

\- `0`：建立休止符。

\- 無法可靠確認的 token：建立 `type: "unknown"` 或保存至 `extensions.unresolvedTokens`。

\- 高／低八度點：沿用既有 OMR 邏輯，儲存為 `pitch.octave`，並保留點的 bbox。

\- 時值未知：`durationStatus: "unknown"`，不可自動假設成四分音符。

\- 歌詞與音符的水平位置關聯可作為候選，但低信心時必須標為 `lyric\_alignment`。

\- 和弦需獨立保存；解析失敗時保留字串。

\- OMR 辨識到的小節界線、拍號、調性、速度均保存來源資訊。

\- 原始 OMR 完整結果應保留於 `document.extensions.rawOmr` 或指向已儲存原始檔案的路徑。



\---



\## 8. ScoreStudio UI 與互動規格



\### 8.1 介面配置



```text

┌────────────────────────────────────────────────────────────────────┐

│ 樂譜名稱 | Undo | Redo | 播放 | 練習 | 儲存狀態 | 匯出 | 設定      │

├──────────────────┬────────────────────────────────┬────────────────┤

│ 左側結構欄       │ 中央 SVG 樂譜畫布               │ 右側屬性面板   │

│                  │                                │                │

│ 模式             │  調性 / 拍號 / 速度             │ 選取事件資料   │

│ N 音符           │                                │ 時值、八度     │

│ L 歌詞           │  簡譜 + 和弦 + 歌詞              │ 升降、連音     │

│ C 和弦           │  既有事件與淡色插入點           │ OMR 信心值     │

│ P 標注           │                                │ 原圖座標       │

│                  │                                │                │

│ 聲部管理         │                                │                │

│ 段落管理         │                                │                │

│ 小節管理         │                                │                │

├──────────────────┴────────────────────────────────┴────────────────┤

│ 第 X 小節 / 第 X 拍 | Zoom | validation | 已儲存 / 儲存失敗          │

└────────────────────────────────────────────────────────────────────┘

```



\### 8.2 SVG 渲染要求



\- 主譜面必須使用 SVG 元素渲染。

\- 每個可選事件須帶 `data-event-id`。

\- 每個小節須帶 `data-measure-id`。

\- 每個淡色插入點須帶 `data-insert-tick` 與 `data-measure-id`。

\- 以 `viewBox` 搭配 CSS／JS 實作縮放，避免像素化。

\- 支援 50% 到 200% 縮放。

\- 小節不可從中間切斷；可依容器寬度自動換行。

\- 歌詞、和弦、八度點、音符、標注之間必須做基本碰撞避讓。

\- 不可將整張樂譜輸出為不可選取的單一 Canvas bitmap。



\### 8.3 模式與快捷鍵



| 快捷鍵 | 功能 |

|---|---|

| `N` | 音符輸入模式 |

| `L` | 歌詞輸入模式 |

| `C` | 和弦輸入模式 |

| `P` | 標注輸入模式 |

| `V` 或 `Esc` | 選取模式 |

| `1` 至 `7` | 輸入或替換簡譜音符 |

| `0` | 輸入休止符 |

| `Backspace` | 刪除／回刪 |

| `Delete` | 刪除選取事件 |

| `Left` / `Right` | 前後移動選取或插入位置 |

| `Up` / `Down` | 調整八度或選取位置 |

| `Shift + Up` / `Shift + Down` | 半音調整 |

| `Q` | 全音符 |

| `W` | 二分音符 |

| `E` | 四分音符 |

| `R` | 八分音符 |

| `T` | 十六分音符 |

| `.` | 加／移除附點 |

| `-` | 延長音或 tie |

| `Space` | 播放／停止 |

| `Ctrl/Cmd + Z` | Undo |

| `Ctrl/Cmd + Shift + Z` 或 `Ctrl/Cmd + Y` | Redo |

| `Ctrl/Cmd + S` | 立即儲存 |

| `Ctrl/Cmd + =` | 放大 |

| `Ctrl/Cmd + -` | 縮小 |



\### 8.4 插入點



所有可輸入的時間位置必須具有淡色 placeholder，例如：



```text

| 1 | 2 | \[ + ] | 3 | 5 |

```



點選 placeholder 後：



1\. 顯示清楚插入游標。

2\. 狀態列顯示小節、拍點與 tick 位置。

3\. 音符模式按 `1–7` 或 `0` 可立即輸入。

4\. 歌詞模式可輸入／貼上文字。

5\. 和弦模式顯示本地輸入欄位。

6\. 新增後焦點移到下一個合理拍點。

7\. 小節不足拍時維持剩餘空間；滿拍時引導至下一小節。



\---



\## 9. 簡譜、節奏與驗證規格



\### 9.1 簡譜規則



\- 數字 `1–7` 為調內音級。

\- `0` 為休止符。

\- `#`、`b`、`n` 分別表示升、降、還原。

\- 八度必須與附點獨立儲存。

\- 延音與 tie 不可只以重複插入相同音符替代。

\- 三連音與 tuplet 要保留 actual/normal 比例資料。



\### 9.2 時值



固定：



```text

ticksPerQuarter = 480

whole           = 1920 ticks

half            = 960 ticks

quarter         = 480 ticks

eighth          = 240 ticks

sixteenth       = 120 ticks

```



\### 9.3 小節拍數檢查



```text

expectedMeasureTicks = beats \* ticksPerQuarter \* 4 / beatType

```



驗證狀態：



| 狀態 | UI 行為 |

|---|---|

| valid | 正常顯示、可播放、可匯出 |

| underfilled | 小節末端顯示剩餘淡色空間，可補休止或修正 |

| overflow | 紅色標示；阻止危險寫入，提供拆分／移至下一小節／取消 |

| unknown\_duration | 黃色標示；要求人工確認 |

| unresolved\_omr | 黃色或橙色標示；保留原始資料 |



不可因 OMR 時值缺失，就自動補成四分音符。



\---



\## 10. 歌詞與和弦規格



\### 10.1 歌詞



歌詞必須附著於音符事件。



\- 中文：預設一字一音。

\- 日文：允許逐字或詞彙分段。

\- 英文：支援 `single`、`begin`、`middle`、`end`。

\- 休止符預設跳過。

\- `Tab` 前往下一個可填寫音符；`Shift+Tab` 回前一個。

\- 貼上多字／多行歌詞時，先預覽分配，允許套用、取消或人工調整。

\- 長音使用 `extend: true`。



\### 10.2 和弦



\- 支援原始字串輸入。

\- 優先解析 `C`、`Cm`、`C7`、`Cmaj7`、`Cm7`、`Cadd9`、`Csus4`、`C/E`、`F#dim`、`Bb`、`F#m7/C#`。

\- 解析失敗時仍顯示並保存原始字串。

\- 可設定 `transposeWithScore`。

\- 匯出 MusicXML 時，成功解析者輸出 `harmony`；無法解析者以文字 direction 作保底。



\---



\## 11. 原圖對照與 OMR 校正工作台



\### 11.1 雙向定位



新增「原圖校正模式」：



```text

┌──────────────────────┬──────────────────────────────────┐

│ 原始 PDF/JPG 頁面    │ ScoreStudio 編輯樂譜             │

│                      │                                  │

│ 點選原圖辨識框       │ 對應事件高亮                     │

│                      │                                  │

│ 點選音符／歌詞／和弦 │ 原圖跳至 bbox 並框選             │

└──────────────────────┴──────────────────────────────────┘

```



需求：



\- 點選事件時，原圖自動捲動至 bbox。

\- 點選原圖 bbox 時，反向選取事件。

\- 低信心元素在雙側採相同警示色。

\- 可以篩選 `needs\_review`、`unresolved`、低信心、未知時值、歌詞對齊問題、超拍／未滿拍。

\- 可標記「已確認」、「錯誤已修正」、「無法判定」。

\- 原圖 bbox 可切換顯示／隱藏。

\- 人工新增事件標記 `source: manual`。

\- OMR 項目修正後標記 `source: omr+manual`。



\---



\## 12. 播放與排練



使用瀏覽器本機 Web Audio API；不得從網路下載音源。



第一階段必須支援：



\- 播放／停止／重新開始。

\- 從游標播放。

\- 播放全曲、目前段落、選取小節。

\- 節拍器。

\- 1 或 2 小節預備拍。

\- 20 至 240 BPM。

\- 播放中目前音符與播放游標高亮。

\- 單聲部音量控制；多聲部功能先預留。

\- 第一階段可使用簡單本機合成音，後續才加入可選本機 SoundFont。



播放排程：



```text

scheduler interval = 25 ms

schedule ahead     = 150 ms

ticks per quarter  = 480

```



計算：



```text

secondsPerTick = 60 / bpm / ticksPerQuarter

```



\---



\## 13. 調性、拍號、移調與節奏分組



\### 13.1 調性與拍號



至少支援：



```text

調性：C、G、D、A、E、B、F#、F、Bb、Eb、Ab、Db 及相對小調

拍號：2/4、3/4、4/4、6/8、9/8、12/8、自訂

```



並支援：



\- 每小節拍號覆寫。

\- 弱起小節 `pickupTicks`。

\- 文件或小節級節奏分組。



\### 13.2 必須分清兩種移調



| 操作 | 效果 |

|---|---|

| 顯示調性變更 | 如 `1=C` 改為 `1=G`；音級與實際 MIDI 音高不變 |

| 實際移調 | 音高、MIDI 與可選和弦根音改變 |



UI 必須明確顯示使用者操作的是哪一種，不可混淆。



\### 13.3 節奏分組



至少支援：



```text

byTimeSignature

3-3-2

3-2-3

2-3-3

custom，例如

```



\---



\## 14. 儲存、歷史與版本



\### 14.1 前後端保存流程



```text

使用者操作

→ 前端 Command Stack

→ IndexedDB 本地草稿

→ 800ms debounce

→ PUT /api/projects/{id}/score

→ 後端 schema 驗證

→ 寫入專案 score.json

→ revision +1

→ 顯示已儲存或失敗

```



\### 14.2 Revision API



PUT 請求應包含：



```json

{

&#x20; "expectedRevision": 42,

&#x20; "document": {}

}

```



revision 不一致時回傳 HTTP 409，前端必須提供：



\- 載入最新版。

\- 比較差異。

\- 另存本機副本。



\### 14.3 快照時機



以下操作前必須建立 snapshot：



\- 匯入 OMR 結果。

\- 套用新拍號。

\- 整曲實際移調。

\- 刪除聲部。

\- 大量貼上歌詞。

\- 批次修改時值。

\- 從舊版資料轉換為 ScoreDocument。

\- 準備開啟 Legacy Editor 前。



\### 14.4 Undo / Redo



每個可逆修改皆以 Command 保存：



```ts

interface EditorCommand {

&#x20; id: string;

&#x20; type: string;

&#x20; timestamp: number;

&#x20; apply(document: ScoreDocument): ScoreDocument;

&#x20; revert(document: ScoreDocument): ScoreDocument;

}

```



連續輸入可依時間窗合併，但不得失去逐步復原能力。



\---



\## 15. 匯入、匯出與 MusicXML



\### 15.1 保留既有能力



不得移除：



```text

JSON

TSV

TXT

MusicXML

```



輸出應優先由 `ScoreDocument` 轉換。



\### 15.2 MusicXML 最低要求



必須正確處理：



```text

part-list

score-part

attributes

&#x20; divisions

&#x20; key

&#x20; time

&#x20; clef

&#x20; transpose

note

&#x20; pitch

&#x20; rest

&#x20; duration

&#x20; type

&#x20; dot

&#x20; tie

&#x20; notations

lyric

harmony

direction

barline

backup / forward（多聲部階段）

```



不可輸出需要外連 DTD 的 XML。



\### 15.3 匯出前驗證



若有下列問題，應列出匯出前報告：



\- unknown token。

\- unresolved OMR。

\- unknown duration。

\- 超拍。

\- 歌詞對齊衝突。

\- 無法解析的和弦。



使用者可選：



```text

取消匯出

匯出並附警告報告

```



不可靜默輸出明顯錯誤資料。



\---



\## 16. 實作階段與驗收



\### M0：盤點、備份、Feature Flag



實作：



\- 建立盤點文件。

\- 建立完整備份。

\- 新增 Feature Flag，預設關閉。

\- 建立空白 `/editor/studio/{project\_id}`。

\- 保留 Legacy Editor。



驗收：



\- 舊系統可啟動。

\- 原 OMR 流程可完成。

\- 舊匯出功能可用。

\- 新路由可進入，但不影響舊路由。



\### M1：ScoreDocument 與 OMR Adapter



實作：



\- Pydantic schema。

\- OMR Adapter。

\- Schema validation。

\- 讀寫標準 JSON。

\- 保留 bbox、confidence、rawToken、原始來源。



驗收：



\- 至少三個既有專案可轉成 ScoreDocument。

\- 重新載入後 UUID、文本、音符、來源資料一致。

\- OCR 不確定資料仍是 unknown 或 needs\_review。



\### M2：SVG 檢視器



實作：



\- 單聲部簡譜 SVG。

\- 小節線、調性、拍號、速度、音符、休止、八度點、歌詞、和弦。

\- 點選事件。

\- 淡色插入點。

\- 縮放與基本換行。



驗收：



\- 可載入至少 50 小節。

\- 可選取任一事件。

\- 點選插入點可正確顯示 measure ID 與 tick。



\### M3：編輯核心



實作：



\- N/L/C/P 模式。

\- 音符、歌詞、和弦、標注的新增、修改、刪除。

\- 新增、刪除、複製、插入小節。

\- 小節驗證。

\- Undo / Redo。

\- 自動儲存。



驗收：



\- 建立 16 小節簡譜。

\- 可輸入歌詞與和弦。

\- 可刪除、Undo、Redo。

\- 重開服務後資料保持。



\### M4：原圖校正



實作：



\- 原圖／編輯譜雙向定位。

\- bbox 顯示。

\- 低信心篩選。

\- 校正標記與修正歷史。



驗收：



\- 點選低信心音符能跳原圖。

\- 修正後保留原始辨識資料。



\### M5：播放與匯出



實作：



\- Web Audio 播放。

\- 節拍器和游標高亮。

\- MusicXML、JSON、TSV、TXT 匯出。

\- 匯出前問題報告。



驗收：



\- 可播放 16 小節。

\- MusicXML 可由至少一套外部樂譜軟體開啟。

\- 舊版輸出不退化。



\### M6：多聲部與進階功能



後續才實作：



\- 多聲部。

\- 段落與反覆。

\- 弱起與進階節奏分組。

\- 總譜／分譜。

\- 列印 PDF、SVG、PNG。

\- TAB、鼓譜、五線譜以 plugin 介面擴充。



\---



\## 17. 必做測試矩陣



請建立：



```text

docs/SCORE\_STUDIO\_TEST\_CASES.md

```



至少包含：



| ID | 測試 | 預期 |

|---|---|---|

| T01 | 開啟既有 OCR 專案 | 新舊編輯器均可讀取，來源資料不遺失 |

| T02 | 低信心音符 | 顯示警示，能跳回原圖 bbox |

| T03 | OCR 無法識別符號 | unknown，不可自動猜音符 |

| T04 | 將 `1` 改 `3` | UI、播放、JSON、MusicXML 同步 |

| T05 | 4/4 輸入五個四分音符 | 阻止超拍或提供安全處理 |

| T06 | 貼上中文「我愛你」 | 可預覽並正確對應三個音符 |

| T07 | 輸入 `F#m7/C#` | 原字串不遺失，解析結果正確或標示未解析 |

| T08 | 80 BPM 改 120 BPM | UI、播放、MusicXML 均更新 |

| T09 | `1=C` 改 `1=G` 顯示轉調 | 音級與實際音高不變 |

| T10 | 實際移調 +2 | MIDI 及可選和弦根音更新 |

| T11 | Undo / Redo | 操作可正確往返 |

| T12 | 重整頁面／重啟服務 | 自動儲存資料完整載入 |

| T13 | 切回 Legacy Editor | 不破壞 ScoreDocument 的未知欄位 |

| T14 | 斷網測試 | 已承諾功能完整可用 |

| T15 | MusicXML round-trip | 核心音符、歌詞、和弦不遺失 |

| T16 | 繁中歌詞 | 原尺寸與放大 OCR 結果的既有選擇策略未退化 |

| T17 | 高八度點 | 既有加權中位數修正流程未退化 |

| T18 | 多頁 PDF | 頁碼、原圖定位與小節來源保持正確 |



每次提交或階段完成前應執行自動測試；所有失敗需記錄原因，禁止略過。



\---



\## 18. Windows 離線驗證



請新增：



```text

scripts/verify\_score\_studio.ps1

```



需求：



1\. 確認服務只監聽 `127.0.0.1`，不得綁定 `0.0.0.0`。

2\. 確認 ScoreStudio JS/CSS 不含外部 CDN URL。

3\. 確認 HTML 不含外部字型／外部腳本。

4\. 在禁網或離線環境下啟動並執行基本測試。

5\. 確認 `legacy-editor` 可開啟。

6\. 確認 `studio` 可開啟。

7\. 以測試專案驗證 JSON、TSV、TXT、MusicXML 匯出。

8\. 產出易讀報告與退出碼：全部成功為 0，任一核心失敗為非 0。



\---



\## 19. Agent 最終交付要求



所有階段完成後，必須輸出：



1\. `docs/SCORE\_STUDIO\_MIGRATION.md`

&#x20;  - 修改內容。

&#x20;  - 新舊路由。

&#x20;  - 設定方法。

&#x20;  - 回退方式。

&#x20;  - 已知限制。



2\. `docs/SCORE\_DOCUMENT\_SCHEMA.md`

&#x20;  - 完整 schema、欄位意義、版本策略。



3\. `docs/SCORE\_STUDIO\_TEST\_CASES.md`

&#x20;  - 測試矩陣、實測結果。



4\. `CHANGELOG\_SCORE\_STUDIO.md`

&#x20;  - 新增／修改／保留檔案清單。



5\. Windows 啟動與驗證命令。



6\. 最終報告需誠實列出：

&#x20;  - 已完成功能。

&#x20;  - 未完成功能。

&#x20;  - 需使用者手動測試的項目。

&#x20;  - 發現的既有問題。

&#x20;  - 回退到舊版的方法。



不得將計畫、靜態頁、mock 或未實測功能寫成「已完成」。



\---



\## 20. 開發優先順序結論



請將開發重點依序放在：



1\. 保護既有可用工具與資料。

2\. 統一 ScoreDocument 資料格式。

3\. OMR 結果可追溯與可校正。

4\. 簡譜、歌詞、和弦的高效率編輯。

5\. 節奏驗證、Undo/Redo、自動儲存。

6\. 原圖雙向定位。

7\. 播放與 MusicXML 匯出。

8\. 最後再擴充多聲部、TAB、五線譜、鼓譜與列印。



完成的判準不是畫面像樂譜，而是：使用者可以可靠地由 OMR 結果出發，追溯來源、人工修正、播放驗證、保存版本並匯出可交換的音樂資料。

