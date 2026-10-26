/* ScoreStudio 和弦指法表（§6.6 和弦欄位：SVG 指法圖）— 純離線資料＋SVG 元素
   只收錄標準開放把位（開放和弦）自然七根（C D E F G A B）；
   升/降根（C#、F#、Bb…）與未收錄和弦：誠實回 null，渲染層顯示「未收錄」，絕不補造。
   資料：6 根琴（低 E→高 e）開放把位標準指法，-1=悶音 ×、0=空弦 ○、1-4=品。
*/
(function () {
  const NS = "http://www.w3.org/2000/svg";
  // quality 鍵：maj(大) / min(小) / 7(七) / maj7(大七) / sus4(挂四)
  const SHAPES = {
    C: { maj: [-1, 3, 2, 0, 1, 0], min: [-1, 3, 5, 5, 4, 3], "7": [-1, 3, 2, 3, 1, 0], maj7: [-1, 3, 2, 0, 0, 0], sus4: [-1, 3, 2, 3, 1, 1] },
    D: { maj: [-1, -1, 0, 2, 3, 1], min: [-1, -1, 0, 3, 2, 1], "7": [-1, -1, 0, 2, 1, 0], maj7: [-1, -1, 0, 2, 3, 0], sus4: [-1, -1, 0, 2, 3, 0] },
    E: { maj: [0, 2, 2, 1, 0, 0], min: [0, 2, 2, 0, 0, 0], "7": [0, 2, 0, 1, 0, 0], maj7: [0, 2, 2, 1, 0, 2], sus4: [0, 2, 2, 0, 0, 4] },
    F: { maj: [-1, -1, 3, 3, 2, 1], min: [-1, -1, 3, 5, 4, 3], "7": [-1, -1, 3, 2, 1, 0], maj7: [-1, -1, 3, 3, 0, 1] },
    G: { maj: [3, 2, 0, 0, 0, 3], min: [3, 5, 5, 3, 3, 3], "7": [3, 2, 0, 0, 1, 0], maj7: [3, 2, 0, 0, 0, 2], sus4: [3, 0, 0, 0, 0, 3] },
    A: { maj: [-1, -1, 0, 2, 2, 0], min: [-1, -1, 0, 2, 1, 0], "7": [-1, -1, 0, 2, 0, 0], maj7: [-1, -1, 0, 2, 1, 0], sus4: [-1, -1, 0, 2, 2, 0] },
    B: { maj: [-1, -1, 1, 3, 1, 2], min: [-1, -1, 1, 2, 1, 2], "7": [-1, -1, 1, 3, 1, 0], maj7: [-1, -1, 1, 3, 0, 1], sus4: [-1, -1, 1, 3, 1, 2] },
  };
  const NATURAL_ROOTS = ["C", "D", "E", "F", "G", "A", "B"];

  // 把位表查表：依 root/quality 回 6 根品位陣列；無 → null（不補造）
  function shapeFor(root, quality) {
    const r = (root || "").toUpperCase();
    if (NATURAL_ROOTS.indexOf(r) < 0) return null;      // 升/降根：未收錄
    const table = SHAPES[r];
    if (!table) return null;
    const q = (quality || "maj").toLowerCase();
    const key = (q === "" || q === "maj" || q === "major") ? "maj"
      : (q === "min" || q === "m" || q === "minor") ? "min"
      : (q === "7") ? "7"
      : (q === "maj7" || q === "major7") ? "maj7"
      : (q === "sus4") ? "sus4"
      : null;
    if (key === null || !table[key]) return null;
    return table[key];
  }

  // 前端本地和弦名解析（供指法圖顯示用；權威 parsed 仍由後端 parse_chord 決定）
  function parseChordLocal(raw) {
    const s = (raw || "").trim();
    if (!s) return null;
    let head = s, bass = "";
    const slash = s.indexOf("/");
    if (slash > 0) { head = s.slice(0, slash); bass = s.slice(slash + 1); }
    const m = head.match(/^(C|C#|D|Eb|E|F|F#|G|Ab|A|Bb|B)(maj7|major7|sus4|m7|dim|add9|m|min|7|sus2)?(.*)$/);
    if (!m) return null;
    const root = m[1];
    let quality = (m[2] || "");
    quality = quality === "m" ? "min" : quality === "min" ? "min" : quality;
    return { root, quality, bass };
  }

  function chordLabel(chord) {
    if (!chord) return "?";
    if (chord.parsed && chord.parsed.root) {
      let s = chord.parsed.root + chord.parsed.quality;
      if (chord.parsed.bass) s += "/" + chord.parsed.bass;
      return s;
    }
    const p = parseChordLocal(chord.rawText);
    if (p) {
      let s = p.root + (p.quality === "min" ? "m" : p.quality === "maj" ? "" : p.quality);
      if (p.bass) s += "/" + p.bass;
      return s;
    }
    return chord.rawText || "?";
  }

  // 生成指法圖 <svg>（白底黑線、和弦名稱置上方、圖示縮小；開放把位 6 根 × 4 品）。
  // 無 shape → 畫佔位「未收錄」（誠實，不補造）。
  function diagramSVG(root, quality, bass, opts) {
    const o = opts || {};
    const W = o.width || 36, H = o.height || 46;
    const name = (o.name || "").trim();
    const svg = document.createElementNS(NS, "svg");
    svg.setAttribute("width", W); svg.setAttribute("height", H);
    svg.setAttribute("class", "ss-chord-svg");
    // 白底（無外框，符合附件格式）
    const bg = document.createElementNS(NS, "rect");
    bg.setAttribute("width", W); bg.setAttribute("height", H);
    bg.setAttribute("class", "cd-bg");
    svg.appendChild(bg);
    // 名稱置於圖上方（黑、粗體）
    const nameH = name ? 13 : 0;
    if (name) {
      const nt = document.createElementNS(NS, "text");
      nt.setAttribute("x", W / 2); nt.setAttribute("y", 10);
      nt.setAttribute("class", "cd-name"); nt.setAttribute("text-anchor", "middle");
      nt.setAttribute("font-size", "10");
      nt.textContent = name;
      svg.appendChild(nt);
    }
    const x0 = 5, x1 = W - 5, y0 = nameH + 7, y1 = H - 3;
    const sx = (x1 - x0) / 5, sy = (y1 - y0) / 4;
    const line = o.line || "#000000";   // 白底黑色：弦／品統一純黑
    const dotFill = o.dotFill || "#000000";

    // 弦（6 條縱線）
    for (let i = 0; i < 6; i++) {
      const ln = document.createElementNS(NS, "line");
      ln.setAttribute("x1", x0 + i * sx); ln.setAttribute("x2", x0 + i * sx);
      ln.setAttribute("y1", y0); ln.setAttribute("y2", y1);
      ln.setAttribute("class", "cd-string");
      ln.setAttribute("stroke", line);
      ln.setAttribute("stroke-width", i === 0 ? 1.4 : 0.7);
      svg.appendChild(ln);
    }
    // 品（5 條橫線，首品最粗）
    for (let j = 0; j <= 4; j++) {
      const y = y0 + j * sy;
      const ln = document.createElementNS(NS, "line");
      ln.setAttribute("x1", x0); ln.setAttribute("x2", x1);
      ln.setAttribute("y1", y); ln.setAttribute("y2", y);
      ln.setAttribute("stroke", line);
      ln.setAttribute("stroke-width", j === 0 ? 2 : 0.7);
      svg.appendChild(ln);
    }

    const shape = shapeFor(root, quality);
    if (!shape) {
      // 誠實：無指法 → 顯示「未收錄」佔位，不補造
      const t = document.createElementNS(NS, "text");
      t.setAttribute("x", (x0 + x1) / 2); t.setAttribute("y", (y0 + y1) / 2 + 3);
      t.setAttribute("class", "cd-missing"); t.setAttribute("text-anchor", "middle");
      t.setAttribute("font-size", "8");
      t.textContent = "未收錄";
      svg.appendChild(t);
      svg.setAttribute("data-has-shape", "0");
      return svg;
    }
    for (let i = 0; i < 6; i++) {
      const v = shape[i];
      const cx = x0 + i * sx;
      if (v === -1) {
        const t = document.createElementNS(NS, "text");
        t.setAttribute("x", cx); t.setAttribute("y", y0 - 1);
        t.setAttribute("class", "cd-x"); t.setAttribute("text-anchor", "middle");
        t.setAttribute("font-size", "7");
        t.textContent = "×";
        svg.appendChild(t);
      } else if (v === 0) {
        const c = document.createElementNS(NS, "circle");
        c.setAttribute("cx", cx); c.setAttribute("cy", y0 - 3);
        c.setAttribute("r", 1.8); c.setAttribute("class", "cd-open");
        c.setAttribute("fill", "none"); c.setAttribute("stroke", line);
        c.setAttribute("stroke-width", "0.9");
        svg.appendChild(c);
      } else {
        const c = document.createElementNS(NS, "circle");
        c.setAttribute("cx", cx); c.setAttribute("cy", y0 + (v - 1) * sy + sy / 2);
        c.setAttribute("r", 2.4); c.setAttribute("class", "cd-dot");
        c.setAttribute("fill", dotFill);
        svg.appendChild(c);
      }
      // 低音（slash 和弦）：低根標記
      if (bass && i === 0) {
        const t = document.createElementNS(NS, "text");
        t.setAttribute("x", cx); t.setAttribute("y", H - 0.5);
        t.setAttribute("class", "cd-bass"); t.setAttribute("text-anchor", "middle");
        t.setAttribute("font-size", "6");
        t.textContent = "b:" + bass;
        svg.appendChild(t);
      }
    }
    svg.setAttribute("data-has-shape", "1");
    return svg;
  }

  // 依 ChordRef 物件（{rawText, parsed}）直接生成指法圖 <svg>（名稱置圖上方、白底黑線）
  function diagramForChord(chord) {
    const p = (chord && chord.parsed && chord.parsed.root) ? chord.parsed
      : parseChordLocal(chord ? chord.rawText : "");
    const name = chordLabel(chord);
    if (!p) return diagramSVG("", "", "", { name: name === "?" ? "" : name, placeholder: true });
    return diagramSVG(p.root, p.quality, p.bass, { name: name });
  }

  window.ScoreChordDiagram = {
    shapeFor, parseChordLocal, chordLabel, diagramSVG, diagramForChord,
    NATURAL_ROOTS,
  };
})();
