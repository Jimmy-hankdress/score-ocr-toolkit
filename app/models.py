"""核心資料模型（規劃書第 5 章）。

ScoreDocument → ScoreMeasure → ScoreBeat 兩層設計：
* 小節層 (`chordText` / `noteText` / `lyricText`) 保存使用者在原稿畫布看到與
  編輯的完整句子。
* 拍位層 (`beats`) 保存 OCR 對齊與 MusicXML 生成所需的細節。
前端只編輯整句，拍位由本層在失焦／保存時重新展開，不會遺失對齊關係。
"""
from __future__ import annotations

import re
import uuid
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone

MEASURES_PER_LINE = 4

# 簡譜 token：#/b 升降 → 1-7 音級（0 為休止）→ ' 高八度 / , 低八度（含組合高低音點）→ _ 減半時值 → . 附點
NOTE_TOKEN = re.compile(r"^([#b\u266f\u266d]*)([0-7])([',\u2019\u0307\u0323]*)(_*)(\.*)[~^3]*$")
CJK = re.compile(r"[\u3400-\u4dbf\u4e00-\u9fff\uf900-\ufaff\u3040-\u30ff]")


def now_iso() -> str:
    return datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds")


def new_id(prefix: str) -> str:
    return f"{prefix}_{uuid.uuid4().hex[:12]}"


def split_notes(text: str) -> list[str]:
    """把整句簡譜切成 token；`|` 視為小節線，由呼叫端處理。"""
    return [t for t in re.split(r"\s+", (text or "").strip()) if t and t != "|"]


def split_lyrics(text: str) -> list[str]:
    """歌詞切分：中文逐字展開，拉丁字以空白／連字號分詞（規劃書附錄 A）。"""
    text = (text or "").strip()
    if not text:
        return []
    if " " in text and not CJK.search(text):
        return [t for t in re.split(r"\s+", text) if t]
    out: list[str] = []
    buf = ""
    for ch in text:
        if CJK.search(ch):
            if buf.strip():
                out.append(buf.strip())
                buf = ""
            out.append(ch)
        elif ch.isspace():
            if buf.strip():
                out.append(buf.strip())
            buf = ""
        else:
            buf += ch
    if buf.strip():
        out.append(buf.strip())
    return out


def split_chords(text: str) -> list[str]:
    return [t for t in re.split(r"\s+", (text or "").strip()) if t and t != "|"]


@dataclass
class ScoreBeat:
    beat: int = 1
    note: str = ""
    lyric: str = ""
    chord: str = ""
    duration: str = "quarter"
    confidence: float = 1.0
    annotation: str = ""

    def to_dict(self) -> dict:
        return asdict(self)

    @staticmethod
    def from_dict(d: dict) -> "ScoreBeat":
        return ScoreBeat(
            beat=int(d.get("beat", 1) or 1),
            note=str(d.get("note", "") or ""),
            lyric=str(d.get("lyric", "") or ""),
            chord=str(d.get("chord", "") or ""),
            duration=str(d.get("duration", "quarter") or "quarter"),
            confidence=float(d.get("confidence", 1.0) or 0.0),
            annotation=str(d.get("annotation", "") or ""),
        )


def duration_from_token(token: str) -> str:
    m = NOTE_TOKEN.match(token or "")
    if not m:
        return "quarter"
    _, _, _, halvings, dots = m.groups()
    base = {0: "quarter", 1: "eighth", 2: "16th", 3: "32nd"}.get(len(halvings), "quarter")
    return f"dotted-{base}" if dots else base


@dataclass
class ScoreMeasure:
    number: int = 1
    lineIndex: int = 0
    linePosition: int = 1  # 1..3，每行固定三個小節
    chordText: str = ""
    chordOffsets: list[int] = field(default_factory=list)  # 和弦滑軌：第 k 個和弦對齊的拍序（token 序，0 起；預設 [0,1,2...]）
    chordTicks: list[int] = field(default_factory=list)    # 和弦精確 tick 位置（480 ticks = 1 quarter note）
    noteText: str = ""
    noteTicks: list[int] = field(default_factory=list)     # 音符精確 tick 位置
    lyricText: str = ""
    lyricTicks: list[int] = field(default_factory=list)    # 第 1 行歌詞音節精確 tick 位置
    lyricText2: str = ""   # 同小節第 2～4 行歌詞（Score Studio 多行歌詞）
    lyricText2Ticks: list[int] = field(default_factory=list)
    lyricText3: str = ""
    lyricText3Ticks: list[int] = field(default_factory=list)
    lyricText4: str = ""
    lyricText4Ticks: list[int] = field(default_factory=list)
    lyricRows: int = 1     # 使用者已新增的歌曲行數（1～4，空白末行自動收回）
    barline: bool = True   # 本小節右側小節線是否顯示（Score Studio 工具列可增刪；舊檔無此欄位＝預設顯示）
    marks: str = ""        # 結構記號（代號形式，空格分隔）：SN 𝄋 / RS 𝄆 / RE 𝄇 / DC / DS / 1. / 2. / CODA / tr / ~ / p mp mf f / cresc. dim.
    section: str = ""      # 段落標籤（如 intro / verse / chorus / bridge / outro / A / B / C / D）
    beats: list[ScoreBeat] = field(default_factory=list)
    sourcePage: int | None = None
    eventOverrides: dict = field(default_factory=dict)  # Phase 6D：事件覆蓋 { uid: {"tick": int} }；僅非空時持久化
    melodyEvents: list = field(default_factory=list)
    chordEvents: list = field(default_factory=list)
    lyricTracks: list = field(default_factory=list)
    annotations: list = field(default_factory=list)
    eventModelVersion: int = 0

    def expand_beats(self, min_confidence: float = 1.0) -> list[ScoreBeat]:
        """由整句重建拍位，盡量保留既有拍位的信心值與註記。
        
        關鍵變更：若有 tick 陣列，依 tick 位置分配 beat（tick 480 = beat 1）。
        否則回退原本均勻分配邏輯。
        """
        notes = split_notes(self.noteText)
        lyrics = split_lyrics(self.lyricText)
        chords = split_chords(self.chordText)
        
        # 決定每個 token 的 beat 位置（1-based），切片對齊 token 長度避免 IndexError
        def tick_to_beat(tick: int) -> int:
            return max(1, (tick // 480) + 1)  # 0-based tick -> 1-based beat
        
        note_beats = [tick_to_beat(t) for t in self.noteTicks[:len(notes)]] if self.noteTicks else list(range(1, len(notes) + 1))
        lyric_beats = [tick_to_beat(t) for t in self.lyricTicks[:len(lyrics)]] if self.lyricTicks else list(range(1, len(lyrics) + 1))
        chord_beats = [tick_to_beat(t) for t in self.chordTicks[:len(chords)]] if self.chordTicks else (
            [tick_to_beat(t * 480) for t in self.chordOffsets[:len(chords)]] if self.chordOffsets else list(range(1, len(chords) + 1))
        )
        
        # 總拍數 = 所有 token 位置的最大值；若為空小節且已有預建拍位（如 4/4 的 4 拍），保留既有拍數
        default_beats = len(self.beats) if (not notes and not lyrics and not chords and len(self.beats) > 1) else 1
        max_beat = max(note_beats + lyric_beats + chord_beats, default=default_beats)
        
        previous = {b.beat: b for b in self.beats}
        beats: list[ScoreBeat] = []
        
        for beat in range(1, max_beat + 1):
            # P0-1: 同拍多事件 — 收集所有落在這拍的 token (非只取第一個)，並確保索引不越界
            note_idxs = [i for i, b in enumerate(note_beats) if b == beat and i < len(notes)]
            lyric_idxs = [i for i, b in enumerate(lyric_beats) if b == beat and i < len(lyrics)]
            chord_idxs = [i for i, b in enumerate(chord_beats) if b == beat and i < len(chords)]
            
            note = " ".join(notes[i] for i in note_idxs) if note_idxs else ""
            lyric = " ".join(lyrics[i] for i in lyric_idxs) if lyric_idxs else ""
            chord = " ".join(chords[i] for i in chord_idxs) if chord_idxs else ""
            old = previous.get(beat)
            conf = min_confidence
            annotation = ""
            dur = duration_from_token(note.split(' ')[0]) if note else (old.duration if (old is not None and old.duration) else "quarter")
            if old is not None and old.note == note:
                conf = old.confidence
                annotation = old.annotation
            
            beats.append(
                ScoreBeat(
                    beat=beat,
                    note=note,
                    lyric=lyric,
                    chord=chord,
                    duration=dur,
                    confidence=conf,
                    annotation=annotation,
                )
            )
        self.beats = beats
        return beats

    def min_confidence(self) -> float:
        return min([b.confidence for b in self.beats], default=1.0)

    def to_dict(self) -> dict:
        d = {
            "number": self.number,
            "lineIndex": self.lineIndex,
            "linePosition": self.linePosition,
            "chordText": self.chordText,
            "chordOffsets": list(self.chordOffsets),
            "noteText": self.noteText,
            "lyricText": self.lyricText,
            "lyricText2": self.lyricText2,
            "lyricText3": self.lyricText3,
            "lyricText4": self.lyricText4,
            "lyricRows": int(self.lyricRows),
            "barline": bool(self.barline),
            "marks": str(self.marks or ""),
            "section": str(self.section or ""),
            "sourcePage": self.sourcePage,
            "beats": [b.to_dict() for b in self.beats],
            "melodyEvents": list(self.melodyEvents),
            "chordEvents": list(self.chordEvents),
            "lyricTracks": list(self.lyricTracks),
            "annotations": list(self.annotations),
            "eventModelVersion": int(self.eventModelVersion),
        }
        # 只輸出非空 tick 陣列，避免污染舊檔
        if self.chordTicks:
            d["chordTicks"] = list(self.chordTicks)
        if self.noteTicks:
            d["noteTicks"] = list(self.noteTicks)
        if self.lyricTicks:
            d["lyricTicks"] = list(self.lyricTicks)
        if self.lyricText2Ticks:
            d["lyricText2Ticks"] = list(self.lyricText2Ticks)
        if self.lyricText3Ticks:
            d["lyricText3Ticks"] = list(self.lyricText3Ticks)
        if self.lyricText4Ticks:
            d["lyricText4Ticks"] = list(self.lyricText4Ticks)
        # Phase 6D：事件覆蓋（非空才輸出，舊檔零污染，並完整保留 duration / tick 等覆寫屬性）
        if self.eventOverrides and isinstance(self.eventOverrides, dict):
            clean = {}
            for k, v in self.eventOverrides.items():
                if isinstance(v, dict):
                    entry = dict(v)
                    if "tick" in entry and entry["tick"] is not None:
                        try:
                            entry["tick"] = int(entry["tick"])
                        except (ValueError, TypeError):
                            entry["tick"] = 0
                    clean[str(k)] = entry
                else:
                    clean[str(k)] = {"tick": 0}
            d["eventOverrides"] = clean
        return d

    @staticmethod
    def from_dict(d: dict) -> "ScoreMeasure":
        raw_eo = d.get("eventOverrides")
        eo_dict = {}
        if isinstance(raw_eo, dict):
            for k, v in raw_eo.items():
                if isinstance(v, dict):
                    entry = dict(v)
                    if "tick" in entry and entry["tick"] is not None:
                        try:
                            entry["tick"] = int(entry["tick"])
                        except (ValueError, TypeError):
                            entry["tick"] = 0
                    eo_dict[str(k)] = entry
                else:
                    eo_dict[str(k)] = {"tick": 0}
        melody_ev = list(d.get("melodyEvents") or []) if isinstance(d.get("melodyEvents"), list) else []
        note_txt = str(d.get("noteText", "") or "")
        raw_emv = int(d.get("eventModelVersion", 0) or 0)
        if not melody_ev and note_txt.strip():
            raw_emv = 0
        m = ScoreMeasure(
            number=int(d.get("number", 1) or 1),
            lineIndex=int(d.get("lineIndex", 0) or 0),
            linePosition=int(d.get("linePosition", 1) or 1),
            chordText=str(d.get("chordText", "") or ""),
            chordOffsets=[int(x) for x in (d.get("chordOffsets") or []) if isinstance(x, (int, float, str)) and str(x).lstrip("-").isdigit()],
            chordTicks=[int(x) for x in (d.get("chordTicks") or []) if isinstance(x, (int, float, str)) and str(x).lstrip("-").isdigit()],
            noteText=note_txt,
            noteTicks=[int(x) for x in (d.get("noteTicks") or []) if isinstance(x, (int, float, str)) and str(x).lstrip("-").isdigit()],
            lyricText=str(d.get("lyricText", "") or ""),
            lyricTicks=[int(x) for x in (d.get("lyricTicks") or []) if isinstance(x, (int, float, str)) and str(x).lstrip("-").isdigit()],
            lyricText2=str(d.get("lyricText2", "") or ""),
            lyricText2Ticks=[int(x) for x in (d.get("lyricText2Ticks") or []) if isinstance(x, (int, float, str)) and str(x).lstrip("-").isdigit()],
            lyricText3=str(d.get("lyricText3", "") or ""),
            lyricText3Ticks=[int(x) for x in (d.get("lyricText3Ticks") or []) if isinstance(x, (int, float, str)) and str(x).lstrip("-").isdigit()],
            lyricText4=str(d.get("lyricText4", "") or ""),
            lyricText4Ticks=[int(x) for x in (d.get("lyricText4Ticks") or []) if isinstance(x, (int, float, str)) and str(x).lstrip("-").isdigit()],
            lyricRows=int(d.get("lyricRows", 1) or 1),
            barline=bool(d.get("barline", True)),
            marks=str(d.get("marks", "") or ""),
            section=str(d.get("section", "") or ""),
            beats=[ScoreBeat.from_dict(b) for b in (d.get("beats") or []) if isinstance(b, dict)],
            sourcePage=d.get("sourcePage"),
            eventOverrides=eo_dict,
            melodyEvents=melody_ev,
            chordEvents=list(d.get("chordEvents") or []) if isinstance(d.get("chordEvents"), list) else [],
            lyricTracks=list(d.get("lyricTracks") or []) if isinstance(d.get("lyricTracks"), list) else [],
            annotations=list(d.get("annotations") or []) if isinstance(d.get("annotations"), list) else [],
            eventModelVersion=raw_emv,
        )
        # 兼容：若無 chordTicks 但有 chordOffsets，自動轉換
        if not m.chordTicks and m.chordOffsets:
            m.chordTicks = [x * 480 for x in m.chordOffsets]
        if not m.beats:
            m.expand_beats()
        return m


@dataclass
class ScoreDocument:
    id: str = field(default_factory=lambda: new_id("doc"))
    title: str = "未命名樂譜"
    lyricist: str = ""
    composer: str = ""
    key: str = "C"
    timeSignature: str = "4/4"
    tempo: int = 90
    measures: list[ScoreMeasure] = field(default_factory=list)
    sections: list = field(default_factory=list)
    engineMode: str = "manual"  # tesseract-ocr / text-import / manual
    engineNote: str = ""
    sourceName: str = ""
    capo: int | None = None       # Capo 碼（文字層互補，指南 §1.1）
    sourceNote: str = ""          # 出處／附註（文字層互補）
    createdAt: str = field(default_factory=now_iso)
    updatedAt: str = field(default_factory=now_iso)

    def renumber(self) -> "ScoreDocument":
        """重新編號並依每行三小節重排 lineIndex / linePosition（規劃書 8.2）。

        同時依整句重新展開每個小節的拍位——這是規劃書「拍位在失焦／保存時重新
        展開」的落點：讓 beats 快取與 noteText／lyricText／chordText 保持同步。
        expand_beats 在音符未變時保留既有信心值與註記（lossless），變了才重新對齊，
        避免「磁碟上 stale beats 跟整句錯位」導致匯出 verse／拍數全錯。"""
        for i, m in enumerate(self.measures):
            m.number = i + 1
            m.lineIndex = i // MEASURES_PER_LINE
            m.linePosition = (i % MEASURES_PER_LINE) + 1
            m.expand_beats()
        return self

    def stats(self) -> dict:
        low = [
            {"measure": m.number, "confidence": round(m.min_confidence(), 3)}
            for m in self.measures
            if m.min_confidence() < 0.7
        ]
        return {
            "measures": len(self.measures),
            "lines": (len(self.measures) + MEASURES_PER_LINE - 1) // MEASURES_PER_LINE,
            "beats": sum(len(m.beats) for m in self.measures),
            "lowConfidence": low,
        }

    def to_dict(self) -> dict:
        d = {
            "id": self.id,
            "title": self.title,
            "lyricist": self.lyricist,
            "composer": self.composer,
            "key": self.key,
            "timeSignature": self.timeSignature,
            "tempo": self.tempo,
            "engineMode": self.engineMode,
            "engineNote": self.engineNote,
            "sourceName": self.sourceName,
            "capo": self.capo,
            "sourceNote": self.sourceNote,
            "createdAt": self.createdAt,
            "updatedAt": self.updatedAt,
            "measures": [m.to_dict() for m in self.measures],
            "stats": self.stats(),
        }
        if self.sections:
            d["sections"] = list(self.sections)
        return d

    @staticmethod
    def from_dict(d: dict) -> "ScoreDocument":
        doc = ScoreDocument(
            id=str(d.get("id") or new_id("doc")),
            title=str(d.get("title") or "未命名樂譜"),
            lyricist=str(d.get("lyricist", "") or ""),
            composer=str(d.get("composer", "") or ""),
            key=str(d.get("key") or "C"),
            timeSignature=str(d.get("timeSignature") or "4/4"),
            tempo=int(d.get("tempo", 90) or 90),
            engineMode=str(d.get("engineMode", "manual") or "manual"),
            engineNote=str(d.get("engineNote", "") or ""),
            sourceName=str(d.get("sourceName", "") or ""),
            capo=(d.get("capo") if isinstance(d.get("capo"), int) else None),
            sourceNote=str(d.get("sourceNote", "") or ""),
            createdAt=str(d.get("createdAt") or now_iso()),
            updatedAt=str(d.get("updatedAt") or now_iso()),
            measures=[ScoreMeasure.from_dict(m) for m in d.get("measures", []) or []],
            sections=list(d.get("sections") or []) if isinstance(d.get("sections"), list) else [],
        )
        return doc.renumber()


def blank_document(title: str = "未命名樂譜", measures: int = 6) -> ScoreDocument:
    doc = ScoreDocument(title=title)
    doc.measures = [ScoreMeasure(number=i + 1) for i in range(max(1, measures))]
    return doc.renumber()


# =============================================================================
# SolaFlow: 單一文字流編輯器資料模型 (Phase 7+)
# 設計目標：與既有 ScoreDocument 並存、雙向同步、向後相容
# =============================================================================

FLOW_VERSION = 1
TICKS_PER_BEAT = 480
BEAT_WIDTH = 48          # 1 拍 = 48px (視覺單位)
SNAP_TICKS = 120         # 1/16 音符吸附 (120 ticks = 6px)


@dataclass
class SolaFlowEvent:
    """扁平化事件：和弦、音符、歌詞、小節線統一結構"""
    uid: str                    # 穩定 ID：fnv36(type|tick|content|#seq)
    type: str                   # 'chord' | 'note' | 'lyric' | 'barline'
    content: str                # 和弦名 / 簡譜 token / 歌詞字 / '|'
    tick: int                   # 絕對 tick (0 起算，480 = 1 quarter note)
    # 視覺輔助欄位 (由 layout 產出，不持久化)
    renderX: int = 0            # px, 相對容器左緣
    renderWidth: int = 0        # px
    lineIndex: int = 0          # 換行後所在行

    def to_dict(self) -> dict:
        return {
            "uid": self.uid,
            "type": self.type,
            "content": self.content,
            "tick": self.tick,
        }

    @staticmethod
    def from_dict(d: dict) -> "SolaFlowEvent":
        return SolaFlowEvent(
            uid=str(d.get("uid", "")),
            type=str(d.get("type", "note")),
            content=str(d.get("content", "")),
            tick=int(d.get("tick", 0) or 0),
        )


@dataclass
class SolaFlowDoc:
    """單一文字流文件：扁平事件陣列 + 小節邊界"""
    flowVersion: int = FLOW_VERSION
    timeSignature: str = "4/4"
    ticksPerBeat: int = TICKS_PER_BEAT
    events: list[SolaFlowEvent] = field(default_factory=list)   # 已按 tick 排序
    measureBounds: list[int] = field(default_factory=list)      # 每小節起始 tick，含第 0 小節 = 0
    # Legacy 同步欄位 (選填，供舊匯出器/編輯器)
    legacy: "ScoreDocument | None" = field(default=None, repr=False)

    def to_dict(self) -> dict:
        return {
            "flowVersion": self.flowVersion,
            "timeSignature": self.timeSignature,
            "ticksPerBeat": self.ticksPerBeat,
            "events": [e.to_dict() for e in self.events],
            "measureBounds": list(self.measureBounds),
        }

    @staticmethod
    def from_dict(d: dict) -> "SolaFlowDoc":
        return SolaFlowDoc(
            flowVersion=int(d.get("flowVersion", FLOW_VERSION) or FLOW_VERSION),
            timeSignature=str(d.get("timeSignature", "4/4") or "4/4"),
            ticksPerBeat=int(d.get("ticksPerBeat", TICKS_PER_BEAT) or TICKS_PER_BEAT),
            events=[SolaFlowEvent.from_dict(e) for e in d.get("events", []) or []],
            measureBounds=[int(x) for x in d.get("measureBounds", []) or []],
        )

    def ensure_measure_bounds(self, beats_per_measure: int | None = None) -> list[int]:
        """確保 measureBounds 存在且正確。若無則依 timeSignature 推算。"""
        if self.measureBounds and self.measureBounds[0] == 0:
            return self.measureBounds
        if beats_per_measure is None:
            beats_per_measure = parse_time_signature_to_beats(self.timeSignature)
        measure_ticks = beats_per_measure * self.ticksPerBeat
        # 找出最大 tick
        max_tick = max((e.tick for e in self.events), default=0)
        # 也要考慮小節線事件
        for e in self.events:
            if e.type == "barline":
                max_tick = max(max_tick, e.tick)
        num_measures = max(1, (max_tick // measure_ticks) + 2)
        self.measureBounds = [i * measure_ticks for i in range(num_measures + 1)]
        return self.measureBounds


# ---- FNV-1a 32-bit → base36 (決定性 UID) ----
def _fnv36(s: str) -> str:
    h = 0x811c9dc5
    for ch in s.encode("utf-8"):
        h ^= ch
        h = (h * 0x01000193) & 0xffffffff
    # base36
    chars = "0123456789abcdefghijklmnopqrstuvwxyz"
    if h == 0:
        return "0"
    out = []
    while h:
        h, r = divmod(h, 36)
        out.append(chars[r])
    return "".join(reversed(out))


def solaflow_generate_uid(ev_type: str, tick: int, content: str, seq: int = 0) -> str:
    """依事件類型、tick、內容產生穩定 UID；相同內容同 tick 以 seq 区分"""
    base = f"{ev_type}|{tick}|{content}"
    if seq:
        base += f"|#{seq}"
    return _fnv36(base)


def solaflow_assign_uids(events: list[SolaFlowEvent]) -> None:
    """為事件陣列分配/修正 UID (就地修改)。依 (type, tick, content) 分組計數。"""
    from collections import Counter
    key_counts = Counter((e.type, e.tick, e.content) for e in events)
    seen: dict[tuple, int] = {}
    for e in events:
        key = (e.type, e.tick, e.content)
        seen[key] = seen.get(key, 0) + 1
        seq = seen[key] if key_counts[key] > 1 else 0
        if not e.uid or e.uid == "0":
            e.uid = solaflow_generate_uid(e.type, e.tick, e.content, seq)


# ---- Legacy ↔ Flow 雙向轉換 ----

def parse_time_signature_to_beats(sig: str) -> int:
    """'4/4' -> 4, '3/4' -> 3, '6/8' -> 3 (視為 3 拍)"""
    import re
    m = re.match(r"^\s*(\d{1,2})\s*/\s*(\d{1,2})\s*$", sig or "")
    if not m:
        return 4
    beats, beat_type = int(m.group(1)), int(m.group(2))
    if beat_type == 8:
        return beats // 2  # 6/8 -> 3, 9/8 -> 4 (近似)
    return max(1, beats)


def score_document_to_flow(doc: ScoreDocument) -> SolaFlowDoc:
    """ScoreDocument → SolaFlowDoc (單向遷移，啟動 Flow 編輯器時呼叫)"""
    flow = SolaFlowDoc(
        timeSignature=doc.timeSignature,
        ticksPerBeat=TICKS_PER_BEAT,
        legacy=doc,
    )
    events: list[SolaFlowEvent] = []
    measure_bounds = [0]
    current_tick = 0

    for m in doc.measures:
        beats_per_measure = parse_time_signature_to_beats(m.timeSignature if hasattr(m, 'timeSignature') and m.timeSignature else doc.timeSignature)
        measure_ticks = beats_per_measure * TICKS_PER_BEAT

        # 和弦
        chords = split_chords(m.chordText)
        chord_ticks = m.chordTicks if m.chordTicks else ([t * 480 for t in m.chordOffsets] if m.chordOffsets else list(range(0, len(chords) * 480, 480)))
        for i, (chord, tick) in enumerate(zip(chords, chord_ticks)):
            abs_tick = current_tick + min(tick, measure_ticks - 1)
            events.append(SolaFlowEvent(
                uid="", type="chord", content=chord, tick=abs_tick
            ))

        # 音符
        notes = split_notes(m.noteText)
        note_ticks = m.noteTicks if m.noteTicks else list(range(0, len(notes) * 480, 480))
        for i, (note, tick) in enumerate(zip(notes, note_ticks)):
            abs_tick = current_tick + min(tick, measure_ticks - 1)
            events.append(SolaFlowEvent(
                uid="", type="note", content=note, tick=abs_tick
            ))

        # 歌詞 (最多 4 行)
        for verse_idx, (field, ticks_field) in enumerate([
            ("lyricText", "lyricTicks"),
            ("lyricText2", "lyricText2Ticks"),
            ("lyricText3", "lyricText3Ticks"),
            ("lyricText4", "lyricText4Ticks"),
        ]):
            raw = getattr(m, field, "") or ""
            if not raw:
                continue
            words = split_lyrics(raw)
            ticks = getattr(m, ticks_field, []) or list(range(0, len(words) * 480, 480))
            for j, (word, tick) in enumerate(zip(words, ticks)):
                abs_tick = current_tick + min(tick, measure_ticks - 1)
                events.append(SolaFlowEvent(
                    uid="", type="lyric", content=word, tick=abs_tick
                ))

        # 小節線
        if m.barline:
            events.append(SolaFlowEvent(
                uid="", type="barline", content="|", tick=current_tick + measure_ticks
            ))

        current_tick += measure_ticks
        measure_bounds.append(current_tick)

    # 排序並分配 UID
    events.sort(key=lambda e: (e.tick, {"chord": 0, "note": 1, "lyric": 2, "barline": 3}.get(e.type, 9)))
    solaflow_assign_uids(events)
    flow.events = events
    flow.measureBounds = measure_bounds
    return flow


def flow_to_score_document(flow: SolaFlowDoc) -> ScoreDocument:
    """SolaFlowDoc → ScoreDocument (儲存/匯出時呼叫)"""
    # 重建 measures
    beats_per_measure = parse_time_signature_to_beats(flow.timeSignature)
    measure_ticks = beats_per_measure * flow.ticksPerBeat

    # 依 measureBounds 分組事件
    measures_dict: dict[int, list[SolaFlowEvent]] = {}
    for e in flow.events:
        if e.type == "barline":
            continue  # 小節線由 measureBounds 決定
        mi = 0
        for i, bound in enumerate(flow.measureBounds):
            if e.tick < bound:
                mi = max(0, i - 1)
                break
        else:
            mi = len(flow.measureBounds) - 2
        measures_dict.setdefault(mi, []).append(e)

    measures: list[ScoreMeasure] = []
    for mi in range(len(flow.measureBounds) - 1):
        m_events = measures_dict.get(mi, [])
        m_tick_start = flow.measureBounds[mi]

        chords = [e for e in m_events if e.type == "chord"]
        notes = [e for e in m_events if e.type == "note"]
        lyrics = [e for e in m_events if e.type == "lyric"]

        m = ScoreMeasure(
            number=mi + 1,
            lineIndex=mi // MEASURES_PER_LINE,
            linePosition=(mi % MEASURES_PER_LINE) + 1,
            chordText=" ".join(e.content for e in chords),
            chordTicks=[e.tick - m_tick_start for e in chords],
            noteText=" ".join(e.content for e in notes),
            noteTicks=[e.tick - m_tick_start for e in notes],
            lyricText="".join(e.content for e in lyrics),  # 中文逐字
            lyricTicks=[e.tick - m_tick_start for e in lyrics],
            barline=(mi < len(flow.measureBounds) - 2),  # 最後一個小節可選
        )
        m.expand_beats()
        measures.append(m)

    doc = ScoreDocument(
        id=flow.legacy.id if flow.legacy else new_id("doc"),
        title=flow.legacy.title if flow.legacy else "未命名樂譜",
        lyricist=flow.legacy.lyricist if flow.legacy else "",
        composer=flow.legacy.composer if flow.legacy else "",
        key=flow.legacy.key if flow.legacy else "C",
        timeSignature=flow.timeSignature,
        tempo=flow.legacy.tempo if flow.legacy else 90,
        measures=measures,
        engineMode=flow.legacy.engineMode if flow.legacy else "manual",
        engineNote=flow.legacy.engineNote if flow.legacy else "",
        sourceName=flow.legacy.sourceName if flow.legacy else "",
        capo=flow.legacy.capo if flow.legacy else None,
        sourceNote=flow.legacy.sourceNote if flow.legacy else "",
        createdAt=flow.legacy.createdAt if flow.legacy else now_iso(),
        updatedAt=now_iso(),
    )
    return doc.renumber()
