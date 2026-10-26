/* ============================================================
 * Phase 4A — Isolated Editor Core（Selection + Command API + validateMeasure）
 *
 * 純資料層（第四層 Editor）：
 *   Event Model（凍結）→ Layout Engine（凍結）→ Renderer（3A/3B 凍結）→ Editor（本層）
 *
 * 設計原則：
 *   1. 全部 command 為純函數：copy-on-write 回傳新 doc，輸入 doc 永不 mutation
 *      （前後 deep-equal 可由測試驗證）。
 *   2. 只改受影響的 measure，其餘 measure deep-copy 保留。
 *   3. no-fabricate：未知/缺失 pitch 一律 throw，不補成四分音符。
 *   4. 時間合法性沿用 Layout 規則：start < 0、duration <= 0（非 null-chord）→ throw，不偷修。
 *   5. 每個 command 回傳 { newDoc, commandRecord }；commandRecord 供 4B undo/redo 使用。
 *   6. 本模組禁止：document / window / DOM / querySelector / CSS / Canvas /
 *      任何 P0（app.js/styles.css/index.html）或 Legacy 依賴。
 *
 * 只讀依賴：phase15/event_model.js（事件工廠，字節凍結、不改）。
 *
 * 新增事件 id 格式（與 Selection 解析約定一致）：
 *   m{measureId}.{track}.{eventIndex}，track ∈ melody | lyrics | chords
 *
 * 用法（Node）：
 *   const EditorCore = require('./editor.js');
 *   const { newDoc, commandRecord } = EditorCore.addNote(doc, 0, 0, { pitch: 1, duration: 1 });
 * ============================================================ */
(function (root, factory) {
  'use strict';
  if (typeof module !== 'undefined' && module.exports) {
    module.exports = factory(typeof require !== 'undefined' ? require('../phase15/event_model.js') : (root && root.EventModel));
  } else {
    root.EditorCore = factory((typeof self !== 'undefined' ? self : globalThis).EventModel);
  }
})(typeof self !== 'undefined' ? self : (typeof globalThis !== 'undefined' ? globalThis : this), function (EventModel) {
  'use strict';
  if (!EventModel || typeof EventModel.noteEvent !== 'function' || typeof EventModel.measure !== 'function') {
    throw new Error('EditorCore: EventModel (phase15/event_model.js) unavailable');
  }

  /* ---- 基礎工具 ---- */
  function deepCopy(x) {
    if (x == null) return x;
    return JSON.parse(JSON.stringify(x));
  }

  var TRACKS = { melody: 'melodyEvents', lyrics: 'lyricEvents', chords: 'chordEvents' };
  var SEQ = 0;
  function makeId() {
    SEQ += 1;
    var rid;
    try {
      rid = (typeof globalThis !== 'undefined' && globalThis.crypto && globalThis.crypto.randomUUID)
        ? globalThis.crypto.randomUUID()
        : ('rnd-' + Math.random().toString(36).slice(2));
    } catch (e) { rid = 'rnd-' + Math.random().toString(36).slice(2); }
    return 'cmd-' + SEQ + '-' + rid;
  }

  /* ---- 時間合法性（沿用 Layout：throw 不偷修）---- */
  function assertTick(tick, ctx) {
    if (typeof tick !== 'number' || !isFinite(tick) || tick < 0) {
      throw new Error('editor: ' + ctx + ' tick/start must be a finite number >= 0, got ' + tick);
    }
  }
  function assertPosDuration(d, kind) {
    if (d != null && (typeof d !== 'number' || !isFinite(d) || d <= 0)) {
      throw new Error('editor: ' + kind + ' duration must be a finite number > 0, got ' + d);
    }
  }

  /* ---- no-fabricate：pitch 必須是 0–7（number 或數字字串）；rest=true → 0；否則 throw ---- */
  function normalizePitch(p, rest) {
    if (rest) return 0;
    if (p == null) {
      throw new Error('editor: no-fabricate — missing pitch; will not auto-fill (add rest=true for 休止)');
    }
    var n = (typeof p === 'number') ? p : (/^[0-7]$/.test(String(p)) ? parseInt(String(p), 10) : NaN);
    if (!Number.isInteger(n) || n < 0 || n > 7) {
      throw new Error('editor: no-fabricate — unknown pitch "' + p + '" rejected; will not auto-fill');
    }
    return n;
  }
  function isKnownPitch(p, rest) {
    if (rest) return true;
    if (p == null) return false;
    var n = (typeof p === 'number') ? p : (/^[0-7]$/.test(String(p)) ? parseInt(String(p), 10) : NaN);
    return Number.isInteger(n) && n >= 0 && n <= 7;
  }
  function requireText(v, label) {
    if (typeof v !== 'string' || v.length === 0) {
      throw new Error('editor: ' + label + ' must be a non-empty string, got ' + (typeof v === 'string' ? JSON.stringify(v) : String(v)));
    }
    return v;
  }
  function toEventKey(eventKey) {
    if (!Number.isInteger(eventKey) || eventKey < 0) {
      throw new Error('editor: eventKey must be a non-negative integer, got ' + eventKey);
    }
    return eventKey;
  }
  function idFor(measureId, track, index) {
    return 'm' + measureId + '.' + track + '.' + index;
  }

  /* 依 start 找插入位置（依時間排序，非 array index 綁定） */
  function insertIndex(arr, tick) {
    var i = 0;
    while (i < arr.length && ((arr[i] && arr[i].start != null) ? arr[i].start : 0) <= tick) i++;
    return i;
  }

  /* ---- doc / measure 工廠 ---- */
  function createEmptyDoc() {
    return { measures: [] };
  }
  function createEmptyMeasure() {
    return EventModel.measure({});
  }

  /* measureId 解析（在 newDoc 上操作）：
     - 空 doc + measureId===0 → 自動建立 measure 0（文件化行為，供 4A B1 規格）；
     - 其餘 measureId 必須在既有範圍內，否則 throw（不靜默擴張）。 */
  function ensureMeasure(doc, measureId) {
    if (!Number.isInteger(measureId) || measureId < 0) {
      throw new Error('editor: measureId must be a non-negative integer, got ' + measureId);
    }
    if (doc.measures.length === 0 && measureId === 0) {
      doc.measures.push(createEmptyMeasure());
      return null; // 新建 measure：無「原始狀態」可記
    }
    if (measureId >= doc.measures.length) {
      throw new Error('editor: measureId ' + measureId + ' out of range (doc has ' + doc.measures.length + ' measures)');
    }
    return deepCopy(doc.measures[measureId]);
  }

  function buildRecord(type, measureId, track, eventKey, payload, revertPayload, affectedMeasure) {
    return {
      id: makeId(),
      type: type,
      timestamp: Date.now(),
      measureId: measureId,
      track: track,
      eventKey: eventKey,
      payload: payload,
      revertPayload: revertPayload,
      affectedMeasure: affectedMeasure
    };
  }

  /* ---- Note 事件 ---- */
  function makeNote(spec, tick) {
    spec = spec || {};
    var rest = spec.rest === true;
    var pitch = normalizePitch(spec.pitch, rest);
    if (pitch === 0) rest = true;
    var d = (spec.duration != null) ? spec.duration : 1;
    assertPosDuration(d, 'note');
    return EventModel.noteEvent({
      start: tick,
      duration: d,
      pitch: pitch,
      accidental: (spec.accidental != null) ? spec.accidental : null,
      octave: (spec.octave != null) ? spec.octave : null,
      dotted: spec.dotted === true,
      tieStart: spec.tieStart === true,
      tieEnd: spec.tieEnd === true,
      rest: rest
    });
  }

  function addNote(doc, measureId, tick, spec) {
    assertTick(tick, 'addNote');
    var note = makeNote(spec, tick);
    var newDoc = deepCopy(doc);
    var affected = ensureMeasure(newDoc, measureId);
    var evs = newDoc.measures[measureId].melodyEvents;
    var idx = insertIndex(evs, tick);
    note.id = idFor(measureId, 'melody', idx);
    evs.splice(idx, 0, note);
    var payload = { pitch: note.pitch, duration: note.duration };
    ['accidental', 'octave', 'dotted', 'tieStart', 'tieEnd', 'rest'].forEach(function (k) {
      if (Object.prototype.hasOwnProperty.call(spec || {}, k)) payload[k] = spec[k];
    });
    return { newDoc: newDoc, commandRecord: buildRecord('addNote', measureId, 'melody', idx, payload, null, affected) };
  }

  function setNote(doc, measureId, eventKey, patch) {
    patch = patch || {};
    if (Object.prototype.hasOwnProperty.call(patch, 'start')) {
      throw new Error('editor: setNote patch does not support "start"（reposition 留待後續階段）');
    }
    var i = toEventKey(eventKey);
    var newDoc = deepCopy(doc);
    var affected = ensureMeasure(newDoc, measureId);
    if (affected == null) throw new Error('editor: setNote requires an existing measure ' + measureId);
    var evs = newDoc.measures[measureId].melodyEvents;
    if (i >= evs.length) throw new Error('editor: eventKey ' + i + ' out of range (measure has ' + evs.length + ' notes)');
    var original = deepCopy(evs[i]);
    var merged = Object.assign({}, original, patch);
    var rest = (patch.rest != null) ? patch.rest === true : original.rest === true;
    var pitch = normalizePitch(merged.pitch, rest);
    if (pitch === 0) rest = true;
    var d = (patch.duration != null) ? patch.duration : original.duration;
    assertPosDuration(d, 'note');
    var nv = EventModel.noteEvent({
      id: original.id,
      start: original.start,
      duration: d,
      pitch: pitch,
      accidental: merged.accidental != null ? merged.accidental : original.accidental,
      octave: merged.octave != null ? merged.octave : original.octave,
      dotted: merged.dotted === true,
      tieStart: merged.tieStart === true,
      tieEnd: merged.tieEnd === true,
      rest: rest
    });
    evs[i] = nv;
    var payload = {};
    Object.keys(patch).forEach(function (k) { payload[k] = patch[k]; });
    // setNote revertPayload = 原 { pitch, duration }（依 4A C3 斷言；4B undo 依 index 套用）
    var revert = { pitch: original.pitch, duration: original.duration };
    return { newDoc: newDoc, commandRecord: buildRecord('setNote', measureId, 'melody', i, payload, revert, affected) };
  }

  function removeNote(doc, measureId, eventKey) {
    var i = toEventKey(eventKey);
    var newDoc = deepCopy(doc);
    var affected = ensureMeasure(newDoc, measureId);
    if (affected == null) throw new Error('editor: removeNote requires an existing measure ' + measureId);
    var evs = newDoc.measures[measureId].melodyEvents;
    if (i >= evs.length) throw new Error('editor: eventKey ' + i + ' out of range (measure has ' + evs.length + ' notes)');
    var original = deepCopy(evs[i]);
    evs.splice(i, 1);
    return { newDoc: newDoc, commandRecord: buildRecord('removeNote', measureId, 'melody', i, { eventKey: i }, original, affected) };
  }

  /* ---- Lyric 事件 ---- */
  function addLyric(doc, measureId, tick, text) {
    assertTick(tick, 'addLyric');
    text = requireText(text, 'lyric text');
    var newDoc = deepCopy(doc);
    var affected = ensureMeasure(newDoc, measureId);
    var evs = newDoc.measures[measureId].lyricEvents;
    var idx = insertIndex(evs, tick);
    var lyric = EventModel.lyricEvent({ id: idFor(measureId, 'lyrics', idx), start: tick, duration: 1, text: text });
    evs.splice(idx, 0, lyric);
    return { newDoc: newDoc, commandRecord: buildRecord('addLyric', measureId, 'lyrics', idx, { text: text }, null, affected) };
  }

  function setLyric(doc, measureId, eventKey, text) {
    text = requireText(text, 'lyric text');
    var i = toEventKey(eventKey);
    var newDoc = deepCopy(doc);
    var affected = ensureMeasure(newDoc, measureId);
    if (affected == null) throw new Error('editor: setLyric requires an existing measure ' + measureId);
    var evs = newDoc.measures[measureId].lyricEvents;
    if (i >= evs.length) throw new Error('editor: eventKey ' + i + ' out of range (measure has ' + evs.length + ' lyrics)');
    var original = deepCopy(evs[i]);
    var nl = EventModel.lyricEvent({
      id: original.id,
      start: original.start,
      duration: (original.duration != null) ? original.duration : 1,
      text: text
    });
    evs[i] = nl;
    return { newDoc: newDoc, commandRecord: buildRecord('setLyric', measureId, 'lyrics', i, { text: text }, original, affected) };
  }

  function removeLyric(doc, measureId, eventKey) {
    var i = toEventKey(eventKey);
    var newDoc = deepCopy(doc);
    var affected = ensureMeasure(newDoc, measureId);
    if (affected == null) throw new Error('editor: removeLyric requires an existing measure ' + measureId);
    var evs = newDoc.measures[measureId].lyricEvents;
    if (i >= evs.length) throw new Error('editor: eventKey ' + i + ' out of range (measure has ' + evs.length + ' lyrics)');
    var original = deepCopy(evs[i]);
    evs.splice(i, 1);
    return { newDoc: newDoc, commandRecord: buildRecord('removeLyric', measureId, 'lyrics', i, { eventKey: i }, original, affected) };
  }

  /* ---- Chord 事件 ---- */
  function addChord(doc, measureId, tick, text, duration) {
    assertTick(tick, 'addChord');
    text = requireText(text, 'chord text');
    if (duration != null) assertPosDuration(duration, 'chord');
    var newDoc = deepCopy(doc);
    var affected = ensureMeasure(newDoc, measureId);
    var evs = newDoc.measures[measureId].chordEvents;
    var idx = insertIndex(evs, tick);
    var chord = EventModel.chordEvent({
      id: idFor(measureId, 'chords', idx),
      start: tick,
      duration: (duration == null) ? null : duration,
      text: text
    });
    evs.splice(idx, 0, chord);
    return { newDoc: newDoc, commandRecord: buildRecord('addChord', measureId, 'chords', idx, { text: text, duration: (duration == null) ? null : duration }, null, affected) };
  }

  function setChord(doc, measureId, eventKey, patch) {
    patch = patch || {};
    if (patch.text != null) requireText(patch.text, 'chord text');
    if (patch.duration != null) assertPosDuration(patch.duration, 'chord');
    if (Object.prototype.hasOwnProperty.call(patch, 'start')) {
      throw new Error('editor: setChord patch does not support "start"（reposition 留待後續階段）');
    }
    var i = toEventKey(eventKey);
    var newDoc = deepCopy(doc);
    var affected = ensureMeasure(newDoc, measureId);
    if (affected == null) throw new Error('editor: setChord requires an existing measure ' + measureId);
    var evs = newDoc.measures[measureId].chordEvents;
    if (i >= evs.length) throw new Error('editor: eventKey ' + i + ' out of range (measure has ' + evs.length + ' chords)');
    var original = deepCopy(evs[i]);
    var merged = Object.assign({}, original, patch);
    // 未 patch duration 時保留原值（chord duration 可為 null 或數字）
    var nc = EventModel.chordEvent({
      id: original.id,
      start: original.start,
      duration: (patch.duration != null) ? patch.duration : original.duration,
      text: (patch.text != null) ? patch.text : original.text
    });
    evs[i] = nc;
    var payload = {};
    Object.keys(patch).forEach(function (k) { payload[k] = patch[k]; });
    return { newDoc: newDoc, commandRecord: buildRecord('setChord', measureId, 'chords', i, payload, original, affected) };
  }

  function removeChord(doc, measureId, eventKey) {
    var i = toEventKey(eventKey);
    var newDoc = deepCopy(doc);
    var affected = ensureMeasure(newDoc, measureId);
    if (affected == null) throw new Error('editor: removeChord requires an existing measure ' + measureId);
    var evs = newDoc.measures[measureId].chordEvents;
    if (i >= evs.length) throw new Error('editor: eventKey ' + i + ' out of range (measure has ' + evs.length + ' chords)');
    var original = deepCopy(evs[i]);
    evs.splice(i, 1);
    return { newDoc: newDoc, commandRecord: buildRecord('removeChord', measureId, 'chords', i, { eventKey: i }, original, affected) };
  }

  /* ---- Measure 命令 ---- */
  function renumber(ms) {
    for (var i = 0; i < ms.length; i++) ms[i].measure = i;
  }

  function addMeasure(doc, afterIndex) {
    if (!Number.isInteger(afterIndex) || afterIndex < -1 || afterIndex >= doc.measures.length) {
      throw new Error('editor: addMeasure afterIndex must be in [-1, ' + (doc.measures.length - 1) + '], got ' + afterIndex);
    }
    var newDoc = deepCopy(doc);
    var pos = afterIndex + 1;
    newDoc.measures.splice(pos, 0, createEmptyMeasure());
    renumber(newDoc.measures);
    return { newDoc: newDoc, commandRecord: buildRecord('addMeasure', pos, null, null, { afterIndex: afterIndex }, null, null) };
  }

  function removeMeasure(doc, measureId) {
    if (!Number.isInteger(measureId) || measureId < 0 || measureId >= doc.measures.length) {
      throw new Error('editor: removeMeasure measureId out of range, got ' + measureId);
    }
    var newDoc = deepCopy(doc);
    var removed = deepCopy(newDoc.measures[measureId]);
    newDoc.measures.splice(measureId, 1);
    renumber(newDoc.measures);
    return { newDoc: newDoc, commandRecord: buildRecord('removeMeasure', measureId, null, null, { measureId: measureId }, removed, removed) };
  }

  /* ---- Selection 模型 ----
     格式（與 4C renderer 的 data-* 約定一致）：
       data-event-id    : m{measureIndex}.{melody|lyrics|chords}.{eventIndex}
       data-insert-tick : m{measureIndex}.insert.{tick} */
  function parseEventIdToSelection(eventId) {
    var m = /^m(\d+)\.(melody|lyrics|chords)\.(\d+)$/.exec(String(eventId));
    if (!m) throw new Error('editor: invalid event id "' + eventId + '"（預期 m{measureId}.{track}.{eventIndex}）');
    return { measureId: parseInt(m[1], 10), track: m[2], eventKey: parseInt(m[3], 10), insertTick: null, mode: 'select' };
  }

  function parseInsertTickToSelection(insertTickStr) {
    var m = /^m(\d+)\.insert\.(\d+(?:\.\d+)?)$/.exec(String(insertTickStr));
    if (!m) throw new Error('editor: invalid insert-tick "' + insertTickStr + '"（預期 m{measureId}.insert.{tick}）');
    return { measureId: parseInt(m[1], 10), track: 'melody', eventKey: null, insertTick: parseFloat(m[2]), mode: 'insert' };
  }

  function validateSelection(sel) {
    if (!sel || typeof sel !== 'object') return false;
    if (!Number.isInteger(sel.measureId) || sel.measureId < 0) return false;
    if (TRACKS[sel.track] === undefined) return false;
    if (sel.mode === 'select') {
      if (!Number.isInteger(sel.eventKey) || sel.eventKey < 0) return false;
      if (sel.insertTick != null) return false;
      return true;
    }
    if (sel.mode === 'insert') {
      if (sel.eventKey != null) return false;
      if (typeof sel.insertTick !== 'number' || !isFinite(sel.insertTick) || sel.insertTick < 0) return false;
      return true;
    }
    return false;
  }

  /* ---- validateMeasure 純函數（不補拍、不修正，只回報）----
     規則：
       - 每個 event 的 start 必須為 number 且 >= 0（否則 error）
       - note/lyric duration 必須 > 0（error）；chord duration 可 null（位置性）或 > 0
       - 未知 pitch（ambig/unknown/null 且非 rest）→ warning「unknown」，不補
       - coverage = max(start + duration)；< beatsPerMeasure → warning「underfilled」
       - coverage > beatsPerMeasure → error「overflow」（4B 會據此阻止危險寫入） */
  function validateMeasure(measure, options) {
    measure = measure || {};
    options = options || {};
    var bpm = (options.beatsPerMeasure != null) ? options.beatsPerMeasure : 4;
    if (!Number.isInteger(bpm) || bpm <= 0) {
      throw new Error('editor: validateMeasure beatsPerMeasure must be a positive integer, got ' + bpm);
    }
    var errors = [];
    var warnings = [];
    var label = 'm' + (measure.measure != null ? measure.measure : 0);
    var specs = [
      ['melody', measure.melodyEvents || [], 'note'],
      ['lyrics', measure.lyricEvents || [], 'lyric'],
      ['chords', measure.chordEvents || [], 'chord']
    ];
    var coverage = 0;
    specs.forEach(function (s) {
      var tName = s[0], arr = s[1], kind = s[2];
      for (var i = 0; i < arr.length; i++) {
        var ev = arr[i] || {};
        var el = label + '.' + tName + '[' + i + ']';
        var st = (ev.start != null) ? ev.start : 0;
        if (typeof st !== 'number' || !isFinite(st) || st < 0) {
          errors.push(el + ': start must be a finite number >= 0, got ' + st);
          continue;
        }
        var d = ev.duration;
        if (kind === 'chord') {
          if (d != null && (typeof d !== 'number' || !isFinite(d) || d <= 0)) {
            errors.push(el + ': chord duration must be null or > 0, got ' + d);
          }
        } else if (typeof d !== 'number' || !isFinite(d) || d <= 0) {
          errors.push(el + ': duration must be a finite number > 0, got ' + d);
        }
        if (kind === 'note' && !ev.rest && !isKnownPitch(ev.pitch, ev.rest)) {
          warnings.push(el + ': unknown pitch ("' + ev.pitch + '") — marked unknown, not filled');
        }
        var end = st + ((d != null) ? d : 0);
        if (end > coverage) coverage = end;
      }
    });
    if (coverage < bpm) warnings.push(label + ' underfilled: coverage ' + coverage + ' < ' + bpm + ' beats');
    if (coverage > bpm) errors.push(label + ' overflow: coverage ' + coverage + ' > ' + bpm + ' beats');
    return { isValid: errors.length === 0, errors: errors, warnings: warnings };
  }

  return {
    createEmptyDoc: createEmptyDoc,
    createEmptyMeasure: createEmptyMeasure,
    parseEventIdToSelection: parseEventIdToSelection,
    parseInsertTickToSelection: parseInsertTickToSelection,
    validateSelection: validateSelection,
    addNote: addNote,
    setNote: setNote,
    removeNote: removeNote,
    addLyric: addLyric,
    setLyric: setLyric,
    removeLyric: removeLyric,
    addChord: addChord,
    setChord: setChord,
    removeChord: removeChord,
    addMeasure: addMeasure,
    removeMeasure: removeMeasure,
    validateMeasure: validateMeasure,
    deepCopy: deepCopy,
    version: 'phase4.0.0'
  };
});
