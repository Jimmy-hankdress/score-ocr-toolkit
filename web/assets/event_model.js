/* ============================================================
 * Phase 1.5 — Event Model 隔離層（純資料層，不參與畫面渲染）
 *
 * 設計原則：
 *   1. 只有 Legacy → Adapter → Events 單向路徑。
 *      本模組永遠只讀 Legacy doc，絕不寫回、絕不修改輸入。
 *   2. 事件之間不強制對應：
 *      - LyricEvent 沒有 noteId 欄位，數量可以少於 NoteEvent
 *      - ChordEvent 不依附 NoteEvent，只有 start（無 duration）也合法
 *      - 缺拍不自動補 event（不補歌詞、不補音符、不強迫每拍一個 event）
 *   3. 序列化結果不含 undefined（所有欄位皆有明確默認值）。
 *
 * 用法（Node 測試）：
 *   const EventModel = require('./event_model.js');
 *   const events = EventModel.legacyToEvents(doc);
 * 未來瀏覽器端（Phase 2）可直接 <script src> 載入：window.EventModel
 * ============================================================ */
(function (root, factory) {
  'use strict';
  var api = factory();
  if (typeof module !== 'undefined' && module.exports) module.exports = api;
  if (root) root.EventModel = api;
})(typeof self !== 'undefined' ? self : (typeof globalThis !== 'undefined' ? globalThis : this), function () {
  'use strict';

  var DOT_ABOVE = '\u0307';  // 高八度點
  var DOT_BELOW = '\u0323';  // 低八度點
  var seq = 0;
  function nextId(prefix) { seq += 1; return prefix + '-' + String(seq).padStart(3, '0'); }

  /* ---- NoteEvent ----
     pitch: 簡譜數字字串（"1".."7"）；休止時 null
     octave: 點號淨偏移（上點-下點）；無點時 null
     duration: 拍數（四分音符 = 1） */
  function noteEvent(spec) {
    spec = spec || {};
    return {
      id: spec.id != null ? spec.id : nextId('ev-note'),
      type: 'note',
      start: spec.start != null ? spec.start : 0,
      duration: spec.duration != null ? spec.duration : 1,
      pitch: spec.pitch != null ? spec.pitch : null,
      accidental: spec.accidental != null ? spec.accidental : null,
      octave: spec.octave != null ? spec.octave : null,
      dotted: spec.dotted != null ? spec.dotted : false,
      tieStart: spec.tieStart != null ? spec.tieStart : false,
      tieEnd: spec.tieEnd != null ? spec.tieEnd : false,
      rest: spec.rest != null ? spec.rest : false
    };
  }

  /* ---- LyricEvent ----
     刻意不設 noteId：歌詞與音符不強制一一对應。
     缺拍 → 不建 event，絕不補假歌詞。 */
  function lyricEvent(spec) {
    spec = spec || {};
    return {
      id: spec.id != null ? spec.id : nextId('ev-lyric'),
      type: 'lyric',
      start: spec.start != null ? spec.start : 0,
      duration: spec.duration != null ? spec.duration : 1,
      text: spec.text != null ? spec.text : ''
    };
  }

  /* ---- ChordEvent ----
     刻意不設 noteId：和弦不依附音符。
     duration = null 代表「位置性」：只落某拍，時值未定（可持有至小節尾）。 */
  function chordEvent(spec) {
    spec = spec || {};
    return {
      id: spec.id != null ? spec.id : nextId('ev-chord'),
      type: 'chord',
      start: spec.start != null ? spec.start : 0,
      duration: spec.duration != null ? spec.duration : null,
      text: spec.text != null ? spec.text : ''
    };
  }

  /* ---- Measure Event Container ----
     名稱依 Phase 1.5 規範：melodyEvents / lyricEvents / chordEvents
     （既有 Legacy 結構 {number, chordText, noteText, lyricText} 完全不動） */
  function measure(spec) {
    spec = spec || {};
    return {
      measure: spec.measure != null ? spec.measure : 0,
      melodyEvents: spec.melodyEvents || [],
      lyricEvents: spec.lyricEvents || [],
      chordEvents: spec.chordEvents || []
    };
  }

  /* ---- Legacy → Event Adapter（單向，純讀取）----
   規則（文檔化假設）：
   - 音符：noteText 以空白切分；第 i 個 token 落第 i 拍（start=i），
     預設四分音符 duration=1；"0" = 休止（rest=true, pitch=null）；
     高八度點/低八度點 記入 octave 偏移，不污染 pitch。
   - 歌詞：lyricText 以空白切分；第 j 個音节 位置性對齊第 j 個音符
     （start=j），時長預設 1。缺拍不建 LyricEvent。
   - 和弦：chordText 以空白切分；第 k 個和弦落第 k 拍（start=k），
     duration=null（位置性）。Legacy 無法表達「和弦落非 1..k 拍」或
     「和弦時值」→ 該表達力直接用 chordEvent() 工廠構造（Test D/E）。
   - 輸入 doc 永遠不被修改（可 deep-compare 驗證）。 */
  function legacyToEvents(doc) {
    var out = [];
    (doc.measures || []).forEach(function (m, mi) {
      var label = 'm' + mi;

      var notes = String(m.noteText || '').split(/\s+/).filter(Boolean);
      var melodyEvents = notes.map(function (tok, i) {
        var above = (tok.match(new RegExp(DOT_ABOVE, 'g')) || []).length;
        var below = (tok.match(new RegExp(DOT_BELOW, 'g')) || []).length;
        var base = tok.replace(new RegExp('[' + DOT_ABOVE + DOT_BELOW + ']', 'g'), '');
        var isRest = base === '0';
        return noteEvent({
          id: label + '.note.' + i,
          start: i,
          duration: 1,
          pitch: isRest ? null : base,
          octave: (above - below) !== 0 ? above - below : null,
          rest: isRest
        });
      });

      var lyrics = String(m.lyricText || '').split(/\s+/).filter(Boolean);
      var lyricEvents = lyrics.map(function (txt, j) {
        return lyricEvent({ id: label + '.lyric.' + j, start: j, duration: 1, text: txt });
      });

      var chords = String(m.chordText || '').split(/\s+/).filter(Boolean);
      var chordEvents = chords.map(function (txt, k) {
        return chordEvent({ id: label + '.chord.' + k, start: k, text: txt });
      });

      out.push(measure({
        measure: m.number != null ? m.number : mi + 1,
        melodyEvents: melodyEvents,
        lyricEvents: lyricEvents,
        chordEvents: chordEvents
      }));
    });
    return out;
  }

  return {
    noteEvent: noteEvent,
    lyricEvent: lyricEvent,
    chordEvent: chordEvent,
    measure: measure,
    legacyToEvents: legacyToEvents,
    version: 'phase1.5.0'
  };
});
