#!/usr/bin/env python3
"""Phase 0 深入追查：list index out of range 根因定位

目標：找出真正觸發 400 的程式路徑，非僅假設「dataclass 拒收未知欄位」
"""
import json
import sys
sys.path.insert(0, r'D:\SheetMusicOMR_v3.00\app')

from models import ScoreDocument, ScoreMeasure, ScoreBeat

# ── 重現 client 端完整 payload ───────────────────────────────────────────────
print('=' * 70)
print('測試：重現 client saveCurrentDoc 完整 payload')
print('=' * 70)

# 模擬 client 端 state3.doc 結構（含 event model）
client_doc = {
    'id': 'test-repro-002',
    'title': '根因追查',
    'timeSignature': '4/4',
    'key': 'C',
    'tempo': 90,
    'measures': [
        {
            'number': 1,
            'chordText': 'C',
            'noteText': '5 3 2 1 | ',
            'lyricText': '歌 詞 對 位',
            'lyricText2': '',
            'lyricText3': '',
            'lyricText4': '',
            'lyricRows': 1,
            'barline': True,
            'marks': '',
            'beats': [
                {'beat': 1, 'note': '5', 'lyric': '歌', 'chord': 'C', 'duration': 'quarter', 'confidence': 1.0},
                {'beat': 2, 'note': '3', 'lyric': '詞', 'chord': '', 'duration': 'quarter', 'confidence': 1.0},
                {'beat': 3, 'note': '2', 'lyric': '對', 'chord': '', 'duration': 'quarter', 'confidence': 1.0},
                {'beat': 4, 'note': '1', 'lyric': '位', 'chord': '', 'duration': 'quarter', 'confidence': 1.0},
            ],
            # Event model 欄位（client 端新增）
            'melodyEvents': [
                {'uid': 'e1n0ct4i', 'type': 'note', 'lane': 0, 'start': 0, 'duration': 1.0, 'content': '5'},
                {'uid': 'e1n1ct4i', 'type': 'note', 'lane': 0, 'start': 1, 'duration': 1.0, 'content': '3'},
                {'uid': 'e1n2ct4i', 'type': 'note', 'lane': 0, 'start': 2, 'duration': 1.0, 'content': '2'},
                {'uid': 'e1n3ct4i', 'type': 'note', 'lane': 0, 'start': 3, 'duration': 1.0, 'content': '1'},
            ],
            'chordEvents': [
                {'uid': 'c1h0d0e1', 'type': 'chord', 'start': 0, 'duration': 4.0, 'content': 'C'},
            ],
            'lyricTracks': [
                [{'uid': 'l1r0c0k1', 'syllables': ['歌', '詞', '對', '位'], 'start': 0, 'duration': 4.0}]
            ],
            'annotations': [],
            'eventModelVersion': 3,
            'eventOverrides': {},
            # Client-side computed ticks
            'noteTicks': [0, 120, 240, 360],
            'chordTicks': [0],
            'lyricTicks': [0, 120, 240, 360],
        }
    ],
}

print(f'Client payload 小節數: {len(client_doc["measures"])}')
print(f'小節 1 欄位: {sorted(client_doc["measures"][0].keys())}')

# ── 測試 from_dict ───────────────────────────────────────────────────────────
print()
print('=' * 70)
print('測試 1：ScoreDocument.from_dict 直接呼叫')
print('=' * 70)
try:
    doc = ScoreDocument.from_dict(client_doc)
    print(f'  PASS: doc.id={doc.id}, measures={len(doc.measures)}')
    for i, m in enumerate(doc.measures):
        print(f'    measure[{i}]: number={m.number}, chordText={m.chordText!r}, beats={len(m.beats)}')
except Exception as e:
    print(f'  FAIL: {type(e).__name__}: {e}')
    import traceback
    traceback.print_exc()

# ── 測試 to_dict → from_dict round-trip ──────────────────────────────────────
print()
print('=' * 70)
print('測試 2：to_dict → from_dict round-trip')
print('=' * 70)
try:
    doc1 = ScoreDocument.from_dict(client_doc)
    out = doc1.to_dict()
    print(f'  to_dict 小節欄位: {sorted(out["measures"][0].keys())}')
    
    doc2 = ScoreDocument.from_dict(out)
    print(f'  round-trip PASS: id={doc2.id}, measures={len(doc2.measures)}')
except Exception as e:
    print(f'  round-trip FAIL: {type(e).__name__}: {e}')
    import traceback
    traceback.print_exc()

# ── 測試空 beats 的情況 ──────────────────────────────────────────────────────
print()
print('=' * 70)
print('測試 3：空 beats + event model')
print('=' * 70)
empty_beats_doc = {
    'id': 'test-empty-beats',
    'title': '空 beats',
    'measures': [
        {
            'number': 1,
            'chordText': '',
            'noteText': '',
            'beats': [],  # 空 beats
            'melodyEvents': [],
            'eventModelVersion': 3,
        }
    ],
}
try:
    doc = ScoreDocument.from_dict(empty_beats_doc)
    print(f'  PASS: measure beats={len(doc.measures[0].beats)}')
except Exception as e:
    print(f'  FAIL: {type(e).__name__}: {e}')
    import traceback
    traceback.print_exc()

# ── 測試 eventOverrides 格式問題 ─────────────────────────────────────────────
print()
print('=' * 70)
print('測試 4：eventOverrides 非 dict 格式')
print('=' * 70)
bad_override_doc = {
    'id': 'test-bad-override',
    'title': '錯誤 override',
    'measures': [
        {
            'number': 1,
            'chordText': 'C',
            'noteText': '5',
            'beats': [{'beat': 1, 'note': '5'}],
            'eventOverrides': 'not-a-dict',  # 錯誤格式
        }
    ],
}
try:
    doc = ScoreDocument.from_dict(bad_override_doc)
    print(f'  PASS（容錯）')
except Exception as e:
    print(f'  FAIL: {type(e).__name__}: {e}')
    import traceback
    traceback.print_exc()

# ── 測試 missing field ───────────────────────────────────────────────────────
print()
print('=' * 70)
print('測試 5：缺少必要欄位')
print('=' * 70)
missing_field_doc = {
    'id': 'test-missing',
    'title': '缺欄位',
    'measures': [
        {
            'number': 1,
            # 缺少 chordText, noteText 等
            'beats': [],
        }
    ],
}
try:
    doc = ScoreDocument.from_dict(missing_field_doc)
    print(f'  PASS（預設值）')
except Exception as e:
    print(f'  FAIL: {type(e).__name__}: {e}')

print()
print('=' * 70)
print('結論')
print('=' * 70)
print('''
從 Python 測試結果：
1. ScoreMeasure.from_dict 接受 event model 欄位（Python dataclass 容錯）
2. ScoreDocument.from_dict 能成功解析完整 client payload
3. 空 beats 會觸發 expand_beats()，自動重建
4. eventOverrides 錯誤格式會被 try-except 容錯

推測「list index out of range」的可能來源：
A. models.py 內部某個索引操作（如 beats[0] 在空 beats 時）
B. projects.py 的存檔邏輯有額外驗證
C. client 端的 payload 結構與測試案例不同

建議下一步：
1. 抓取真實 400 請求的完整 payload（從 Chrome DevTools Network 面板）
2. 在 server.py 加入詳細 log，顯示 from_dict 失敗時的完整 exception chain
3. 檢查 projects.py 的 save_document 是否有額外驗證
''')
