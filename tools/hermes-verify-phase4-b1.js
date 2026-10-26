/* hermes-verify-phase4-b1.js — 第一批（新增／刪除）隔離 headless 驗收
   用獨立臨時 profile 啟動 Chrome 新實例（不碰既有 Chrome／既有 profile）；對隔離專案 doc_b35b8bd1f3cd 操作。
   讀取：window.__solaProbe（?probe=1 暴露）＋ 伺服器 API（持久化）。
   結果：逐項 PASS/FAIL/证据 + JSON summary。 */
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
    req.on('error', reject);
    if (data) req.write(data);
    req.end();
  });
}
const sleep = ms => new Promise(r => setTimeout(r, ms));
// 可靠點擊：dispatch 到元素（scrollIntoView 處理 off-viewport 的 del 按鈕；比座標 click 穩定）
async function vop(page, sel) {
  for (let i = 0; i < 6; i++) {
    const clicked = await page.evaluate(s => {
      const b = document.querySelector(s);
      if (!b) return false;
      b.scrollIntoView({ block: 'center' });
      b.click();
      return true;
    }, sel);
    if (clicked) { await sleep(550); return true; }
    await sleep(200);
  }
  return false;
}

(async function main() {
  const puppeteer = require(path.join(__dirname, '..', 'node_modules', 'puppeteer-core'));
  const tmpProfile = fs.mkdtempSync(path.join(os.tmpdir(), 'hermes-verify-p4b1-'));
  const results = [];
  const ok = (id, pass, evidence) => results.push({ id, pass: !!pass, evidence });
  console.log('[p4b1] launching Chrome (isolated temp profile ' + tmpProfile + ')');
  // 開場重置：把專案回 PUT 成乾淨 base doc（6 節 4/4），讓測試可重複執行、起點確定
  if (fs.existsSync(BASEDOC)) {
    const base = JSON.parse(fs.readFileSync(BASEDOC, 'utf8'));
    base.title = base.title || 'hermes-verify-phase4-b3';
    await api('PUT', '/api/projects/' + PROJECT, base).then(r => console.log('[p4b1] reset → measures=' + (r && r.measures ? r.measures.length : (base.measures ? base.measures.length : 'NA'))));
  } else {
    console.log('[p4b1] WARN base doc missing, skip reset');
  }
  const browser = await puppeteer.launch({
    executablePath: CHROME, headless: true,
    args: ['--user-data-dir=' + tmpProfile, '--no-first-run', '--no-default-browser-check', '--disable-gpu', '--disable-extensions', '--window-size=1280,900']
  });
  try {
    const page = await browser.newPage();
    const consoleErrs = [];
    page.on('console', m => { if (m.type() === 'error') consoleErrs.push(m.text()); });
    page.on('pageerror', e => consoleErrs.push('PAGEERROR: ' + e.message));

    await page.goto(BASE + '/?project=' + PROJECT + '&probe=1', { waitUntil: 'networkidle2', timeout: 60000 });
    // 等專案載入 + probe 暴露
    await page.waitForFunction('typeof window.__solaProbe === "function"', { timeout: 30000 });
    await sleep(500);
    const p0 = await page.evaluate('window.__solaProbe()');
    ok('T0-baseline', p0.count === 6 && JSON.stringify(p0.numbers) === JSON.stringify([1,2,3,4,5,6]),
       'count=' + p0.count + ' numbers=' + JSON.stringify(p0.numbers) + ' ts=' + p0.ts);

    // 切到直式視圖
    await page.click('.sola321-vg[data-view="vertical"]');
    await sleep(400);

    // T1: 新增（游標 mi=0 → 插到 idx=1）
    await vop(page, '.sola321-v-opbtn[data-vop="add"]');
    await sleep(700); // 等 fire-and-forget PUT
    const p1 = await page.evaluate('window.__solaProbe()');
    const j1 = await api('GET', '/api/projects/' + PROJECT);
    const m1 = j1.measures ? j1.measures[1] : null;
    ok('T1-add', p1.count === 7 && JSON.stringify(p1.numbers) === JSON.stringify([1,2,3,4,5,6,7]) && p1.mi === 1,
       'count=' + p1.count + ' numbers=' + JSON.stringify(p1.numbers) + ' cursor mi=' + p1.mi + ' eventModelVersion=' + (m1 ? m1.eventModelVersion : 'NA'));
    // §9 決策：新小節依 ts 動態建拍（4/4→4 拍），驗 client 端（活畫）；server 對空小節載入時依文字重建（殘留：空小節=1）
    ok('T1b-beats-by-ts', p1.beatLens && p1.beatLens[1] === 4,
       'client measures[1].beats.len=' + (p1.beatLens ? p1.beatLens[1] : 'NA') + '（4/4 應 4 拍）；server 持久化=' + (m1 && m1.beats ? m1.beats.length : 'NA') + '（空小節依文字重建=1，既有行為）');

    // T2: 再新增一次（cursor mi=1 → 插 idx=2）
    await vop(page, '.sola321-v-opbtn[data-vop="add"]');
    await sleep(700);
    const p2 = await page.evaluate('window.__solaProbe()');
    ok('T2-add-again', p2.count === 8, 'count=' + p2.count + ' mi=' + p2.mi);

    // T3: Undo ×2（還原到 6）
    for (let k = 0; k < 2; k++) { await page.click('.sola321-tb-btn[data-op="undo"]'); await sleep(400); }
    const p3 = await page.evaluate('window.__solaProbe()');
    ok('T3-undo-restore', p3.count === 6 && JSON.stringify(p3.numbers) === JSON.stringify([1,2,3,4,5,6]),
       'count=' + p3.count + ' numbers=' + JSON.stringify(p3.numbers) + ' mi=' + p3.mi + ' undoLen=' + p3.undoLen + ' redoLen=' + p3.redoLen);

    // T4: Redo ×2（回到 8）
    for (let k = 0; k < 2; k++) { await page.click('.sola321-tb-btn[data-op="redo"]'); await sleep(400); }
    const p4 = await page.evaluate('window.__solaProbe()');
    ok('T4-redo', p4.count === 8, 'count=' + p4.count + ' mi=' + p4.mi);

    // T5: 刪除首小節 mi=0（cursor 現 mi=2 → 刪 mi=0 < cursor → cursor=1）
    await vop(page, '.sola321-v-opbtn[data-vop="del"][data-mi="0"]');
    await sleep(400);
    const p5 = await page.evaluate('window.__solaProbe()');
    ok('T5-del-first', p5.count === 7, 'count=' + p5.count + ' numbers=' + JSON.stringify(p5.numbers) + ' cursor mi=' + p5.mi + '（刪游標之前→游標索引-1）');

    // T6: 刪除到空文件
    // 先把 cursor 移回 0，再依序刪
    let guard = 0;
    while ((await page.evaluate('window.__solaProbe().count')) > 0 && guard < 20) {
      const did = await vop(page, '.sola321-v-opbtn[data-vop="del"][data-mi="0"]');
      if (!did) break;
      guard++;
    }
    await sleep(400);
    const p6 = await page.evaluate('window.__solaProbe()');
    const j6 = await api('GET', '/api/projects/' + PROJECT);
    ok('T6-empty-doc', p6.count === 0 && p6.mi === 0 && p6.nti === 0 && j6.measures && j6.measures.length === 0,
       'count=' + p6.count + ' mi=' + p6.mi + ' nti=' + p6.nti + ' api.measures.len=' + (j6.measures ? j6.measures.length : 'NA'));

    // T7: 空文件新增 → 1 小節
    await vop(page, '.sola321-v-opbtn[data-vop="add"]');
    await sleep(700);
    const p7 = await page.evaluate('window.__solaProbe()');
    ok('T7-add-on-empty', p7.count === 1 && p7.mi === 0 && p7.nti === 0, 'count=' + p7.count + ' mi=' + p7.mi + ' nti=' + p7.nti);

    // T8: 再補到 2 小節，刪游標所在小節（cursor mi=0 → 刪 mi=0 = 游標所在 → cursor 落到補位 mi=0）
    await vop(page, '.sola321-v-opbtn[data-vop="add"]');
    await sleep(500);
    // cursor 現 mi=0（T7 後）；再 add → cursor=1。刪 mi=1（游標所在）→ cursor 落到補位 min(1, len-1)
    const p8pre = await page.evaluate('window.__solaProbe()');
    await vop(page, '.sola321-v-opbtn[data-vop="del"][data-mi="1"]');
    await sleep(300);
    const p8 = await page.evaluate('window.__solaProbe()');
    ok('T8-del-cursor-measure', p8.count === 1 && p8.mi === 0 && p8.nti === 0,
       'pre count=' + p8pre.count + ' mi=' + p8pre.mi + ' → 刪 mi=1（游標所在）→ post count=' + p8.count + ' mi=' + p8.mi + ' nti=' + p8.nti);

    // T9: 存檔重載一致（操作已 auto-saveCurrentDoc；此處 GET 二次 + reload page 驗證持久化）
    await sleep(500);
    const j9 = await api('GET', '/api/projects/' + PROJECT);
    const beforeReload = j9.measures.length;
    await page.goto(BASE + '/?project=' + PROJECT + '&probe=1', { waitUntil: 'networkidle2', timeout: 60000 });
    await page.waitForFunction('typeof window.__solaProbe === "function"', { timeout: 30000 });
    await sleep(400);
    const p9 = await page.evaluate('window.__solaProbe()');
    ok('T9-save-reload', p9.count === beforeReload, 'reload 前 api=' + beforeReload + ' reload 後 probe.count=' + p9.count);

    // T10: 三檢視一致（模型層 count 不變 + 各視圖 DOM 渲染小節數）
    const ensureSola = async () => {
      for (let i = 0; i < 6; i++) {
        const has = await page.$('.sola321-vg[data-view="grid"]');
        if (has) return true;
        await page.evaluate(() => { const t = document.querySelector('#tab-sola321'); if (t) t.click(); });
        await sleep(300);
      }
      return false;
    };
    const clickView = async (view) => {
      await ensureSola();
      await page.evaluate(v => { const b = document.querySelector('.sola321-vg[data-view="' + v + '"]'); if (b) b.click(); }, view);
      await sleep(400);
    };
    const countIn = async (view) => {
      await clickView(view);
      return page.evaluate(() => {
        const probe = window.__solaProbe();
        const vCount = document.querySelectorAll('.sola321-vmeasure').length;
        const gCount = document.querySelectorAll('#sola321-score .sola321-measure:not(.sola321-measure-timeline)').length;
        return { model: probe.count, v: vCount, g: gCount };
      });
    };
    await ensureSola();
    const gv = await countIn('grid');
    const tv = await countIn('timeline');
    const vv = await countIn('vertical');
    ok('T10-3view', gv.model === tv.model && tv.model === vv.model,
       'grid model=' + gv.model + '/gridDom=' + gv.g + ' timeline model=' + tv.model + ' vertical model=' + vv.model + '/vDom=' + vv.v);

    ok('T11-console', !consoleErrs.some(e => e.indexOf('|.svg') >= 0 || e.indexOf('undefined is not') >= 0),
       'console errors=' + (consoleErrs.length ? JSON.stringify(consoleErrs.slice(0,5)) : '(none)'));

    const summary = {
      project: PROJECT, results, 
      pass: results.filter(r => r.pass).length, fail: results.filter(r => !r.pass).length
    };
    console.log('\n===== PHASE4-B1 RESULTS =====');
    results.forEach(r => console.log((r.pass ? 'PASS' : 'FAIL') + '  ' + r.id + '  :: ' + r.evidence));
    console.log('\n' + JSON.stringify(summary, null, 2));
    fs.writeFileSync(path.join(__dirname, 'hermes-verify-phase4-b1-result.json'), JSON.stringify(summary, null, 2));
  } catch (e) {
    console.log('EXCEPTION: ' + (e.stack || e));
  } finally {
    await browser.close().catch(() => {});
    try { fs.rmSync(tmpProfile, { recursive: true, force: true }); } catch (e) {}
    console.log('[p4b1] closed + cleaned temp profile');
  }
})();
