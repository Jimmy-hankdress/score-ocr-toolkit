"""
單元測試：MusicXML 建構器
測試 symbols_to_musicxml、音高解析、小節分割等功能
"""

import pytest

from src.ocr.musicxml_builder import (
    DURATION_MAP,
    MEASURE_DIVISIONS,
    _parse_pitch_for_musicxml,
    symbols_to_musicxml,
)


class TestParsePitchForMusicXML:
    """MusicXML 專用音高解析測試"""

    @pytest.mark.parametrize("pitch,expected_step,expected_alter,expected_octave", [
        ("C4", "C", 0, 4),
        ("C#4", "C", 1, 4),
        ("Db4", "D", -1, 4),
        ("F##5", "F", 2, 5),
        ("Dbb2", "D", -2, 2),
        ("Gbb4", "G", -2, 4),
        ("E#5", "E", 1, 5),
        ("Fb3", "F", -1, 3),
        ("B#4", "B", 1, 4),
        ("Cb4", "C", -1, 4),
    ])
    def test_valid_pitches(self, pitch, expected_step, expected_alter, expected_octave):
        step, alter, octave = _parse_pitch_for_musicxml(pitch)
        assert step == expected_step
        assert alter == expected_alter
        assert octave == expected_octave

    def test_none_pitch_returns_default(self):
        step, alter, octave = _parse_pitch_for_musicxml(None)
        assert step == "C"
        assert alter == 0
        assert octave == 4

    def test_empty_string_returns_default(self):
        step, alter, octave = _parse_pitch_for_musicxml("")
        assert step == "C"
        assert alter == 0
        assert octave == 4

    def test_invalid_pitch_returns_default_with_warning(self, caplog):
        step, alter, octave = _parse_pitch_for_musicxml("INVALID")
        assert step == "C"
        assert alter == 0
        assert octave == 4
        assert "無法解析音高" in caplog.text


class TestDurationMap:
    """時值對照表測試"""

    def test_duration_map_values(self):
        assert DURATION_MAP["whole"] == 32
        assert DURATION_MAP["half"] == 16
        assert DURATION_MAP["quarter"] == 8
        assert DURATION_MAP["eighth"] == 4
        assert DURATION_MAP["16th"] == 2
        assert DURATION_MAP["32nd"] == 1

    def test_measure_divisions(self):
        assert MEASURE_DIVISIONS == 32  # 4 quarter notes per measure


class TestSymbolsToMusicXML:
    """完整 MusicXML 生成測試"""

    def create_symbol(self, pitch, duration="quarter", sym_type="note", sym_id=None):
        """建立測試用符號字典"""
        return {
            "id": sym_id or f"sym-{pitch}",
            "type": sym_type,
            "pitch": pitch,
            "duration": duration,
            "x": 0,
            "y": 0,
            "width": 20,
            "height": 18,
            "confidence": 1.0,
        }

    def test_single_note(self):
        """單一音符生成"""
        symbols = [self.create_symbol("C4")]
        xml = symbols_to_musicxml(symbols, title="Test")

        assert '<?xml version="1.0" ?>' in xml
        assert "<work-title>Test</work-title>" in xml
        assert "<part-name>Music</part-name>" in xml
        assert "<step>C</step>" in xml
        assert "<octave>4</octave>" in xml
        assert "<alter>0</alter>" not in xml  # 不應有 alter=0
        assert "<duration>8</duration>" in xml
        assert "<type>quarter</type>" in xml

    def test_sharp_note(self):
        """升號音符"""
        symbols = [self.create_symbol("C#4")]
        xml = symbols_to_musicxml(symbols)
        assert "<step>C</step>" in xml
        assert "<alter>1</alter>" in xml
        assert "<octave>4</octave>" in xml

    def test_flat_note(self):
        """降號音符"""
        symbols = [self.create_symbol("Bb3")]
        xml = symbols_to_musicxml(symbols)
        assert "<step>B</step>" in xml
        assert "<alter>-1</alter>" in xml
        assert "<octave>3</octave>" in xml

    def test_double_sharp_note(self):
        """雙升號音符"""
        symbols = [self.create_symbol("F##5")]
        xml = symbols_to_musicxml(symbols)
        assert "<step>F</step>" in xml
        assert "<alter>2</alter>" in xml
        assert "<octave>5</octave>" in xml

    def test_double_flat_note(self):
        """雙降號音符"""
        symbols = [self.create_symbol("Dbb2")]
        xml = symbols_to_musicxml(symbols)
        assert "<step>D</step>" in xml
        assert "<alter>-2</alter>" in xml
        assert "<octave>2</octave>" in xml

    def test_rest_note(self):
        """休止符"""
        symbols = [self.create_symbol(None, sym_type="rest")]
        xml = symbols_to_musicxml(symbols)
        assert "<rest/>" in xml
        assert "<pitch>" not in xml  # 休止符不應有 pitch

    def test_multiple_notes_same_measure(self):
        """同一小節多音符"""
        symbols = [
            self.create_symbol("C4", sym_id="1"),
            self.create_symbol("D4", sym_id="2"),
            self.create_symbol("E4", sym_id="3"),
            self.create_symbol("F4", sym_id="4"),
        ]
        xml = symbols_to_musicxml(symbols)
        # 4 個四分音符 = 1 小節
        assert xml.count("<measure number=\"1\">") == 1
        assert xml.count("<measure number=\"2\">") == 0

    def test_multiple_measures(self):
        """跨小節音符 (5 個四分音符 = 1 小節 + 1 拍)"""
        symbols = [
            self.create_symbol("C4", sym_id="1"),
            self.create_symbol("D4", sym_id="2"),
            self.create_symbol("E4", sym_id="3"),
            self.create_symbol("F4", sym_id="4"),
            self.create_symbol("G4", sym_id="5"),
        ]
        xml = symbols_to_musicxml(symbols)
        assert xml.count("<measure number=\"1\">") == 1
        assert xml.count("<measure number=\"2\">") == 1

    def test_chord_notes(self):
        """和弦音符 (同時發聲)"""
        symbols = [
            self.create_symbol("C4", sym_id="1"),
            self.create_symbol("E4", sym_type="chord", sym_id="2"),
            self.create_symbol("G4", sym_type="chord", sym_id="3"),
        ]
        xml = symbols_to_musicxml(symbols)
        # 第一個音符無 chord 標記，後兩個應有
        assert xml.count("<chord/>") == 2

    def test_custom_key_signature(self):
        """自訂調號"""
        symbols = [self.create_symbol("C4")]
        xml = symbols_to_musicxml(symbols, key_fifths=1)  # G major / E minor
        assert "<fifths>1</fifths>" in xml

    def test_custom_time_signature(self):
        """自訂拍號"""
        symbols = [self.create_symbol("C4")]
        xml = symbols_to_musicxml(symbols, time_beats=3, time_beat_type=4)  # 3/4
        assert "<beats>3</beats>" in xml
        assert "<beat-type>4</beat-type>" in xml

    def test_custom_clef(self):
        """自訂譜號"""
        symbols = [self.create_symbol("C4")]
        xml = symbols_to_musicxml(symbols, clef_sign="F", clef_line=4)  # Bass clef
        assert "<sign>F</sign>" in xml
        assert "<line>4</line>" in xml

    def test_xml_structure_validity(self):
        """XML 結構基本有效性"""
        symbols = [self.create_symbol("C4")]
        xml = symbols_to_musicxml(symbols)

        # 必要元素檢查
        assert "<score-partwise" in xml
        assert 'version="4.0"' in xml
        assert "<part-list>" in xml
        assert "<score-part id=\"P1\">" in xml
        assert "<part id=\"P1\">" in xml
        assert "<measure number=\"1\">" in xml
        assert "<attributes>" in xml
        assert "<divisions>8</divisions>" in xml
        assert "<clef>" in xml
        assert "<sign>G</sign>" in xml
        assert "<line>2</line>" in xml

    def test_duration_values(self):
        """各時值對應正確的 duration 數值 (divisions=8)"""
        test_cases = [
            ("whole", "32"),
            ("half", "16"),
            ("quarter", "8"),
            ("eighth", "4"),
            ("16th", "2"),
            ("32nd", "1"),
        ]
        for dur_name, expected_dur in test_cases:
            symbols = [self.create_symbol("C4", duration=dur_name)]
            xml = symbols_to_musicxml(symbols)
            assert f"<duration>{expected_dur}</duration>" in xml, f"Duration {dur_name} failed"


class TestEdgeCases:
    """邊界情況測試"""

    def test_empty_symbols_list(self):
        """空符號列表"""
        xml = symbols_to_musicxml([])
        assert "<measure number=\"1\">" in xml
        # 應該只有空小節

    def test_dict_and_dataclass_compatibility(self):
        """dict 和 dataclass 相容性"""
        from src.ocr.recognizer import Symbol
        symbols_dict = [{"id": "1", "type": "note", "pitch": "C4", "duration": "quarter", "x": 0, "y": 0, "width": 20, "height": 18, "confidence": 1.0}]
        symbols_dc = [Symbol(id="1", type="note", pitch="C4", duration="quarter", x=0, y=0, width=20, height=18, confidence=1.0)]

        xml_dict = symbols_to_musicxml(symbols_dict)
        xml_dc = symbols_to_musicxml(symbols_dc)
        # 兩者產生的 XML 應相同 (除了可能的屬性順序)
        assert "<step>C</step>" in xml_dict
        assert "<step>C</step>" in xml_dc
