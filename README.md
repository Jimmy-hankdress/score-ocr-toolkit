# ScoreOCR Toolkit

本機優先的樂譜 OCR／OMR 工具，將樂譜圖片轉換為可編輯的 MusicXML。

## 目前狀態

MVP 開發中。目前已提供圖片上傳與 OpenCV 影像預處理；OMR 辨識、人工校對與 MusicXML 匯出將逐步加入。

## 安裝

```bash
git clone https://github.com/Jimmy-hankdress/score-ocr-toolkit.git
cd score-ocr-toolkit
python -m venv .venv
source .venv/bin/activate  # Windows: .venv\Scripts\activate
pip install -r requirements.txt
uvicorn app:app --reload
```

開啟：

```text
http://127.0.0.1:8000/docs
```

## API

### `GET /health`
檢查服務是否正常。

### `POST /upload`
上傳樂譜圖片，回傳原始檔與二值化預處理結果路徑。

## Roadmap

- [x] 專案初始化
- [x] 圖片上傳
- [x] OpenCV 預處理
- [ ] OMR 辨識整合
- [ ] 辨識結果人工校對
- [ ] MusicXML 匯出
- [ ] 批次處理
- [ ] MIDI 與 PDF 輸出

## License

MIT
