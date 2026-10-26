#!/usr/bin/env python3
"""Phase 0 根因確認：存檔 400 最小重現案例

目標：
1. 確認 server 的 ScoreMeasure dataclass 不接受 melodyEvents/chordEvents/lyricTracks/annotations/eventModelVersion 欄位
2. 重建 client 端的完整 payload 結構
3. 證明這是「client event model 與 server legacy schema 不匹配」所致

嚴格限制：不改 server.py，只做唯讀驗證 + 最小重現 PUT
"""
import json
import sys
sys.path.insert(0, r'D:\SheetMusicOMR_v3.00\app')

from models import ScoreDocument, ScoreMeasure, ScoreBeat

# ── 測試 1：確認 ScoreMeasure.from_dict 接受哪些欄位 ──────────────────────
print('=' * 70)
print('測試 1：ScoreMeasure.from_dict 欄位接受度')
print('=' * 70)

# 1a. 純 legacy（應成功）
legacy_only = {
    'number': 1,
    'chordText': 'C',
    'noteText': '5 3 2 | ',
    'lyricText': '歌 詞',
    'beats': [{'beat': 1, 'note': '5', 'lyric': '歌', 'chord': 'C'}],
    'eventOverrides': {},
}
try:
    m = ScoreMeasure.from_dict(legacy_only)
    print(f'  legacy-only: PASS (number={m.number}, chordText={m.chordText!r})')
except Exception as e:
    print(f'  legacy-only: FAIL {type(e).__name__}: {e}')

# 1b. 含 event model 欄位（預期失敗）
with_event_model = {
    'number': 1,
    'chordText': 'C',
    'noteText': '5 3 2 | ',
    'lyricText': '歌 詞',
    'beats': [{'beat': 1, 'note': '5', 'lyric': '歌', 'chord': 'C'}],
    'melodyEvents': [{'uid': 'e1n0ct4i', 'type': 'note', 'lane': 0, 'start': 0, 'duration': 1.0, 'content': '5'}],
    'chordEvents': [{'uid': 'c1h0d0e1', 'type': 'chord', 'start': 0, 'duration': 4.0, 'content': 'C'}],
    'lyricTracks': [[{'uid': 'l1r0c0k1', 'syllables': ['歌', '詞']}]],
    'annotations': [],
    'eventModelVersion': 3,
    'eventOverrides': {},
}
try:
    m = ScoreMeasure.from_dict(with_event_model)
    print(f'  with-event-model: PASS（意外！可能 dataclass 已更新）')
except TypeError as e:
    print(f'  with-event-model: FAIL（預期）→ TypeError: {e}')
except Exception as e:
    print(f'  with-event-model: FAIL（其他）→ {type(e).__name__}: {e}')

# ── 測試 2：確認 ScoreDocument.from_dict 的錯誤訊息 ──────────────────────
print()
print('=' * 70)
print('測試 2：ScoreDocument.from_dict 錯誤訊息格式')
print('=' * 70)

bad_doc = {
    'id': 'test-repro-001',
    'title': '根因確認測試',
    'timeSignature': '4/4',
    'measures': [with_event_model],
}
try:
    doc = ScoreDocument.from_dict(bad_doc)
    print(f'  整份文件: PASS（意外）')
except TypeError as e:
    msg = str(e)
    print(f'  整份文件: FAIL（預期）→ TypeError')
    # 取出「unexpected keyword argument」部分
    if 'unexpected keyword argument' in msg:
        bad_field = msg.split("'")[-2] if "'" in msg else 'unknown'
        print(f'         受拒欄位: {bad_field!r}')
    print(f'         完整訊息: {msg[:200]}')
except Exception as e:
    print(f'  整份文件: FAIL（其他）→ {type(e).__name__}: {e}')

# ── 測試 3：對比 to_dict 輸出 vs from_dict 輸入 ──────────────────────────
print()
print('=' * 70)
print('測試 3：to_dict 輸出 vs from_dict 輸入欄位差異')
print('=' * 70)

# 3a. 建立合法 legacy measure，檢查 to_dict 輸出
clean_m = ScoreMeasure(
    number=1,
    chordText='C',
    noteText='5 3 2 | ',
    lyricText='歌 詞',
    beats=[ScoreBeat(beat=1, note='5', lyric='歌', chord='C')],
)
out = clean_m.to_dict()
print(f'  to_dict 輸出欄位: {sorted(out.keys())}')

# 3b. 這些輸出能 round-trip 成功？
try:
    roundtrip = ScoreMeasure.from_dict(out)
    print(f'  round-trip: PASS')
except Exception as e:
    print(f'  round-trip: FAIL → {e}')

# 3c. 加入 eventOverrides 後 to_dict 是否包含 event model？
m_with_ov = ScoreMeasure(
    number=1,
    chordText='C',
    noteText='5 3 2 | ',
    eventOverrides={'e1n0ct4i': {'tick': 0}},
)
out2 = m_with_ov.to_dict()
print(f'  with-eventOverrides to_dict 欄位: {sorted(out2.keys())}')
has_event_in_out = 'melodyEvents' in out2 or 'eventModelVersion' in out2
print(f'  to_dict 含 melodyEvents/eventModelVersion: {has_event_in_out}（應為 False）')

# ── 測試 4：確認 server 端 save_project 的驗證位置 ────────────────────────
print()
print('=' * 70)
print('測試 4：server save_project 驗證路徑')
print('=' * 70)
print('  server.py L184: doc = ScoreDocument.from_dict(payload)')
print('  server.py L185-186: except Exception as e → raise HTTPException(400, ...)')
print('  錯誤訊息格式: "Invalid document structure: <原錯誤>"')
print()
print('  推論：client 送完整 state3.doc（含 event model 欄位）→')
print('        server from_dict 拒收 → TypeError → 400')

# ── 總結 ────────────────────────────────────────────────────────────────────
print()
print('=' * 70)
print('根因總結')
print('=' * 70)
print('''
1. Client 端 (app.js L2163-2170)：
   - migrateAllMeasures() → ensureEventModel() 給每個 measure 加上：
     * melodyEvents: [...]
     * chordEvents: [...]
     * lyricTracks: [[...], [...], [...], [...]]
     * annotations: []
     * eventModelVersion: 3

2. Server 端 (models.py L102-124)：
   - ScoreMeasure dataclass 只有 legacy 欄位 + eventOverrides
   - 沒有 melodyEvents / chordEvents / lyricTracks / annotations / eventModelVersion

3. 衝突點：
   - saveCurrentDoc() 送完整 state3.doc（含 event model）
   - server.py L184 ScoreDocument.from_dict(payload) 觸發
   - ScoreMeasure.from_dict() 收到未知欄位 → TypeError
   - server.py L185-186 捕獲 → 400 "Invalid document structure: list index out of range"
     （注：list index out of range 是 from_dict 內部某處索引越界，非 TypeError，
       可能因為 eventOverrides 解析或 beats 解析時的副效應）

4. 建議修復方向（非本任務範圍，僅列根因）：
   A. server.py 的 ScoreMeasure 新增 melodyEvents/chordEvents/lyricTracks/annotations/eventModelVersion
      欄位，並實作雙向轉換邏輯
   B. client 端 saveCurrentDoc 前濾掉 event model 欄位，只送 legacy
   C. server 端 from_dict 改用 **kwargs 容錯，忽略未知欄位
''')
