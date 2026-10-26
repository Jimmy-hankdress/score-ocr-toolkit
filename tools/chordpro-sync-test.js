/* tools/chordpro-sync-test.js
 * 完整驗收 ChordPro 解析器、匯出器、衝突偵測、版本追蹤與雙向同步引擎
 * 覆蓋報告 7.2 節所有測試案例：
 *   - P-001 ~ P-008 (ChordPro Parser 測試)
 *   - E-001 ~ E-004 (Score Studio 匯出與語法錯誤防護測試)
 *   - S-001 ~ S-006 (雙向同步、防呆鎖、衝突偵測、版本追蹤、錯誤回滾、<100ms 效能)
 */
'use strict';

const ChordProParser = require('../web/assets/chordpro-parser.js');
const SyncConflict = require('../web/assets/sync-conflict.js');
const SyncVersion = require('../web/assets/sync-version.js');
const SyncEngine = require('../web/assets/sync-engine.js');

let pass = 0, fail = 0;
function check(id, desc, cond, detail) {
  if (cond) {
    pass++;
    console.log(`  ✓ [${id}] ${desc}`);
  } else {
    fail++;
    console.log(`  ✗ [${id}] ${desc}${detail ? ' → ' + detail : ''}`);
  }
}

console.log('========== 7.2.1 ChordPro Parser 測試 (P-001 ~ P-008) ==========');

// P-001: 基本 metadata 解析 (#title: Test\n#key: C\n#bpm: 108)
{
  const meta = ChordProParser.parseMetadata('#title: Test\n#key: C\n#bpm: 108\n#time: 3/4');
  check('P-001', '基本 metadata 解析 (#title: Test\\n#key: C\\n#bpm: 108)',
    meta.title === 'Test' && meta.key === 'C' && meta.tempo === 108 && meta.timeSignature === '3/4',
    JSON.stringify(meta));
}

// P-002: 基本和弦 + 歌詞解析 ([C]歌詞)
{
  const m = ChordProParser.parseMeasures('[C]歌詞');
  check('P-002', '基本和弦 + 歌詞解析 ([C]歌詞)',
    m.length === 1 && m[0].chordText === 'C' && m[0].lyricText === '歌詞',
    JSON.stringify(m));
}

// P-003: 多和弦同小節 ([C][G]歌詞)
{
  const m = ChordProParser.parseMeasures('[C][G]歌詞');
  check('P-003', '多和弦同小節 ([C][G]歌詞)',
    m.length === 1 && m[0].chordText === 'C G' && m[0].lyricText === '歌詞',
    JSON.stringify(m));
}

// P-004: 段落標記解析 ([verse]\n[C]歌詞)
{
  const doc = ChordProParser.parseChordProToDoc('[verse]\n[C]歌詞');
  check('P-004', '段落標記解析 ([verse]\\n[C]歌詞)',
    doc.sections.length === 1 && doc.sections[0].type === 'verse' &&
    doc.sections[0].startMeasure === 0 && doc.measures.length === 1,
    JSON.stringify(doc));
}

// P-005: 空行處理 ([C]歌詞\n\n[G]歌詞)
{
  const m = ChordProParser.parseMeasures('[C]歌詞\n\n[G]歌詞');
  check('P-005', '空行處理 ([C]歌詞\\n\\n[G]歌詞) → 兩個 measure，無空 measure',
    m.length === 2 && m[0].chordText === 'C' && m[1].chordText === 'G',
    JSON.stringify(m));
}

// P-006: 特殊和弦 ([Cmaj7][Dm7-G7][C]歌詞)
{
  const m = ChordProParser.parseMeasures('[Cmaj7][Dm7-G7][C]歌詞');
  check('P-006', '特殊和弦 ([Cmaj7][Dm7-G7][C]歌詞)',
    m.length === 1 && m[0].chordText === 'Cmaj7 Dm7-G7 C' && m[0].lyricText === '歌詞',
    JSON.stringify(m));
}

// P-007: 長歌詞換行 ([C]這是一句很長的歌詞測試內容完整保留)
{
  const longLyric = '這是一句很長的歌詞測試內容完整保留不截斷';
  const m = ChordProParser.parseMeasures('[C]' + longLyric);
  check('P-007', '長歌詞單一小節完整保留',
    m.length === 1 && m[0].chordText === 'C' && m[0].lyricText === longLyric,
    JSON.stringify(m));
}

// P-008: 無和弦行 (純歌詞文字) & 空輸入 ("")
{
  const m = ChordProParser.parseMeasures('純歌詞文字');
  const emptyDoc = ChordProParser.parseChordProToDoc('');
  check('P-008', '無和弦行 (純歌詞文字) 與空輸入 ("")',
    m.length === 1 && m[0].chordText === '' && m[0].lyricText === '純歌詞文字' &&
    emptyDoc.measures.length === 0,
    JSON.stringify({ m, emptyDoc }));
}

console.log('\n========== 7.2.2 Score Studio 匯出與語法驗證測試 (E-001 ~ E-004) ==========');

// E-001: 基本匯出 + 未閉合括號驗證
{
  const out = ChordProParser.renderDocToChordPro({
    title: '匯出測試', key: 'C', timeSignature: '4/4', tempo: 90,
    measures: [{ number: 1, chordText: 'C', noteText: '', lyricText: '歌詞' }]
  });
  const vErr = ChordProParser.validateChordPro('[C 未閉合');
  check('E-001', '基本匯出 ([C]歌詞) 與未閉合括號驗證',
    out.includes('[C]歌詞') && vErr.valid === false && vErr.errors.some(e => e.code === 'E-001'),
    JSON.stringify({ out, vErr }));
}

// E-002: 多行匯出 + 空和弦括號驗證
{
  const out = ChordProParser.renderDocToChordPro({
    title: '多行測試', key: 'C', timeSignature: '4/4', tempo: 90,
    measures: [
      { number: 1, lineIndex: 0, chordText: 'C', noteText: '', lyricText: '第一行' },
      { number: 2, lineIndex: 1, chordText: 'G', noteText: '', lyricText: '第二行' },
      { number: 3, lineIndex: 2, chordText: 'Am', noteText: '', lyricText: '第三行' }
    ]
  });
  const vErr = ChordProParser.validateChordPro('[]空和弦');
  check('E-002', '多行匯出 (3 個 measures) 與空和弦 [] 驗證',
    out.includes('[C]第一行') && out.includes('[G]第二行') && out.includes('[Am]第三行') &&
    vErr.valid === false && vErr.errors.some(e => e.code === 'E-002'),
    JSON.stringify({ out, vErr }));
}

// E-003: 段落標記匯出 + 未閉合段落標記驗證
{
  const out = ChordProParser.renderDocToChordPro({
    title: '段落測試', key: 'C', timeSignature: '4/4', tempo: 90,
    sections: [{ type: 'verse', startMeasure: 0, endMeasure: 0 }],
    measures: [{ number: 1, lineIndex: 0, chordText: 'C', noteText: '', lyricText: '主歌歌詞' }]
  });
  const vErr = ChordProParser.validateChordPro('[verse');
  check('E-003', '段落標記匯出 ([verse]) 與未閉合段落標記驗證',
    out.includes('[verse]') && out.includes('[C]主歌歌詞') &&
    vErr.valid === false && vErr.errors.some(e => e.code === 'E-003'),
    JSON.stringify({ out, vErr }));
}

// E-004: 空 measure 處理 + 無效 metadata 驗證
{
  const out = ChordProParser.renderDocToChordPro({
    title: '空小節測試', key: 'C', timeSignature: '4/4', tempo: 90,
    measures: [{ number: 1, lineIndex: 0, chordText: '', noteText: '', lyricText: '' }]
  });
  const vErr = ChordProParser.validateChordPro('#title 缺少冒號');
  check('E-004', '空 measure 匯出處理與無效 metadata 驗證',
    typeof out === 'string' && out.includes('#title: 空小節測試') &&
    vErr.valid === false && vErr.errors.some(e => e.code === 'E-004'),
    JSON.stringify({ out, vErr }));
}

console.log('\n========== 7.2.3 同步功能測試 (S-001 ~ S-006) ==========');

// S-001: ChordPro → Score Studio
{
  const state = {
    doc: {
      title: '舊標題', key: 'C', tempo: 90, timeSignature: '4/4',
      measures: [{ number: 1, chordText: 'C', noteText: '1 2 3 4', lyricText: '舊歌詞' }]
    }
  };
  let rendered = false;
  const res = SyncEngine.syncFromChordProToScore(
    '#title: 新標題\n#key: G\n\n[G]新歌詞第一節\n[D]第二節歌詞',
    { state, renderScore: () => { rendered = true; } }
  );
  check('S-001', 'ChordPro → Score Studio 同步更新 state.doc.measures 並保留既有音符',
    res.ok === true && rendered === true &&
    state.doc.title === '新標題' && state.doc.key === 'G' &&
    state.doc.measures.length === 2 &&
    state.doc.measures[0].chordText === 'G' &&
    state.doc.measures[0].noteText === '1 2 3 4' &&
    state.doc.measures[0].lyricText === '新歌詞第一節',
    JSON.stringify(state.doc));
}

// S-002: Score Studio → ChordPro
{
  const fakeEditor = { value: '' };
  const doc = {
    title: '奇異恩典', key: 'G', tempo: 90, timeSignature: '3/4',
    measures: [
      { number: 1, lineIndex: 0, chordText: 'G', noteText: '5 1 3', lyricText: '奇 異 恩' },
      { number: 2, lineIndex: 0, chordText: 'C', noteText: '1 3 2', lyricText: '典 何 等' }
    ]
  };
  const text = SyncEngine.syncChordProEditor(doc, { editorEl: fakeEditor, force: true });
  check('S-002', 'Score Studio → ChordPro 自動更新 #chordpro-editor.value',
    fakeEditor.value.includes('#title: 奇異恩典') &&
    fakeEditor.value.includes('[G]') &&
    fakeEditor.value.includes('奇 異 恩') &&
    text === fakeEditor.value,
    fakeEditor.value);
}

// S-003: 同步延遲 (<100ms 內完成 50 小節同步)
{
  const measures50 = Array.from({ length: 50 }, (_, i) => ({
    number: i + 1,
    lineIndex: Math.floor(i / 4),
    linePosition: (i % 4) + 1,
    chordText: i % 2 === 0 ? 'C G' : 'Am F',
    noteText: '1 2 3 5',
    lyricText: `第${i + 1}小節歌詞`
  }));
  const state = {
    doc: { title: '五十小節效能測試', key: 'C', tempo: 120, timeSignature: '4/4', measures: measures50 }
  };
  const fakeEditor = { value: '' };
  const t0 = performance.now();
  const cpText = SyncEngine.syncChordProEditor(state.doc, { editorEl: fakeEditor, force: true });
  const res = SyncEngine.syncFromChordProToScore(cpText, { state });
  const elapsedMs = performance.now() - t0;
  check('S-003', `同步延遲 < 100ms (50 小節雙向同步實測 ${elapsedMs.toFixed(2)}ms)`,
    res.ok === true && state.doc.measures.length === 50 && elapsedMs < 100,
    `elapsed=${elapsedMs.toFixed(2)}ms`);
}

// S-004: 衝突偵測 (detectConflicts + 循環觸發防護 syncLock)
{
  const report = SyncConflict.detectConflicts(
    '[G]修改後歌詞\n[Am]新增第二小節',
    [{ number: 1, chordText: 'C', lyricText: '原本歌詞' }]
  );
  check('S-004', '衝突偵測 (detectConflicts 正確識別 measure_count_mismatch / chord_conflict / lyric_conflict)',
    report.hasConflict === true &&
    report.details.length === 3 &&
    report.details.some(c => c.type === 'measure_count_mismatch') &&
    report.details.some(c => c.type === 'chord_conflict') &&
    report.details.some(c => c.type === 'lyric_conflict'),
    JSON.stringify(report));
}

// S-005: 版本追蹤 (每次同步正確增加版本號並計算 FNV-1a hash)
{
  SyncVersion.resetVersionTracker();
  const v1 = SyncVersion.trackVersion('chordpro', '[C]第一版');
  const v2 = SyncVersion.trackVersion('chordpro', '[G]第二版');
  check('S-005', '版本追蹤 (trackVersion 版本遞增與 isStale 檢查)',
    v1.version === 1 && v2.version === 2 && v1.hash !== v2.hash &&
    SyncVersion.isStale('chordpro', v1.hash) === true &&
    SyncVersion.isStale('chordpro', v2.hash) === false,
    JSON.stringify({ v1, v2 }));
}

// S-006: 錯誤恢復 (Parser 驗證失敗時回滾，保留原有內容)
{
  const state = {
    doc: {
      title: '回滾測試', key: 'C', tempo: 90, timeSignature: '4/4',
      measures: [{ number: 1, chordText: 'Dm', noteText: '2 3 4 5', lyricText: '有效狀態' }]
    }
  };
  const res = SyncEngine.syncFromChordProToScore('[Dm 未閉合語法錯誤', { state });
  check('S-006', '錯誤恢復 (Parser 失敗時自動回滾並保留原有內容)',
    res.ok === false &&
    res.rolledBack === true &&
    state.doc.measures[0].chordText === 'Dm' &&
    state.doc.measures[0].lyricText === '有效狀態',
    JSON.stringify(res));
}

console.log(`\n===== ChordPro 同步測試結果：${pass} 項通過，${fail} 項失敗 =====`);
process.exit(fail > 0 ? 1 : 0);
