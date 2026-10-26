/**
 * ChordPro Parser Module (web/assets/chordpro-parser.js)
 * 將 ChordPro 純文字解析為 ScoreDocument 結構，並提供格式驗證與雙向轉換輔助。
 * 同時相容瀏覽器全域 (window.ChordProParser) 與 Node.js CommonJS (module.exports)。
 */
(function (root, factory) {
  if (typeof module === 'object' && module.exports) {
    module.exports = factory();
  } else {
    var api = factory();
    root.ChordProParser = api;
    root.parseChordProToDoc = api.parseChordProToDoc;
    root.parseMeasures = api.parseMeasures;
    root.parseSections = api.parseSections;
    root.parseMetadata = api.parseMetadata;
    root.validateChordPro = api.validateChordPro;
    root.renderDocToChordPro = api.renderDocToChordPro;
  }
})(typeof self !== 'undefined' ? self : this, function () {
  'use strict';

  var SECTION_NAMES = [
    'verse', 'chorus', 'bridge', 'intro', 'outro',
    'solo', 'interlude', 'pre-chorus', 'prechorus', 'coda', 'tag'
  ];

  var ZH_SECTION_MAP = {
    '前奏': 'intro',
    '主歌': 'verse',
    '副歌': 'chorus',
    '間奏': 'bridge',
    '橋段': 'bridge',
    '尾奏': 'outro',
    'a段': 'A段',
    'b段': 'B段',
    'c段': 'C段',
    'd段': 'D段'
  };

  var KNOWN_HASH_DIRECTIVES = [
    'title', 't', 'subtitle', 'st', 'key', 'time', 'tempo', 'bpm',
    'capo', 'composer', 'lyricist', 'artist', 'author'
  ];

  function isSectionTag(tagContent) {
    var raw = String(tagContent || '').trim();
    var clean = raw.toLowerCase();
    if (!clean) return false;
    if (ZH_SECTION_MAP[clean]) return ZH_SECTION_MAP[clean];
    for (var i = 0; i < SECTION_NAMES.length; i++) {
      var s = SECTION_NAMES[i];
      if (clean === s || clean.indexOf(s + ' ') === 0 || clean.indexOf(s + '_') === 0 || clean.indexOf(s + '-') === 0 || clean.match(new RegExp('^' + s + '\\d+$'))) {
        return s === 'prechorus' ? 'pre-chorus' : s;
      }
    }
    return false;
  }

  function extractMeasureSectionTag(m, idx, sectionByStart) {
    if (!m) return '';
    if (m.section) {
      var mapped = isSectionTag(m.section);
      if (mapped) return mapped;
      if (/^[A-D]$/.test(String(m.section).trim())) return String(m.section).trim() + '段';
      return String(m.section).trim();
    }
    if (sectionByStart && sectionByStart[idx]) {
      return sectionByStart[idx];
    }
    if (m.marks) {
      var mks = String(m.marks).trim().split(/\s+/);
      for (var k = 0; k < mks.length; k++) {
        var sec = isSectionTag(mks[k]);
        if (sec) return sec;
      }
    }
    return '';
  }

  /**
   * 驗證 ChordPro 語法，檢查 E-001 ~ E-004 錯誤情況
   * @param {string} text
   * @returns {{ valid: boolean, errors: Array<{ code: string, line: number, message: string, raw: string }> }}
   */
  function validateChordPro(text) {
    var errors = [];
    if (typeof text !== 'string') {
      return { valid: false, errors: [{ code: 'E-000', line: 0, message: '輸入不是有效字串', raw: '' }] };
    }
    var lines = text.split(/\r?\n/);
    for (var i = 0; i < lines.length; i++) {
      var rawLine = lines[i];
      var trimmed = rawLine.trim();
      var lineNum = i + 1;
      if (!trimmed) continue;

      // 檢查 # 開頭指令 (E-004: 無效的 metadata 格式，例如 #title 缺少冒號；但排除 #1~#7 升記號簡譜音符行)
      if (trimmed.charAt(0) === '#' && !/^#[1-7]/.test(trimmed)) {
        var hashBody = trimmed.slice(1).trim();
        var colonIdx = hashBody.indexOf(':');
        if (colonIdx === -1) {
          var word = hashBody.split(/\s+/)[0].toLowerCase();
          if (KNOWN_HASH_DIRECTIVES.indexOf(word) !== -1) {
            errors.push({
              code: 'E-004',
              line: lineNum,
              message: '無效的 metadata 格式（缺少冒號）：' + trimmed,
              raw: rawLine
            });
          }
        }
        continue;
      }

      // 檢查大括號指令 {title: ...}
      if (trimmed.charAt(0) === '{' && trimmed.indexOf('}') === -1) {
        errors.push({
          code: 'E-004',
          line: lineNum,
          message: '未閉合的指令括號：' + trimmed,
          raw: rawLine
        });
        continue;
      }

      // 檢查方括號配對 (E-001: 未閉合和弦括號, E-002: 空和弦, E-003: 未閉合段落標記)
      var depth = 0;
      var openPos = -1;
      for (var c = 0; c < trimmed.length; c++) {
        var ch = trimmed.charAt(c);
        if (ch === '[') {
          if (depth > 0) {
            errors.push({
              code: 'E-001',
              line: lineNum,
              message: '未閉合的括號（重複開啟 [）：' + trimmed,
              raw: rawLine
            });
            break;
          }
          depth = 1;
          openPos = c;
        } else if (ch === ']') {
          if (depth === 0) {
            errors.push({
              code: 'E-001',
              line: lineNum,
              message: '多餘的閉合括號 ]：' + trimmed,
              raw: rawLine
            });
            break;
          }
          var inside = trimmed.slice(openPos + 1, c).trim();
          if (!inside) {
            errors.push({
              code: 'E-002',
              line: lineNum,
              message: '空和弦括號 []：' + trimmed,
              raw: rawLine
            });
          }
          depth = 0;
          openPos = -1;
        }
      }
      if (depth > 0) {
        var unclosedContent = trimmed.slice(openPos + 1).trim();
        var maybeSec = isSectionTag(unclosedContent);
        if (maybeSec && openPos === 0) {
          errors.push({
            code: 'E-003',
            line: lineNum,
            message: '無效的段落標記（未閉合）：' + trimmed,
            raw: rawLine
          });
        } else {
          errors.push({
            code: 'E-001',
            line: lineNum,
            message: '未閉合的和弦括號：' + trimmed,
            raw: rawLine
          });
        }
      }
    }
    return { valid: errors.length === 0, errors: errors };
  }

  /**
   * 解析 Metadata (#title:, #key:, #time:, #tempo: 與 {title:...} 等)
   * @param {string} text
   * @returns {{ title: string, key: string, timeSignature: string, tempo: number, lyricist?: string, composer?: string, capo?: number }}
   */
  function parseMetadata(text) {
    var meta = {
      title: 'Untitled',
      key: 'C',
      timeSignature: '4/4',
      tempo: 120
    };
    if (!text || typeof text !== 'string') return meta;

    var lines = text.split(/\r?\n/);
    for (var i = 0; i < lines.length; i++) {
      var line = lines[i].trim();
      if (!line) continue;

      var mHash = line.match(/^#([a-zA-Z0-9_-]+)\s*:\s*(.+)$/);
      var mBrace = line.match(/^\{([a-zA-Z0-9_-]+)\s*:\s*([^}]*)\}$/);
      var match = mHash || mBrace;
      if (match) {
        var k = match[1].toLowerCase();
        var v = match[2].trim();
        if (k === 'title' || k === 't') meta.title = v;
        else if (k === 'key' || k === 'k') meta.key = v;
        else if (k === 'time') meta.timeSignature = v;
        else if (k === 'tempo' || k === 'bpm') {
          var num = parseInt(v, 10);
          if (!isNaN(num) && num > 0) meta.tempo = num;
        } else if (k === 'lyricist') meta.lyricist = v;
        else if (k === 'composer' || k === 'artist' || k === 'author') meta.composer = v;
        else if (k === 'capo') {
          var cNum = parseInt(v, 10);
          if (!isNaN(cNum)) meta.capo = cNum;
        }
      }
    }
    return meta;
  }

  function isJianpuNoteSegment(str) {
    var s = String(str || '').trim();
    if (!s) return false;
    var cleaned = s.replace(/[\u0307\u0323]/g, '');
    if (!/[0-7]/.test(cleaned)) return false;
    return /^[0-7#b♯♭♮_.\-\s',/()=\^~]+$/.test(cleaned);
  }

  function parseSingleSegment(seg) {
    var chords = [];
    var inlineSection = null;
    var chordRegex = /\[([^\]]*)\]/g;
    var match;
    while ((match = chordRegex.exec(seg)) !== null) {
      var ch = match[1].trim();
      if (!ch) continue;
      var sec = isSectionTag(ch);
      if (sec) {
        inlineSection = sec;
      } else {
        chords.push(ch);
      }
    }
    var rem = seg.replace(/\[[^\]]*\]/g, '').trim();
    return {
      chordText: chords.join(' '),
      section: inlineSection,
      rem: rem
    };
  }

  function isChordOnlyLine(line) {
    if (!/\[[^\]]+\]/.test(line)) return false;
    var rawSegs = line.indexOf('|') !== -1 ? line.split('|') : [line];
    var hasAnyChord = false;
    for (var i = 0; i < rawSegs.length; i++) {
      var p = parseSingleSegment(rawSegs[i]);
      if (p.chordText) hasAnyChord = true;
      if (p.rem !== '' && p.rem !== '-') return false;
    }
    return hasAnyChord;
  }

  /**
   * 內部核心解析器：同時回傳 measures 與 sections
   */
  function parseBody(text, options) {
    options = options || {};
    var measures = [];
    var sections = [];
    var currentSection = null;
    if (!text || typeof text !== 'string') {
      return { measures: measures, sections: sections };
    }

    var lines = text.split(/\r?\n/);
    var pendingNoteMeasureStartIdx = -1;
    var pendingNoteMeasureCount = 0;
    var pendingChordSegments = null;

    function startNewSection(secType, atMeasureIdx) {
      if (!secType) return;
      if (currentSection) {
        currentSection.endMeasure = Math.max(currentSection.startMeasure, atMeasureIdx - 1);
        sections.push(currentSection);
      }
      currentSection = {
        type: secType,
        startMeasure: atMeasureIdx,
        endMeasure: atMeasureIdx
      };
    }

    function flushPendingChordSegments() {
      if (!pendingChordSegments || !pendingChordSegments.length) return;
      var startIdx = measures.length;
      for (var cIdx = 0; cIdx < pendingChordSegments.length; cIdx++) {
        var cs = pendingChordSegments[cIdx];
        if (cs.section) {
          startNewSection(cs.section, measures.length);
        }
        var mObj = {
          number: measures.length + 1,
          chordText: cs.chordText || '',
          noteText: '',
          lyricText: '',
          beats: []
        };
        if (currentSection && measures.length === currentSection.startMeasure) {
          mObj.section = currentSection.type;
        }
        measures.push(mObj);
      }
      pendingNoteMeasureStartIdx = startIdx;
      pendingNoteMeasureCount = pendingChordSegments.length;
      pendingChordSegments = null;
    }

    for (var i = 0; i < lines.length; i++) {
      var line = lines[i].trim();
      if (!line) {
        flushPendingChordSegments();
        pendingNoteMeasureStartIdx = -1;
        pendingNoteMeasureCount = 0;
        continue;
      }

      // 跳過 # metadata 或註解（但排除 #1~#7 開頭的升記號簡譜音符行，例如 #5 b6 1 5^ 6 1）
      if (line.charAt(0) === '#' && !/^#[1-7]/.test(line)) continue;

      // 檢查 {start_of_verse} / {sov} 等指令或 {title:...}
      if (line.charAt(0) === '{' && line.charAt(line.length - 1) === '}') {
        flushPendingChordSegments();
        var directive = line.slice(1, -1).trim();
        var dLower = directive.toLowerCase();
        if (dLower.indexOf(':') !== -1) {
          var parts = dLower.split(':');
          var dk = parts[0].trim();
          var dv = parts.slice(1).join(':').trim();
          if (dk === 'start_of_verse' || dk === 'sov') dLower = 'verse';
          else if (dk === 'start_of_chorus' || dk === 'soc') dLower = 'chorus';
          else if (dk === 'start_of_bridge' || dk === 'sob') dLower = 'bridge';
          else if (dk === 'comment' || dk === 'c') {
            var secFromComment = isSectionTag(dv);
            if (secFromComment) dLower = secFromComment;
            else continue;
          } else {
            continue;
          }
        }
        var mappedSec = isSectionTag(dLower);
        if (mappedSec) {
          startNewSection(mappedSec, measures.length);
          pendingNoteMeasureStartIdx = -1;
          pendingNoteMeasureCount = 0;
        }
        continue;
      }

      // 檢查獨立段落標記行：[verse], [chorus], [bridge], [intro], [outro]
      var secMatch = line.match(/^\[([^\]]+)\]$/);
      if (secMatch) {
        var secType = isSectionTag(secMatch[1]);
        if (secType) {
          flushPendingChordSegments();
          startNewSection(secType, measures.length);
          pendingNoteMeasureStartIdx = -1;
          pendingNoteMeasureCount = 0;
          continue;
        }
      }

      // 檢查是否為「獨立和弦行」（例如：[F] | - | [C] [F]），先暫存等待下一行簡譜音符行配對
      if (isChordOnlyLine(line)) {
        flushPendingChordSegments();
        var rawChordSegs = line.indexOf('|') !== -1 ? line.split('|') : [line];
        pendingChordSegments = [];
        for (var ci = 0; ci < rawChordSegs.length; ci++) {
          var cSeg = rawChordSegs[ci].trim();
          if (cSeg || rawChordSegs.length === 1) {
            pendingChordSegments.push(parseSingleSegment(cSeg));
          } else if (line.indexOf('|') !== -1) {
            pendingChordSegments.push({ chordText: '', section: null, rem: '' });
          }
        }
        pendingNoteMeasureStartIdx = -1;
        pendingNoteMeasureCount = 0;
        continue;
      }

      // 若前一行是「獨立和弦行」，而本行是純歌詞行（非簡譜音符行），則先把暫存和弦行轉成小節再填入歌詞
      var hasChordBracket = /\[[^\]]+\]/.test(line);
      if (pendingChordSegments && !hasChordBracket) {
        var checkSegs = line.indexOf('|') !== -1 ? line.split('|') : [line];
        var isNoteRow = checkSegs.some(function (seg) { return isJianpuNoteSegment(seg); });
        if (!isNoteRow) {
          flushPendingChordSegments();
        }
      }

      // 若前一行是「簡譜音符行」，且本行純為對應歌詞（不含和弦且非純簡譜），則配對填入歌詞
      if (pendingNoteMeasureStartIdx >= 0 && !hasChordBracket) {
        var lyrSegments = line.indexOf('|') !== -1 ? line.split('|') : [line];
        var allNotJianpu = lyrSegments.every(function (seg) { return !isJianpuNoteSegment(seg); });
        if (allNotJianpu && lyrSegments.length <= pendingNoteMeasureCount) {
          for (var k = 0; k < lyrSegments.length; k++) {
            var targetM = measures[pendingNoteMeasureStartIdx + k];
            if (targetM) {
              var cleanLyr = lyrSegments[k].replace(/^\s+|\s+$/g, '');
              targetM.lyricText = cleanLyr === '（無歌詞）' ? '' : cleanLyr;
            }
          }
          pendingNoteMeasureStartIdx = -1;
          pendingNoteMeasureCount = 0;
          continue;
        }
      }

      // 一般小節行（支援單行單小節，或以 | 分隔的多小節行）
      var rawSegments = line.indexOf('|') !== -1 ? line.split('|') : [line];
      var segments = [];
      for (var sIdx = 0; sIdx < rawSegments.length; sIdx++) {
        var segTrim = rawSegments[sIdx].trim();
        if (segTrim || rawSegments.length === 1) {
          segments.push(segTrim);
        }
      }

      var lineStartMeasureIdx = measures.length;
      var lineIsNoteLine = true;
      var totalCols = pendingChordSegments ? Math.max(segments.length, pendingChordSegments.length) : segments.length;

      for (var j = 0; j < totalCols; j++) {
        var segStr = j < segments.length ? segments[j] : '';
        var parsedSeg = parseSingleSegment(segStr);
        var pendChord = (pendingChordSegments && pendingChordSegments[j]) ? pendingChordSegments[j] : null;
        var mergedSec = (pendChord && pendChord.section) || parsedSeg.section;
        if (mergedSec) {
          startNewSection(mergedSec, measures.length);
        }
        var mergedChord = '';
        if (pendChord && pendChord.chordText && parsedSeg.chordText) {
          mergedChord = pendChord.chordText + ' ' + parsedSeg.chordText;
        } else if (pendChord && pendChord.chordText) {
          mergedChord = pendChord.chordText;
        } else {
          mergedChord = parsedSeg.chordText;
        }

        var remStr = parsedSeg.rem === '-' ? '' : parsedSeg.rem;
        var isNote = isJianpuNoteSegment(remStr) || (parsedSeg.rem === '-' && (!!pendChord || segments.length > 1));
        if (!isNote && remStr !== '') {
          lineIsNoteLine = false;
        }
        var mObj = {
          number: measures.length + 1,
          chordText: mergedChord,
          noteText: isNote ? remStr : '',
          lyricText: isNote ? '' : (remStr === '（無歌詞）' ? '' : remStr),
          beats: []
        };
        if (currentSection && measures.length === currentSection.startMeasure) {
          mObj.section = currentSection.type;
        }
        measures.push(mObj);
      }
      pendingChordSegments = null;

      if (lineIsNoteLine && totalCols > 0) {
        pendingNoteMeasureStartIdx = lineStartMeasureIdx;
        pendingNoteMeasureCount = totalCols;
      } else {
        pendingNoteMeasureStartIdx = -1;
        pendingNoteMeasureCount = 0;
      }
    }

    flushPendingChordSegments();

    if (currentSection) {
      currentSection.endMeasure = Math.max(currentSection.startMeasure, measures.length - 1);
      sections.push(currentSection);
    }

    // 若提供 existingDoc，保留未在純歌詞 ChordPro 中出現的既有 noteText 與其他欄位
    if (options.existingDoc && Array.isArray(options.existingDoc.measures)) {
      var oldMeasures = options.existingDoc.measures;
      for (var mi = 0; mi < measures.length; mi++) {
        var oldM = oldMeasures[mi];
        if (oldM) {
          if (!measures[mi].noteText && oldM.noteText) {
            measures[mi].noteText = oldM.noteText;
          }
          if (oldM.marks && !measures[mi].marks) {
            measures[mi].marks = oldM.marks;
          }
          if (oldM.barline !== undefined) {
            measures[mi].barline = oldM.barline;
          }
        }
      }
    }

    return { measures: measures, sections: sections };
  }

  /**
   * 解析小節列表
   * @param {string} text
   * @returns {Array<{ number: number, chordText: string, lyricText: string, noteText: string, beats: Array }>}
   */
  function parseMeasures(text, options) {
    return parseBody(text, options).measures;
  }

  /**
   * 解析段落標記列表
   * @param {string} text
   * @returns {Array<{ type: string, startMeasure: number, endMeasure: number }>}
   */
  function parseSections(text) {
    return parseBody(text).sections;
  }

  /**
   * 將 ChordPro 文字解析為完整 ScoreDocument 結構
   * @param {string} text
   * @param {object} [options]
   * @returns {{ title: string, key: string, timeSignature: string, tempo: number, measures: Array, sections: Array, errors?: Array }}
   */
  function parseChordProToDoc(text, options) {
    options = options || {};
    var validation = validateChordPro(text);
    if (options.strict && !validation.valid) {
      var err = new Error(validation.errors[0].message);
      err.code = validation.errors[0].code;
      err.errors = validation.errors;
      throw err;
    }

    var meta = parseMetadata(text);
    var body = parseBody(text, options);
    var result = {
      title: meta.title,
      key: meta.key,
      timeSignature: meta.timeSignature,
      tempo: meta.tempo,
      measures: body.measures,
      sections: body.sections
    };
    if (meta.lyricist !== undefined) result.lyricist = meta.lyricist;
    if (meta.composer !== undefined) result.composer = meta.composer;
    if (meta.capo !== undefined) result.capo = meta.capo;

    Object.defineProperty(result, 'validation', {
      value: validation,
      enumerable: false,
      configurable: true
    });
    return result;
  }

  /**
   * 將 ScoreDocument 渲染為 ChordPro 文字
   * @param {object} doc
   * @param {object} [options] - { mode: 'standard' | 'grid' }
   * @returns {string}
   */
  function renderDocToChordPro(doc, options) {
    if (!doc) return '';
    options = options || {};
    var lines = [];
    lines.push('#title: ' + (doc.title || 'Untitled'));
    lines.push('#key: ' + (doc.key || 'C'));
    lines.push('#time: ' + (doc.timeSignature || '4/4'));
    lines.push('#tempo: ' + (doc.tempo || 120));
    lines.push('');

    var measures = doc.measures || [];
    var sectionByStart = {};
    if (Array.isArray(doc.sections)) {
      for (var si = 0; si < doc.sections.length; si++) {
        var sec = doc.sections[si];
        if (sec && typeof sec.startMeasure === 'number') {
          sectionByStart[sec.startMeasure] = sec.type;
        }
      }
    }

    var hasAnyNotes = measures.some(function (m) {
      return m && m.noteText && String(m.noteText).trim().length > 0;
    });
    var useGridMode = options.mode === 'grid' || (options.mode !== 'line' && hasAnyNotes);

    if (!useGridMode) {
      // 標準單行一節模式（與 P-001 ~ P-008 完全對稱）
      for (var idx = 0; idx < measures.length; idx++) {
        var m = measures[idx];
        var secTag = extractMeasureSectionTag(m, idx, sectionByStart);
        if (secTag) {
          lines.push('[' + secTag + ']');
        }
        var chords = (m.chordText || '').trim().split(/\s+/).filter(Boolean);
        var chordPrefix = chords.map(function (c) { return '[' + c + ']'; }).join('');
        var lyr = (m.lyricText || '').trim();
        lines.push(chordPrefix + lyr);
      }
      return lines.join('\n');
    }

    // 含簡譜音符的多小節對齊模式：
    // 1. 段落名稱（[intro], [verse], [chorus]...）永遠獨立一行，若中間小節開啟新段落則自動換組
    // 2. 和弦獨立在「和弦行」（位於音符行上方，以 | 對齊小節），絕不混入音符行
    // 3. 音符獨立在「簡譜音符行」
    // 4. 歌詞獨立在「歌詞行」
    var maxPerRow = options.measuresPerLine || 4;
    var i = 0;
    while (i < measures.length) {
      var firstSec = extractMeasureSectionTag(measures[i], i, sectionByStart);
      if (firstSec) {
        lines.push('[' + firstSec + ']');
      }
      var slice = [measures[i]];
      var j = i + 1;
      while (j < measures.length && slice.length < maxPerRow) {
        var nextSec = extractMeasureSectionTag(measures[j], j, sectionByStart);
        if (nextSec) break; // 下一小節有新段落標記時，提前結束本行，讓新段落獨立成行
        slice.push(measures[j]);
        j++;
      }

      var hasSliceChords = slice.some(function (m) {
        return m && m.chordText && String(m.chordText).trim().length > 0;
      });
      if (hasSliceChords) {
        var chordLine = slice.map(function (m) {
          var chords = (m.chordText || '').trim().split(/\s+/).filter(Boolean);
          return chords.length ? chords.map(function (c) { return '[' + c + ']'; }).join(' ') : '-';
        }).join(' | ');
        lines.push(chordLine);
      }

      var noteLine = slice.map(function (m) {
        var cleanNote = String(m.noteText || '').replace(/[\u0307\u0323]/g, '').trim();
        return cleanNote || '-';
      }).join(' | ');

      var lyricLine = slice.map(function (m) {
        var lyr = String(m.lyricText || '').replace(/^\s+|\s+$/g, '');
        return lyr || '（無歌詞）';
      }).join(' | ');

      lines.push(noteLine);
      lines.push(lyricLine);
      lines.push('');
      i = j;
    }
    return lines.join('\n').replace(/\n+$/, '\n');
  }

  return {
    parseChordProToDoc: parseChordProToDoc,
    parseMeasures: parseMeasures,
    parseSections: parseSections,
    parseMetadata: parseMetadata,
    validateChordPro: validateChordPro,
    renderDocToChordPro: renderDocToChordPro
  };
});
