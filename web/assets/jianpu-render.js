/* 標準簡譜排版渲染
 *
 * 內部以 ASCII 速記保存與編輯（好打、好存、好比對）：
 *   5'   高八度      5''  高兩個八度
 *   5,   低八度      5,,  低兩個八度
 *   5_   八分音符    5__  十六分音符   5___ 三十二分音符
 *   5.   附點        -    增時線（延長一拍）    |  小節線    0  休止符
 *
 * 顯示時一律轉成**標準簡譜寫法**：
 *   高低音 → 數字上／下方的小圓點，兩點以上垂直疊放
 *   減時線 → 數字下方的橫線，相鄰音符自動連成一條共用底線
 *   附點   → 數字右側的小圓點
 *   增時線 → 數字右側的橫線
 *
 * 依據：
 *   https://zh.wikipedia.org/zh-tw/簡譜
 *   https://en.wikipedia.org/wiki/Numbered_musical_notation
 *     （"Where there is more than one dot above or below the number,
 *       the dots are vertically stacked"）
 */

const FULLWIDTH_DIGITS = '０１２３４５６７８９';

/** 把使用者可能貼進來的各種全形／相似字元正規化成內部 ASCII 速記。 */
function normalizeJianpu(text) {
  let out = String(text || '');
  for (let i = 0; i < 10; i += 1) {
    out = out.split(FULLWIDTH_DIGITS[i]).join(String(i));
  }
  return out
    .replace(/[－—–ー─━]/g, '-')     // 各種長橫線 → 增時線
    .replace(/[’‘ˊ˙･]/g, "'")        // 各種上標點 → 高八度
    .replace(/[，、]/g, ',')          // 全形逗號 → 低八度
    .replace(/[。・·．]/g, '.')       // 各種圓點 → 附點
    .replace(/[＿﹍﹏¯‾]/g, '_')      // 全形底線 → 減時線
    .replace(/[｜∣│]/g, '|')         // 全形豎線 → 小節線
    .replace(/\u3000/g, ' ')          // 全形空白
    .replace(/[ \t]+/g, ' ')
    .trim();
}

/** 解析單一 token。回傳 null 表示無法解析（原樣顯示，不偽造結果）。 */
function parseToken(raw) {
  const t = String(raw || '');
  if (!t) return null;
  if (/^\|+$/.test(t)) return { kind: 'bar' };
  if (/^-+$/.test(t)) return { kind: 'dash', count: t.length };
  const m = /^([0-7])('*|,*)(_*)(\.*)$/.exec(t);
  if (!m) return { kind: 'raw', text: t };
  const marks = m[2];
  return {
    kind: 'note',
    digit: m[1],
    up: marks.startsWith("'") ? marks.length : 0,
    down: marks.startsWith(',') ? marks.length : 0,
    under: m[3].length,
    aug: m[4].length,
  };
}

function parseJianpu(text) {
  return normalizeJianpu(text)
    .split(/\s+/)
    .filter(Boolean)
    .map(parseToken)
    .filter(Boolean);
}

function dotColumn(n, cls) {
  if (!n) return '';
  return `<span class="jp-${cls}">${'<i class="jp-o"></i>'.repeat(n)}</span>`;
}

/** 產生一組小節的標準簡譜 HTML。 */
function jianpuHtml(text) {
  const tokens = parseJianpu(text);
  if (!tokens.length) return '';
  const maxUnder = tokens.reduce((a, t) => Math.max(a, t.under || 0), 0);
  const parts = tokens.map((t) => {
    if (t.kind === 'bar') return shell('jp-bar', '│');
    if (t.kind === 'dash') return shell('jp-dash', '－'.repeat(t.count));
    if (t.kind === 'raw') {
      return shell('jp-unknown', escapeHtml(t.text), '無法解析的記號，已原樣保留');
    }
    const aug = t.aug ? '<i class="jp-o jp-aug"></i>'.repeat(t.aug) : '';
    return `<span class="jp jp-u${t.under}">`
      + `<span class="jp-up">${dotColumn(t.up, 'dots')}</span>`
      + `<span class="jp-mid"><span class="jp-num">${t.digit}</span>${aug}</span>`
      + `<span class="jp-dn">${dotColumn(t.down, 'dots')}</span>`
      + '</span>';
  });
  return `<span class="jp-row" style="--jp-under-room:${maxUnder * 3}px">${parts.join('')}</span>`;
}

/** 延長線、小節線也要包同樣的上／下層，才能與數字對齊。 */
function shell(cls, inner, title) {
  const tip = title ? ` title="${title}"` : '';
  return `<span class="jp ${cls}"${tip}>`
    + '<span class="jp-up"></span>'
    + `<span class="jp-mid">${inner}</span>`
    + '<span class="jp-dn"></span>'
    + '</span>';
}

function escapeHtml(s) {
  return String(s).replace(/[&<>"']/g, (c) =>
    ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));
}

window.Jianpu = { normalizeJianpu, parseToken, parseJianpu, jianpuHtml };
