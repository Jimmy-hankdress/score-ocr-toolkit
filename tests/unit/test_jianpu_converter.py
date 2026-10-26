"""
單元測試：簡譜轉換核心邏輯
測試 pitch_to_jianpu、symbols_to_jianpu_text、parse_pitch 等核心函數
"""

import pytest

from src.ocr.jianpu_converter import (
    DURATION_BEATS,
    KEY_OFFSETS,
    PITCH_SEMITONES,
    SEMITONE_TO_JIANPU,
    parse_pitch,
    pitch_to_jianpu,
    symbol_to_jianpu_notation,
    symbols_to_jianpu_text,
)
from src.ocr.recognizer import Symbol


class TestParsePitch:
    """音高解析測試"""

    @pytest.mark.parametrize("pitch,expected", [
        ("C4", ("C", "", 4)),
        ("C#4", ("C", "#", 4)),
        ("Bb3", ("B", "b", 3)),
        ("F##5", ("F", "##", 5)),
        ("Dbb2", ("D", "bb", 2)),
        ("Gbb4", ("G", "bb", 4)),
        ("E#5", ("E", "#", 5)),
        ("Fb3", ("F", "b", 3)),
        ("c4", ("C", "", 4)),  # 小寫
        ("Db4", ("D", "b", 4)),
        ("G#5", ("G", "#", 5)),
    ])
    def test_valid_pitches(self, pitch, expected):
        assert parse_pitch(pitch) == expected

    @pytest.mark.parametrize("pitch", [
        "H4",      # 無效音名
        "C",       # 無八度 (應該預設為 4)
        "C44",     # 雙位數八度
        "C##4",    # 這是有效的 (雙升)
        "C###4",   # 三重升 - 無效
        "Cbbb4",   # 三重降 - 無效
        "",        # 空字串
        None,      # None
    ])
    def test_invalid_pitches(self, pitch):
        if pitch in ("C##4", "C", "C4"):  # 這些其實是有效的
            pass
        result = parse_pitch(pitch)
        if pitch in ("C", "C##4"):
            assert result is not None
        else:
            assert result is None, f"Expected None for '{pitch}', got {result}"


class TestPitchToJianpu:
    """音高轉簡譜測試"""

    @pytest.mark.parametrize("pitch,key,expected", [
        # 基本音級 (1=C)
        ("C4", "C", "1"),
        ("D4", "C", "2"),
        ("E4", "C", "3"),
        ("F4", "C", "4"),
        ("G4", "C", "5"),
        ("A4", "C", "6"),
        ("B4", "C", "7"),

        # 升降記號 (異名同音：Db4 = C#4 = #1, Gb4 = F#4 = #4, Ab4 = G#4 = #5)
        ("C#4", "C", "#1"),
        ("Db4", "C", "#1"),
        ("D#4", "C", "b3"),
        ("Eb4", "C", "b3"),
        ("F#4", "C", "#4"),
        ("Gb4", "C", "#4"),
        ("G#4", "C", "#5"),
        ("Ab4", "C", "#5"),
        ("A#4", "C", "b7"),
        ("Bb4", "C", "b7"),

        # 高八度 (點在上)
        ("C5", "C", "1\u0307"),
        ("D5", "C", "2\u0307"),
        ("G5", "C", "5\u0307"),

        # 低八度 (點在下)
        ("C3", "C", "1\u0323"),
        ("D3", "C", "2\u0323"),
        ("G3", "C", "5\u0323"),

        # 轉調測試 (1=G)
        ("G4", "G", "1"),
        ("A4", "G", "2"),
        ("B4", "G", "3"),
        ("C5", "G", "4"),
        ("D5", "G", "5"),
        ("E5", "G", "6"),
        ("F#5", "G", "7"),

        # 轉調測試 (1=F)
        ("F4", "F", "1"),
        ("G4", "F", "2"),
        ("A4", "F", "3"),
        ("Bb4", "F", "4"),
        ("C5", "F", "5"),
        ("D5", "F", "6"),
        ("E5", "F", "7"),

        # 休止符
        (None, "C", "0"),
        ("", "C", "0"),
    ])
    def test_pitch_conversion(self, pitch, key, expected):
        result = pitch_to_jianpu(pitch, key=key)
        assert result == expected, f"pitch_to_jianpu('{pitch}', key='{key}') = '{result}', expected '{expected}'"


class TestSymbolToJianpuNotation:
    """單一符號轉簡譜標記測試 (含時值)"""

    @pytest.mark.parametrize("sym_dict,key,expected", [
        # 基本四分音符
        ({"type": "note", "pitch": "C4", "duration": "quarter"}, "C", "1"),
        ({"type": "note", "pitch": "D4", "duration": "quarter"}, "C", "2"),

        # 時值符號
        ({"type": "note", "pitch": "C4", "duration": "whole"}, "C", "1 - - -"),
        ({"type": "note", "pitch": "C4", "duration": "half"}, "C", "1 -"),
        ({"type": "note", "pitch": "C4", "duration": "eighth"}, "C", "1_"),
        ({"type": "note", "pitch": "C4", "duration": "16th"}, "C", "1="),
        ({"type": "note", "pitch": "C4", "duration": "32nd"}, "C", "1≡"),

        # 休止符
        ({"type": "rest", "pitch": None, "duration": "quarter"}, "C", "0"),
        ({"type": "rest", "pitch": None, "duration": "half"}, "C", "0 -"),
    ])
    def test_notation_with_duration(self, sym_dict, key, expected):
        result = symbol_to_jianpu_notation(sym_dict, key=key)
        assert result == expected


class TestSymbolsToJianpuText:
    """完整簡譜文字生成測試"""

    def test_simple_scale(self):
        """基本音階測試"""
        symbols = [
            Symbol(id="1", type="note", pitch="C4", duration="quarter", x=0, y=0, width=10, height=10, confidence=1.0),
            Symbol(id="2", type="note", pitch="D4", duration="quarter", x=10, y=0, width=10, height=10, confidence=1.0),
            Symbol(id="3", type="note", pitch="E4", duration="quarter", x=20, y=0, width=10, height=10, confidence=1.0),
            Symbol(id="4", type="note", pitch="F4", duration="quarter", x=30, y=0, width=10, height=10, confidence=1.0),
            Symbol(id="5", type="note", pitch="G4", duration="quarter", x=40, y=0, width=10, height=10, confidence=1.0),
            Symbol(id="6", type="note", pitch="A4", duration="quarter", x=50, y=0, width=10, height=10, confidence=1.0),
            Symbol(id="7", type="note", pitch="B4", duration="quarter", x=60, y=0, width=10, height=10, confidence=1.0),
            Symbol(id="8", type="note", pitch="C5", duration="quarter", x=70, y=0, width=10, height=10, confidence=1.0),
        ]
        result = symbols_to_jianpu_text(symbols, title="Test Scale", key="C", meter="4/4")
        assert "《Test Scale》" in result
        assert "1=C" in result
        assert "4/4" in result
        assert "1  2  3  4" in result
        assert "5  6  7  1" in result
        assert "||" in result  # 結尾終止線

    def test_multiple_measures(self):
        """多小節測試 (4/4 拍，8 個四分音符 = 2 小節)"""
        symbols = [
            Symbol(id=str(i), type="note", pitch="C4", duration="quarter", x=i*10, y=0, width=10, height=10, confidence=1.0)
            for i in range(8)
        ]
        result = symbols_to_jianpu_text(symbols, key="C", meter="4/4")
        # 應該有兩個小節，用 | 分隔
        assert result.count("|") >= 3  # 開頭、中間、結尾

    def test_3_4_meter(self):
        """3/4 拍測試"""
        symbols = [
            Symbol(id=str(i), type="note", pitch="C4", duration="quarter", x=i*10, y=0, width=10, height=10, confidence=1.0)
            for i in range(6)  # 6 個四分音符 = 2 小節
        ]
        result = symbols_to_jianpu_text(symbols, key="C", meter="3/4")
        assert "3/4" in result

    def test_transposition(self):
        """轉調測試"""
        symbols = [
            Symbol(id="1", type="note", pitch="C4", duration="quarter", x=0, y=0, width=10, height=10, confidence=1.0),
            Symbol(id="2", type="note", pitch="G4", duration="quarter", x=10, y=0, width=10, height=10, confidence=1.0),
        ]
        # 1=C 時：C4=1, G4=5
        result_c = symbols_to_jianpu_text(symbols, key="C", meter="4/4")
        assert "1" in result_c and "5" in result_c

        # 1=G 時：C4=4, G4=1
        result_g = symbols_to_jianpu_text(symbols, key="G", meter="4/4")
        assert "4" in result_g and "1" in result_g


class TestConstants:
    """常數表完整性測試"""

    def test_pitch_semitones_complete(self):
        """PITCH_SEMITONES 應包含所有基本音名及其異名同音"""
        required = ["C", "C#", "Db", "D", "D#", "Eb", "E", "F", "F#", "Gb", "G", "G#", "Ab", "A", "A#", "Bb", "B"]
        for note in required:
            assert note in PITCH_SEMITONES, f"Missing {note} in PITCH_SEMITONES"

        # 雙升/雙降
        assert "C##" in PITCH_SEMITONES
        assert "Dbb" in PITCH_SEMITONES
        assert "F##" in PITCH_SEMITONES
        assert "Gbb" in PITCH_SEMITONES

    def test_key_offsets_complete(self):
        """KEY_OFFSETS 應包含常用調號"""
        required_keys = ["C", "C#", "Db", "D", "D#", "Eb", "E", "F", "F#", "Gb", "G", "G#", "Ab", "A", "A#", "Bb", "B"]
        for key in required_keys:
            assert key in KEY_OFFSETS or f"1={key}" in KEY_OFFSETS, f"Missing key {key}"

    def test_semitone_to_jianpu_complete(self):
        """SEMITONE_TO_JIANPU 應覆蓋 0-11 所有半音"""
        for i in range(12):
            assert i in SEMITONE_TO_JIANPU, f"Missing semitone {i}"
            num, acc = SEMITONE_TO_JIANPU[i]
            assert num in ["1", "2", "3", "4", "5", "6", "7"]
            assert acc in ["", "#", "b"]

    def test_duration_beats_complete(self):
        """DURATION_BEATS 應包含所有標準時值"""
        required = ["whole", "half", "quarter", "eighth", "16th", "32nd"]
        for dur in required:
            assert dur in DURATION_BEATS
            assert DURATION_BEATS[dur] > 0
