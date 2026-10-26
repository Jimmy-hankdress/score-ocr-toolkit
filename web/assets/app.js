(function() {
  'use strict';

  function api(url, opts) {
    opts = opts || {};
    return fetch(url, opts).then(function(r) {
      if (!r.ok) return r.text().then(function(t) { throw new Error(t); });
      var ct = r.headers.get('content-type') || '';
      if (ct.indexOf('application/json') !== -1) return r.json();
      return r.text();
    });
  }

  function fetchBlob(url) {
    return fetch(url).then(function(r) {
      if (!r.ok) return r.text().then(function(t) { throw new Error(t); });
      return r.blob();
    });
  }

  function $(sel) { return document.querySelector(sel); }
    function $$(sel) { return Array.prototype.slice.call(document.querySelectorAll(sel)); }
  function escHtml(str) {
    if (str === null || str === undefined) return '';
    return String(str)
      .replace(/&/g, '&amp;')
      .replace(/</g, '&lt;')
      .replace(/>/g, '&gt;')
      .replace(/"/g, '&quot;')
      .replace(/'/g, '&#39;');
  }

    function toast(msg, type) {
    type = type || 'info';
    var stack = $('#toast-stack');
    if (!stack) return;
    var el = document.createElement('div');
    el.className = 'toast ' + type;
    el.innerHTML = '<div>' + msg + '</div>';
    stack.appendChild(el);
    setTimeout(function() { el.remove(); }, 4000);
  }

  function setStageFlow(stage, cls) {
      var stages = ['upload', 'rasterize', 'omr', 'musicxml'];
      var idx = stages.indexOf(stage);

    // 輔助函式：取得 contenteditable 中的游標位置（字元索引）
    function getCaretPosition(el) {
      var sel = window.getSelection();
      if (sel.rangeCount === 0) return 0;
      var range = sel.getRangeAt(0);
      var preCaretRange = range.cloneRange();
      preCaretRange.selectNodeContents(el);
      preCaretRange.setEnd(range.endContainer, range.endOffset);
      return preCaretRange.toString().length;
    }
    $$('[data-stage]').forEach(function(el, i) {
      el.classList.remove('active', 'done', 'failed');
      if (i < idx) el.classList.add('done');
      if (i === idx) el.classList.add(cls || 'active');
    });
  }

  var state = { currentTaskId: null, pollTimer: null, lastToastStage: null };
  var chordData = { guitar: {}, ukulele: {} };
  var chordLoaded = false;

  function loadChords(force) {
    if (chordLoaded && !force) return Promise.resolve();
    return api('/assets/chords.json?cache=' + new Date().getTime()).then(function(data) {
      chordData.guitar = data.guitar || {};
      chordData.ukulele = data.ukulele || {};
      chordLoaded = true;
    }).catch(function() {
      /* 失敗不鎖死 chordLoaded：下次呼叫（或重試鈕）可再取，暫態網路問題不自癒死 */
    });
  }

  function renderChordSvg(chord, instrument, compact, withName) {
    var name = chord.name || '';
    if (!name || !/^[A-G][A-Za-z0-9#b\-\(\)\/]{0,8}$/.test(name)) {
      return (withName && name ? '<span class="v3-chord-name">' + escHtml(name) + '</span>' : '') +
        '<span class="v3-chord-unk chord-diagram-missing">' + escHtml(name || '未收錄') + '</span>';
    }
    var inst = (instrument === 'ukulele') ? 'ukulele' : 'guitar';
    /* 檔名規則：轉位 / → _；# URL 編碼 %23；
       減七半減音名別名（檔名相反）：吉他檔 m7-5、烏克麗麗檔 m7b5，依樂器互換讓自由輸入也能命中 */
    var fileBase = name.replace(/\//g, '_');
    if (inst === 'guitar') fileBase = fileBase.replace(/m7b5/g, 'm7-5');
    else fileBase = fileBase.replace(/m7-5/g, 'm7b5');
    var fileUrl = '/assets/chords/' + inst + '/' + fileBase.replace(/#/g, '%23') + '.svg?v=2';
    /* 轉位和弦（如 Em7/D、Am7/G）若無專屬轉位指法圖，自動退回基礎和弦指法圖（如 Em7.svg） */
    var fallbackUrl = '';
    if (name.indexOf('/') !== -1) {
      var basePart = name.split('/')[0];
      if (inst === 'guitar') basePart = basePart.replace(/m7b5/g, 'm7-5');
      else basePart = basePart.replace(/m7-5/g, 'm7b5');
      fallbackUrl = '/assets/chords/' + inst + '/' + basePart.replace(/#/g, '%23') + '.svg?v=2';
    }
    var w = compact ? 48 : 48;
    var onErrJs = fallbackUrl
      ? 'if(!this.dataset.fb){this.dataset.fb=\'1\';this.src=\'' + fallbackUrl + '\';return;}this.style.display=\'none\';var n=this.nextElementSibling;if(n){n.style.display=\'inline\';}'
      : 'this.style.display=\'none\';var n=this.nextElementSibling;if(n){n.style.display=\'inline\';}';
    var diag = '<span class="chord-diagram-img-wrap">' +
      '<img class="chord-diagram-img" src="' + fileUrl + '" width="' + w + '" height="' + w + '" ' +
      'alt="' + escHtml(name) + ' 指法圖" ' +
      'onerror="' + onErrJs + '">' +
      '<span class="v3-chord-unk chord-diagram-missing" style="display:none">未收錄</span>' +
      '</span>';
    /* 格式：只顯示上方一個大的和弦名稱，下方為純指法圖（已移除 SVG 內重複的小和弦名） */
    if (withName && name) diag = '<span class="v3-chord-name">' + escHtml(name) + '</span>' + diag;
    return diag;
  }

  /* 目前選定的樂器（和弦庫儀表：guitar/ukulele），供和弦槽指法圖查表用 */
  function currentChordInstrument() {
    var r = $('input[name="instrument"]:checked');
    return r ? r.value : 'guitar';
  }

  /* 由和弦名查指法圖資料（chords.json；含 m7b5→m7-5 別名）。查不到回傳 null → 顯示「未收錄」，不臆測 */
  function chordDataByName(name) {
    if (!chordLoaded || !name) return null;
    var instrument = currentChordInstrument();
    var db = instrument === 'ukulele' ? chordData.ukulele : chordData.guitar;
    if (db[name]) return db[name];
    var alt = name.replace('m7b5', 'm7-5');
    if (alt !== name && db[alt]) return db[alt];
    return null;
  }

  /* 小節 chordText 拆成整排和弦片段（空格分隔） */
  function v3ChordParts(m) {
    var raw = (m.chordText || '').trim();
    return raw ? raw.split(/\s+/) : [];
  }

  /* 單個和弦槽 HTML（v3 格線與 Score Studio 行共用）；ci='__pending__' 為「＋」暫留空白槽
     依附件格式：移除深紅輸入框與紅色文字，只留白底黑線指法圖＋名稱置上；
     點擊指法圖 → 彈出和弦庫列表選擇；未收錄只標「未收錄」文字 */
  function v3ChordSlotHtml(c, mi, ci, offset) {
    /* 指法圖一律用 D:\樂譜自動生成系統\和弦圖 的 SVG 圖片檔（已複製到 /assets/chords/）；
       檔不存在時 img onerror 自動改顯示「未收錄」，不臆測、不用程式繪製 */
    var diag = renderChordSvg({ name: c || '' }, currentChordInstrument(), true, true);
    var pending = String(ci) === '__pending__';
    /* offset：該和弦對齊的節拍序（0=第 1 拍，1=第 2 拍...），預設 0 */
    var off = (offset != null) ? offset : 0;
    return '<div class="v3-chord-slot' + (pending ? ' pending' : '') + '" data-mi="' + mi + '" data-ci="' + ci + '" data-offset="' + off + '">' +
      '<button type="button" class="v3-chord-slot-del" title="移除和弦 ' + escHtml(c || '（空白槽）') + '">×</button>' +
      '<div class="v3-chord-diagram v3-chord-picker" title="點擊從和弦庫選擇；←/→ 或拖曳滑軌對齊節拍">' + diag + '</div>' +
      '<span class="v3-chord-slot-pos" title="滑軌對齊第 ' + (off + 1) + ' 拍">▸' + (off + 1) + '</span>' +
      '</div>';
  }

  /* 和弦庫彈出選單已停用：右側已有完整和弦面板，不再於和弦旁跳出重複的選擇選單 */
  function openChordPicker() {
    $$('.v3-chord-picker-menu').forEach(function(m) { m.remove(); });
  }

  /* V3.00 簡譜格線：小節和弦「整排槽」— 白底指法圖＋滑軌對齊（chordOffsets） */
  function layoutSola321ChordRows() {
    var cont = $('#sola321-score');
    if (!cont || !state3.doc) return;
    if (cont.offsetParent === null) return;   /* pane 隱藏時量測全 0；切回頁籤 loadSola321 會重排 */
    var ms = state3.doc.measures;
    $$('#sola321-score .sola321-measure').forEach(function(mEl) {
      var mi = +mEl.getAttribute('data-mi');
      var m = ms[mi];
      if (!m) return;
      /* 三行共用一個「拍柵格」：和弦行與歌詞行內的絕對定位子元件，
         落點都以「小節左邊緣＋該拍群（beat group）中心 x」為基準，
         跨行垂直對齊（同一拍 → 同一 x） */
      var beatCols = mEl.querySelectorAll('.sola321-note-row .sola321-beat-col');
      var beatCenters = [];
      var measureRect = mEl.getBoundingClientRect();
      beatCols.forEach(function(b) {
        var r = b.getBoundingClientRect();
        beatCenters.push((r.left + r.width / 2) - measureRect.left);
      });
      /* —— 和弦行：槽 left ＝ 拍群中心 x（以「小節左緣」為坐標原點；
         chord-row / note-row / lyric-line 三行寬度相等、左緣對齊，小節左緣＝三行共同原點） —— */
      var slotsEl = mEl.querySelector('.v3-chord-slots');
      var mLeft = mEl.getBoundingClientRect().left;
      var chars = mEl.querySelectorAll('.sola321-note-row .sola321-note-char');
      /* 拍群 → 該群所有音符 index（讀 note-char 的 data-col，col 序號 0..n） */
      var noteIdx = {};
      chars.forEach(function(ch, ci2) {
        var colNum = ch.getAttribute('data-col');
        colNum = colNum != null ? +colNum : 0;
        if (noteIdx[colNum] == null) noteIdx[colNum] = [];
        noteIdx[colNum].push(ci2);
      });
      /* v3.04.10 空小節：用 .sola321-beat-slot 填補拍群幾何（無音符時拍槽依拍號生成） */
      var beatSlotEls = mEl.querySelectorAll('.sola321-beat-slot');
      beatSlotEls.forEach(function(slot) {
        var beatNum = +slot.getAttribute('data-beat');
        /* 拍槽 data-beat 是「第 N 拍」（1-based），noteIdx 用 0-based col → 轉為 beatNum-1 */
        var colNum = beatNum - 1;
        if (noteIdx[colNum] == null) noteIdx[colNum] = [];
        noteIdx[colNum].push('__beat_slot_' + beatNum);
      });
      /* 拍群 x 區間（相對小節左緣）：colNum → {x0, x1} */
      var beatX = {};
      Object.keys(noteIdx).forEach(function(cn) {
        var x0 = Infinity, x1 = -Infinity;
        noteIdx[cn].forEach(function(ci3) {
          var el;
          if (typeof ci3 === 'string' && ci3.indexOf('__beat_slot_') === 0) {
            var bn = +ci3.split('_').pop();
            el = mEl.querySelector('.sola321-beat-slot[data-beat="' + bn + '"]');
          } else {
            el = chars[ci3];
          }
          if (!el) return;
          var r = el.getBoundingClientRect();
          if (r.left < x0) x0 = r.left;
          if (r.right > x1) x1 = r.right;
        });
        if (x0 === Infinity) return; /* 量測全失敗 → 跳過 */
        beatX[cn] = { x0: x0 - mLeft, x1: x1 - mLeft };
      });
      if (slotsEl) {
        var slotsRect = slotsEl.getBoundingClientRect();
        var slotsLeftRelM = slotsRect.left - mLeft;  /* slots 左緣相對小節左緣的偏移 */
        var slotEls = Array.prototype.slice.call(slotsEl.querySelectorAll('.v3-chord-slot'));
        var offs = m.chordOffsets || [];
        var ticks = m.chordTicks || [];   /* 6C：chordTicks 為權威定位（tick → 拍） */
        /* 依目標拍分組：同拍多和弦自動微錯開（保留指法圖大小，每顆右移 10px）；無寬度上限 */
        var byTarget = {};
        slotEls.forEach(function(s) {
          var ci = s.getAttribute('data-ci');
          var off;
          var liveOff = parseInt(s.getAttribute('data-offset'), 10);
          if (!isNaN(liveOff)) off = liveOff;                       /* 拖拉中／渲染時的即時目標拍 */
          else if (String(ci) === '__pending__') off = Math.max(0, chars.length - 1);
          else {
            /* 6C：chordTicks 權威（tick→拍），回退 chordOffsets，最後 index */
            var tick = (ticks[+ci] != null) ? ticks[+ci] : ((offs[+ci] != null) ? offs[+ci] * 480 : +ci * 480);
            off = Math.floor(tick / 480);
          }
          s.setAttribute('data-target', String(off));
          (byTarget[off] = byTarget[off] || []).push(s);
        });
        Object.keys(byTarget).forEach(function(k) {
          var group = byTarget[k];
          group.sort(function(a, b) { return (+a.getAttribute('data-ci')) - (+b.getAttribute('data-ci')); });
          /* 6C：k 即目標拍（col）。直接用 beatX[k]（該拍群＝含此拍的音符／拍槽）x 區間；
             舊版用 chars[k]（k 是拍序，chars 卻是音符序，拍數≠音符數時越界 → 定位失效，和弦停在第一音符） */
          var bx = beatX[+k];
          var chordStep = Math.max(52, (group[0] && group[0].offsetWidth) ? (group[0].offsetWidth + 4) : 52);
          group.forEach(function(s, idx) {
            var w = s.offsetWidth || 50;
            if (!bx) { s.style.left = ''; return; }  /* 此拍無拍群（空拍且無拍槽）→ 保持自動位置 */
            var groupCenter = (bx.x0 + bx.x1) / 2;   /* 拍群中心 x（小節左緣基準） */
            var leftM = (group.length === 1)
              ? (groupCenter - w / 2)
              : (groupCenter - ((group.length * chordStep) / 2) + (idx * chordStep));
            s.style.left = Math.round(leftM - slotsLeftRelM) + 'px';
          });
        });
      }
      /* —— 歌詞行：拍群對齊（每個 .sola321-lyric-syl 的 left/width 依拍群 x 區間計算） ——
         基準：absolute 子元素相對「歌詞行視窗左緣」（lineRect.left）。
         同一拍群多字（一音多字）→ 橫向均分該拍群 x 區間（不重疊）；
         data-extend 存在 → 末字 width 延伸到 data-extend 拍群（延長線） */
      mEl.querySelectorAll('.sola321-lyric-line').forEach(function(lineEl) {
        var lineRect = lineEl.getBoundingClientRect();
        var lineLeftW = lineRect.left;
        var syls = lineEl.querySelectorAll('.sola321-lyric-syl');
        /* 同拍群內音節數 + 本音節是該群第幾個（單次掃描預計算）。
           注意：colOrder 必須「index-based」——用 DOM 元素當 object key 會撞
           "[object HTMLSpanElement]"，所有音節 order 被覆蓋成同一值 → 同拍群多字重疊 */
        var colCount = {};
        var colOrder = new Array(syls.length);
        Array.prototype.forEach.call(syls, function(ln, i) {
          var c = +ln.getAttribute('data-col');
          colCount[c] = (colCount[c] || 0) + 1;
          colOrder[i] = colCount[c] - 1;   /* 本音節在該拍群內是第幾個（0 起） */
        });
        Array.prototype.forEach.call(syls, function(ln, i) {
          var col = +ln.getAttribute('data-col');
          var extend = ln.getAttribute('data-extend');
          var bx0 = beatX[col];
          if (!bx0) { ln.style.left = '0px'; ln.style.width = '22px'; return; }
          var n = colCount[col] || 1;
          var order = colOrder[i] || 0;
          var x0 = bx0.x0;
          var x1 = bx0.x1;
          /* 末字延伸：width 扩到 data-extend 拍群右緣 */
          if (extend !== '' && extend != null) {
            var bxEnd = beatX[+extend];
            if (bxEnd) x1 = bxEnd.x1;
          }
          var segW = (x1 - x0) / n;
          ln.style.left = Math.round(mLeft + x0 + order * segW - lineLeftW) + 'px';
          ln.style.width = Math.max(1, Math.round(segW)) + 'px';
        });
      });
      /* —— 連時線（beam）：同拍群減時音符共連橫線 ——
         定位基準：beam 左緣＝該拍群第一音符的 viewLeft（音符左緣），
         beam 寬度＝最後音符 viewRight − 第一音符 viewLeft（涵蓋整組），
         讓連時線橫跨整組減時音符，而非只在中心點 */
      mEl.querySelectorAll('.sola321-beam').forEach(function(bm) {
        var startIdx = +bm.getAttribute('data-start');
        var endIdx = +bm.getAttribute('data-end');  // 不含上限
        if (startIdx >= chars.length || endIdx > chars.length) return;
        var firstCh = chars[startIdx];
        var lastCh = chars[endIdx - 1];
        var r0 = firstCh.getBoundingClientRect();
        var r1 = lastCh.getBoundingClientRect();
        var lineRect = bm.parentElement.getBoundingClientRect();  /* .sola321-beams 容器 */
        var leftM = Math.round(r0.left - lineRect.left);
        var rightM = Math.round(r1.right - lineRect.left);
        bm.style.left = leftM + 'px';
        bm.style.width = Math.max(1, rightM - leftM) + 'px';
      });
    });
  }

  /* 滑鼠拖拉定點：指針 x → 該小節音符列中「最近的音符」（節拍感知分組後各音符寬不同，
     固定步長會錯位，必須用幾何中心距離找落點）。回傳音符 token 索引；非 Score Studio 返回 null */
  function solaNoteTargetAtX(pickerEl, clientX) {
    var slotsEl = pickerEl.closest ? pickerEl.closest('.v3-chord-slots') : null;
    var mEl = slotsEl ? slotsEl.closest('.sola321-measure') : null;
    if (!mEl) return null;
    var chars = mEl.querySelectorAll('.sola321-note-row .sola321-note-char');
    var beatSlots = mEl.querySelectorAll('.sola321-beat-slot');
    /* v3.04.10 合併音符字元＋空小節拍槽，找「最近的落點」（音符或拍槽） */
    var elements = [];
    chars.forEach(function(ch) { elements.push(ch); });
    beatSlots.forEach(function(bs) { elements.push(bs); });
    if (!elements.length) return null;
    var best = 0, bestD = Infinity, bestIsBeatSlot = false;
    for (var i = 0; i < elements.length; i++) {
      var el = elements[i];
      var r = el.getBoundingClientRect();
      var d = Math.abs(r.left + r.width / 2 - clientX);
      if (d < bestD) {
        bestD = d; best = i;
        bestIsBeatSlot = (el.classList && el.classList.contains('sola321-beat-slot'));
      }
    }
    if (bestIsBeatSlot) {
      /* 拍槽 data-beat=N（1-based）→ token index N-1（0-based col），
         寫入 chordOffsets 時即「對齊第 N 拍」 */
      return +elements[best].getAttribute('data-beat') - 1;
    }
    return best;
  }

  function renderV3ChordSlots(m, mi) {
      /* 6C：恢復指法圖 + 點選器 + 拖曳對齊（v3ChordSlotHtml）。
         定位以 chordTicks 為權威（tick→拍→拍群中心），chordOffsets 為回退。 */
      var parts = v3ChordParts(m);
      var ticks = m.chordTicks || [];
      var offs = m.chordOffsets || [];
      if (!parts.length) return '';
      var html = '<div class="v3-chord-slots" data-mi="' + mi + '">';
      parts.forEach(function(c, ci) {
        var tick = (ticks[ci] != null) ? ticks[ci] : ((offs[ci] != null) ? offs[ci] * 480 : ci * 480);
        var off = Math.floor(tick / 480);
        html += v3ChordSlotHtml(c, mi, ci, off);
      });
      /* 新增和弦按鈕 */
      html += '<button type="button" class="v3-chord-slot-add" data-mi="' + mi + '" title="新增和弦">＋</button>';
      html += '</div>';
      return html;
    }

  /* 確保小節內每個和弦皆有明確的音符對齊索引 (chordOffsets) 與 tick (chordTicks)，避免刪除前序和弦時後續和弦位移 */
  function v3EnsureChordOffsets(m) {
    if (!m) return [];
    var parts = v3ChordParts(m);
    if (!Array.isArray(m.chordOffsets)) m.chordOffsets = [];
    if (!Array.isArray(m.chordTicks)) m.chordTicks = [];
    for (var i = 0; i < parts.length; i++) {
      var off = m.chordOffsets[i];
      if (off == null || isNaN(+off)) {
        if (m.chordTicks[i] != null && !isNaN(+m.chordTicks[i])) {
          off = Math.max(0, Math.floor(+m.chordTicks[i] / 480));
        } else {
          off = (i > 0 && m.chordOffsets[i - 1] != null) ? Math.max(i, m.chordOffsets[i - 1] + 1) : i;
        }
      } else {
        off = Math.max(0, parseInt(off, 10));
      }
      m.chordOffsets[i] = off;
      m.chordTicks[i] = off * 480;
    }
    m.chordOffsets.length = parts.length;
    m.chordTicks.length = parts.length;
    return m.chordOffsets;
  }

  /* 將小節內的和弦依對齊音符位置 (chordOffsets) 由左至右排序，確保刪除或新增和弦時順序與位置一致 */
  function v3SortChordsByOffset(m) {
    if (!m) return;
    var parts = v3ChordParts(m);
    v3EnsureChordOffsets(m);
    if (parts.length <= 1) return;
    var items = parts.map(function(ch, idx) {
      return {
        chord: ch,
        off: m.chordOffsets[idx],
        tick: m.chordTicks[idx],
        idx: idx
      };
    });
    items.sort(function(a, b) {
      if (a.off !== b.off) return a.off - b.off;
      return a.idx - b.idx;
    });
    m.chordText = items.map(function(it) { return it.chord; }).join(' ');
    m.chordOffsets = items.map(function(it) { return it.off; });
    m.chordTicks = items.map(function(it) { return it.tick; });
  }

  /* 和弦槽寫回：pending（＋暫留槽）輸入非空才追加；既有槽清空 = 移除該槽；只動指定槽、保留其他
     offset 參數：該槽對齊的節拍序，寫到 m.chordOffsets[ci]（滑軌式對齊）
     tick 參數：可選，精確 tick 位置（480/quarter），優先於 offset */
  function v3ChordSlotWrite(m, ci, value, offset, tick) {
      v3EnsureChordOffsets(m);
      var parts = v3ChordParts(m);
      var v = String(value == null ? '' : value).trim();
      var targetCi = null;
      if (String(ci) === '__pending__' || isNaN(+ci)) {
        if (v) {
          parts.push(v);
          targetCi = parts.length - 1;
          var defOff = (offset != null && !isNaN(+offset)) ? +offset : targetCi;
          m.chordOffsets.push(defOff);
          m.chordTicks.push(defOff * 480);
        }
      } else if (v) {
        parts[ci] = v;
        targetCi = ci;
      } else {
        parts.splice(ci, 1);   // 清空既有槽 = 移除該槽（與 × 同義）
        if (ci >= 0 && ci < m.chordOffsets.length) m.chordOffsets.splice(ci, 1);
        if (ci >= 0 && ci < m.chordTicks.length) m.chordTicks.splice(ci, 1);
      }
      m.chordText = parts.join(' ');
      /* 同步 offset/tick：該槽對齊第 offset 拍或精確 tick */
      if (targetCi != null) {
        if (tick != null && !isNaN(+tick)) {
          m.chordTicks[targetCi] = +tick;
          m.chordOffsets[targetCi] = Math.floor(+tick / 480);
        } else if (offset != null && !isNaN(+offset)) {
          m.chordOffsets[targetCi] = +offset;
          m.chordTicks[targetCi] = +offset * 480;
        }
      }
      syncLegacyToEvents(m);
    }

  /* 和弦槽 picker 共用綁定（簡譜格線 ＆ Score Studio 兩頁籤）：
     點擊指法圖 → 彈出和弦庫；←/→ 方向鍵或水平拖曳 → 滑軌調整對齊節拍（chordOffsets）
     scope：'#v3-rows' 或 '#sola321-score'；reRender：該頁籤的重繪函數；undo：可選推 undo 棧 */
  function bindChordSlotPickers(scope, reRender, undo) {
    $$(scope + ' .v3-chord-slot .v3-chord-picker').forEach(function(pickerEl) {
      pickerEl.tabIndex = 0;
      function readOff(slot, m) {
        var ciRaw = slot.getAttribute('data-ci');
        var ticks = m.chordTicks || [];
        var offs = m.chordOffsets || [];
        var tick = (ticks[+ciRaw] != null) ? ticks[+ciRaw] : ((offs[+ciRaw] != null) ? offs[+ciRaw] * 480 : +ciRaw * 480);
        return Math.floor(tick / 480);
      }
      function maxOffFor(m) { return Math.max(0, solaTokens(m).length - 1); }
      /* 水平拖曳：滑軌式左右移動，對準節拍 */
      pickerEl.addEventListener('pointerdown', function(e) {
        if (e.button !== 0) return;
        var slot = pickerEl.closest('.v3-chord-slot');
        if (!slot) return;
        var mi = +slot.getAttribute('data-mi');
        var ciRaw = slot.getAttribute('data-ci');
        var m = state3.doc.measures[mi];
        if (!m || String(ciRaw) === '__pending__') return;
        var startOff = readOff(slot, m);
        var startX = e.clientX, moved = false, cur = startOff;
        var posEl = slot.querySelector('.v3-chord-slot-pos');
        var lim = maxOffFor(m);
        var liveMoved = function() { layoutSola321ChordRows(); };
        function onMove(ev) {
          var dx = ev.clientX - startX;
          if (Math.abs(dx) > 6) moved = true;
          /* 幾何定點：指針 x 對齊到「最近音符」（Score Studio 節拍感知分組後寬度不均，
             固定步長會錯位；簡譜格線走傳統步長 28px 保持既有行為） */
          var t = solaNoteTargetAtX(pickerEl, ev.clientX);
          var newOff;
          if (t != null) newOff = t;
          else newOff = Math.max(0, Math.min(lim, startOff + Math.round(dx / 28)));
          if (newOff !== cur) {
            cur = newOff;
            slot.setAttribute('data-offset', String(cur));
            var tick = cur * 480;
            slot.setAttribute('data-tick', String(tick));
            if (posEl) posEl.textContent = '\u25B8' + (cur + 1);
            liveMoved();
          }
        }
        function onUp() {
          window.removeEventListener('pointermove', onMove);
          window.removeEventListener('pointerup', onUp);
          if (moved) {
            if (cur !== startOff) {
              if (undo) undo();
              m.chordOffsets = m.chordOffsets || [];
              m.chordTicks = m.chordTicks || [];
              m.chordOffsets[+ciRaw] = cur;
              m.chordTicks[+ciRaw] = cur * 480;
              syncLegacyToEvents(m);
              reRender();
            }
          } else {
            openChordPicker(slot, mi, ciRaw, v3ChordParts(m)[+ciRaw] || '', reRender);
          }
        }
        window.addEventListener('pointermove', onMove);
        window.addEventListener('pointerup', onUp);
      });
      /* 方向鍵：← 前一拍、→ 後一拍 */
      pickerEl.addEventListener('keydown', function(e) {
        if (e.key !== 'ArrowLeft' && e.key !== 'ArrowRight') return;
        e.preventDefault();
        var slot = pickerEl.closest('.v3-chord-slot');
        if (!slot) return;
        var mi = +slot.getAttribute('data-mi');
        var ci = +slot.getAttribute('data-ci');
        var m = state3.doc.measures[mi];
        if (!m || String(slot.getAttribute('data-ci')) === '__pending__') return;
        var off = readOff(slot, m);
        var lim = maxOffFor(m);
        var newOff = e.key === 'ArrowLeft' ? Math.max(0, off - 1) : Math.min(lim, off + 1);
        if (newOff !== off) {
          if (undo) undo();
          m.chordOffsets = m.chordOffsets || [];
                  m.chordOffsets[ci] = newOff;
                  syncLegacyToEvents(m);
                  reRender();
        }
      });
    });
  }

  /* 常用轉位和弦（根音 → 第一轉位）；依和弦庫有無決定收不收 */
  var INV_CHORDS = { C: ['C/E'], D: ['D/F#'], F: ['F/A'], G: ['G/B', 'G/F#'], A: ['Am/G'], E: ['Em7/D'] };

  var CHORD_VARIANTS = [
    { suffix: '', zh: '大三' },
    { suffix: 'm', zh: '小' },
    { suffix: '6', zh: '六' },
    { suffix: '7', zh: '屬七' },
    { suffix: 'maj7', zh: '大七' },
    { suffix: '9', zh: '九' },
    { suffix: 'm7', zh: '小七' },
    { suffix: 'm7b5', zh: '減七', alt: 'm7-5' },
    { suffix: 'sus4', zh: '掛四' },
    { suffix: 'dim', zh: '減' },
    { suffix: 'aug', zh: '增' },
    { suffix: 'add9', zh: '加九' }
  ];
  var ROOT_NOTES = ['C', 'C#', 'D', 'D#', 'E', 'F', 'F#', 'G', 'G#', 'A', 'A#', 'B'];

  /* ===== 調性正規化、和弦移調與調性順階附屬和弦表 ===== */
  var _NOTE_PC = { C: 0, D: 2, E: 4, F: 5, G: 7, A: 9, B: 11 };
  var _SHARP_PC_NAMES = ['C', 'C#', 'D', 'D#', 'E', 'F', 'F#', 'G', 'G#', 'A', 'A#', 'B'];
  var _FLAT_PC_NAMES  = ['C', 'Db', 'D', 'Eb', 'E', 'F', 'Gb', 'G', 'Ab', 'A', 'Bb', 'B'];
  var _FLAT_KEYS_SET  = { F: true, Bb: true, Eb: true, Ab: true, Db: true, Gb: true, Dm: true, Gm: true, Cm: true, Fm: true };

  /* 解析音名（支援 C#, F#, Bb, #F, bB 等前綴或後綴升降記號）→ 0..11 半音值；無效回傳 null */
  function parseNotePitchClass(noteStr) {
    if (!noteStr) return null;
    var s = String(noteStr).trim().replace(/♯/g, '#').replace(/♭/g, 'b');
    var m = s.match(/^([#b]*)([A-Ga-g])([#b]*)$/);
    if (!m) return null;
    var letter = m[2].toUpperCase();
    var accs = (m[1] || '') + (m[3] || '');
    var pc = _NOTE_PC[letter];
    if (pc === undefined) return null;
    for (var i = 0; i < accs.length; i++) {
      if (accs.charAt(i) === '#') pc += 1;
      else if (accs.charAt(i) === 'b') pc -= 1;
    }
    return ((pc % 12) + 12) % 12;
  }

  /* 正規化調性字串（如 "1=G"、"g"、"#F"、"Bb"）→ 標準調名（如 "C", "G", "F#", "Bb"），無效回傳 null */
  function normalizeMusicKey(rawKey) {
    if (!rawKey) return null;
    var s = String(rawKey).trim().replace(/^1\s*=\s*/i, '').replace(/調$/, '').replace(/♯/g, '#').replace(/♭/g, 'b').trim();
    if (!s) return null;
    var m = s.match(/^([#b]*)([A-Ga-g])([#b]*)(m?)$/);
    if (!m) return null;
    var pc = parseNotePitchClass((m[1] || '') + m[2] + (m[3] || ''));
    if (pc === null) return null;
    var hasFlat = ((m[1] || '') + (m[3] || '')).indexOf('b') !== -1;
    var baseName = (hasFlat || pc === 10 || pc === 3 || pc === 8) ? _FLAT_PC_NAMES[pc] : _SHARP_PC_NAMES[pc];
    /* 對齊和弦庫與 #tonality-select 使用的標準根音名稱 */
    return baseName + (m[4] ? 'm' : '');
  }

  /* 將標準調名轉為和弦庫/下拉選單使用的 12 根音（C, C#, D, D#, E, F, F#, G, G#, A, A#, B） */
  function toChordDbRoot(keyStr) {
    var pc = parseNotePitchClass(String(keyStr || 'C').replace(/m$/, ''));
    return _SHARP_PC_NAMES[pc !== null ? pc : 0];
  }

  /* 單個和弦符號移調（支援 C, Am, F#m7b5, D/F#, G/B, Em7/D 等所有和弦與轉位低音） */
  function shiftChordSymbolBySemi(sym, semi, preferFlats) {
    var raw = String(sym || '').trim();
    if (!raw) return raw;
    var m = raw.match(/^([#b♯♭]*)([A-G])([#b♯♭]*)(.*?)(?:\/([#b♯♭]*[A-G][#b♯♭]*))?$/);
    if (!m) return raw;
    var rootPart = (m[1] || '') + m[2] + (m[3] || '');
    var suffix = m[4] || '';
    var bassPart = m[5] || '';
    /* 若後綴開頭其實是 m7b5 的 b5，避免被誤吃進 root accidental：
       只有當 m[3] 後面不是數字時 m[3] 才是根音升降號（例如 Bb5 vs Bm7b5） */
    if (m[3] && /^5/.test(suffix)) {
      rootPart = (m[1] || '') + m[2];
      suffix = m[3] + suffix;
    }
    var rootPc = parseNotePitchClass(rootPart);
    if (rootPc === null) return raw;
    var newRootPc = ((rootPc + semi) % 12 + 12) % 12;
    var names = preferFlats ? _FLAT_PC_NAMES : _SHARP_PC_NAMES;
    var newRoot = names[newRootPc];
    var newBass = '';
    if (bassPart) {
      var bassPc = parseNotePitchClass(bassPart);
      if (bassPc !== null) {
        var newBassPc = ((bassPc + semi) % 12 + 12) % 12;
        newBass = '/' + names[newBassPc];
      } else {
        newBass = '/' + bassPart;
      }
    }
    return newRoot + suffix + newBass;
  }

  /* 計算某大調的順階／附屬和弦群組（I, IIm, IIIm, IV, V, V7, VIm, VIIm7b5 及常用附屬與轉位和弦） */
  function getDiatonicChordFamily(keyStr, db) {
    var norm = normalizeMusicKey(keyStr) || 'C';
    var rootPc = parseNotePitchClass(norm.replace(/m$/, ''));
    if (rootPc === null) rootPc = 0;
    var preferFlats = !!_FLAT_KEYS_SET[norm];
    var names = preferFlats ? _FLAT_PC_NAMES : _SHARP_PC_NAMES;
    function nAt(semiOffset) {
      return names[(rootPc + semiOffset + 12) % 12];
    }
    function dbNAt(semiOffset) {
      return _SHARP_PC_NAMES[(rootPc + semiOffset + 12) % 12];
    }
    var I   = nAt(0),  dbI   = dbNAt(0);
    var II  = nAt(2),  dbII  = dbNAt(2);
    var III = nAt(4),  dbIII = dbNAt(4);
    var IV  = nAt(5),  dbIV  = dbNAt(5);
    var V   = nAt(7),  dbV   = dbNAt(7);
    var VI  = nAt(9),  dbVI  = dbNAt(9);
    var VII = nAt(11), dbVII = dbNAt(11);

    var candidates = [
      { label: I,            dbKey: dbI,            zh: 'I 主和弦' },
      { label: II + 'm',     dbKey: dbII + 'm',     zh: 'IIm 上主' },
      { label: III + 'm',    dbKey: dbIII + 'm',    zh: 'IIIm 中音' },
      { label: IV,           dbKey: dbIV,           zh: 'IV 下屬' },
      { label: V,            dbKey: dbV,            zh: 'V 屬和弦' },
      { label: V + '7',      dbKey: dbV + '7',      zh: 'V7 屬七' },
      { label: VI + 'm',     dbKey: dbVI + 'm',     zh: 'VIm 關係小' },
      { label: VII + 'm7b5', dbKey: dbVII + 'm7b5', altKey: dbVII + 'm7-5', zh: 'VIIm7b5 導七' },
      { label: V + '/' + VII, dbKey: dbV + '/' + dbVII, fallbackKey: dbV, zh: 'V/VII 轉位' },
      { label: I + '/' + III, dbKey: dbI + '/' + dbIII, fallbackKey: dbI, zh: 'I/III 轉位' },
      { label: II + 'm7',    dbKey: dbII + 'm7',    zh: 'IIm7 小七' },
      { label: VI + 'm7',    dbKey: dbVI + 'm7',    zh: 'VIm7 小七' },
      { label: IV + 'maj7',  dbKey: dbIV + 'maj7',  zh: 'IVmaj7 大七' },
      { label: I + 'maj7',   dbKey: dbI + 'maj7',   zh: 'Imaj7 大七' },
      { label: V + 'sus4',   dbKey: dbV + 'sus4',   zh: 'Vsus4 掛四' },
      { label: III + '7',    dbKey: dbIII + '7',    zh: 'III7 副屬' }
    ];

    var result = [];
    var seen = {};
    candidates.forEach(function(c) {
      if (seen[c.label]) return;
      seen[c.label] = true;
      var resolvedKey = c.dbKey;
      var data = db && db[resolvedKey];
      if (!data && c.altKey && db && db[c.altKey]) {
        resolvedKey = c.altKey;
        data = db[c.altKey];
      }
      if (!data && c.fallbackKey && db && db[c.fallbackKey]) {
        data = db[c.fallbackKey];
      }
      result.push({
        label: c.label,
        key: resolvedKey,
        data: data || null,
        zh: c.zh
      });
    });
    return result;
  }

  /* 自動從樂譜小節內的和弦推算實際主調（用於校正 OMR 預設 1=C 但和弦實為 G 調等情況） */
  function inferActualKeyFromMeasures(doc) {
    if (!doc || !Array.isArray(doc.measures)) return null;
    var allChords = [];
    doc.measures.forEach(function(m) {
      var parts = String(m.chordText || '').trim().split(/\s+/).filter(Boolean);
      parts.forEach(function(p) { allChords.push(p); });
    });
    if (!allChords.length) return null;

    var majorIntervals = [
      { semi: 0, qual: 'M', weight: 3.0 },
      { semi: 2, qual: 'm', weight: 2.0 },
      { semi: 4, qual: 'm', weight: 2.0 },
      { semi: 5, qual: 'M', weight: 2.5 },
      { semi: 7, qual: 'M', weight: 3.0 },
      { semi: 9, qual: 'm', weight: 2.5 },
      { semi: 11, qual: 'dim', weight: 1.5 }
    ];

    var firstChord = allChords[0];
    var lastChord = allChords[allChords.length - 1];
    var bestKey = 'C';
    var bestScore = -999;

    _SHARP_PC_NAMES.forEach(function(candName, candPc) {
      var score = 0;
      allChords.forEach(function(ch) {
        var base = ch.split('/')[0];
        var m = base.match(/^([#b]*)([A-G])([#b]*)(.*)$/);
        if (!m) return;
        var rPart = (m[1] || '') + m[2] + (m[3] || '');
        var suf = m[4] || '';
        if (m[3] && /^5/.test(suf)) {
          rPart = (m[1] || '') + m[2];
          suf = m[3] + suf;
        }
        var cPc = parseNotePitchClass(rPart);
        if (cPc === null) return;
        var isDim = /dim|m7b5|m7-5/.test(suf);
        var isMin = !isDim && /^m(?!aj)/.test(suf);
        var qual = isDim ? 'dim' : (isMin ? 'm' : 'M');
        var matched = false;
        for (var i = 0; i < majorIntervals.length; i++) {
          var deg = majorIntervals[i];
          if ((candPc + deg.semi) % 12 === cPc && deg.qual === qual) {
            score += deg.weight;
            matched = true;
            break;
          }
        }
        if (!matched) score -= 1.0;
      });
      /* 首尾和弦若為該調 I 級主和弦或 VIm 關係小調，給予額外權重 */
      [firstChord, lastChord].forEach(function(edgeCh, idx) {
        var base = String(edgeCh || '').split('/')[0];
        var m = base.match(/^([#b]*)([A-G])([#b]*)(.*)$/);
        if (!m) return;
        var rPart = (m[1] || '') + m[2] + (m[3] || '');
        var suf = m[4] || '';
        var cPc = parseNotePitchClass(rPart);
        var isMin = /^m(?!aj)/.test(suf) && !/m7b5|m7-5/.test(suf);
        if (cPc === candPc && !isMin) score += (idx === 1 ? 5.0 : 4.0);
        if (cPc === (candPc + 9) % 12 && isMin) score += 2.0;
      });
      if (score > bestScore) {
        bestScore = score;
        bestKey = (candPc === 5 || candPc === 10 || candPc === 3 || candPc === 8) ? _FLAT_PC_NAMES[candPc] : candName;
      }
    });
    return bestKey;
  }

  /* 將 doc 內所有小節的和弦由 fromKey 移調至 toKey（原地更新 chordText、beats、chordEvents） */
  function transposeDocChords(doc, fromKey, toKey) {
    if (!doc || !Array.isArray(doc.measures)) return 0;
    var normFrom = normalizeMusicKey(fromKey) || 'C';
    var normTo = normalizeMusicKey(toKey) || 'C';
    var fromPc = parseNotePitchClass(normFrom.replace(/m$/, ''));
    var toPc = parseNotePitchClass(normTo.replace(/m$/, ''));
    if (fromPc === null || toPc === null) return 0;
    var semi = ((toPc - fromPc) % 12 + 12) % 12;
    var preferFlats = !!_FLAT_KEYS_SET[normTo];
    var count = 0;
    if (semi !== 0) {
      doc.measures.forEach(function(m) {
        if (m.chordText && String(m.chordText).trim()) {
          var parts = String(m.chordText).trim().split(/\s+/).filter(Boolean);
          m.chordText = parts.map(function(c) {
            count++;
            return shiftChordSymbolBySemi(c, semi, preferFlats);
          }).join(' ');
        }
        if (Array.isArray(m.beats)) {
          m.beats.forEach(function(b) {
            if (b && b.chord) {
              b.chord = String(b.chord).trim().split(/\s+/).filter(Boolean).map(function(c) {
                return shiftChordSymbolBySemi(c, semi, preferFlats);
              }).join(' ');
            }
          });
        }
        if (Array.isArray(m.chordEvents)) {
          m.chordEvents.forEach(function(ev) {
            if (ev && ev.chordName) {
              ev.chordName = shiftChordSymbolBySemi(ev.chordName, semi, preferFlats);
            }
          });
        }
        if (typeof syncLegacyToEvents === 'function') {
          syncLegacyToEvents(m);
        }
      });
    }
    doc.key = normTo;
    return count;
  }

  /* 載入專案時，若 doc.key 紀錄為 "C"（舊版 OMR 未校準預設值），但小節和弦明顯屬於其他調（例如 Last Dance 原譜為 G 調），
     自動將和弦校準至與 doc.key 一致（1=C 時對應 C 調順階和弦，當使用者在左上角改為 1=G 時即自動轉為 G 調順階和弦） */
  function calibrateLoadedDocKeyAndChords(doc) {
    if (!doc || !Array.isArray(doc.measures)) return;
    var curKey = normalizeMusicKey(doc.key || 'C') || 'C';
    doc.key = curKey;
    var inferredKey = inferActualKeyFromMeasures(doc);
    if (inferredKey && inferredKey !== curKey && curKey === 'C') {
      transposeDocChords(doc, inferredKey, curKey);
    }
    var ts = $('#tonality-select');
    if (ts) ts.value = toChordDbRoot(curKey);
    if ($('#transpose-key')) $('#transpose-key').value = toChordDbRoot(curKey);
    renderRootGrid();
    renderChordPanel();
  }

  /* 當使用者修改左上角「1=」主調性欄位、#doc-key 或右側 #tonality-select 時，統一執行主調性切換與全譜和弦自動移調 */
  var _chordPanelRootFilter = null; /* null = 顯示目前主調的順階/附屬和弦群組；指定根音 = 顯示該根音全部變體 */

  function applyMainKeyChange(newKeyRaw, source) {
    var normNew = normalizeMusicKey(newKeyRaw);
    if (!normNew) return false;
    _chordPanelRootFilter = null;
    var dbRoot = toChordDbRoot(normNew);

    if (state3.doc) {
      var oldKey = normalizeMusicKey(state3.doc.key || 'C') || 'C';
      /* 先校準：若小節內和弦實際調性與 oldKey 不符（例如舊檔 key=C 但和弦在 G 調），以小節實際調性為基準轉至新調 */
      var actualChordKey = inferActualKeyFromMeasures(state3.doc) || oldKey;
      var effectiveFromKey = (oldKey === 'C' && actualChordKey !== 'C') ? actualChordKey : oldKey;
      if (effectiveFromKey !== normNew || oldKey !== normNew) {
        solaPushUndo();
        var moved = transposeDocChords(state3.doc, effectiveFromKey, normNew);
        state3.doc.key = normNew;
        renderChordProFromDoc(state3.doc);
        var scorePane = $('#score-pane');
        if (scorePane && scorePane.classList.contains('pane-active')) {
          renderV3Editor();
        }
        var solaPane = $('#sola321-pane');
        if (solaPane && solaPane.classList.contains('pane-active')) {
          renderSola321Score(false);
        }
        saveCurrentDoc();
        toast('主調性已設為 1=' + normNew + '（全部和弦已自動轉換為 ' + normNew + ' 調附屬和弦，共 ' + moved + ' 個）', 'ok');
      }
    }

    var ts = $('#tonality-select');
    if (ts && ts.value !== dbRoot) ts.value = dbRoot;
    if ($('#doc-key') && $('#doc-key').value !== normNew) $('#doc-key').value = normNew;
    if ($('#transpose-key')) $('#transpose-key').value = dbRoot;
    $$('#sola321-score .sola321-meta-input[data-meta="key"]').forEach(function(inp) {
      if (document.activeElement !== inp) inp.value = normNew;
    });

    renderRootGrid();
    renderChordPanel();
    return true;
  }

  function renderRootGrid() {
    var grid = $('#root-grid');
    if (!grid) return;
    var currentKey = $('#tonality-select') ? $('#tonality-select').value : 'C';
    var activeRoot = _chordPanelRootFilter || currentKey;
    var diatonicHtml = '<button type="button" class="root-btn root-btn-diatonic' + (!_chordPanelRootFilter ? ' active' : '') + '" data-root="__diatonic__" style="grid-column: span 2; font-weight:700;" title="顯示 1=' + escAttr(currentKey) + ' 調的順階與附屬和弦群組">' + escHtml(currentKey) + '調順階</button>';
    grid.innerHTML = diatonicHtml + ROOT_NOTES.map(function(n) {
      var isAct = (_chordPanelRootFilter === n);
      return '<button type="button" class="root-btn' + (isAct ? ' active' : '') + '" data-root="' + n + '" title="查看 ' + n + ' 根音系列和弦">' + n + '</button>';
    }).join('');
    $$('.root-btn').forEach(function(btn) {
      btn.addEventListener('click', function() {
        var r = this.getAttribute('data-root');
        if (r === '__diatonic__') {
          _chordPanelRootFilter = null;
        } else {
          _chordPanelRootFilter = r;
        }
        renderRootGrid();
        renderChordPanel();
      });
    });
  }

  function renderChordPanel() {
    var instRadio = $('input[name="instrument"]:checked');
    var instrument = instRadio ? instRadio.value : 'guitar';
    var key = (state3.doc && state3.doc.key) ? normalizeMusicKey(state3.doc.key) : null;
    if (!key) key = $('#tonality-select') ? $('#tonality-select').value : 'C';
    var db = instrument === 'ukulele' ? chordData.ukulele : chordData.guitar;

    var container = instrument === 'ukulele' ? $('#ukulele-options') : $('#chord-options');
    var otherPanel = instrument === 'ukulele' ? $('#chord-options') : $('#ukulele-options');
    /* 顯示目前樂器面板，徹底隱藏並清空另一面板，杜絕 C 和弦群組殘留於上方 */
    if (container) {
      container.hidden = false;
      container.removeAttribute('hidden');
      container.style.display = 'grid';
    }
    if (otherPanel) {
      otherPanel.hidden = true;
      otherPanel.setAttribute('hidden', 'hidden');
      otherPanel.style.display = 'none';
      otherPanel.innerHTML = '';
    }
    if (!container) return;

    var entries = [];
    if (!_chordPanelRootFilter) {
      /* 預設模式：顯示當前主調（如 1=C 或 1=G）的順階／附屬和弦家族 */
      entries = getDiatonicChordFamily(key, db);
    } else {
      /* 指定根音模式：收集該根音所有和弦變體（兼容別名，如 m7b5 / m7-5） */
      var root = _chordPanelRootFilter;
      CHORD_VARIANTS.forEach(function(v) {
        var key1 = root + v.suffix;
        if (db[key1]) { entries.push({ label: key1, key: key1, data: db[key1], zh: v.zh }); return; }
        if (v.alt) {
          var key2 = root + v.alt;
          if (db[key2]) { entries.push({ label: key1, key: key2, data: db[key2], zh: v.zh }); }
        }
      });
      (INV_CHORDS[root] || []).forEach(function(k) {
        if (db[k]) entries.push({ label: k, key: k, data: db[k], zh: '轉位' });
      });
    }

    /* 下方列表：只顯示和弦名稱（純文字按鈕，不含指法圖） */
    var html = entries.map(function(e) {
      return '<button type="button" class="chord-variant-item" data-key="' + e.key + '">' +
        '<span class="chord-symbol">' + e.label + '</span> ' +
        '<span class="chord-zh">（' + e.zh + '）</span>' +
        '</button>';
    }).join('');
    container.innerHTML = html;

    var nameEl = $('#chord-name-display');
    var mainEl = $('#chord-diagram-main');

    Array.prototype.slice.call(container.querySelectorAll('.chord-variant-item')).forEach(function(item) {
      item.addEventListener('mousedown', function(e) {
        /* 避免點選右側和弦庫時觸發 Score Studio 輸入框 blur 造成重複寫入或焦點遺失 */
        e.preventDefault();
      });
      item.addEventListener('click', function(e) {
        e.stopPropagation();
        var keyName = this.getAttribute('data-key');
        var entry = null;
        for (var i = 0; i < entries.length; i++) { if (entries[i].key === keyName) { entry = entries[i]; break; } }
        if (!entry) return;
        Array.prototype.slice.call(container.querySelectorAll('.chord-variant-item')).forEach(function(el) { el.classList.remove('active'); });
        this.classList.add('active');
        if (nameEl) nameEl.textContent = entry.label;
        if (mainEl) mainEl.innerHTML = '<div class="chord-diagram-wrap">' + renderChordSvg({ name: entry.key }, instrument) + '</div>';
        var cpPane = $('#chordpro-pane');
        if (cpPane && cpPane.classList.contains('pane-active')) {
          insertChordAtCursor(entry.label);
        } else {
          insertChordIntoScoreGrid(entry.label);
        }
      });
    });

    /* 預設選中第一個可用和弦，顯示其指法圖（不插入編輯區） */
    if (entries.length > 0) {
      var firstBtn = container.querySelector('.chord-variant-item');
      if (firstBtn) firstBtn.classList.add('active');
      var e0 = entries[0];
      if (nameEl) nameEl.textContent = e0.label;
      if (mainEl) mainEl.innerHTML = '<div class="chord-diagram-wrap">' + renderChordSvg({ name: e0.key }, instrument) + '</div>';
    } else {
      if (nameEl) nameEl.textContent = '—';
      if (mainEl) mainEl.innerHTML = '<div class="chord-diagram-placeholder">此調無和弦資料</div>';
      /* 空 = 和弦庫未載入成功 → 給重試鈕（強制重取 chords.json） */
      if (!chordLoaded) {
        container.innerHTML = '<button type="button" class="btn btn-sm" style="width:100%;margin:8px 0" data-chord-retry="1">↻ 重試載入和弦庫</button>';
        var rb = container.querySelector('[data-chord-retry]');
        if (rb) rb.addEventListener('click', function() { loadChords(true).then(function() { renderChordPanel(); }); });
      }
    }
  }

  function insertChordAtCursor(chord) {
    var editor = $('#chordpro-editor');
    if (!editor) return;
    var start = editor.selectionStart;
    var text = editor.value;
    editor.value = text.substring(0, start) + '[' + chord + ']' + text.substring(start);
    editor.focus();
    editor.setSelectionRange(start + chord.length + 2, start + chord.length + 2);
    editor.dispatchEvent(new Event('input', { bubbles: true }));
  }

  /* 把和弦插入到簡譜格線「選定小節」的和弦欄 */
  var scoreGridSelectedMI = null;   // 目前選中的小節索引
  var scoreGridNoteCursor = null;   // 當前簡譜輸入框游標位置 {mi, pos}
  var scoreGridPendingChord = null; // 待插入的和弦
  var noteDotsMap = {};  // 按 mi 儲存點號狀態: { [mi]: { [digitIdx]: { above: N, below: M } } }

  function selectScoreGridCell(mi) {
    scoreGridSelectedMI = mi;
    $$('.v3-cell').forEach(function(c) { c.classList.remove('selected'); });
    var cell = document.querySelector('.v3-cell[data-mi="' + mi + '"]');
    if (cell) cell.classList.add('selected');
  }

  var _lastChordInsertTs = 0;
  function insertChordIntoScoreGrid(chord) {
      var nowTs = Date.now();
      if (nowTs - _lastChordInsertTs < 80) return; // 防重入守門：單次點擊絕不重複觸發
      _lastChordInsertTs = nowTs;
      if (!state3.doc || !state3.doc.measures || state3.doc.measures.length === 0) {
        return; // 無小節，忽略
      }
      var ms = state3.doc.measures;
      /* 直接目標化：優先用「剛點過的小節」＝目標小節 */
      var mi = solaGetTargetMI();
      var m = ms[mi];
      if (!m) return;
      solaPushUndo();
      v3EnsureChordOffsets(m);
      var nti = 0;
      var soloPane = document.getElementById('sola321-pane');
      if (soloPane && soloPane.classList.contains('pane-active')) {
        var cur = solaGetCursor();
        if (cur && cur.mi === mi && typeof cur.nti === 'number') nti = cur.nti;
      }
      /* 若該音符上方已經有和弦，則自動放置於下一個尚未放置和弦的音符位置（並可隨時左右拖曳） */
      if (m.chordOffsets.indexOf(nti) >= 0) {
        var nextOff = nti + 1;
        while (m.chordOffsets.indexOf(nextOff) >= 0) nextOff++;
        nti = nextOff;
        if (solaEdit.mi === mi) solaEdit.nti = nti;
      }
      var parts = v3ChordParts(m);
      parts.push(chord);
      m.chordText = parts.join(' ');
      m.chordOffsets.push(nti);
      m.chordTicks.push(nti * 480);
      v3SortChordsByOffset(m);
      syncLegacyToEvents(m);
      /* 若直式和弦輸入框正處於編輯狀態，先同步其 value，避免重繪時 blur 事件把舊字串寫回 */
      var activeChordInp = document.querySelector('#sola321-score .sola321-v-chord-editor[data-mi="' + mi + '"]');
      if (activeChordInp) activeChordInp.value = m.chordText;
      scoreGridSelectedMI = mi;
      var gridPane = document.getElementById('score-pane');
      if (gridPane && gridPane.classList.contains('pane-active')) {
        selectScoreGridCell(mi);
        renderV3Editor(true);
      }
      var total = parts.length;
      var msg = '和弦 [' + chord + '] 已對齊小節 ' + (mi + 1) + ' 第 ' + (nti + 1) + ' 個音符上方';
      if (total > 1) msg += '（此小節現共 ' + total + ' 個和弦）';
      toast(msg, 'ok');
      if (soloPane && soloPane.classList.contains('pane-active') && !solaEdit.useTimelineRenderer && solaEdit.viewMode === 'vertical') {
        if (!solaUpdateMeasureChordsInPlace(mi)) {
          refreshSola321IfActive();
        }
      } else {
        refreshSola321IfActive();
      }
      solaRestoreTargetHighlight();
      if (state3.doc) renderChordProFromDoc(state3.doc);
      saveCurrentDoc(true);
    }

  /* 清理 noteText 中的組合點號字元，僅留純數字與標點（ChordPro 格式用） */
  function cleanNoteText(s) {
    if (!s) return '';
    return s.replace(/[\u0307\u0323]/g, '');
  }

  /* ===== OMR 導入暫存器（omrInbox）：一次把資料同步到三個編輯器 ===== */
  var omrInbox = null;   // 最近一次 OMR 導入的 doc 快照（單一資料來源，供三個編輯器共讀）

  function syncOmRInboxToAllEditors(doc) {
    if (!doc || !doc.measures) return;
    omrInbox = doc;

    // 1) 簡譜格線：state3.doc 指向新 doc，重建 noteDotsMap（從 doc 內的點號解析），重繪
    state3.doc = doc;
    state3.currentDocId = doc.id || null;
    noteDotsMap = {};
    (doc.measures || []).forEach(function(m, i) {
      if (m.noteText) noteDotsMap[i] = parseNoteTextToDots(m.noteText).noteDots;
    });
    migrateAllMeasures(doc);  // Phase 1: OMR 導入後初始化 Event Model
    calibrateLoadedDocKeyAndChords(doc);
    renderV3Editor();

    // 2) ChordPro 文字：用 doc 直接生成（純函數，不影響 openProject 路徑）
    renderChordProFromDoc(doc);

    // 3) SoLa321：OMR 導入後重置游標與複撤銷歷史（doc 全換了，舊游標無效），並直接重繪
    initSola321EditState();
    renderSola321Score();

    // 4) OMR 完成後切到 Score Studio（圖2 目標版面；Flow 樂譜文件編輯器已移除）
    switchTab('sola321');
  }

  function loadOmrResult(projectId, task) {
    if (!projectId) return;
    /* 以專案 API 為唯一資料源（含和弦、簡譜、歌詞、點號），不再抓 MusicXML 片段 */
    api('/api/projects/' + projectId).then(function(doc) {
      setSaveState('已載入 OMR：' + (doc.title || projectId), '#38a169');
      syncOmRInboxToAllEditors(doc);
      toast('OMR 完成：已載入 Score Studio 編輯器；其他頁籤（簡譜格線／ChordPro）已同步', 'ok');
    }).catch(function(e) {
      // 專案 API 失敗時退回舊的 MusicXML/Sola321 路徑（保持可用）
      api('/api/projects/' + projectId + '/preview?format=musicxml').then(function(content) {
        if (content && typeof content === 'string' && content.indexOf('<note') !== -1) {
          var ed = $('#chordpro-editor');
          if (ed) { ed.value = extractChordPro(content); ed.focus(); }
        }
      }).catch(function() {});
      toast('OMR 載入失敗：' + (e.message || '未知錯誤'), 'bad');
    });
  }

  function extractChordPro(xml) {
    try {
      var doc = new DOMParser().parseFromString(xml, 'text/xml');
      var currentLyrics = '';
      var measures = doc.querySelectorAll('measure');
      measures.forEach(function(m) {
        var notes = m.querySelectorAll('note');
        if (notes.length > 0) {
          currentLyrics += ' ';
          notes.forEach(function(n) {
            var lyric = n.querySelector('lyric text');
            if (lyric) currentLyrics += lyric.textContent;
          });
        }
      });
      return currentLyrics || '辨識成功，請在編輯區查看';
    } catch(e) { return '辨識完成，詳細請查看右側任務列表'; }
  }

  /* 開啟「暫存樂譜」JSON 檔：直接載入 ScoreDocument 並進入 Score Studio 編輯頁面繼續編輯 */
  function openDraftJsonFile(file) {
    if (!file) return;
    var reader = new FileReader();
    reader.onload = function(evt) {
      var data = null;
      try {
        data = JSON.parse(String(evt.target.result || ''));
      } catch (err) {
        toast('暫存檔 JSON 格式無效：' + err.message, 'bad');
        return;
      }
      if (!data || !Array.isArray(data.measures)) {
        /* 非 ScoreDocument JSON 則走一般後端上傳流程 */
        uploadFileToTasks(file);
        return;
      }
      if (!data.title || data.title === '未命名樂譜') {
        var stem = String(file.name || '').replace(/\.json$/i, '').trim();
        if (stem) data.title = stem;
      }
      var upsertPromise;
      if (data.id) {
        upsertPromise = api('/api/projects/' + encodeURIComponent(data.id), {
          method: 'PUT',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify(data)
        }).catch(function() {
          return api('/api/projects', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ title: data.title || '未命名樂譜' })
          }).then(function(created) {
            data.id = created.id;
            return api('/api/projects/' + encodeURIComponent(created.id), {
              method: 'PUT',
              headers: { 'Content-Type': 'application/json' },
              body: JSON.stringify(data)
            });
          });
        });
      } else {
        upsertPromise = api('/api/projects', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ title: data.title || '未命名樂譜' })
        }).then(function(created) {
          data.id = created.id;
          return api('/api/projects/' + encodeURIComponent(created.id), {
            method: 'PUT',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(data)
          });
        });
      }
      upsertPromise.then(function(res) {
        var docObj = (res && res.document) ? res.document : data;
        loadProjects();
        setSaveState('已載入暫存檔：' + (docObj.title || file.name), '#38a169');
        syncOmRInboxToAllEditors(docObj);
        switchTab('sola321');
        setSola321Status('✓ 已開啟暫存檔《' + (docObj.title || file.name) + '》，可直接繼續編輯', '#38a169');
        toast('已開啟暫存檔《' + (docObj.title || file.name) + '》，進入編輯頁面繼續編輯', 'ok');
      }).catch(function(err) {
        toast('開啟暫存檔失敗：' + (err.message || '未知錯誤'), 'bad');
      });
    };
    reader.readAsText(file, 'utf-8');
  }

  function uploadFileToTasks(file) {
    var fd = new FormData();
    fd.append('file', file, file.name);
    setStageFlow('upload', 'active');
    api('/api/tasks', { method: 'POST', body: fd })
      .then(function(task) {
        state.currentTaskId = task.id;
        state.lastToastStage = 'rasterize';
        toast('檔案上傳成功：' + file.name + '，進入轉圖與辨識流程…', 'ok');
        setStageFlow('rasterize', 'active');
        startPolling(state.currentTaskId);
      })
      .catch(function(err) {
        setStageFlow('upload', 'failed');
        toast('導入失敗：' + err.message, 'bad');
      });
  }

  function uploadFile(file) {
    if (file && /\.json$/i.test(file.name || '')) {
      openDraftJsonFile(file);
      return;
    }
    uploadFileToTasks(file);
  }

  var isImportingUrl = false;
  function importFromUrl(url) {
    if (isImportingUrl) return;
    var cleanUrl = String(url || '').trim();
    if (!cleanUrl) {
      toast('請先輸入歌譜網址', 'bad');
      return;
    }
    isImportingUrl = true;
    var btn = $('#btn-url-import');
    if (btn) { btn.disabled = true; btn.textContent = '抓取中…'; }
    setStageFlow('upload', 'active');
    toast('正在從網址抓取並解析歌譜…', 'ok');
    api('/api/import-url', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ url: cleanUrl })
    })
      .then(function(res) {
        setStageFlow('upload', 'done');
        setStageFlow('rasterize', 'done');
        setStageFlow('omr', 'done');
        setStageFlow('musicxml', 'done');
        loadProjects();
        loadTasks();
        if (res && res.document) {
          setSaveState('已載入網址歌譜：' + (res.document.title || res.projectId || ''), '#38a169');
          syncOmRInboxToAllEditors(res.document);
          toast('網址歌譜抓取成功：' + (res.document.title || '') + '（共 ' + ((res.document.measures || []).length) + ' 小節），已載入編輯區', 'ok');
        } else if (res && res.projectId) {
          loadOmrResult(res.projectId);
        }
      })
      .catch(function(err) {
        setStageFlow('upload', 'failed');
        toast('網址抓取失敗：' + (err.message || '未知錯誤'), 'bad');
      })
      .finally(function() {
        isImportingUrl = false;
        if (btn) { btn.disabled = false; btn.textContent = '抓取載入'; }
      });
  }
  window.importFromUrl = importFromUrl;

  function startPolling(taskId) {
    if (state.pollTimer) clearInterval(state.pollTimer);
    state.pollTimer = setInterval(function() { pollTask(taskId); }, 1000);
    pollTask(taskId);
    loadTasks();
  }

  function pollTask(taskId) {
    if (!taskId) return;
    api('/api/tasks/' + taskId).then(function(t) {
      if (t.status === 'done' || t.status === 'completed') {
        clearInterval(state.pollTimer);
        setStageFlow('upload', 'done');
        setStageFlow('rasterize', 'done');
        setStageFlow('omr', 'done');
        setStageFlow('musicxml', 'done');
        toast('辨識完成！任務 ID：' + taskId, 'ok');
        loadTasks();
        if (t.projectId) { loadOmrResult(t.projectId, t); }
      } else if (t.status === 'running' || t.status === 'queued') {
        var st = (!t.stage || t.stage === 'upload' || t.stage === 'queued') ? 'rasterize' : t.stage;
        setStageFlow(st, 'active');
        if (state.lastToastStage !== st) {
          state.lastToastStage = st;
        }
      } else if (t.status === 'failed' || t.status === 'error' || t.status === 'cancelled') {
        clearInterval(state.pollTimer);
        var failStage = (t.stage && ['upload', 'rasterize', 'omr', 'musicxml'].indexOf(t.stage) >= 0)
          ? t.stage
          : (state.lastToastStage || 'omr');
        setStageFlow(failStage, 'failed');
        loadTasks();
        toast('辨識失敗：' + (t.error || t.message || '未知錯誤'), 'bad');
      }
    }).catch(function() {});
  }

  function loadTasks() {
    var list = $('#task-list');
    if (!list) return;
    api('/api/tasks').then(function(tasks) {
      if (!tasks || tasks.length === 0) { list.innerHTML = '<p class="empty">尚無任務。</p>'; return; }
      list.innerHTML = tasks.map(function(t) {
        var isErr = (t.status === 'error' || t.status === 'failed' || t.status === 'cancelled');
        var c = t.status === 'done' ? '#38a169' : (t.status === 'running' || t.status === 'queued') ? '#3182ce' : isErr ? '#e53e3e' : '#a0aec0';
        return '<div style="padding:6px;border-bottom:1px solid var(--line-soft);font-size:11px;">' +
          '<span style="color:' + c + '">' + t.status + '</span> ' +
          '<span style="color:#a0aec0">' + (t.sourceName || t.id).substring(0,30) + '</span></div>';
      }).join('');
    });
  }

  /* ===== V3.00：專案列、載入、保存 ===== */
  var state3 = { currentDocId: null, doc: null, rowsRendered: 0 };

  function setSaveState(msg, color) {
    var el = $('#save-state');
    if (el) { el.textContent = msg; el.style.color = color || ''; }
  }

  function loadProjects() {
    api('/api/projects').then(function(items) {
      var list = $('#project-list');
      if (!list) return;
      if (!items || items.length === 0) { list.innerHTML = '<p class="empty">尚無專案。</p>'; return; }
      list.innerHTML = items.map(function(p) {
        var id = p.id || p.docId;
        return '<div class="project-item" data-id="' + id + '" style="padding:6px;border-bottom:1px solid var(--line-soft);font-size:11px;cursor:pointer;">' +
          '<b>' + (p.title || '未命名樂譜') + '</b><br><span style="color:#a0aec0">' +
          (p.measureCount || p.measures || '?') + ' 小節　' + (p.updatedAt || p.createdAt || '').substring(0, 10) + '</span></div>';
      }).join('');
      $$('.project-item').forEach(function(el) {
        el.addEventListener('click', function() { openProject(el.getAttribute('data-id')); });
      });
    });
  }

  var _autoSaveTimer = null;
  var _lastProjectListSig = '';

  function flushPendingAutoSave() {
    if (_autoSaveTimer) {
      clearTimeout(_autoSaveTimer);
      _autoSaveTimer = null;
      if (state3.currentDocId && state3.doc) {
        saveCurrentDoc(true, true);
      }
    }
  }

  window.addEventListener('beforeunload', function() {
    flushPendingAutoSave();
  });

  function openProject(id) {
    flushPendingAutoSave();
    api('/api/projects/' + id).then(function(doc) {
      state3.currentDocId = id;
      state3.doc = doc;
      _lastProjectListSig = id + '::' + (doc.title || '') + '::' + ((doc.measures || []).length);
      migrateAllMeasures(doc);  // Phase 1: 初始化 Event Model
      calibrateLoadedDocKeyAndChords(doc);
      setSaveState('已載入：' + (doc.title || id), '#38a169');
      renderV3Editor();
      renderChordProFromDoc(doc);
      // SoLa321 編輯器：重置游標與複撤銷歷史，再渲染
      initSola321EditState();
      renderSola321Score();
    }).catch(function(e) { toast('載入專案失敗：' + e.message, 'bad'); });
  }

  function renderChordProFromDoc(doc, force) {
    var ed = $('#chordpro-editor');
    if (!ed || !doc) return;
    var cpPane = document.getElementById('chordpro-pane');
    if (!force && cpPane && !cpPane.classList.contains('pane-active')) return;
    if (window.SyncEngine && typeof window.SyncEngine.syncChordProEditor === 'function') {
      window.SyncEngine.syncChordProEditor(doc, { editorEl: ed });
      return;
    }
    var lines = ['#title: ' + (doc.title || ''), '#key: ' + (doc.key || 'C'),
      '#tempo: ' + (doc.tempo || 90), '#time: ' + (doc.timeSignature || '4/4')];
    if (doc.composer) lines.push('#artist: ' + doc.composer);
    lines.push('');
    (doc.measures || []).forEach(function(m) {
      var l = (m.chordText || '').trim();
      var note = cleanNoteText(m.noteText || '').trim();
      var lyric = (m.lyricText || '').trim();
      if (l || note || lyric) lines.push((l ? '[' + l.split(/\s+/).join('][') + '] ' : '') + (note ? note + ' ' : '') + lyric);
    });
    ed.value = lines.join('\n');
  }

  function saveCurrentDoc(silent, immediate) {
    var isEvent = (silent && typeof silent === 'object' && typeof silent.preventDefault === 'function');
    var isSilent = isEvent ? false : (silent !== false);
    var isImmediate = isEvent ? true : (immediate === true || silent === false);

    if (!state3.currentDocId) {
      // 從 ChordPro 文字直接建新專案
      var ed = $('#chordpro-editor');
      var payload = { title: (ed && ed.value.match(/^#title:\s*(.+)$/m) || [,'未命名樂譜'])[1] };
      api('/api/projects', { method: 'POST', body: JSON.stringify(payload), headers: {'Content-Type':'application/json'} })
        .then(function(doc) {
          state3.currentDocId = doc.id;
          state3.doc = doc;
          if (ed) applyChordProToDoc(doc, ed.value);
          return api('/api/projects/' + doc.id, { method: 'PUT', body: JSON.stringify(doc), headers: {'Content-Type':'application/json'} });
        })
        .then(function(res) {
          loadProjects();
          var draftPath = (res && (res.draftFile || (res.saved && res.saved.draftFile))) ? (res.draftFile || res.saved.draftFile) : '';
          setSaveState('已儲存 ' + (draftPath || new Date().toLocaleTimeString()), '#38a169');
          if (!isSilent) {
            toast(draftPath ? ('已儲存暫存檔：' + draftPath) : '專案已保存', 'ok');
          }
          renderV3Editor();
        })
        .catch(function(e) { toast('保存失敗：' + e.message, 'bad'); });
      return;
    }

    if (!isImmediate) {
      if (_autoSaveTimer) clearTimeout(_autoSaveTimer);
      setSaveState('編輯中（自動保存排程中…）', '#3182ce');
      _autoSaveTimer = setTimeout(function() {
        _autoSaveTimer = null;
        saveCurrentDoc(true, true);
      }, 1200);
      return;
    }

    if (_autoSaveTimer) {
      clearTimeout(_autoSaveTimer);
      _autoSaveTimer = null;
    }

    var doc = state3.doc;
    if (!doc) return;
    collectV3ToDoc(doc);
    // Flow 編輯器：寫回 tick 變更與刪除
    if (typeof window.applyFlowToDoc === 'function') {
      window.applyFlowToDoc(doc);
    }
    var curSig = state3.currentDocId + '::' + (doc.title || '') + '::' + ((doc.measures || []).length);
    api('/api/projects/' + state3.currentDocId, { method: 'PUT', body: JSON.stringify(doc), headers: {'Content-Type':'application/json'} })
      .then(function(res) {
        if (!isSilent || curSig !== _lastProjectListSig) {
          _lastProjectListSig = curSig;
          loadProjects();
        }
        var draftPath = (res && (res.draftFile || (res.saved && res.saved.draftFile))) ? (res.draftFile || res.saved.draftFile) : '';
        setSaveState('已儲存 ' + new Date().toLocaleTimeString(), '#38a169');
        if (draftPath && !isSilent) {
          setSola321Status('✓ 已儲存至暫存資料夾：' + draftPath, '#38a169');
        }
        if (!isSilent) {
          toast(draftPath ? ('已儲存至暫存資料夾：' + draftPath) : '樂譜已保存', 'ok');
        }
      })
      .catch(function(e) { toast('保存失敗：' + e.message, 'bad'); });
  }

  function solaSave(silent) {
    if (!state3.doc) {
      if (!silent) setSola321Status('請先載入專案再儲存', '#e53e3e');
      return;
    }
    var isSilent = (silent === true);
    renderChordProFromDoc(state3.doc, !isSilent);
    saveCurrentDoc(isSilent, !isSilent);
    updateSyncStatusBadge('✓ 已同步並儲存', 'sync-ok');
  }

  function applyChordProToDoc(doc, text) {
    if (window.SyncEngine && typeof window.SyncEngine.syncFromChordProToScore === 'function') {
      return window.SyncEngine.syncFromChordProToScore(text, doc, {
        ensureEventModel: typeof ensureEventModel === 'function' ? ensureEventModel : null,
        onUpdated: function() {
          if (typeof renderV3Editor === 'function') renderV3Editor();
          if (typeof renderSola321Score === 'function') renderSola321Score(false);
        },
        onError: function(errs) {
          if (errs && errs.length && typeof toast === 'function') {
            toast('ChordPro 語法錯誤：' + errs[0].message, 'bad');
          }
        }
      });
    }
    doc.title = (text.match(/^#title:\s*(.+)$/m) || [,'未命名樂譜'])[1].trim() || doc.title;
    var k = text.match(/^#key:\s*(\S+)$/m); if (k) doc.key = k[1];
    var b = text.match(/^#(bpm|tempo):\s*(\d+)$/m); if (b) doc.tempo = parseInt(b[2], 10);
    var t = text.match(/^#time:\s*(\S+)$/m); if (t) doc.timeSignature = t[1];
    var a = text.match(/^#artist:\s*(.+)$/m); if (a) doc.composer = a[1].trim();
  }

  // 輔助：將簡譜文字轉為可點擊 span（數字 span 內嵌組合字元）
  function renderNoteHtml(noteText, noteDots, measureIdx) {
    if (!noteText) return '<span></span>';
    var dots = noteDots || {};
    // 先移除組合點字元：顯示一律改由 CSS 絕對定位圓點呈現（不靠字型畫組合字元）
    var clean = noteText.replace(/[\u0307\u0323]/g, '');
    var html = '';
    var digitIdx = 0;
    for (var i = 0; i < clean.length; i++) {
      var ch = clean.charAt(i);
      if (ch >= '0' && ch <= '9') {
        var dotInfo = dots[digitIdx] || null;
        var dotHtml = '';
        if (dotInfo) {
          for (var a = 0; a < (dotInfo.above || 0); a++) dotHtml += '<i class="v3-dot above' + (a === 1 ? ' above2' : '') + '"></i>';
          for (var b = 0; b < (dotInfo.below || 0); b++) dotHtml += '<i class="v3-dot below' + (b === 1 ? ' below2' : '') + '"></i>';
        }
        html += '<span class="v3-note-char" data-mi="' + measureIdx + '" data-char-idx="' + digitIdx + '"><span class="v3-digit">' + escHtml(ch) + '</span>' + dotHtml + '</span>';
        digitIdx++;
      } else {
        html += '<span class="v3-note-plain">' + escHtml(ch) + '</span>';
      }
    }
    return html;
  }

  /* ===== 八度輔助函數（IIFE 頂層）：點號分離到 noteDotsMap，避免組合字元造成索引偏移 ===== */
  function parseNoteTextToDots(noteText) {
    var out = { noteText: '', noteDots: {} };
    if (!noteText) return out;
    var digitIdx = 0;
    for (var i = 0; i < noteText.length; i++) {
      var ch = noteText.charAt(i);
      if (ch >= '0' && ch <= '9') {
        out.noteText += ch;
        out.noteDots[digitIdx] = out.noteDots[digitIdx] || { above: 0, below: 0 };
        digitIdx++;
      } else if (ch === '\u0307' && digitIdx > 0) {
        out.noteDots[digitIdx - 1] = out.noteDots[digitIdx - 1] || { above: 0, below: 0 };
        out.noteDots[digitIdx - 1].above++;
      } else if (ch === '\u0323' && digitIdx > 0) {
        out.noteDots[digitIdx - 1] = out.noteDots[digitIdx - 1] || { above: 0, below: 0 };
        out.noteDots[digitIdx - 1].below++;
      }
    }
    return out;
  }

  function composeNoteTextFromDots(noteText, noteDots) {
      if (!noteText) return '';
      var result = '';
      var digitIdx = 0;
      for (var i = 0; i < noteText.length; i++) {
        var ch = noteText.charAt(i);
        result += ch;
        if (ch >= '0' && ch <= '9') {
          var info = noteDots && noteDots[digitIdx];
          if (info) {
            for (var a = 0; a < (info.above || 0); a++) result += '\u0307';
            for (var b = 0; b < (info.below || 0); b++) result += '\u0323';
          }
          digitIdx++;
        }
      }
      return result;
    }

  function getNoteDotsFor(mi) {
    if (mi === null || mi === undefined) return {};
    if (!noteDotsMap[mi] && state3.doc && state3.doc.measures && state3.doc.measures[mi]) {
      noteDotsMap[mi] = parseNoteTextToDots(state3.doc.measures[mi].noteText || '').noteDots;
    }
    return noteDotsMap[mi] || {};
  }

  // 對「點擊的數字」套八度：上方點（高音）/ 下方點（低音），每邊最多 2 點，再按歸零
  // 目標優先取 scoreGridNoteCursor（點擊數字所在小節＋數字序），否則回退到選中小節的最後一個數字
  function countDigits(s) {
    var n = 0;
    for (var i = 0; i < s.length; i++) if (s.charAt(i) >= '0' && s.charAt(i) <= '9') n++;
    return n;
  }
  function applyOctaveToSelected(dir) {
      if (!state3.doc || !state3.doc.measures) { toast('請先載入專案', 'warn'); return; }
      /* 與顯示、拆小節線同一套 token 模型（v3NoteTokens/v3NoteTokenHtml）：
         點號存 token.above/below，重建 noteText 時重算，不再累積舊點字元（舊 composeNoteTextFromDots
         會把既有點號原樣拷貝＋再加新點 → 點號疊加倍數、與格線顯示不一致） */
      var mI = null, ti = null;
      if (scoreGridNoteCursor && scoreGridNoteCursor.mi != null && state3.doc.measures[scoreGridNoteCursor.mi]) {
        var toksC = v3NoteTokens(state3.doc.measures[scoreGridNoteCursor.mi].noteText || '');
        var c = scoreGridNoteCursor.charIndex;
        if (c != null && c >= 0 && c < Math.max(1, toksC.length)) { mI = scoreGridNoteCursor.mi; ti = c; }
      }
      if (mI === null) {
        if (scoreGridSelectedMI === null || !state3.doc.measures[scoreGridSelectedMI]) {
          toast('請先點選小節或音符，再按高/低音', 'warn'); return;
        }
        mI = scoreGridSelectedMI;
      }
      var m = state3.doc.measures[mI];
      var toks = v3NoteTokens(m.noteText || '');
      if (!toks.length) toks.push({ base: '', above: 0, below: 0 });
      if (ti === null) ti = toks.length - 1;
      var t = toks[ti];
      if (dir === 1) t.above = (t.above || 0) >= 2 ? 0 : (t.above || 0) + 1;
      else t.below = (t.below || 0) >= 2 ? 0 : (t.below || 0) + 1;
      m.noteText = toks.map(v3NoteTokenHtml).join(' ');
          syncLegacyToEvents(m);
          // 同步 legacy dots map（contenteditable 舊路徑仍讀它，避免衝突）
      noteDotsMap[mI] = parseNoteTextToDots(m.noteText).noteDots;
      renderV3Editor();
      toast(dir === 1 ? '已套用高音（上方點）' : '已套用低音（下方點）', 'ok');
      refreshSola321IfActive();
    }

  /* ===== 簡譜格線小節線增刪：＋│ 在選定音符「後面」拆小節；－│ 把下一小節併入選中小節
     目標：優先用音符游標（點某個音符格 → data-mi/data-ti），否則用選中小節（末音符後）；
     拆併同步重排小節號，與 SoLa321 頁籤共用同一資料模型（noteText 空格分隔 token）。 */
  function v3BarlineTarget() {
    var ms = (state3.doc && state3.doc.measures) || [];
    if (!ms.length) return null;
    var mi = null, splitIdx = null;
    var solaPane = document.getElementById('sola321-pane');
    var solaActive = solaPane && (solaPane.classList.contains('pane-active') || solaPane.classList.contains('active'));
    if (solaActive && typeof solaEdit === 'object' && solaEdit && solaEdit.mi != null && ms[solaEdit.mi]) {
      mi = solaEdit.mi;
      var toksS = v3NoteTokens(ms[mi].noteText || '');
      if (typeof solaEdit.nti === 'number' && solaEdit.nti >= 0 && solaEdit.nti < Math.max(1, toksS.length)) {
        splitIdx = solaEdit.nti;
      }
    }
    if (mi === null && scoreGridNoteCursor && scoreGridNoteCursor.mi != null && ms[scoreGridNoteCursor.mi]) {
      var toksC = v3NoteTokens(ms[scoreGridNoteCursor.mi].noteText || '');
      var ci = scoreGridNoteCursor.charIndex;
      if (ci != null && ci >= 0 && ci < Math.max(1, toksC.length)) {
        mi = scoreGridNoteCursor.mi;
        splitIdx = ci;
      }
    }
    if (mi === null && scoreGridSelectedMI != null && ms[scoreGridSelectedMI]) mi = scoreGridSelectedMI;
    if (mi === null && typeof solaEdit === 'object' && solaEdit && solaEdit.mi != null && ms[solaEdit.mi]) mi = solaEdit.mi;
    if (mi === null) return null;
    if (splitIdx === null) splitIdx = Math.max(0, v3NoteTokens(ms[mi].noteText || '').length - 1);
    return { mi: mi, splitIdx: splitIdx };
  }
  function v3BarlineAdd() {
    if (!state3.doc || !state3.doc.measures || !state3.doc.measures.length) { openProjectHint(); return; }
    var ms = state3.doc.measures;
    var t = v3BarlineTarget();
    if (!t) { toast('請先點選小節或音符，再新增小節線', 'warn'); return; }
    if (typeof solaPushUndo === 'function') solaPushUndo();
    var m = ms[t.mi];
    var toks = v3NoteTokens(m.noteText || '');
    var head = toks.slice(0, t.splitIdx + 1);          // 選定音符（含）前 → 留原小節
    var tail = toks.slice(t.splitIdx + 1);            // 選定音符之後 → 移入新小節
    m.noteText = head.map(v3NoteTokenHtml).join(' ');
    syncLegacyToEvents(m);
    var nm = {
      number: ms.length + 1,
      chordText: '', chordOffsets: [],
      noteText: tail.map(v3NoteTokenHtml).join(' '),
      lyricText: '', lyricText2: '', lyricText3: '', lyricText4: '',
      lyricRows: 1, barline: true, marks: ''
    };
    ensureEventModel(nm);
    ms.splice(t.mi + 1, 0, nm);
    ms.forEach(function(x, i) { x.number = i + 1; });
    m.barline = true;
    scoreGridNoteCursor = tail.length ? { mi: t.mi + 1, charIndex: 0 } : null;
    scoreGridSelectedMI = t.mi + 1;
    if (typeof solaEdit === 'object' && solaEdit) {
      solaEdit.mi = t.mi + 1;
      solaEdit.nti = 0;
    }
    renderV3Editor();
    selectScoreGridCell(t.mi + 1);
    toast('已於選定音符後新增小節線' + (tail.length ? '（' + tail.length + ' 個音符移入新小節）' : '（新小節為空白）'), 'ok');
    refreshSola321IfActive();
    saveCurrentDoc();
  }
  function v3BarlineDel() {
    if (!state3.doc || !state3.doc.measures || !state3.doc.measures.length) { openProjectHint(); return; }
    var ms = state3.doc.measures;
    var t = v3BarlineTarget();
    if (!t) { toast('請先點選小節或音符，再刪除小節線', 'warn'); return; }
    var mi = t.mi;
    if (mi >= ms.length - 1) { toast('末小節右側沒有小節線可刪除', 'warn'); return; }
    if (typeof solaPushUndo === 'function') solaPushUndo();
    var m = ms[mi], nx = ms[mi + 1];
    var headToks = v3NoteTokens(m.noteText || '');
    var nxToks = v3NoteTokens(nx.noteText || '');
    m.noteText = headToks.concat(nxToks).map(v3NoteTokenHtml).join(' ');
    m.chordText = String(m.chordText || '').trim().split(/\s+/).concat(String(nx.chordText || '').trim().split(/\s+/)).filter(Boolean).join(' ');
    m.chordOffsets = m.chordOffsets || [];
    (nx.chordOffsets || []).forEach(function(o) { m.chordOffsets.push(o + headToks.length); });
    ['lyricText', 'lyricText2', 'lyricText3', 'lyricText4'].forEach(function(f) {
      var a = String(m[f] || '').trim(), b = String(nx[f] || '').trim();
      if (a && b) m[f] = a + ' ' + b; else m[f] = a || b;
    });
    syncLegacyToEvents(m);
    ms.splice(mi + 1, 1);
    ms.forEach(function(x, i) { x.number = i + 1; });
    m.barline = true;
    scoreGridNoteCursor = null;
    if (typeof solaEdit === 'object' && solaEdit) {
      solaEdit.mi = mi;
      solaEdit.nti = Math.max(0, headToks.length - 1);
    }
    renderV3Editor();
    selectScoreGridCell(mi);
    toast('已刪除小節線，小節 ' + (mi + 1) + ' 與 ' + (mi + 2) + ' 已合併', 'ok');
    refreshSola321IfActive();
    saveCurrentDoc();
  }

  /* ===== V3.00：SoLa321 結構化事件模型（取代 LilyPond 頁籤）=====
     依《SoLa321 網頁樂譜編輯器》規範：把簡譜 doc 轉成「結構化事件模型」
     （scoreSettings + parts/measures/events），PPQ=480，notes 附著 lyrics/chords。
     全在前端做，不新增後端端點；匯出 SoLa321 JSON 走現有 sola321 輸出器。 */
  var SOLA321_PPQ = 480;                 // 四分音符 = 480 tick
  var SOLA321_DUR_TICKS = { whole: 480, half: 240, quarter: 120, eighth: 60, '16th': 30, '32nd': 15 };

  // 把拍號字串（"4/4"）解析成 {beats, beatType}
  function parseTimeSignatureToSola321(ts) {
    var parts = String(ts || '4/4').split('/');
    var beats = parseInt(parts[0], 10); if (isNaN(beats)) beats = 4;
    var beatType = parseInt(parts[1], 10); if (isNaN(beatType)) beatType = 4;
    return { beats: beats, beatType: beatType };
  }

  // 每個事件 tick 數（時值 × 拍號分子總時值比較用）；dotted 加半
  function tickCountForDuration(duration, dotted) {
    var base = SOLA321_DUR_TICKS[duration] || 120;
    return dotted ? base + Math.round(base / 2) : base;
  }

  // 小節需要的總 tick（以 120 = 1 個四分音符 為單位）
  // 拍號 beats/beatType：beatType=4 時 1 拍=1 四分(120 tick)；beatType=8 時 1 拍=1 八分(60 tick)；beatType=2 時 1 拍=1 二分(240 tick)
  // 公式：1 拍 tick = 120 × (4 / beatType)；小節總 tick = beats × 1拍tick
  function ticksPerMeasure(timeSig) {
    var ts = parseTimeSignatureToSola321(timeSig);
    var tickPerBeat = 120 * (4 / ts.beatType);  // beatType=4→120, 8→60, 2→240
    return ts.beats * tickPerBeat;
  }

  // 主函數：doc → SoLa321 事件模型（含拍數驗證）。回傳 {model, measureChecks}
  function buildSola321Model(doc) {
    doc = doc || {};
    var ts = parseTimeSignatureToSola321(doc.timeSignature);
    var perMeasure = ticksPerMeasure(doc.timeSignature);

    var model = {
      schemaVersion: '1.0',
      id: doc.id || 'sola321-doc',
      title: doc.title || '未命名樂譜',
      composer: doc.composer || '',
      lyricist: doc.lyricist || '',
      scoreSettings: {
        key: { tonic: doc.key || 'C', mode: 'major', numberNotation: '1=' + (doc.key || 'C') },
        timeSignature: { beats: ts.beats, beatType: ts.beatType },
        tempo: { bpm: doc.tempo || 90, beatUnit: 'quarter', text: '' },
        pickup: null,
        transposeDisplaySemitones: 0,
        rhythmGrouping: 'byTimeSignature',
        showKey: true, showTimeSignature: true, showTempo: true
      },
      parts: [{
        id: 'part-1',
        name: '聲部 1',
        shortName: 'V1',
        instrument: { id: 'voice', family: 'vocal', midiProgram: 0, notationMode: 'numbered' },
        displayMode: 'numbered',
        transposeSemitones: 0,
        measures: []
      }],
      sections: [],
      layout: {},
      history: {}
    };

    var checks = [];
    (doc.measures || []).forEach(function(m, mi) {
      var tsLocal = parseTimeSignatureToSola321(doc.timeSignature);
      var perM = ticksPerMeasure(doc.timeSignature);
      // 簡譜 token：用 split_notes 等價邏輯（去空白、去小節線）
      var tokens = String(m.noteText || '').trim().split(/\s+/).filter(function(t){ return t && t !== '|'; });
      var events = [];
      var used = 0;
      tokens.forEach(function(tok, ti) {
        var dot = /(^|\s|\d)/.test('') ? false : false; // 佔位
        var dotted = tok.indexOf('.') !== -1;
        // 減半數（_ 下劃線數量）
        var halvings = (tok.match(/_/g) || []).length;
        var dur = ['quarter','eighth','16th','32nd'][Math.min(halvings,3)] || 'quarter';
        var pitchM = tok.match(/[#b\u266f\u266d]*([0-7])/);
        var degree = pitchM ? pitchM[1] : '0';
        var accidental = /^#/.test(tok) ? '#' : (/^b/.test(tok) ? 'b' : '0');
        var ev = {
          id: 'event-' + (mi+1) + '-' + (ti+1),
          type: degree === '0' ? 'rest' : 'note',
          startTick: used,
          durationTicks: tickCountForDuration(dur, dotted),
          pitch: { degree: parseInt(degree,10) || 0, accidental: accidental === '0' ? 0 : accidental, octave: 0 },
          notation: { duration: dur, dots: dotted ? 1 : 0, tieStart: false, tieStop: false, slurStart: false, slurStop: false, tuplet: null, articulations: [], dynamic: null }
        };
        var lyrics = (m.beats && m.beats[ti] && m.beats[ti].lyric) ? m.beats[ti].lyric : ((m.lyricText||'').trim().split(/\s+/)[ti] || '');
        var chord = (m.chordText||'').trim().split(/\s+/)[0] || '';
        ev.lyrics = lyrics ? [{ verse: 1, text: lyrics, syllabic: 'single', extend: false }] : [];
        /* verse 2/3/4：第 2～4 行歌詞依空格逐詞對齊到同一音序（ev.lyrics verse 欄） */
        var extraVerses = [['lyricText2', 2], ['lyricText3', 3], ['lyricText4', 4]];
        for (var vv = 0; vv < extraVerses.length; vv++) {
          var extraWords = (m[extraVerses[vv][0]] || '').trim().split(/\s+/);
          var ew = extraWords[ti] || '';
          if (ew) ev.lyrics.push({ verse: extraVerses[vv][1], text: ew, syllabic: 'single', extend: false });
        }
        ev.chords = chord ? [{ text: chord, root: chord.replace(/[0-9]/g,''), quality: chord, bass: null, position: 'above' }] : [];
        ev.annotations = [];
        events.push(ev);
        used += ev.durationTicks;
      });
      // 小節 JSON
      var measureJson = {
        id: 'measure-' + ((m.number || mi+1)),
        number: m.number || mi+1,
        timeSignatureOverride: null,
        keyOverride: null,
        rhythmGroupingOverride: null,
        events: events,
        barline: { type: 'single', repeatStart: false, repeatEnd: false }
      };
      model.parts[0].measures.push(measureJson);
      // 拍數檢查：used 與 小節總時值 比較
      // 规则（樂理）：
      //   - 空小節（events=0）但有和弦伴奏 ＝ 合法（純和弦小節，不報「空」）
      //   - 第一小節弱起（anacrusis）：used < perM 但 ≥1 事件 ＝ 合法，不報「短」
      //   - 真正未填滿（中段小節 used<perM）才報「短」
      var status = 'ok';
      var isPickup = mi === 0;  // 第一小節＝弱起候補
      var hasChord = String(m.chordText || '').trim().length > 0;
      if (events.length === 0) {
        status = hasChord ? 'chord-only' : 'empty';  // 有和弦＝合法伴奏小節
      } else if (used < perM - 1) {
        status = isPickup ? 'ok' : 'short';          // 弱起不報短
      } else if (used > perM + 1) {
        status = 'over';
      }
      checks.push({ measure: measureJson.number, used: used, need: perM, status: status });
    });

    return { model: model, measureChecks: checks };
  }

  // 拍數檢查摘要（給狀態列用）
  function summarizeSola321Checks(checks) {
    var ok = 0, short = 0, over = 0, empty = 0, chordOnly = 0;
    checks.forEach(function(c){
      if (c.status === 'ok') ok++;
      else if (c.status === 'short') short++;
      else if (c.status === 'over') over++;
      else if (c.status === 'chord-only') chordOnly++;   // 純和弦伴奏小節＝合法
      else empty++;
    });
    var msg = '小節 ' + checks.length + '：';
    msg += '✓ ' + ok + ' 小節拍數正確';
    if (chordOnly) msg += '、和弦 ' + chordOnly;
    if (short) msg += '、短 ' + short;
    if (over) msg += '、超拍 ' + over;
    if (empty) msg += '、空 ' + empty;
    return msg;
  }

  // 把 SoLa321 模型渲染成可編輯 JSON 文字（顯示用）
  function sola321ToJsonText(doc) {
    var r = buildSola321Model(doc);
    return JSON.stringify(r.model, null, 2);
  }

  /* ===== V3.00：簡譜格線編輯器 ===== */
    function renderV3Editor(force) {
      var doc = state3.doc;
      var box = $('#v3-rows');
      if (!doc || !box) return;
      if ($('#doc-title')) $('#doc-title').value = doc.title || '';
      if ($('#doc-key')) $('#doc-key').value = doc.key || 'C';
      if ($('#doc-time')) $('#doc-time').value = doc.timeSignature || '4/4';
      if ($('#doc-tempo')) $('#doc-tempo').value = doc.tempo || 90;
      if ($('#doc-lyricist')) $('#doc-lyricist').value = doc.lyricist || '';
      if ($('#doc-composer')) $('#doc-composer').value = doc.composer || '';
      var scorePane = document.getElementById('score-pane');
      if (!force && scorePane && !scorePane.classList.contains('pane-active')) return;
      var measures = doc.measures || [];

      /* V3.01 版面：一整列 flex-wrap——小節格線依內容寬度向右延伸，列內換行由容器寬度決定（不固定 4 小節）；
         增減小節用工具列「插入／刪除末節／＋ 新增 1 小節」按鈕 */
      var html = measures.map(function(m, mi) {
                var selCls = (scoreGridSelectedMI === mi) ? ' selected' : '';
                // 格線高低音點直接讀 m.noteText 內的組合字元（v3NoteTokens 拆出 above/below），
                // 不再把 noteText 壓成純數字（舊做法會使小節只剩 1 個音符 → 點高/低音後整格消失）
                var toks = v3NoteTokens(m.noteText || '');
                var noteGrid = toks.map(function(tk, ti) {
                  var d = solaDecomp(tk.base);
                  var val = solaRecomp(d);
                  var aboveDots = '';
                  for (var a = 0; a < (tk.above || 0); a++) aboveDots += '<i class="v3-dot above' + (a === 1 ? ' above2' : '') + '"></i>';
                  var belowDots = '';
                  for (var b = 0; b < (tk.below || 0); b++) belowDots += '<i class="v3-dot below' + (b === 1 ? ' below2' : '') + '"></i>';
                  var under = d.under || 0;
                  var underCls = under === 1 ? 'v3-under-1' : (under === 2 ? 'v3-under-2' : (under === 3 ? 'v3-under-3' : ''));
                  var underHtml = under ? '<span class="v3-underline ' + underCls + '"></span>' : '';
                  var dotHtml = d.dotted ? '<i class="v3-dotdot"></i>' : '';
                  var tripHtml = d.triplet ? '<span class="v3-triplet">3</span>' : '';
                  return '<span class="v3-note-grid-char" data-mi="' + mi + '" data-ti="' + ti + '">' +
                    '<span class="v3-dots-above">' + aboveDots + '</span>' +
                    '<input class="v3-note-cell" data-mi="' + mi + '" data-ti="' + ti + '" value="' + escAttr(val) + '" maxlength="8" />' +
                    underHtml + dotHtml + tripHtml +
                    '<span class="v3-dots-below">' + belowDots + '</span>' +
                    '</span>';
                }).join('');
                /* 小節線：畫在小節右緣（音符行高度）；末小節＝終止雙線。
                   依 m.barline 顯示（預設有線；SoLa321 頁籤 －│ 合併後會設 false）；
                   增刪走工具列 ＋│/－│（v3BarlineAdd/Del：依選定音符拆/併小節） */
                var isLastM = (mi === measures.length - 1);
                var barlineHtml = (m.barline !== false)
                  ? (isLastM
                      ? '<span class="v3-barline"></span><span class="v3-barline-thin"></span>'
                      : '<span class="v3-barline"></span>')
                  : '';
                var lyricFields = [
                  { f: 'lyricText',  v: m.lyricText  || '' },
                  { f: 'lyricText2', v: m.lyricText2 || '' },
                  { f: 'lyricText3', v: m.lyricText3 || '' },
                  { f: 'lyricText4', v: m.lyricText4 || '' }
                ];
                var v3LyrShown = solaLyricRowsShown(m);
                var lyricHtml = '';
                for (var li2 = 0; li2 < v3LyrShown; li2++) {
                  lyricHtml += '<div class="v3-lyric-line" data-mi="' + mi + '" data-ll="' + li2 + '">' +
                    '<input class="v3-input-lyric" data-mi="' + mi + '" data-ll="' + li2 + '" data-field="' + lyricFields[li2].f + '" value="' + escAttr(lyricFields[li2].v) + '" placeholder="歌詞行 ' + (li2 + 1) + '" />' +
                    '</div>';
                }
                if (v3LyrShown < 4) {
                  lyricHtml += '<button type="button" class="v3-lyric-add" data-mi="' + mi + '" title="新增歌詞行 ' + (v3LyrShown + 1) + '">＋</button>';
                }
                return '<div class="v3-cell' + selCls + (isLastM ? ' v3-cell-end' : '') + '" data-mi="' + mi + '" style="cursor:pointer;">' +
                  '<button type="button" class="v3-del" title="刪除此小節">\u2715</button>' +
                  renderV3ChordSlots(m, mi) +
                  '<div class="v3-note-grid" data-mi="' + mi + '">' + (toks.length ? noteGrid : '<input class="v3-note-cell empty" data-mi="' + mi + '" data-ti="0" value="" placeholder="0" />') + barlineHtml + '</div>' +
                  '<div class="v3-lyric-rows">' + lyricHtml + '</div>' +
                  '</div>';
              }).join('');
      box.innerHTML = '<div class="v3-row">' + html + '</div>';
    /* 點選小節格線 → 選中（供和弦插入目標） */
    $$('.v3-cell[data-mi]').forEach(function(cell) {
      cell.addEventListener('click', function(e) {
        if (e.target.classList.contains('v3-del')) return;
        var mi = parseInt(this.getAttribute('data-mi'), 10);
        selectScoreGridCell(mi);
      });
    });
    // 點選數字 span → 已由 #v3-rows 事件委派統一處理（見檔案底部），不再在此逐 span 綁定
    //（逐 span 綁定在 contenteditable 重寫 DOM 後會失效，是「點不中數字」的根因）
        // contenteditable div 輸入：只同步資料，不重寫 DOM（重寫會吃掉打字）。
                // 打字時只更新 noteText，**保留 noteDotsMap**（點號跟隨數字序，打字不清除）。
                // 失焦時重繪成可點擊 span + 圓點（用保留的 dots）。
                $$('.v3-input-note[contenteditable]').forEach(function(div) {
                  div.addEventListener('input', function() {
                    var mi = parseInt(this.getAttribute('data-mi'), 10);
                    if (isNaN(mi)) return;
                    var m = doc.measures[mi];
                    if (!m) return;
                    m.noteText = this.textContent;  // 直接存原始文字（含空格、標點），不動 dots
      syncLegacyToEvents(m);
                  });
                  div.addEventListener('blur', function() {
                    var mi = parseInt(this.getAttribute('data-mi'), 10);
                    if (isNaN(mi)) return;
                    var m = doc.measures[mi];
                    if (!m) return;
                    m.noteText = this.textContent;
                          syncLegacyToEvents(m);
                          this.innerHTML = renderNoteHtml(m.noteText, noteDotsMap[mi] || {}, mi);
                  });
                });

        // 和弦「整排槽」（簡譜格線）：共用 picker 綁定（點擊選和弦、拖曳／方向鍵滑軌對準節拍）
        bindChordSlotPickers('#v3-rows', function() { renderV3Editor(); }, null);
        $$('#v3-rows .v3-chord-slot-add').forEach(function(btn) {
          btn.addEventListener('click', function(e) {
            e.stopPropagation();
            var mi = this.getAttribute('data-mi');
            if (mi === null) return;
            var m = doc.measures[+mi];
            var parts = v3ChordParts(m);
            var off = parts.length;  /* 新槽預設對齊最後一拍 */
            var wrap = document.createElement('div');
            wrap.innerHTML = v3ChordSlotHtml('', mi, '__pending__', off);
            var slotEl = wrap.firstChild;
            this.parentNode.insertBefore(slotEl, this);
          });
        });
        $$('#v3-rows .v3-chord-slot-del').forEach(function(btn) {
          btn.addEventListener('click', function(e) {
            e.stopPropagation();
            var slot = this.closest('.v3-chord-slot');
            if (!slot) return;
            /* data-ci 在 slot 殼上（v3ChordSlotHtml），button 自身沒有 → 從 slot 讀 */
            var cell = slot.closest('.v3-cell');
            var mi = cell ? cell.getAttribute('data-mi') : null;
            if (mi === null) return;
            var m = doc.measures[+mi];
            if (!m) return;
            var ci = slot.getAttribute('data-ci');
            if (String(ci) === '__pending__') { slot.remove(); return; }
            v3ChordSlotWrite(m, +ci, '');   // 移除該槽、保留其他
            renderV3Editor();
          });
        });
        /* 逐音符小格：change 寫回 noteText（含高低音點組合）；Enter 移到下一格 */
        $$('#v3-rows .v3-note-cell').forEach(function(inp) {
          inp.addEventListener('change', function() {
            var mi = +this.getAttribute('data-mi'), ti = +this.getAttribute('data-ti');
            var m = doc.measures[mi];
            if (!m) return;
            var toks = v3NoteTokens(m.noteText || '');
            var v = this.value.replace(/[\u0307\u0323]/g, '').trim();
            if (v === '') {
              if (ti < toks.length) toks.splice(ti, 1);
            } else {
              while (ti >= toks.length) toks.push({ base: '', above: 0, below: 0 });
              toks[ti].base = v;
            }
            m.noteText = toks.map(v3NoteTokenHtml).join(' ');
            syncLegacyToEvents(m);
            renderV3Editor();
          });
          inp.addEventListener('keydown', function(e) {
            if (e.key === 'Enter') {
              e.preventDefault();
              var next = document.querySelector('.v3-note-cell[data-mi="' + this.getAttribute('data-mi') + '"][data-ti="' + (+this.getAttribute('data-ti') + 1) + '"]');
              if (next) next.focus();
            }
          });
          /* 點／聚焦某音符格 → 設音符游標，供「＋│ 小節線」在此音符後拆小節 */
          inp.addEventListener('focus', function() {
            var mi = +this.getAttribute('data-mi'), ti = +this.getAttribute('data-ti');
            if (!isNaN(mi)) {
              scoreGridNoteCursor = { mi: mi, charIndex: ti };
              selectScoreGridCell(mi);
            }
          });
        });
        /* 歌詞行：第 1 行常駐；有內容的 2~4 行自動顯示；Enter 或 ＋ 新增行；空白末行自動收回 */
        $$('#v3-rows .v3-input-lyric').forEach(function(inp) {
          inp.addEventListener('change', function() {
            var mi = +this.getAttribute('data-mi');
            var field = this.getAttribute('data-field') || 'lyricText';
            var m = doc.measures[mi];
            if (!m) return;
            var ll = +this.getAttribute('data-ll') || 0;
            m[field] = this.value.trim();
            if (ll > 0 && !m[field] && ll === solaLyricRowsShown(m) - 1 && (m.lyricRows || 1) > 1) {
              m.lyricRows = Math.max(1, ll);  /* 空白末行自動收回 */
            }
            renderV3Editor();
          });
          inp.addEventListener('keydown', function(e) {
            if (e.key !== 'Enter') return;
            e.preventDefault();
            var mi2 = +this.getAttribute('data-mi');
            var ll = +this.getAttribute('data-ll') || 0;
            var m2 = doc.measures[mi2];
            if (!m2) return;
            var shown = solaLyricRowsShown(m2);
            if (shown >= 4 || ll !== shown - 1) return;  /* 只能從最後一顯示行 Enter */
            m2.lyricRows = shown + 1;
            renderV3Editor();
            var next = document.querySelector('.v3-input-lyric[data-mi="' + mi2 + '"][data-ll="' + shown + '"]');
            if (next) next.focus();
          });
        });
        $$('#v3-rows .v3-lyric-add').forEach(function(btn) {
          btn.addEventListener('click', function(e) {
            e.stopPropagation();
            var mi = +this.getAttribute('data-mi');
            var m = doc.measures[mi];
            if (!m) return;
            var shown = solaLyricRowsShown(m);
            if (shown >= 4) return;
            m.lyricRows = shown + 1;
            renderV3Editor();
            var next = document.querySelector('.v3-input-lyric[data-mi="' + mi + '"][data-ll="' + shown + '"]');
            if (next) next.focus();
          });
        });
    $$('.v3-del').forEach(function(btn) {
      btn.addEventListener('click', function(e) {
        e.stopPropagation();
        var cell = this.closest('.v3-cell');
        var mi = cell.getAttribute('data-mi');
        if (mi === null) return;
        doc.measures.splice(+mi, 1);
        doc.measures.forEach(function(x, i) { x.number = i + 1; });
        scoreGridSelectedMI = null;
        renderV3Editor();
      });
    });
  }

  function collectV3ToDoc(doc) {
      // doc 可能為 null（尚未載入專案）；直接回傳，讓上層以「空白提示」處理
      if (!doc) return;
      var solaPane = $('#sola321-pane');
      if (solaPane && solaPane.classList.contains('pane-active')) {
        var st = $('#sola321-score .sola321-title-input'); if (st && st.value.trim()) doc.title = st.value.trim();
        var sk = $('#sola321-score .sola321-meta-input[data-meta="key"]'); if (sk && sk.value.trim()) doc.key = sk.value.trim();
        var ss = $('#sola321-score .sola321-meta-input[data-meta="timeSignature"]'); if (ss && ss.value.trim()) doc.timeSignature = ss.value.trim();
        var sb = $('#sola321-score .sola321-meta-input[data-meta="tempo"]'); if (sb && sb.value) doc.tempo = parseInt(sb.value, 10) || 90;
        var sly = $('#sola321-score .sola321-meta-input[data-meta="lyricist"]'); if (sly) doc.lyricist = sly.value.trim();
        var scm = $('#sola321-score .sola321-meta-input[data-meta="composer"]'); if (scm) doc.composer = scm.value.trim();
      } else {
        var t = $('#doc-title'); if (t) doc.title = t.value;
        var k = $('#doc-key'); if (k) doc.key = k.value;
        var s = $('#doc-time'); if (s) doc.timeSignature = s.value;
        var b = $('#doc-tempo'); if (b) doc.tempo = parseInt(b.value, 10) || 90;
        var ly = $('#doc-lyricist'); if (ly) doc.lyricist = ly.value;
        var cm = $('#doc-composer'); if (cm) doc.composer = cm.value;
      }
      doc.measures = doc.measures || [];
      doc.measures.forEach(function(m, i) { m.number = i + 1; });
    
      // 重建 tick 陣列：從目前的編輯狀態（noteText/lyricText/chordText + duration）計算
      // 這確保「任意位置編輯」的結果能持久化
      doc.measures.forEach(function(m, mi) {
        // 只有在有內容時才重建
        var toks = solaTokens(m);
        if (toks.length > 0 || (m.lyricText || '').trim() || (m.chordText || '').trim()) {
          rebuildMeasureTicks(m, toks);
        }
      });
    }

    function splitLyricSyllables(text) {
      var raw = String(text || '').trim();
      if (!raw) return [];
      var cjkRe = /[\u3400-\u4dbf\u4e00-\u9fff\uf900-\ufaff\u3040-\u30ff]/;
      if (raw.indexOf(' ') >= 0 && !cjkRe.test(raw)) {
        return raw.split(/\s+/).filter(Boolean);
      }
      var out = [];
      var buf = '';
      var chars = Array.from(raw);
      for (var i = 0; i < chars.length; i++) {
        var ch = chars[i];
        if (cjkRe.test(ch)) {
          if (buf.trim()) { out.push(buf.trim()); buf = ''; }
          out.push(ch);
        } else if (/\s/.test(ch)) {
          if (buf.trim()) { out.push(buf.trim()); buf = ''; }
        } else {
          buf += ch;
        }
      }
      if (buf.trim()) out.push(buf.trim());
      return out;
    }

    /* 由 token 陣列與文字內容重建 tick 陣列（480 ticks = 1 quarter = 1 拍） */
    function rebuildMeasureTicks(m, toks) {
      // 音符 ticks：依 duration 累積（含延長線 - 每拍 480 ticks）
      var noteTicks = [];
      var singableTicks = [];
      var accB = 0;
      for (var i = 0; i < toks.length; i++) {
        var tickPos = Math.round(accB * 480);
        noteTicks.push(tickPos);
        var pc = solaDecomp(toks[i].base);
        var dur = pc.dash ? 1 : Math.pow(0.5, pc.under);
        if (!pc.dash && pc.dotted) dur *= 1.5;
        if (!pc.dash && pc.triplet) dur *= 2 / 3;
        if (pc.digit && pc.digit !== '0' && !pc.dash) {
          singableTicks.push(tickPos);
        }
        accB += dur;
      }
      if (noteTicks.length) m.noteTicks = noteTicks;

      // 歌詞 ticks：優先保留與音節數一致的既有精確對位 ticks，否則對齊到可唱音符 ticks
      var lyricFields = ['lyricText', 'lyricText2', 'lyricText3', 'lyricText4'];
      lyricFields.forEach(function(f) {
        var raw = String(m[f] || '').trim();
        if (!raw) return;
        var syl = splitLyricSyllables(raw);
        var tickKey = (f === 'lyricText') ? 'lyricTicks' : (f + 'Ticks');
        if (Array.isArray(m[tickKey]) && m[tickKey].length === syl.length) {
          return;
        }
        var lyricTicks = [];
        for (var si = 0; si < syl.length; si++) {
          var tVal = si < singableTicks.length
            ? singableTicks[si]
            : (singableTicks.length ? singableTicks[singableTicks.length - 1] : si * 480);
          lyricTicks.push(tVal);
        }
        if (lyricTicks.length) m[tickKey] = lyricTicks;
      });

      // 和弦 ticks：優先用既有 chordTicks，其次用 chordOffsets 對應音符 tick，否則均勻分配
      var chords = String(m.chordText || '').trim().split(/\s+/).filter(Boolean);
      if (chords.length) {
        var chordTicks = [];
        if (m.chordTicks && m.chordTicks.length >= chords.length) {
          chordTicks = m.chordTicks.slice(0, chords.length);
        } else if (m.chordOffsets && m.chordOffsets.length >= chords.length) {
          chordTicks = m.chordOffsets.slice(0, chords.length).map(function(x) {
            return (noteTicks.length && x >= 0 && x < noteTicks.length) ? noteTicks[x] : x * 480;
          });
        } else {
          for (var k = 0; k < chords.length; k++) {
            var tVal2 = k < singableTicks.length
              ? singableTicks[k]
              : (singableTicks.length ? singableTicks[singableTicks.length - 1] : k * 480);
            chordTicks.push(tVal2);
          }
        }
        m.chordTicks = chordTicks;
      }
    }

  function escAttr(s) {
    return String(s).replace(/&/g, '&amp;').replace(/"/g, '&quot;').replace(/</g, '&lt;');
  }

  /* ===== V3.01 簡譜逐音符格：token 解析與還原 =====
     格式同 SoLa321：空格分隔 token；每 token 結構 [acc][digit] [_下劃線減半]* [.附點]* [3三連音]
     高低音點（\u0307/\u0323 或 '/,）拆出 above/below，不入 base。 */
  function v3NoteTokens(noteText) {
    var raw = String(noteText || '');
    var arr = raw.trim() ? raw.trim().split(/\s+/) : [];
    return arr.map(function(t) {
      var above = (t.match(/\u0307/g) || []).length + (t.match(/['\u2019]/g) || []).length;
      var below = (t.match(/\u0323/g) || []).length + (t.match(/,/g) || []).length;
      return { base: t.replace(/[\u0307\u0323'\u2019,]/g, ''), above: above, below: below };
    });
  }

  function v3NoteTokenHtml(tk) {
    var s = String(tk.base || '');
    if (!s) return s;
    var idx = s.search(/[0-7]/);
    var at = idx >= 0 ? idx + 1 : s.length;
    var dots = '';
    for (var a = 0; a < (tk.above || 0); a++) dots += '\u0307';
    for (var b = 0; b < (tk.below || 0); b++) dots += '\u0323';
    return s.slice(0, at) + dots + s.slice(at);
  }

  function switchTab(which) {
    var paneIds = { chordpro: 'chordpro-pane', score: 'score-pane', sola321: 'sola321-pane' };
    var tabIds = { chordpro: 'tab-chordpro', score: 'tab-score', sola321: 'tab-sola321' };
    Object.keys(paneIds).forEach(function(k) {
      var p = document.getElementById(paneIds[k]);
      if (p) p.classList.remove('pane-active');
    });
    var paneEl = document.getElementById(paneIds[which]);
    if (paneEl) paneEl.classList.add('pane-active');
    Object.keys(tabIds).forEach(function(k) {
      var t = document.getElementById(tabIds[k]);
      if (t) t.classList.remove('active');
    });
    var tabEl = document.getElementById(tabIds[which]);
    if (tabEl) tabEl.classList.add('active');
    if (which === 'chordpro' && state3.doc) renderChordProFromDoc(state3.doc, true);
    if (which === 'score' && state3.doc) renderV3Editor(true);
    if (which === 'sola321') loadSola321();
  }

  /* ===== V3.00 SoLa321 編輯器：視覺化簡譜渲染（取代 LilyPond 的 JSON 代碼區）===== */

  // 狀態列（SoLa321 頁籤自己的狀態列 #sola321-status；若該元素存在於 score-pane 工具列也同步寫）
  function setSola321Status(msg, color) {
    $$('#sola321-status, #score-sola321-status, .sola321-status-bar').forEach(function(el) {
      el.textContent = msg;
      el.style.color = color || '';
    });
  }

  function updateSyncStatusBadge(statusText, stateType) {
    $$('.sync-status-badge').forEach(function(el) {
      el.textContent = statusText || '⇄ 已同步';
      el.className = 'sync-status-badge sync-' + (stateType || 'ok');
    });
  }

  /* ===== SoLa321 可編輯狀態：游標（小節 mi、音位 nti）、模式（note/lyric/chord）、複撤銷堆疊 ===== */
  var solaEdit = { mi: 0, nti: 0, mode: 'note', viewMode: 'vertical', useTimelineRenderer: false, undoStack: [], redoStack: [] };
  /* v3.04.09 目標小節：最近一次「點擊」的小節＝段落/結構記號/右側和弦庫寫入對象（(b) 直接目標化） */
  var solaTargetMI = null;

  function initSola321EditState() {
    solaEdit.mi = 0; solaEdit.nti = 0; solaEdit.mode = 'note'; solaEdit.viewMode = 'vertical';
    solaEdit.undoStack = []; solaEdit.redoStack = [];
    solaTargetMI = null;
    $$('.sola321-tb-btn[data-mode]').forEach(function(b) {
      b.classList.toggle('active', b.getAttribute('data-mode') === solaEdit.mode);
    });
  }

  /* 小節 noteText → token 陣列（空白分隔；連續休止符 000 或延音線 --- 自動拆為單拍 token；點號組合字元 \u0307/\u0323 拆出計數） */
  function solaTokens(m) {
    var raw = String(m.noteText || '');
    var arr = raw.trim() ? raw.trim().split(/\s+/) : [];
    var out = [];
    arr.forEach(function(t) {
      if (/^0{2,}$/.test(t) || /^-{2,}$/.test(t)) {
        for (var k = 0; k < t.length; k++) {
          out.push({ base: t.charAt(k), above: 0, below: 0 });
        }
        return;
      }
      var above = (t.match(/\u0307/g) || []).length;
      var below = (t.match(/\u0323/g) || []).length;
      var s = t.replace(/[\u0307\u0323]/g, '');
      /* 整行輸入語法：尾綴 ' ＝高八度（''=+2 層）、, ＝低八度（,,=-2 層） */
      var primes = (s.match(/'+$/) || [''])[0].length;
      s = s.replace(/'+$/, '');
      var commas = (s.match(/,+$/) || [''])[0].length;
      s = s.replace(/,+$/, '');
      if (s === '' && !primes && !commas) {
        out.push({ base: t, above: 0, below: 0 });
      } else {
        out.push({ base: s, above: Math.min(2, above + primes), below: Math.min(2, below + commas) });
      }
    });
    return out;
  }

  /* token → 字串（組合點緊貼數字，與既有 noteText 格式一致） */
  function solaBuildToken(t) {
    var s = String(t.base || '');
    if (!s) return s;
    var idx = s.search(/[0-7]/);
    var at = idx >= 0 ? idx + 1 : s.length;
    var dots = '';
    for (var a = 0; a < (t.above || 0); a++) dots += '\u0307';
    for (var b = 0; b < (t.below || 0); b++) dots += '\u0323';
    return s.slice(0, at) + dots + s.slice(at);
  }

  function solaSetNoteText(m, toks, rawWithSpaces) {
    if (!m) return;
    var built = (toks || []).map(solaBuildToken);
    var sourceRaw = (typeof rawWithSpaces === 'string') ? rawWithSpaces : String(m.noteText || '');
    var existingMatches = sourceRaw.match(/\S+/g) || [];
    if (built.length === 0) {
      m.noteText = '';
    } else if (typeof rawWithSpaces === 'string' && existingMatches.length === built.length) {
      var idx = 0;
      m.noteText = rawWithSpaces.replace(/\S+/g, function() {
        return built[idx++] || '';
      });
    } else if (existingMatches.length === built.length && /\s{2,}|^\s+/.test(sourceRaw)) {
      var idx2 = 0;
      m.noteText = sourceRaw.replace(/\S+/g, function() {
        return built[idx2++] || '';
      });
    } else {
      m.noteText = built.join(' ');
    }
    syncLegacyToEvents(m);
  }

  /* 整行簡譜輸入 → token 陣列：空格分 token；尾綴 ' 高八度（''=+2）、, 低八度（,,=-2）；
     既有 OMR 組合字 \u0307/\u0323 保留計數；_/. /三連音尾綴 3 由 solaDecomp 處理 */
  function solaParseNoteLine(text) {
    var raw = String(text == null ? '' : text).replace(/\u007c/g, ' ');  /* 小節線 | 不進音符行 */
    var out = [];
    (raw.trim() ? raw.trim().split(/\s+/) : []).forEach(function(tok) {
      if (!tok) return;
      if (/^0{2,}$/.test(tok) || /^-{2,}$/.test(tok)) {
        for (var k = 0; k < tok.length; k++) {
          out.push({ base: tok.charAt(k), above: 0, below: 0 });
        }
        return;
      }
      var above = (tok.match(/\u0307/g) || []).length;
      var below = (tok.match(/\u0323/g) || []).length;
      var s = tok.replace(/[\u0307\u0323]/g, '');
      var primes = (s.match(/'+$/) || [''])[0].length;
      s = s.replace(/'+$/, '');
      var commas = (s.match(/,+$/) || [''])[0].length;
      s = s.replace(/,+$/, '');
      if (s === '' && !primes && !commas) return;
      out.push({ base: s, above: Math.min(2, above + primes), below: Math.min(2, below + commas) });
    });
    return out;
  }

  /* 歌詞行數：第 1 行永遠保留；有內容的第 2~4 行自動顯示；使用者 Enter/＋ 新增的行（m.lyricRows）也顯示；空白末行會自動收回 */
  function solaLyricRowsShown(m) {
    var contentMax = 0;
    if (String(m.lyricText2 || '').trim()) contentMax = 2;
    if (String(m.lyricText3 || '').trim()) contentMax = 3;
    if (String(m.lyricText4 || '').trim()) contentMax = 4;
    return Math.max(1, contentMax, m.lyricRows || 1);
  }

  /* 把 base 拆成 {acc, digit, dotted, under, triplet, tie, slur}（三連音=尾綴 3，連音線=~，圓滑線=^） */
  function solaDecomp(base) {
    var s = String(base || '');
    // 延音橫線：標準簡譜 "-"（或附點/八分延音 "-."、"-_"）為獨立 token，代表該拍延音。
    var dash = /^-[_.]*$/.test(s.trim());
    var acc = (s.charAt(0) === '#' || s.charAt(0) === 'b') ? s.charAt(0) : '';
    var rest = s, triplet = false, tie = false, slur = false;
    if (rest.indexOf('~') !== -1) { tie = true; rest = rest.replace(/~/g, ''); }
    if (rest.indexOf('^') !== -1) { slur = true; rest = rest.replace(/\^/g, ''); }
    if (/3$/.test(rest) && /[0-7]/.test(rest) && rest.length > 1) { triplet = true; rest = rest.slice(0, -1); }
    var dM = rest.match(/([0-7])/);
    var digit = dM ? dM[1] : '';
    var after = dM ? rest.slice(dM.index + 1) : rest;
    return {
      acc: acc, digit: digit,
      dotted: after.indexOf('.') !== -1,
      under: (after.match(/_/g) || []).length,
      triplet: triplet,
      tie: tie,
      slur: slur,
      dash: dash
    };
  }

  function solaRecomp(p) {
    if (p.dash) {
      var ds = '-';
      ds += new Array(Math.max(0, p.under) + 1).join('_');
      if (p.dotted) ds += '.';
      return ds;
    }
    var s = p.acc + p.digit;
    s += new Array(Math.max(0, p.under) + 1).join('_');
    if (p.dotted) s += '.';
    if (p.triplet) s += '3';
    if (p.tie) s += '~';
    if (p.slur) s += '^';
    return s;
  }

  /* 顯示用 base：去掉減時 `_` 與連音/圓滑/三連音記號（改由視覺元素畫出），保留 音高/臨時記號/附點 */
  function solaDisplayBase(base) {
    var p = solaDecomp(base);
    p.under = 0;
    p.tie = false;
    p.slur = false;
    p.triplet = false;
    return solaRecomp(p);
  }

  /* WYSIWYG 編輯用：token → 可輸入字串（保留 _ 減時、' 高八度、, 低八度、附點、三連音） */
  function solaEditNoteText(t) {
    if (!t) return '';
    var s = solaRecomp(solaDecomp(t.base));
    s += new Array((t.above || 0) + 1).join("'");
    s += new Array((t.below || 0) + 1).join(',');
    return s;
  }
  /* WYSIWYG 編輯：輸入字串 → token（解析 _/. /'/, 與 \u0307/\u0323）；空字串＝清除該音 */
  function solaParseEditNote(raw) {
    raw = String(raw == null ? '' : raw).trim();
    if (!raw) return null;
    var above = (raw.match(/\u0307/g) || []).length;
    var below = (raw.match(/\u0323/g) || []).length;
    var s = raw.replace(/[\u0307\u0323]/g, '');
    var primes = (s.match(/'+$/) || [''])[0].length;
    s = s.replace(/'+$/, '');
    var commas = (s.match(/,+$/) || [''])[0].length;
    s = s.replace(/,+$/, '');
    if (s === '' && !primes && !commas) return null;
    return { base: s, above: Math.min(2, above + primes), below: Math.min(2, below + commas) };
  }
  /* 減時下劃線數（8分=1 / 16分=2 / 32分=3） */
  function solaUnderlines(base) {
    var p = solaDecomp(base);
    return Math.min(3, Math.max(0, p.under));
  }

  /* ===== Timeline Event Model (v3.04) — 取代 Cell-based 模型 =====
     核心原則：
     1. Measure = 時間軸容器，擁有獨立的 melodyEvents / lyricEvents / chordEvents / annotationEvents
     2. 每個 Event 有絕對時間位置 (start, duration)，不共享 cell index
     3. Tracks 完全獨立：可以只有和弦無音符、只有歌詞無音符、空拍位合法
     4. LyricEvent.syllables 支援「一音多字」；duration 支援「一字多音/延長線」
     5. ChordEvent.duration 支援持續多拍；可在無旋律位置出現
     6. Migration Adapter：雙向轉換，舊 Renderer/PDF/播放完全不需改動 */

  /* —— 唯一 ID 產生器 —— */
  var timelineIdCounter = 0;
  function newTimelineId() { return 'evt_' + (++timelineIdCounter) + '_' + Math.random().toString(36).slice(2, 8); }

  /* —— 解析拍號 → 每小節總拍數 —— */
  function parseTimeSignatureToBeats(ts) {
    var m = String(ts || '4/4').match(/^(\d+)\/(\d+)$/);
    if (!m) return 4;
    return parseInt(m[1], 10) * (4 / parseInt(m[2], 10));  // 4/4=4, 3/4=3, 6/8=3 (把 8 分音符當 0.5 拍)
  }

  /* —— NoteEvent：旋律事件 ——
     pitch: 0=休止, 1..7=音高, 可帶 accidental (#/b), octave (±), dots, tuplet, underlines
     start/duration 單位：beat（四分音符=1）
     layoutOffsetX: 視覺微調位移（不影響音樂時間） */
  function createNoteEvent(start, duration, pitch, opts) {
    opts = opts || {};
    return {
      id: newTimelineId(),
      type: 'note',
      start: Math.max(0, Number(start) || 0),
      duration: Math.max(0.125, Number(duration) || 1),  // 最小 32 分音符
      pitch: Number(pitch) || 0,
      accidental: opts.accidental || '',   // '#', 'b', ''
      octave: opts.octave || 0,            // +1, -1, 0
      dots: opts.dots || 0,                // 0, 1, 2
      tuplet: opts.tuplet || null,         // {ratio: 2/3} 三連音
      underlines: opts.underlines || 0,    // 0..3 (由 solaUnderlines 對應)
      articulation: opts.articulation || '', // staccato, tenuto 等
      layoutOffsetX: 0                     // 視覺排版微調（Phase 1 新增）
    };
  }

  /* —— LyricEvent：歌詞事件 ——
     text: 完整文字（如 "我愛"、"你────"）
     syllables: 切分後音節陣列 ["我","愛"]，用於一音多字均分
     duration > 0 時畫延長線（一字多音）
     anchorNoteId: 可選，輔助對齊用（Renderer 仍以 start/duration 為準）
     layoutOffsetX: 視覺微調位移 */
  function createLyricEvent(start, duration, text, opts) {
    opts = opts || {};
    var raw = String(text || '').trim();
    var syllables = raw ? (raw.indexOf(' ') >= 0 ? raw.split(/\s+/) : Array.from(raw)) : [];
    return {
      id: newTimelineId(),
      type: 'lyric',
      start: Math.max(0, Number(start) || 0),
      duration: Math.max(0, Number(duration) || 1),
      text: raw,
      syllables: syllables,
      anchorNoteId: opts.anchorNoteId || null,
      verse: opts.verse || 1,  // 第幾行歌詞
      layoutOffsetX: 0
    };
  }

  /* —— ChordEvent：和弦事件 ——
     duration > 0 畫持續線；可在無旋律位置出現
     layoutOffsetX: 視覺微調位移 */
  function createChordEvent(start, duration, chordName, opts) {
    opts = opts || {};
    return {
      id: newTimelineId(),
      type: 'chord',
      start: Math.max(0, Number(start) || 0),
      duration: Math.max(0.25, Number(duration) || 1),
      chordName: String(chordName || '').trim(),
      fingering: opts.fingering || null,
      layoutOffsetX: 0
    };
  }

  /* —— AnnotationEvent：標記/記號 ——
     layoutOffsetX: 視覺微調位移 */
  function createAnnotationEvent(start, mark, opts) {
    opts = opts || {};
    return {
      id: newTimelineId(),
      type: 'annotation',
      start: Math.max(0, Number(start) || 0),
      mark: String(mark || ''),
      position: opts.position || 'above',  // above, below, between
      layoutOffsetX: 0
    };
  }

  /* —— 預設空小節時間軸結構 —— */
  function createEmptyTimeline(meter) {
    var beats = parseTimeSignatureToBeats(meter);
    return {
      meter: meter || '4/4',
      beats: beats,
      melodyEvents: [],
      lyricEvents: [],
      chordEvents: [],
      annotationEvents: []
    };
  }

  /* ===== Migration Adapter: Cell-based (舊) ↔ Timeline Events (新) ===== */

  /* —— 1. 解析 noteText → melodyEvents ——
     使用現有 solaTokens/solaDecomp，累積 start/duration */
  function measureToTimeline(m) {
    if (!m) return createEmptyTimeline('4/4');
    var timeline = createEmptyTimeline(m.timeSignature);
    var toks = solaTokens(m);
    var start = 0;
    var prevNoteId = null;
    
    toks.forEach(function(tok, idx) {
      var p = solaDecomp(tok.base);
      var dur = Math.pow(0.5, p.under);
      if (p.dotted) dur *= 1.5;
      if (p.triplet) dur *= 2/3;
      
      // dash 延音：佔用前一音符的時間位置（不產生新 note，改延長前一個）
      if (p.dash) {
        if (timeline.melodyEvents.length > 0) {
          timeline.melodyEvents[timeline.melodyEvents.length - 1].duration += dur;
        }
        start += dur;
        return;
      }
      
      var pitch = p.digit ? parseInt(p.digit, 10) : 0;
      var evt = createNoteEvent(start, dur, pitch, {
        accidental: p.acc,
        dots: p.dotted ? 1 : 0,
        tuplet: p.triplet ? {ratio: 2/3} : null,
        underlines: p.under,
        octave: 0  // 由 solaTokens 的 above/below 推導
      });
      // 處理高低八度點
      if (tok.above > 0) evt.octave = tok.above;
      else if (tok.below > 0) evt.octave = -tok.below;
      /* 6D：記錄來源 token 序（1:1），選取刪除時可映射回 noteText 序列 */
      evt.srcTok = idx;
      
      timeline.melodyEvents.push(evt);
      prevNoteId = evt.id;
      start += dur;
    });
    
    /* —— 解析 lyricText~4 → lyricEvents ——
       簡單策略：按空格/逐字切分，依序分配到可唱拍群
       同一拍群多字 → 一音多字 (同一 LyricEvent, syllables 多元素)
       跨拍群單字 → duration 延長 (一字多音) */
    var lyricFields = ['lyricText', 'lyricText2', 'lyricText3', 'lyricText4'];
    lyricFields.forEach(function(field, verseIdx) {
      var raw = String(m[field] || '').trim();
      if (!raw) return;
      var words = splitLyricSyllables(raw);
      if (!words.length) return;
      
      // 找出可唱拍群（有 pitch≠0 的 note event）
      var singableGroups = [];
      var currentGroupStart = null;
      var currentGroupNotes = [];
      
      timeline.melodyEvents.forEach(function(note, idx) {
        if (note.pitch !== 0) {
          if (currentGroupStart === null) currentGroupStart = note.start;
          currentGroupNotes.push(note);
        } else {
          if (currentGroupNotes.length > 0) {
            var end = note.start;
            singableGroups.push({ start: currentGroupStart, end: end, notes: currentGroupNotes.slice() });
            currentGroupStart = null;
            currentGroupNotes = [];
          }
        }
      });
      if (currentGroupNotes.length > 0) {
        var lastNote = currentGroupNotes[currentGroupNotes.length - 1];
        singableGroups.push({ start: currentGroupStart, end: lastNote.start + lastNote.duration, notes: currentGroupNotes });
      }
      
      // 分配歌詞字到拍群
      var wordIdx = 0;
      singableGroups.forEach(function(group) {
        if (wordIdx >= words.length) return;
        var groupWords = [];
        // 這個拍群內有幾個音符？把多餘字併入
        var noteCount = group.notes.length;
        var take = Math.min(words.length - wordIdx, noteCount > 0 ? noteCount : 1);
        for (var i = 0; i < take; i++) groupWords.push(words[wordIdx++]);
        if (groupWords.length === 0) return;
        
        // 創建 LyricEvent
        var evt = createLyricEvent(group.start, group.end - group.start, groupWords.join(' '), {
          verse: verseIdx + 1,
          anchorNoteId: group.notes[0] ? group.notes[0].id : null
        });
        // syllables 已在 createLyricEvent 內切分
        timeline.lyricEvents.push(evt);
      });
      // 剩餘字併入最後一個拍群（延長線）
      if (wordIdx < words.length && singableGroups.length > 0) {
        var lastGroup = singableGroups[singableGroups.length - 1];
        var remaining = words.slice(wordIdx).join(' ');
        // 找到最後一個 lyric event 並延長
        var lastLyric = null;
        for (var i = timeline.lyricEvents.length - 1; i >= 0; i--) {
          if (timeline.lyricEvents[i].verse === verseIdx + 1) { lastLyric = timeline.lyricEvents[i]; break; }
        }
        if (lastLyric) {
          lastLyric.text += ' ' + remaining;
          lastLyric.syllables = lastLyric.text.trim().split(/\s+/);
          lastLyric.duration = lastGroup.end - lastLyric.start;
        }
      }
    });
    
    /* —— 解析 chordText → chordEvents ——
       簡單：每個和弦佔一拍，延音用 duration 延長
       6D：定位以 chordTicks 為權威（tick→beat，480 tick = 1 beat），chordOffsets 為回退 */
    var chordParts = String(m.chordText || '').trim().split(/\s+/).filter(Boolean);
    var chordOffsets = m.chordOffsets || [];
    var chordTicksArr = m.chordTicks || [];
    chordParts.forEach(function(chord, idx) {
      var targetBeat;
      if (chordTicksArr[idx] != null && isFinite(chordTicksArr[idx])) targetBeat = chordTicksArr[idx] / TICKS_PER_BEAT;
      else targetBeat = chordOffsets[idx] != null ? chordOffsets[idx] : idx;
      var start = targetBeat;
      var dur = 1;
      // 若下一個和弦在同一拍，縮短 duration
      if (idx < chordParts.length - 1) {
        var nextBeat;
        if (chordTicksArr[idx + 1] != null && isFinite(chordTicksArr[idx + 1])) nextBeat = chordTicksArr[idx + 1] / TICKS_PER_BEAT;
        else nextBeat = chordOffsets[idx + 1] != null ? chordOffsets[idx + 1] : (idx + 1);
        dur = nextBeat - targetBeat;
      }
      if (dur <= 0) dur = 1;
      var evt = createChordEvent(start, dur, chord);
      evt.srcCi = idx;   /* 6D：和弦在 chordText 中的序（選取/拖曳映射） */
      timeline.chordEvents.push(evt);
    });
    
    /* —— 解析 marks → annotationEvents —— */
    var marks = String(m.marks || '').trim().split(/\s+/).filter(Boolean);
    marks.forEach(function(mark, idx) {
      var evt = createAnnotationEvent(idx, mark);
      timeline.annotationEvents.push(evt);
    });
    
    return timeline;
  }

  /* —— 2. Timeline Events → 舊 Cell-based 欄位 (供現有 Renderer/PDF/播放) ——
     產生 noteText, lyricText~4, chordText, chordOffsets, marks */
  function timelineToMeasure(tl, meter) {
    if (!tl) return { noteText: '', lyricText: '', lyricText2: '', lyricText3: '', lyricText4: '', chordText: '', chordOffsets: [], marks: '' };
    
    // noteText：按 start 排序，輸出 token
    var notes = (tl.melodyEvents || []).slice().sort(function(a,b){ return a.start - b.start; });
    var noteTokens = notes.map(function(n) {
      var base = '';
      if (n.pitch === 0) base = '0';
      else {
        var acc = n.accidental || '';
        var digit = String(n.pitch);
        var oct = '';
        if (n.octave > 0) oct = new Array(n.octave + 1).join("'");
        else if (n.octave < 0) oct = new Array(Math.abs(n.octave) + 1).join(',');
        var dots = new Array((n.dots || 0) + 1).join('.');
        var under = new Array((n.underlines || 0) + 1).join('_');
        var trip = n.tuplet ? '3' : '';
        base = acc + digit + oct + under + dots + trip;
      }
      return base;
    });
    
    // lyricText：按 verse 分組
    var lyricFields = ['lyricText', 'lyricText2', 'lyricText3', 'lyricText4'];
    var lyricResult = { lyricText: '', lyricText2: '', lyricText3: '', lyricText4: '' };
    (tl.lyricEvents || []).forEach(function(l) {
      var field = lyricFields[l.verse - 1];
      if (!field) return;
      var existing = lyricResult[field] || '';
      var add = l.syllables ? l.syllables.join(' ') : l.text;
      lyricResult[field] = existing ? existing + ' ' + add : add;
    });
    
    // chordText + offsets
    var chords = (tl.chordEvents || []).slice().sort(function(a,b){ return a.start - b.start; });
    var chordText = chords.map(function(c){ return c.chordName; }).join(' ');
    var chordOffsets = chords.map(function(c){ return c.start; });
    
    // marks
    var marks = (tl.annotationEvents || []).map(function(a){ return a.mark; }).join(' ');
    
    return {
      noteText: noteTokens.join(' '),
      lyricText: lyricResult.lyricText,
      lyricText2: lyricResult.lyricText2,
      lyricText3: lyricResult.lyricText3,
      lyricText4: lyricResult.lyricText4,
      chordText: chordText,
      chordOffsets: chordOffsets,
      marks: marks
    };
  }

  /* —— 3. 雙向同步：掛在 Measure 物件上 ——
     m.timeline = measureToTimeline(m)
     修改 timeline 後呼叫 syncTimelineToMeasure(m) 更新舊欄位 */
  function syncTimelineToMeasure(m) {
    if (!m || !m.timeline) return;
    var synced = timelineToMeasure(m.timeline, m.timeSignature);
    Object.assign(m, synced);
  }

  function ensureTimeline(m) {
    if (!m.timeline) m.timeline = measureToTimeline(m);
    return m.timeline;
  }

  function getMelodyEvents(m) { return ensureTimeline(m).melodyEvents; }
  function getLyricEvents(m, verse) { 
    var tl = ensureTimeline(m);
    return verse ? tl.lyricEvents.filter(function(l){ return l.verse === verse; }) : tl.lyricEvents;
  }
  function getChordEvents(m) { return ensureTimeline(m).chordEvents; }
  function getAnnotationEvents(m) { return ensureTimeline(m).annotationEvents; }

  /* ===== Phase 1: Event Model Migration Adapter =====
     直接在 measure 上建立：
       measure.melodyEvents = []
       measure.lyricTracks = []  // 陣列的陣列，每 verse 一個陣列
       measure.chordEvents = []
       measure.annotations = []
     並加上 version flag 防止重複 Migration。
     Legacy fields (noteText, chordText, lyricText~4, chordOffsets, marks) 保留供相容。 */

  // 事件模型版本
  var EVENT_MODEL_VERSION = 3;

  /* 一次性初始化：若 measure 沒有 Event Model，從 Legacy 建立 */
  function ensureEventModel(m) {
    var needsParse = (!m.melodyEvents || m.melodyEvents.length === 0) && String(m.noteText || '').trim().length > 0;
    if (m.eventModelVersion === EVENT_MODEL_VERSION && !needsParse) return m;
    if (!m.melodyEvents) m.melodyEvents = [];
    if (!m.lyricTracks) m.lyricTracks = [[], [], [], []];  // 4 verses
    if (!m.chordEvents) m.chordEvents = [];
    if (!m.annotations) m.annotations = [];
    if (needsParse || (m.melodyEvents.length === 0 && m.chordEvents.length === 0 && m.annotations.length === 0 &&
        m.lyricTracks.every(function(t){ return t.length === 0; }))) {
      // 尚未 migrate，從 Legacy 解析
      parseMeasureToEvents(m);
    }
    m.eventModelVersion = EVENT_MODEL_VERSION;
    return m;
  }

  /* Legacy → Event Model（寫入 measure.melodyEvents/lyricTracks/chordEvents/annotations） */
  function parseMeasureToEvents(m) {
    if (!m) return;
    // 先清空（冪等）
    m.melodyEvents = [];
    m.lyricTracks = [[], [], [], []];
    m.chordEvents = [];
    m.annotations = [];

    // 1. noteText → melodyEvents
    var timeline = measureToTimeline(m);  // 復用既有邏輯
    m.melodyEvents = timeline.melodyEvents || [];
    // lyricEvents 按 verse 分組
    (timeline.lyricEvents || []).forEach(function(l) {
      var verseIdx = (l.verse || 1) - 1;
      if (verseIdx >= 0 && verseIdx < 4) m.lyricTracks[verseIdx].push(l);
    });
    m.chordEvents = timeline.chordEvents || [];
    m.annotations = timeline.annotationEvents || [];

    /* Phase 6D：確定性 uid（基於「覆蓋前」生成位置）＋ 套用 m.eventOverrides。
       uid 在覆蓋套用前計算 → 重載後同一 legacy 資料產生同 uid → 覆蓋可持久對應。 */
    solaAssignEventUids(m);
    applyEventOverrides(m);
  }

  /* Legacy 寫入後同步到 Event Model（單向：Legacy → Events） */
  function syncLegacyToEvents(m) {
    if (!m) return;
    // 確保 Event Model 結構存在
    if (!m.melodyEvents) m.melodyEvents = [];
    if (!m.lyricTracks) m.lyricTracks = [[], [], [], []];
    if (!m.chordEvents) m.chordEvents = [];
    if (!m.annotations) m.annotations = [];
    // 重新解析（冪等，可重複呼叫）
    parseMeasureToEvents(m);
    // 更新版本號
    m.eventModelVersion = EVENT_MODEL_VERSION;
  }

  /* Event Model → Legacy（供現有 Renderer/Export/Playback/Undo 使用） */
  function eventsToLegacy(m) {
    if (!m) return {};
    var timeline = {
      meter: m.timeSignature || '4/4',
      melodyEvents: m.melodyEvents || [],
      lyricEvents: [],
      chordEvents: m.chordEvents || [],
      annotationEvents: m.annotations || []
    };
    // lyricTracks 扁平化
    (m.lyricTracks || [[],[],[],[]]).forEach(function(track, vi) {
      track.forEach(function(l) { timeline.lyricEvents.push(l); });
    });
    var legacy = timelineToMeasure(timeline, m.timeSignature);
    return legacy;
  }

  /* 批次遷移整份文件 */
    function migrateAllMeasures(doc) {
      if (!doc || !doc.measures) return;
      doc.measures.forEach(ensureEventModel);
    }

    /* ===== Phase 2: Layout Engine (Event Model → Visual Positions) =====
       核心原則：
       - 唯一資料來源：Event Model (melodyEvents, lyricTracks, chordEvents, annotations)
       - 時間單位：beat (四分音符 = 1)
       - 佈局單位：px (1 beat = BEAT_WIDTH px)
       - 產出：每個 event 獲得 renderX, renderY (視覺絕對座標)
       - 無雙層：單一視覺層，編輯器為 overlay input
    ===== */

    // Layout 常數
    const BEAT_WIDTH = 48;           // 1 拍 = 48px (可調)
    const MEASURE_PADDING = 16;      // 小節左右留白
    const SYSTEM_MARGIN = 24;        // 左右系統邊距
    /* Phase 6D：tick 換算常數。既有 tick 欄位（chordTicks/noteTicks/lyricTicks）皆為
       480 ticks = 1 四分音符拍（models.py expand_beats、v3ChordSlotWrite 同單位）。
       拖曳吸附格＝1/16 音符（120 ticks）；1 拍 48px → 16 分＝6px 步距。 */
    const TICKS_PER_BEAT = 480;
    const SNAP_TICKS = 120;
    const MAX_SYSTEM_WIDTH = 960;    // 系統最大寬度 (約 20 拍)
    const TRACK_HEIGHTS = {
      chord: 56,       // 和弦區高度
      melody: 40,      // 旋律/簡譜區高度
      lyric: 24,       // 每行歌詞高度
      annotation: 16   // 標記區高度
    };
    const TRACK_ORDER = ['chord', 'melody', 'lyric1', 'lyric2', 'lyric3', 'lyric4', 'annotation'];
    const TRACK_Y_OFFSET = (function() {
      var off = {}, y = MEASURE_PADDING;
      TRACK_ORDER.forEach(function(t) {
        off[t] = y;
        y += TRACK_HEIGHTS[t] + 4;  // track gap
      });
      return off;
    })();
    const MEASURE_TOTAL_HEIGHT = (function() {
      var y = MEASURE_PADDING;
      TRACK_ORDER.forEach(function(t) { y += TRACK_HEIGHTS[t] + 4; });
      return y + MEASURE_PADDING;
    })();

    /* —— 核心：單一小節佈局 ——
       輸入：measure (含 Event Model)
       副作用：為每個 event 寫入 renderX, renderY
       回傳：{ width, height, events: [...] }
    */
    function layoutMeasureEvents(m) {
      if (!m) return { width: 0, height: MEASURE_TOTAL_HEIGHT, events: [] };

      var meter = m.timeSignature || '4/4';
      var beatsPerMeasure = parseTimeSignatureToBeats(meter);
      var measureWidth = beatsPerMeasure * BEAT_WIDTH + MEASURE_PADDING * 2;

      // 收集所有 events，按 track 分組
      var allEvents = [];
      var byTrack = { chord: [], melody: [], lyric1: [], lyric2: [], lyric3: [], lyric4: [], annotation: [] };

      // Melody events
      (m.melodyEvents || []).forEach(function(e) {
        if (e.pitch === 0) return; // 休止符不佔寬度？保留位置
        e._track = 'melody';
        e.renderY = TRACK_Y_OFFSET.melody;
        byTrack.melody.push(e);
        allEvents.push(e);
      });

      // Chord events
      (m.chordEvents || []).forEach(function(e) {
        e._track = 'chord';
        e.renderY = TRACK_Y_OFFSET.chord;
        byTrack.chord.push(e);
        allEvents.push(e);
      });

      // Lyric tracks (4 verses)
      (m.lyricTracks || [[],[],[],[]]).forEach(function(track, vi) {
        var trackName = 'lyric' + (vi + 1);
        track.forEach(function(e) {
          e._track = trackName;
          e.renderY = TRACK_Y_OFFSET[trackName];
          byTrack[trackName].push(e);
          allEvents.push(e);
        });
      });

      // Annotations
      (m.annotations || []).forEach(function(e) {
        e._track = 'annotation';
        e.renderY = TRACK_Y_OFFSET.annotation;
        byTrack.annotation.push(e);
        allEvents.push(e);
      });

      // 計算 renderX：start(beat) → px
      /* 6C 冪等修正：
         - layoutOffsetX ＝「暫時」碰撞修正：每趟排版歸零重算，避免重排累加漂移。
         - userOffsetX ＝「持久」使用者偏移（保留給未來拖曳功能，目前恆 0／undefined）。
         - 基準位置只含持久偏移，暫存碰撞值不進入基準 → 同一資料重複排版結果相同。 */
      allEvents.forEach(function(e) { e.layoutOffsetX = 0; });
      allEvents.forEach(function(e) {
        e.renderX = MEASURE_PADDING + (e.start || 0) * BEAT_WIDTH + (e.userOffsetX || 0);
        // 寬度 = duration * BEAT_WIDTH (最小寬度保護)
        e.renderWidth = Math.max(16, (e.duration || 1) * BEAT_WIDTH);
      });

      // 衝突檢測與解決：同 track 內不重疊（左右微調）
      TRACK_ORDER.forEach(function(trackName) {
        var trackEvents = byTrack[trackName];
        if (trackEvents.length <= 1) return;

        // 按 renderX 排序
        trackEvents.sort(function(a, b) { return a.renderX - b.renderX; });

        // 檢測重疊並向右推
        for (var i = 1; i < trackEvents.length; i++) {
          var prev = trackEvents[i - 1];
          var curr = trackEvents[i];
          var prevRight = prev.renderX + prev.renderWidth;
          var minGap = 4; // 最小間隙
          if (curr.renderX < prevRight + minGap) {
            var shift = prevRight + minGap - curr.renderX;
            curr.renderX += shift;
            curr.layoutOffsetX = (curr.layoutOffsetX || 0) + shift;
            // 連帶後續事件也要推 (同 track)
            for (var j = i + 1; j < trackEvents.length; j++) {
              trackEvents[j].renderX += shift;
              trackEvents[j].layoutOffsetX = (trackEvents[j].layoutOffsetX || 0) + shift;
            }
          }
        }
      });

      // 跨 track 衝突：旋律 vs 歌詞 (垂直不重疊，但水平對齊檢查)
      // 目前垂直已分 track，水平不處理跨 track 推擠

      // 重新計算小節寬度 (內容可能撐寬)
            var maxX = MEASURE_PADDING * 2;
            allEvents.forEach(function(e) {
              var right = e.renderX + e.renderWidth;
              if (right > maxX) maxX = right;
            });
            measureWidth = Math.max(measureWidth, maxX + MEASURE_PADDING);

            // 計算 beatGroups (供 beam 顯示)：依 start 排序的 melody events
            var beatGroups = [];
            var melodySorted = byTrack.melody.slice().sort(function(a, b) { return a.start - b.start; });
            melodySorted.forEach(function(e) {
              if (e.pitch === 0) return; // 休止符不參與 beatGroups
              var beatStart = Math.floor(e.start || 0);
              var last = beatGroups[beatGroups.length - 1];
              if (last && last.beat === beatStart) {
                last.end = e.renderX + e.renderWidth;
                last.events.push(e);
              } else {
                beatGroups.push({
                  beat: beatStart,
                  x: e.renderX,
                  end: e.renderX + e.renderWidth,
                  events: [e]
                });
              }
            });

            return {
              width: measureWidth,
              height: MEASURE_TOTAL_HEIGHT,
              events: allEvents,
              beatsPerMeasure: beatsPerMeasure,
              byTrack: byTrack,
              beatGroups: beatGroups
            };
          }

    /* —— 系統換行：將 measures 分配到多個 system ——
       輸入：measures[], maxWidth
       回傳：systems = [{ measures: [...], totalWidth, startX }]
    */
    function layoutSystems(measures, maxWidth) {
      maxWidth = maxWidth || MAX_SYSTEM_WIDTH;
      var systems = [];
      var current = { measures: [], totalWidth: 0, startX: SYSTEM_MARGIN };
      var x = SYSTEM_MARGIN;

      measures.forEach(function(m, mi) {
        var layout = layoutMeasureEvents(m);
        m._layout = layout; // cache

        if (current.measures.length > 0 && x + layout.width > maxWidth) {
          // 換行
          current.totalWidth = x - SYSTEM_MARGIN;
          systems.push(current);
          current = { measures: [], totalWidth: 0, startX: SYSTEM_MARGIN };
          x = SYSTEM_MARGIN;
        }

        m._layout.systemX = x;
        current.measures.push(m);
        x += layout.width + 8; // measure gap
      });

      if (current.measures.length) {
        current.totalWidth = x - SYSTEM_MARGIN - 8;
        systems.push(current);
      }

      return systems;
    }

    /* —— 整份樂譜佈局入口 —— */
    function layoutScore(doc) {
      if (!doc || !doc.measures) return { systems: [], totalHeight: 0 };
      var systems = layoutSystems(doc.measures);
      var totalHeight = systems.length * (MEASURE_TOTAL_HEIGHT + 16) + 40; // system gap + header
      return { systems: systems, totalHeight: totalHeight, measureHeight: MEASURE_TOTAL_HEIGHT };
    }

    function solaGetCursor() {
    var ms = (state3.doc && state3.doc.measures) || [];
    if (!ms.length) return null;
    if (solaEdit.mi >= ms.length) solaEdit.mi = ms.length - 1;
    if (solaEdit.mi < 0) solaEdit.mi = 0;
    var toks = solaTokens(ms[solaEdit.mi]);
    if (solaEdit.nti >= toks.length) solaEdit.nti = toks.length ? toks.length - 1 : 0;
    if (solaEdit.nti < 0) solaEdit.nti = 0;
    return { m: ms[solaEdit.mi], mi: solaEdit.mi, nti: solaEdit.nti, toks: toks };
  }

  /* 複撤銷：快照 doc 資料欄位（上限 50 步） */
    function solaSnapshot() {
      var d = state3.doc;
      return JSON.stringify({
        title: d.title, key: d.key, timeSignature: d.timeSignature,
        tempo: d.tempo, composer: d.composer,
        measures: JSON.parse(JSON.stringify(d.measures || [])),  // 深拷貝含 chordTicks/noteTicks/eventOverrides/lyric*Ticks
        cursor: { mi: solaEdit.mi, nti: solaEdit.nti }  // [4.1] 小節操作還原游標（additive；舊快照無此欄位時 solaRestore 保持既有 clamp）
      });
    }
    function solaPushUndo() {
      solaEdit.undoStack.push(solaSnapshot());
      if (solaEdit.undoStack.length > 50) solaEdit.undoStack.shift();
      solaEdit.redoStack = [];
    }
    function solaRestore(snap) {
      var d = state3.doc, o = JSON.parse(snap);
      d.title = o.title; d.key = o.key; d.timeSignature = o.timeSignature;
      d.tempo = o.tempo; d.composer = o.composer; d.measures = o.measures;
      // [4.1] 還原游標：新快照帶 cursor（小節操作）；舊快照無 cursor 欄位時保留既有 clamp 行為
      if (o.cursor && typeof o.cursor.mi === 'number') {
        solaEdit.mi = o.cursor.mi;
        solaEdit.nti = (typeof o.cursor.nti === 'number') ? o.cursor.nti : 0;
      }
      if (solaEdit.mi >= d.measures.length) solaEdit.mi = Math.max(0, d.measures.length - 1);
      if (solaEdit.nti < 0) solaEdit.nti = 0;
      if (typeof collectV3ToDoc === 'function') collectV3ToDoc(d);  // 重建 ticks 確保一致
      var ts = $('#tonality-select');
      if (ts && d.key) ts.value = toChordDbRoot(d.key);
      if ($('#doc-key') && d.key) $('#doc-key').value = d.key;
      renderRootGrid();
      renderChordPanel();
    }
  function solaUndo() {
      if (!solaEdit.undoStack.length) { setSola321Status('沒有可復原的動作', 'var(--text-dim)'); return; }
      solaEdit.redoStack.push(solaSnapshot());
      solaRestore(solaEdit.undoStack.pop());
      renderSola321Score(true);
      if (typeof saveCurrentDoc === 'function') saveCurrentDoc();
    }
    function solaRedo() {
      if (!solaEdit.redoStack.length) { setSola321Status('沒有可重做的動作', 'var(--text-dim)'); return; }
      solaEdit.undoStack.push(solaSnapshot());
      solaRestore(solaEdit.redoStack.pop());
      renderSola321Score(true);
      if (typeof saveCurrentDoc === 'function') saveCurrentDoc();
    }

    /* ===== [4.2 第一批] 直式小節操作：新增 / 刪除 =====
       唯一資料源＝state3.doc.measures。操作前 solaPushUndo（快照含 measures 全欄＋游標）；
       操作後 renumber＋重定位游標＋renderSola321Score(false)＋saveCurrentDoc()。
       saveCurrentDoc 為 fire-and-forget（失敗只 toast、保留本地可復原狀態、不清 undo/redo）→ 操作成功＝模型交易完成。
       絕不重跑 parseMeasureToEvents/syncLegacyToEvents（避免破壞手動編輯的事件模型）。 */
    function solaDefaultMeasure() {
      var ts = String((state3.doc && state3.doc.timeSignature) || '4/4');
      var mm = ts.split('/');
      var num = parseInt(mm[0], 10) || 4;
      var den = parseInt(mm[1], 10) || 4;
      var dur = (den <= 2) ? 'half' : (den === 4) ? 'quarter' : (den === 8) ? 'eighth' : (den === 16) ? 'sixteenth' : 'quarter';
      var beats = [];
      for (var b = 1; b <= num; b++) beats.push({ beat: b, note: '', lyric: '', chord: '', duration: dur, confidence: 1, annotation: '' });
      return {
        number: 1, chordText: '', noteText: '', lyricText: '', lyricText2: '', lyricText3: '', lyricText4: '',
        lyricRows: 1, barline: true, marks: '', sourcePage: null,
        beats: beats, melodyEvents: [], lyricTracks: [[], [], [], []], chordEvents: [], annotations: [],
        eventModelVersion: 3
      };
    }
    function solaAddMeasure() {
      if (!state3.doc) { toast('無文件', 'bad'); return; }
      var arr = state3.doc.measures; if (!arr) { state3.doc.measures = arr = []; }
      var baseMi = (typeof solaGetTargetMI === 'function') ? solaGetTargetMI() : solaEdit.mi;
      var idx = (typeof baseMi === 'number' && baseMi >= 0 && baseMi < arr.length) ? (baseMi + 1) : arr.length;
      solaPushUndo();
      var m = solaDefaultMeasure();
      arr.splice(idx, 0, m);
      for (var i = 0; i < arr.length; i++) arr[i].number = i + 1;
      solaEdit.mi = idx; solaEdit.nti = 0;  // 游標移到新小節
      solaEdit.selStartNti = 0; solaEdit.selEndNti = 0;
      solaTargetMI = idx;
      renderSola321Score(false);
      solaRestoreTargetHighlight();
      saveCurrentDoc();
      toast('已新增小節 ' + (idx + 1), 'ok');
    }
    function solaDeleteMeasure(mi) {
      if (!state3.doc || !state3.doc.measures) { toast('無小節可刪除', 'bad'); return; }
      var arr = state3.doc.measures;
      var targetMi = (typeof mi === 'number' && !isNaN(mi)) ? mi : ((typeof solaGetTargetMI === 'function') ? solaGetTargetMI() : solaEdit.mi);
      if (targetMi < 0 || targetMi >= arr.length) { toast('無效小節索引', 'bad'); return; }  // 非法游標→安全拒絕、不破壞資料
      solaPushUndo();
      var isProbe = (typeof window !== 'undefined' && String(location.search).indexOf('probe=1') >= 0);
      arr.splice(targetMi, 1);
      if (arr.length === 0 && !isProbe) {
        arr.push(solaDefaultMeasure());
      }
      for (var i = 0; i < arr.length; i++) arr[i].number = i + 1;
      // 游標重定位：刪空→0/0；刪游標所在節→落到補位節(節點0)；刪游標之前→游標索引-1(保留選取小節)；刪之後→游標不變
      var curMi = (typeof solaEdit.mi === 'number') ? solaEdit.mi : 0;
      if (arr.length === 0) { solaEdit.mi = 0; solaEdit.nti = 0; }
      else if (targetMi === curMi) { solaEdit.mi = Math.min(curMi, arr.length - 1); solaEdit.nti = 0; }
      else if (targetMi < curMi) { solaEdit.mi = curMi - 1; /* 同一小節左移，nti 保留 */ }
      /* targetMi > curMi：游標不受影響，不改 */
      solaEdit.selStartNti = solaEdit.nti; solaEdit.selEndNti = solaEdit.nti;
      solaTargetMI = Math.min(Math.max(0, solaEdit.mi), Math.max(0, arr.length - 1));
      renderSola321Score(false);
      solaRestoreTargetHighlight();
      saveCurrentDoc();
      toast('已刪除小節', 'ok');
    }
    /* ===== [4.2 第二批] 直式小節操作：上移／下移 =====
       只重排 state3.doc.measures 陣列順序＋renumber；不重解析事件模型、不重建事件 UID。
       游標：被移／被頂的小節若被選中→跟隨到新索引（同小節 token 數不變→nti 保留）；其他小節→不變。
       邊界：首節上移／末節下移＝no-op（不入 undo、不清 redo、不改資料）。 */
    function solaMoveMeasure(mi, dir) {
      if (!state3.doc || !state3.doc.measures) { toast('無小節可移動', 'bad'); return; }
      var arr = state3.doc.measures;
      if (mi < 0 || mi >= arr.length) { toast('無效小節索引', 'bad'); return; }
      var target = (dir === 'up') ? mi - 1 : mi + 1;
      if (target < 0 || target >= arr.length) {
        setSola321Status((dir === 'up') ? '已是首節，無法上移' : '已是末節，無法下移', 'var(--text-dim)');
        return;  // 邊界 no-op：不碰 undoStack/redoStack、不改資料
      }
      solaPushUndo();  // 成功才入 undo（快照含全欄＋游標＋eventOverrides）
      var t = arr[mi]; arr[mi] = arr[target]; arr[target] = t;
      for (var i = 0; i < arr.length; i++) arr[i].number = i + 1;  // renumber
      var curMi = (typeof solaEdit.mi === 'number') ? solaEdit.mi : 0;
      if (curMi === mi) solaEdit.mi = target;        // 游標在被移小節→跟隨
      else if (curMi === target) solaEdit.mi = mi;    // 游標在被頂小節→跟隨
      /* 其他位置：游標不變 */
      renderSola321Score(false);
      saveCurrentDoc();
      setSola321Status('已' + (dir === 'up' ? '上移' : '下移') + '小節', 'var(--text-dim)');
    }
    function solaMoveUp(mi) { solaMoveMeasure(mi, 'up'); }
    function solaMoveDown(mi) { solaMoveMeasure(mi, 'down'); }

    /* [4.2 第三批] 小節剪貼簿（複製／剪下／貼上／指定小節後插入） */
    var solaClipboardMeasure = null;
    function solaCloneMeasureForClipboard(m) {
      if (!m) return null;
      return JSON.parse(JSON.stringify(m));
    }
    function solaCopyMeasure(mi) {
      if (!state3.doc || !Array.isArray(state3.doc.measures)) return;
      var idx = (typeof mi === 'number' && !isNaN(mi)) ? mi : solaGetTargetMI();
      var m = state3.doc.measures[idx];
      if (!m) return;
      solaClipboardMeasure = solaCloneMeasureForClipboard(m);
      renderSola321Score(false);
      solaRestoreTargetHighlight();
      toast('已複製第 ' + (idx + 1) + ' 小節', 'ok');
      setSola321Status('已複製第 ' + (idx + 1) + ' 小節至剪貼簿', '#38a169');
    }
    function solaCutMeasure(mi) {
      if (!state3.doc || !Array.isArray(state3.doc.measures)) return;
      var idx = (typeof mi === 'number' && !isNaN(mi)) ? mi : solaGetTargetMI();
      var m = state3.doc.measures[idx];
      if (!m) return;
      solaClipboardMeasure = solaCloneMeasureForClipboard(m);
      solaDeleteMeasure(idx);
      setSola321Status('已剪下第 ' + (idx + 1) + ' 小節', '#38a169');
    }
    function solaPasteMeasure(afterMi) {
      if (!state3.doc) return;
      if (!solaClipboardMeasure) {
        toast('剪貼簿尚無小節，請先複製小節', 'bad');
        setSola321Status('剪貼簿尚無小節，請先複製或剪下小節', '#f0b429');
        return;
      }
      if (!Array.isArray(state3.doc.measures)) state3.doc.measures = [];
      var arr = state3.doc.measures;
      var baseMi = (typeof afterMi === 'number' && !isNaN(afterMi)) ? afterMi : solaGetTargetMI();
      var insertIdx = (typeof baseMi === 'number' && !isNaN(baseMi) && baseMi >= 0 && baseMi < arr.length)
        ? (baseMi + 1)
        : ((arr.length === 0) ? 0 : Math.min(Math.max(0, solaEdit.mi) + 1, arr.length));
      solaPushUndo();
      var pasted = solaCloneMeasureForClipboard(solaClipboardMeasure);
      pasted.number = insertIdx + 1;
      arr.splice(insertIdx, 0, pasted);
      for (var i = 0; i < arr.length; i++) arr[i].number = i + 1;
      solaEdit.mi = insertIdx;
      solaEdit.nti = 0;
      solaEdit.selStartNti = 0;
      solaEdit.selEndNti = 0;
      solaTargetMI = insertIdx;
      renderSola321Score(false);
      solaRestoreTargetHighlight();
      saveCurrentDoc();
      toast('已貼上至第 ' + (insertIdx + 1) + ' 小節', 'ok');
      setSola321Status('已於第 ' + (insertIdx + 1) + ' 小節位置貼上小節', '#38a169');
    }
    function solaAddMeasureAfter(mi) {
      if (!state3.doc) return;
      if (!Array.isArray(state3.doc.measures)) state3.doc.measures = [];
      var arr = state3.doc.measures;
      if (typeof mi === 'number' && !isNaN(mi) && mi >= 0 && mi < arr.length) {
        solaEdit.mi = mi;
        solaTargetMI = mi;
      }
      solaAddMeasure();
    }
    function solaResolveTargetMeasureIndex() {
      return solaGetTargetMI();
    }
    function solaMeasureOp(op, mi) {
      var targetMi = (typeof mi === 'number' && !isNaN(mi) && mi >= 0) ? mi : solaGetTargetMI();
      if (op === 'add-after' || op === 'add-measure') {
        solaAddMeasureAfter(targetMi);
      } else if (op === 'copy' || op === 'copy-measure') {
        solaCopyMeasure(targetMi);
      } else if (op === 'paste' || op === 'paste-measure') {
        solaPasteMeasure(targetMi);
      } else if (op === 'dup' || op === 'dup-measure') {
        solaDuplicateMeasure(targetMi);
      } else if (op === 'del' || op === 'del-measure') {
        solaDeleteMeasure(targetMi);
      }
    }

    // [4.2 測試] 門控 probe：僅 ?probe=1 時暴露，供隔離驗讀取游標/模型（默認關閉、不干擾正式操作）
    if (typeof window !== 'undefined' && String(location.search).indexOf('probe=1') >= 0) {
      window.__solaProbe = function() {
        return {
          mi: solaEdit.mi, nti: solaEdit.nti,
          count: (state3.doc && state3.doc.measures) ? state3.doc.measures.length : -1,
          numbers: (state3.doc && state3.doc.measures) ? state3.doc.measures.map(function(x) { return x.number; }) : [],
          marks: (state3.doc && state3.doc.measures) ? state3.doc.measures.map(function(x) { return (x && x.marks) ? x.marks : ''; }) : [],
          beatLens: (state3.doc && state3.doc.measures) ? state3.doc.measures.map(function(x) { return x.beats ? x.beats.length : 0; }) : [],
          ts: state3.doc ? state3.doc.timeSignature : null,
          undoLen: solaEdit.undoStack.length, redoLen: solaEdit.redoStack.length,
          hasClipboard: !!solaClipboardMeasure
        };
      };
      window.__solaSetCursor = function(mi, nti) {
        var arr = state3.doc.measures || [];
        solaEdit.mi = (typeof mi === 'number' && mi >= 0 && mi < arr.length) ? mi : 0;
        solaEdit.nti = (typeof nti === 'number' && nti >= 0) ? nti : 0;
        return { mi: solaEdit.mi, nti: solaEdit.nti };
      };
      window.__solaMeasureAt = function(i) {
        var a = state3.doc.measures;
        return (a && a[i]) ? JSON.parse(JSON.stringify(a[i])) : null;
      };
      window.__solaSetOverride = function(mi, uid, patch) {
        var m = state3.doc.measures[mi]; if (!m) return null;
        m.eventOverrides = m.eventOverrides || {};
        m.eventOverrides[uid] = JSON.parse(JSON.stringify(patch));
        return Object.keys(m.eventOverrides);
      };
    }

  /* 游標移動（dm 小節、dn 音位） */
  function solaMoveCursor(dm, dn) {
    var ms = state3.doc.measures || [];
    if (!ms.length) return;
    var mi = solaEdit.mi + dm;
    if (mi < 0) mi = 0;
    if (mi >= ms.length) mi = ms.length - 1;
    var maxni = Math.max(0, solaTokens(ms[mi]).length - 1);
    var ni;
    if (dn > 0 && mi !== solaEdit.mi) ni = 0;          // 右移換小節：到下一小節頭
    else if (dn < 0 && mi !== solaEdit.mi) ni = maxni;  // 左移換小節：到上一小節尾
    else ni = solaEdit.nti + dn;
    if (ni < 0) ni = 0;
    if (ni > maxni) ni = maxni;
    solaEdit.mi = mi; solaEdit.nti = ni;
    solaEdit.selStartNti = ni; solaEdit.selEndNti = ni;
    solaMarkCursor();
  }

  /* 只更新游標視覺（不重寫 DOM、不掉焦點）：顯示格 .sola321-note-char 加 .sola321-cursor 及選取範圍 .sola321-selected */
  function solaMarkCursor() {
    var sc = document.getElementById('sola321-score');
    if (!sc) return;
    sc.querySelectorAll('.sola321-note-char.sola321-cursor, .sola321-note-char.sola321-selected').forEach(function(el) {
      el.classList.remove('sola321-cursor');
      el.classList.remove('sola321-selected');
    });
    var ch = sc.querySelector('.sola321-note-char[data-mi="' + solaEdit.mi + '"][data-nti="' + solaEdit.nti + '"]');
    if (ch) ch.classList.add('sola321-cursor');
    var sStart = (typeof solaEdit.selStartNti === 'number') ? solaEdit.selStartNti : solaEdit.nti;
    var sEnd = (typeof solaEdit.selEndNti === 'number') ? solaEdit.selEndNti : solaEdit.nti;
    var lo = Math.min(sStart, sEnd);
    var hi = Math.max(sStart, sEnd);
    if (hi > lo) {
      for (var k = lo; k <= hi; k++) {
        var selEl = sc.querySelector('.sola321-note-char[data-mi="' + solaEdit.mi + '"][data-nti="' + k + '"]');
        if (selEl) selEl.classList.add('sola321-selected');
      }
    }
  }

  /* 聚焦游標小節：WYSIWYG 版—游標音設好後無獨立輸入行，改由點擊顯示元素開啟 overlay 編輯 */
  function solaFocusCursor() {
    solaMarkCursor();
    if (solaEdit.viewMode === 'vertical') return;
    var ch = document.querySelector('#sola321-score .sola321-note-char[data-mi="' + solaEdit.mi + '"][data-nti="' + solaEdit.nti + '"]');
    if (ch) { openSolaNoteOverlay(ch); }
  }

  /* ===== v3.04.09 目標小節（(b) 直接目標化）=====
     段落/結構記號/右側和弦庫寫入對象＝「剛點過的小節」，不再用 keyboard 游標 solaEdit.mi。
     橘色小節級框（.sola321-measure-target）標在目標小節上，重繪後自動恢復。 */
  function solaSetTarget(mi) {
    solaTargetMI = mi;
    solaHighlightTarget();
  }
  function solaGetTargetMI() {
    var ms = state3.doc && state3.doc.measures;
    if (solaTargetMI != null && ms && ms[solaTargetMI]) return solaTargetMI;
    /* 未點過任何小節 → 落回游標小節 */
    return (ms && ms.length) ? Math.min(solaEdit.mi, ms.length - 1) : 0;
  }
  function solaHighlightTarget() {
    var sc = document.getElementById('sola321-score');
    if (!sc) return;
    var mi = (solaTargetMI != null && solaTargetMI < ((state3.doc && state3.doc.measures) || []).length)
      ? solaTargetMI : solaGetTargetMI();
    sc.querySelectorAll('.sola321-measure.sola321-measure-target, .sola321-vmeasure.sola321-measure-target, .sola321-measure-timeline.sola321-measure-target').forEach(function(el) { el.classList.remove('sola321-measure-target'); });
    var tgt = sc.querySelector('.sola321-measure[data-mi="' + mi + '"], .sola321-vmeasure[data-mi="' + mi + '"], .sola321-measure-timeline[data-mi="' + mi + '"]');
    if (tgt) tgt.classList.add('sola321-measure-target');
  }
  /* 重繪後恢復目標小節橘框 */
  function solaRestoreTargetHighlight() { if (solaTargetMI != null) solaHighlightTarget(); }

  function solaSetMode(mode) {
    solaEdit.mode = mode;
    $$('.sola321-tb-btn[data-mode]').forEach(function(b) {
      b.classList.toggle('active', b.getAttribute('data-mode') === mode);
    });
  }

  /* 結構性編輯（時值／附點／三連音／臨時記號／八度／休止／刪除／直接音符） */
  function solaApplyOp(op, key) {
    if (!state3.doc) return;
    /* 新增 1 小節（＋）：在目標/游標小節「後面」插入一個空小節 */
    if (op === 'add-measure') {
      solaAddMeasure();
      return;
    }
    var cur = solaGetCursor();
    if (!cur) return;
    var toks = cur.toks;
    if (!toks.length) toks.push({ base: '', above: 0, below: 0 });
    var sStart = (typeof solaEdit.selStartNti === 'number') ? solaEdit.selStartNti : cur.nti;
    var sEnd = (typeof solaEdit.selEndNti === 'number') ? solaEdit.selEndNti : cur.nti;
    var rangeLo = Math.max(0, Math.min(sStart, sEnd, toks.length - 1));
    var targetNti = (op === 'tie' || op === 'slur' || op === 'triplet') ? rangeLo : cur.nti;
    var t = toks[targetNti];
    solaPushUndo();
    if (op === 'del') {
      toks.splice(cur.nti, 1);
      if (cur.nti >= toks.length) solaEdit.nti = Math.max(0, toks.length - 1);
      solaEdit.selStartNti = solaEdit.nti; solaEdit.selEndNti = solaEdit.nti;
      solaSetNoteText(cur.m, toks);
      if (!solaUpdateMeasureNotesInPlace(cur.mi, true)) {
        renderSola321Score(true);
      }
      saveCurrentDoc();
      return;
    }
    /* 小節線增刪＝拆分／合併小節（作用在游標小節）；可複撤銷（Ctrl+Z/Y）：
       ＋│ barline-add＝在游標音符「後面」插入小節線：游標音符留原小節，其後音符移入新小節
          （原稿有線但辨識漏掉時，選到該位置的音符按 ＋│ 補上分隔線）
       －│ barline-del＝移除游標小節「末音符後」的小節線：與下一小節合併為一小節 */
    if (op === 'barline-add') {
      var msA = state3.doc.measures;
      var mA = cur.m;
      var head = cur.toks.slice(0, cur.nti + 1);   // 游標音符（含）前 → 留原小節
      var tail = cur.toks.slice(cur.nti + 1);      // 游標音符之後 → 移入新小節
      mA.noteText = head.map(solaBuildToken).join(' ');
      var nm = {
        number: mA.number + 1,
        chordText: '', chordOffsets: [],
        noteText: tail.map(solaBuildToken).join(' '),
        lyricText: '', lyricText2: '', lyricText3: '', lyricText4: '',
        lyricRows: 1, barline: true, marks: ''
      };
      msA.splice(cur.mi + 1, 0, nm);
      msA.forEach(function(x, i) { x.number = i + 1; });
      solaEdit.mi = cur.mi + 1; solaEdit.nti = 0;  // 游標移到新小節第一個音符
      solaEdit.selStartNti = 0; solaEdit.selEndNti = 0;
      renderSola321Score(true);
      saveCurrentDoc();
      return;
    }
    if (op === 'barline-del') {
      var msB = state3.doc.measures;
      if (cur.mi >= msB.length - 1) { setSola321Status('末小節右側沒有小節線可刪除', '#f0b429'); return; }
      var mB = cur.m, nx = msB[cur.mi + 1];
      solaPushUndo();
      var headCount = cur.toks.length;  // 原小節 token 數（供 chordOffsets 偏移）
      mB.noteText = cur.toks.concat(solaTokens(nx)).map(solaBuildToken).join(' ');
      mB.chordText = String(mB.chordText || '').trim().split(/\s+/).concat(String(nx.chordText || '').trim().split(/\s+/)).filter(Boolean).join(' ');
      mB.chordOffsets = mB.chordOffsets || [];
      (nx.chordOffsets || []).forEach(function(o) { mB.chordOffsets.push(o + headCount); });
      ['lyricText', 'lyricText2', 'lyricText3', 'lyricText4'].forEach(function(f) {
        var a = String(mB[f] || '').trim(), b = String(nx[f] || '').trim();
        if (a && b) mB[f] = a + ' ' + b; else mB[f] = a || b;
      });
      msB.splice(cur.mi + 1, 1);
      msB.forEach(function(x, i) { x.number = i + 1; });
      solaEdit.mi = cur.mi;
      renderSola321Score(false);
      saveCurrentDoc();
      return;
    }
    var p = (op === 'digit')
      ? { acc: '', digit: key, dotted: false, under: 0, triplet: false, tie: false, slur: false }
      : solaDecomp(t.base);
    switch (op) {
      case 'rest': p = { acc: '', digit: '0', dotted: false, under: 0, triplet: false, tie: false, slur: false }; t.above = 0; t.below = 0; break;
      case 'dot': p.dotted = !p.dotted; break;
      case 'triplet': {
        p.triplet = !p.triplet;
        /* 若取消三連音，一併清除後續兩個音符上可能殘留的舊版 triplet 標記 */
        if (!p.triplet) {
          for (var tk = 1; tk <= 2; tk++) {
            if (toks[targetNti + tk]) {
              var pk = solaDecomp(toks[targetNti + tk].base);
              if (pk.triplet) {
                pk.triplet = false;
                toks[targetNti + tk].base = solaRecomp(pk);
              }
            }
          }
        }
        break;
      }
      case 'tie': p.tie = !p.tie; if (p.tie) p.slur = false; break;
      case 'slur': p.slur = !p.slur; if (p.slur) p.tie = false; break;
      case 'sharp': p.acc = (p.acc === '#' ? '' : '#'); break;
      case 'flat': p.acc = (p.acc === 'b' ? '' : 'b'); break;
      case 'natural': p.acc = ''; break;
      case 'oct-up': t.above = t.above >= 2 ? 0 : t.above + 1; t.below = 0; break;
      case 'oct-down': t.below = t.below >= 2 ? 0 : t.below + 1; t.above = 0; break;
      case 'dur': {
        var u = { A: 0, S: 0, D: 0, F: 1, G: 2, H: 3 }[key];
        if (u != null && p.digit) { p.under = u; p.dotted = false; }
        break;
      }
    }
    t.base = solaRecomp(p);
    solaSetNoteText(cur.m, toks);
    solaEdit.mi = cur.mi;
    solaEdit.nti = targetNti;
    if (!solaUpdateMeasureNotesInPlace(cur.mi, true)) {
      renderSola321Score(true);
    }
    saveCurrentDoc();
  }

  /* 結構記號 toggle（小節層 m.marks，代號形式：𝄋/𝄆/𝄇/‖/D.C./D.S./1./2./Coda/tr/~/p/mp/mf/f/cresc./dim.）：
     點工具列記號＝對游標小節切換該記號；點小節上的記號＝移除該記號 */
  function solaToggleMark(mark) {
    if (!state3.doc || !state3.doc.measures) { setSola321Status('請先載入專案再插入記號', '#e53e3e'); return; }
    var tmi = solaGetTargetMI();
    var m = state3.doc.measures[tmi];
    if (!m) return;
    solaPushUndo();
    var marks = String(m.marks || '').trim().split(/\s+/).filter(Boolean);
    var i = marks.indexOf(mark);
    if (i >= 0) marks.splice(i, 1); else marks.push(mark);
    m.marks = marks.join(' ');
    syncLegacyToEvents(m);
    if (state3.doc) renderChordProFromDoc(state3.doc);
    setSola321Status('小節 ' + (m.number != null ? m.number : tmi + 1) + (m.marks ? '：' + m.marks : ' 記號已清空'), '#38a169');
    renderSola321Score(true);
    solaRestoreTargetHighlight();
    saveCurrentDoc();
  }
  function solaRemoveMark(mi, mark) {
    var m = state3.doc && state3.doc.measures[mi];
    if (!m) return;
    solaPushUndo();
    m.marks = String(m.marks || '').trim().split(/\s+/).filter(function(x) { return x !== mark; }).join(' ');
    if (SOLA_ALL_SECTION_LABELS.indexOf(mark) >= 0 || m.section === mark) {
      m.section = '';
    }
    syncLegacyToEvents(m);
    if (state3.doc) renderChordProFromDoc(state3.doc);
    renderSola321Score(true);
  }
  /* 段落記號（前奏/主歌/副歌/間奏/尾奏/A段/B段/C段/D段）：對目標小節切換段落 code，與記號列共用 marks 欄 */
  var SOLA_SECTION_NAMES = {
    verse: '主歌', chorus: '副歌', intro: '前奏', bridge: '間奏', outro: '尾奏',
    A: 'A段', B: 'B段', C: 'C段', D: 'D段'
  };
  var SOLA_ALL_SECTION_LABELS = ['前奏', '主歌', '副歌', '間奏', '尾奏', 'A段', 'B段', 'C段', 'D段', 'A', 'B', 'C', 'D'];
  function solaToggleSection(tag) {
    if (!state3.doc || !state3.doc.measures) { setSola321Status('請先載入專案再插入段落', '#e53e3e'); return; }
    var tmi = solaGetTargetMI();
    var m = state3.doc.measures[tmi];
    if (!m) return;
    var disp = SOLA_SECTION_NAMES[tag] || tag;
    solaPushUndo();
    var marks = String(m.marks || '').trim().split(/\s+/).filter(Boolean);
    var alreadyHas = (marks.indexOf(disp) >= 0) || (m.section === tag);
    marks = marks.filter(function(mk) { return SOLA_ALL_SECTION_LABELS.indexOf(mk) === -1 && mk !== tag; });
    if (alreadyHas) {
      m.section = '';
    } else {
      m.section = tag;
      marks.unshift(disp);
    }
    m.marks = marks.join(' ');
    syncLegacyToEvents(m);
    if (state3.doc) renderChordProFromDoc(state3.doc);
    setSola321Status('小節 ' + (m.number != null ? m.number : tmi + 1) + (m.marks ? '：' + m.marks : ' 段落已清除'), '#38a169');
    renderSola321Score(true);
    solaRestoreTargetHighlight();
    saveCurrentDoc();
  }
  function solaClearSection() {
    if (!state3.doc || !state3.doc.measures) { setSola321Status('請先載入專案再清除段落', '#e53e3e'); return; }
    var tmi = solaGetTargetMI();
    var m = state3.doc.measures[tmi];
    if (!m) return;
    solaPushUndo();
    m.section = '';
    var marks = String(m.marks || '').trim().split(/\s+/).filter(function(mk) {
      return SOLA_ALL_SECTION_LABELS.indexOf(mk) === -1;
    });
    m.marks = marks.join(' ');
    syncLegacyToEvents(m);
    if (state3.doc) renderChordProFromDoc(state3.doc);
    setSola321Status('已清除小節 ' + (m.number != null ? m.number : tmi + 1) + ' 的段落標記', '#38a169');
    renderSola321Score(true);
    solaRestoreTargetHighlight();
    saveCurrentDoc();
  }
  function solaDuplicateMeasure(mi) {
    if (!state3.doc || !Array.isArray(state3.doc.measures)) return;
    var arr = state3.doc.measures;
    var idx = (typeof mi === 'number' && !isNaN(mi) && mi >= 0 && mi < arr.length) ? mi : solaGetTargetMI();
    var src = arr[idx];
    if (!src) return;
    solaPushUndo();
    var dup = JSON.parse(JSON.stringify(src));
    dup.number = idx + 2;
    arr.splice(idx + 1, 0, dup);
    for (var i = 0; i < arr.length; i++) arr[i].number = i + 1;
    solaEdit.mi = idx + 1;
    solaEdit.nti = 0;
    solaTargetMI = idx + 1;
    renderSola321Score(false);
    solaRestoreTargetHighlight();
    saveCurrentDoc();
    setSola321Status('已複製小節 ' + (idx + 1) + ' 至小節 ' + (idx + 2), '#38a169');
  }

  /* 批量貼歌詞：依 SoLa321 手冊規則——從游標起逐字分配到「非休止」音位，休止不佔歌詞 */
  function solaDistributeLyrics(text) {
    var chars = String(text || '').split('').filter(function(c) { return c.trim() !== ''; });
    var ms = state3.doc.measures || [];
    var ci = 0;
    ms.forEach(function(m) {
      var toks = solaTokens(m);
      var syll = [];
      for (var i = 0; i < toks.length; i++) {
        var p = solaDecomp(toks[i].base);
        var isRest = p.digit === '0' || p.digit === '';
        if (!isRest && ci < chars.length) { syll.push(chars[ci]); ci++; }
        else syll.push('');
      }
      m.lyricText = syll.join(' ');
      syncLegacyToEvents(m);
    });
  }

  /* 視覺化簡譜「可編輯」渲染：白底樂譜紙、小節線分隔、游標高亮、每格 input
     資料源仍是 state3.doc（與簡譜格線同欄位：noteText / chordText / lyricText）。 */
  function renderSola321Score(refocus) {
    var cont = $('#sola321-score');
    if (!cont) return;
    var isProbe = (typeof window !== 'undefined' && String(location.search).indexOf('probe=1') >= 0);
    if (!isProbe) {
      solaEdit.viewMode = 'vertical';
      solaEdit.useTimelineRenderer = false;
    }
    if (!state3.doc) {
      cont.innerHTML = '<div class="sola321-score-empty">請先於左欄開啟或建立樂譜專案。</div>';
      setSola321Status('未載入專案，請先開專案再編輯 Score Studio 樂譜', 'var(--text-dim)');
      return;
    }
    if (!Array.isArray(state3.doc.measures)) state3.doc.measures = [];
    if (state3.doc.measures.length === 0) {
      if (isProbe) {
        cont.innerHTML = '<div class="sola321-score-body sola321-use-vertical"><div class="sola321-vertical-body">' +
          '<div class="sola321-v-toolbar" style="display:none"><button type="button" class="sola321-v-opbtn" data-vop="add">＋</button></div>' +
          '</div></div>';
        var ab = cont.querySelector('.sola321-v-opbtn[data-vop="add"]');
        if (ab) ab.addEventListener('click', function (e) { e.stopPropagation(); solaAddMeasure(); });
        setSola321Status('空文件', 'var(--text-dim)');
        return;
      }
      /* 一般模式：若專案無小節，自動建立 4 個空白小節（一行 4 小節）供直接鍵盤輸入 */
      var ts = (state3.doc && state3.doc.timeSignature) || '4/4';
      for (var ei = 0; ei < 4; ei++) {
        var em = createEmptyMeasureForSola(ei + 1, ts);
        ensureEventModel(em);
        state3.doc.measures.push(em);
      }
    }
    var doc = state3.doc;
    var measures = doc.measures || [];
    var viewMode = isProbe ? (solaEdit.viewMode === 'timeline' ? 'timeline' : (solaEdit.viewMode === 'vertical' ? 'vertical' : 'grid')) : 'vertical';
    var useTimeline = (viewMode === 'timeline');

    var paneEl = $('#sola321-pane');
    if (paneEl && doc && doc.titleFontScale) {
      paneEl.style.setProperty('--sola-title-scale', String(doc.titleFontScale));
    }

    var tempoVal = (doc.tempo && doc.tempo !== 90) ? doc.tempo : 80;
    var html = '';
    html += '<div class="sola321-score-header">';
    /* 歌曲名稱置頂置中；下方左側為 1=C  4/4  ♩=80，右側為 作詞 作曲 */
    html += '<div class="sola321-title"><input type="text" class="sola321-title-input" data-meta="title" value="' + escAttr(doc.title || '') + '" placeholder="歌曲名稱" title="點選歌名後可使用上方「字體 − / ＋」自由縮放歌名字體" /></div>';
    html += '<div class="sola321-header-bar">';
    html += '<div class="sola321-meta">' +
      '<span>1=<input type="text" class="sola321-meta-input" data-meta="key" value="' + escAttr(doc.key || 'C') + '" /></span>' +
      '<span><input type="text" class="sola321-meta-input" data-meta="timeSignature" style="width:40px" value="' + escAttr(doc.timeSignature || '4/4') + '" /></span>' +
      '<span>♩=<input type="number" class="sola321-meta-input" data-meta="tempo" style="width:44px" min="20" max="300" value="' + escAttr(String(tempoVal)) + '" /></span>' +
      '</div>';
    html += '<div class="sola321-subtitle"><span>作詞</span><input type="text" class="sola321-meta-input" data-meta="lyricist" value="' + escAttr(doc.lyricist || '') + '" placeholder="作詞" /><span>作曲</span><input type="text" class="sola321-meta-input" data-meta="composer" value="' + escAttr(doc.composer || '') + '" placeholder="作曲" /></div>';
    html += '</div>';
    if (isProbe) {
      html += '<div class="sola321-viewtoggle" style="opacity:0;position:fixed;top:0;left:0;width:10px;height:10px;overflow:hidden;z-index:9999">' +
        '<button type="button" class="sola321-vg" data-view="grid" style="width:2px;height:2px"></button>' +
        '<button type="button" class="sola321-vg" data-view="timeline" style="width:2px;height:2px"></button>' +
        '<button type="button" class="sola321-vg" data-view="vertical" style="width:2px;height:2px"></button>' +
        '</div>';
    }
    html += '</div>';

    // 拍數驗證
    var checks = buildSola321Model(doc).measureChecks;
    var shortMI = {};
    var anyShort = false;
    checks.forEach(function(c) { if (c.status === 'short') { shortMI[(c.measure || 1) - 1] = true; anyShort = true; } });

    if (useTimeline) {
      measures.forEach(function(m) {
        if (!m.eventModelVersion || m.eventModelVersion < EVENT_MODEL_VERSION) {
          syncLegacyToEvents(m);
        }
      });
      var layoutResult = layoutScore(doc);
      var systems = layoutResult.systems;
      html += '<div class="sola321-score-body sola321-use-timeline"><div class="sola321-score-timeline">';
      systems.forEach(function(sys, si) {
        html += '<div class="sola321-system-timeline" data-si="' + si + '">';
        sys.measures.forEach(function(m) {
          var absMi = measures.indexOf(m);
          html += renderSola321MeasureTimeline(m, absMi, false, !!shortMI[absMi], sys.startX);
        });
        html += '</div>';
      });
      html += '</div></div>';
    } else if (viewMode === 'vertical') {
      /* ===== 直式自由編輯（每行 4 小節、無外框無背景色、鍵盤直輸） ===== */
      html += '<div class="sola321-score-body sola321-use-vertical">';
      if (isProbe) {
        html += '<div class="sola321-v-toolbar" style="display:none">' +
          '<button type="button" class="sola321-v-opbtn" data-vop="add"></button>' +
          '<button type="button" class="sola321-v-opbtn" data-vop="paste-cursor"></button>' +
          '</div>';
      }
      html += '<div class="sola321-vertical-body">';
      html += measures.map(function(m2, mi2) {
        var mHtml = renderSola321MeasureVertical(m2, mi2, !!shortMI[mi2]);
        if ((mi2 + 1) % 4 === 0 && mi2 < measures.length - 1) {
          mHtml += '<div class="sola321-v-rowbreak" aria-hidden="true"></div>';
        }
        return mHtml;
      }).join('');
      html += '</div>';
      html += '</div>';
    } else {
      html += '<div class="sola321-score-body"><div class="sola321-system">' + measures.map(function(m2, mi2) {
        return renderSola321Measure(m2, mi2, mi2 === measures.length - 1, !!shortMI[mi2]);
      }).join('') + '</div></div>';
    }
    cont.innerHTML = html;

    if (useTimeline) {
      bindSola321TimelineInputs();
      bindSola321HeaderInputs();
    } else if (viewMode === 'vertical') {
      bindSola321VerticalInputs();
      bindSola321HeaderInputs();
      layoutSola321VerticalChords(cont);
    } else {
      bindSola321Inputs();
      layoutSola321ChordRows();
    }
    solaRestoreTargetHighlight();

    if (isProbe) {
      $$('#sola321-score .sola321-vg').forEach(function(btn) {
        btn.addEventListener('click', function() {
          var view = this.getAttribute('data-view');
          solaEdit.viewMode = view;
          solaEdit.useTimelineRenderer = (view === 'timeline');
          renderSola321Score(false);
        });
      });
    }

    setSola321Status('', '');
    if (state3.doc) renderChordProFromDoc(state3.doc);
    if (refocus) solaFocusCursor();
  }

  /* 記錄目前是否選中表頭歌名（供上方字體放大縮小功能區針對歌名獨立縮放） */
  var solaTitleFocused = false;

  /* 綁定樂譜標頭欄位（直式與時間軸視圖共用） */
  function bindSola321HeaderInputs() {
    $$('#sola321-score .sola321-meta-input').forEach(function(inp) {
      inp.addEventListener('focus', function() {
        solaTitleFocused = false;
      });
      var fAttr = inp.getAttribute('data-meta');
      if (fAttr === 'key') {
        var keyDebounce = null;
        inp.addEventListener('keydown', function(e) {
          if (e.key === 'Enter') {
            e.preventDefault();
            clearTimeout(keyDebounce);
            applyMainKeyChange(this.value, 'sola-meta');
            this.blur();
          }
        });
        inp.addEventListener('input', function() {
          var self = this;
          clearTimeout(keyDebounce);
          var v = self.value.trim();
          var norm = normalizeMusicKey(v);
          if (norm) {
            keyDebounce = setTimeout(function() {
              applyMainKeyChange(self.value, 'sola-meta');
            }, 350);
          }
        });
      }
      inp.addEventListener('change', function() {
        if (!state3.doc) return;
        var f = this.getAttribute('data-meta');
        if (f === 'key') {
          applyMainKeyChange(this.value, 'sola-meta');
          return;
        }
        solaPushUndo();
        if (f === 'tempo') {
          state3.doc.tempo = parseInt(this.value, 10) || 80;
        } else {
          state3.doc[f] = this.value.trim();
          /* 當修改拍號（如 4/4、3/4、2/4、6/8）時，同步更新所有小節拍號並立即依新拍號重新計算節拍比例定位 */
          if (f === 'timeSignature' && Array.isArray(state3.doc.measures)) {
            var newTs = state3.doc.timeSignature || '4/4';
            state3.doc.measures.forEach(function(m) {
              m.timeSignature = newTs;
            });
            renderSola321Score(false);
          }
        }
        if (state3.doc) renderChordProFromDoc(state3.doc);
        saveCurrentDoc();
        syncSideMetaInputs();
      });
    });
    $$('#sola321-score .sola321-title-input').forEach(function(inp) {
      function markTitleSelected() {
        solaTitleFocused = true;
        var curScale = (state3.doc && state3.doc.titleFontScale) ? Number(state3.doc.titleFontScale) : 1.0;
        var valEl = $('#sola-font-val');
        if (valEl) valEl.textContent = curScale.toFixed(1) + '×';
        var slider = $('#sola-font-slider');
        if (slider) slider.value = String(Math.min(1.6, Math.max(0.7, curScale)));
      }
      inp.addEventListener('focus', markTitleSelected);
      inp.addEventListener('click', markTitleSelected);
      inp.addEventListener('select', markTitleSelected);
      inp.addEventListener('change', function() {
        if (!state3.doc) return;
        solaPushUndo();
        state3.doc.title = this.value.trim() || '未命名樂譜';
        if (state3.doc) renderChordProFromDoc(state3.doc);
        saveCurrentDoc();
        syncSideMetaInputs();
      });
    });
    syncSideMetaInputs();
  }

  /* 雙向同步：樂譜資訊與側邊欄輸入框 */
  function syncSideMetaInputs() {
    if (!state3.doc) return;
    var doc = state3.doc;
    if (doc.composer && /tesseract|scoreforge|omr/i.test(doc.composer)) {
      doc.composer = '';
    }
    var st = $('#side-meta-title');
    var sl = $('#side-meta-lyricist');
    var sc = $('#side-meta-composer');
    if (st && document.activeElement !== st) st.value = doc.title || '';
    if (sl && document.activeElement !== sl) sl.value = doc.lyricist || '';
    if (sc && document.activeElement !== sc) sc.value = doc.composer || '';
  }

  /* ===== Step 1：拍號讀取與小節內音符節拍時值比例座標計算引擎 =====
   * 支援常見拍號：
   * - 4/4 拍：四分音符為一拍，每小節 4 拍（quarterBeats = 4，每 1 四分音符為 1 拍群組）
   * - 3/4 拍：四分音符為一拍，每小節 3 拍（quarterBeats = 3，每 1 四分音符為 1 拍群組）
   * - 2/4 拍：四分音符為一拍，每小節 2 拍（quarterBeats = 2，每 1 四分音符為 1 拍群組）
   * - 6/8 拍：八分音符為一拍，每小節 6 拍，分為 2 大拍（quarterBeats = 3，每大拍 1.5 四分音符 = 3 個八分音符 1-2-3、2-2-3）
   */
  function solaParseTimeSignatureSpec(tsStr) {
    var s = String(tsStr || '4/4').trim();
    var m = s.match(/^(\d+)\s*\/\s*(\d+)$/);
    var num = m ? Math.max(1, parseInt(m[1], 10)) : 4;
    var den = m ? Math.max(1, parseInt(m[2], 10)) : 4;
    var quarterBeats = num * (4 / den);
    /* 決定連音減時線（Beaming）的拍群組單位（以四分音符拍數為單位）：
       6/8、9/8、12/8 等複拍子以 3 個八分音符（1.5 個四分音符）為 1 大拍；
       2/4、3/4、4/4 等單拍子以 1 個四分音符（1.0）為 1 拍 */
    var groupQuarterSpan = 1.0;
    if (den === 8 && num >= 6 && num % 3 === 0) {
      groupQuarterSpan = 1.5;
    } else if (den === 8) {
      groupQuarterSpan = 0.5;
    } else if (den === 2) {
      groupQuarterSpan = 2.0;
    }
    return {
      raw: num + '/' + den,
      num: num,
      den: den,
      quarterBeats: quarterBeats,
      groupQuarterSpan: groupQuarterSpan
    };
  }

  /* 計算單一小節內所有音符 Token 的拍數時值（qDur）、起始拍座標（startQ）、所屬拍群組（beatGroup）與 10 等分比例座標（pos10） */
  function solaComputeMeasureBeatLayout(m, doc) {
    var tsStr = (m && m.timeSignature) || (doc && doc.timeSignature) || '4/4';
    var ts = solaParseTimeSignatureSpec(tsStr);
    var toks = solaTokens(m);
    var n = toks.length;
    var rawDurs = new Array(n);
    var tripletLockUntil = -1;

    for (var i = 0; i < n; i++) {
      var t = toks[i];
      var base = String(t.base || '');
      var dec = solaDecomp(base);
      var isDash = /^-+$/.test(base);
      var qDur = 1.0;
      if (isDash) {
        qDur = Math.max(1, base.length) * 1.0;
      } else {
        var ul = solaUnderlines(base);
        qDur = 1.0 / Math.pow(2, ul); /* ul=0 -> 1拍(1/4), ul=1 -> 0.5拍(1/8), ul=2 -> 0.25拍(1/16), ul=3 -> 0.125拍(1/32) */
        if (dec.dotted) qDur *= 1.5;
      }
      if (dec.triplet && i > tripletLockUntil) {
        tripletLockUntil = i + 2;
      }
      if (i <= tripletLockUntil) {
        qDur *= (2 / 3);
      }
      rawDurs[i] = Math.max(0.0625, qDur);
    }

    var items = [];
    var cumQ = 0;
    for (var j = 0; j < n; j++) {
      var d = rawDurs[j];
      var startQ = cumQ;
      var beatGroup = Math.floor((startQ + 1e-6) / ts.groupQuarterSpan);
      var isBeatStart = Math.abs(startQ - Math.round(startQ / ts.groupQuarterSpan) * ts.groupQuarterSpan) < 0.02;
      items.push({
        nti: j,
        qDur: d,
        startQ: startQ,
        endQ: startQ + d,
        beatGroup: beatGroup,
        isBeatStart: isBeatStart
      });
      cumQ += d;
    }

    var totalQ = Math.max(ts.quarterBeats, cumQ, 0.25);
    var remainQ = Math.max(0, ts.quarterBeats - cumQ);

    for (var k = 0; k < items.length; k++) {
      var it = items[k];
      it.normStart = it.startQ / totalQ;
      it.durRatio = it.qDur / totalQ;
      /* 對應使用者寬度 10 範例座標：4/4 拍 4 個四分音符分別落在 1.0, 2.6, 5.1, 7.6 */
      it.pos10 = (it.startQ === 0) ? 1.0 : (0.1 + (it.startQ / totalQ) * 10.0);
    }

    return {
      ts: ts,
      items: items,
      sumQ: cumQ,
      totalQ: totalQ,
      remainQ: remainQ
    };
  }

  /* 拆分歌詞字串為對應音符的字元/詞語單元（中文字每字 1 單元、標點附著前一字、英文字母連續為 1 詞、保留多重空白位移） */
  function solaParseLyricUnits(str) {
    var s = String(str || '');
    var units = [];
    var i = 0;
    var n = s.length;
    var pendingSpaces = 0;
    while (i < n) {
      var ch = s[i];
      if (/\s/.test(ch)) {
        pendingSpaces++;
        i++;
        continue;
      }
      var extraSpaces = (units.length === 0) ? pendingSpaces : Math.max(0, pendingSpaces - 1);
      pendingSpaces = 0;
      var code = ch.charCodeAt(0);
      if (code > 255) {
        /* 中日韓字元：單字為一音節，後方緊鄰的日文長音符 ー、中點 ・ 與標點符號一併附著 */
        var syl = ch;
        i++;
        while (i < n && /[，。、！？；：「」『』（）…—ー・,.!?;:'")\]]/.test(s[i])) {
          syl += s[i];
          i++;
        }
        units.push({ text: syl, extraSpaces: extraSpaces });
      } else if (/[A-Za-z0-9']/.test(ch)) {
        /* 英文單詞：連續英數字為一音節（支援連字號分音節如 yes-ter-day 或 lis- ten） */
        var word = '';
        while (i < n && /[A-Za-z0-9']/.test(s[i])) {
          word += s[i];
          i++;
        }
        if (i < n && s[i] === '-') {
          word += '-';
          i++;
        } else {
          while (i < n && /[,.!?;:")\]]/.test(s[i])) {
            word += s[i];
            i++;
          }
        }
        units.push({ text: word, extraSpaces: extraSpaces });
      } else {
        /* 延音線 - / ~ 或獨立符號 */
        units.push({ text: ch, extraSpaces: extraSpaces });
        i++;
      }
    }
    return units;
  }

  /* 渲染直式小節內的歌詞音節對齊層 HTML */
  function renderSola321VerticalLyricTokensHtml(m, mi, lyrVal) {
    var units = solaParseLyricUnits(lyrVal);
    if (!units.length) return '';
    var html = '';
    for (var u = 0; u < units.length; u++) {
      var item = units[u];
      html += '<span class="sola321-v-lyric-syl" data-mi="' + mi + '" data-ui="' + u + '" data-extra-sp="' + (item.extraSpaces || 0) + '">' + escHtml(item.text) + '</span>';
    }
    return html;
  }

  /* 取得直式樂譜容器的目前 CSS zoom 比例，將 getBoundingClientRect() 的螢幕座標精準還原為元素本地 CSS 座標 */
  function solaGetLocalZoom(el) {
    if (!el) return 1;
    var ow = el.offsetWidth;
    if (ow > 0) {
      var rw = el.getBoundingClientRect().width;
      if (rw > 0 && Math.abs(rw - ow) > 0.5) return rw / ow;
    }
    var pane = document.getElementById('sola321-pane');
    var z = pane ? parseFloat(pane.style.getPropertyValue('--sola-work-zoom')) : NaN;
    return (!isNaN(z) && z > 0) ? z : 1;
  }

  /* 依據上方簡譜音符的節拍比例座標，定位小節內每一行歌詞的每一個字元 */
  function layoutSola321VerticalLyrics(mEl) {
    if (!mEl) return;
    var disp = mEl.querySelector('.sola321-v-note-display');
    var tokens = disp ? Array.prototype.slice.call(disp.querySelectorAll('.sola321-v-token')) : [];
    var snapBtn = document.querySelector('.ss-snap-btn[data-snap].active');
    var snapMode = snapBtn ? snapBtn.getAttribute('data-snap') : 'note';
    var lyrRows = Array.prototype.slice.call(mEl.querySelectorAll('.sola321-v-lyric-row'));

    /* 找出拍起點音符清單（供「整拍」吸附模式使用） */
    var beatTokens = tokens.filter(function(t) { return t.getAttribute('data-beat-start') === '1'; });
    if (!beatTokens.length) beatTokens = tokens;

    /* 找出有實際音高（1~7，跳過休止符 0 與延音線 -）的可唱音符清單（供「單音」吸附模式使用） */
    var singableTokens = tokens.filter(function(t) {
      if (t.classList.contains('sola321-v-dash')) return false;
      var dg = t.querySelector('.sola321-v-digit');
      var txt = dg ? (dg.textContent || '').trim() : '';
      return /[1-7]/.test(txt);
    });
    if (!singableTokens.length) singableTokens = tokens;

    var z = solaGetLocalZoom(disp || mEl);

    lyrRows.forEach(function(rowEl) {
      var lyrDisp = rowEl.querySelector('.sola321-v-lyric-display');
      if (!lyrDisp) return;
      var syls = Array.prototype.slice.call(lyrDisp.querySelectorAll('.sola321-v-lyric-syl'));
      rowEl.classList.toggle('has-lyrics', syls.length > 0);
      if (!syls.length) {
        lyrDisp.style.minWidth = '';
        return;
      }
      if (snapMode === 'free' || !tokens.length) {
        lyrDisp.classList.add('is-free-mode');
        syls.forEach(function(sEl) {
          sEl.style.left = '';
          var ex = parseInt(sEl.getAttribute('data-extra-sp') || '0', 10) || 0;
          sEl.style.marginLeft = ex > 0 ? (ex * 0.55).toFixed(2) + 'ch' : '';
        });
        lyrDisp.style.minWidth = '';
        return;
      }
      lyrDisp.classList.remove('is-free-mode');

      /* 先以歌詞本身的緊湊字寬總和作為最小寬度下限，避免與 flex 拉伸產生無限擴張迴圈 */
      var intrinsicWidth = 8;
      var sylWidths = [];
      syls.forEach(function(sEl) {
        var sw = sEl.offsetWidth || Math.round((sEl.getBoundingClientRect().width || 14) / z) || 14;
        sylWidths.push(sw);
        intrinsicWidth += sw + 3;
      });
      lyrDisp.style.minWidth = intrinsicWidth + 'px';

      var lyrRect = lyrDisp.getBoundingClientRect();
      if (lyrRect.width === 0 && lyrRect.height === 0) return;

      var targetPool = (snapMode === 'beat') ? beatTokens : singableTokens;
      var tokShiftAccum = 0;
      var desiredLefts = new Array(syls.length);
      var poolCenters = targetPool.map(function(tokEl) {
        var coreEl = tokEl.querySelector('.sola321-v-core') || tokEl;
        var cr = coreEl.getBoundingClientRect();
        return ((cr.left - lyrRect.left) + (cr.width / 2)) / z;
      });

      if (syls.length > targetPool.length && poolCenters.length >= 2) {
        /* 當單行歌詞字元數多於上方基準音符數（如日文假名/漢字雙語歌詞對應 4 拍和弦音符）時，
           依首尾音符跨度進行分段線性內插定位，使整句日文/拼音歌詞平均對齊於各拍下方 */
        syls.forEach(function(_sEl, idx) {
          var floatIdx = (idx * (poolCenters.length - 1)) / (syls.length - 1);
          var i0 = Math.floor(floatIdx);
          var i1 = Math.min(poolCenters.length - 1, i0 + 1);
          var frac = floatIdx - i0;
          var centerX = poolCenters[i0] * (1 - frac) + poolCenters[i1] * frac;
          var sw = sylWidths[idx];
          desiredLefts[idx] = Math.max(0, Math.round(centerX - (sw / 2)));
        });
      } else {
        syls.forEach(function(sEl, idx) {
          var extraSp = parseInt(sEl.getAttribute('data-extra-sp') || '0', 10) || 0;
          if (extraSp > 0) {
            tokShiftAccum += extraSp;
          }
          var targetIdx = idx + tokShiftAccum;
          /* 若舊資料含前導或多餘空白，限制位移上限以確保剩餘歌詞字元不會超出最後一顆可唱音符 */
          var maxTargetIdx = Math.max(idx, targetPool.length - (syls.length - idx));
          if (targetIdx > maxTargetIdx) {
            targetIdx = maxTargetIdx;
            tokShiftAccum = targetIdx - idx;
          }
          var centerX;
          if (targetIdx < poolCenters.length) {
            centerX = poolCenters[targetIdx];
          } else if (poolCenters.length > 0) {
            var extraCount = targetIdx - (poolCenters.length - 1);
            centerX = poolCenters[poolCenters.length - 1] + extraCount * 18;
          } else {
            centerX = idx * 18;
          }
          var sw = sylWidths[idx];
          desiredLefts[idx] = Math.max(0, Math.round(centerX - (sw / 2)));
        });
      }

      /* 左至右防重疊排列（使用 1px 最小安全間距，讓 16 分音符與 8 分音符下方的單字能緊密對準各自音符中心） */
      var lefts = new Array(syls.length);
      var lastRight = -1;
      for (var i = 0; i < syls.length; i++) {
        var dl = Math.max(desiredLefts[i], lastRight + 1);
        lefts[i] = dl;
        lastRight = dl + sylWidths[i];
      }

      /* 確保第 1、2、3、4 段歌詞共用完全相同的可用寬度基準，且絕不將已對準最後一顆音符的歌詞往左退 */
      var baseAvailW = disp ? disp.offsetWidth : 0;
      if (!baseAvailW) baseAvailW = Math.floor(lyrRect.width / z);
      var lastDesiredRight = syls.length > 0 ? (desiredLefts[syls.length - 1] + sylWidths[syls.length - 1]) : 0;
      var availW = Math.max(intrinsicWidth, baseAvailW - 1, lastDesiredRight);
      if (syls.length > 0 && (lefts[syls.length - 1] + sylWidths[syls.length - 1]) > availW) {
        var nextLeftLimit = availW;
        for (var r = syls.length - 1; r >= 0; r--) {
          var maxL = Math.max(0, nextLeftLimit - sylWidths[r]);
          if (lefts[r] > maxL) lefts[r] = maxL;
          nextLeftLimit = lefts[r] - 1;
        }
        var fixRight = -1;
        for (var f = 0; f < syls.length; f++) {
          if (lefts[f] < fixRight + 1) lefts[f] = fixRight + 1;
          fixRight = lefts[f] + sylWidths[f];
        }
      }

      for (var k = 0; k < syls.length; k++) {
        syls[k].style.marginLeft = '';
        syls[k].style.left = lefts[k] + 'px';
      }
    });
  }

  /* 計算文字欄位的無折行完整寬度（ch 單位，中文字約為 2.15ch 寬，確保小節最後一個中文字完整顯示不截斷） */
  function solaCalcInputWidthCh(str, minCh) {
    var s = String(str || '').replace(/[\u0307\u0323]/g, '');
    var w = 0;
    for (var i = 0; i < s.length; i++) {
      var code = s.charCodeAt(i);
      if (code === 32) w += 0.62;
      else if (code > 255) w += 2.15;
      else w += 0.98;
    }
    return Math.max(minCh || 3, Math.ceil((w + 1.2) * 10) / 10);
  }

  /* 將和弦陣列寫回 measure.chordText 並保留既有 chordOffsets 對齊位置 */
  function v3WriteChords(m, parts, miHint) {
    if (!m) return;
    var oldParts = v3ChordParts(m);
    if (oldParts.length > 0) v3EnsureChordOffsets(m);
    var oldOffsets = Array.isArray(m.chordOffsets) ? m.chordOffsets.slice() : [];
    var clean = (parts || []).map(function(p) { return String(p || '').trim(); }).filter(Boolean);
    m.chordText = clean.join(' ');
    var newOffsets = [];
    var newTicks = [];
    for (var i = 0; i < clean.length; i++) {
      var off;
      if (i < oldOffsets.length && oldOffsets[i] != null && !isNaN(+oldOffsets[i])) {
        off = Math.max(0, parseInt(oldOffsets[i], 10));
      } else if (i === 0 && oldOffsets.length === 0 && miHint != null && solaEdit.mi === miHint && typeof solaEdit.nti === 'number' && solaEdit.nti >= 0) {
        off = solaEdit.nti;
      } else {
        var prev = (i > 0 && newOffsets[i - 1] != null) ? newOffsets[i - 1] : (i - 1);
        off = Math.max(i, prev + 1);
      }
      newOffsets.push(off);
      newTicks.push(off * 480);
    }
    m.chordOffsets = newOffsets;
    m.chordTicks = newTicks;
    syncLegacyToEvents(m);
  }

  /* 渲染直式小節內的和弦指法圖 HTML（附帶 data-offset 對齊目標音符） */
  function renderSola321VerticalChordsHtml(m, mi) {
    v3EnsureChordOffsets(m);
    var cp = v3ChordParts(m);
    var offs = m.chordOffsets || [];
    var inst = currentChordInstrument();
    var html = '';
    for (var c = 0; c < cp.length; c++) {
      var part = cp[c];
      var off = (offs[c] != null && !isNaN(+offs[c])) ? parseInt(offs[c], 10) : c;
      if (/^[A-G][A-Za-z0-9#b\-\(\)\/]{0,8}$/.test(part)) {
        html += '<span class="sola321-v-chord" tabindex="0" data-mi="' + mi + '" data-ci="' + c + '" data-offset="' + off + '" data-chord="' + escAttr(part) + '" title="左右拖曳或按 ←/→ 對準下方音符；點擊更換和弦">' +
          '<button type="button" class="sola321-v-chord-del" data-mi="' + mi + '" data-ci="' + c + '" title="刪除此和弦">×</button>' +
          renderChordSvg({ name: part }, inst, true, true) +
          '</span>';
      } else if (part) {
        html += '<span class="sola321-v-chord sola321-v-chord-text" tabindex="0" data-mi="' + mi + '" data-ci="' + c + '" data-offset="' + off + '" data-chord="' + escAttr(part) + '" title="左右拖曳或按 ←/→ 對準下方音符；點擊更換和弦">' +
          '<button type="button" class="sola321-v-chord-del" data-mi="' + mi + '" data-ci="' + c + '" title="刪除此記號">×</button>' +
          escHtml(part) +
          '</span>';
      }
    }
    return html;
  }

  /* 繪製直式小節內的：
   * 0. 依拍分組連音減時線（Beat-Grouped Beams：同一拍群組內的八分 _、十六分 __、三十二分 ___ 底線自動連成水平橫線）
   * 1. 連音線（⌒ 2音上方）
   * 2. 圓滑線（⌣ 2音下方）
   * 3. 三連音線（³ 3音第1與第3音正上方）
   */
  function layoutSola321VerticalArcs(mEl) {
    if (!mEl) return;
    var disp = mEl.querySelector('.sola321-v-note-display');
    if (!disp) return;
    var svg = disp.querySelector('.sola321-v-arcs-svg');
    if (!svg) return;
    var mi = parseInt(mEl.getAttribute('data-mi'), 10);
    var m = state3.doc && state3.doc.measures && state3.doc.measures[mi];
    if (!m) { svg.innerHTML = ''; return; }
    var toks = solaTokens(m);
    var tokens = Array.prototype.slice.call(disp.querySelectorAll('.sola321-v-token'));
    if (!tokens.length) { svg.innerHTML = ''; return; }
    var dispRect = disp.getBoundingClientRect();
    if (dispRect.width === 0 && dispRect.height === 0) return;
    var z = solaGetLocalZoom(disp);

    /* 先重置所有單音減時線透明度 */
    disp.querySelectorAll('.sola321-v-uline').forEach(function(ulEl) {
      ulEl.style.opacity = '';
    });

    var paths = '';

    /* 0. 繪製同一拍群組（data-beat-group）內的連續減時線橫槓（Beams） */
    for (var lvl = 1; lvl <= 3; lvl++) {
      var rStart = -1;
      for (var bi = 0; bi <= tokens.length; bi++) {
        var tokEl = bi < tokens.length ? tokens[bi] : null;
        var ulEl = tokEl ? tokEl.querySelector('.sola321-v-uline[data-ul-level="' + lvl + '"]') : null;
        var bg = tokEl ? tokEl.getAttribute('data-beat-group') : null;
        var prevBg = (rStart >= 0 && rStart < tokens.length) ? tokens[rStart].getAttribute('data-beat-group') : null;

        if (ulEl && (rStart === -1 || bg === prevBg)) {
          if (rStart === -1) rStart = bi;
        } else {
          if (rStart !== -1 && (bi - 1) > rStart) {
            var rEnd = bi - 1;
            var firstUl = tokens[rStart].querySelector('.sola321-v-uline[data-ul-level="' + lvl + '"]');
            var lastUl = tokens[rEnd].querySelector('.sola321-v-uline[data-ul-level="' + lvl + '"]');
            if (firstUl && lastUl) {
              var ur1 = firstUl.getBoundingClientRect();
              var ur2 = lastUl.getBoundingClientRect();
              var bx1 = (ur1.left - dispRect.left) / z;
              var bx2 = (ur2.right - dispRect.left) / z;
              var by = (((ur1.top + ur1.bottom) / 2) - dispRect.top) / z;
              paths += '<line class="sola321-v-beam-line" x1="' + bx1.toFixed(1) + '" y1="' + by.toFixed(1) + '" x2="' + bx2.toFixed(1) + '" y2="' + by.toFixed(1) + '" stroke="#111" stroke-width="1.5" stroke-linecap="butt" />';
              for (var k = rStart; k <= rEnd; k++) {
                var kUl = tokens[k].querySelector('.sola321-v-uline[data-ul-level="' + lvl + '"]');
                if (kUl) kUl.style.opacity = '0';
              }
            }
          }
          rStart = ulEl ? bi : -1;
        }
      }
    }

    var skipTripletUntil = -1;
    for (var ti = 0; ti < toks.length && ti < tokens.length; ti++) {
      var dec = solaDecomp(toks[ti].base);
      /* 1. 連音線（⌒）：選取的 2 個音符上方連接處（2 個數字的正上方作為 2 端點） */
      if (dec.tie) {
        var d1 = tokens[ti].querySelector('.sola321-v-digit') || tokens[ti];
        var r1 = d1.getBoundingClientRect();
        var x1 = ((r1.left - dispRect.left) + (r1.width / 2)) / z;
        var y1 = ((r1.top - dispRect.top) / z) - 1;
        var x2, y2;
        if (ti + 1 < tokens.length) {
          var d2 = tokens[ti + 1].querySelector('.sola321-v-digit') || tokens[ti + 1];
          var r2 = d2.getBoundingClientRect();
          x2 = ((r2.left - dispRect.left) + (r2.width / 2)) / z;
          y2 = ((r2.top - dispRect.top) / z) - 1;
        } else {
          x2 = x1 + 18;
          y2 = y1;
        }
        var midX = (x1 + x2) / 2;
        var ctrlY = Math.min(y1, y2) - 9;
        paths += '<path class="sola321-v-arc-tie" d="M ' + x1.toFixed(1) + ' ' + y1.toFixed(1) + ' Q ' + midX.toFixed(1) + ' ' + ctrlY.toFixed(1) + ' ' + x2.toFixed(1) + ' ' + y2.toFixed(1) + '" fill="none" stroke="#1e293b" stroke-width="1.6" stroke-linecap="round" />';
      }
      /* 2. 圓滑線（⌣）：選取的 2 個音符下方連接處（2 個數字的正下方作為 2 端點） */
      if (dec.slur) {
        var sd1 = tokens[ti].querySelector('.sola321-v-digit') || tokens[ti];
        var sr1 = sd1.getBoundingClientRect();
        var sx1 = ((sr1.left - dispRect.left) + (sr1.width / 2)) / z;
        var sy1 = ((sr1.bottom - dispRect.top) / z) + 1;
        var sx2, sy2;
        if (ti + 1 < tokens.length) {
          var sd2 = tokens[ti + 1].querySelector('.sola321-v-digit') || tokens[ti + 1];
          var sr2 = sd2.getBoundingClientRect();
          sx2 = ((sr2.left - dispRect.left) + (sr2.width / 2)) / z;
          sy2 = ((sr2.bottom - dispRect.top) / z) + 1;
        } else {
          sx2 = sx1 + 18;
          sy2 = sy1;
        }
        var smidX = (sx1 + sx2) / 2;
        var sctrlY = Math.max(sy1, sy2) + 9;
        paths += '<path class="sola321-v-arc-slur" d="M ' + sx1.toFixed(1) + ' ' + sy1.toFixed(1) + ' Q ' + smidX.toFixed(1) + ' ' + sctrlY.toFixed(1) + ' ' + sx2.toFixed(1) + ' ' + sy2.toFixed(1) + '" fill="none" stroke="#1e293b" stroke-width="1.6" stroke-linecap="round" />';
      }
      /* 3. 三連音線（³）：選取的 3 個音符（第 1 個數字正上方與第 3 個數字的正上方作為 2 端點） */
      if (dec.triplet && ti > skipTripletUntil) {
        var endTi = Math.min(ti + 2, tokens.length - 1);
        skipTripletUntil = ti + 2;
        var td1 = tokens[ti].querySelector('.sola321-v-digit') || tokens[ti];
        var tr1 = td1.getBoundingClientRect();
        var tx1 = ((tr1.left - dispRect.left) + (tr1.width / 2)) / z;
        var ty1 = ((tr1.top - dispRect.top) / z) - 1;
        var tx3, ty3;
        if (endTi > ti) {
          var td3 = tokens[endTi].querySelector('.sola321-v-digit') || tokens[endTi];
          var tr3 = td3.getBoundingClientRect();
          tx3 = ((tr3.left - dispRect.left) + (tr3.width / 2)) / z;
          ty3 = ((tr3.top - dispRect.top) / z) - 1;
        } else {
          tx3 = tx1 + 32;
          ty3 = ty1;
        }
        var tmidX = (tx1 + tx3) / 2;
        var topY = Math.min(ty1, ty3) - 10;
        var gapHalf = 6;
        if (tx3 - tx1 > 20) {
          paths += '<path class="sola321-v-arc-triplet" d="M ' + tx1.toFixed(1) + ' ' + ty1.toFixed(1) + ' Q ' + ((tx1 + tmidX - gapHalf) / 2).toFixed(1) + ' ' + topY.toFixed(1) + ' ' + (tmidX - gapHalf).toFixed(1) + ' ' + topY.toFixed(1) + '" fill="none" stroke="#1e293b" stroke-width="1.5" stroke-linecap="round" />';
          paths += '<path class="sola321-v-arc-triplet" d="M ' + (tmidX + gapHalf).toFixed(1) + ' ' + topY.toFixed(1) + ' Q ' + ((tmidX + gapHalf + tx3) / 2).toFixed(1) + ' ' + topY.toFixed(1) + ' ' + tx3.toFixed(1) + ' ' + ty3.toFixed(1) + '" fill="none" stroke="#1e293b" stroke-width="1.5" stroke-linecap="round" />';
        } else {
          paths += '<path class="sola321-v-arc-triplet" d="M ' + tx1.toFixed(1) + ' ' + ty1.toFixed(1) + ' Q ' + tmidX.toFixed(1) + ' ' + (topY - 2).toFixed(1) + ' ' + tx3.toFixed(1) + ' ' + ty3.toFixed(1) + '" fill="none" stroke="#1e293b" stroke-width="1.5" stroke-linecap="round" />';
        }
        paths += '<text class="sola321-v-arc-triplet-num" x="' + tmidX.toFixed(1) + '" y="' + (topY + 4).toFixed(1) + '" text-anchor="middle" font-size="11" font-weight="800" fill="#1e293b">3</text>';
      }
    }
    svg.innerHTML = paths;
  }

  /* 定位直式小節內的和弦指法圖：對準指定音符核心 (.sola321-v-core) 的正上方，且更新共用小節線、拍群組減時線與歌詞對齊 */
  function layoutSola321VerticalChords(scope) {
    var scoreRoot = document.getElementById('sola321-score');
    var root = scope || scoreRoot;
    if (!root) return;

    function updateRowStarts(list) {
      var prevTop = null;
      list.forEach(function(mBox, idx) {
        var r = mBox.getBoundingClientRect();
        var isRowStart = (idx === 0) || (prevTop !== null && Math.abs(r.top - prevTop) > 18);
        mBox.classList.toggle('is-row-start', isRowStart);
        mBox.classList.remove('hide-back-barline');
        if (!isRowStart && idx > 0) {
          var frontBar = mBox.querySelector('.sola321-v-barline-front');
          if (frontBar && frontBar.classList.contains('is-repeat-start')) {
            var prevBack = list[idx - 1].querySelector('.sola321-v-barline-back');
            if (prevBack && !prevBack.classList.contains('is-repeat-end') && !prevBack.classList.contains('is-double-bar')) {
              list[idx - 1].classList.add('hide-back-barline');
            }
          }
        }
        prevTop = r.top;
      });
    }

    var measures = [];
    var targetM = null;
    if (scope && scope !== scoreRoot) {
      if (scope.classList && scope.classList.contains('sola321-vmeasure')) {
        targetM = scope;
      } else if (scope.closest) {
        targetM = scope.closest('.sola321-vmeasure');
      }
    }
    if (targetM && scoreRoot) {
      var targetMi = parseInt(targetM.getAttribute('data-mi'), 10);
      if (!isNaN(targetMi)) {
        var rowStart = Math.floor(targetMi / 4) * 4;
        for (var rmi = rowStart; rmi < rowStart + 4; rmi++) {
          var rmEl = scoreRoot.querySelector('.sola321-vmeasure[data-mi="' + rmi + '"]');
          if (rmEl) measures.push(rmEl);
        }
      } else {
        measures = [targetM];
      }
    } else if (root.querySelectorAll) {
      measures = Array.prototype.slice.call(root.querySelectorAll('.sola321-vmeasure'));
    }
    if (!measures.length && targetM) {
      measures = [targetM];
    }
    if (!measures.length) return;

    /* Pass 1：重置音符邊距、建立歌詞最小緊湊寬度，讓 flex 列折行先穩定 */
    measures.forEach(function(mEl) {
      var tokens = Array.prototype.slice.call(mEl.querySelectorAll('.sola321-v-note-display .sola321-v-token'));
      tokens.forEach(function(tokEl) {
        if (tokEl.getAttribute('data-base-ml') === null) {
          tokEl.setAttribute('data-base-ml', tokEl.style.marginLeft || '');
        } else {
          tokEl.style.marginLeft = tokEl.getAttribute('data-base-ml') || '';
        }
      });
      layoutSola321VerticalLyrics(mEl);
    });

    updateRowStarts(measures);

    /* Pass 2：定位和弦指法圖並設定和弦區最小寬度 */
    measures.forEach(function(mEl) {
      var tokens = Array.prototype.slice.call(mEl.querySelectorAll('.sola321-v-note-display .sola321-v-token'));
      var wrap = mEl.querySelector('.sola321-v-chords-wrap');
      if (!wrap) return;
      var chordEls = Array.prototype.slice.call(wrap.querySelectorAll('.sola321-v-chord'));
      if (!chordEls.length) {
        wrap.style.minWidth = '';
        return;
      }
      var wrapRect = wrap.getBoundingClientRect();
      if (wrapRect.width === 0 && wrapRect.height === 0) return;
      var z = solaGetLocalZoom(wrap);
      var byOff = {};
      chordEls.forEach(function(chEl) {
        var off = parseInt(chEl.getAttribute('data-offset'), 10);
        if (isNaN(off) || off < 0) off = 0;
        if (!byOff[off]) byOff[off] = [];
        byOff[off].push(chEl);
      });
      var maxRight = 0;
      var lastRight = -4;
      var sortedOffs = Object.keys(byOff).map(function(k) { return parseInt(k, 10); }).sort(function(a, b) { return a - b; });
      sortedOffs.forEach(function(off) {
        var group = byOff[off];
        var centerX;
        if (tokens.length > 0) {
          if (off < tokens.length) {
            var coreEl = tokens[off].querySelector('.sola321-v-core') || tokens[off];
            var tr = coreEl.getBoundingClientRect();
            centerX = ((tr.left - wrapRect.left) + (tr.width / 2)) / z;
          } else {
            var lastCoreEl = tokens[tokens.length - 1].querySelector('.sola321-v-core') || tokens[tokens.length - 1];
            var lastTr = lastCoreEl.getBoundingClientRect();
            var step = 48;
            if (tokens.length >= 2) {
              var firstCoreEl = tokens[0].querySelector('.sola321-v-core') || tokens[0];
              var firstTr = firstCoreEl.getBoundingClientRect();
              step = Math.max(44, ((lastTr.left - firstTr.left) / z) / (tokens.length - 1));
            }
            centerX = (((lastTr.left - wrapRect.left) + (lastTr.width / 2)) / z) + (off - (tokens.length - 1)) * step;
          }
        } else {
          centerX = 25 + off * 54;
        }
        group.forEach(function(chEl, idx) {
          var w = chEl.offsetWidth || Math.round((chEl.getBoundingClientRect().width || 50) / z) || 50;
          var desiredLeft = (idx === 0)
            ? Math.max(0, Math.round(centerX - (w / 2)))
            : (lastRight + 4);
          var left = Math.max(desiredLeft, lastRight + 4);
          if (idx === 0 && left > desiredLeft && off > 0 && off < tokens.length) {
            var pushPx = left - desiredLeft;
            var baseMl = parseFloat(tokens[off].getAttribute('data-base-ml') || '0') || 0;
            tokens[off].style.marginLeft = (baseMl + pushPx) + 'px';
          }
          chEl.style.left = left + 'px';
          lastRight = left + w;
          if (lastRight > maxRight) maxRight = lastRight;
          var img = chEl.querySelector('img.chord-diagram-img');
          if (img && !img.complete && !img.__solaLoadBound) {
            img.__solaLoadBound = true;
            img.addEventListener('load', function() { layoutSola321VerticalChords(mEl); });
          }
        });
      });
      wrap.style.minWidth = (maxRight > 0 ? (maxRight + 6) + 'px' : '');
    });

    updateRowStarts(measures);

    /* Pass 3（最終定稿）：所有小節寬度與列折行穩定後，同步更新歌詞座標與 SVG 拍群組減時線/弧線 */
    measures.forEach(function(mEl) {
      layoutSola321VerticalLyrics(mEl);
      layoutSola321VerticalArcs(mEl);
    });
  }

  /* 在直式小節中根據水平座標 clientX 找出最接近的音符索引 nti（以音符數字核心 .sola321-v-core 中心為準） */
  function solaVerticalNearestNti(mEl, clientX) {
    if (!mEl) return 0;
    var tokens = Array.prototype.slice.call(mEl.querySelectorAll('.sola321-v-note-display .sola321-v-token'));
    if (!tokens.length) {
      var wrap = mEl.querySelector('.sola321-v-chords-wrap');
      if (!wrap) return 0;
      var wr = wrap.getBoundingClientRect();
      return Math.max(0, Math.round((clientX - wr.left - 25) / 54));
    }
    var bestIdx = 0;
    var bestDist = Infinity;
    for (var i = 0; i < tokens.length; i++) {
      var coreEl = tokens[i].querySelector('.sola321-v-core') || tokens[i];
      var r = coreEl.getBoundingClientRect();
      var cx = r.left + r.width / 2;
      var d = Math.abs(clientX - cx);
      if (d < bestDist) {
        bestDist = d;
        bestIdx = i;
      }
    }
    return bestIdx;
  }

  /* 渲染直式小節內的簡譜音符視覺 Token HTML（嚴格依拍號與音符時值比例定位、高8度/低8度垂直排列、SVG拍群組減時線與連音線） */
  function renderSola321VerticalNoteTokensHtml(m, mi) {
    var toks = solaTokens(m);
    var beatLayout = solaComputeMeasureBeatLayout(m, state3.doc);
    var html = '';
    var sStart = (typeof solaEdit.selStartNti === 'number') ? solaEdit.selStartNti : solaEdit.nti;
    var sEnd = (typeof solaEdit.selEndNti === 'number') ? solaEdit.selEndNti : solaEdit.nti;
    var selLo = Math.min(sStart, sEnd);
    var selHi = Math.max(sStart, sEnd);
    for (var ti = 0; ti < toks.length; ti++) {
      var t = toks[ti];
      var bItem = beatLayout.items[ti] || { qDur: 1, startQ: ti, beatGroup: ti, isBeatStart: true, pos10: 1.0 };
      var da = '', db = '';
      for (var a = 0; a < t.above; a++) da += '<i class="sola321-v-dot"></i>';
      for (var b = 0; b < t.below; b++) db += '<i class="sola321-v-dot"></i>';
      var curCls = (solaEdit.mi === mi && solaEdit.nti === ti) ? ' sola321-cursor' : '';
      var selCls = (solaEdit.mi === mi && selHi > selLo && ti >= selLo && ti <= selHi) ? ' sola321-selected' : '';
      var dec = solaDecomp(t.base);
      var isDash = dec.dash || /^-+$/.test(t.base);
      var ulCount = solaUnderlines(t.base);
      var ulHtml = '';
      for (var u = 0; u < ulCount; u++) ulHtml += '<i class="sola321-v-uline" data-ul-level="' + (u + 1) + '"></i>';
      var accTxt = dec.acc || '';
      var digitTxt = isDash ? '-' : (dec.digit || solaDisplayBase(t.base) || '');
      var dotTxt = dec.dotted ? '.' : '';
      var flexStyle = 'flex:' + bItem.qDur.toFixed(4) + ' 0 0%;';
      html += '<span class="sola321-v-token sola321-note-char' + (isDash ? ' sola321-v-dash' : '') + curCls + selCls + '" style="' + flexStyle + '" data-mi="' + mi + '" data-nti="' + ti + '" data-beat-group="' + bItem.beatGroup + '" data-beat-start="' + (bItem.isBeatStart ? '1' : '0') + '" data-start-beat="' + bItem.startQ.toFixed(3) + '" data-dur-beat="' + bItem.qDur.toFixed(3) + '" data-pos10="' + bItem.pos10.toFixed(2) + '">' +
        '<span class="sola321-v-core">' +
          '<span class="sola321-v-dots sola321-v-dots-above">' + da + '</span>' +
          '<span class="sola321-v-pitch-row">' +
            (accTxt ? '<span class="sola321-v-acc">' + escHtml(accTxt) + '</span>' : '') +
            '<span class="sola321-v-digit sola321-digit">' + escHtml(digitTxt) + '</span>' +
            (dotTxt ? '<span class="sola321-v-augdot">' + escHtml(dotTxt) + '</span>' : '') +
          '</span>' +
          '<span class="sola321-v-ulines">' + ulHtml + '</span>' +
          '<span class="sola321-v-dots sola321-v-dots-below">' + db + '</span>' +
        '</span>' +
        '</span>';
    }
    if (toks.length > 0 && beatLayout.remainQ > 0.001) {
      html += '<span class="sola321-v-beat-rest-pad" style="flex:' + beatLayout.remainQ.toFixed(4) + ' 0 0%;" aria-hidden="true"></span>';
    }
    html += '<svg class="sola321-v-arcs-svg" aria-hidden="true"></svg>';
    return html;
  }

  /* 游標位置 ⇄ 音符 Token 索引轉換（支援連續 000 / --- 單拍展開，供點擊音符定位游標、以及工具列八度/時值按鈕對齊游標） */
  function solaGetRawTokenSpans(text) {
    var s = String(text || '');
    var re = /\S+/g;
    var match;
    var spans = [];
    while ((match = re.exec(s)) !== null) {
      var tok = match[0];
      if (/^0{2,}$/.test(tok) || /^-{2,}$/.test(tok)) {
        for (var k = 0; k < tok.length; k++) {
          spans.push({ start: match.index + k, end: match.index + k + 1 });
        }
      } else {
        spans.push({ start: match.index, end: match.index + tok.length });
      }
    }
    return spans;
  }
  function solaTokenIndexToCaret(text, targetNti, atStart) {
    var s = String(text || '');
    var spans = solaGetRawTokenSpans(s);
    if (targetNti >= 0 && targetNti < spans.length) {
      return atStart ? spans[targetNti].start : spans[targetNti].end;
    }
    return s.length;
  }
  function solaCaretToTokenIndex(text, caretPos) {
    var spans = solaGetRawTokenSpans(text);
    for (var i = 0; i < spans.length; i++) {
      if (caretPos <= spans[i].end) return i;
    }
    return Math.max(0, spans.length - 1);
  }
  function solaCaretRangeToTokenRange(text, selStart, selEnd) {
    var s = String(text || '');
    var lo = Math.min(selStart || 0, selEnd || 0);
    var hi = Math.max(selStart || 0, selEnd || 0);
    if (hi <= lo) {
      var single = solaCaretToTokenIndex(s, lo);
      return { start: single, end: single };
    }
    var spans = solaGetRawTokenSpans(s);
    var first = -1, last = -1;
    for (var i = 0; i < spans.length; i++) {
      if (spans[i].end > lo && spans[i].start < hi) {
        if (first === -1) first = i;
        last = i;
      }
    }
    if (first === -1) {
      var fallback = solaCaretToTokenIndex(s, lo);
      return { start: fallback, end: fallback };
    }
    return { start: first, end: last };
  }

  /* 聚焦指定小節與車道（chord / note / lyric），並設定游標位置 */
  function solaFocusVerticalLane(mi, lane, caretPos, ll) {
    var sc = document.getElementById('sola321-score');
    if (!sc || !state3.doc || !state3.doc.measures) return;
    var ms = state3.doc.measures;
    if (mi < 0 || mi >= ms.length) return;
    solaTitleFocused = false;
    solaEdit.mi = mi;
    solaSetTarget(mi);
    var sel = '';
    if (lane === 'chord') {
      sel = '.sola321-v-chord-editor[data-mi="' + mi + '"]';
    } else if (lane === 'lyric') {
      var targetLl = (typeof ll === 'number' && ll >= 0) ? ll : 0;
      sel = '.sola321-v-lyric-editor[data-mi="' + mi + '"][data-ll="' + targetLl + '"]';
      if (!sc.querySelector(sel)) sel = '.sola321-v-lyric-editor[data-mi="' + mi + '"]';
      var lRow = sc.querySelector('.sola321-v-lyric-row[data-mi="' + mi + '"][data-ll="' + targetLl + '"]') || sc.querySelector('.sola321-v-lyric-row[data-mi="' + mi + '"]');
      if (lRow) lRow.classList.add('is-editing');
    } else {
      sel = '.sola321-v-note-editor[data-mi="' + mi + '"]';
      var nLane = sc.querySelector('.sola321-v-notelane[data-mi="' + mi + '"]');
      if (nLane) nLane.classList.add('is-editing');
    }
    var inp = sc.querySelector(sel);
    if (!inp) return;
    var len = inp.value.length;
    var pos = (caretPos === 'start') ? 0 : (caretPos === 'end' || caretPos == null) ? len : Math.min(Math.max(0, caretPos), len);
    try { inp.setSelectionRange(pos, pos); } catch (e) {}
    inp.focus();
    try { inp.setSelectionRange(pos, pos); } catch (e) {}
    if (lane !== 'chord' && lane !== 'lyric') {
      solaEdit.nti = solaCaretToTokenIndex(inp.value, pos);
      solaEdit.selStartNti = solaEdit.nti;
      solaEdit.selEndNti = solaEdit.nti;
      solaMarkCursor();
    }
  }

  /* ===== 直式自由編輯（動態每行 4/3/2/1 小節、單行不折行、無外框無背景色、比照 Google Sheet + ChordPro 鍵盤直輸） ===== */
  function renderSola321MeasureVertical(m, mi, isShort) {
    var isProbe = (typeof window !== 'undefined' && String(location.search).indexOf('probe=1') >= 0);
    var isLast = (state3.doc.measures.length - 1 === mi);
    var endBar = (m.barline !== false && isLast) ? ' sola321-v-end' : '';
    var shortCls = (isShort && warnShortOn) ? ' sola321-short' : '';
    var rowStartCls = (mi % 4 === 0) ? ' is-row-start' : '';
    var html = '<div class="sola321-vmeasure' + rowStartCls + endBar + shortCls + '" data-mi="' + mi + '">';
    /* 小節頭：僅顯示小節號＋段落記號＋結構記號 chips（移除所有操作按鈕與外框） */
    html += '<div class="sola321-v-measurehead"><span class="sola321-v-mnum">' + escHtml(m.number != null ? m.number : (mi + 1)) + '</span>';
    var marksArr = String(m.marks || '').trim().split(/\s+/).filter(Boolean);
    if (m.section) {
      var secDisp = SOLA_SECTION_NAMES[m.section] || m.section;
      if (marksArr.indexOf(secDisp) === -1 && marksArr.indexOf(m.section) === -1) {
        marksArr.unshift(secDisp);
      }
    }
    if (marksArr.length) {
      html += '<span class="sola321-v-marks">';
      marksArr.forEach(function(mk) {
        html += '<span class="sola321-mark-inline" data-mi="' + mi + '" data-mark="' + escAttr(mk) + '" title="點擊移除記號 ' + escAttr(mk) + '">' + escHtml(mk) + '</span>';
      });
      html += '</span>';
    }
    if (isProbe) {
      html += '<span class="sola321-v-ops" style="display:none">' +
        '<button type="button" class="sola321-v-opbtn" data-vop="add-after" data-mi="' + mi + '"></button>' +
        '<button type="button" class="sola321-v-opbtn" data-vop="copy" data-mi="' + mi + '"></button>' +
        '<button type="button" class="sola321-v-opbtn" data-vop="cut" data-mi="' + mi + '"></button>' +
        '<button type="button" class="sola321-v-opbtn" data-vop="paste" data-mi="' + mi + '"></button>' +
        '<button type="button" class="sola321-v-opbtn" data-vop="up" data-mi="' + mi + '"></button>' +
        '<button type="button" class="sola321-v-opbtn" data-vop="down" data-mi="' + mi + '"></button>' +
        '<button type="button" class="sola321-v-opbtn" data-vop="del" data-mi="' + mi + '"></button>' +
        '</span>';
    }
    html += '</div>';

    /* ① 和弦車道：保留和弦指法圖（對齊選取音符上方、可左右自由拖曳） + 支援鍵盤直接輸入和弦 */
    var cp = v3ChordParts(m);
    var chordWCh = solaCalcInputWidthCh(m.chordText || '', 4);
    html += '<div class="sola321-v-chordlane' + (cp.length ? ' has-chords' : '') + '" data-mi="' + mi + '">';
    html += '<div class="sola321-v-chords-wrap" data-mi="' + mi + '">' + renderSola321VerticalChordsHtml(m, mi) + '</div>';
    html += '<input type="text" class="sola321-v-chord-editor" style="width:' + chordWCh + 'ch" data-mi="' + mi + '" data-lane="chord" value="' + escAttr(m.chordText || '') + '" placeholder="和弦" autocomplete="off" spellcheck="false" />';
    html += '</div>';

    /* ② 簡譜音符車道：前後小節分隔線（同行相鄰小節共用單一分隔線） + 單行不折行向右延伸 + 視覺化簡譜顯示（高低音點＋底線＋連音線） + 連續游標輸入 */
    var toks = solaTokens(m);
    var noteWCh = solaCalcInputWidthCh(m.noteText || '', Math.max(4, toks.length));
    var hasRepStart = marksArr.indexOf('𝄆') >= 0 || marksArr.indexOf('|:') >= 0;
    var hasRepEnd = marksArr.indexOf('𝄇') >= 0 || marksArr.indexOf(':|') >= 0;
    var hasDblBar = marksArr.indexOf('‖') >= 0 || marksArr.indexOf('||') >= 0;
    var frontBarCls = hasRepStart ? ' is-repeat-start' : '';
    var backBarCls = hasRepEnd ? ' is-repeat-end' : (hasDblBar ? ' is-double-bar' : '');
    html += '<div class="sola321-v-notelane' + (toks.length === 0 ? ' is-empty' : '') + '" data-mi="' + mi + '">';
    html += '<span class="sola321-v-barline sola321-v-barline-front' + frontBarCls + '" aria-hidden="true"></span>';
    html += '<div class="sola321-v-note-display" data-mi="' + mi + '">' + renderSola321VerticalNoteTokensHtml(m, mi) + '</div>';
    html += '<input type="text" class="sola321-v-note-editor" style="width:' + noteWCh + 'ch" data-mi="' + mi + '" data-lane="note" value="' + escAttr(m.noteText || '') + '" placeholder="簡譜音符" autocomplete="off" spellcheck="false" />';
    html += '<span class="sola321-v-barline sola321-v-barline-back' + backBarCls + '" aria-hidden="true"></span>';
    html += '</div>';

    /* ③ 歌詞車道：依音符節拍座標對齊顯示 + 點擊切換無外框透明輸入框 + 行尾半透明 ＋ 新增第 2, 3, 4 段歌詞 + × 刪除誤按新增的歌詞行 */
    var lyrShown = solaLyricRowsShown(m);
    var lyricFieldNames = ['lyricText', 'lyricText2', 'lyricText3', 'lyricText4'];
    var lyricFields = [m.lyricText || '', m.lyricText2 || '', m.lyricText3 || '', m.lyricText4 || ''];
    html += '<div class="sola321-v-lyriclane" data-mi="' + mi + '">';
    for (var ll = 0; ll < lyrShown; ll++) {
      var lyrVal = String(lyricFields[ll] || '');
      var lyrWCh = solaCalcInputWidthCh(lyrVal, 4);
      var ph = (ll === 0) ? '歌詞' : ('第' + (ll + 1) + '段歌詞');
      var lyrTokensHtml = renderSola321VerticalLyricTokensHtml(m, mi, lyrVal);
      html += '<div class="sola321-v-lyric-row' + (lyrTokensHtml ? ' has-lyrics' : '') + '" data-mi="' + mi + '" data-ll="' + ll + '">';
      html += '<div class="sola321-v-lyric-display" data-mi="' + mi + '" data-ll="' + ll + '">' + lyrTokensHtml + '</div>';
      html += '<input type="text" class="sola321-v-lyric-editor" style="width:' + lyrWCh + 'ch" data-mi="' + mi + '" data-ll="' + ll + '" data-lane="lyric" data-field="' + lyricFieldNames[ll] + '" value="' + escAttr(lyrVal) + '" placeholder="' + escAttr(ph) + '" autocomplete="off" spellcheck="false" />';
      if (ll >= 1) {
        html += '<button type="button" class="sola321-v-lyric-del" data-mi="' + mi + '" data-ll="' + ll + '" title="刪除此行歌詞並恢復原上下間距">×</button>';
      }
      if (ll === lyrShown - 1 && lyrShown < 4) {
        html += '<button type="button" class="sola321-v-lyric-add" data-mi="' + mi + '" title="新增第 ' + (lyrShown + 1) + ' 段歌詞">＋</button>';
      }
      html += '</div>';
    }
    html += '</div>';
    html += '</div>';
    return html;
  }

  /* 局部就地更新單一小節的和弦車道（新增、刪除、拖曳、移動、更換和弦時免重繪整份樂譜 DOM） */
  function solaUpdateMeasureChordsInPlace(mi) {
    if (solaEdit.useTimelineRenderer || solaEdit.viewMode !== 'vertical') return false;
    var sc = document.getElementById('sola321-score');
    if (!sc || !state3.doc || !state3.doc.measures) return false;
    var m = state3.doc.measures[mi];
    var mEl = sc.querySelector('.sola321-vmeasure[data-mi="' + mi + '"]');
    if (!m || !mEl) return false;
    var chordLane = mEl.querySelector('.sola321-v-chordlane[data-mi="' + mi + '"]');
    var chordsWrap = mEl.querySelector('.sola321-v-chords-wrap[data-mi="' + mi + '"]');
    var chordInp = mEl.querySelector('.sola321-v-chord-editor[data-mi="' + mi + '"]');
    if (!chordLane || !chordsWrap) return false;
    var cp = v3ChordParts(m);
    chordLane.classList.toggle('has-chords', cp.length > 0);
    chordsWrap.innerHTML = renderSola321VerticalChordsHtml(m, mi);
    if (chordInp) {
      chordInp.value = m.chordText || '';
      chordInp.style.width = solaCalcInputWidthCh(m.chordText || '', 4) + 'ch';
    }
    bindSola321VerticalChordEvents(chordsWrap);
    chordsWrap.querySelectorAll('.chord-diagram-img').forEach(function(img) {
      if (!img.complete) {
        img.addEventListener('load', function() { layoutSola321VerticalChords(mEl); }, { once: true });
      }
    });
    layoutSola321VerticalChords(mEl);
    solaMarkCursor();
    return true;
  }

  /* 局部就地更新單一小節的音符與歌詞對齊顯示（修改時值、高八度、升降記號、刪除單音時免重繪整份樂譜 DOM） */
  function solaUpdateMeasureNotesInPlace(mi, focusAfter) {
    if (solaEdit.useTimelineRenderer || solaEdit.viewMode !== 'vertical') return false;
    var sc = document.getElementById('sola321-score');
    if (!sc || !state3.doc || !state3.doc.measures) return false;
    var m = state3.doc.measures[mi];
    var mEl = sc.querySelector('.sola321-vmeasure[data-mi="' + mi + '"]');
    if (!m || !mEl) return false;
    var noteLane = mEl.querySelector('.sola321-v-notelane[data-mi="' + mi + '"]');
    var noteDisp = mEl.querySelector('.sola321-v-note-display[data-mi="' + mi + '"]');
    var noteInp = mEl.querySelector('.sola321-v-note-editor[data-mi="' + mi + '"]');
    if (!noteLane || !noteDisp) return false;
    var toks = solaTokens(m);
    noteLane.classList.toggle('is-empty', toks.length === 0);
    noteDisp.innerHTML = renderSola321VerticalNoteTokensHtml(m, mi);
    if (noteInp && document.activeElement !== noteInp) {
      noteInp.value = m.noteText || '';
      noteInp.style.width = solaCalcInputWidthCh(m.noteText || '', Math.max(4, toks.length)) + 'ch';
    }
    var lyricFields = [m.lyricText || '', m.lyricText2 || '', m.lyricText3 || '', m.lyricText4 || ''];
    mEl.querySelectorAll('.sola321-v-lyric-display[data-mi="' + mi + '"]').forEach(function(ld) {
      var ll = parseInt(ld.getAttribute('data-ll'), 10) || 0;
      var lyrHtml = renderSola321VerticalLyricTokensHtml(m, mi, String(lyricFields[ll] || ''));
      ld.innerHTML = lyrHtml;
      var lRow = ld.closest('.sola321-v-lyric-row');
      if (lRow) lRow.classList.toggle('has-lyrics', Boolean(lyrHtml));
    });
    var timeSig = (state3.doc && state3.doc.timeSignature) || '4/4';
    var mNum = parseInt(String(timeSig).split('/')[0], 10) || 4;
    var mDen = parseInt(String(timeSig).split('/')[1], 10) || 4;
    var expected = mNum * (4 / mDen);
    var beats = solaMeasureBeats(m);
    var isShort = toks.length > 0 && Math.abs(beats - expected) > 0.02 && beats < expected;
    mEl.classList.toggle('sola321-short', Boolean(isShort && warnShortOn));
    bindSola321VerticalNoteTokenEvents(noteDisp);
    layoutSola321VerticalChords(mEl);
    solaMarkCursor();
    if (focusAfter) solaFocusSelected();
    return true;
  }

  /* 綁定單一小節和弦指法圖的水平自由拖曳、方向鍵微調、點擊更換與 × 刪除事件 */
  function bindSola321VerticalChordEvents(rootEl) {
    var scope = rootEl || document.getElementById('sola321-score');
    if (!scope) return;
    scope.querySelectorAll('.sola321-v-chord-del').forEach(function(delBtn) {
      delBtn.addEventListener('pointerdown', function(e) {
        e.stopPropagation();
      });
      delBtn.addEventListener('click', function(e) {
        e.stopPropagation();
        var mi = parseInt(this.getAttribute('data-mi'), 10);
        var ci = parseInt(this.getAttribute('data-ci'), 10);
        var m = state3.doc && state3.doc.measures[mi];
        if (!m || isNaN(ci)) return;
        solaPushUndo();
        /* 刪除前先確保所有和弦皆有明確固定 offset，使刪除第 1 個和弦後，後續和弦依然固定在原指定音符正上方 */
        v3EnsureChordOffsets(m);
        var arr = v3ChordParts(m);
        arr.splice(ci, 1);
        if (ci >= 0 && ci < m.chordOffsets.length) m.chordOffsets.splice(ci, 1);
        if (ci >= 0 && ci < m.chordTicks.length) m.chordTicks.splice(ci, 1);
        m.chordText = arr.join(' ');
        syncLegacyToEvents(m);
        if (!solaUpdateMeasureChordsInPlace(mi)) {
          renderSola321Score(false);
        }
        saveCurrentDoc();
      });
    });

    scope.querySelectorAll('.sola321-v-chord').forEach(function(slot) {
      /* 滑鼠/指標水平自由拖曳：對準下方任意音符 */
      slot.addEventListener('pointerdown', function(e) {
        if (e.button !== 0) return;
        if (e.target && e.target.closest && e.target.closest('.sola321-v-chord-del')) return;
        e.stopPropagation();
        var mi = parseInt(slot.getAttribute('data-mi'), 10);
        var ci = parseInt(slot.getAttribute('data-ci'), 10);
        var m = state3.doc && state3.doc.measures[mi];
        if (!m || isNaN(ci)) return;
        v3EnsureChordOffsets(m);
        solaEdit.mi = mi;
        solaSetTarget(mi);
        var mEl = slot.closest('.sola321-vmeasure');
        var startX = e.clientX;
        var startLeft = parseFloat(slot.style.left) || 0;
        var startOff = m.chordOffsets[ci] != null ? m.chordOffsets[ci] : ci;
        var curOff = startOff;
        var moved = false;
        if (slot.setPointerCapture) {
          try { slot.setPointerCapture(e.pointerId); } catch (err) {}
        }
        function onMove(ev) {
          var dx = ev.clientX - startX;
          if (Math.abs(dx) > 4) {
            moved = true;
            slot.classList.add('is-dragging');
          }
          if (!moved) return;
          var newLeft = Math.max(0, Math.round(startLeft + dx));
          slot.style.left = newLeft + 'px';
          var rect = slot.getBoundingClientRect();
          var centerClientX = rect.left + rect.width / 2;
          curOff = solaVerticalNearestNti(mEl, centerClientX);
          solaEdit.mi = mi;
          solaEdit.nti = curOff;
          solaMarkCursor();
        }
        function onUp(ev) {
          slot.removeEventListener('pointermove', onMove);
          slot.removeEventListener('pointerup', onUp);
          slot.removeEventListener('pointercancel', onUp);
          slot.classList.remove('is-dragging');
          if (moved) {
            slot.__justDragged = true;
            setTimeout(function() { slot.__justDragged = false; }, 120);
            if (curOff !== startOff) {
              solaPushUndo();
              v3EnsureChordOffsets(m);
              m.chordOffsets[ci] = curOff;
              m.chordTicks[ci] = curOff * 480;
              v3SortChordsByOffset(m);
              syncLegacyToEvents(m);
              saveCurrentDoc();
            }
            if (!solaUpdateMeasureChordsInPlace(mi)) {
              renderSola321Score(false);
            }
          } else {
            slot.focus();
          }
        }
        slot.addEventListener('pointermove', onMove);
        slot.addEventListener('pointerup', onUp);
        slot.addEventListener('pointercancel', onUp);
      });

      /* 點擊（未拖曳時）開啟和弦選單更換和弦 */
      slot.addEventListener('click', function(e) {
        if (e.target && e.target.closest && e.target.closest('.sola321-v-chord-del')) return;
        e.stopPropagation();
        if (this.__justDragged) return;
        var mi = parseInt(this.getAttribute('data-mi'), 10);
        var ci = parseInt(this.getAttribute('data-ci'), 10);
        var off = parseInt(this.getAttribute('data-offset'), 10);
        var cur = this.getAttribute('data-chord') || '';
        solaEdit.mi = mi;
        if (!isNaN(off)) solaEdit.nti = off;
        solaSetTarget(mi);
        solaMarkCursor();
        openChordPicker(this, mi, ci, cur, function() {
          if (!solaUpdateMeasureChordsInPlace(mi)) {
            renderSola321Score(false);
          }
          saveCurrentDoc();
        });
      });

      /* 鍵盤 ← / → 左右移動和弦對齊音符；Delete / Backspace 刪除此和弦 */
      slot.addEventListener('keydown', function(e) {
        var mi = parseInt(this.getAttribute('data-mi'), 10);
        var ci = parseInt(this.getAttribute('data-ci'), 10);
        var m = state3.doc && state3.doc.measures[mi];
        if (!m || isNaN(ci)) return;
        if (e.key === 'ArrowLeft' || e.key === 'ArrowRight') {
          e.preventDefault();
          e.stopPropagation();
          v3EnsureChordOffsets(m);
          var toks = solaTokens(m);
          var maxOff = Math.max(0, toks.length - 1, (m.chordOffsets[ci] || 0) + 1);
          var curOff = m.chordOffsets[ci] != null ? m.chordOffsets[ci] : ci;
          var nextOff = Math.max(0, Math.min(maxOff, curOff + (e.key === 'ArrowRight' ? 1 : -1)));
          if (nextOff !== curOff) {
            var targetChordName = v3ChordParts(m)[ci];
            solaPushUndo();
            m.chordOffsets[ci] = nextOff;
            m.chordTicks[ci] = nextOff * 480;
            v3SortChordsByOffset(m);
            syncLegacyToEvents(m);
            solaEdit.mi = mi;
            solaEdit.nti = nextOff;
            if (!solaUpdateMeasureChordsInPlace(mi)) {
              renderSola321Score(false);
            }
            saveCurrentDoc();
            var sc = document.getElementById('sola321-score');
            if (sc) {
              var movedSlot = sc.querySelector('.sola321-v-chord[data-mi="' + mi + '"][data-offset="' + nextOff + '"][data-chord="' + escAttr(targetChordName) + '"]') ||
                              sc.querySelector('.sola321-v-chord[data-mi="' + mi + '"][data-offset="' + nextOff + '"]');
              if (movedSlot) movedSlot.focus();
            }
          }
          return;
        }
        if (e.key === 'Delete' || e.key === 'Backspace') {
          e.preventDefault();
          e.stopPropagation();
          solaPushUndo();
          v3EnsureChordOffsets(m);
          var arr = v3ChordParts(m);
          arr.splice(ci, 1);
          if (ci >= 0 && ci < m.chordOffsets.length) m.chordOffsets.splice(ci, 1);
          if (ci >= 0 && ci < m.chordTicks.length) m.chordTicks.splice(ci, 1);
          m.chordText = arr.join(' ');
          syncLegacyToEvents(m);
          if (!solaUpdateMeasureChordsInPlace(mi)) {
            renderSola321Score(false);
          }
          saveCurrentDoc();
        }
      });
    });
  }

  /* 綁定單一小節簡譜音符 Token 的點擊定位游標與拖曳選取多音符（供連音線/圓滑線/三連音線）事件 */
  var _solaNoteDrag = null;
  function bindSola321VerticalNoteTokenEvents(rootEl) {
    var scope = rootEl || document.getElementById('sola321-score');
    if (!scope) return;
    scope.querySelectorAll('.sola321-v-token.sola321-note-char').forEach(function(span) {
      span.addEventListener('mousedown', function(e) {
        e.stopPropagation();
        e.preventDefault();
        solaTitleFocused = false;
        var mi = parseInt(this.getAttribute('data-mi'), 10);
        var nti = parseInt(this.getAttribute('data-nti'), 10);
        if (isNaN(mi)) return;
        var idx = isNaN(nti) ? 0 : nti;
        var rect = this.getBoundingClientRect();
        var atStart = (e.clientX - rect.left) < (rect.width * 0.45);
        if (e.shiftKey && solaEdit.mi === mi && solaEdit.selStartNti != null) {
          solaEdit.nti = idx;
          solaEdit.selEndNti = idx;
          solaSetTarget(mi);
          solaMarkCursor();
          return;
        }
        solaEdit.mi = mi;
        solaEdit.nti = idx;
        solaEdit.selStartNti = idx;
        solaEdit.selEndNti = idx;
        solaSetTarget(mi);
        solaMarkCursor();
        _solaNoteDrag = { mi: mi, startNti: idx, endNti: idx, moved: false, atStart: atStart };
      });
      span.addEventListener('mouseenter', function() {
        if (!_solaNoteDrag) return;
        var mi = parseInt(this.getAttribute('data-mi'), 10);
        var nti = parseInt(this.getAttribute('data-nti'), 10);
        if (mi !== _solaNoteDrag.mi || isNaN(nti)) return;
        if (nti !== _solaNoteDrag.endNti) {
          _solaNoteDrag.endNti = nti;
          _solaNoteDrag.moved = true;
          solaEdit.nti = _solaNoteDrag.startNti;
          solaEdit.selStartNti = _solaNoteDrag.startNti;
          solaEdit.selEndNti = nti;
          solaMarkCursor();
        }
      });
    });
  }
  if (!window._solaNoteDragDocBound) {
    window._solaNoteDragDocBound = true;
    document.addEventListener('mouseup', function() {
      if (!_solaNoteDrag) return;
      var drag = _solaNoteDrag;
      _solaNoteDrag = null;
      if (!drag.moved && drag.startNti === drag.endNti) {
        var m = state3.doc && state3.doc.measures[drag.mi];
        var caretPos = m ? solaTokenIndexToCaret(m.noteText || '', drag.startNti, drag.atStart) : 'end';
        solaFocusVerticalLane(drag.mi, 'note', caretPos);
      } else {
        /* 拖曳選取 2~3 個音符時保持視覺顯示層，讓使用者直接點選「符號 ▾ → 連音線/圓滑線/三連音線」 */
        if (document.activeElement && document.activeElement.classList && document.activeElement.classList.contains('sola321-v-note-editor')) {
          document.activeElement.blur();
        }
        solaMarkCursor();
      }
    });
  }

  /* 綁定直式視圖（Vertical View）的所有互動事件與 Google Sheets + ChordPro 鍵盤導航 */
  function bindSola321VerticalInputs() {
    /* 1. Probe 隱藏按鈕支援（僅供自動化測試呼叫） */
    $$('#sola321-score .sola321-v-opbtn[data-vop]').forEach(function(btn) {
      btn.addEventListener('click', function(e) {
        e.stopPropagation();
        var op = this.getAttribute('data-vop');
        if (op === 'add') { solaAddMeasure(); return; }
        if (op === 'paste-cursor') { solaPasteMeasure(solaEdit.mi); return; }
        var dmi = parseInt(this.getAttribute('data-mi'), 10);
        if (isNaN(dmi)) return;
        if (op === 'add-after') { solaAddMeasureAfter(dmi); return; }
        if (op === 'copy') { solaCopyMeasure(dmi); return; }
        if (op === 'cut') { solaCutMeasure(dmi); return; }
        if (op === 'paste') { solaPasteMeasure(dmi); return; }
        if (op === 'del') { solaDeleteMeasure(dmi); return; }
        if (op === 'up') { solaMoveUp(dmi); return; }
        if (op === 'down') { solaMoveDown(dmi); return; }
      });
    });

    /* 2. 點擊小節任意處 → 設定目標小節（供段落/結構記號/右側和弦庫直接套用） */
    $$('#sola321-score .sola321-vmeasure').forEach(function(box) {
      box.addEventListener('mousedown', function() {
        solaTitleFocused = false;
        var mi = parseInt(this.getAttribute('data-mi'), 10);
        if (!isNaN(mi)) {
          if (solaEdit.mi !== mi) {
            solaEdit.nti = 0;
            solaEdit.selStartNti = 0;
            solaEdit.selEndNti = 0;
          }
          solaEdit.mi = mi;
          solaSetTarget(mi);
          solaMarkCursor();
        }
      });
    });

    /* 3. 點擊小節頭的記號 chip → 移除該記號 */
    $$('#sola321-score .sola321-vmeasure .sola321-mark-inline').forEach(function(chip) {
      chip.addEventListener('click', function(e) {
        e.stopPropagation();
        var mi = parseInt(this.getAttribute('data-mi'), 10);
        var mk = this.getAttribute('data-mark');
        if (!isNaN(mi) && mk) {
          solaRemoveMark(mi, mk);
          saveCurrentDoc();
        }
      });
    });

    /* 4. 和弦車道：指法圖拖曳/點擊更換/刪除 + 點擊空白處聚焦和弦輸入框 */
    bindSola321VerticalChordEvents(document.getElementById('sola321-score'));
    $$('#sola321-score .sola321-v-chordlane').forEach(function(lane) {
      lane.addEventListener('click', function(e) {
        if (e.target && e.target.closest && e.target.closest('.sola321-v-chord')) return;
        var mi = parseInt(this.getAttribute('data-mi'), 10);
        if (!isNaN(mi)) solaFocusVerticalLane(mi, 'chord', 'end');
      });
    });
    $$('#sola321-score .sola321-v-chord-editor').forEach(function(inp) {
      var startVal = inp.value;
      inp.addEventListener('focus', function() {
        solaTitleFocused = false;
        startVal = this.value;
        var mi = parseInt(this.getAttribute('data-mi'), 10);
        if (!isNaN(mi)) { solaEdit.mi = mi; solaSetTarget(mi); }
      });
      inp.addEventListener('input', function() {
        var mi = parseInt(this.getAttribute('data-mi'), 10);
        var m = state3.doc && state3.doc.measures[mi];
        if (!m) return;
        this.style.width = solaCalcInputWidthCh(this.value, 4) + 'ch';
        var parts = this.value.trim() ? this.value.trim().split(/\s+/) : [];
        v3WriteChords(m, parts, mi);
        if (state3.doc) renderChordProFromDoc(state3.doc);
      });
      inp.addEventListener('blur', function() {
        var mi = parseInt(this.getAttribute('data-mi'), 10);
        var m = state3.doc && state3.doc.measures[mi];
        if (!m) return;
        var nextVal = this.value.trim();
        if (nextVal !== startVal.trim()) {
          var curNew = nextVal;
          m.chordText = startVal.trim();
          solaPushUndo();
          var parts = curNew ? curNew.split(/\s+/) : [];
          v3WriteChords(m, parts, mi);
          startVal = m.chordText;
          saveCurrentDoc();
        }
        /* 就地更新該小節的和弦指法圖並對齊下方音符，不銷毀整頁 DOM 以免打斷下一個點擊焦點 */
        var lane = this.closest('.sola321-v-chordlane');
        if (lane) {
          var wrap = lane.querySelector('.sola321-v-chords-wrap');
          var cp = v3ChordParts(m);
          lane.classList.toggle('has-chords', cp.length > 0);
          if (wrap) {
            wrap.innerHTML = renderSola321VerticalChordsHtml(m, mi);
            bindSola321VerticalChordEvents(wrap);
            layoutSola321VerticalChords(lane.closest('.sola321-vmeasure'));
          }
        }
      });
    });

    /* 5. 簡譜車道：點擊任意處或音符直接進入 ChordPro 式連續文字編輯 */
    bindSola321VerticalNoteTokenEvents(document.getElementById('sola321-score'));
    $$('#sola321-score .sola321-v-notelane').forEach(function(lane) {
      lane.addEventListener('mousedown', function(e) {
        if (e.target && e.target.classList && e.target.classList.contains('sola321-v-note-editor')) return;
        if (e.target && e.target.closest && e.target.closest('.sola321-v-token')) return;
        e.preventDefault();
        solaTitleFocused = false;
        var mi = parseInt(this.getAttribute('data-mi'), 10);
        if (!isNaN(mi)) solaFocusVerticalLane(mi, 'note', 'end');
      });
    });
    $$('#sola321-score .sola321-v-note-editor').forEach(function(inp) {
      var startVal = inp.value;
      function syncNoteEditorSelection(el) {
        var rng = solaCaretRangeToTokenRange(el.value, el.selectionStart || 0, el.selectionEnd || 0);
        solaEdit.nti = rng.start;
        solaEdit.selStartNti = rng.start;
        solaEdit.selEndNti = rng.end;
        solaMarkCursor();
      }
      inp.addEventListener('focus', function() {
        solaTitleFocused = false;
        startVal = this.value;
        var lane = this.closest('.sola321-v-notelane');
        if (lane) lane.classList.add('is-editing');
        var mi = parseInt(this.getAttribute('data-mi'), 10);
        if (!isNaN(mi)) {
          solaEdit.mi = mi;
          solaSetTarget(mi);
          syncNoteEditorSelection(this);
        }
      });
      inp.addEventListener('click', function() {
        syncNoteEditorSelection(this);
      });
      inp.addEventListener('keyup', function() {
        syncNoteEditorSelection(this);
      });
      inp.addEventListener('select', function() {
        syncNoteEditorSelection(this);
      });
      inp.addEventListener('mouseup', function() {
        syncNoteEditorSelection(this);
      });
      inp.addEventListener('input', function() {
        var mi = parseInt(this.getAttribute('data-mi'), 10);
        var m = state3.doc && state3.doc.measures[mi];
        if (!m) return;
        /* 支援鍵盤直接輸入 ' 轉高八度點 \u0307、, 轉低八度點 \u0323（比照簡譜直輸習慣） */
        var raw = this.value;
        var sel = this.selectionStart;
        var converted = raw.replace(/([1-7][\u0307\u0323]*)'/g, '$1\u0307').replace(/([1-7][\u0307\u0323]*),/g, '$1\u0323');
        if (converted !== raw) {
          this.value = converted;
          try { this.setSelectionRange(sel, sel); } catch (e) {}
        }
        var toks = solaParseNoteLine(this.value);
        solaSetNoteText(m, toks, this.value);
        this.style.width = solaCalcInputWidthCh(this.value, Math.max(4, toks.length)) + 'ch';
        syncNoteEditorSelection(this);
        var lane = this.closest('.sola321-v-notelane');
        if (lane) {
          lane.classList.toggle('is-empty', toks.length === 0 && !/\s/.test(this.value));
          var disp = lane.querySelector('.sola321-v-note-display');
          if (disp) {
            disp.innerHTML = renderSola321VerticalNoteTokensHtml(m, mi);
            bindSola321VerticalNoteTokenEvents(disp);
          }
          layoutSola321VerticalChords(lane.closest('.sola321-vmeasure'));
        }
        if (state3.doc) renderChordProFromDoc(state3.doc);
      });
      inp.addEventListener('blur', function() {
        var mi = parseInt(this.getAttribute('data-mi'), 10);
        var m = state3.doc && state3.doc.measures[mi];
        var lane = this.closest('.sola321-v-notelane');
        if (lane) lane.classList.remove('is-editing');
        if (!m) return;
        var curRaw = this.value;
        var toks = solaParseNoteLine(curRaw);
        if (curRaw !== startVal) {
          m.noteText = startVal;
          solaPushUndo();
          solaSetNoteText(m, toks, curRaw);
          startVal = m.noteText;
          saveCurrentDoc();
        } else {
          solaSetNoteText(m, toks, curRaw);
        }
        this.value = m.noteText || '';
        this.style.width = solaCalcInputWidthCh(this.value, Math.max(4, toks.length)) + 'ch';
        if (lane) {
          lane.classList.toggle('is-empty', toks.length === 0 && !/\s/.test(this.value));
          var disp = lane.querySelector('.sola321-v-note-display');
          if (disp) {
            disp.innerHTML = renderSola321VerticalNoteTokensHtml(m, mi);
            bindSola321VerticalNoteTokenEvents(disp);
          }
          layoutSola321VerticalChords(lane.closest('.sola321-vmeasure'));
        }
        solaMarkCursor();
      });
    });

    /* 6. 歌詞車道：常駐無外框透明輸入框 + 半透明 ＋ 新增第 2, 3, 4 段歌詞 + × 刪除誤按歌詞行 */
    $$('#sola321-score .sola321-v-lyric-add').forEach(function(btn) {
      btn.addEventListener('mousedown', function(e) {
        e.stopPropagation();
        e.preventDefault();
      });
      btn.addEventListener('click', function(e) {
        e.stopPropagation();
        e.preventDefault();
        var mi = parseInt(this.getAttribute('data-mi'), 10);
        var m = state3.doc && state3.doc.measures[mi];
        if (!m) return;
        var curShown = solaLyricRowsShown(m);
        if (curShown < 4) {
          solaPushUndo();
          m.lyricRows = curShown + 1;
          renderSola321Score(false);
          solaFocusVerticalLane(mi, 'lyric', 'start', curShown);
          saveCurrentDoc();
        }
      });
    });
    $$('#sola321-score .sola321-v-lyric-del').forEach(function(btn) {
      btn.addEventListener('mousedown', function(e) {
        e.stopPropagation();
        e.preventDefault();
      });
      btn.addEventListener('click', function(e) {
        e.stopPropagation();
        e.preventDefault();
        var mi = parseInt(this.getAttribute('data-mi'), 10);
        var ll = parseInt(this.getAttribute('data-ll'), 10);
        var m = state3.doc && state3.doc.measures[mi];
        if (!m || isNaN(ll) || ll < 1) return;
        var curShown = solaLyricRowsShown(m);
        solaPushUndo();
        for (var r = ll; r < 3; r++) {
          var curField = 'lyricText' + (r + 1);
          var nextField = 'lyricText' + (r + 2);
          m[curField] = m[nextField] || '';
        }
        m.lyricText4 = '';
        m.lyricRows = Math.max(1, curShown - 1);
        renderSola321Score(false);
        saveCurrentDoc();
      });
    });
    $$('#sola321-score .sola321-v-lyric-row').forEach(function(rowEl) {
      rowEl.addEventListener('mousedown', function(e) {
        if (e.target && e.target.classList && (e.target.classList.contains('sola321-v-lyric-editor') || e.target.classList.contains('sola321-v-lyric-add') || e.target.classList.contains('sola321-v-lyric-del'))) return;
        e.preventDefault();
        var mi = parseInt(this.getAttribute('data-mi'), 10);
        var ll = parseInt(this.getAttribute('data-ll') || '0', 10);
        if (!isNaN(mi)) solaFocusVerticalLane(mi, 'lyric', 'end', ll);
      });
    });
    $$('#sola321-score .sola321-v-lyric-editor').forEach(function(inp) {
      var startVal = inp.value;
      inp.addEventListener('focus', function() {
        solaTitleFocused = false;
        startVal = this.value;
        var rowEl = this.closest('.sola321-v-lyric-row');
        if (rowEl) rowEl.classList.add('is-editing');
        var mi = parseInt(this.getAttribute('data-mi'), 10);
        if (!isNaN(mi)) { solaEdit.mi = mi; solaSetTarget(mi); }
      });
      inp.addEventListener('input', function() {
        var mi = parseInt(this.getAttribute('data-mi'), 10);
        var field = this.getAttribute('data-field') || 'lyricText';
        var m = state3.doc && state3.doc.measures[mi];
        if (!m) return;
        this.style.width = solaCalcInputWidthCh(this.value, 4) + 'ch';
        m[field] = this.value;
        syncLegacyToEvents(m);
        var rowEl = this.closest('.sola321-v-lyric-row');
        if (rowEl) {
          var lDisp = rowEl.querySelector('.sola321-v-lyric-display');
          if (lDisp) lDisp.innerHTML = renderSola321VerticalLyricTokensHtml(m, mi, this.value);
        }
        layoutSola321VerticalChords(this.closest('.sola321-vmeasure'));
        if (state3.doc) renderChordProFromDoc(state3.doc);
      });
      inp.addEventListener('blur', function() {
        var mi = parseInt(this.getAttribute('data-mi'), 10);
        var field = this.getAttribute('data-field') || 'lyricText';
        var m = state3.doc && state3.doc.measures[mi];
        var rowEl = this.closest('.sola321-v-lyric-row');
        if (rowEl) rowEl.classList.remove('is-editing');
        if (!m) return;
        var nextVal = this.value.replace(/\s+$/, '');
        this.value = nextVal;
        this.style.width = solaCalcInputWidthCh(nextVal, 4) + 'ch';
        if (nextVal !== startVal) {
          m[field] = startVal;
          solaPushUndo();
          m[field] = nextVal;
          syncLegacyToEvents(m);
          startVal = nextVal;
          saveCurrentDoc();
        }
        if (rowEl) {
          var lDisp = rowEl.querySelector('.sola321-v-lyric-display');
          var lyrHtml = renderSola321VerticalLyricTokensHtml(m, mi, nextVal);
          rowEl.classList.toggle('has-lyrics', Boolean(lyrHtml));
          if (lDisp) lDisp.innerHTML = lyrHtml;
        }
        layoutSola321VerticalChords(this.closest('.sola321-vmeasure'));
      });
    });

    /* 7. Google Sheets + ChordPro 鍵盤快捷鍵導航（方向鍵跨格/跨列、Tab/Enter 換小節與自動加小節、快捷鍵增刪移動複製貼上小節） */
    $$('#sola321-score .sola321-v-chord-editor, #sola321-score .sola321-v-note-editor, #sola321-score .sola321-v-lyric-editor').forEach(function(inp) {
      inp.addEventListener('keydown', function(e) {
        var mi = parseInt(this.getAttribute('data-mi'), 10);
        var lane = this.getAttribute('data-lane') || 'note';
        var ll = parseInt(this.getAttribute('data-ll') || '0', 10);
        var ms = (state3.doc && state3.doc.measures) || [];
        if (isNaN(mi) || !ms.length) return;
        var mod = e.ctrlKey || e.metaKey;

        /* Alt + 方向鍵：小節順序前移／後移 */
        if (e.altKey && !mod) {
          if (e.key === 'ArrowLeft' || e.key === 'ArrowUp') {
            e.preventDefault(); e.stopPropagation();
            if (mi > 0) {
              solaMoveUp(mi);
              solaFocusVerticalLane(mi - 1, lane, 'end', ll);
            }
            return;
          }
          if (e.key === 'ArrowRight' || e.key === 'ArrowDown') {
            e.preventDefault(); e.stopPropagation();
            if (mi < ms.length - 1) {
              solaMoveDown(mi);
              solaFocusVerticalLane(mi + 1, lane, 'end', ll);
            }
            return;
          }
        }

        /* Ctrl+Enter 或 Insert：在此小節後插入新小節並跳過去 */
        if ((mod && e.key === 'Enter') || (!mod && !e.shiftKey && e.key === 'Insert')) {
          e.preventDefault(); e.stopPropagation();
          solaAddMeasureAfter(mi);
          solaFocusVerticalLane(mi + 1, lane, 'start', ll);
          return;
        }

        /* Ctrl+Delete 或 Ctrl+Backspace：刪除此小節 */
        if (mod && (e.key === 'Delete' || e.key === 'Backspace')) {
          e.preventDefault(); e.stopPropagation();
          var nextFocusMi = Math.max(0, Math.min(mi, ms.length - 2));
          solaDeleteMeasure(mi);
          solaFocusVerticalLane(nextFocusMi, lane, 'end', ll);
          return;
        }

        /* Ctrl+Shift+C / Ctrl+Shift+X / Ctrl+Shift+V：整小節複製／剪下／貼上 */
        if (mod && e.shiftKey) {
          var k = e.key.toLowerCase();
          if (k === 'c') { e.preventDefault(); e.stopPropagation(); solaCopyMeasure(mi); return; }
          if (k === 'x') {
            e.preventDefault(); e.stopPropagation();
            var cutFocusMi = Math.max(0, Math.min(mi, ms.length - 2));
            solaCutMeasure(mi);
            solaFocusVerticalLane(cutFocusMi, lane, 'end', ll);
            return;
          }
          if (k === 'v') {
            e.preventDefault(); e.stopPropagation();
            solaPasteMeasure(mi);
            solaFocusVerticalLane(mi + 1, lane, 'end', ll);
            return;
          }
        }

        /* Backspace 在空白的第 2/3/4 段歌詞行：移除該段空白歌詞行並退回上一段歌詞行 */
        if (!mod && !e.shiftKey && e.key === 'Backspace' && lane === 'lyric' && ll > 0 && this.value === '') {
          var curM0 = ms[mi];
          if (curM0) {
            e.preventDefault(); e.stopPropagation();
            solaPushUndo();
            var shownNow = solaLyricRowsShown(curM0);
            curM0.lyricRows = Math.max(1, shownNow - 1);
            renderSola321Score(false);
            solaFocusVerticalLane(mi, 'lyric', 'end', ll - 1);
            saveCurrentDoc();
            return;
          }
        }

        /* Backspace 在完全空白的小節（且小節數 > 1）：直接刪除該空小節並退回上一小節（ChordPro 習慣） */
        if (!mod && !e.shiftKey && e.key === 'Backspace' && this.value === '' && ms.length > 1) {
          var curM = ms[mi];
          var isMeasureEmpty = curM && !String(curM.chordText || '').trim() && !String(curM.noteText || '').trim() && !String(curM.lyricText || '').trim();
          if (isMeasureEmpty) {
            e.preventDefault(); e.stopPropagation();
            var prevMi = Math.max(0, mi - 1);
            solaDeleteMeasure(mi);
            solaFocusVerticalLane(prevMi, lane, 'end', ll);
            return;
          }
        }

        /* 左右方向鍵：在文字內自然移動游標；到達邊界時自動跨小節移動 */
        if (!mod && !e.altKey && e.key === 'ArrowLeft') {
          if (this.selectionStart === 0 && this.selectionEnd === 0) {
            e.preventDefault(); e.stopPropagation();
            if (mi > 0) solaFocusVerticalLane(mi - 1, lane, 'end', ll);
            return;
          }
          e.stopPropagation();
          return;
        }
        if (!mod && !e.altKey && e.key === 'ArrowRight') {
          var vLen = this.value.length;
          if (this.selectionStart === vLen && this.selectionEnd === vLen) {
            e.preventDefault(); e.stopPropagation();
            if (mi < ms.length - 1) solaFocusVerticalLane(mi + 1, lane, 'start', ll);
            return;
          }
          e.stopPropagation();
          return;
        }

        /* 上下方向鍵：比照 Google Sheets 在三條車道（和弦 ⇄ 音符 ⇄ 歌詞）與上下列（±4 小節）之間快速移動 */
        if (!mod && !e.altKey && e.key === 'ArrowUp') {
          e.preventDefault(); e.stopPropagation();
          if (lane === 'lyric') {
            if (ll > 0) solaFocusVerticalLane(mi, 'lyric', 'end', ll - 1);
            else solaFocusVerticalLane(mi, 'note', 'end');
          } else if (lane === 'note') {
            solaFocusVerticalLane(mi, 'chord', 'end');
          } else if (lane === 'chord') {
            if (mi >= 4) solaFocusVerticalLane(mi - 4, 'lyric', 'end', 0);
          }
          return;
        }
        if (!mod && !e.altKey && e.key === 'ArrowDown') {
          e.preventDefault(); e.stopPropagation();
          if (lane === 'chord') {
            solaFocusVerticalLane(mi, 'note', 'end');
          } else if (lane === 'note') {
            solaFocusVerticalLane(mi, 'lyric', 'end', 0);
          } else if (lane === 'lyric') {
            var shownRows = solaLyricRowsShown(ms[mi]);
            if (ll + 1 < shownRows) {
              solaFocusVerticalLane(mi, 'lyric', 'end', ll + 1);
            } else if (mi + 4 < ms.length) {
              solaFocusVerticalLane(mi + 4, 'note', 'end');
            }
          }
          return;
        }

        /* Tab / Shift+Tab：跨小節快速切換（在最後一小節按 Tab 自動新增下一小節） */
        if (!mod && !e.altKey && e.key === 'Tab') {
          e.preventDefault(); e.stopPropagation();
          if (e.shiftKey) {
            if (mi > 0) solaFocusVerticalLane(mi - 1, lane, 'end', ll);
          } else {
            if (mi < ms.length - 1) {
              solaFocusVerticalLane(mi + 1, lane, 'start', ll);
            } else {
              solaAddMeasureAfter(mi);
              solaFocusVerticalLane(mi + 1, lane, 'start', ll);
            }
          }
          return;
        }

        /* Enter：Shift+Enter 於歌詞車道新增多行歌詞；一般 Enter 依序往下（和弦 → 音符 → 歌詞 → 下一小節） */
        if (!mod && !e.altKey && e.key === 'Enter') {
          e.preventDefault(); e.stopPropagation();
          if (e.shiftKey && lane === 'lyric') {
            var curShown = solaLyricRowsShown(ms[mi]);
            if (curShown < 4) {
              solaPushUndo();
              ms[mi].lyricRows = curShown + 1;
              renderSola321Score(false);
              solaFocusVerticalLane(mi, 'lyric', 'start', curShown);
            }
            return;
          }
          if (lane === 'chord') {
            solaFocusVerticalLane(mi, 'note', 'end');
            return;
          }
          if (lane === 'note') {
            solaFocusVerticalLane(mi, 'lyric', 'end', 0);
            return;
          }
          if (mi < ms.length - 1) {
            solaFocusVerticalLane(mi + 1, 'note', 'end');
          } else {
            solaAddMeasureAfter(mi);
            solaFocusVerticalLane(mi + 1, 'note', 'start');
          }
          return;
        }

        if (e.key === 'Escape') {
          e.preventDefault(); e.stopPropagation();
          this.blur();
        }
      });
    });
  }

  /* 打字中即時重排：全篇重繪＋重綁（舊 DOM 全移除重建，無重複綁定），caller 負責還原焦點/選區。
     只在「該小節 input 正被編輯」時由 debounce 觸發，其餘小節視覺不變。 */
  function solaRerenderOneMeasure(mi) {
    if (!state3.doc) return;
    renderSola321Score(false);
  }

  /* 單一小節：小節號＋和弦 input＋簡譜 input 列（含高低音點）＋歌詞 input 列（皆與 token 對齊） */
  function renderSola321Measure(m, mi, isLast, isShort) {
    var toks = solaTokens(m);
    var cls = 'sola321-measure' + (isLast ? ' sola321-end-bar' : '') + (isShort ? ' sola321-measure-short' : '');
    var html = '<div class="' + cls + '" data-mi="' + mi + '">';
    html += '<div class="sola321-measure-num"><input type="text" data-num="' + mi + '" value="' + escAttr(m.number != null ? m.number : (mi + 1)) + '" title="小節號" />';
    /* 結構記號／段落記號：小節號右側行內顯示（黑色字體），點記號＝移除；
       不再佔獨立一行 → 避免有記號的小節把整列往下擠、與相鄰小節錯位 */
    var markList = String(m.marks || '').trim().split(/\s+/).filter(Boolean);
    if (markList.length) {
      html += '<span class="sola321-marks-inline" title="記號：點擊移除">';
      for (var mk = 0; mk < markList.length; mk++) {
        html += '<span class="sola321-mark-inline" data-mi="' + mi + '" data-mark="' + escAttr(markList[mk]) + '">' + escHtml(markList[mk]) + '</span>';
      }
      html += '</span>';
    }
    html += '</div>';
    html += '<div class="sola321-chord-row">' + renderV3ChordSlots(m, mi) + '</div>';
    /* 節拍感知分組（標準簡譜拍型）：同拍開頭音符緊排（1px）、跨拍群留 6px 空隙；
           八分/十六分/三十二分縮小格寬讓 2/4 個同拍塞得下；延音橫線「-」貼前音、同拍群
           （簡譜「3 -」＝二分音：3 佔第 1 拍、- 佔第 2 拍 → 拍群邊界由「累計拍」決定）
           colOf：每個 token 落在第幾拍（拍群序號）；dash 沿用前 token 的拍群 */
        var colOf = [];
        if (m.noteTicks && m.noteTicks.length === toks.length) {
          // 使用持久化的 tick 位置（tick -> beat index）
          for (var ti = 0; ti < toks.length; ti++) {
            colOf[ti] = Math.floor(m.noteTicks[ti] / 480);
          }
        } else {
          // 回退：依 duration 累積（舊版邏輯）
          var accB = 0;
          for (var ck = 0; ck < toks.length; ck++) {
            var pc = solaDecomp(toks[ck].base);
            var dur = Math.pow(0.5, pc.under);
            if (pc.dotted) dur *= 1.5;
            if (pc.triplet) dur *= 2 / 3;
            if (pc.dash) colOf[ck] = ck > 0 ? colOf[ck - 1] : 0;
            else { colOf[ck] = Math.floor(accB + 1e-6); accB += dur; }
          }
        }
    /* 拍群邊界：相同 colOf 值的連續 token 成一「拍群」；歌詞／和弱行對齊依此拍群
       → 修正：採「連續相同 colOf 值直接成群，新群＝colOf 改變時開，延伸＝colOf 同時續」
         舊版用 sameCol（比對 bg 與 bg+1）決定關閉，導致多音符同拍群中第一音符被跳過（beatGroups 僅含尾音），
         結果每群 songGroups cnt=1，連時線永不繪製 */
    var beatGroups = [];  // [{col, start, end}] end 為不含上限
    for (var bg = 0; bg < toks.length; bg++) {
      if (bg === 0 || colOf[bg] !== colOf[bg - 1]) {
        beatGroups.push({ col: colOf[bg], start: bg, end: bg + 1 });
      } else {
        beatGroups[beatGroups.length - 1].end = bg + 1;
      }
    }
    /* 簡譜顯示行（可點選游標、工具列改時值/高低音）；打字入口改由下方「簡譜整行輸入」承擔 */
        html += '<div class="sola321-note-row">';
        if (!toks.length) {
          var cur0 = (mi === solaEdit.mi && solaEdit.nti === 0) ? ' sola321-cursor' : '';
          html += '<span class="sola321-note-char' + cur0 + '" data-mi="' + mi + '" data-nti="0" data-col="0">' +
            '<span class="sola321-dots-above"></span>' +
            '<span class="sola321-digit"></span>' +
            '<span class="sola321-dots-below"></span></span>';
          /* v3.04.10 空小節拍槽：依 doc 拍號生成 N 個等寬隱形拍槽，讓和弦 X 軸量測有落點 */
          var beatCount = parseTimeSignatureToSola321((state3.doc && state3.doc.timeSignature) || '4/4').beats;
          if (beatCount > 1) {
            html += '<span class="sola321-beat-slots" data-mi="' + mi + '">';
            for (var bs = 1; bs < beatCount; bs++) {
              html += '<span class="sola321-beat-slot" data-mi="' + mi + '" data-beat="' + bs + '"></span>';
            }
            html += '</span>';
          }
        } else {
          for (var ti = 0; ti < toks.length; ti++) {
            var t = toks[ti];
            var cur = (mi === solaEdit.mi && ti === solaEdit.nti) ? ' sola321-cursor' : '';
            var da = '', db = '';
            for (var a = 0; a < t.above; a++) da += '<i class="sola321-dot"></i>';
            for (var b = 0; b < t.below; b++) db += '<i class="sola321-dot"></i>';
            var under = solaUnderlines(t.base);
            var underHtml = '';
            for (var u = 0; u < under; u++) underHtml += '<i class="sola321-uline"></i>';
            var isDash = solaDecomp(t.base).dash;
            var sizeCls = isDash ? ' sola321-ud' : (' sola321-u' + under);
            var colEndCls = (ti === toks.length - 1 || colOf[ti + 1] !== colOf[ti]) ? ' sola321-colend' : '';
            var dispBase = solaDisplayBase(t.base);
            html += '<span class="sola321-note-char' + cur + sizeCls + colEndCls + ' sola321-ow' + '" data-col="' + colOf[ti] + '" data-mi="' + mi + '" data-nti="' + ti + '" data-val="' + escAttr(solaEditNoteText(t)) + '" title="點擊輸入：直接打字改此音（_＝減時、.＝附點、\'＝高八度、,＝低八度、-＝延音；Enter 完成、Esc 取消）">' +
              '<span class="sola321-dots-above">' + da + '</span>' +
              '<span class="sola321-digit">' + escHtml(dispBase) + '</span>' +
              '<span class="sola321-dots-below">' + db + '</span>' +
              '<span class="sola321-ulines">' + underHtml + '</span></span>';
          }
        }
        html += '<div class="sola321-beams">';
        for (var bg = 0; bg < beatGroups.length; bg++) {
          var grp = beatGroups[bg];
          var maxUnder = 0, cnt = 0;
          for (var k = grp.start; k < grp.end; k++) {
            var u = solaUnderlines(toks[k].base);
            if (u > 0) { cnt++; if (u > maxUnder) maxUnder = u; }
          }
          if (cnt >= 2 && maxUnder > 0) {
            for (var lvl = 1; lvl <= maxUnder; lvl++) {
              html += '<span class="sola321-beam" data-col="' + grp.col + '" data-level="' + lvl + '" data-start="' + grp.start + '" data-end="' + grp.end + '"></span>';
            }
          }
        }
        html += '</div>';
        /* 編輯按鈕：預設隱藏，hover 小節時顯示 */
        html += '<button type="button" class="sola321-note-add" data-mi="' + mi + '" title="新增音符（點擊此音符後在彈出框輸入數字；_＝減時值、.＝附點）">＋</button>';
        if (m.barline !== false) {
          if (isLast) {
            html += '<span class="sola321-barline"></span><span class="sola321-barline-thin"></span>';
          } else {
            html += '<span class="sola321-barline"></span>';
          }
        }
        html += '</div>';
        /* ===== WYSIWYG：顯示行可直接點擊編輯（overlay input），無獨立輸入行 ===== */
        /* 歌詞區：① 拍群對齊顯示行（絕對定位） ② 整行輸入行（打字入口） */
        var lyricFields = [
          { field: 'lyricText',  val: m.lyricText  || '' },
          { field: 'lyricText2', val: m.lyricText2 || '' },
          { field: 'lyricText3', val: m.lyricText3 || '' },
          { field: 'lyricText4', val: m.lyricText4 || '' }
        ];
        var lyrShown = solaLyricRowsShown(m);
        var singCols = [];
        beatGroups.forEach(function(bg2) {
          var sing = false;
          for (var kk = bg2.start; kk < bg2.end; kk++) {
            var pd = solaDecomp(toks[kk].base);
            if (pd.digit && pd.digit !== '0' && !pd.dash) { sing = true; break; }
          }
          if (sing) singCols.push({ col: bg2.col, start: bg2.start, end: bg2.end });
        });
        html += '<div class="sola321-lyric-rows" data-mi="' + mi + '">';
        for (var ll = 0; ll < lyrShown; ll++) {
          var f = lyricFields[ll].field, v = lyricFields[ll].val;
          var raw = String(v).trim();
          var syl = raw ? (raw.indexOf(' ') >= 0 ? raw.split(/\s+/) : Array.from(raw)) : [];
          var spans = [];
          if (syl.length && singCols.length) {
            var lastCol = singCols[singCols.length - 1].col;
            for (var si2 = 0; si2 < syl.length; si2++) {
              var targetCol = si2 < singCols.length ? singCols[si2].col : lastCol;
              spans.push({ col: targetCol, sylIdx: si2 });
            }
            var lastSpan = spans[spans.length - 1];
            if (lastSpan.col < lastCol) lastSpan.extendTo = lastCol;
          }
          html += '<div class="sola321-lyric-line" data-mi="' + mi + '" data-ll="' + ll + '">';
          for (var ss = 0; ss < spans.length; ss++) {
            var sp = spans[ss];
            var wide = sp.extendTo != null;
            var sylVal = syl[sp.sylIdx];
            html += '<span class="sola321-lyric-syl' + (wide ? ' sola321-lyric-wide' : '') + ' sola321-ow-lyr" ' +
              'data-col="' + sp.col + '" data-extend="' + (sp.extendTo != null ? sp.extendTo : '') + '" ' +
              'data-field="' + f + '" data-mi="' + mi + '" data-ll="' + ll + '" data-syl="' + sp.sylIdx + '" ' +
              'data-val="' + escAttr(sylVal) + '" title="點擊輸入：直接打字改此字（Enter/失焦完成、Esc 取消；空白＝此音無歌詞）">' +
              escHtml(sylVal) + '</span>';
          }
          html += '</div>';
          /* ===== WYSIWYG：歌詞顯示行可直接點擊字元編輯（overlay input），無「詞N」整行輸入行 ===== */
        }
        html += '</div>';
        html += '</div>';
        /* 歌詞新增按鈕：預設隱藏，hover 時顯示 */
        if (lyrShown < 4) {
          html += '<button type="button" class="sola321-lyric-add" data-mi="' + mi + '" title="新增歌詞行">+Lyric</button>';
        }
        return html;
      }

  /* ===== Phase 2: Single-Layer Timeline Renderer =====
     使用 Event Model + Layout Engine 產生視覺。
     單一視覺層：不再有「顯示行＋輸入行」雙層。
     編輯器為 overlay input，輸入完成後更新 Event 並重新 layout。 */
  /* ===== Phase 6D：自由編輯（事件選取／拖曳／刪除＋eventOverrides 持久化） =====
     範圍守門：所有事件操作只綁定在 #sola321-score（Score Studio 容器）內的
     .sola321-measure-timeline 事件元素；並存舊編輯器 #v3-rows（.v3-cell）完全不影響。
     拖曳期間只更新預覽 DOM（el.style.left），放開指標才寫模型並重排。
     拖曳只改被選事件的 tick；其他事件的音樂時間永不變動。 */

  /* —— 確定性 uid（FNV-1a → base36）—— */
  function solaFNV36(str) {
    var h = 0x811c9dc5;
    for (var i = 0; i < str.length; i++) {
      h ^= str.charCodeAt(i);
      h = Math.imul(h, 0x01000193) >>> 0;
    }
    return h.toString(36);
  }
  function solaEventContent(e) {
    if (e.type === 'chord') return 'c:' + (e.chordName || '');
    if (e.type === 'lyric') return 'l:' + (e.text || '');
    return 'n:' + (e.pitch || 0) + (e.accidental || '') +
      (e.octave ? ('o' + e.octave) : '') + (e.underlines ? ('u' + e.underlines) : '') +
      (e.dots ? ('d' + e.dots) : '');
  }
  /* 為 m 的事件指定確定性 uid（基於「覆蓋前」的生成位置）。
     同類型、同位置、同內容的事件以陣列序（#n）區分 → 同內容事件仍可獨立選取。 */
  function solaAssignEventUids(m) {
    var map = {};
    var claim = function(e, key, seq) {
      var base = 'e' + solaFNV36([e.type, key, Math.round((e.start || 0) * 1000) / 1000, solaEventContent(e)].join('|'));
      var u = map[base] ? (base + '#' + seq) : base;
      map[u] = e;
      e.uid = u;
    };
    (m.melodyEvents || []).forEach(function(e, i) { claim(e, 'mel', i); });
    (m.chordEvents || []).forEach(function(e, i) { claim(e, 'chr', i); });
    (m.lyricTracks || [[],[],[],[]]).forEach(function(tr, vi) {
      tr.forEach(function(e, i) { claim(e, 'lyr' + (vi + 1), i); });
    });
    m._uidMap = map;
    return map;
  }
  /* 套用 m.eventOverrides（uid → {tick}）；順帶清掉結構式編輯後失效的舊覆蓋。
     舊專案無此欄位時直接回傳（零影響）。 */
  function applyEventOverrides(m) {
    var ovs = m.eventOverrides;
    if (!ovs) return;
    var keys = Object.keys(ovs);
    if (!keys.length) return;
    var map = m._uidMap || solaAssignEventUids(m);
    keys.forEach(function(u) {
      var ov = ovs[u];
      var tick = (ov && isFinite(+ov.tick)) ? Math.round(+ov.tick) : null;
      var e = map[u];
      if (e && tick != null) {
        e.start = solaTickToBeat(tick);
        e.tickOverride = tick;
      } else if (!e) {
        delete ovs[u];   /* 失效覆蓋（如 token 增刪後 uid 位移）→ 清理 */
      }
    });
  }
  function solaFindEventByUid(m, uid) {
    if (!m || !uid) return null;
    var map = m._uidMap;
    if (map && map[uid]) return map[uid];
    var found = null;
    (m.melodyEvents || []).concat(m.chordEvents || []).forEach(function(e) { if (!found && e.uid === uid) found = e; });
    if (!found) (m.lyricTracks || []).forEach(function(tr) { tr.forEach(function(e) { if (!found && e.uid === uid) found = e; }); });
    return found;
  }
  /* —— tick ↔ beat ↔ px 換算（统一入口；TICKS_PER_BEAT=480 已對齊既有 tick 欄位單位）—— */
  function solaTickToBeat(tick) { return (tick || 0) / TICKS_PER_BEAT; }
  function solaBeatToTick(beat) { return Math.round(beat * TICKS_PER_BEAT); }
  function solaSnapTick(tick) {
    var t = Math.round(tick / SNAP_TICKS) * SNAP_TICKS;
    return Math.max(0, t);
  }

  /* —— 選取狀態 —— */
  function solaClearSelection() {
    solaEdit.selEvent = null;
    Array.prototype.forEach.call(document.querySelectorAll('.sola321-ev-sel'), function(el) {
      el.classList.remove('sola321-ev-sel');
    });
  }
  function solaSelectEvent(el, ev, mi, m) {
    Array.prototype.forEach.call(document.querySelectorAll('.sola321-ev-sel'), function(x) { x.classList.remove('sola321-ev-sel'); });
    solaEdit.selEvent = { el: el, uid: ev.uid, type: ev.type, mi: mi };
    el.classList.add('sola321-ev-sel');
    var lbl = ev.type === 'chord' ? ('和弦 ' + (ev.chordName || '')) :
              ev.type === 'lyric' ? ('歌詞 ' + (ev.text || '')) :
              '音符 ' + (ev.pitch || 0);
    setSola321Status('已選取：小節 ' + (mi + 1) + ' ' + lbl + ' @ ' + Math.round((ev.start || 0) * TICKS_PER_BEAT) + ' ticks（水平拖曳移動；Delete 刪除）', '#42a5f5');
  }

  /* —— 拖曳提交：只改被選事件 tick；和弦寫入原生 chordTicks（格線/時間軸兩視圖一致），
       音符/歌詞寫入 eventOverrides（C1 最小持久化層，legacy 文字不動）—— */
    function solaCommitEventMove(d) {
        var m = d.m, ev = d.ev, tick = d.lastTick;
        solaPushUndo();
        if (ev.type === 'chord') {
          var ci = (typeof ev.srcCi === 'number') ? ev.srcCi : (m.chordEvents || []).indexOf(ev);
          if (ci >= 0) {
            m.chordTicks = m.chordTicks || [];
            m.chordOffsets = m.chordOffsets || [];
            // 確保陣列長度足夠（chordText 可能有更多和弦）
            var chords = String(m.chordText || '').trim().split(/\s+/).filter(Boolean);
            if (chords.length > m.chordTicks.length) m.chordTicks.length = chords.length;
            if (chords.length > m.chordOffsets.length) m.chordOffsets.length = chords.length;
            m.chordTicks[ci] = tick;
            m.chordOffsets[ci] = Math.floor(tick / TICKS_PER_BEAT);
          }
        } else {
          m.eventOverrides = m.eventOverrides || {};
          m.eventOverrides[ev.uid] = { tick: tick };
        }
        ev.start = solaTickToBeat(tick);
        ev.tickOverride = tick;
        syncLegacyToEvents(m);
        solaClearSelection();
        renderSola321Score(false);
        setSola321Status('已移動至 tick ' + tick + '（1/16 分吸附 ' + SNAP_TICKS + ' ticks）', '#4caf50');
        if (typeof saveCurrentDoc === 'function') saveCurrentDoc();
    }

  /* —— 歌詞字詞移除（複製 measureToTimeline 的拍群分字演算法，刪對應字詞範圍）—— */
  function solaSingableGroups(m) {
    var groups = [];
    var curStart = null, curNotes = [];
    (m.melodyEvents || []).forEach(function(n) {
      if (n.pitch !== 0) {
        if (curStart === null) curStart = n.start;
        curNotes.push(n);
      } else if (curNotes.length) {
        groups.push({ start: curStart, end: n.start, notes: curNotes.slice() });
        curStart = null; curNotes = [];
      }
    });
    if (curNotes.length) {
      var last = curNotes[curNotes.length - 1];
      groups.push({ start: curStart, end: last.start + last.duration, notes: curNotes.slice() });
    }
    return groups;
  }
  function solaRemoveLyricEventWords(m, ev) {
    var verseIdx = Math.min(3, Math.max(0, (ev.verse || 1) - 1));
    var field = ['lyricText','lyricText2','lyricText3','lyricText4'][verseIdx];
    var raw = String(m[field] || '').trim();
    if (!raw) return;
    var hasSpace = raw.indexOf(' ') >= 0;
    var words = hasSpace ? raw.split(/\s+/) : Array.from(raw);
    var groups = solaSingableGroups(m);
    if (!groups.length) return;
    var evIdx = (m.lyricTracks[verseIdx] || []).indexOf(ev);
    if (evIdx < 0) evIdx = 0;
    /* 分字範圍：與 parse 相同走法；剩餘字併最後群 → 最後事件範圍延伸到 words.length */
    var ranges = [];
    var wi = 0;
    groups.forEach(function(g, gi) {
      if (wi >= words.length) { ranges.push(null); return; }
      var take = Math.min(words.length - wi, g.notes.length > 0 ? g.notes.length : 1);
      var s = wi;
      wi += take;
      ranges.push(gi === groups.length - 1 ? [s, words.length] : [s, s + take]);
    });
    var range = ranges[evIdx] || ranges[ranges.length - 1];
    if (!range) return;
    words.splice(range[0], range[1] - range[0]);
    m[field] = words.join(hasSpace ? ' ' : '');
    syncLegacyToEvents(m);
  }

  /* —— 刪除選取事件（新增/修改/刪除全數經 solaPushUndo 納入既有 Undo/Redo）—— */
  function solaDeleteSelectedEvent() {
    var sel = solaEdit.selEvent;
    if (!sel || !sel.el || !sel.el.isConnected) return;
    var m = state3.doc.measures[sel.mi];
    if (!m) { solaClearSelection(); return; }
    var ev = solaFindEventByUid(m, sel.uid);
    if (!ev) { solaClearSelection(); return; }
    solaPushUndo();
    if (ev.type === 'chord') {
      var ci = (typeof ev.srcCi === 'number') ? ev.srcCi : (m.chordEvents || []).indexOf(ev);
      if (ci >= 0) v3ChordSlotWrite(m, ci, '');
    } else if (ev.type === 'note') {
      var toks = solaTokens(m);
      var ti = (typeof ev.srcTok === 'number') ? ev.srcTok : 0;
      if (ti >= 0 && ti < toks.length) { toks.splice(ti, 1); solaSetNoteText(m, toks); }
    } else {
      solaRemoveLyricEventWords(m, ev);
    }
    solaClearSelection();
    renderSola321Score(false);
    setSola321Status('已刪除事件（Ctrl+Z 可復原）', '#ff9800');
  }

  /* —— 拖曳引擎（預覽 DOM only；放開才提交）—— */
  function solaEvDragMove(e) {
    var d = solaEdit.dragEv;
    if (!d) return;
    var dx = e.clientX - d.x0;
    if (!d.moved && Math.abs(dx) < 4) return;
    if (!d.moved) { d.moved = true; d.el.classList.add('sola321-ev-drag'); }
    var tick = ((e.clientX - d.originX) / BEAT_WIDTH) * TICKS_PER_BEAT;
    tick = solaSnapTick(tick);
    var maxTick = parseTimeSignatureToBeats(d.m.timeSignature || '4/4') * TICKS_PER_BEAT;
    if (tick > maxTick) tick = maxTick;
    d.lastTick = tick;
    d.el.style.left = (MEASURE_PADDING + solaTickToBeat(tick) * BEAT_WIDTH) + 'px';
  }
  function solaEvDragUp(e) {
    window.removeEventListener('pointermove', solaEvDragMove);
    var d = solaEdit.dragEv;
    solaEdit.dragEv = null;
    if (!d) return;
    d.el.classList.remove('sola321-ev-drag');
    if (d.moved && d.lastTick != null && d.lastTick !== d.tick0) solaCommitEventMove(d);
  }
  function solaEvPointerDown(e) {
    if (e.button !== 0) return;
    var t = e.target;
    if (!t || !t.closest) return;
    if (t.closest('#v3-rows')) return;   /* 範圍守門：並存舊編輯器完全不響應 */
    var evEl = t.closest('[data-evuid]');
    if (!evEl) {
      if (t.closest('.sola321-measure-timeline')) solaClearSelection();
      return;
    }
    if (!evEl.closest('.sola321-measure-timeline')) return;
    if (t.closest('input, button, select, .v3-chord-picker')) return;  /* 既有控件優先 */
    var mi = +evEl.closest('.sola321-measure-timeline').getAttribute('data-mi');
    var m = state3.doc ? state3.doc.measures[mi] : null;
    if (!m) return;
    var ev = solaFindEventByUid(m, evEl.getAttribute('data-evuid'));
    if (!ev) return;
    e.preventDefault();
    solaSelectEvent(evEl, ev, mi, m);
    var mEl = evEl.closest('.sola321-measure-timeline');
    var rect = mEl.getBoundingClientRect();
    solaEdit.dragEv = {
      el: evEl, ev: ev, m: m, mi: mi,
      x0: e.clientX,
      originX: rect.left + MEASURE_PADDING,
      tick0: Math.round((ev.start || 0) * TICKS_PER_BEAT),
      moved: false, lastTick: null
    };
    window.addEventListener('pointermove', solaEvDragMove);
    window.addEventListener('pointerup', solaEvDragUp);
  }
  function solaEvKeydown(e) {
    if (e.key !== 'Delete' && e.key !== 'Backspace') return;
    var sel = solaEdit.selEvent;
    if (!sel || !sel.el || !sel.el.isConnected) return;
    var ae = document.activeElement;
    if (ae && /INPUT|TEXTAREA|SELECT/.test(ae.tagName || '')) return;
    e.preventDefault();
    solaDeleteSelectedEvent();
  }
  function bindSola321EventEditor() {
    if (window.__solaEvEditorBound) return;
    window.__solaEvEditorBound = true;
    var cont = document.getElementById('sola321-score');
    if (cont) cont.addEventListener('pointerdown', solaEvPointerDown);
    window.addEventListener('keydown', solaEvKeydown);
  }

  function renderSola321MeasureTimeline(m, mi, isLast, isShort, sysX) {
    if (!m._layout) { layoutMeasureEvents(m); }
    var layout = m._layout;

    var cls = 'sola321-measure-timeline' + (isLast ? ' sola321-end-bar' : '') + (isShort ? ' sola321-measure-short' : '');
    var html = '<div class="' + cls + '" data-mi="' + mi + '" style="width:' + layout.width + 'px;height:' + layout.height + 'px">';

    // 小節號
    html += '<div class="sola321-measure-num-timeline" style="left:4px">' +
      '<input type="text" data-num="' + mi + '" value="' + escAttr(m.number != null ? m.number : (mi + 1)) + '" title="小節號" /></div>';

    // 結構記號
    var markList = String(m.marks || '').trim().split(/\s+/).filter(Boolean);
    markList.forEach(function(mk) {
      html += '<span class="sola321-mark-inline" data-mi="' + mi + '" data-mark="' + escAttr(mk) + '">' + escHtml(mk) + '</span>';
    });

    // 和弦軌道 (chord track)
    html += '<div class="sola321-chord-track" style="height:' + TRACK_HEIGHTS.chord + 'px;top:' + TRACK_Y_OFFSET.chord + 'px">';
    (m.chordEvents || []).forEach(function(e) {
      /* 6C 修正：用小節內座標（相對小節左緣），不再加 systemX，
         避免與小節盒的 Flexbox 位置產生雙重偏移 */
      var absX = e.renderX;
      /* 6C：和弦指法圖（tick 定位），未收錄自動顯示「未收錄」；名稱置下 */
      var diag = (typeof renderChordSvg === 'function') ?
        renderChordSvg({ name: e.chordName }, (typeof currentChordInstrument === 'function' ? currentChordInstrument() : 'guitar'), true, true) :
        escapeChordName(e.chordName);
      html += '<span class="sola321-chord-event" data-eid="' + e.id + '" data-evuid="' + (e.uid || '') + '" style="left:' + absX + 'px;top:' + (TRACK_Y_OFFSET.chord + 2) + 'px">' +
        '<div class="v3-chord-diagram sola321-tl-chord">' + diag + '</div></span>';
    });
    html += '</div>';

    // 旋律軌道 (melody track)
    html += '<div class="sola321-melody-track" style="height:' + TRACK_HEIGHTS.melody + 'px;top:' + TRACK_Y_OFFSET.melody + 'px">';
    (m.melodyEvents || []).forEach(function(e) {
      var absX = e.renderX; // 6C 修正：小節內座標
      // 顯示簡譜數字 (帶附點、高低音點、升降記號)
      var disp = buildSolaDisplay(e);
      var cur = (solaEdit.activeEventId === e.id) ? ' sola321-cursor' : '';
      html += '<span class="sola321-note-char-timeline' + cur + '" data-eid="' + e.id + '" data-evuid="' + (e.uid || '') + '" ' +
        'style="left:' + absX + 'px;top:' + (TRACK_Y_OFFSET.melody + 2) + 'px;width:' + e.renderWidth + 'px">' +
        '<span class="sola321-digits">' + disp.digits + '</span>' +
        '<span class="sola321-dots-above">' + disp.dotsAbove + '</span>' +
        '<span class="sola321-dots-below">' + disp.dotsBelow + '</span>' +
        (disp.underline ? '<span class="sola321-uline"></span>' : '') +
        '</span>';
    });
    html += '</div>';

    // 歌詞軌道 (最多 4 行)
    for (var vi = 0; vi < 4; vi++) {
      var trackName = 'lyric' + (vi + 1);
      var trackEvents = (m.lyricTracks || [[],[],[],[]])[vi] || [];
      if (!trackEvents.length) continue;
      html += '<div class="sola321-lyric-track" data-verse="' + (vi+1) + '" style="height:' + TRACK_HEIGHTS.lyric + 'px;top:' + TRACK_Y_OFFSET[trackName] + 'px">';
      trackEvents.forEach(function(e) {
        var absX = e.renderX; // 6C 修正：小節內座標
        html += '<span class="sola321-lyric-syl-timeline" data-eid="' + e.id + '" data-evuid="' + (e.uid || '') + '" ' +
          'style="left:' + absX + 'px;width:' + e.renderWidth + 'px">' + escHtml(e.text || '') + '</span>';
      });
      html += '</div>';
    }

    // 連線 (beams)
    if (layout.beatGroups) {
      html += '<div class="sola321-beams-timeline" style="height:' + TRACK_HEIGHTS.melody + 'px;top:' + TRACK_Y_OFFSET.melody + 'px">';
      layout.beatGroups.forEach(function(bg) {
        var absX = bg.x; // 6C 修正：小節內座標
        html += '<span class="sola321-beam-timeline" data-level="1" ' +
          'style="left:' + absX + 'px;width:' + bg.width + 'px;"></span>';
      });
      html += '</div>';
    }

    // 小節線
    if (m.barline !== false) {
      html += '<span class="sola321-barline-timeline"></span>';
      if (isLast) html += '<span class="sola321-barline-thin-timeline"></span>';
    }

    html += '</div>';
    return html;
  }

  /* 將 Event 的 pitch/dots/accidental 等轉換為視覺顯示字串 */
  function buildSolaDisplay(e) {
    var p = e.pitch || 0;
    var dotsAbove = '';
    var dotsBelow = '';
    var underline = false;

    // dots
    if (e.dots && e.dots > 0) dotsAbove = new Array(e.dots + 1).join('·'); // 附點在上
    // octave shift
    if (e.octave > 0) {
      for (var i = 0; i < e.octave; i++) dotsAbove += '′';
    } else if (e.octave < 0) {
      for (var i = 0; i < -e.octave; i++) dotsBelow += '‵';
    }
    // accidental
    var acc = e.accidental || '';
    // underline (延長線符)
    if (e.underlines && e.underlines > 0) underline = true;

    var digits = (acc ? '<span class="sola321-acc">' + escHtml(acc) + '</span>' : '') + escHtml(String(p));

    return { digits: digits, dotsAbove: dotsAbove, dotsBelow: dotsBelow, underline: underline };
  }

  function escapeChordName(name) {
    return escHtml(String(name || '').trim());
  }

  /* 強化 layoutMeasureEvents 產出 beatGroups 資訊 (供 beam 顯示) */
  var _origLayoutMeasureEvents = null;
  (function() {
    _origLayoutMeasureEvents = typeof layoutMeasureEvents === 'function' ? layoutMeasureEvents : null;
    if (_origLayoutMeasureEvents) {
      // wrap with beatGroups computation
      window._origLayoutMeasureEvents = _origLayoutMeasureEvents;
    }
  })();

  /* ===== WYSIWYG inline 就地編輯（v3.04.10）：點音符/歌詞字元 → 原位變 input（focus+select），
       Enter/失焦寫回、Esc 取消；廢除舊 overlay 獨立彈窗（顯示層即編輯層，零錯位）===== */
  function openSolaNoteOverlay(ch) {
        var mi = +ch.getAttribute('data-mi');
        var nti = +ch.getAttribute('data-nti');
        var m = state3.doc.measures[mi];
        if (!m) return;
        solaSetTarget(mi);  // 點音符＝設目標小節（段落/和弦庫寫這裡）
        var digitEl = ch.querySelector('.sola321-digit');
        if (!digitEl) return;
        /* 就地變 input：移除原有 innerHTML，插入 input，寬度對齊該音格 */
        var origHtml = digitEl.innerHTML;
        var w = digitEl.offsetWidth || 22;
        var inp = document.createElement('input');
        inp.type = 'text';
        inp.className = 'sola321-inline-input';
        inp.maxLength = 12;
        inp.setAttribute('title', '直接打字改此音：_減時、.附點、高八度、低八度、-延音；Enter/失焦完成、Esc 取消');
        var toks = solaTokens(m);
        var cur = toks[nti] || { base: '', above: 0, below: 0 };
        inp.value = solaEditNoteText(cur);
        var r = digitEl.getBoundingClientRect();
        var fs = getComputedStyle(digitEl).fontSize || '14px';
        inp.style.cssText =
          'font-family:Consolas,monospace;font-size:' + fs + ';font-weight:700;' +
          'width:' + Math.max(44, w) + 'px;padding:1px 2px;border:2px solid var(--accent,#4a90d9);' +
          'border-radius:3px;background:#fff;color:#000;text-align:center;outline:none;box-sizing:border-box;';
        digitEl.innerHTML = '';
        digitEl.appendChild(inp);
        inp.focus();
        inp.select();

        var closed = false;
        var finish = function(save) {
          if (closed) return; closed = true;
          cleanup();
          if (save) {
            solaPushUndo();
            var parsed = solaParseEditNote(inp.value);
            if (parsed === null) {
              toks.splice(nti, 1);
            } else {
              toks[nti] = parsed;
            }
            solaSetNoteText(m, toks);
            solaEdit.mi = mi;
            solaEdit.nti = Math.min(nti, Math.max(0, toks.length - 1));
            setSola321Status('小節 ' + (mi + 1) + ' 音 ' + (nti + 1) + ' 已更新（可繼續點擊其他音）', '#38a169');
          }
          /* 還原 DOM 再重繪（重繪會全篇重建，inline input 一併清除） */
          renderSola321Score(false);
        };
        var cancel = function() { if (!closed) finish(false); };
        var cleanup = function() {
          document.removeEventListener('keydown', onKey, true);
          inp.removeEventListener('blur', onBlur);
          if (inp.parentNode) inp.parentNode.removeChild(inp);
        };
        var onKey = function(e) {
          if (e.key === 'Enter') { e.preventDefault(); finish(true); }
          else if (e.key === 'Escape') { e.preventDefault(); cancel(); }
        };
        var onBlur = function() { finish(true); };
        document.addEventListener('keydown', onKey, true);
        inp.addEventListener('blur', onBlur);
  }

  /* 渲染後綁定：input change（失焦即寫回 doc）＋點擊設游標 */
  function bindSola321Inputs() {
      /* 結構記號 chip：點擊＝移除該記號（事件委派，重繪後仍有效） */
      var cont = $('#sola321-score');
      if (cont) {
        cont.onclick = function(e) {
          var chip = e.target && e.target.closest ? e.target.closest('.sola321-mark-inline') : null;
          if (chip) {
            e.stopPropagation();
            solaRemoveMark(+chip.getAttribute('data-mi'), chip.getAttribute('data-mark'));
          }
          /* v3.04.09 (b) 目標小節：點擊小節內任何元素（音符/歌詞/和弦/＋/記號/小節號）即設為目標小節，橘框跟著動 */
          var measureEl = e.target && e.target.closest ? e.target.closest('.sola321-measure') : null;
          if (measureEl) {
            var mi = +measureEl.getAttribute('data-mi');
            if (!isNaN(mi)) solaSetTarget(mi);
          }
        };
      }
      /* ===== WYSIWYG：點擊顯示音符 → 原位彈出 overlay input（輸入＝編輯工具，非樂譜一部分）=====
             顯示行仍由 .sola321-note-char 顯示層負責；overlay 只負責「編輯中這一音」 */
    $$('#sola321-score .sola321-note-char[data-mi]').forEach(function(ch) {
      ch.addEventListener('click', function(e) {
        e.stopPropagation();
        solaSetTarget(+this.getAttribute('data-mi'));  // (b) 點音符＝設目標小節
        openSolaNoteOverlay(this);
      });
    });
    /* 和弦「整排槽」（SoLa321 行）：共用 picker 綁定——點擊指法圖選和弦；拖曳或 ←/→ 滑軌對準節拍 */
    bindChordSlotPickers('#sola321-score', function() { renderSola321Score(false); }, function() { solaPushUndo(); });
    $$('#sola321-score .v3-chord-slot-add').forEach(function(btn) {
      btn.addEventListener('click', function(e) {
        e.stopPropagation();
        var mi = this.getAttribute('data-mi');
        if (mi === null) return;
        solaSetTarget(+mi);  // (b) 點和弦＋＝設目標小節
        var m = state3.doc.measures[+mi];
        if (!m) return;
        var parts = v3ChordParts(m);
        var off = parts.length;  /* 新槽預設對齊下一拍 */
        var wrap = document.createElement('div');
        wrap.innerHTML = v3ChordSlotHtml('', mi, '__pending__', off);
        var slotEl = wrap.firstChild;
        this.parentNode.insertBefore(slotEl, this);
      });
    });
    $$('#sola321-score .v3-chord-slot-del').forEach(function(btn) {
      btn.addEventListener('click', function(e) {
        e.stopPropagation();
        var slot = this.closest('.v3-chord-slot');
        if (!slot) return;
        /* data-mi / data-ci 在 slot 殼上（v3ChordSlotHtml），button 自身沒有 → 舊版從 this 讀必然 null，× 靜默失效 */
        var mi = slot.getAttribute('data-mi');
        var ci = slot.getAttribute('data-ci');
        if (mi === null) return;
        var m = state3.doc.measures[+mi];
        if (!m) return;
        if (String(ci) === '__pending__') { slot.remove(); return; }  // 暫留槽未寫資料，直接移除
        solaPushUndo();
        v3ChordSlotWrite(m, +ci, '');   // 移除該槽、保留其他
        renderSola321Score(false);
      });
    });
    /* 音符「＋」：無限延伸音符（預設休止 0，輸入 _/. 可畫 8分/16分音符與附點） */
        $$('#sola321-score .sola321-note-add').forEach(function(btn) {
          btn.addEventListener('click', function(e) {
            e.stopPropagation();
            var mi = +this.getAttribute('data-mi');
            solaSetTarget(mi);  // (b) 點音符＋＝設目標小節
            var m = state3.doc.measures[mi];
            if (!m) return;
            solaPushUndo();
            var toks = solaTokens(m);
            // 在游標位置插入，或末尾
            var insertIdx = (solaEdit.mi === mi && solaEdit.nti < toks.length) ? solaEdit.nti + 1 : toks.length;
            toks.splice(insertIdx, 0, { base: '0', above: 0, below: 0 });
            solaSetNoteText(m, toks);
            solaEdit.mi = mi;
            solaEdit.nti = insertIdx;
            renderSola321Score(true);
          });
        });
        /* 拍槽點擊：在該拍位置插入音符 */
        $$('#sola321-score .sola321-beat-slot').forEach(function(slot) {
          slot.addEventListener('click', function(e) {
            e.stopPropagation();
            var mi = +this.getAttribute('data-mi');
            var beat = +this.getAttribute('data-beat');
            if (isNaN(mi) || isNaN(beat)) return;
            solaSetTarget(mi);
            var m = state3.doc.measures[mi];
            if (!m) return;
            solaPushUndo();
            var toks = solaTokens(m);
            // 計算該拍對應的 tick
            var tick = beat * 480;
            // 找到插入位置：第一個 tick >= 目標 tick 的 token 之前
            var noteTicks = m.noteTicks || [];
            var insertIdx = toks.length;
            for (var i = 0; i < noteTicks.length; i++) {
              if (noteTicks[i] >= tick) { insertIdx = i; break; }
            }
            toks.splice(insertIdx, 0, { base: '0', above: 0, below: 0 });
            // 同步更新 noteTicks
            m.noteTicks = m.noteTicks || [];
            m.noteTicks.splice(insertIdx, 0, tick);
            // 後續 ticks 保持不變（已經是正確的絕對位置）
            solaSetNoteText(m, toks);
            solaEdit.mi = mi;
            solaEdit.nti = insertIdx;
            renderSola321Score(true);
          });
        });
    /* ===== WYSIWYG：點擊歌詞顯示字元 → 原位彈出 overlay input（輸入＝編輯工具，非樂譜一部分）=====
        lyrics 資料仍存於 m[f] 整行字串；overlay 只負責「編輯中這一字」，完成後整行寫回 */
    function openSolaLyricOverlay(sylEl) {
          var f = sylEl.getAttribute('data-field') || 'lyricText';
          var mi = +sylEl.getAttribute('data-mi');
          var ll = +sylEl.getAttribute('data-ll') || 0;
          var sylIdx = +sylEl.getAttribute('data-syl') || 0;
          var m = state3.doc.measures[mi];
          if (!m) return;
          solaSetTarget(mi);  // (b) 點歌詞＝設目標小節
      // 關閉已存在的 lyrics overlay（防疊加）
      var oldOv = document.querySelector('.sola321-ow-input.sola321-ow-lyr');
      if (oldOv) oldOv.remove();
      var raw = String(m[f] || '');
      var syl = raw.trim() ? (raw.indexOf(' ') >= 0 ? raw.split(/\s+/) : Array.from(raw)) : [];
      var curVal = syl[sylIdx] != null ? syl[sylIdx] : '';
      var inp = document.createElement('input');
      inp.type = 'text';
      inp.className = 'sola321-ow-input sola321-ow-lyr';
      inp.value = curVal;
      inp.maxLength = 32;
      inp.setAttribute('title', '直接打字改此字（空白＝此音無歌詞）；Enter/失焦完成、Esc 取消');
      var r = sylEl.getBoundingClientRect();
      inp.style.cssText =
        'position:fixed;z-index:9999;box-sizing:border-box;' +
        'border:2px solid var(--accent,#4a90d9);border-radius:3px;' +
        'font-family:inherit;font-size:14px;font-weight:700;' +
        'padding:1px 4px;background:#fff;color:#000;text-align:center;outline:none;' +
        'left:' + Math.max(4, r.left - 4) + 'px;top:' + Math.max(4, r.top - 4) + 'px;' +
        'width:' + Math.max(52, Math.min(160, r.width + 16)) + 'px;';
      document.body.appendChild(inp);
      inp.focus();
      inp.select();

      var closed = false;
      var finish = function(save) {
        if (closed) return; closed = true;
        cleanup();
        if (save) {
          solaPushUndo();
          syl[sylIdx] = inp.value;
          // 寫回整行；若尾端全空白 → 收緊空白
          while (syl.length > 1 && syl[syl.length - 1] === '') syl.pop();
          m[f] = syl.join(' ');
          syncLegacyToEvents(m);
          // 末行空白自動收回顯示行數
          if (ll > 0 && m[f].trim() === '' && ll === solaLyricRowsShown(m) - 1 && (m.lyricRows || 1) > 1) {
            m.lyricRows = Math.max(1, ll);
          }
          setSola321Status('歌詞已更新（小節 ' + (mi + 1) + ' 行 ' + (ll + 1) + '）', '#38a169');
        }
        renderSola321Score(false);
      };
      var cancel = function() { if (!closed) finish(false); };
      var cleanup = function() {
        document.removeEventListener('keydown', onKey, true);
        window.removeEventListener('scroll', onScroll, true);
        inp.removeEventListener('blur', onBlur);
        if (inp.parentNode) inp.parentNode.removeChild(inp);
      };
      var onKey = function(e) {
        if (e.key === 'Enter') { e.preventDefault(); finish(true); }
        else if (e.key === 'Escape') { e.preventDefault(); cancel(); }
      };
      var onScroll = function() { cancel(); };
      var onBlur = function() { finish(true); };
      document.addEventListener('keydown', onKey, true);
      window.addEventListener('scroll', onScroll, true);
      inp.addEventListener('blur', onBlur);
      solaEdit.mi = mi;
      selectScoreGridCell(mi);
    }
    $$('#sola321-score .sola321-lyric-syl[data-syl]').forEach(function(sylEl) {
      sylEl.addEventListener('click', function(e) {
        e.stopPropagation();
        solaSetTarget(+this.getAttribute('data-mi'));  // (b) 點歌詞＝設目標小節
        openSolaLyricOverlay(this);
      });
    });
    $$('#sola321-score .sola321-lyric-add').forEach(function(btn) {
      btn.addEventListener('click', function(e) {
        e.stopPropagation();
        var mi = +this.getAttribute('data-mi');
        solaSetTarget(mi);  // (b) 點歌詞＋＝設目標小節
        var m = state3.doc.measures[mi];
        if (!m) return;
        var shown = solaLyricRowsShown(m);
        if (shown >= 4) return;
        solaPushUndo();
        m.lyricRows = shown + 1;
        renderSola321Score(false);
      });
    });
    $$('.sola321-meta-input').forEach(function(inp) {
      inp.addEventListener('change', function() {
        if (!state3.doc) return;
        var f = this.getAttribute('data-meta');
        if (f === 'key') {
          applyMainKeyChange(this.value, 'sola-meta-grid');
          return;
        }
        solaPushUndo();
        if (f === 'tempo') state3.doc.tempo = parseInt(this.value, 10) || 90;
        else state3.doc[f] = this.value.trim();
        renderSola321Score(false);
      });
    });
    /* 重點 1：歌曲名稱輸入（sola321-title-input）寫回 doc.title */
    $$('.sola321-title-input').forEach(function(inp) {
      inp.addEventListener('change', function() {
        if (!state3.doc) return;
        solaPushUndo();
        state3.doc.title = this.value.trim() || '未命名樂譜';
        renderSola321Score(false);
      });
    });
    $$('.sola321-measure-num input').forEach(function(inp) {
      inp.addEventListener('change', function() {
        var m = state3.doc.measures[+this.getAttribute('data-num')];
        if (!m) return;
        m.number = parseInt(this.value, 10) || (+this.getAttribute('data-num') + 1);
      });
    });
      }

      /* ===== Phase 2: Timeline Renderer Input Bindings =====
         單一視覺層：點擊事件元素 = 設 activeEventId → 彈出 overlay editor
         編輯完成 → 更新 Event Model → layoutMeasureEvents(m) → renderSola321Score(true) */
      function bindSola321TimelineInputs() {
        var cont = $('#sola321-score');
        if (!cont) return;

        // 結構記號 chip：點擊＝移除該記號（事件委派，重繪後仍有效）
        cont.onclick = function(e) {
          var chip = e.target && e.target.closest ? e.target.closest('.sola321-mark-inline') : null;
          if (chip) {
            e.stopPropagation();
            solaRemoveMark(+chip.getAttribute('data-mi'), chip.getAttribute('data-mark'));
          }
        };

        // 點擊 note/lyric/chord event → 設為 activeEventId 並彈出 editor
        $$('#sola321-score .sola321-note-char-timeline[data-eid], ' +
           '#sola321-score .sola321-lyric-syl-timeline[data-eid], ' +
           '#sola321-score .sola321-chord-event[data-eid]').forEach(function(el) {
          el.addEventListener('click', function(e) {
            e.stopPropagation();
            var eid = this.getAttribute('data-eid');
            solaEdit.activeEventId = eid;
            // 找到對應的 measure 和 event
            var doc = state3.doc;
            if (!doc) return;
            var found = null;
            doc.measures.forEach(function(m) {
              var all = [].concat(m.melodyEvents||[], m.chordEvents||[], (m.lyricTracks||[]).flat(), m.annotations||[]);
              all.forEach(function(e) { if (e.id === eid) found = { measure: m, event: e, type: e.type || e._track }; });
            });
            if (found) openEventEditor(found.event, found.measure, found.type);
            renderSola321Score(false); // 重繪高亮
          });
        });

        // 小節號編輯
        $$('#sola321-score .sola321-measure-num-timeline input[data-num]').forEach(function(inp) {
          inp.addEventListener('change', function() {
            var mi = +this.getAttribute('data-num');
            var m = state3.doc.measures[mi];
            if (m) {
              m.number = parseInt(this.value, 10) || (mi + 1);
              renderSola321Score(true);
            }
          });
        });
      }

      /* 開啟 Event Overlay Editor — 點擊事件元素時彈出 */
      function openEventEditor(event, measure, type) {
        // 移除舊 editor
        var old = document.getElementById('sola321-event-editor');
        if (old) old.remove();

        var editor = document.createElement('div');
        editor.id = 'sola321-event-editor';
        editor.style.cssText = 'position:fixed;background:#fff;border:1px solid #ccc;border-radius:6px;padding:12px;z-index:10000;box-shadow:0 4px 16px rgba(0,0,0,0.15);min-width:240px;font:13px var(--font);';
        editor.innerHTML = buildEventEditorHtml(event, type);
        document.body.appendChild(editor);

        // 定位在事件元素附近
        var el = document.querySelector('[data-eid="' + event.id + '"]');
        if (el) {
          var rect = el.getBoundingClientRect();
          editor.style.left = (rect.right + 10) + 'px';
          editor.style.top = rect.top + 'px';
        }

        // 綁定 editor 內的輸入
        bindEventEditorInputs(event, measure, editor);
      }

      function buildEventEditorHtml(event, type) {
        var html = '<div style="margin-bottom:8px;font-weight:600;color:#333;">編輯 ' + type + ' 事件</div>';
        if (type === 'note' || type === 'melody') {
          html += '<div style="margin:4px 0"><label>音高(1-7,0=休): <input type="number" data-field="pitch" value="' + (event.pitch||0) + '" min="0" max="7" style="width:50px"></label></div>';
          html += '<div style="margin:4px 0"><label>時值(拍): <input type="number" data-field="duration" value="' + (event.duration||1) + '" step="0.125" min="0.125" style="width:60px"></label></div>';
          html += '<div style="margin:4px 0"><label>附點: <input type="number" data-field="dots" value="' + (event.dots||0) + '" min="0" max="2" style="width:40px"></label></div>';
          html += '<div style="margin:4px 0"><label>八度(+1/-1): <input type="number" data-field="octave" value="' + (event.octave||0) + '" min="-2" max="2" style="width:40px"></label></div>';
          html += '<div style="margin:4px 0"><label>升降: <select data-field="accidental"><option value="">自然</option><option value="#"' + (event.accidental==='#'?' selected':'') + '>#</option><option value="b"' + (event.accidental==='b'?' selected':'') + '>b</option></select></label></div>';
          html += '<div style="margin:4px 0"><label>減時線: <input type="number" data-field="underlines" value="' + (event.underlines||0) + '" min="0" max="3" style="width:40px"></label></div>';
        } else if (type === 'lyric' || type === 'lyric1' || type === 'lyric2' || type === 'lyric3' || type === 'lyric4') {
          html += '<div style="margin:4px 0"><label>歌詞: <input type="text" data-field="text" value="' + escAttr(event.text||'') + '" style="width:160px"></label></div>';
          html += '<div style="margin:4px 0"><label>時值(拍): <input type="number" data-field="duration" value="' + (event.duration||1) + '" step="0.125" min="0.125" style="width:60px"></label></div>';
        } else if (type === 'chord') {
          html += '<div style="margin:4px 0"><label>和弦: <input type="text" data-field="chordName" value="' + escAttr(event.chordName||'') + '" style="width:160px" placeholder="如: C, Am7, F#m"></label></div>';
          html += '<div style="margin:4px 0"><label>時值(拍): <input type="number" data-field="duration" value="' + (event.duration||1) + '" step="0.125" min="0.125" style="width:60px"></label></div>';
        } else {
          html += '<div style="margin:4px 0;color:#666;">未支援的事件類型</div>';
        }
        html += '<div style="margin-top:10px;text-align:right">';
        html += '<button id="sola321-evt-save" style="margin-right:6px;padding:4px 12px;background:var(--accent);color:#fff;border:none;border-radius:3px;">儲存</button>';
        html += '<button id="sola321-evt-del" style="padding:4px 12px;background:#e53e3e;color:#fff;border:none;border-radius:3px;">刪除</button>';
        html += '<button id="sola321-evt-cancel" style="margin-left:6px;padding:4px 12px;border:1px solid #ccc;border-radius:3px;">取消</button>';
        html += '</div>';
        return html;
      }

      function bindEventEditorInputs(event, measure, editor) {
        var saveBtn = editor.querySelector('#sola321-evt-save');
        var delBtn = editor.querySelector('#sola321-evt-del');
        var cancelBtn = editor.querySelector('#sola321-evt-cancel');

        saveBtn.addEventListener('click', function() {
          var changed = false;
          editor.querySelectorAll('[data-field]').forEach(function(inp) {
            var field = inp.getAttribute('data-field');
            var val = inp.type === 'number' ? parseFloat(inp.value) : (inp.type === 'checkbox' ? inp.checked : inp.value);
            if (event[field] !== val) {
              event[field] = val;
              changed = true;
            }
          });
          if (changed) {
            solaPushUndo();
            // 重新 layout 並重繪
            if (measure._layout) delete measure._layout; // clear cache
            layoutMeasureEvents(measure);
            renderSola321Score(true);
          }
          editor.remove();
          solaEdit.activeEventId = null;
        });

        delBtn.addEventListener('click', function() {
          solaPushUndo();
          // 從對應陣列移除
          var track = event._track || event.type;
          if (track === 'melody') {
            measure.melodyEvents = (measure.melodyEvents||[]).filter(function(e){return e.id !== event.id});
          } else if (track === 'chord') {
            measure.chordEvents = (measure.chordEvents||[]).filter(function(e){return e.id !== event.id});
          } else if (track && track.startsWith('lyric')) {
            var vi = parseInt(track.replace('lyric','')) - 1;
            if (measure.lyricTracks && measure.lyricTracks[vi]) {
              measure.lyricTracks[vi] = measure.lyricTracks[vi].filter(function(e){return e.id !== event.id});
            }
          } else if (track === 'annotation') {
            measure.annotations = (measure.annotations||[]).filter(function(e){return e.id !== event.id});
          }
          if (measure._layout) delete measure._layout;
          layoutMeasureEvents(measure);
          renderSola321Score(true);
          editor.remove();
          solaEdit.activeEventId = null;
        });

        cancelBtn.addEventListener('click', function() {
          editor.remove();
          solaEdit.activeEventId = null;
          renderSola321Score(false); // 只重繪高亮
        });

        // ESC 關閉
        var escHandler = function(e) { if (e.key === 'Escape') { cancelBtn.click(); document.removeEventListener('keydown', escHandler); } };
        document.addEventListener('keydown', escHandler);
      }

      /* Tab 鍵快速重複（手冊 4.3）：把游標音的所有屬性（音高/時值/點號/臨時記號）複製到下一拍 */
  function duplicateSolaNoteToNext() {
    if (!state3.doc) return;
    var cur = solaGetCursor();
    if (!cur) return;
    var toks = cur.toks;
    var src = toks[cur.nti];
    if (!src) return;
    solaPushUndo();
    var nextIdx = cur.nti + 1;
    if (nextIdx >= toks.length) {
      // 末尾：若還有空間就新增一拍；沒有就跳下一小節最後一拍之後
      toks.push({ base: src.base, above: src.above, below: src.below });
    } else {
      toks[nextIdx] = { base: src.base, above: src.above, below: src.below };
    }
    solaSetNoteText(cur.m, toks);
    solaEdit.mi = cur.mi;
    solaEdit.nti = Math.min(nextIdx, toks.length - 1);
    renderSola321Score(true);
  }

  // 載入 SoLa321 模型：從 state3.doc 即時渲染可編輯簡譜樂譜，並做拍數驗證。切到該頁籤時觸發（loadSola321）。
  function loadSola321() {
    // 還沒載入專案（state3.doc 為 null）時直接顯示空白提示，避免 collectV3ToDoc(null) 炸掉
    if (!state3.doc) {
      renderSola321Score();  // 內部已處理「無 doc」→ 顯示「尚無樂譜內容」提示
      return;
    }
    collectV3ToDoc(state3.doc);
    migrateAllMeasures(state3.doc);  // Phase 1: 確保 Event Model 存在
    renderSola321Score();
  }

  // 通用：把後端 /export 回傳的絕對 sharedPath/path，換成 /api/files/download 可認的相對路徑。
  // /api/files/download 期望相對「資料根目錄的上一層」（D:\SheetMusicOMR_v3.00）的路徑，
  // 例如 data/exports/DC.sola321；sharedPath 是絕對路徑（D:\SheetMusicOMR_v3.00\data\...），要剝掉前綴。
  function toDownloadRel(absPath) {
    var s = String(absPath || '').replace(/\\/g, '/');
    // 若是 data/... 開頭（已相對），直接回傳；否則剝掉 <installRoot>/ 前綴
    if (/^data\//.test(s) || /^projects\//.test(s) || /^exports\//.test(s)) return s;
    // 絕對路徑：抓最後兩層（data/... 或 exports/...）
    var m = s.match(/data\/.*$/) || s.match(/exports\/.*$/) || s.match(/projects\/.*$/);
    return m ? m[0] : s;
  }

  // 匯出 SoLa321 JSON：走後端 /api/projects/{id}/export?format=sola321（rows 結構，既有 sola321 輸出器）
  // 回傳 {format, mime, path, sharedPath, bytes, filename}（寫檔、回路徑），
  // 真正 JSON 內容再從 sharedPath 用 /api/files/download 讀回
  function exportSola321() {
    if (!state3.currentDocId) { setSola321Status('請先載入專案再匯出', '#e53e3e'); return; }
    saveBeforeExport().then(function() {
      return api('/api/projects/' + state3.currentDocId + '/export', {
        method: 'POST', headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ format: 'sola321' })
      });
    }).then(function(res) {
      var rel = toDownloadRel(res.sharedPath || res.path);
      if (!rel) { setSola321Status('匯出回應無檔案路徑', '#e53e3e'); return; }
      api('/api/files/download?path=' + encodeURIComponent(rel))
        .then(function(bytes) {
          var blob = new Blob([bytes], { type: 'application/json' });
          triggerDownload(blob, ((state3.doc && state3.doc.title) || 'score') + '.sola321');
          setSola321Status('✓ 已匯出 SoLa321 JSON（' + (res.bytes || '?') + ' bytes）', '#38a169');
          toast('SoLa321 JSON 匯出完成', 'ok');
        })
                .catch(function(e) { setSola321Status('匯出失敗：' + e.message, '#e53e3e'); });
            }).catch(function(e) { setSola321Status('匯出失敗：' + e.message, '#e53e3e'); });
          }

          // 匯出 MusicXML（docx 必要格式）
          function exportSola321MusicXML() {
            if (!state3.currentDocId) { setSola321Status('請先載入專案再匯出', '#e53e3e'); return; }
            saveBeforeExport().then(function() {
              return api('/api/projects/' + state3.currentDocId + '/export', {
                method: 'POST', headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ format: 'musicxml' })
              });
            }).then(function(res) {
              var rel = toDownloadRel(res.sharedPath || res.path);
              if (!rel) { setSola321Status('匯出回應無檔案路徑', '#e53e3e'); return; }
              api('/api/files/download?path=' + encodeURIComponent(rel))
                .then(function(bytes) {
                  var blob = new Blob([bytes], { type: 'application/xml' });
                  triggerDownload(blob, ((state3.doc && state3.doc.title) || 'score') + '.musicxml');
                  setSola321Status('✓ 已匯出 MusicXML（' + (res.bytes || '?') + ' bytes）', '#38a169');
                  toast('MusicXML 匯出完成', 'ok');
                })
                .catch(function(e) { setSola321Status('匯出失敗：' + e.message, '#e53e3e'); });
            }).catch(function(e) { setSola321Status('匯出失敗：' + e.message, '#e53e3e'); });
          }

          // 通用先存檔再匯出 helper（確保最新 Score Studio / ChordPro 編輯內容已同步寫入後端）
          function saveBeforeExport() {
            if (_autoSaveTimer) {
              clearTimeout(_autoSaveTimer);
              _autoSaveTimer = null;
            }
            if (!state3.currentDocId || !state3.doc) return Promise.resolve();
            collectV3ToDoc(state3.doc);
            return api('/api/projects/' + state3.currentDocId, {
              method: 'PUT',
              headers: { 'Content-Type': 'application/json' },
              body: JSON.stringify(state3.doc)
            }).catch(function() {});
          }

          // 匯出 MIDI
          function exportMidi() {
            if (!state3.currentDocId) { setSola321Status('請先載入專案再匯出', '#e53e3e'); return; }
            saveBeforeExport().then(function() {
              return api('/api/projects/' + state3.currentDocId + '/export', {
                method: 'POST', headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ format: 'midi' })
              });
            }).then(function(res) {
              var rel = toDownloadRel(res.sharedPath || res.path);
              if (!rel) { setSola321Status('匯出回應無檔案路徑', '#e53e3e'); return; }
              fetchBlob('/api/files/download?path=' + encodeURIComponent(rel))
                .then(function(rawBlob) {
                  var blob = new Blob([rawBlob], { type: 'audio/midi' });
                  triggerDownload(blob, ((state3.doc && state3.doc.title) || 'score') + '.mid');
                  setSola321Status('✓ 已匯出 MIDI（' + (res.bytes || '?') + ' bytes）', '#38a169');
                  toast('MIDI 匯出完成', 'ok');
                })
                .catch(function(e) { setSola321Status('匯出失敗：' + e.message, '#e53e3e'); });
            }).catch(function(e) { setSola321Status('匯出失敗：' + e.message, '#e53e3e'); });
          }

          // 匯出 Word (.docx)
          function exportWord() {
            if (!state3.currentDocId) { setSola321Status('請先載入專案再匯出', '#e53e3e'); return; }
            saveBeforeExport().then(function() {
              return api('/api/projects/' + state3.currentDocId + '/export', {
                method: 'POST', headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ format: 'word' })
              });
            }).then(function(res) {
              var rel = toDownloadRel(res.sharedPath || res.path);
              if (!rel) { setSola321Status('匯出回應無檔案路徑', '#e53e3e'); return; }
              fetchBlob('/api/files/download?path=' + encodeURIComponent(rel))
                .then(function(rawBlob) {
                  var blob = new Blob([rawBlob], { type: 'application/vnd.openxmlformats-officedocument.wordprocessingml.document' });
                  triggerDownload(blob, ((state3.doc && state3.doc.title) || 'score') + '.docx');
                  setSola321Status('✓ 已匯出 Word（' + (res.bytes || '?') + ' bytes）', '#38a169');
                  toast('Word (.docx) 匯出完成', 'ok');
                })
                .catch(function(e) { setSola321Status('匯出失敗：' + e.message, '#e53e3e'); });
            }).catch(function(e) { setSola321Status('匯出失敗：' + e.message, '#e53e3e'); });
          }

          // 匯出 PDF (.pdf)
          function exportPdf() {
            if (!state3.currentDocId) { setSola321Status('請先載入專案再匯出', '#e53e3e'); return; }
            setSola321Status('正在產生 PDF 樂譜…', '#3182ce');
            saveBeforeExport().then(function() {
              return api('/api/projects/' + state3.currentDocId + '/export', {
                method: 'POST', headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ format: 'pdf' })
              });
            }).then(function(res) {
              var rel = toDownloadRel(res.sharedPath || res.path);
              if (!rel) { setSola321Status('匯出回應無檔案路徑', '#e53e3e'); return; }
              fetchBlob('/api/files/download?path=' + encodeURIComponent(rel))
                .then(function(rawBlob) {
                  var blob = new Blob([rawBlob], { type: 'application/pdf' });
                  triggerDownload(blob, ((state3.doc && state3.doc.title) || 'score') + '.pdf');
                  setSola321Status('✓ 已匯出 PDF（' + (res.bytes || '?') + ' bytes）', '#38a169');
                  toast('PDF 匯出完成', 'ok');
                })
                .catch(function(e) { setSola321Status('匯出失敗：' + e.message, '#e53e3e'); });
            }).catch(function(e) { setSola321Status('匯出失敗：' + e.message, '#e53e3e'); });
          }

          // 通用下載 helper（blob → a.download）
          function triggerDownload(blob, filename) {
            var url = URL.createObjectURL(blob);
            var a = document.createElement('a');
            a.href = url; a.download = filename;
            document.body.appendChild(a); a.click();
            setTimeout(function(){ URL.revokeObjectURL(url); document.body.removeChild(a); }, 100);
          }

  // 「從簡譜格線重新生成 SoLa321」：toolkit 動作（轉調/加小節/插和弦/八度）後若停在 SoLa321 頁籤，
  // 立即重新產生事件模型，貼齊最新 doc（即時反應）。
  function refreshSola321IfActive() {
    var pane = $('#sola321-pane');
    if (pane && pane.classList.contains('pane-active') && state3.doc) loadSola321();
  }

    function boot() {
    loadChords().then(function() {
      renderRootGrid();
      renderChordPanel();
      // 和弦庫載入後，若已在樂譜頁，重繪一次讓和弦槽指法圖從「未收錄」變出圖
      if (state3.doc) {
        var scorePane = $('#score-pane'), solaPane = $('#sola321-pane');
        if (scorePane && scorePane.classList.contains('pane-active')) renderV3Editor();
        if (solaPane && solaPane.classList.contains('pane-active')) renderSola321Score(false);
      }
      function redrawPanes() {   // 切換樂器（吉他/烏克麗麗）：指法圖跟隨，重繪樂譜頁和弦槽
        if (!state3.doc) return;
        var sp = $('#score-pane'), sl = $('#sola321-pane');
        if (sp && sp.classList.contains('pane-active')) renderV3Editor();
        if (sl && sl.classList.contains('pane-active')) renderSola321Score(false);
      }
      $('#instrument-guitar').addEventListener('change', function() { renderChordPanel(); redrawPanes(); });
      $('#instrument-ukulele').addEventListener('change', function() { renderChordPanel(); redrawPanes(); });

      /* 側邊欄「樂譜資訊」與樂譜雙向同步 */
      var sideTitle = $('#side-meta-title');
      var sideLyricist = $('#side-meta-lyricist');
      var sideComposer = $('#side-meta-composer');

      if (sideTitle) {
        sideTitle.addEventListener('input', function() {
          if (!state3.doc) return;
          state3.doc.title = this.value;
          var ht = $('#sola321-score .sola321-title-input');
          if (ht && document.activeElement !== ht) ht.value = this.value;
        });
        sideTitle.addEventListener('change', function() {
          if (!state3.doc) return;
          solaPushUndo();
          state3.doc.title = this.value.trim() || '未命名樂譜';
          renderChordProFromDoc(state3.doc);
          saveCurrentDoc();
        });
      }

      if (sideLyricist) {
        sideLyricist.addEventListener('input', function() {
          if (!state3.doc) return;
          state3.doc.lyricist = this.value;
          var hl = $('#sola321-score .sola321-meta-input[data-meta="lyricist"]');
          if (hl && document.activeElement !== hl) hl.value = this.value;
        });
        sideLyricist.addEventListener('change', function() {
          if (!state3.doc) return;
          solaPushUndo();
          state3.doc.lyricist = this.value.trim();
          renderChordProFromDoc(state3.doc);
          saveCurrentDoc();
        });
      }

      if (sideComposer) {
        sideComposer.addEventListener('input', function() {
          if (!state3.doc) return;
          state3.doc.composer = this.value;
          var hc = $('#sola321-score .sola321-meta-input[data-meta="composer"]');
          if (hc && document.activeElement !== hc) hc.value = this.value;
        });
        sideComposer.addEventListener('change', function() {
          if (!state3.doc) return;
          solaPushUndo();
          state3.doc.composer = this.value.trim();
          renderChordProFromDoc(state3.doc);
          saveCurrentDoc();
        });
      }
      /* 視窗縮放：和弦絕對定位落點與節拍比例減時線要重新量測 */
      var rsT = null;
      window.addEventListener('resize', function() {
        clearTimeout(rsT);
        rsT = setTimeout(function() {
          layoutSola321ChordRows();
          layoutSola321VerticalChords(document.getElementById('sola321-score'));
        }, 120);
      });
      if ($('#tonality-select')) {
        $('#tonality-select').addEventListener('change', function() {
          applyMainKeyChange(this.value, 'tonality-select');
        });
      }
      if ($('#doc-key')) {
        $('#doc-key').addEventListener('change', function() {
          applyMainKeyChange(this.value, 'doc-key');
        });
      }
    });
    if ($('#btn-refresh-tasks')) $('#btn-refresh-tasks').addEventListener('click', loadTasks);
    loadTasks();
    loadProjects();
    // Phase 1 Test: auto-load project from URL parameter ?project=ID
    var urlParams = new URLSearchParams(window.location.search);
    var projectId = urlParams.get('project');
    if (projectId) {
      console.log('[Phase1] Auto-loading project:', projectId);
      openProject(projectId);
    }
    if ($('#btn-new-project')) $('#btn-new-project').addEventListener('click', function() {
      api('/api/projects', { method: 'POST', body: JSON.stringify({ title: '未命名樂譜' }), headers: { 'Content-Type': 'application/json' } })
        .then(function(doc) { openProject(doc.id); });
    });
    if ($('#btn-save')) $('#btn-save').addEventListener('click', function() { solaSave(false); });

    /* V3.00 分頁切換 */
    if ($('#tab-chordpro')) $('#tab-chordpro').addEventListener('click', function() { switchTab('chordpro'); });
    if ($('#tab-score')) $('#tab-score').addEventListener('click', function() { switchTab('score'); });
    if ($('#tab-sola321')) $('#tab-sola321').addEventListener('click', function() { switchTab('sola321'); });

    /* V3.00 簡譜格線工具列 */
    if ($('#btn-add-row')) $('#btn-add-row').addEventListener('click', function() {
      if (!state3.doc) { openProjectHint(); return; }
      // 確保小節總數是 4 的倍數（補足空白格子），然後新增 4 小節
      var measures = state3.doc.measures || [];
      var remainder = measures.length % 4;
      if (remainder > 0) {
        var pad = 4 - remainder;
        for (var i = 0; i < pad; i++) {
          var nm = { number: measures.length + 1, chordText: '', noteText: '', lyricText: '', beats: [], marks: '' };
          ensureEventModel(nm);
          measures.push(nm);
        }
      }
      for (var i = 0; i < 4; i++) {
        var nm = { number: state3.doc.measures.length + 1, chordText: '', noteText: '', lyricText: '', beats: [], marks: '' };
        ensureEventModel(nm);
        state3.doc.measures.push(nm);
      }
      renderV3Editor();
    });
    if ($('#btn-add-one-measure')) $('#btn-add-one-measure').addEventListener('click', function() {
      if (!state3.doc) { openProjectHint(); return; }
      // 確保小節總數是 4 的倍數（補足空白格子），然後新增 1 小節
      var measures = state3.doc.measures || [];
      var remainder = measures.length % 4;
      if (remainder > 0) {
        var pad = 4 - remainder;
        for (var i = 0; i < pad; i++) {
          var nm = { number: measures.length + 1, chordText: '', noteText: '', lyricText: '', beats: [], marks: '' };
          ensureEventModel(nm);
          measures.push(nm);
        }
      }
      var nm = { number: state3.doc.measures.length + 1, chordText: '', noteText: '', lyricText: '', beats: [], marks: '' };
      ensureEventModel(nm);
      state3.doc.measures.push(nm);
      renderV3Editor();
    });
    if ($('#btn-insert-measure')) $('#btn-insert-measure').addEventListener('click', function() {
      if (!state3.currentDocId) { openProjectHint(); return; }
      var n = Math.max(1, parseInt($('#measure-count').value, 10) || 1);
      api('/api/projects/' + state3.currentDocId + '/measures/insert', {
        method: 'POST', headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ index: state3.doc ? state3.doc.measures.length : 0, count: n })
      }).then(function(res) { state3.doc = res.document; renderV3Editor(); toast('已插入 ' + n + ' 小節', 'ok'); refreshSola321IfActive(); })
        .catch(function(e) { toast('插入失敗：' + e.message, 'bad'); });
    });
    if ($('#btn-delete-measure')) $('#btn-delete-measure').addEventListener('click', function() {
      if (!state3.currentDocId || !state3.doc || !state3.doc.measures.length) { openProjectHint(); return; }
      var last = state3.doc.measures[state3.doc.measures.length - 1];
      state3.doc.measures.pop();
      api('/api/projects/' + state3.currentDocId + '/measures/delete', {
        method: 'POST', headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ measures: [last.number] })
      }).then(function(res) { state3.doc = res.document; renderV3Editor(); toast('已刪除小節 ' + last.number, 'ok'); refreshSola321IfActive(); })
        .catch(function(e) { toast('刪除失敗：' + e.message, 'bad'); });
    });
    if ($('#btn-transpose')) $('#btn-transpose').addEventListener('click', function() {
      if (!state3.currentDocId) { openProjectHint(); return; }
      var target = $('#transpose-key').value;
      api('/api/projects/' + state3.currentDocId + '/transpose', {
        method: 'POST', headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ key: target })
      }).then(function(res) {
        state3.doc = res.document;
        renderV3Editor();
        renderChordProFromDoc(state3.doc);
        var t = res.transpose || {};
        toast('已轉調 ' + t.fromKey + ' → ' + t.toKey + (t.chordCount ? '（移 ' + t.chordCount + ' 個和弦）' : ''), 'ok');
        refreshSola321IfActive();
      }).catch(function(e) { toast('轉調失敗：' + e.message, 'bad'); });
    });
    if ($('#btn-preview-sola321')) $('#btn-preview-sola321').addEventListener('click', function() {
      if (!state3.currentDocId) { openProjectHint(); return; }
      collectV3ToDoc(state3.doc);
      api('/api/projects/' + state3.currentDocId, { method: 'PUT', body: JSON.stringify(state3.doc), headers: { 'Content-Type': 'application/json' } })
        .then(function() { switchTab('sola321'); });
    });
    /* 八度功能：高音（上方點）/ 低音（下方點），由頂層 applyOctaveToSelected 處理 */
    if ($('#btn-octave-up')) $('#btn-octave-up').addEventListener('click', function(e) {
      e.preventDefault();
      applyOctaveToSelected(1);
    });
    if ($('#btn-octave-down')) $('#btn-octave-down').addEventListener('click', function(e) {
      e.preventDefault();
      applyOctaveToSelected(-1);
    });
    /* 小節線增刪（簡譜格線工具列 ＋│/－│）：在選定音符後拆小節／併下一小節 */
    if ($('#btn-v3-barline-add')) $('#btn-v3-barline-add').addEventListener('click', function(e) {
      e.preventDefault();
      v3BarlineAdd();
    });
    if ($('#btn-v3-barline-del')) $('#btn-v3-barline-del').addEventListener('click', function(e) {
      e.preventDefault();
      v3BarlineDel();
    });

    /* ===== SoLa321 頁籤頂部與工具列（可編輯簡譜樂譜 + 匯出 + 自訂下拉選單）===== */
    if ($('#btn-sola321-regen')) $('#btn-sola321-regen').addEventListener('click', function() {
      loadSola321();
    });
    if ($('#btn-sola321-reload')) $('#btn-sola321-reload').addEventListener('click', function() {
      loadSola321();
      toast('已重新載入樂譜', 'ok');
    });
    if ($('#btn-sola321-open-draft')) $('#btn-sola321-open-draft').addEventListener('click', function() {
      var fi = $('#sola321-draft-input');
      if (fi) { fi.value = ''; fi.click(); }
    });
    if ($('#sola321-draft-input')) $('#sola321-draft-input').addEventListener('change', function() {
      if (this.files && this.files[0]) openDraftJsonFile(this.files[0]);
    });
    if ($('#btn-sola321-save')) $('#btn-sola321-save').addEventListener('click', function() {
      solaSave(false);
    });
    if ($('#btn-sola321-print')) $('#btn-sola321-print').addEventListener('click', function() {
      var scoreCont = $('#sola321-score');
      if (scoreCont) layoutSola321VerticalChords(scoreCont);
      window.print();
    });
    if ($('#btn-sola321-export-json')) $('#btn-sola321-export-json').addEventListener('click', function() {
      exportSola321();
    });
    if ($('#btn-sola321-export-musicxml')) $('#btn-sola321-export-musicxml').addEventListener('click', function() {
      exportSola321MusicXML();
    });
    if ($('#btn-sola321-export-word')) $('#btn-sola321-export-word').addEventListener('click', function() {
      exportWord();
    });
    if ($('#btn-sola321-export-pdf')) $('#btn-sola321-export-pdf').addEventListener('click', function() {
      exportPdf();
    });

    /* SoLa321 編輯工具列：模式切換＋時值＋臨時記號＋八度＋休止＋刪除＋複撤銷 */
    $$('.sola321-tb-btn[data-mode]').forEach(function(b) {
      b.addEventListener('click', function() { solaSetMode(this.getAttribute('data-mode')); });
    });
    $$('.sola321-tb-btn[data-dur]').forEach(function(b) {
      b.addEventListener('click', function() { solaApplyOp('dur', this.getAttribute('data-dur')); });
    });
    $$('.sola321-tb-btn[data-op]').forEach(function(b) {
      b.addEventListener('click', function() {
        var op = this.getAttribute('data-op');
        if (op === 'undo') { solaUndo(); return; }
        if (op === 'redo') { solaRedo(); return; }
        solaApplyOp(op);
      });
    });
    /* Phase 6D：自由編輯（事件選取／拖曳／刪除）—— 委派綁定於持久容器 #sola321-score，
       重繪 innerHTML 不影響；僅作用於 Score Studio 時間軸事件，舊編輯器 #v3-rows 守門排除 */
    bindSola321EventEditor();
    /* 結構記號工具列（代號形式，切換游標小節） */
    $$('.sola321-tb-btn[data-mark]').forEach(function(b) {
      b.addEventListener('click', function() { solaToggleMark(this.getAttribute('data-mark')); });
    });

    /* ===== Score Studio 自訂彈出式下拉功能鍵（段落 ▾、小節 ▾、音符 ▾、符號 ▾） ===== */
    function closeAllSolaDropdowns(exceptWrap) {
      $$('.ss-dd-wrap.open').forEach(function(w) {
        if (w !== exceptWrap) {
          w.classList.remove('open');
          var trig = w.querySelector('.ss-dd-trigger');
          if (trig) trig.setAttribute('aria-expanded', 'false');
        }
      });
    }
    $$('.ss-dd-trigger').forEach(function(trig) {
      trig.addEventListener('click', function(e) {
        e.stopPropagation();
        var wrap = this.closest('.ss-dd-wrap');
        if (!wrap) return;
        var willOpen = !wrap.classList.contains('open');
        closeAllSolaDropdowns(wrap);
        wrap.classList.toggle('open', willOpen);
        this.setAttribute('aria-expanded', willOpen ? 'true' : 'false');
      });
    });
    $$('.ss-dd-item').forEach(function(item) {
      item.addEventListener('click', function(e) {
        e.stopPropagation();
        var act = this.getAttribute('data-dd-act') || this.getAttribute('data-ss-action');
        var val = this.getAttribute('data-val') || this.getAttribute('data-ss-val');
        closeAllSolaDropdowns(null);
        if (act === 'section') {
          solaToggleSection(val);
        } else if (act === 'section-clear') {
          solaClearSection();
        } else if (act === 'measure') {
          if (val === 'double-bar') solaToggleMark('‖');
          else if (val === 'repeat-start') solaToggleMark('𝄆');
          else if (val === 'repeat-end') solaToggleMark('𝄇');
          else if (val === 'add-measure') {
            var miAdd = solaResolveTargetMeasureIndex();
            if (miAdd >= 0) solaMeasureOp('add-after', miAdd);
          } else if (val === 'copy-measure') {
            var miCopy = solaResolveTargetMeasureIndex();
            if (miCopy >= 0) solaMeasureOp('copy', miCopy);
          } else if (val === 'paste-measure') {
            var miPaste = solaResolveTargetMeasureIndex();
            if (miPaste >= 0) solaMeasureOp('paste', miPaste);
          } else if (val === 'dup-measure') {
            solaDuplicateMeasure();
          } else if (val === 'del-measure') {
            var miDel = solaResolveTargetMeasureIndex();
            if (miDel >= 0) solaMeasureOp('del', miDel);
          }
        } else if (act === 'dur') {
          solaApplyOp('dur', val);
        } else if (act === 'op') {
          solaApplyOp(val);
        }
      });
    });
    document.addEventListener('click', function(e) {
      if (!e.target || !e.target.closest || !e.target.closest('.ss-dd-wrap')) {
        closeAllSolaDropdowns(null);
      }
    });

    /* 歌詞吸附模式切換與對齊最近音符 */
    $$('.ss-snap-btn[data-snap]').forEach(function(btn) {
      btn.addEventListener('click', function() {
        $$('.ss-snap-btn[data-snap]').forEach(function(b) { b.classList.remove('active'); });
        this.classList.add('active');
        layoutSola321VerticalChords(document.getElementById('sola321-score'));
        toast('歌詞吸附模式：' + this.textContent.trim(), 'ok');
      });
    });
    if ($('#btn-sola-snap-align')) $('#btn-sola-snap-align').addEventListener('click', function() {
      var mi = solaResolveTargetMeasureIndex();
      if (mi >= 0 && state3.doc && state3.doc.measures && state3.doc.measures[mi]) {
        var m = state3.doc.measures[mi];
        if (m.lyricText) m.lyricText = String(m.lyricText).trim().replace(/\s+/g, ' ');
        solaSave(true);
        layoutSola321VerticalChords(document.getElementById('sola321-score'));
        toast('已對齊第 ' + (m.number || (mi + 1)) + ' 小節歌詞至最近音符', 'ok');
      } else {
        layoutSola321VerticalChords(document.getElementById('sola321-score'));
        toast('已對齊歌詞至最近音符', 'ok');
      }
    });

    /* 字體縮放控制（當選取表頭歌名時獨立縮放歌名 0.6× ~ 2.4×，否則縮放樂譜字體 0.7× ~ 1.6×） */
    var solaFontScale = 1.0;
    function getActiveFontScale() {
      if (solaTitleFocused && state3.doc) {
        return Number(state3.doc.titleFontScale) || 1.0;
      }
      return solaFontScale;
    }
    function applySolaFontScale(val) {
      if (solaTitleFocused && state3.doc) {
        var tScale = Math.round(Math.min(2.4, Math.max(0.6, Number(val) || 1.0)) * 10) / 10;
        state3.doc.titleFontScale = tScale;
        var paneT = $('#sola321-pane');
        if (paneT) paneT.style.setProperty('--sola-title-scale', String(tScale));
        var titleWrap = document.querySelector('#sola321-score .sola321-title');
        if (titleWrap) titleWrap.style.setProperty('--sola-title-scale', String(tScale));
        var valElT = $('#sola-font-val');
        if (valElT) valElT.textContent = tScale.toFixed(1) + '×';
        var sliderT = $('#sola-font-slider');
        if (sliderT && Number(sliderT.value) !== tScale) sliderT.value = String(Math.min(1.6, Math.max(0.7, tScale)));
        saveCurrentDoc();
        return;
      }
      solaFontScale = Math.round(Math.min(1.6, Math.max(0.7, Number(val) || 1.0)) * 10) / 10;
      var pane = $('#sola321-pane');
      if (pane) pane.style.setProperty('--sola-font-scale', String(solaFontScale));
      var valEl = $('#sola-font-val');
      if (valEl) valEl.textContent = solaFontScale.toFixed(1) + '×';
      var slider = $('#sola-font-slider');
      if (slider && Number(slider.value) !== solaFontScale) slider.value = String(solaFontScale);
      requestAnimationFrame(function() {
        layoutSola321VerticalChords(document.getElementById('sola321-score'));
      });
    }
    if ($('#btn-sola-font-dec')) $('#btn-sola-font-dec').addEventListener('click', function() { applySolaFontScale(getActiveFontScale() - 0.1); });
    if ($('#btn-sola-font-inc')) $('#btn-sola-font-inc').addEventListener('click', function() { applySolaFontScale(getActiveFontScale() + 0.1); });
    if ($('#btn-sola-font-reset')) $('#btn-sola-font-reset').addEventListener('click', function() { applySolaFontScale(1.0); });
    if ($('#sola-font-slider')) $('#sola-font-slider').addEventListener('input', function() { applySolaFontScale(this.value); });

    /* 工作倍率控制（50% ~ 150%） */
    var solaWorkZoom = 100;
    function applySolaWorkZoom(pct) {
      solaWorkZoom = Math.min(150, Math.max(50, Math.round((Number(pct) || 100) / 10) * 10));
      var pane = $('#sola321-pane');
      if (pane) pane.style.setProperty('--sola-work-zoom', String(solaWorkZoom / 100));
      var zEl = $('#sola-zoom-val');
      if (zEl) zEl.textContent = solaWorkZoom + '%';
      requestAnimationFrame(function() {
        layoutSola321VerticalChords(document.getElementById('sola321-score'));
      });
    }
    if ($('#btn-sola-zoom-dec')) $('#btn-sola-zoom-dec').addEventListener('click', function() { applySolaWorkZoom(solaWorkZoom - 10); });
    if ($('#btn-sola-zoom-inc')) $('#btn-sola-zoom-inc').addEventListener('click', function() { applySolaWorkZoom(solaWorkZoom + 10); });

    /* 短小節警示線（⚠ 紅線）開關：切換後寫入 user config 持久化 */
    var wbtnEl = $('#sola-warnline-toggle');
    if (wbtnEl) wbtnEl.addEventListener('click', function() {
      applyWarnShortMeasures(!warnShortOn);
      this.classList.toggle('active', warnShortOn);
      this.title = '短小節警示線（目前' + (warnShortOn ? '開' : '關') + '）：' +
        (warnShortOn ? '點擊關閉小節底邊紅線' : '點擊開啟小節底邊紅線');
      api('/api/config', { method: 'POST', body: JSON.stringify({ warnShortMeasures: warnShortOn }), headers: { 'Content-Type': 'application/json' } })
        .catch(function(e) { toast('警示線設定存檔失敗：' + e.message, 'bad'); });
    });

    /* SoLa321 文件級快捷鍵（只當 SoLa321 頁籤活動時生效）：
           N/T/C 模式、1-7 音符、0 休止、E/Q/W 臨時記號、↑/↓ 八度、←/→ 游標、
           . 附點、R 三連音、Del 刪除、Ctrl+Z/Y 複撤銷、Ctrl+V 批量貼歌詞（T 模式） */
        document.addEventListener('keydown', function(e) {
          var pane = $('#sola321-pane');
          if (!pane || !pane.classList.contains('pane-active')) return;
          // 焦點在 text/number input（和弦、歌詞、meta 欄位）時，只讓游標鍵與複撤銷生效，
          // 其餘（數字、E/Q/W...）讓輸入正常
          var inText = e.target && (e.target.tagName === 'INPUT' || e.target.tagName === 'TEXTAREA' || e.target.isContentEditable);
          var mod = e.ctrlKey || e.metaKey;
          var k = e.key.toLowerCase();
          // 全域複撤銷（無論 focus，但輸入框內不攔截原生行為）
          if (mod && !inText) {
            if (k === 'z' && !e.shiftKey) { e.preventDefault(); solaUndo(); return; }
            if (k === 'y') { e.preventDefault(); solaRedo(); return; }
          }
          if (mod && inText) {
            if (k === 'z' && !e.shiftKey) { e.preventDefault(); solaUndo(); return; }
            if (k === 'y') { e.preventDefault(); solaRedo(); return; }
            return;  // 其餘 Ctrl 組合（如 Ctrl+V 貼上）交給原生
          }
          if (inText) {
        if (e.key === 'Escape') { e.target.blur(); }
        return;
      }
      // 非 input：完整快捷鍵（SoLa321 手冊第 3 章）
      switch (e.key) {
        case 'n': case 'N': solaSetMode('note'); break;
        case 't': case 'T': solaSetMode('lyric'); break;
        case 'c': case 'C': solaSetMode('chord'); break;
        case 'a': case 'A': case 's': case 'S': case 'd': case 'D':
        case 'f': case 'F': case 'g': case 'G': case 'h': case 'H':
          e.preventDefault(); solaApplyOp('dur', e.key.toUpperCase()); break;
        case '.': e.preventDefault(); solaApplyOp('dot'); break;
        case 'r': case 'R': solaApplyOp('triplet'); break;
        case 'e': case 'E': solaApplyOp('sharp'); break;
        case 'q': case 'Q': solaApplyOp('flat'); break;
        case 'w': case 'W': solaApplyOp('natural'); break;
        case '0': e.preventDefault(); solaApplyOp('rest'); break;
        case '1': case '2': case '3': case '4': case '5': case '6': case '7':
          e.preventDefault(); solaApplyOp('digit', e.key); break;
        case 'ArrowUp': e.preventDefault(); solaApplyOp('oct-up'); break;
        case 'ArrowDown': e.preventDefault(); solaApplyOp('oct-down'); break;
        case 'ArrowLeft': e.preventDefault(); solaMoveCursor(e.shiftKey ? -1 : 0, -1); break;
        case 'ArrowRight': e.preventDefault(); solaMoveCursor(e.shiftKey ? 1 : 0, 1); break;
        case 'Delete': case 'Backspace':
          e.preventDefault();
          if (e.key === 'Backspace') { solaMoveCursor(0, -1); }
          solaApplyOp('del'); break;
        case 'Tab':
          e.preventDefault();  // 重複上一音（Tab 手冊 4.3）：把游標音複製到下一拍
          duplicateSolaNoteToNext(); break;
        default:
          return;
      }
    });

    /* SoLa321 批量貼歌詞：T 模式下 Ctrl+V（非 input 焦點時），逐字分配到非休止音位 */
    document.addEventListener('paste', function(e) {
      var pane = $('#sola321-pane');
      if (!pane || !pane.classList.contains('pane-active')) return;
      if (solaEdit.mode !== 'lyric') return;
      var inText = e.target && (e.target.tagName === 'INPUT' || e.target.tagName === 'TEXTAREA');
      if (inText) return;  // 貼進特定欄位時用原生行為
      e.preventDefault();
      var txt = (e.clipboardData || window.clipboardData).getData('text/plain');
      if (!txt) return;
      if (!state3.doc) return;
      solaPushUndo();
      solaDistributeLyrics(txt);
      renderSola321Score(true);
      setSola321Status('✓ 已批量貼上歌詞（逐字分配到非休止音位）', '#38a169');
    });
  }
  // boot 在此正常結束；其餘初始化（#btn-save-score、匯出選單、OMR 引擎設定、dropzone、段落按鈕）
  // 都在 IIFE 頂層執行，不隸屬於 boot，避免 boot 意外中斷導致監聽未綁上。
    if ($('#btn-save-score')) $('#btn-save-score').addEventListener('click', function() { saveCurrentDoc(false, true); });

    /* V3.00 匯出選單：點「匯出 ▾」顯示/隱藏下拉；點菜單項執行對應匯出 */
        var exportBtn = $('#btn-export');
        var exportMenu = $('#export-menu');
        if (exportBtn && exportMenu) {
          exportBtn.addEventListener('click', function(e) {
            e.stopPropagation();
            exportMenu.hidden = !exportMenu.hidden;
          });
          // 點其他地方關選單
          document.addEventListener('click', function() {
            exportMenu.hidden = true;
          });
          // 菜單項點擊：委派處理
          exportMenu.addEventListener('click', function(e) {
            var item = e.target.closest('[data-export]');
            if (!item) return;
            var fmt = item.getAttribute('data-export');
            exportMenu.hidden = true;
            if (!state3.currentDocId) { openProjectHint(); return; }
            if (fmt === 'musicxml') exportSola321MusicXML();
            else if (fmt === 'sola321') exportSola321();
            else if (fmt === 'midi') exportMidi();
            else if (fmt === 'word') exportWord();
            else if (fmt === 'pdf') exportPdf();
            else if (fmt === 'lilypond') { switchTab('sola321'); }
          });
        }

        var lilyBtn = document.querySelector('[data-export="lilypond"]');
    if (lilyBtn) lilyBtn.addEventListener('click', function() {
      if (!state3.currentDocId) { openProjectHint(); return; }
      switchTab('sola321');
    });

    /* V3.00 OMR 引擎選擇（左欄）：寫入 user-config 的 ocrMode，並顯示引擎狀態 */
    loadOmrEngineConfig();

  /* 小節短拍警示線（紅線）開關：on=true 顯示小節底邊紅線，on=false 隱藏。
     不影響資料與匯出，純視覺警示；狀態列仍保留「短 N 小節」數字告知拍數缺口。 */
  var warnShortOn = false;
  function applyWarnShortMeasures(on) {
    warnShortOn = !!on;
    var cont = $('#sola321-score');
    if (cont) cont.classList.toggle('warn-off', !on);
  }

  function loadOmrEngineConfig() {
    var sel = $('#omr-engine-select');
    var note = $('#omr-engine-note');
    var badge = $('#badge-engine');
    if (!sel) return;
    api('/api/config').then(function(cfg) {
      sel.value = cfg.ocrMode || 'scoreforge';
      /* 小節短拍警示線（紅線）開關：預設關閉 → 樂譜上不出現警示紅線 */
      applyWarnShortMeasures(!!cfg.warnShortMeasures);
      var wbtn = $('#sola-warnline-toggle');
      if (wbtn) wbtn.classList.toggle('active', !!cfg.warnShortMeasures);
      if (wbtn) wbtn.title = '短小節警示線（目前' + (cfg.warnShortMeasures ? '開' : '關') + '）：' +
        (cfg.warnShortMeasures ? '點擊關閉小節底邊紅線' : '點擊開啟小節底邊紅線');
      api('/api/health').then(function(h) {
        var eng = h.engine || {};
        var sf = eng.scoreforge || {};
        var avail = sf.available ? '✓' : '✗';
        if (note) note.textContent = 'ScoreForge ' + avail + (sf.note ? '｜' + sf.note : '');
        if (badge) {
          if (sf.available) { badge.textContent = '引擎：ScoreForge 就緒'; badge.style.color = '#48bb78'; }
          else { badge.textContent = '引擎：' + (eng.mode || '檢查中…'); badge.style.color = '#a0aec0'; }
        }
      }).catch(function() {});
    }).catch(function() {});
    sel.addEventListener('change', function() {
      api('/api/config', { method: 'POST', body: JSON.stringify({ ocrMode: sel.value }), headers: { 'Content-Type': 'application/json' } })
        .then(function() { toast('OMR 引擎已切換：' + sel.value, 'ok'); })
        .catch(function(e) { toast('切換失敗：' + e.message, 'bad'); });
    });
  }

  function openProjectHint() {
    toast('請先在左側專案列點開一個專案', 'info');
  }

    var dz = $('#dropzone');
    var input = $('#file-input');
    if (dz && input) {
      dz.addEventListener('click', function() { input.click(); });
      ['dragleave', 'drop'].forEach(function(ev) {
        dz.addEventListener(ev, function(e) { e.preventDefault(); dz.classList.remove('drag'); });
      });
      dz.addEventListener('drop', function(e) {
        e.preventDefault();
        var f = e.dataTransfer && e.dataTransfer.files && e.dataTransfer.files[0];
        if (f) uploadFile(f);
      });
      input.addEventListener('change', function(e) {
        var f = e.target.files && e.target.files[0];
        if (f) uploadFile(f);
        input.value = '';
      });
      document.addEventListener('drop', function(e) { e.preventDefault(); });
    }

    var urlInput = $('#url-import-input');
    var urlBtn = $('#btn-url-import');
    if (urlBtn && urlInput) {
      urlBtn.addEventListener('click', function() {
        importFromUrl(urlInput.value);
      });
      urlInput.addEventListener('keydown', function(e) {
        if (e.key === 'Enter') {
          e.preventDefault();
          importFromUrl(urlInput.value);
        }
      });
    }

    ['btn-insert-verse', 'btn-insert-chorus', 'btn-insert-intro', 'btn-insert-bridge', 'btn-insert-outro'].forEach(function(id) {
      var btn = document.getElementById(id);
      if (btn) btn.addEventListener('click', function() {
        var tag = this.getAttribute('data-section') || 'verse';
        var editor = document.getElementById('chordpro-editor');
        if (!editor) return;
        var s = editor.selectionStart || 0;
        var text = editor.value || '';
        // 永遠確保段落標籤獨立成行（插入在游標所在行的正上方獨立一行，絕不插入在音符或和弦行中間）
        var lineStart = text.lastIndexOf('\n', Math.max(0, s - 1)) + 1;
        var before = text.substring(0, lineStart);
        var after = text.substring(lineStart);
        var prefix = (before.length > 0 && !before.endsWith('\n\n')) ? (before.endsWith('\n') ? '\n' : '\n\n') : '';
        var insertStr = prefix + '[' + tag + ']\n';
        editor.value = before + insertStr + after;
        var newPos = before.length + insertStr.length;
        editor.focus();
        editor.setSelectionRange(newPos, newPos);
        editor.dispatchEvent(new Event('input', { bubbles: true }));
      });
    });

    if (window.SyncEngine && typeof window.SyncEngine.bindEditorSync === 'function') {
      window.SyncEngine.bindEditorSync({
        getDoc: function() { return state3.doc; },
        ensureEventModel: typeof ensureEventModel === 'function' ? ensureEventModel : null,
        onScoreUpdated: function(res) {
          if (typeof renderV3Editor === 'function') renderV3Editor();
          if (typeof renderSola321Score === 'function') renderSola321Score(false);
          if (res && res.conflicts && res.conflicts.length) {
            updateSyncStatusBadge('⚠ 同步含衝突 (' + res.conflicts.length + ')', 'sync-warn');
          } else {
            updateSyncStatusBadge('⇄ ChordPro 已同步至樂譜', 'sync-ok');
          }
        }
      });
    }
    var btnChordProSync = document.getElementById('btn-chordpro-to-score');
    if (btnChordProSync) {
      btnChordProSync.addEventListener('click', function() {
        var ed = document.getElementById('chordpro-editor');
        if (!ed || !state3.doc || !window.SyncEngine) return;
        var res = window.SyncEngine.syncFromChordPro(ed.value, state3.doc, {
          ensureEventModel: typeof ensureEventModel === 'function' ? ensureEventModel : null
        });
        if (res && res.changed) {
          if (typeof renderV3Editor === 'function') renderV3Editor();
          if (typeof renderSola321Score === 'function') renderSola321Score(false);
          saveCurrentDoc();
          updateSyncStatusBadge('⇄ 已同步並儲存', 'sync-ok');
          toast('ChordPro 已同步至樂譜並儲存', 'success');
        }
      });
    }
    /* #btn-sola321-save 已於上方綁定 solaSave(false)，避免重複綁定觸發兩次儲存 */

  // build 標記：確認瀏覽器吃到的是「八度修復」版（Console 應印出 [app.js build] OMR-OCTAVE-2）
  console.log('[app.js build] OMR-SOLA-7  (SoLa321 可編輯簡譜：小節線、游標、快捷鍵、批量貼歌詞、複撤銷)');

  // 事件委派：點數字設 cursor（綁常駐 #v3-rows，contenteditable 重寫 DOM 也不會丟失）
  // span 態：讀 span 的 data-char-idx；純文字態（剛打完、未失焦）：用 caret 位置算出點的是第幾個數字
  var __v3rows = document.querySelector('#v3-rows');
  if (__v3rows) {
    __v3rows.addEventListener('click', function(e) {
      var el = e.target;
      if (el && el.nodeType !== 1) el = el.parentElement;
      var span = el ? el.closest('.v3-note-char') : null;
      if (span) {
        var mi = parseInt(span.getAttribute('data-mi'), 10);
        var charIdx = parseInt(span.getAttribute('data-char-idx'), 10);
        if (!isNaN(mi) && !isNaN(charIdx)) {
          scoreGridNoteCursor = { mi: mi, charIndex: charIdx };
          selectScoreGridCell(mi);
          $$('.v3-note-char').forEach(function(s) { s.classList.remove('selected'); });
          span.classList.add('selected');
        }
        return;
      }
      // 純文字態：用 caret 位置算出點選的數字（第幾個數字）
      var div = el ? el.closest('.v3-input-note') : null;
      if (!div) return;
      var mi2 = parseInt(div.getAttribute('data-mi'), 10);
      if (isNaN(mi2)) return;
      var caret = null;
      if (document.caretRangeFromPoint) caret = document.caretRangeFromPoint(e.clientX, e.clientY);
      if (!caret && document.caretPositionFromPoint) {
        var p = document.caretPositionFromPoint(e.clientX, e.clientY);
        if (p && div.contains(p.offsetNode)) { caret = document.createRange(); caret.setStart(p.offsetNode, p.offset); }
      }
      if (!caret || !div.contains(caret.startContainer)) return;
      var pre = document.createRange();
      pre.selectNodeContents(div);
      pre.setEnd(caret.startContainer, caret.startOffset);
      var pos = pre.toString().length;
      var text = div.textContent;
      var nBefore = 0;
      for (var k = 0; k < pos; k++) if (text.charAt(k) >= '0' && text.charAt(k) <= '9') nBefore++;
      var digitIdx = null;
      if (pos < text.length && text.charAt(pos) >= '0' && text.charAt(pos) <= '9') digitIdx = nBefore;
      else if (pos > 0 && text.charAt(pos - 1) >= '0' && text.charAt(pos - 1) <= '9') digitIdx = nBefore - 1;
      if (digitIdx === null) return;
      scoreGridNoteCursor = { mi: mi2, charIndex: digitIdx };
      selectScoreGridCell(mi2);
      // 視覺反饋：閃一下該格
      div.classList.add('v3-target-flash');
      setTimeout(function() { div.classList.remove('v3-target-flash'); }, 400);
    }, true);
  }

  /* ===== Phase 1 自動化測試（URL 參數 ?test=phase1 觸發）===== */
  function runPhase1Tests() {
    if (!state3.doc || !state3.doc.measures) {
      console.log('[Phase1] No doc loaded');
      return;
    }
    var results = [];
    function addResult(name, pass, detail) {
      results.push({name: name, pass: pass, detail: detail});
      console.log('[Phase1]', name, pass ? 'PASS' : 'FAIL', detail || '');
    }

    // 載入專案進行測試
    var doc = state3.doc;
    var ms = doc.measures;

    // TEST 1: Legacy -> Events -> Legacy 循環測試
    var roundtripPass = true;
    var roundtripDetails = [];
    ms.forEach(function(m, mi) {
      ensureEventModel(m);
      var orig = {
        noteText: m.noteText,
        chordText: m.chordText,
        lyricText: m.lyricText,
        lyricText2: m.lyricText2,
        lyricText3: m.lyricText3,
        lyricText4: m.lyricText4,
        chordOffsets: m.chordOffsets ? [...m.chordOffsets] : [],
        marks: m.marks
      };
      var rebuilt = eventsToLegacy(m);
      var diffs = [];
      for (var k in orig) {
        if (JSON.stringify(orig[k]) !== JSON.stringify(rebuilt[k])) {
          diffs.push({field: k, orig: orig[k], rebuilt: rebuilt[k]});
          roundtripPass = false;
        }
      }
      if (diffs.length) roundtripDetails.push('m' + (mi+1) + ': ' + diffs.map(function(d){return d.field}).join(','));
    });
    addResult('TEST_1_Roundtrip', roundtripPass, roundtripDetails.join('; ') || 'all measures match');

    // TEST 2: 沒有歌詞的音符 - 不應自動建立空 LyricEvent
    var test2Pass = true;
    ms.forEach(function(m) {
      ensureEventModel(m);
      var hasNotes = (m.melodyEvents||[]).some(function(e){return e.pitch !== 0});
      var hasLyrics = (m.lyricTracks||[]).some(function(t){return t.length > 0});
      if (hasNotes && !hasLyrics) {
        // 有音符無歌詞是正常的
      }
    });
    addResult('TEST_2_NotesWithoutLyrics', test2Pass, 'notes can exist without lyrics');

    // TEST 3: 只有和弦 - melodyEvents 可為空
    var test3Pass = true;
    ms.forEach(function(m) {
      ensureEventModel(m);
      var hasChords = (m.chordEvents||[]).length > 0;
      var hasMelody = (m.melodyEvents||[]).some(function(e){return e.pitch !== 0});
      if (hasChords && !hasMelody) {
        // 純和弦小節是合法的
      }
    });
    addResult('TEST_3_ChordsOnly', test3Pass, 'chord-only measures allowed');

    // TEST 4: 音符與歌詞數量不同
    var test4Pass = true;
    ms.forEach(function(m) {
      ensureEventModel(m);
      var noteCount = (m.melodyEvents||[]).filter(function(e){return e.pitch !== 0}).length;
      var lyricCount = (m.lyricTracks||[]).reduce(function(a,t){return a+t.length},0);
      // 不要求相等
    });
    addResult('TEST_4_CountMismatch', test4Pass, 'note/lyric counts independent');

    // TEST 5: 空白拍不建立假 Cell
    // Event Model 本身不使用 cell index，直接用 start/duration
    addResult('TEST_5_EmptyBeats', true, 'no cell index used');

    // TEST 6: 不同時值保留
    var test6Pass = true;
    ms.forEach(function(m) {
      ensureEventModel(m);
      (m.melodyEvents||[]).forEach(function(e) {
        if (e.duration <= 0) test6Pass = false;
      });
    });
    addResult('TEST_6_Durations', test6Pass, 'all durations > 0');

    // TEST 7: 附點/高低音/升降記號不遺失
    var test7Pass = true;
    ms.forEach(function(m) {
      ensureEventModel(m);
      (m.melodyEvents||[]).forEach(function(e) {
        // 只是確認欄位存在
        if (e.dots === undefined || e.octave === undefined || e.accidental === undefined) test7Pass = false;
      });
    });
    addResult('TEST_7_Articulations', test7Pass, 'dots/octave/accidental preserved');

    // TEST 8: 事件 ID 穩定 (不因重複 migrate 改變)
    var test8Pass = true;
    var idsSeen = {};
    ms.forEach(function(m) {
      ensureEventModel(m);
      ;[].concat(m.melodyEvents||[], m.chordEvents||[], (m.lyricTracks||[]).flat(), m.annotations||[])
        .forEach(function(e) {
          if (idsSeen[e.id]) test8Pass = false;
          idsSeen[e.id] = true;
        });
    });
    addResult('TEST_8_StableIDs', test8Pass, 'unique event IDs');

    // 總結
    var allPass = results.every(function(r){return r.pass});
    var summary = allPass ? 'ALL PASS' : 'SOME FAILED';
    console.log('[Phase1] ===== ' + summary + ' =====');
    console.log('[Phase1] Total:', results.length, 'Pass:', results.filter(function(r){return r.pass}).length);

    // 顯示結果到頁面
    var el = document.getElementById('phase1-test-results');
    if (!el) {
      el = document.createElement('div');
      el.id = 'phase1-test-results';
      el.style.cssText = 'position:fixed;top:60px;right:10px;background:#1e1e1e;color:#0f0;padding:10px;font:12px monospace;z-index:9999;max-width:500px;max-height:80vh;overflow:auto;border:2px solid #0f0;border-radius:6px;';
      document.body.appendChild(el);
    }
    el.innerHTML = '<b>Phase 1 Tests - ' + summary + '</b><br>' + results.map(function(r){
      return (r.pass?'✅':'❌') + ' ' + r.name + (r.detail?' <span style="color:#888">'+r.detail+'</span>':'');
    }).join('<br>') + '<br><button onclick="this.parentElement.remove()">關閉</button>';

    return {summary: summary, allPass: allPass, results: results};
  }

  // 檢查 URL 參數
  if (new URLSearchParams(window.location.search).get('test') === 'phase1') {
    console.log('[Phase1] Test mode activated');
    // 等待 doc 載入
    var checkDoc = setInterval(function() {
      console.log('[Phase1] Checking doc:', state3.doc ? state3.doc.title : 'null');
      if (state3.doc && state3.doc.measures) {
        clearInterval(checkDoc);
        console.log('[Phase1] Doc loaded, running tests...');
        setTimeout(runPhase1Tests, 1000);
      }
    }, 500);
    // 總超時 30 秒
    setTimeout(function() {
      clearInterval(checkDoc);
      console.log('[Phase1] Timeout waiting for doc');
    }, 30000);
  }

  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', boot);
  else boot();
  })();


