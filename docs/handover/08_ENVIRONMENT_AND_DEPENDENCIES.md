# 環境與依賴

## 一、作業系統

| 項目 | 規格 |
|------|------|
| 作業系統 | Windows 11 |
| 架構 | x64 |
| 使用者 | hankdress |

## 二、Python 環境

### 2.1 版本
- **主要版本**: Python 3.11.15
- **虛擬環境**: `D:\SheetMusicOMR_v3.00\.venv`
- **Python 執行檔**: `.venv\Scripts\python.exe`

### 2.2 必要套件
```
fastapi>=0.110,<1.0
uvicorn>=0.27,<1.0
python-multipart>=0.0.9
pydantic>=2.0
pydantic-core>=2.0
PyMuPDF>=1.24
Pillow>=10.2
numpy>=1.24
python-docx>=1.0.0
```

### 2.3 安裝命令
```powershell
cd D:\SheetMusicOMR_v3.00
.venv\Scripts\python.exe -m pip install -r requirements.txt
```

### 2.4 驗證
```powershell
.venv\Scripts\python.exe -c "import fastapi; import docx; print('OK')"
```

## 三、Node.js 環境

| 項目 | 規格 |
|------|------|
| 版本 | 20.x |
| 用途 | Phase 測試、工具腳本 |

### 3.1 驗證
```powershell
node --version
npm --version
```

### 3.2 測試執行
```powershell
cd D:\SheetMusicOMR_v3.00\phase15
node event_to_legacy_test.js
```

## 四、Tesseract OCR

| 項目 | 規格 |
|------|------|
| 版本 | v5.5.3.20260724 |
| 語言支援 | 多語言 (含 chi_sim, chi_tra, eng) |

### 4.1 驗證
```powershell
tesseract --version
tesseract --list-langs
```

## 五、瀏覽器

| 項目 | 規格 |
|------|------|
| 測試瀏覽器 | Chrome |
| 用途 | 前端測試、驗證 |

## 六、啟動命令

### 6.1 啟動伺服器
```powershell
cd D:\SheetMusicOMR_v3.00
.venv\Scripts\python.exe launcher.py --port 8763 --no-browser
```

### 6.2 啟動後驗證
```powershell
# 健康檢查
curl http://127.0.0.1:8763/api/health

# 開啟瀏覽器
Start-Process "http://127.0.0.1:8763/"
```

### 6.3 停止伺服器
```powershell
# 找到 PID
netstat -ano | findstr :8763

# 終止進程
taskkill /F /PID <PID>
```

## 七、建置命令

### 7.1 執行測試
```powershell
# Node.js 測試
cd D:\SheetMusicOMR_v3.00\phase15
node event_to_legacy_test.js
node roundtrip_test.js

# Python 測試
cd D:\SheetMusicOMR_v3.00
.venv\Scripts\python.exe tools\test_regression.py
```

### 7.2 檢查語法
```powershell
# Python
.venv\Scripts\python.exe -m py_compile app\server.py

# Node.js
node --check web\assets\app.js
```

## 八、日誌位置

| 日誌 | 路徑 |
|------|------|
| 伺服器日誌 | `data\logs\launcher.log` |
| 重啟日誌 | `data\logs\restart.log` |
| 控制台輸出 | `datalogsstartup-test.out` |

## 九、環境變數

無特殊環境變數需求。

## 十、依賴圖

```
launcher.py
    ↓
app/server.py (FastAPI)
    ├── app/projects.py
    ├── app/db.py
    ├── app/formats/ (MIDI, MusicXML, Word, PDF)
    ├── app/omr/ (Tesseract, OrpheusNet)
    └── app/scorestudio/ (Score Studio API)
    
web/index.html
    ├── web/assets/app.js
    ├── web/assets/event_model.js
    ├── web/assets/layout_engine.js
    ├── web/assets/svg_renderer.js
    └── web/assets/phase_a_integration.js
```
