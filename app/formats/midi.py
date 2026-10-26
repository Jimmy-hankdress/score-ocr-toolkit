
from __future__ import annotations

import re
import struct
from typing import List, Tuple

from ..models import NOTE_TOKEN, ScoreDocument, ScoreMeasure, ScoreBeat

TICKS_PER_QUARTER = 480
BASE_MIDI_C4 = 60
PITCH_SEMITONE = {1:0, 2:2, 3:4, 4:5, 5:7, 6:9, 7:11}
DUR_FRAC = {
    'whole':4.0, 'half':2.0, 'quarter':1.0,
    'eighth':0.5, '16th':0.25, '32nd':0.125,
    'dotted-quarter':1.5, 'dotted-eighth':0.75, 'dotted-16th':0.375,
}


def _parse_key(key: str):
    if not key:
        key = 'C'
    m = re.match(r'([A-Ga-g])', key)
    base = m.group(1).upper() if m else 'C'
    alter = key[len(m.group(1)):] if m else ''
    semitone_map = {'C':0,'D':2,'E':4,'F':5,'G':7,'A':9,'B':11}
    base_sem = semitone_map.get(base, 0)
    tr = 0
    for ch in alter:
        if ch == '#':
            tr += 1
        elif ch in 'bB':
            tr -= 1
    return base, base_sem + tr


def _token_to_frac(token: str, beat_dur: str = 'quarter'):
    if beat_dur and beat_dur != 'quarter':
        if beat_dur.startswith('dotted-'):
            base = beat_dur[7:]
            f = DUR_FRAC.get(base, 0.25)
            return {'fraction': f * 1.5, 'name': beat_dur}
        f = DUR_FRAC.get(beat_dur, 0.25)
        return {'fraction': f, 'name': beat_dur}
    m = NOTE_TOKEN.match(token or '')
    if not m:
        return {'fraction': 1.0, 'name': 'quarter'}
    _, _, _, halvings, dots = m.groups()
    base = {0:1.0, 1:0.5, 2:0.25, 3:0.125}.get(len(halvings), 0.25)
    if dots:
        base *= 1.5
    return {'fraction': base, 'name': 'quarter'}


def _build_events(doc: ScoreDocument) -> List[Tuple[int,int,int,int]]:
    events = []
    bpm = doc.tempo or 90
    tempo_us = int(60_000_000 / bpm)
    events.append((0, 0xFF, 0x51, tempo_us))
    delta = 0
    for measure in (doc.measures or []):
        beats = measure.beats
        if not beats:
            from ..models import split_notes, split_lyrics
            nl = split_notes(measure.noteText)
            ll = split_lyrics(measure.lyricText)
            cnt = max(len(nl), len(ll), 1)
            for i in range(cnt):
                n = nl[i] if i < len(nl) else ''
                l = ll[i] if i < len(ll) else ''
                beats.append(ScoreBeat(beat=i+1, note=n, lyric=l, chord='', duration='quarter'))
        last_note_off = None   # 最近一個「真音符」的 note-off 事件索引（延音線要延它）
        last_was_rest = False  # 上一拍是否為休止（延音線延休止＝延後下一音）
        for beat in beats:
            raw_note = (beat.note or '').strip()
            note_toks = raw_note.split() if raw_note else []
            if len(note_toks) > 1:
                # 同拍多音符: 所有 note-on 於同一 tick 同時發聲，
                # 各 note-off 依該音符自身 duration 決定結束時間。
                # (舊邏輯對每個 token 都用同一個 `delta` 當 note-on 增量,
                #  使後一個音在相對時軸上被延後一整拍 → 序列化; 現改為同時。)
                chord_notes = []  # [(midi_n, dur_ticks), ...]
                for _nt in note_toks:
                    tok = _nt
                    if tok in {"-", "\u2014", "\u2013"}:
                        continue
                    if not tok or tok == "0":
                        continue
                    _m = NOTE_TOKEN.match(tok)
                    if not _m:
                        continue
                    _, _deg, _oct, _, _ = _m.groups()
                    try:
                        _pitch = int(_deg)
                    except (ValueError, TypeError):
                        continue
                    _octv = 4
                    for _ch in (_oct or ''):
                        if _ch in "'\u2018\u2019":
                            _octv += 1
                        elif _ch == ',':
                            _octv -= 1
                    _frac = _token_to_frac(tok, beat.duration)['fraction']
                    _midi_n = BASE_MIDI_C4 + PITCH_SEMITONE.get(_pitch, 0) + 12 * (_octv - 4)
                    chord_notes.append((_midi_n, int(_frac * TICKS_PER_QUARTER)))
                if not chord_notes:
                    last_note_off, last_was_rest = None, False
                    continue
                # 1) 同時 note-on: 首個 delta = 目前 `delta` (與前事件的間隔), 其餘 0
                for _i, (_mn, _dur) in enumerate(chord_notes):
                    events.append((delta if _i == 0 else 0, 0x90, _mn, 100))
                # 2) note-off: 絕對結束 = onset + 各音 dur, 依 dur 升序, 用相對增量
                _off_sorted = sorted((_dur, _mn) for (_mn, _dur) in chord_notes)
                _last_off = 0
                for _dur, _mn in _off_sorted:
                    events.append((_dur - _last_off, 0x80, _mn, 0))
                    _last_off = _dur
                # 3) 後續 beat 缺口與單音路徑一致 (視同已 advance 到本拍結束)
                delta = 0
                last_note_off, last_was_rest = None, False
                continue
            tok = raw_note
            if tok in {"-", "\u2014", "\u2013"}:
                # 延音中線：把前一音（或休止）延長一拍；語意與 musicxml 匯出一致。
                if last_note_off is not None:
                    _d, _c, _m, _v = events[last_note_off]
                    events[last_note_off] = (_d + TICKS_PER_QUARTER, _c, _m, _v)
                else:
                    delta += TICKS_PER_QUARTER
                last_note_off, last_was_rest = None, False
                continue
            if not tok or tok == "0":
                frac = _token_to_frac(tok, beat.duration)['fraction']
                delta += int(frac * TICKS_PER_QUARTER)
                last_note_off, last_was_rest = None, True
                continue
            m = NOTE_TOKEN.match(tok)
            if not m:
                continue
            _, degree, oct_part, _, _ = m.groups()
            try:
                pitch = int(degree)
            except (ValueError, TypeError):
                continue
            octv = 4
            for ch in (oct_part or ''):
                if ch in "'‘’":
                    octv += 1
                elif ch == ',':
                    octv -= 1
            frac_info = _token_to_frac(tok, beat.duration)
            frac = frac_info['fraction']
            midi_n = BASE_MIDI_C4 + PITCH_SEMITONE.get(pitch, 0) + 12 * (octv - 4)
            events.append((delta, 0x90, midi_n, 100))
            delta = 0
            events.append((int(frac * TICKS_PER_QUARTER), 0x80, midi_n, 0))
            last_note_off, last_was_rest = len(events) - 1, False
    return events


def _vlen(n: int) -> bytes:
    n = max(0, n)
    out = bytearray()
    while True:
        b = n & 0x7F
        n >>= 7
        if n:
            out.append(b | 0x80)
        else:
            out.append(b)
            break
    return bytes(out)


def _encode_track(events: List[Tuple[int,int,int,int]]) -> bytes:
    body = bytearray()
    for delta, status, d1, d2 in events:
        body.extend(_vlen(delta))
        if status == 0xFF:
            body.append(0xFF)
            body.append(d1)
            if d1 == 0x51:
                body.extend(_vlen(3))
                body.append((d2 >> 16) & 0xFF)
                body.append((d2 >> 8) & 0xFF)
                body.append(d2 & 0xFF)
            else:
                body.extend(_vlen(d2))
        else:
            body.append(status)
            body.append(d1)
            body.append(d2)
    return bytes(body)


def export_score_to_midi(doc: ScoreDocument) -> bytes:
    ev = _build_events(doc)
    hdr = struct.pack('>4sIHHH', b'MThd', 6, 0, 1, TICKS_PER_QUARTER)
    trk = _encode_track(ev)
    return hdr + struct.pack('>4sI', b'MTrk', len(trk)) + trk


def export_score_to_midi_hex(doc: ScoreDocument) -> str:
    return export_score_to_midi(doc).hex()
