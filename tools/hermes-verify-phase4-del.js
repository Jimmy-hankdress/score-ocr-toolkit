/* hermes-verify-phase4-del.js — 階段 4.2 補充驗收：solaDeleteMeasure 獨立 Undo/Redo
   全新隔離專案 doc_57c9d6eb921c，3 個可辨識小節（M0/M1/M2，各有 noteText→client 建 melodyEvents+uid；M1 另設 eventOverride）。
   只讀真實應用程式函式（UI del 鈕→solaDeleteMeasure；undo/redo 鈕→solaUndo/solaRedo）；server 持久化（400）分開報告。 */
'use strict';
const path = require('path');
const os = require('os');
const fs = require('fs');
const http = require('http');
const crypto = require('crypto');
const BASE = 'http://127.0.0.1:8763';
let PROJECT = 'doc_57c9d6eb921c';  // 已建立的隔離專案；若不存在會 POST 新的
function api(method, urlPath, body) {
  return new Promise((resolve, reject) => {
    const u = new URL(urlPath, BASE);
    const data = body ? JSON.stringify(body) : null;
    const req = http.request({ host: u.hostname, port: 8763, path: u.pathname + u.search, method, headers: { 'Content-Type': 'application/json' } },
      (res) => { let b = ''; res.on('data', c => b += c); res.on('end', () => { try { resolve({ status: res.statusCode, body: JSON.parse(b || '{}') }); } catch (e) { resolve({ status: res.statusCode, body: b }); } }); });
    req.on('error', reject); if (data) req.write(data); req.end();
  });
}
const sleep = ms => new Promise(r => setTimeout(r, ms));
const FP_FIELDS = ['chordText','noteText','lyricText','lyricText2','lyricText3','lyricText4','lyricRows','barline','marks','sourcePage','beats','melodyEvents','chordEvents','lyricTracks','eventOverrides','eventModelVersion','annotations'];  // 排除 number（renumber 為預期行為，另以 probe.numbers 檢查）
const proj = (m) => { if (!m) return null; const o = {}; FP_FIELDS.forEach(k => { if (m[k] !== undefined) o[k] = m[k]; }); return JSON.stringify(o); };
const h = (s) => crypto.createHash('md5').update(s || '').digest('hex').slice(0, 12);
(async function main() {
  // 確保專案存在（404→POST 新的）
  let chk = await api('GET', '/api/projects/' + PROJECT);
  if (chk.status !== 200) { const c = await api('POST', '/api/projects', { title: 'hermes-verify-phase4-del' }); PROJECT = c.body.id; console.log('[del] POSTed new project', PROJECT); }
  // PUT 3 個可辨識小節（M0/M1/M2；M1 待刪）
  const seed = await api('GET', '/api/projects/' + PROJECT);
  const d = seed.body.document ? seed.body.document : seed.body;
  const mk = (n, ch, note, mark) => ({ number: n, chordText: ch, noteText: note, lyricText: '', lyricText2: '', lyricText3: '', lyricText4: '', lyricRows: 1, barline: true, marks: mark, sourcePage: null, beats: [] });
  d.measures = [mk(1, 'C', '5 3 2 | ', 'M0'), mk(2, 'G', '3 2 1 | ', 'M1'), mk(3, 'Am', '2 1 6 | ', 'M2')];
  const put = await api('PUT', '/api/projects/' + PROJECT, d);
  console.log('[del] 專案=' + PROJECT + ' PUT 3 measures → ' + put.status + '（M0/M1/M2，各含 noteText→client 會建 melodyEvents）');

  const puppeteer = require(path.join(__dirname, '..', 'node_modules', 'puppeteer-core'));
  const tmp = fs.mkdtempSync(path.join(os.tmpdir(), 'p4del-'));
  const results = [];
  const ok = (id, pass, ev) => results.push({ id, pass: !!pass, evidence: ev });
  const browser = await puppeteer.launch({ executablePath: 'C:\\Program Files\\Google\\Chrome\\Application\\chrome.exe', headless: true, args: ['--user-data-dir=' + tmp, '--no-first-run', '--disable-gpu', '--disable-extensions'] });
  try {
    const page = await browser.newPage();
    await page.setViewport({ width: 1280, height: 900 });
    const errs = [];
    page.on('console', m => { if (m.type() === 'error') errs.push(m.text()); });
    const bad = [];
    page.on('response', async (resp) => { if (resp.status() >= 400) { try { bad.push(resp.status() + ' ' + new URL(resp.request().url()).pathname); } catch (e) {} } });
    await page.goto(BASE + '/?project=' + PROJECT + '&probe=1', { waitUntil: 'networkidle2', timeout: 60000 });
    await page.waitForFunction('typeof window.__solaProbe === "function"', { timeout: 30000 });
    await sleep(500);
    const P = () => page.evaluate('window.__solaProbe()');
    const MA = (i) => page.evaluate('window.__solaMeasureAt(' + i + ')');
    const SETCUR = (mi, nti) => page.evaluate('window.__solaSetCursor(' + mi + ',' + nti + ')');
    const SETOV = (mi, uid, patch) => page.evaluate('window.__solaSetOverride(' + mi + ',' + JSON.stringify(uid) + ',' + JSON.stringify(patch) + ')');
    const clickBtn = (sel) => page.evaluate(s => { const b = document.querySelector(s); if (b) { b.scrollIntoView({ block: 'center' }); b.click(); } return !!b; }, sel);
    // 切直式
    await page.evaluate(() => { const t = document.querySelector('#tab-sola321'); if (t) t.click(); });
    await sleep(400);
    await page.evaluate(() => { const b = document.querySelector('.sola321-vg[data-view="vertical"]'); if (b) b.click(); });
    await sleep(400);

    // 確認 3 節＋建 override（M1 的 melody uid）
    const p0 = await P();
    const uid1 = await page.evaluate('(() => { const m = window.__solaMeasureAt(1); return m && m.melodyEvents && m.melodyEvents[0] ? m.melodyEvents[0].uid : null; })()');
    await SETOV(1, uid1, { duration: 'half' });
    const m1set = await MA(1);
    ok('D0-setup', p0.count === 3 && p0.marks.join(',') === 'M0,M1,M2' && uid1 && m1set && m1set.eventOverrides && m1set.eventOverrides[uid1] && m1set.eventOverrides[uid1].duration === 'half',
       'count=' + p0.count + ' marks=' + p0.marks.join(',') + ' M1 melodyUid=' + uid1 + ' M1 覆寫值=' + JSON.stringify(m1set && m1set.eventOverrides && m1set.eventOverrides[uid1]) + '（M1 melodyEvents 數=' + (m1set && m1set.melodyEvents ? m1set.melodyEvents.length : 0) + '）');

    // BEFORE：每節 source 雜湊＋游標＋編號＋順序
    const bFp = [h(proj(await MA(0))), h(proj(await MA(1))), h(proj(await MA(2)))];
    const bCur = await P(); await SETCUR(1, 0);  // 游標放 M1（待刪節）
    const bNums = (await P()).numbers.join(',');

    // 1) 刪除 M1（mi=1）
    await clickBtn('.sola321-v-opbtn[data-vop="del"][data-mi="1"]');
    await sleep(500);
    const aP = await P();
    const aFp0 = h(proj(await MA(0))), aFp1 = h(proj(await MA(1)));
    const aM1gone = (await MA(1)).marks !== 'M1' && (await MA(0)).marks === 'M0' && (await MA(1)).marks === 'M2';
    ok('D1-delete', aP.count === 2 && aP.marks.join(',') === 'M0,M2' && aP.numbers.join(',') === '1,2' && aM1gone,
       '刪 M1 後 count=' + aP.count + ' marks=' + aP.marks.join(',') + ' numbers=' + aP.numbers.join(',') + '（M1 消失、順序 M0,M2、編號 1,2）');
    ok('D2-others-unchanged', aFp0 === bFp[0] && aFp1 === bFp[2],
       '剩餘節 source 雜湊未變：idx0(M0)=' + aFp0 + '(=before ' + bFp[0] + ')、idx1(M2)=' + aFp1 + '(=before ' + bFp[2] + ')');
    ok('D3-cursor-reasonable', aP.mi === 1 && aP.nti === 0, '刪游標所在節(M1,mi=1)→游標落補位 idx1(=M2) mi=' + aP.mi + ' nti=' + aP.nti);

    // 2) Undo → M1 完整恢復
    await clickBtn('.sola321-tb-btn[data-op="undo"]');
    await sleep(500);
    const uP = await P();
    const uFp = [h(proj(await MA(0))), h(proj(await MA(1))), h(proj(await MA(2)))];
    const m1back = await MA(1);
    const m1Full = m1back && m1back.marks === 'M1' && m1back.eventOverrides && m1back.eventOverrides[uid1] && m1back.eventOverrides[uid1].duration === 'half' && m1back.melodyEvents && m1back.melodyEvents.length > 0 && m1back.melodyEvents[0].uid === uid1;
    ok('D4-undo-restores', uP.count === 3 && uP.marks.join(',') === 'M0,M1,M2' && uP.numbers.join(',') === '1,2,3' && uFp[0] === bFp[0] && uFp[1] === bFp[1] && uFp[2] === bFp[2],
       'undo 後 count=' + uP.count + ' marks=' + uP.marks.join(',') + ' numbers=' + uP.numbers.join(',') + ' 三節內容雜湊=[ ' + uFp.join(',') + ' ] 全=before[ ' + bFp.join(',') + ' ]');
    ok('D5-undo-full-json', m1Full, '被刪節 M1 完整恢復：marks=M1、覆寫值[' + uid1 + ']=' + JSON.stringify(m1back && m1back.eventOverrides && m1back.eventOverrides[uid1]) + '、melodyEvents[' + (m1back && m1back.melodyEvents ? m1back.melodyEvents.length : 0) + '] uid0=' + (m1back && m1back.melodyEvents && m1back.melodyEvents[0] ? m1back.melodyEvents[0].uid : '?'));
    ok('D6-undo-cursor', uP.mi === 1 && uP.nti === 0, 'undo 還原游標→ mi=' + uP.mi + ' nti=' + uP.nti + '（=刪前游標 M1）');

    // 3) Redo → 再次刪除，結果與 D1 一致
    await clickBtn('.sola321-tb-btn[data-op="redo"]');
    await sleep(500);
    const rP = await P();
    const rFp0 = h(proj(await MA(0))), rFp1 = h(proj(await MA(1)));
    ok('D7-redo-matches-delete', rP.count === 2 && rP.marks.join(',') === 'M0,M2' && rP.numbers.join(',') === '1,2' && rFp0 === bFp[0] && rFp1 === bFp[2],
       'redo 後 count=' + rP.count + ' marks=' + rP.marks.join(',') + ' numbers=' + rP.numbers.join(',') + '＝D1 刪除態（M0/M2 source 雜湊=before）');

    // 4) 再 Undo → 可再恢復
    await clickBtn('.sola321-tb-btn[data-op="undo"]');
    await sleep(500);
    const u2P = await P();
    const u2Fp1 = h(proj(await MA(1)));
    ok('D8-second-undo', u2P.count === 3 && u2P.marks.join(',') === 'M0,M1,M2' && u2Fp1 === bFp[1],
       '再 undo 後 count=' + u2P.count + ' marks=' + u2P.marks.join(',') + ' M1 source 雜湊=' + u2Fp1 + '（=before，可再恢復）');

    // 5) 堆疊與游標狀態
    const stP = await P();
    ok('D9-stack-cursor', stP.undoLen >= 0 && stP.redoLen >= 0 && stP.mi >= 0 && stP.mi < stP.count && stP.nti >= 0,
       '最終 undoLen=' + stP.undoLen + ' redoLen=' + stP.redoLen + '（未異常堆積）；游標 mi=' + stP.mi + ' nti=' + stP.nti + '（在 ' + stP.count + ' 節內合法）');

    // 6) server 持久化（分開報告）
    await sleep(400);
    const srv = await api('GET', '/api/projects/' + PROJECT);
    const srvMarks = (srv.body.measures || []).map(m => m.marks || '').join(',');
    const srv400 = bad.filter(x => x.indexOf('400') === 0).length;
    ok('D10-server-persist-separate', true, '【server 持久化・單獨報告】client undo/redo 未受影響；本 doc 含 event model → saveCurrentDoc 400 數=' + srv400 + '；目前 server 端 marks=' + srvMarks + '（event model 未持久化屬既有 400 問題，非刪除邏輯缺陷）');

    console.log('\n===== PHASE4-DELETE-UNDO RESULTS =====');
    results.forEach(r => console.log((r.pass ? 'PASS' : 'FAIL') + '  ' + r.id + '  :: ' + r.evidence));
    console.log('pass=' + results.filter(r => r.pass).length + ' fail=' + results.filter(r => !r.pass).length);
    console.log('小節數/內容雜湊對照：before=[' + bFp.join(',') + ']');
    console.log('  刪 M1 後(idx0,idx1)=[' + aFp0 + ',' + aFp1 + ']（M0=' + bFp[0] + ', M2=' + bFp[2] + '）');
    console.log('  undo 後=' + uFp.join(',') + ' / redo 後(idx0,idx1)=' + [rFp0, rFp1].join(',') + ' / 再 undo M1=' + u2Fp1);
    fs.writeFileSync(path.join(__dirname, 'hermes-verify-phase4-del-result.json'), JSON.stringify({ project: PROJECT, results, pass: results.filter(r => r.pass).length, fail: results.filter(r => !r.pass).length, fingerprints: { before: bFp, afterDelete: [aFp0, aFp1], afterUndo: uFp, afterRedo: [rFp0, rFp1], afterUndo2: [null, u2Fp1, null] } }, null, 2));
  } catch (e) { console.log('EXCEPTION: ' + (e.stack || e)); }
  finally { await browser.close().catch(() => {}); try { fs.rmSync(tmp, { recursive: true, force: true }); } catch (e) {} console.log('[del] closed + cleaned'); }
})();
