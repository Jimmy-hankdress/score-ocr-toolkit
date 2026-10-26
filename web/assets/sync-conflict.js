/**
 * Sync Conflict Detection Module (web/assets/sync-conflict.js)
 * 偵測 ChordPro 文字與 Score Studio 小節結構之間的資訊落差或內容差異。
 */
(function (root, factory) {
  if (typeof module === 'object' && module.exports) {
    var parser = null;
    try { parser = require('./chordpro-parser.js'); } catch (e) {}
    module.exports = factory(parser);
  } else {
    var api = factory(root.ChordProParser);
    root.SyncConflict = api;
    root.detectConflicts = api.detectConflicts;
    root.computeContentHash = api.computeContentHash;
  }
})(typeof self !== 'undefined' ? self : this, function (Parser) {
  'use strict';

  /**
   * 計算字串的穩定內容雜湊 (FNV-1a 32-bit hex)
   * @param {string} text
   * @returns {string}
   */
  function computeContentHash(text) {
    var str = String(text || '');
    var hash = 0x811c9dc5;
    for (var i = 0; i < str.length; i++) {
      hash ^= str.charCodeAt(i);
      hash = (hash + (hash << 1) + (hash << 4) + (hash << 7) + (hash << 8) + (hash << 24)) >>> 0;
    }
    return ('00000000' + (hash >>> 0).toString(16)).slice(-8);
  }

  /**
   * 偵測 ChordPro 文字與現有 measures 陣列的衝突與差異
   * @param {string} chordproText
   * @param {Array} measures
   * @returns {{ hasConflict: boolean, type: string|null, details: Array, conflicts: Array }}
   */
  function detectConflicts(chordproText, measures) {
    var conflicts = [];
    var safeMeasures = Array.isArray(measures) ? measures : [];
    var parseFn = (Parser && Parser.parseMeasures)
      ? Parser.parseMeasures
      : (typeof parseMeasures === 'function' ? parseMeasures : null);

    var chordproMeasures = parseFn ? parseFn(chordproText || '') : [];
    var primaryType = null;

    // 1. 小節數量不一致 (measure-mismatch)
    if (chordproMeasures.length !== safeMeasures.length) {
      primaryType = 'measure-mismatch';
      conflicts.push({
        type: 'measure_count_mismatch',
        category: 'measure-mismatch',
        message: 'ChordPro 有 ' + chordproMeasures.length + ' 小節，簡譜有 ' + safeMeasures.length + ' 小節',
        severity: 'warning'
      });
    }

    // 2. 逐小節內容差異 (content-diff: chord_conflict / lyric_conflict)
    var minLen = Math.min(chordproMeasures.length, safeMeasures.length);
    for (var i = 0; i < minLen; i++) {
      var cm = chordproMeasures[i] || {};
      var sm = safeMeasures[i] || {};
      var cChord = String(cm.chordText || '').trim();
      var sChord = String(sm.chordText || '').trim();
      if (cChord !== sChord) {
        if (!primaryType) primaryType = 'content-diff';
        conflicts.push({
          type: 'chord_conflict',
          category: 'content-diff',
          measureIndex: i,
          measureNumber: i + 1,
          chordproValue: cChord,
          scoreValue: sChord,
          message: '第 ' + (i + 1) + ' 小節和弦差異：ChordPro 為 "' + cChord + '"，簡譜為 "' + sChord + '"',
          severity: 'info'
        });
      }
      var cLyric = String(cm.lyricText || '').trim();
      var sLyric = String(sm.lyricText || '').trim();
      if (cLyric !== sLyric) {
        if (!primaryType) primaryType = 'content-diff';
        conflicts.push({
          type: 'lyric_conflict',
          category: 'content-diff',
          measureIndex: i,
          measureNumber: i + 1,
          chordproValue: cLyric,
          scoreValue: sLyric,
          message: '第 ' + (i + 1) + ' 小節歌詞差異：ChordPro 為 "' + cLyric + '"，簡譜為 "' + sLyric + '"',
          severity: 'info'
        });
      }
    }

    // 3. ChordPro 未包含簡譜音符但簡譜小節已有音符時，提示將自動保留既有音符
    var chordproHasNotes = chordproMeasures.some(function (m) {
      return m && m.noteText && m.noteText.trim().length > 0;
    });
    var hasNotesInScore = safeMeasures.some(function (m) {
      return m && m.noteText && m.noteText.trim().length > 0;
    });
    if (hasNotesInScore && !chordproHasNotes) {
      conflicts.push({
        type: 'missing_notes_in_chordpro',
        category: 'content-diff',
        message: '簡譜包含音符資訊，ChordPro 僅含和弦與歌詞，同步時將自動保留對應小節的簡譜音符',
        severity: 'info'
      });
    }

    // 4. 多聲部歌詞提示
    var hasMultiRowLyrics = safeMeasures.some(function (m) {
      return m && ((m.lyricText2 && m.lyricText2.trim()) || (m.lyricText3 && m.lyricText3.trim()) || (m.lyricText4 && m.lyricText4.trim()));
    });
    if (hasMultiRowLyrics) {
      conflicts.push({
        type: 'multi_track_lyrics',
        category: 'content-diff',
        message: '簡譜包含多行歌詞（第 2~4 行），ChordPro 僅編輯第 1 行歌詞',
        severity: 'info'
      });
    }

    return {
      hasConflict: conflicts.length > 0,
      type: primaryType,
      details: conflicts,
      conflicts: conflicts
    };
  }

  return {
    detectConflicts: detectConflicts,
    computeContentHash: computeContentHash
  };
});
