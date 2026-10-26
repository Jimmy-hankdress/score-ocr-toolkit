/* ============================================================
 * Phase 4B — Measure Validation（純資料層：拍數 / 合法性驗證）
 *
 * 定位：為 Command Stack / 4C 預覽提供結構化拍數判定。
 * 獨立實作（不共用 4A validateMeasure），因需額外欄位：
 *   totalTicks / underfilled / overflow / unknownCount
 *
 * 規則（不補拍、不修正，只回報）：
 *   - 每個 event 的 start 必須為有限數且 >= 0（否則 error）
 *   - note/lyric duration 必須 > 0（否則 error）
 *   - chord duration 可 null（位置性）或 > 0（否則 error）
 *   - unknown pitch（非 rest 且無法解析 0–7）→ warning + unknownCount++，不補
 *   - rest（rest=true）不誤判 unknown
 *   - totalTicks = melody 軌時長覆蓋（coverage = max(start+duration)）
 *       underfilled = totalTicks < beatsPerMeasure（warning）
 *       overflow    = totalTicks > beatsPerMeasure（error）
 *
 * 純資料：無 DOM/UI/儲存；P0/Legacy 完全不碰。
 * ============================================================ */
(function (root, factory) {
  'use strict';
  if (typeof module !== 'undefined' && module.exports) module.exports = factory();
  else if (root) root.MeasureValidation = factory();
})(typeof self !== 'undefined' ? self : (typeof globalThis !== 'undefined' ? globalThis : this), function () {
  'use strict';

  var DEFAULT_BPM = 4;

  function knownPitch(p, rest) {
    if (rest) return true;
    if (p == null) return false;
    var n = (typeof p === 'number') ? p : (/^[0-7]$/.test(String(p)) ? parseInt(String(p), 10) : NaN);
    return Number.isInteger(n) && n >= 0 && n <= 7;
  }

  function finiteNonNegStart(st) {
    return typeof st === 'number' && isFinite(st) && st >= 0;
  }

  /* ---- 驗證單一 measure ---- */
  function validateMeasure(measure, options) {
    measure = measure || {};
    options = options || {};
    var bpm = (options.beatsPerMeasure != null) ? options.beatsPerMeasure : DEFAULT_BPM;
    if (!Number.isInteger(bpm) || bpm <= 0) {
      throw new Error('measure_validation: beatsPerMeasure must be a positive integer, got ' + bpm);
    }
    var errors = [];
    var warnings = [];
    var label = 'm' + (measure.measure != null ? measure.measure : 0);
    var totalTicks = 0;
    var unknownCount = 0;

    // melody 軌：totalTicks（coverage）+ unknown pitch
    (measure.melodyEvents || []).forEach(function (ev, i) {
      ev = ev || {};
      var el = label + '.melody[' + i + ']';
      var st = ev.start != null ? ev.start : 0;
      if (!finiteNonNegStart(st)) {
        errors.push(el + ': start must be a finite number >= 0, got ' + st);
        return;
      }
      var d = ev.duration;
      if (typeof d !== 'number' || !isFinite(d) || d <= 0) {
        errors.push(el + ': note duration must be a finite number > 0, got ' + d);
      }
      var end = st + ((typeof d === 'number' && isFinite(d) && d > 0) ? d : 0);
      if (end > totalTicks) totalTicks = end;
      if (!ev.rest && !knownPitch(ev.pitch, ev.rest)) {
        unknownCount += 1;
        warnings.push(el + ': unknown pitch ("' + ev.pitch + '") — marked unknown, not filled');
      }
    });

    // lyrics 軌：duration 合法性（不計入 totalTicks）
    (measure.lyricEvents || []).forEach(function (ev, i) {
      ev = ev || {};
      var el = label + '.lyrics[' + i + ']';
      var st = ev.start != null ? ev.start : 0;
      if (!finiteNonNegStart(st)) {
        errors.push(el + ': start must be a finite number >= 0, got ' + st);
        return;
      }
      if (typeof ev.duration !== 'number' || !isFinite(ev.duration) || ev.duration <= 0) {
        errors.push(el + ': lyric duration must be a finite number > 0, got ' + ev.duration);
      }
    });

    // chords 軌：duration 可 null 或 > 0（不計入 totalTicks）
    (measure.chordEvents || []).forEach(function (ev, i) {
      ev = ev || {};
      var el = label + '.chords[' + i + ']';
      var st = ev.start != null ? ev.start : 0;
      if (!finiteNonNegStart(st)) {
        errors.push(el + ': start must be a finite number >= 0, got ' + st);
        return;
      }
      if (ev.duration != null && (typeof ev.duration !== 'number' || !isFinite(ev.duration) || ev.duration <= 0)) {
        errors.push(el + ': chord duration must be null or > 0, got ' + ev.duration);
      }
    });

    var underfilled = totalTicks < bpm;
    var overflow = totalTicks > bpm;
    if (underfilled) warnings.push(label + ' underfilled: coverage ' + totalTicks + ' < ' + bpm + ' beats');
    if (overflow) errors.push(label + ' overflow: coverage ' + totalTicks + ' > ' + bpm + ' beats');

    return {
      isValid: errors.length === 0,
      errors: errors,
      warnings: warnings,
      totalTicks: totalTicks,
      underfilled: underfilled,
      overflow: overflow,
      unknownCount: unknownCount
    };
  }

  /* ---- 驗證整份文件（逐 measure，彙總）---- */
  function validateDocument(doc, options) {
    doc = doc || {};
    var measures = (doc.measures && Array.isArray(doc.measures)) ? doc.measures : [];
    var errors = [];
    var warnings = [];
    var results = [];
    measures.forEach(function (m, idx) {
      var r = validateMeasure(m, options);
      results.push({
        measureId: (m && m.measure != null) ? m.measure : idx,
        result: r
      });
      if (!r.isValid) {
        r.errors.forEach(function (e) { errors.push('measure ' + idx + ': ' + e); });
      }
      r.warnings.forEach(function (w) { warnings.push('measure ' + idx + ': ' + w); });
    });
    return {
      isValid: errors.length === 0,
      errors: errors,
      warnings: warnings,
      measures: results
    };
  }

  return {
    validateMeasure: validateMeasure,
    validateDocument: validateDocument,
    version: 'phase4.0.0'
  };
});
