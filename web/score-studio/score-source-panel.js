/* ScoreStudio 原圖校正面板（§11.2 雙向定位）
   對齊真實端點：GET /source-pages → {pages:[{name, path, size}]}
   拍數狀態：validation.checks[]（measure 1-based，經 statusesOf 轉 0-based）
   事件：ev.provenance / ev.chords[] / ev.lyrics[]
   reviewStatus 合法值：verified | needs_review | unresolved（schema 枚舉）
*/
(function () {
  const { api } = window.ScoreStudioAPI;
  const { statusesOf } = window.ScoreStudioStore;

  class SourcePanel {
    constructor(store, docId, render) {
      this.store = store; this.docId = docId; this.render = render;
      this.pages = [];
      this._bind();
    }
    _bind() {
      const t = document.getElementById("ss-source-toggle");
      if (t) t.addEventListener("click", () => {
        const el = document.getElementById("ss-source");
        el.classList.toggle("hidden");
        if (!el.classList.contains("hidden") && !this._loaded) this.loadPages();
      });
      ["review", "unres", "low", "over"].forEach(f => {
        const el = document.getElementById("ss-f-" + f);
        if (el) el.addEventListener("change", () => this.renderMarks());
      });
      const bb = document.getElementById("ss-f-bbox");
      if (bb) bb.addEventListener("change", () => this.renderMarks());
      const mv = document.getElementById("ss-mark-verified");
      if (mv) mv.addEventListener("click", () => this._mark("verified"));
      const mc = document.getElementById("ss-mark-corrected");
      if (mc) mc.addEventListener("click", () => this._markCorrected());
      const mu = document.getElementById("ss-mark-unres");
      if (mu) mu.addEventListener("click", () => this._mark("unresolved"));
    }
    async loadPages() {
      this._loaded = true;
      const note = document.getElementById("ss-source-note");
      const wrap = document.getElementById("ss-source-img-wrap");
      try {
        const data = await api.doc(this.docId).sourcePages();
        this.pages = (data && data.pages) || [];
      } catch (e) { this.pages = []; }
      if (!this.pages.length) {
        if (note) note.textContent = "此專案沒有原圖頁面（純文字/匯入專案）。僅顯示 token/bbox 對照。";
        if (wrap) wrap.innerHTML = "";
        return;
      }
      const p = this.pages[0];
      const rel = p.path || p.name;
      const img = document.createElement("img");
      img.id = "ss-source-img";
      img.src = "/api/files/preview?path=" + encodeURIComponent(rel);
      img.alt = "原圖";
      img.draggable = false;
      img.addEventListener("error", () => {
        if (note) note.textContent = "原圖不存在（可能已清理），僅顯示 token/bbox";
      });
      if (wrap) wrap.innerHTML = "";
      if (wrap) wrap.appendChild(img);
      if (note) note.textContent = "原圖頁面：" + this.pages.map(x => x.name).join(", ");
    }
    _activeFilters() {
      const on = id => { const e = document.getElementById(id); return e ? e.checked : false; };
      return { review: on("ss-f-review"), unres: on("ss-f-unres"), low: on("ss-f-low"), over: on("ss-f-over"), bbox: on("ss-f-bbox") };
    }
    _statusMap() {
      return statusesOf(this.store.validation);
    }
    renderMarks() {
      const f = this._activeFilters();
      const list = document.getElementById("ss-source-map");
      if (!list) return;
      const statuses = this._statusMap();
      const msList = this.store.allMeasures();
      const rows = [];
      let count = 0;
      for (let mi = 0; mi < msList.length; mi++) {
        const m = msList[mi];
        const mStatus = statuses[mi];
        for (const ev of m.events) {
          const p = ev.provenance || {};
          const reasons = [];
          if (f.review && p.reviewStatus === "needs_review") reasons.push("needs_review");
          if (f.unres && p.reviewStatus === "unresolved") reasons.push("unresolved");
          if (f.low && p.confidence != null && p.confidence < 0.5) reasons.push("低信心");
          if (f.over && mStatus && mStatus !== "valid") reasons.push(mStatus);
          if ((ev.chords || []).some(c => c.parsed == null && c.rawText)) reasons.push("和弦未解析");
          if (reasons.length) {
            count++;
            const deg = ev.pitch != null
              ? ((ev.pitch.accidental === 1 ? "#" : ev.pitch.accidental === -1 ? "b" : "") + ev.pitch.degree)
              : ev.type;
            let line = "小節" + (m.number || mi + 1) + " " + deg + " [" + reasons.join(", ") + "]";
            if (f.bbox && p.bbox) line += " @" + JSON.stringify(p.bbox);
            rows.push(line);
          }
        }
      }
      list.textContent = count ? rows.slice(0, 60).join("\n") : "無符合過濾的事件";
      list.style.whiteSpace = "pre-wrap";
    }
    _mark(status) {
      const sel = this.store.selection;
      if (!sel) return;
      const ms = this.store.allMeasures()[sel.measureIndex];
      if (!ms) return;
      const ev = ms.events.find(e => e.id === sel.eventId);
      if (!ev) return;
      ev.provenance = ev.provenance || { source: "manual" };
      ev.provenance.reviewStatus = status;
      ev.provenance.reviewedByUser = true;
      this.store.dirty = true;
      this.render();
      this.renderMarks();
    }
    // 「錯誤已修正」= verified + 標記 correctedValue（§6.7 溯源）
    _markCorrected() {
      const sel = this.store.selection;
      if (!sel) return;
      const ms = this.store.allMeasures()[sel.measureIndex];
      if (!ms) return;
      const ev = ms.events.find(e => e.id === sel.eventId);
      if (!ev) return;
      ev.provenance = ev.provenance || { source: "manual" };
      ev.provenance.reviewStatus = "verified";
      ev.provenance.reviewedByUser = true;
      if (ev.unknownText) ev.provenance.correctedValue = ev.unknownText;
      this.store.dirty = true;
      this.render();
      this.renderMarks();
    }
  }
  window.ScoreStudioSourcePanel = { SourcePanel };
})();
