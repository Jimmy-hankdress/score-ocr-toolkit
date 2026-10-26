/* hermes-verify-phase4-b2.js — 第二批（上移／下移）隔離 headless 驗收
   對隔離專案 b3（doc_62821712c5e4）操作；注入 MVMARK 標記節（含 melodyEvents + eventOverrides）驗證 UID/覆寫值隨小節移動。
   依規格：只重排 array＋renumber、不重解析、游標跟隨、邊界 no-op（不入 undo/不清 redo）、undo/redo 還原。 */
'use strict';
const path = require('path');
const os = require('os');
const fs = require('fs');
const http = require('http');
const BASE = 'http://127.0.0.1:8763';
const PROJECT = 'doc_62821712c5e4';
const BASEDOC = path.join(__dirname, 'hermes-verify-phase4-b1-base.json');
const CHROME = 'C:\\Program Files\\Google\\Chrome\\Application\\chrome.exe';
function api(method, urlPath, body) {
  return new Promise((resolve, reject) => {
    const u = new URL(urlPath, BASE);
    const data = body ? JSON.stringify(body) : null;
    const req = http.request({ host: u.hostname, port: u.port || 8763, path: u.pathname + u.search, method, headers: { 'Content-Type': 'application/json' } },
      (res) => { let b = ''; res.on('data', c => b += c); res.on('end', () => { try { resolve(JSON.parse(b || '{}')); } catch (e) { resolve(b); } }); });
    req.on('error', reject); if (data) req.write(data); req.end();
  });
}
const sleep = ms => new Promise(r => setTimeout(r, ms));
async function vop(page, sel) {
  for (let i = 0; i < 6; i++) {
    const clicked = await page.evaluate(s => { const b = document.querySelector(s); if (!b) return false; b.scrollIntoView({ block: 'center' }); b.click(); return true; }, sel);
    if (clicked) { await sleep(550); return true; }
    await sleep(200);
  }
  return false;
}
(async function main() {
  const puppeteer = require(path.join(__dirname, '..', 'node_modules', 'puppeteer-core'));
  const tmp = fs.mkdtempSync(path.join(os.tmpdir(), 'p4b2-'));
  const results = [];
  const ok = (id, pass, ev) => results.push({ id, pass: !!pass, evidence: ev });

  // 準備：b3 = 6 節，marks 各異；MVMARK(idx2) 有 noteText（伺服器自然生成 uid，無孤兒覆寫）
  const base = JSON.parse(fs.readFileSync(BASEDOC, 'utf8'));
  base.title = base.title || 'hermes-verify-phase4-b3';
  ['A', 'B', 'MVMARK', 'D', 'E', 'F'].forEach((mk, i) => { if (base.measures[i]) base.measures[i].marks = mk; });
  const m2 = base.measures[2]; m2.noteText = '5 3 2 | ';
  delete m2.melodyEvents; delete m2.eventOverrides;
  await api('PUT', '/api/projects/' + PROJECT, base).then(r => console.log('[p4b2] 注入 marks + MVMARK noteText → measures=' + (r && r.measures ? r.measures.length : 'NA')));

  const browser = await puppeteer.launch({ executablePath: CHROME, headless: true, args: ['--user-data-dir=' + tmp, '--no-first-run', '--disable-gpu', '--disable-extensions'] });
  try {
    const page = await browser.newPage();
    await page.setViewport({ width: 1280, height: 900 });
    const errs = [];
    page.on('console', m => { if (m.type() === 'error') errs.push(m.text()); });
    page.on('pageerror', e => errs.push('PAGEERROR ' + e.message));
    await page.goto(BASE + '/?project=' + PROJECT + '&probe=1', { waitUntil: 'networkidle2', timeout: 60000 });
    await page.waitForFunction('typeof window.__solaProbe === "function"', { timeout: 30000 });
    await sleep(400);
    const P = () => page.evaluate('window.__solaProbe()');
    const MA = (i) => page.evaluate('window.__solaMeasureAt(' + i + ')');
    const SETCUR = (mi, nti) => page.evaluate('window.__solaSetCursor(' + mi + ',' + nti + ')');
    const SETOV = (mi, uid, patch) => page.evaluate('window.__solaSetOverride(' + mi + ',' + JSON.stringify(uid) + ',' + JSON.stringify(patch) + ')');
    const ensureSola = async () => { for (let i = 0; i < 6; i++) { if (await page.$('.sola321-vg[data-view="grid"]')) return; await page.evaluate(() => { const t = document.querySelector('#tab-sola321'); if (t) t.click(); }); await sleep(300); } };
    await ensureSola();
    await page.evaluate(() => { const b = document.querySelector('.sola321-vg[data-view="vertical"]'); if (b) b.click(); });
    await sleep(400);

    const p0 = await P();
    const mel0 = await MA(2);
    const melUid = mel0 && mel0.melodyEvents && mel0.melodyEvents[0] ? mel0.melodyEvents[0].uid : null;
    await SETOV(2, melUid, { duration: 'half' });  // 對得上 uid 的真實覆寫值（非孤兒）
    const m2ov = await MA(2);
    ok('M0-baseline', p0.count === 6 && p0.marks.join(',') === 'A,B,MVMARK,D,E,F' && melUid && m2ov && m2ov.eventOverrides && (m2ov.eventOverrides[melUid] ? m2ov.eventOverrides[melUid].duration === 'half' : false),
       'order=' + p0.marks.join(',') + ' MVMARK melodyUid=' + melUid + ' 覆寫值=' + JSON.stringify(m2ov && m2ov.eventOverrides && m2ov.eventOverrides[melUid]));

    // M1: 下移 idx2（MVMARK 節 2→3）
    await vop(page, '.sola321-v-opbtn[data-vop="down"][data-mi="2"]');
    const p1 = await P();
    const at3 = await MA(3), at2 = await MA(2);
    ok('M1-move-down', p1.numbers.join(',') === '1,2,3,4,5,6' && at3 && at3.marks === 'MVMARK' && (!at2 || at2.marks !== 'MVMARK'),
       '下移後 numbers=' + p1.numbers.join(',') + ' marks(idx3)=' + (at3 && at3.marks) + ' marks(idx2)=' + (at2 && at2.marks));

    // M2: 上移 idx3（MVMARK 節 3→2，還原）
    await vop(page, '.sola321-v-opbtn[data-vop="up"][data-mi="3"]');
    const p2 = await P();
    const at2b = await MA(2);
    ok('M2-move-up', p2.numbers.join(',') === '1,2,3,4,5,6' && at2b && at2b.marks === 'MVMARK',
       '上移後 numbers=' + p2.numbers.join(',') + ' marks(idx2)=' + (at2b && at2b.marks));

    // M3: 邊界 no-op（首節上移）→ 順序不變、undo/redo 不增清
    const before = await P();
    await vop(page, '.sola321-v-opbtn[data-vop="up"][data-mi="0"]');
    const after3 = await P();
    ok('M3-first-up-noop', after3.numbers.join(',') === before.numbers.join(',') && after3.undoLen === before.undoLen && after3.redoLen === before.redoLen,
       'pre undo/redo=' + before.undoLen + '/' + before.redoLen + ' post=' + after3.undoLen + '/' + after3.redoLen + ' numbers 不變=' + (after3.numbers.join(',') === before.numbers.join(',')));

    // M4: 邊界 no-op（末節下移）
    const b4 = await P();
    await vop(page, '.sola321-v-opbtn[data-vop="down"][data-mi="5"]');
    const a4 = await P();
    ok('M4-last-down-noop', a4.numbers.join(',') === b4.numbers.join(',') && a4.undoLen === b4.undoLen && a4.redoLen === b4.redoLen,
       'pre undo/redo=' + b4.undoLen + '/' + b4.redoLen + ' post=' + a4.undoLen + '/' + a4.redoLen + ' numbers 不變');

    // M5: 游標在被移小節（idx2）→ 下移後游標跟隨到 3
    await SETCUR(2, 0);
    await vop(page, '.sola321-v-opbtn[data-vop="down"][data-mi="2"]');
    const p5 = await P();
    ok('M5-cursor-on-moved', p5.mi === 3 && p5.nti === 0, '游標原 mi=2（被移節）→ 下移後 mi=' + p5.mi + ' nti=' + p5.nti + '（應跟隨到 3）');

    // M6: 游標在被頂小節（idx3）→ 上移 idx2 後游標跟隨到 2
    await SETCUR(3, 0);
    await vop(page, '.sola321-v-opbtn[data-vop="up"][data-mi="3"]');  // 移 idx3 上到 idx2；游標在 idx3（被移節）→ 跟隨到 2
    const p6 = await P();
    ok('M6-cursor-on-moved-up', p6.mi === 2 && p6.nti === 0, '游標原 mi=3（被移節）→ 上移後 mi=' + p6.mi + '（應跟隨到 2）');

    // M7: 游標在其他小節（idx0）→ 移 idx2/idx3 不影響
    await SETCUR(0, 0);
    await vop(page, '.sola321-v-opbtn[data-vop="down"][data-mi="2"]');
    const p7 = await P();
    ok('M7-cursor-on-other', p7.mi === 0, '游標 mi=0（非被移/被頂節）→ 移 idx2 後 mi=' + p7.mi + '（應不變）');

    // M8: 物件不變式 —— 小節移動前後整節物件（uid + 覆寫值 + 內容）完全相同（純搬移、未重建）
    const mvmPos = (await P()).marks.indexOf('MVMARK');
    const beforeM8 = await MA(mvmPos);
    const dirM8 = mvmPos < 5 ? 'down' : 'up';
    await vop(page, '.sola321-v-opbtn[data-vop="' + dirM8 + '"][data-mi="' + mvmPos + '"]');
    const mvmPos2 = (await P()).marks.indexOf('MVMARK');
    const afterM8 = await MA(mvmPos2);
    const stripNumber = (m) => { const c = m ? JSON.parse(JSON.stringify(m)) : null; if (c) delete c.number; return c; };  // number 因 renumber 應變、排除
    const sameM8 = beforeM8 && afterM8 && JSON.stringify(stripNumber(beforeM8)) === JSON.stringify(stripNumber(afterM8));
    ok('M8-uid-override-invariant', sameM8,
       'MVMARK idx ' + mvmPos + '→' + mvmPos2 + ' 前後 JSON ' + (sameM8 ? '完全相同（uids ' + JSON.stringify(beforeM8.melodyEvents.map(e => e.uid)) + '＋覆寫 ' + JSON.stringify(Object.keys(beforeM8.eventOverrides || {})) + ' 未重建）' : '不同'));

    // M9: 連續 2 移 + undo×2 逐步還原（用 marks 順序判定）
    const startOrder = (await P()).marks.join(',');
    await vop(page, '.sola321-v-opbtn[data-vop="down"][data-mi="1"]');
    await vop(page, '.sola321-v-opbtn[data-vop="up"][data-mi="5"]');
    const midOrder = (await P()).marks.join(',');
    await page.evaluate(() => { const b = document.querySelector('.sola321-tb-btn[data-op="undo"]'); if (b) b.click(); });
    await sleep(400);
    await page.evaluate(() => { const b = document.querySelector('.sola321-tb-btn[data-op="undo"]'); if (b) b.click(); });
    await sleep(400);
    const backOrder = (await P()).marks.join(',');
    ok('M9-undo-steps', startOrder !== midOrder && backOrder === startOrder, '起=' + startOrder + ' 兩移後=' + midOrder + ' undo×2 後=' + backOrder + '（應還原到起）');

    // M10: 存檔重載順序一致
    await sleep(500);
    const j10 = await api('GET', '/api/projects/' + PROJECT);
    const beforeReload = j10.measures.map(m => m.marks || '').join(',');
    await page.goto(BASE + '/?project=' + PROJECT + '&probe=1', { waitUntil: 'networkidle2', timeout: 60000 });
    await page.waitForFunction('typeof window.__solaProbe === "function"', { timeout: 30000 });
    await sleep(400);
    const marksAfter = [];
    for (let i = 0; i < (await P()).count; i++) { const mm = await MA(i); marksAfter.push(mm ? (mm.marks || '') : ''); }
    ok('M10-save-reload', marksAfter.join(',') === beforeReload, '重載前 marks=' + beforeReload + ' 重載後=' + marksAfter.join(',') + '（順序一致）');

    ok('M11-console', !errs.some(e => e.indexOf('|.svg') >= 0), 'console errors=' + (errs.length ? JSON.stringify(errs.slice(0, 4)) : '(none)') + '（400 數=' + errs.filter(e => e.indexOf('400') >= 0).length + '）');

    console.log('\n===== PHASE4-B2 RESULTS =====');
    results.forEach(r => console.log((r.pass ? 'PASS' : 'FAIL') + '  ' + r.id + '  :: ' + r.evidence));
    console.log('pass=' + results.filter(r => r.pass).length + ' fail=' + results.filter(r => !r.pass).length);
    fs.writeFileSync(path.join(__dirname, 'hermes-verify-phase4-b2-result.json'), JSON.stringify({ project: PROJECT, results, pass: results.filter(r => r.pass).length, fail: results.filter(r => !r.pass).length }, null, 2));
  } catch (e) { console.log('EXCEPTION: ' + (e.stack || e)); }
  finally { await browser.close().catch(() => {}); try { fs.rmSync(tmp, { recursive: true, force: true }); } catch (e) {} console.log('[p4b2] closed + cleaned'); }
})();
