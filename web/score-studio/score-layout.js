/* ScoreStudio 版面配置 — tick ↔ 座標（§8.1：SVG 可選取、帶 data-*；§8.3 縮放/捲動）
   對齊真實 ScoreDocument v1：
   - pitch:{degree:int(0=rest), accidental:int(+1升/-1降/0), octave:int(+1高八度/-1低八度), midi}
   - notation:{duration:str, dots:int, tieStart, tieStop}
   - ev.chords[]:{rawText, parsed:{root,quality,bass}} ；ev.lyrics[]:{text}
   - 時值：ticksPerQuarter=480；quarter=480、eighth=240 …
*/
(function () {
  const NS = "http://www.w3.org/2000/svg";
  const LAY = { chordRowY: 4, chordSlotH: 48, noteY: 58, lyricY: 92, measureH: 118 };
  const SLOT_W = 44;      // 一個和弦槽寬（指法表 40 + 間距；圖高 46 含上方名稱）
  const TPQ = 480;       // ticksPerQuarter
  const QW = 40;         // 一個四分音符（480 ticks）的像素寬
  const PAD = 26;        // 小節左 padding

  function evW(ev, zoom) {
    return ((ev.durationTicks || 480) / TPQ) * QW * zoom;
  }

  function measureWidthPx(ms, zoom) {
    const total = ms.events.reduce((s, e) => s + evW(e, 1), 0);
    return Math.max(120, total + PAD + 6) * zoom;
  }

  class Layout {
    constructor(store) { this.store = store; }

    render(container) {
      const s = this.store;
      const zoom = s.settings.zoom;
      const msList = s.allMeasures();
      const totalW = msList.reduce((sum, m) => sum + measureWidthPx(m, zoom), 0) + 40 * zoom;
      const H = LAY.measureH + 30;
      container.innerHTML = "";
      const svg = document.createElementNS(NS, "svg");
      svg.setAttribute("class", "ss-svg");
      svg.setAttribute("width", totalW);
      svg.setAttribute("height", H);
      svg.setAttribute("viewBox", `0 0 ${totalW} ${H}`);
      let x = 20 * zoom;
      for (let i = 0; i < msList.length; i++) {
        const ms = msList[i];
        const w = measureWidthPx(ms, zoom);
        this._drawMeasure(svg, i, ms, x, w, zoom);
        x += w;
      }
      // 游標
      const cur = this._cursorX(msList);
      if (cur != null) {
        const line = document.createElementNS(NS, "line");
        line.setAttribute("x1", cur); line.setAttribute("x2", cur);
        line.setAttribute("y1", 4); line.setAttribute("y2", H - 4);
        line.setAttribute("stroke", "var(--cursor)");
        line.setAttribute("stroke-width", "2");
        line.setAttribute("class", "ss-cursor");
        svg.appendChild(line);
      }
      container.appendChild(svg);
      return { svg, H, zoom };
    }

    _cursorX(msList) {
      const s = this.store;
      const zoom = s.settings.zoom;
      let cum = 20 * zoom;
      for (let i = 0; i < s.cursor.measureIndex && i < msList.length; i++) cum += measureWidthPx(msList[i], zoom);
      cum += (s.cursor.tick / TPQ) * QW * zoom;
      return cum;
    }

    _drawMeasure(svg, mi, ms, x, w, zoom) {
      const g = document.createElementNS(NS, "g");
      g.setAttribute("data-measure-index", mi);
      g.setAttribute("data-measure-id", ms.id);
      g.setAttribute("data-measure-number", ms.number);
      g.setAttribute("transform", `scale(${zoom})`);
      g.setAttribute("class", "ss-measure" + (this._isSel(mi) ? " selected" : ""));
      const sx = x / zoom;
      const innerW = w / zoom;

      // 小節框（超拍/未滿拍用紅邊）
      const box = document.createElementNS(NS, "rect");
      box.setAttribute("x", sx); box.setAttribute("y", 8);
      box.setAttribute("width", innerW - 4); box.setAttribute("height", LAY.measureH - 8);
      box.setAttribute("class", "ss-box" + (this._warn(mi) ? " ss-measure-warn" : ""));
      g.appendChild(box);

      // 小節線（左右）
      for (const xx of [sx, sx + innerW - 2]) {
        const l = document.createElementNS(NS, "line");
        l.setAttribute("x1", xx); l.setAttribute("x2", xx);
        l.setAttribute("y1", 10); l.setAttribute("y2", LAY.measureH - 4);
        l.setAttribute("class", "ss-bar" + (xx === sx + innerW - 2 && mi === this.store.allMeasures().length - 1 ? " final" : ""));
        g.appendChild(l);
      }
      // 小節號
      const num = document.createElementNS(NS, "text");
      num.setAttribute("x", sx + 3); num.setAttribute("y", 22);
      num.setAttribute("class", "ss-mnum");
      num.textContent = ms.number != null ? ms.number : (mi + 1);
      g.appendChild(num);

      // 第一小節：調號/拍號
      if (mi === 0) {
        const set = this.store.doc && this.store.doc.scoreSettings;
        const key = set && set.key && set.key.display;
        const ts = set && set.timeSignature;
        const meta = document.createElementNS(NS, "text");
        meta.setAttribute("x", sx + 34); meta.setAttribute("y", 22);
        meta.setAttribute("class", "ss-m-meta");
        meta.textContent = [key, ts ? `${ts.beats}/${ts.beatType}` : ""].filter(Boolean).join("  ");
        g.appendChild(meta);
      }

      // 事件（音符/休止/未知）
      let ex = sx + PAD;
      let tickAcc = 0;
      for (const ev of ms.events) {
        const wpx = evW(ev, 1);
        this._drawEvent(g, mi, ev, ex, wpx, ms);
        ex += wpx;
        tickAcc += (ev.durationTicks || 480);
        // 插入 placeholder（§8.4）：data-tick 是 tick 值（供 insertAt 用）
        const ins = document.createElementNS(NS, "text");
        ins.setAttribute("x", ex + 2); ins.setAttribute("y", LAY.noteY + 8);
        ins.setAttribute("class", "ss-insert");
        ins.textContent = "+";
        ins.setAttribute("data-measure-index", mi);
        ins.setAttribute("data-tick", tickAcc);
        g.appendChild(ins);
      }
      // §6.6 和弦槽橫列（小節頂端整排，可並列多和弦）
      this._drawChordRow(g, mi, ms, sx, innerW);
      svg.appendChild(g);
    }

    // §6.6 和弦槽橫列：每小節頂端一整排 slot，slot 對齊到「帶該和弦的事件 x」，可多和弦並列
    _drawChordRow(g, mi, ms, sx, innerW) {
      const ns = NS;
      const s = this.store;
      const y = LAY.chordRowY;
      const h = LAY.chordSlotH;
      const sel = s.selection;
      // 依事件排，slot 中心對齊該事件 ex（和該事件上的第 ci 個和弦）
      let ex = sx + PAD;
      for (const ev of ms.events) {
        const wpx = evW(ev, 1);
        const evChords = ev.chords || [];
        const slotCount = Math.max(evChords.length, (s.mode === "chord" ? 1 : 0));
        for (let ci = 0; ci < slotCount; ci++) {
          const c = evChords[ci];
          const isSel = sel && sel.measureIndex === mi && sel.eventId === ev.id &&
            ((sel.chordIndex == null && ci === 0) || sel.chordIndex === ci);
          const slotX = ex + 4 + ci * SLOT_W;
          const slot = document.createElementNS(ns, "g");
          slot.setAttribute("class", "ss-chord-slot" + (isSel ? " selected" : "") + (c ? "" : " empty"));
          slot.setAttribute("data-event-id", ev.id);
          slot.setAttribute("data-measure-index", mi);
          slot.setAttribute("data-chord-index", ci);
          slot.setAttribute("transform", `translate(${slotX},${y})`);
          const rect = document.createElementNS(ns, "rect");
          rect.setAttribute("width", SLOT_W - 4); rect.setAttribute("height", h);
          rect.setAttribute("class", "ss-chord-slot-bg");
          slot.appendChild(rect);
          if (c) {
            const diagram = (window.ScoreChordDiagram && window.ScoreChordDiagram.diagramForChord(c));
            if (diagram) {
              diagram.setAttribute("x", 0); diagram.setAttribute("y", 0);
              slot.appendChild(diagram);
            }
            // 和弦名稱已在指法圖上方呈現（白底黑線附件格式），槽內不再重覆 label
          } else {
            const ph = document.createElementNS(ns, "text");
            ph.setAttribute("x", (SLOT_W - 4) / 2); ph.setAttribute("y", h / 2 + 4);
            ph.setAttribute("class", "ss-chord-slot-empty");
            ph.setAttribute("text-anchor", "middle");
            ph.textContent = "+";
            slot.appendChild(ph);
          }
          g.appendChild(slot);
        }
        ex += wpx;
      }
    }

    _drawEvent(g, mi, ev, ex, wpx, ms) {
      const ns = NS;
      const isSel = this._isSelEvent(mi, ev.id);
      const lowconf = ev.provenance && ev.provenance.confidence != null && ev.provenance.confidence < 0.5;
      const review = ev.provenance && (ev.provenance.reviewStatus === "needs_review" || ev.provenance.reviewStatus === "unresolved");

      if (ev.type === "unknown") {
        const u = document.createElementNS(ns, "text");
        u.setAttribute("x", ex + 6); u.setAttribute("y", LAY.noteY + 10);
        u.setAttribute("class", "ss-note unknown");
        u.textContent = "?" + (ev.unknownText ? " " + ev.unknownText : "");
        u.setAttribute("data-event-id", ev.id);
        u.setAttribute("data-measure-index", mi);
        g.appendChild(u);
        this._attachSubs(g, mi, ev, ex, wpx);
        return;
      }

      const degree = ev.pitch ? (ev.pitch.degree != null ? ev.pitch.degree : 0) : 0;
      const accidental = ev.pitch && ev.pitch.accidental;
      const accPrefix = accidental === 1 ? "#" : accidental === -1 ? "b" : "";
      const label = accPrefix + degree;

      const n = document.createElementNS(ns, "text");
      n.setAttribute("x", ex + 6); n.setAttribute("y", LAY.noteY + 10);
      n.setAttribute("class", "ss-note" + (isSel ? " selected" : "") + (lowconf ? " lowconf" : "") + (review ? " lowconf" : ""));
      n.textContent = label;
      n.setAttribute("data-event-id", ev.id);
      n.setAttribute("data-measure-index", mi);
      g.appendChild(n);

      // 高低八度點（octave +1 上點 / -1 下點）
      const oct = ev.pitch ? (ev.pitch.octave || 0) : 0;
      if (oct > 0) {
        const d = document.createElementNS(ns, "circle");
        d.setAttribute("cx", ex + 6 + (label.length * 7)); d.setAttribute("cy", LAY.noteY - 6);
        d.setAttribute("r", 2.4); d.setAttribute("class", "ss-dot");
        g.appendChild(d);
      } else if (oct < 0) {
        const d = document.createElementNS(ns, "circle");
        d.setAttribute("cx", ex + 6 + (label.length * 7)); d.setAttribute("cy", LAY.noteY + 20);
        d.setAttribute("r", 2.4); d.setAttribute("class", "ss-dot");
        g.appendChild(d);
      }
      // 附點（notation.dots）
      const dots = ev.notation && ev.notation.dots;
      if (dots) {
        for (let i = 0; i < dots; i++) {
          const d = document.createElementNS(ns, "circle");
          d.setAttribute("cx", ex + 6 + (label.length * 7) + 6 + i * 6);
          d.setAttribute("cy", LAY.noteY + 4);
          d.setAttribute("r", 2); d.setAttribute("class", "ss-dot");
          g.appendChild(d);
        }
      }
      // tie 顯示（-）
      if (ev.notation && (ev.notation.tieStop || ev.notation.tieStart)) {
        const t = document.createElementNS(ns, "text");
        t.setAttribute("x", ex + 6 + (label.length * 7) + (dots ? dots * 6 + 6 : 6));
        t.setAttribute("y", LAY.noteY + 10);
        t.setAttribute("class", "ss-note");
        t.textContent = "-";
        g.appendChild(t);
      }
      this._attachSubs(g, mi, ev, ex, wpx);
    }

    // 歌詞（下）— 事件的子物件；和弦改由頂端和弦槽 _drawChordRow 負責（§6.6 整排並列）
    _attachSubs(g, mi, ev, ex, wpx) {
      const ns = NS;
      if (ev.lyrics && ev.lyrics.length) {
        const lyricTxt = ev.lyrics.map(l => l.text || "").join("");
        const t = document.createElementNS(ns, "text");
        t.setAttribute("x", ex + 4); t.setAttribute("y", LAY.lyricY + 10);
        t.setAttribute("class", "ss-lyric");
        t.textContent = lyricTxt;
        t.setAttribute("data-event-id", ev.id);
        t.setAttribute("data-measure-index", mi);
        g.appendChild(t);
      }
    }

    _isSel(mi) {
      const sel = this.store.selection;
      return sel && sel.measureIndex === mi;
    }
    _isSelEvent(mi, id) {
      const sel = this.store.selection;
      return sel && sel.measureIndex === mi && sel.eventId === id;
    }
    _warn(mi) {
      const rep = this.store.validation;
      if (!rep || !Array.isArray(rep.checks)) return false;
      const c = rep.checks.find(x => x.measure === mi + 1);
      return c && c.status !== "valid";
    }
  }

  window.ScoreStudioLayout = { Layout, LAY, TPQ, QW, evW, measureWidthPx };
})();
