# ScoreOCR Toolkit

本機優先的樂譜 OCR／OMR 與簡譜／五線譜雙向校對轉換工具，支援將樂譜圖片、PDF、Word、TXT、JSON 轉換為可編輯的 MusicXML 與標準簡譜（Numbered Musical Notation）。

## 目前狀態

已提供：
1. **多格式輸入支援**：支援 PDF（.pdf）、Word 文檔（.docx）、純文字文字譜（.txt）、JSON 符號格式（.json）以及點陣圖片（.png, .jpg, .bmp, .webp, .tiff）。
2. **OMR 神經網路辨識**：外接 HOMR 模型引擎，自動偵測五線譜與提取音符座標、音高、時值。
3. **網頁互動式視覺化校對畫布**：在 HTML5 Canvas 上直觀疊加音符外框、五線譜音名以及**簡譜音符標籤（1, 2, 3, 5, 6... 與高低八度點）**。
4. **簡譜格式轉換與即時預覽**：
   - 支援自由切換調號（1=C, 1=D, 1=G, 1=F, 1=Bb 等）與拍號（4/4, 3/4, 2/4, 6/8）。
   - 即時計算並排版為標準小節線（`| 1 2 3 4 |`）、時值減時線與延長線。
   - 支援一鍵複製與下載簡譜純文字檔（.txt）。
5. **雙格式匯出**：一鍵匯出校對後的標準 MusicXML 4.0（可匯入 MuseScore、Finale）與純文字簡譜。

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

HOMR 採 AGPL-3.0 授權，獨立於本專案（主專案維持 MIT）：

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
- **多格式上傳**：點擊「📁 上傳樂譜/檔案」，可直接上傳 PDF 樂譜、Word 檔、文字簡譜（如 `1 2 3 1 | 3 4 5 -`）、JSON 或圖片（BMP/PNG/JPG）。
- **畫布操作**：放大、縮小、平移、點擊選取音符外框、拖曳移動位置、調整外框大小。
- **簡譜標記開關**：工具列「🎼 簡譜標記」按鈕可自由切換畫布音符頭上方的簡譜數字角標。
- **音高與時值校對**：側邊欄快速選擇 C-D-E-F-G-A-B、升降記號、八度音階以及全音符至 32 分音符。
- **簡譜即時預覽與調號轉調**：即時調整 `1=C` 或 `1=G`，簡譜文字與畫布標籤即時同步連動。
- **匯出**：可一鍵下載 MusicXML 或純文字簡譜 (.txt)。

API Swagger 文件可於 `http://127.0.0.1:8000/docs` 檢視。

## API 端點

### `GET /` 或 `GET /ui`
提供視覺化樂譜校對畫布與簡譜轉換前端介面。

### `GET /health`
檢查服務狀態。

### `POST /recognize`
上傳樂譜檔案（支援 PDF, DOCX, TXT, JSON, BMP, PNG, JPG），執行影像預處理或文字語意解析，並回傳 MusicXML、簡譜文字、音符框座標 `(x, y, w, h)` 與音高。

### `GET /download/{filename}`
安全下載產生的 MusicXML、簡譜文字檔 (.txt)、JSON 或圖片。

### `POST /api/convert-to-jianpu`
接收目前畫布上的音符符號清單，依據指定調號（如 1=C）與拍號（如 4/4）即時計算產生對應的簡譜文字與音符簡譜標籤。

### `POST /api/export-jianpu`
將符號清單編譯並存為純文字簡譜檔案，回傳下載連結。

### `POST /api/export-musicxml`
接收校對後的音符列表，重新編譯並匯出為標準 MusicXML 4.0 檔案。

## Roadmap

- [x] 專案初始化
- [x] 圖片上傳
- [x] OpenCV 預處理
- [x] HOMR OMR backend adapter
- [x] 網頁視覺化校對畫布（Canvas 疊加音符框與即時校對）
- [x] MusicXML 匯出與即時編譯
- [x] 多格式輸入支援（PDF, Word docx, TXT, JSON, BMP/PNG/JPG）
- [x] 簡譜格式輸出（Numbered Musical Notation）、調號轉調與即時視覺化標籤
- [ ] 批次處理
- [ ] 音訊 MIDI 輸出

## License

MIT
