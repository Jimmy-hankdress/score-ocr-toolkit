"""
SoLa321 格式 JSON 輸出器（v2.0）。

輸入：ScoreDocument（來自 app/models.py）
輸出：符合 SoLa321 規範的 JSON 字串（UTF-8）

設計目標：
- 支援四分、八分、十六分、附點、延音、休止符等基本時值
- 支援高低音點（' 和 ,）
- 支援和弦標示與歌詞陣列（每個音符對應一個歌詞字符）
- 支援速度（tempo）、拍號（timeSignature）、調號（key）等 metadata
"""

from __future__ import annotations

import json
from typing import Any

from ..models import MEASURES_PER_LINE, NOTE_TOKEN, ScoreDocument, ScoreMeasure, ScoreBeat, split_lyrics

DURATION_MAP = {
    'whole': 'whole',
    'half': 'half',
    'quarter': 'quarter',
    'eighth': 'eighth',
    '16th': '16th',
    '32nd': '32nd',
}

# 延音中線（-）token：標準簡譜「數字 -」＝ 前一音延長一拍。
# 與 musicxml 匯出同一語意：把一拍併入前一音時值，不另建音符。
_DASH_TOKENS = {"-", "\u2014", "\u2013"}
_DUR_TICKS = {"whole": 16, "half": 8, "quarter": 4, "eighth": 2, "16th": 1, "32nd": 1}


def _ticks_of(duration_name: str, dotted: bool) -> int:
    base = _DUR_TICKS.get(duration_name, 4)
    total, add = base, base
    if dotted:
        add //= 2
        total += add
    return total


def _name_of_ticks(total: int) -> tuple:
    """ticks → (duration 名稱, 是否附點)；無精確對應時取 ≤ total 的最大可表示時值。"""
    best, best_t = ("quarter", False), 0
    for name, base in _DUR_TICKS.items():
        for dots in range(0, 4):
            t, a = base, base
            for _ in range(dots):
                a //= 2
                t += a
            if t <= total and t > best_t:
                best_t, best = t, (name, dots > 0)
    return best


def _pitch_number_from_token(token: str, base_octave: int = 4) -> dict:
    """
    將簡譜 token（如 '5', '5_', '5.', '5\'', '5,'）解析為 pitch 資訊。
    回傳：{pitch: int, octave: int, duration: str, dotted: bool, tied: bool}
    pitch 為 1-7（0 代表休止）
    """
    if not token:
        return {}

    # 處理休止符
    if token.strip() == '0':
        return {'pitch': 0, 'octave': base_octave, 'duration': 'quarter', 'dotted': False}

    # 基本音符部分：提取 1-7 數字
    import re
    m = NOTE_TOKEN.match(token)
    if not m:
        return {}

    acc, degree, octave_part, halvings, dots = m.groups()

    # pitch 數字
    try:
        pitch = int(degree)
    except (ValueError, TypeError):
        return {}

    # 八度處理：' 代表上移， , 代表下移
    octave = base_octave
    for ch in (octave_part or ''):
        if ch in "'‘’":
            octave += 1
        elif ch == ',':
            octave -= 1

    # 時值處理：_ 代表 halving（八分、十六分等）
    halvings_count = len(halvings or '')
    if halvings_count == 0:
        duration = 'quarter'
    elif halvings_count == 1:
        duration = 'eighth'
    elif halvings_count == 2:
        duration = '16th'
    elif halvings_count == 3:
        duration = '32nd'
    else:
        duration = '16th'  # 預設避免出錯

    # 附點處理
    dotted = bool(dots)

    return {
        'pitch': pitch,
        'octave': octave,
        'duration': duration,
        'dotted': dotted,
        'tied': False,  # 延音由模型中的 tieStart/tieEnd 決定
    }


def _beat_to_note_json(beat: NoteBeat, index: int, base_octave: int = 4) -> dict:
    """將單一 NoteBeat 轉為 SoLa321 note JSON 物件。"""
    token = (beat.note or '').strip()
    if not token:
        if beat.rest:
            return {
                'id': 'mNone',
                'pitch': 0,
                'duration': 'quarter',
                'octave': base_octave,
                'dotted': False,
                'tieStart': False,
                'tieEnd': False,
                'accidental': None,
                'isPlaceholder': False,
                'type': 'rest',
            }
        return {}

    pitch_info = _pitch_number_from_token(token, base_octave)
    if not pitch_info:
        return {}

    pitch = pitch_info.get('pitch', 0)
    octave = pitch_info.get('octave', base_octave)
    duration = pitch_info.get('duration', 'quarter')
    dotted = pitch_info.get('dotted', False)
    tied_start = bool(beat.tied_to_next) if hasattr(beat, 'tied_to_next') else False

    return {
        'id': f'mNone',
        'pitch': pitch,
        'duration': duration,
        'octave': octave,
        'dotted': dotted,
        'tieStart': tied_start,
        'tieEnd': False,
        'accidental': None,
        'isPlaceholder': False,
        'type': 'note' if pitch != 0 else 'rest',
    }


def _measure_to_sola321_json(
    measure: ScoreMeasure,
    base_octave: int = 4,
    doc_key: str = "C",
    doc_time_sig: str = "4/4",
    doc_tempo: int = 90,
) -> dict:
    """將單一 ScoreMeasure 轉為 SoLa321 measure JSON。"""
    notes = []
    lyrics_list = []

    beats = measure.beats or []

    for idx, beat in enumerate(beats):
        token = (beat.note or "").strip()
        if not token:
            # 若無音符 token：若 beat.note 為 "0" 或空白，視為休止
            if token == "0" or (not token and not beat.note):
                notes.append({
                    "id": "mNone",
                    "pitch": 0,
                    "duration": "quarter",
                    "octave": base_octave,
                    "dotted": False,
                    "tieStart": False,
                    "tieEnd": False,
                    "accidental": None,
                    "isPlaceholder": False,
                    "type": "rest",
                })
                lyrics_list.append("")
            continue

        # 延音中線：標準簡譜「數字 -」＝ 前一音延長一拍。
        # 與 musicxml 匯出同一語意：把一拍併入前音時值，不另建音符（不佔歌詞對齊位以外的樂音）。
        if token in _DASH_TOKENS:
            if notes:  # 延前一音（含休止；與 musicxml 匯出同一語意）
                _n, _d = _name_of_ticks(_ticks_of(notes[-1]["duration"], notes[-1]["dotted"]) + 4)
                notes[-1]["duration"] = _n
                notes[-1]["dotted"] = _d
            lyrics_list.append("")
            continue

        pitch_info = _pitch_number_from_token(token, base_octave)
        if not pitch_info:
            lyrics_list.append("")
            continue

        pitch = pitch_info["pitch"]
        octave = pitch_info["octave"]
        duration = pitch_info["duration"]
        dotted = pitch_info["dotted"]
        # tied_to_next 目前模型無此欄位，忽略
        tied_start = False

        note_obj = {
            "id": f"m{measure.number}-n{idx}",
            "pitch": pitch,
            "duration": duration,
            "octave": octave,
            "dotted": dotted,
            "tieStart": tied_start,
            "tieEnd": False,
            "accidental": None,
            "isPlaceholder": False,
            "type": "note" if pitch != 0 else "rest",
        }
        notes.append(note_obj)

        # 歌詞處理：每個音符對應一個歌詞字符
        lyric = (beat.lyric or "").strip()
        lyrics_list.append(lyric)

    # 解析 doc 的 timeSignature 字串（例："4/4" → numerator=4, denominator=4）
    ts_parts = doc_time_sig.split("/")
    ts_num = int(ts_parts[0]) if ts_parts and ts_parts[0].isdigit() else 4
    ts_den = int(ts_parts[1]) if len(ts_parts) > 1 and ts_parts[1].isdigit() else 4

    # 第 2～4 行歌詞（lyricText2~4）：同樣 split_lyrics 逐詞切分、依拍序對齊；
    # 歌詞必須附著於音符事件——無拍（beats 為空）時無附著點，不輸出。
    extra: dict[str, list[str]] = {}
    for num, src in ((2, measure.lyricText2), (3, measure.lyricText3), (4, measure.lyricText4)):
        words = split_lyrics(src)
        if not words or not beats:
            continue
        pad = [words[i] if i < len(words) else "" for i in range(len(beats))]
        if any(pad):
            extra[f"lyrics{num}"] = pad

    result = {
        "id": f"m{measure.number}",
        "notes": notes,
        "timeSignature": {
            "numerator": ts_num,
            "denominator": ts_den,
        },
        "keySignature": {
            "key": doc_key,
        },
        "chord": (measure.chordText or "").strip() or "",
        "lyrics": lyrics_list,
    }
    result.update(extra)
    return result


def _document_to_sola321_json(doc: ScoreDocument, base_octave: int = 4) -> dict:
    """將完整 ScoreDocument 轉為 SoLa321 JSON 物件。"""
    rows = []

    bars_per_row = getattr(doc, 'measures_per_line', MEASURES_PER_LINE) or MEASURES_PER_LINE
    measures = doc.measures or [ScoreMeasure()]

    # 將 measures 分組為 rows
    for i in range(0, len(measures), bars_per_row):
        row_measures = measures[i:i + bars_per_row]
        row_measures_json = [
            _measure_to_sola321_json(
                m,
                base_octave=base_octave,
                doc_key=doc.key or "C",
                doc_time_sig=doc.timeSignature or "4/4",
                doc_tempo=doc.tempo or 90,
            )
            for m in row_measures
        ]
        rows.append({
            'id': f'row-{i // bars_per_row + 1}',
            'measures': row_measures_json,
        })

    _ts_parts = (doc.timeSignature or "4/4").split("/")
    _ts_num = int(_ts_parts[0]) if _ts_parts and _ts_parts[0].isdigit() else 4
    _ts_den = int(_ts_parts[1]) if len(_ts_parts) > 1 and _ts_parts[1].isdigit() else 4

    metadata = {
        'title': doc.title or '未命名樂譜',
        'subtitle': '',
        'lyricist': doc.lyricist or '',
        'composer': doc.composer or '',
        'arranger': '',
        'key': doc.key or 'C',
        'originalKey': doc.key or 'C',
        'capo': 0,
        'tempo': doc.tempo or 90,
        'timeSignatureNumerator': _ts_num,
        'timeSignatureDenominator': _ts_den,
        'barsPerRow': bars_per_row,
        'voiceInstruments': ['general'],
        'voiceMixerConfig': [
            {
                'muted': False,
                'solo': False,
                'volume': 0.8,
            }
        ],
    }

    return {
        'id': doc.id or 'last-dance-wubai-2026',
        'metadata': metadata,
        'rows': rows,
        'ties': [],
        'slurs': [],
        'sectionMarks': [],
        'annotations': [],
        'createdAt': doc.createdAt or '',
        'updatedAt': doc.updatedAt or '',
    }


def export_score_to_sola321(doc: ScoreDocument, base_octave: int = 4, pretty: bool = True) -> str:
    """將 ScoreDocument 導出為 SoLa321 JSON 字串。"""
    data = _document_to_sola321_json(doc, base_octave)
    return json.dumps(data, ensure_ascii=False, indent=2 if pretty else None)


def export_score_to_sola321_bytes(doc: ScoreDocument, base_octave: int = 4) -> bytes:
    """回傳 UTF-8 位元組（用於 HTTP 回應）。"""
    return export_score_to_sola321(doc, base_octave).encode('utf-8')
