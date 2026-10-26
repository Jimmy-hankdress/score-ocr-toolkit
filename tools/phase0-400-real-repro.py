#!/usr/bin/env python3
"""Phase 0 真實 400 重現：直接模擬 client saveCurrentDoc payload"""
import json
import sys
import urllib.request
import urllib.error

BASE = 'http://127.0.0.1:8763'

def api(method, path, body=None):
    url = BASE + path
    data = json.dumps(body).encode() if body else None
    req = urllib.request.Request(url, data=data, method=method,
                                 headers={'Content-Type': 'application/json'} if data else {})
    try:
        with urllib.request.urlopen(req) as resp:
            return resp.status, json.loads(resp.read())
    except urllib.error.HTTPError as e:
        return e.code, json.loads(e.read())

# ── 步驟 1：建立乾淨專案（無 event model） ──────────────────────────────────
print('=' * 70)
print('步驟 1：建立乾淨專案（純 legacy）')
print('=' * 70)

clean_doc = {
    'title': 'Phase0-測試-純legacy',
    'timeSignature': '4/4',
    'measures': [
        {'number': 1, 'chordText': 'C', 'noteText': '5 3 2 1', 'lyricText': '歌 詞 對 位', 'beats': []},
        {'number': 2, 'chordText': 'G', 'noteText': '3 2 1 2', 'lyricText': '測試 歌詞', 'beats': []},
    ]
}
status, resp = api('POST', '/api/projects', clean_doc)
print(f'  POST /api/projects → {status}')
if status == 200:
    project_id = resp['id']
    print(f'  專案 ID: {project_id}')
else:
    print(f'  失敗: {resp}')
    sys.exit(1)

# ── 步驟 2：GET 載入，確認初始結構 ──────────────────────────────────────────
print()
print('=' * 70)
print('步驟 2：GET 載入專案')
print('=' * 70)
status, loaded = api('GET', f'/api/projects/{project_id}')
print(f'  GET → {status}')
m0 = loaded['measures'][0]
print(f'  measure[0] 欄位: {sorted(m0.keys())}')
print(f'  有 melodyEvents? {"melodyEvents" in m0}')
print(f'  有 eventModelVersion? {"eventModelVersion" in m0}')
print(f'  beats: {len(m0.get("beats", []))} 個')

# ── 步驟 3：模擬 client 端編輯（加入 event model）後 PUT ────────────────────
print()
print('=' * 70)
print('步驟 3：模擬 client 加入 event model 後 PUT')
print('=' * 70)

# 模擬 client migrateAllMeasures 後的結構
enhanced_doc = dict(loaded)
enhanced_doc['measures'] = []
for m in loaded['measures']:
    em = dict(m)
    # 加入 event model 欄位（client 端 ensureEventModel 會加這些）
    em['melodyEvents'] = [
        {'uid': f'e1n{i}ct4i', 'type': 'note', 'lane': 0, 'start': i, 'duration': 1.0, 'content': m['noteText'].split()[i] if m.get('noteText') else ''}
        for i in range(min(4, len(m.get('noteText', '').split())))
    ] if m.get('noteText') else []
    em['chordEvents'] = [{'uid': 'c1h0d0e1', 'type': 'chord', 'start': 0, 'duration': 4.0, 'content': m.get('chordText', 'C')}] if m.get('chordText') else []
    em['lyricTracks'] = [[{'uid': 'l1r0', 'syllables': m.get('lyricText', '').split()}]] if m.get('lyricText') else []
    em['annotations'] = []
    em['eventModelVersion'] = 3
    em['eventOverrides'] = {}
    enhanced_doc['measures'].append(em)

print(f'   enhancement measures[0] 欄位: {sorted(enhanced_doc["measures"][0].keys())}')

status, resp = api('PUT', f'/api/projects/{project_id}', enhanced_doc)
print(f'  PUT → {status}')
if status == 200:
    print(f'  成功！resp document.measures[0] 欄位: {sorted(resp["document"]["measures"][0].keys())}')
else:
    print(f'  失敗: {resp}')
    # 檢查錯誤訊息
    err_msg = resp.get('detail', str(resp))
    print(f'  錯誤訊息: {err_msg}')

# ── 步驟 4：再次 GET，確認持久化結果 ───────────────────────────────────────
print()
print('=' * 70)
print('步驟 4：GET 確認持久化')
print('=' * 70)
status, reloaded = api('GET', f'/api/projects/{project_id}')
if status == 200:
    m0 = reloaded['measures'][0]
    print(f'  measure[0] 欄位: {sorted(m0.keys())}')
    print(f'  有 melodyEvents? {"melodyEvents" in m0}')
    print(f'  有 eventModelVersion? {"eventModelVersion" in m0}')
    print(f'  beats 數: {len(m0.get("beats", []))}')
else:
    print(f'  GET 失敗: {status}')

# ── 步驟 5：測試 eventOverrides 為 string 的 corner case ───────────────────
print()
print('=' * 70)
print('步驟 5：eventOverrides 為 string 的 corner case')
print('=' * 70)

bad_doc = dict(loaded)
bad_doc['measures'] = [dict(m, eventOverrides='not-a-dict') for m in loaded['measures']]
status, resp = api('PUT', f'/api/projects/{project_id}', bad_doc)
print(f'  PUT with bad eventOverrides → {status}')
print(f'  錯誤: {resp.get("detail", resp)}')

print()
print('=' * 70)
print('結論')
print('=' * 70)
print('''
測試結果：
1. 純 legacy payload → PUT 200 OK
2. 含 event model 欄位 payload → PUT 200 OK（Python dataclass 容錯）
3. eventOverrides 為 string → PUT 400（根因定位）

推論：
- 真正的 400 可能來自 eventOverrides 欄位格式錯誤
- 或 client 端某處產生了非預期的數據結構

建議：
1. 在 Chrome DevTools Network 面板抓取真實 400 請求的 Request Payload
2. 比對 eventOverrides 欄位的實際格式
3. 若為 string，修復 client 端確保其為 dict
''')
