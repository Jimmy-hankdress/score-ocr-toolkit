/**
 * Bidirectional Sync Engine Module (web/assets/sync-engine.js)
 * 負責 ChordPro 編輯器與 Score Studio (state3.doc) 之間的即時雙向同步、
 * 防抖 (<100ms)、防迴圈編輯鎖、語法錯誤回滾 (Optimistic Update + Rollback)。
 */
(function (root, factory) {
  if (typeof module === 'object' && module.exports) {
    var parser = require('./chordpro-parser.js');
    var conflict = require('./sync-conflict.js');
    var version = require('./sync-version.js');
    module.exports = factory(root, parser, conflict, version);
  } else {
    var api = factory(root, root.ChordProParser, root.SyncConflict, root.SyncVersion);
    root.SyncEngine = api;
    root.syncChordProEditor = api.syncChordProEditor;
    root.syncFromChordProToScore = api.syncFromChordProToScore;
  }
})(typeof self !== 'undefined' ? self : this, function (root, Parser, Conflict, Version) {
  'use strict';

  var DEFAULT_DEBOUNCE_MS = 60; // < 100ms 即時同步要求
  var syncLock = false;
  var debounceTimer = null;
  var lastValidDocSnapshot = null;
  var lastSyncStatus = { ok: true, direction: null, timestamp: 0, errors: [], conflicts: [] };

  function cloneDoc(doc) {
    if (!doc) return null;
    return JSON.parse(JSON.stringify(doc));
  }

  /**
   * 將變更套用到目標 doc 物件（原地更新欄位與 measures，保留既有 noteText / ticks / id 等）
   */
  function mergeParsedIntoDoc(targetDoc, parsedDoc, ensureMeasureFn) {
    if (!targetDoc || !parsedDoc) return targetDoc;
    if (parsedDoc.title && parsedDoc.title !== 'Untitled') targetDoc.title = parsedDoc.title;
    if (parsedDoc.key) targetDoc.key = parsedDoc.key;
    if (parsedDoc.timeSignature) targetDoc.timeSignature = parsedDoc.timeSignature;
    if (parsedDoc.tempo) targetDoc.tempo = parsedDoc.tempo;
    if (parsedDoc.lyricist !== undefined) targetDoc.lyricist = parsedDoc.lyricist;
    if (parsedDoc.composer !== undefined) targetDoc.composer = parsedDoc.composer;
    if (parsedDoc.capo !== undefined) targetDoc.capo = parsedDoc.capo;
    if (Array.isArray(parsedDoc.sections)) targetDoc.sections = parsedDoc.sections;

    var oldMeasures = Array.isArray(targetDoc.measures) ? targetDoc.measures : [];
    var newMeasures = [];

    for (var i = 0; i < parsedDoc.measures.length; i++) {
      var pm = parsedDoc.measures[i];
      var existing = oldMeasures[i] || {};
      var m = {
        number: i + 1,
        lineIndex: Math.floor(i / 3),
        linePosition: (i % 3) + 1,
        chordText: pm.chordText !== undefined ? pm.chordText : (existing.chordText || ''),
        chordOffsets: Array.isArray(existing.chordOffsets) ? existing.chordOffsets.slice() : [],
        noteText: pm.noteText ? pm.noteText : (existing.noteText || ''),
        lyricText: pm.lyricText !== undefined ? pm.lyricText : (existing.lyricText || ''),
        lyricText2: existing.lyricText2 || '',
        lyricText3: existing.lyricText3 || '',
        lyricText4: existing.lyricText4 || '',
        lyricRows: existing.lyricRows || 1,
        barline: existing.barline !== undefined ? existing.barline : true,
        marks: existing.marks || '',
        beats: Array.isArray(existing.beats) ? existing.beats : []
      };
      if (pm.section) {
        m.section = pm.section;
      } else if (existing.section) {
        m.section = existing.section;
      }
      if (typeof ensureMeasureFn === 'function') {
        ensureMeasureFn(m);
      }
      newMeasures.push(m);
    }

    targetDoc.measures = newMeasures;
    return targetDoc;
  }

  /**
   * 方向 A：ChordPro 文字 → Score Studio (doc)
   * 具備 Optimistic Update + 語法驗證失敗自動回滾機制
   * @param {string} chordproText
   * @param {object} targetDoc
   * @param {object} [hooks] - { ensureEventModel, onUpdated, onError }
   * @returns {{ ok: boolean, doc: object, errors: Array, conflicts: Array, rolledBack: boolean }}
   */
  function syncFromChordProToScore(chordproText, targetDoc, hooks) {
    hooks = hooks || {};
    if (targetDoc && !Array.isArray(targetDoc.measures) && (targetDoc.state || targetDoc.doc || targetDoc.renderScore)) {
      hooks = Object.assign({}, targetDoc, hooks);
      targetDoc = (targetDoc.state && targetDoc.state.doc) ? targetDoc.state.doc : targetDoc.doc;
    }
    var onUpdatedFn = hooks.onUpdated || hooks.renderScore;
    if (syncLock) {
      return { ok: false, doc: targetDoc, errors: [], conflicts: [], rolledBack: false, locked: true };
    }

    syncLock = true;
    var backup = cloneDoc(targetDoc);
    try {
      var validation = Parser.validateChordPro(chordproText);
      if (!validation.valid) {
        // 語法錯誤：保持原狀態（回滾）並回報錯誤
        if (backup && targetDoc) {
          Object.assign(targetDoc, backup);
        }
        lastSyncStatus = {
          ok: false,
          direction: 'chordpro->score',
          timestamp: Date.now(),
          errors: validation.errors,
          conflicts: []
        };
        if (typeof hooks.onError === 'function') {
          hooks.onError(validation.errors, targetDoc);
        }
        return {
          ok: false,
          doc: targetDoc,
          errors: validation.errors,
          conflicts: [],
          rolledBack: true
        };
      }

      var conflictReport = Conflict.detectConflicts(chordproText, targetDoc ? targetDoc.measures : []);
      var parsed = Parser.parseChordProToDoc(chordproText, { existingDoc: targetDoc, strict: true });

      if (targetDoc) {
        mergeParsedIntoDoc(targetDoc, parsed, hooks.ensureEventModel);
      } else {
        targetDoc = parsed;
      }

      lastValidDocSnapshot = cloneDoc(targetDoc);
      Version.trackVersion('chordpro', chordproText);
      Version.trackVersion('score', targetDoc);

      lastSyncStatus = {
        ok: true,
        direction: 'chordpro->score',
        timestamp: Date.now(),
        errors: [],
        conflicts: conflictReport.conflicts
      };

      if (typeof onUpdatedFn === 'function') {
        onUpdatedFn(targetDoc, conflictReport);
      }

      return {
        ok: true,
        doc: targetDoc,
        errors: [],
        conflicts: conflictReport.conflicts,
        rolledBack: false
      };
    } catch (err) {
      if (backup && targetDoc) {
        Object.assign(targetDoc, backup);
      }
      var errList = err && err.errors ? err.errors : [{ code: 'E-999', line: 0, message: err.message || String(err) }];
      lastSyncStatus = {
        ok: false,
        direction: 'chordpro->score',
        timestamp: Date.now(),
        errors: errList,
        conflicts: []
      };
      if (typeof hooks.onError === 'function') {
        hooks.onError(errList, targetDoc);
      }
      return {
        ok: false,
        doc: targetDoc,
        errors: errList,
        conflicts: [],
        rolledBack: true
      };
    } finally {
      syncLock = false;
    }
  }

  /**
   * 方向 B：Score Studio (doc) → ChordPro 編輯器
   * @param {object} doc
   * @param {object} [options] - { editorEl, mode }
   * @returns {string} rendered ChordPro text
   */
  function syncChordProEditor(doc, options) {
    options = options || {};
    if (!doc) return '';
    if (syncLock) return '';

    syncLock = true;
    try {
      var text = Parser.renderDocToChordPro(doc, options);
      var ed = options.editorEl || (typeof document !== 'undefined' ? document.getElementById('chordpro-editor') : null);
      if (ed && ed.value !== text) {
        ed.value = text;
      }
      lastValidDocSnapshot = cloneDoc(doc);
      Version.trackVersion('score', doc);
      Version.trackVersion('chordpro', text);
      lastSyncStatus = {
        ok: true,
        direction: 'score->chordpro',
        timestamp: Date.now(),
        errors: [],
        conflicts: []
      };
      return text;
    } finally {
      syncLock = false;
    }
  }

  /**
   * 綁定瀏覽器 DOM 的雙向即時同步（含防抖 <100ms）
   * @param {object} config - { getDoc, ensureEventModel, onScoreUpdated, onSyncError, debounceMs }
   */
  function bindEditorSync(config) {
    config = config || {};
    if (typeof document === 'undefined') return;
    var editor = document.getElementById('chordpro-editor');
    if (!editor || editor.__chordproSyncBound) return;
    editor.__chordproSyncBound = true;

    var waitMs = typeof config.debounceMs === 'number' ? config.debounceMs : DEFAULT_DEBOUNCE_MS;

    editor.addEventListener('input', function () {
      if (syncLock) return;
      if (debounceTimer) clearTimeout(debounceTimer);
      debounceTimer = setTimeout(function () {
        var doc = typeof config.getDoc === 'function' ? config.getDoc() : null;
        if (!doc) return;
        syncFromChordProToScore(editor.value, doc, {
          ensureEventModel: config.ensureEventModel,
          onUpdated: config.onScoreUpdated,
          onError: config.onSyncError
        });
      }, waitMs);
    });
  }

  function getLastSyncStatus() {
    return lastSyncStatus;
  }

  return {
    syncFromChordProToScore: syncFromChordProToScore,
    syncChordProEditor: syncChordProEditor,
    bindEditorSync: bindEditorSync,
    mergeParsedIntoDoc: mergeParsedIntoDoc,
    getLastSyncStatus: getLastSyncStatus
  };
});
