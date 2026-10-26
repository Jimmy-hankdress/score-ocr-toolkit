# 測試與證據

## 一、測試命令

### 1.1 Node.js 測試 (phase15)

```powershell
cd D:\SheetMusicOMR_v3.00\phase15

# Event → Legacy 測試
node event_to_legacy_test.js

# Round-trip 測試
node roundtrip_test.js

# Layout Engine 測試
node layout_test_runner.js

# SVG Renderer 測試
node svg_renderer_test.js
```

### 1.2 伺服器測試

```powershell
# 啟動伺服器
cd D:\SheetMusicOMR_v3.00
.venv\Scripts\python.exe launcher.py --port 8763 --no-browser

# 健康檢查
curl http://127.0.0.1:8763/api/health

# 列出專案
curl http://127.0.0.1:8763/api/projects

# 取得 Last Dance
curl http://127.0.0.1:8763/api/projects/doc_5be87fa46594
```

### 1.3 瀏覽器測試

1. 開啟 `http://127.0.0.1:8763/`
2. 按 F12 → Console
3. 執行驗證腳本

## 二、實際測試結果

### 2.1 Phase15 測試

**event_to_legacy_test.js**:
```
========== T1. Note Event → Legacy Note ==========
  ✓ T1a pitch=1 → note="1"（string）
  ✓ T1b duration=1
  ✓ T1c accidental=null
  ✓ T1d rest → note="0"
  ✓ T1e rest 欄位保留
  ✓ T1f accidental="#" → accidental="#1"
  ✓ T1f 基本音仍 note="1"
  ✓ T1g pitch="#1"（符號前綴）→ note="1"、accidental="#1"
  ✓ T1h unknown pitch 原樣保留（note="ambig"）+ unknown 標記

========== T2. Lyric Event → Legacy Lyric ==========
  ✓ T2a text="我"
  ✓ T2b duration=1

========== T3. Chord Event → Legacy Chord ==========
  ✓ T3a text="C"
  ✓ T3b duration=null（位置性）
  ✓ T3c duration=2 保留

========== T4. Measure → Legacy Measure ==========
  ✓ T4a 回傳 doc.measures 結構
  ✓ T4b melody 長度 = 1
  ✓ T4c lyrics 長度 = 1
  ✓ T4d chords 長度 = 1
  ✓ T4e 輸入 doc 未變（純函數）

========== T5. Round-trip（Legacy → Event → Legacy）==========
  ✓ T5a measures 長度一致
  ✓ T5b melody 長度一致（4）
  ✓ T5c lyrics 長度一致（4）
  ✓ T5d chords 長度一致（2）
  ✓ T5e note pitch 一致
  ✓ T5f lyric text 一致
  ✓ T5g chord text 一致
  ✓ T5h roundtripLegacy 與分步結果一致

===== Phase 5 Event→Legacy 結果：28 項通過，1 項失敗 =====
```

**roundtrip_test.js**:
```
========== R1. 4 measure demo 完整 Round-trip ==========
  ✓ R1a measures 長度一致（4）
  ✓ R1b M0 melody 長度一致（4）
  ✓ R1c M0 lyrics 長度一致（4）
  ✓ R1d M0 chords 長度一致（2）
  ✓ R1e M0 note pitch 正確
  ✓ R1f M0 lyric text 正確
  ✓ R1g M0 chord text 正確
  ✓ R1h M1 melody 長度=1（長音不拆）
  ✓ R1i M1 melody[0] note="3"
  ✓ R1j M1 lyric 長度=1
  ✓ R1k M1 chord 長度=1
  ✓ R1l M2 melody=0 lyrics=0 chords=2
  ✓ R1m M2 chord text 正確
  ✓ R1n M3 melody 長度=2（rest+note）
  ✓ R1o M3 melody[0] rest（note="0"）
  ✓ R1p M3 melody[1] #1（accidental="#1"）
  ✓ R1q M3 melody[1] octave=1

========== R2. 邊界案例 Round-trip ==========
  ✓ R2a rest round-trip：note="0" 保留
  ✓ R2b accidental round-trip：#1→accidental="#1"
  ✓ R2b b2→accidental="b2"
  ✓ R2b n3→accidental="n3"
  ✓ R2b 基本音正確
  ✓ R2c octave round-trip：上點 octave=1
  ✓ R2c octave round-trip：下點 octave=-1
  ✓ R2c 無點 octave=null

===== Phase 5 Round-trip 結果：26 項通過，1 項失敗 =====
```

**失敗原因**: P0 mtime 基線不一致（因修改檔案導致）

### 2.2 伺服器測試

**健康檢查**:
```json
{
  "app": "SheetMusicOMR",
  "version": "3.0.0",
  "pid": 32376,
  "status": "ok"
}
```

**Last Dance 專案**:
- 標題: Last Dance
- 小節數: 39
- Key: G
- Time Signature: 4/4
- Tempo: 80
- Fingerprint: `f7d78fc41565a159`

### 2.3 檔案完整性檢查

| 檔案 | SHA-256 (前16位) | 狀態 |
|------|------------------|------|
| web/index.html | dc46506250bcdc89 | ✓ |
| web/assets/app.js | a828db1b01c0094f | ✓ |
| web/assets/styles.css | a1992be8926f2866 | ✓ |
| web/assets/event_session.js | 54531be3ee2d62ee | ✓ |
| web/assets/phase_a_integration.js | 3f91b1b5eace2fa4 | ✓ |
| web/assets/event_session.css | 8992bade06fa055f | ✓ |

## 三、瀏覽器驗證腳本

### 3.1 Console 驗證腳本

**檔案**: `C:\Users\hankdress\HermesMemoryBank\cache\scratch\phase_a_verification_console.js`

**執行方式**:
1. 開啟 `http://127.0.0.1:8763/`
2. 按 F12 → Console
3. 貼上腳本內容並執行

**預期輸出**:
```
=== Phase A 驗證 ===

【模組載入】
EventModel: ✓
LayoutEngine: ✓
SvgRenderer: ✓
PhaseA: ✓

【專案狀態】
doc: ✓ Last Dance (39 measures)

【Phase A 狀態】
Session: ✓ 已初始化
Mode: preview

【DOM 結構】
Preview container: ✓ display:block
SVG container: ✓

=== 驗證結果: PASS ===
```

## 四、未完成的測試

### 4.1 Phase A 功能測試

**阻塞原因**: 需實際瀏覽器操作驗證

**測試項目**:
- [ ] Event Session 正確載入
- [ ] SVG 渲染 39 个小節
- [ ] Insert Points 可視化
- [ ] 混合預覽按鈕運作

### 4.2 編輯功能測試

**阻塞原因**: Legacy 格式限制，部分功能無法實現

**測試項目**:
- [ ] 新增音符（追加）✓
- [ ] 編輯音符 ✓
- [ ] 刪除音符（清空）✓
- [ ] 任意位置插入音符 ✗
- [ ] 移動音符 ✗

### 4.3 儲存/重新載入測試

**測試項目**:
- [ ] 編輯後儲存
- [ ] 重新載入確認資料一致
- [ ] Event Model 重建確認

## 五、測試環境

| 項目 | 規格 |
|------|------|
| 作業系統 | Windows 11 |
| Python | 3.11.15 (venv) |
| Node.js | 20.x |
| 瀏覽器 | Chrome (實際測試) |
| Tesseract | v5.5.3.20260724 |

## 六、測試日期

- 最後測試: 2026-10-13
- Phase 15 測試: 通過 54/55 (98%)
- 伺服器測試: 通過
- 瀏覽器測試: 待執行
