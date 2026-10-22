# ScoreOCR Toolkit

本機優先的樂譜 OCR／OMR 工具，將樂譜圖片轉換為可編輯的 MusicXML。

## 目前狀態

MVP 開發中。目前已提供圖片上傳、OpenCV 影像預處理、HOMR OMR 外接辨識、**網頁互動式視覺化校對畫布（Canvas 上疊加音符外框與音高／時值修改）** 以及校對後 MusicXML 重新編譯匯出功能。

## 安裝

```bash
git clone https://github.com/Jimmy-hankdress/score-ocr-toolkit.git
cd score-ocr-toolkit
python -m venv .venv
source .venv/bin/activate  # Windows: .venv\Scripts\activate
pip install -r requirements.txt
uvicorn app:app --reload
```

## Optional HOMR backend

HOMR 採 AGPL-3.0 授權，獨立於本專案（維持 MIT）：

```bash
pip install "homr[cpu]"
```

HOMR 需要 Python 3.11 或 3.12。

## 使用介面

開啟瀏覽器造訪：

```text
http://127.0.0.1:8000/
```

即可開啟**視覺化樂譜校對畫布**：
- **畫布操作**：放大、縮小、平移、點擊選取音符外框、拖曳移動位置、調整外框大小。
- **音高與時值校對**：側邊欄快速選擇 C-D-E-F-G-A-B、升降記號、八度音階以及全音符至 32 分音符。
- **即時編輯**：支援新增音符（Add Note）、刪除誤判符號（Delete）。
- **匯出**：點擊「儲存並匯出校對後 MusicXML」，即可一鍵匯入 MuseScore、Finale 或 Dorico 製譜軟體。

API Swagger 文件可於 `http://127.0.0.1:8000/docs` 檢視。

## API 端點

### `GET /` 或 `GET /ui`
提供視覺化樂譜校對畫布前端介面。

### `GET /health`
檢查服務是否正常。

### `POST /upload`
上傳樂譜圖片，回傳原始檔與二值化預處理結果路徑。

### `POST /recognize`
上傳樂譜圖片，執行影像預處理並透過 OMR 後端辨識，回傳 MusicXML 下載連結與每個音符的外框座標 `(x, y, w, h)` 與音高。

### `GET /download/{filename}`
下載產生的 MusicXML 檔案。

### `POST /api/export-musicxml`
接收校對後的音符列表，重新編譯並匯出為標準 MusicXML 4.0 檔案。

## Roadmap

- [x] 專案初始化
- [x] 圖片上傳
- [x] OpenCV 預處理
- [x] HOMR OMR backend adapter
- [x] 網頁視覺化校對畫布（Canvas 疊加音符框與即時校對）
- [x] MusicXML 匯出與即時編譯
- [ ] 批次處理
- [ ] MIDI 與 PDF 輸出

## License

MIT
