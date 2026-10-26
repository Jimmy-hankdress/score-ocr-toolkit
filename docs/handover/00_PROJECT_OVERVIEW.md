# ScoreForge 專案總覽

## 一、專案基本資訊

| 項目 | 內容 |
|------|------|
| **完整名稱** | SheetMusicOMR (樂譜數位化與本地化打譜工具) |
| **專案根目錄** | `D:\SheetMusicOMR_v3.00` |
| **最終目標** | 上傳 PDF 樂譜 → 生成 Word/MIDI/MusicXML/Sola321 格式，支援線上編輯 |
| **當前版本** | v3.05.07 (前端) / 3.0.0 (後端) |
| **開發狀態** | **未達需求** — 自由編輯能力未完成 |

## 二、技術架構

### 後端 (Python)
- **語言**: Python 3.11+
- **框架**: FastAPI
- **虛擬環境**: `D:\SheetMusicOMR_v3.00\.venv`
- **主要套件**:
  - `fastapi>=0.110`
  - `uvicorn>=0.27`
  - `python-multipart>=0.0.9`
  - `PyMuPDF>=1.24` (PDF 轉圖)
  - `Pillow>=10.2` (影像處理)
  - `numpy>=1.24` (簡譜幾何分析)
  - `python-docx>=1.0.0` (Word 輸出)
  - `pydantic>=2.0` (資料驗證)

### 前端 (JavaScript)
- **入口檔案**: `web/index.html`
- **主要腳本**:
  - `web/assets/app.js` — 主應用邏輯 (4200+ 行)
  - `web/assets/styles.css` — 樣式表
  - `web/assets/event_model.js` — Event Model (phase15)
  - `web/assets/layout_engine.js` — 排版引擎 (phase15)
  - `web/assets/svg_renderer.js` — SVG 渲染器 (phase15)
  - `web/assets/phase_a_integration.js` — Phase A 整合 (新建)
- **版本標記**: `OMR-SOLA-7` (app.js)

### OMR 引擎
- **Tesseract OCR**: `tesseract v5.5.3.20260724`
- **支援語言**: 多語言 (含 chi_sim, chi_tra, eng)
- **演算法**: jianpu2 (幾何分析), OrpheusNet (CNN 純簡譜), jpeditor

## 三、目錄結構

```
D:\SheetMusicOMR_v3.00\
├── app/                    # 後端 Python 模組
│   ├── config.py          # 設定
│   ├── db.py              # 資料庫
│   ├── projects.py        # 專案管理
│   ├── server.py          # FastAPI 主伺服器
│   ├── formats/           # 匯出格式 (MIDI, MusicXML, Sola321, Word)
│   ├── omr/               # OMR 引擎
│   └── scorestudio/       # Score Studio API
├── web/                    # 前端資源
│   ├── index.html         # 主頁面
│   ├── assets/            # JS/CSS/字型
│   └── score-studio/      # Score Studio 子頁面
├── phase15/               # Event Model 階段 (測試用)
├── phase4/                # Editor Core (已整合)
├── phase6/                # Active Note 整合
├── data/                  # 資料目錄
│   ├── projects/          # 專案檔案 (JSON)
│   ├── exports/           # 匯出檔案
│   ├── imports/           # 匯入原始檔
│   └── sheetmusic.sqlite3 # SQLite 資料庫
├── samples/               # 範例檔案
├── tools/                 # 工具腳本
├── docs/                  # 文件
├── models/                # ML 模型
└── .venv/                 # Python 虛擬環境
```

## 四、啟動方式

### 啟動伺服器
```powershell
cd D:\SheetMusicOMR_v3.00
.venv\Scripts\python.exe launcher.py --port 8763 --no-browser
```

### 啟動網址
```
http://127.0.0.1:8763/
```

### 健康檢查
```
GET http://127.0.0.1:8763/api/health
```

### 停止伺服器
```powershell
# 找到 PID
netstat -ano | findstr :8763
# 終止進程
taskkill /F /PID <PID>
```

## 五、新工程師接手步驟

1. **確認環境**
   - Python 3.11+ 已安裝
   - Tesseract OCR 已安裝 (`tesseract --version`)
   - 專案根目錄: `D:\SheetMusicOMR_v3.00`

2. **啟動伺服器**
   ```powershell
   cd D:\SheetMusicOMR_v3.00
   .venv\Scripts\python.exe launcher.py --port 8763 --no-browser
   ```

3. **開啟瀏覽器**
   ```
   http://127.0.0.1:8763/
   ```

4. **載入測試專案**
   - 點擊「Score Studio」標籤
   - 從左側選擇「Last Dance」(39 measures)

5. **執行驗證**
   - 按 F12 → Console
   - 貼上驗證腳本檢查功能狀態

## 六、重要提醒

- **这不是一个 Git 專案** — 沒有 version control，所有修改需手動備份
- **專案資料在 `data/projects/`** — 不要刪除或修改
- **前端版本標記在 `app.js` 第 1 行** — 修改後需更新
- **Event Model 與 Legacy 格式並存** — 需注意轉換邏輯
