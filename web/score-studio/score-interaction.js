/* ScoreStudio 互動 — 滑鼠選取/插入/事件 CRUD（§7/§8.4/§9）
   對齊真實 schema 與 pre-mutation 歷史：
   - 改動前 this.history.begin()（記改動前快照）
   - 改動後 this._commit(label)（把 base 推入 past + render/validate/props）
*/
(function () {
  const DURATION_TICKS = { whole: 1920, half: 960, quarter: 480, eighth: 240, sixteenth: 120, thirtysecond: 60 };
  const uid = p => p + "_" + Math.random().toString(16).slice(2, 10) + Date.now().toString(16);
  const durTicks = (name, dots) => {
    let t = DURATION_TICKS[name] != null ? DURATION_TICKS[name] : DURATION_TICKS.quarter;
    if (dots) t = t + t / 2;
    return Math.round(t);
  };
  const prov = () => ({ source: "manual", page: null, bbox: null, rawToken: "", confidence: null,
                        reviewStatus: "needs_review", reviewReason: "manual" });

  // §整排輸入：小節「簡譜行／歌詞行」字串 ↔ 事件陣列 互轉
  // 簡譜行 token：[#|b]數字 + 附點(.) + 延音(-)；未知 token（以 ? 或非數字開頭）保留為 unknown 事件
  function notesRowText(ms) {
    return (ms.events || []).map(ev => {
      if (ev.type === "unknown") return "?" + (ev.unknownText || "");
      const p = ev.pitch || {};
      const deg = p.degree != null ? p.degree : 0;
      const acc = p.accidental === 1 ? "#" : p.accidental === -1 ? "b" : "";
      const dots = ev.notation && ev.notation.dots ? new Array(ev.notation.dots + 1).join(".") : "";
      const tie = ev.notation && (ev.notation.tieStart || ev.notation.tieStop) ? "-" : "";
      return acc + deg + dots + tie;
    }).join(" ");
  }
  function lyricsRowText(ms) {
    return (ms.events || []).map(ev => (ev.lyrics && ev.lyrics[0] && ev.lyrics[0].text) || "").join(" ");
  }
  function parseNoteToken(tok, defaultDur) {
    const m = String(tok).match(/^([#b]?)([0-7])(\.*)/);
    const degree = m ? +m[2] : 0;
    const accidental = m ? (m[1] === "#" ? 1 : m[1] === "b" ? -1 : 0) : 0;
    const dots = m ? (m[3] ? m[3].length : 0) : 0;
    const tie = String(tok).indexOf("-") >= 0;
    const base = durTicks(defaultDur, 0);
    let t = base; for (let d = 0; d < dots; d++) t *= 1.5; if (tie) t *= 2;
    return { degree, accidental, dots, tie, durationName: defaultDur, durationTicks: Math.round(t) };
  }

  class Interaction {
    constructor(store, history, render, validate) {
      this.store = store; this.history = history;
      this.render = render; this.validate = validate;
      this._bind();
    }
    _commit(label) {
      this.history.commit(label);
      this.store.dirty = true;
      this.render();
      this.validate();
      this._props();
    }
    _bind() {
      const canvas = document.getElementById("ss-canvas");
      canvas.addEventListener("click", e => {
        const t = e.target;
        if (!t || !t.dataset || !(t.classList)) return;
        // §6.6 和弦槽（頂端整排）：點選該槽以編輯
        if (t.closest && t.closest(".ss-chord-slot")) {
          const slot = t.closest(".ss-chord-slot");
          const mi = +slot.dataset.measureIndex;
          const eid = slot.dataset.eventId;
          const ci = slot.dataset.chordIndex != null ? +slot.dataset.chordIndex : 0;
          if (slot.classList.contains("empty")) this.addChordSlot(mi, 0, "");
          else this.selectChordSlot(mi, eid, ci);
          return;
        }
        if (t.dataset.eventId && t.classList.contains("ss-note")) {
          this.select(+t.dataset.measureIndex, t.dataset.eventId);
        } else if (t.classList.contains("ss-insert")) {
          this.insertAt(+t.dataset.measureIndex, +t.dataset.tick || 0);
        } else if (t.dataset.measureIndex != null) {
          this.store.cursor = { measureIndex: +t.dataset.measureIndex, tick: 0 };
          this.render();
        }
      });
    }
    select(mi, eventId) {
      this.store.selection = { measureIndex: mi, eventId };
      this.render();
      this._props();
    }
    _target(mi) {
      const ms = this.store.allMeasures()[mi];
      if (!ms) return null;
      if (this.store.selection && this.store.selection.measureIndex === mi && this.store.selection.eventId) {
        const ev = ms.events.find(e => e.id === this.store.selection.eventId);
        if (ev && (ev.type === "note" || ev.type === "rest")) return ev;
      }
      return ms.events.find(e => e.type === "note" || e.type === "rest") || null;
    }
    _newNote(mi, tick, degree) {
      return {
        id: uid("ev"), type: degree === 0 ? "rest" : "note", startTick: tick || 0,
        durationTicks: durTicks(this.store.duration, 0),
        durationStatus: "reviewed",
        pitch: { degree: degree || 1, accidental: 0, octave: 0, midi: null },
        notation: { duration: this.store.duration, dots: 0, tieStart: false, tieStop: false },
        unknownText: "", lyrics: [], chords: [], annotations: [],
        provenance: prov(),
      };
    }
    insertAt(mi, tick) {
      if (this.store.mode === "chord") { this.addChordSlot(mi, tick); return; }
      if (this.store.mode === "lyric") { const t = this._target(mi); if (t) this.setEventLyric(mi, ""); return; }
      const ms = this.store.allMeasures()[mi];
      if (!ms) return;
      this.history.begin();
      const note = this._newNote(mi, tick, 1);
      ms.events.push(note);
      this._commit("note_insert");
      this.store.cursor = { measureIndex: mi, tick: (tick || 0) + note.durationTicks };
      this.select(mi, note.id);
    }
    setEventPitch(mi, degree, accidental, octave) {
      const ms = this.store.allMeasures()[mi];
      if (!ms) return;
      let target = this._target(mi);
      this.history.begin();
      if (!target) {
        const startTick = this.store.cursor.measureIndex === mi ? this.store.cursor.tick : 0;
        target = this._newNote(mi, startTick, degree);
        ms.events.push(target);
      }
      target.type = degree === 0 ? "rest" : "note";
      target.pitch = { degree, accidental: accidental || 0, octave: octave || 0, midi: null };
      target.durationStatus = "reviewed";
      target.unknownText = "";
      target.notation = target.notation || { duration: this.store.duration, dots: 0, tieStart: false, tieStop: false };
      this._commit("pitch_set");
      this.select(mi, target.id);
    }
    adjustOctave(mi, delta) {
      const ms = this.store.allMeasures()[mi]; if (!ms) return;
      const target = this._target(mi); if (!target || !target.pitch) return;
      this.history.begin();
      target.pitch.octave = (target.pitch.octave || 0) + delta;
      this._commit("octave_adjust");
      this.select(mi, target.id);
    }
    adjustSemitone(mi, delta) {
      const ms = this.store.allMeasures()[mi]; if (!ms) return;
      const target = this._target(mi); if (!target || !target.pitch) return;
      this.history.begin();
      target.pitch.accidental = (target.pitch.accidental || 0) + delta;
      this._commit("semitone_adjust");
      this.select(mi, target.id);
    }
    setEventDuration(mi, durationName, dotted) {
      const ms = this.store.allMeasures()[mi]; if (!ms) return;
      const target = this._target(mi); if (!target) return;
      this.history.begin();
      target.notation = target.notation || { duration: "quarter", dots: 0, tieStart: false, tieStop: false };
      target.notation.duration = durationName;
      if (dotted !== undefined) target.notation.dots = dotted ? 1 : 0;
      target.durationTicks = durTicks(durationName, target.notation.dots);
      target.durationStatus = "reviewed";
      this._commit("duration_set");
      this.select(mi, target.id);
    }
    toggleDot(mi) {
      const ms = this.store.allMeasures()[mi]; if (!ms) return;
      const target = this._target(mi); if (!target || !target.notation) return;
      this.history.begin();
      target.notation.dots = target.notation.dots ? 0 : 1;
      target.durationTicks = durTicks(target.notation.duration, target.notation.dots);
      target.durationStatus = "reviewed";
      this._commit("dot_toggle");
      this.select(mi, target.id);
    }
    setTie(mi, on) {
      const ms = this.store.allMeasures()[mi]; if (!ms) return;
      const target = this._target(mi); if (!target) return;
      this.history.begin();
      target.notation = target.notation || { duration: "quarter", dots: 0, tieStart: false, tieStop: false };
      target.notation.tieStart = on; target.notation.tieStop = on;
      const base = durTicks(target.notation.duration, target.notation.dots);
      target.durationTicks = on ? base * 2 : base;
      this._commit("tie_set");
      this.select(mi, target.id);
    }
    insertRest(mi) {
      const ms = this.store.allMeasures()[mi]; if (!ms) return;
      this.history.begin();
      const startTick = this.store.cursor.measureIndex === mi ? this.store.cursor.tick : 0;
      const rest = this._newNote(mi, startTick, 0);
      ms.events.push(rest);
      this._commit("rest_insert");
      this.store.cursor = { measureIndex: mi, tick: startTick + rest.durationTicks };
      this.select(mi, rest.id);
    }
    setEventChord(mi, rawText, chordIndex) {
      const ms = this.store.allMeasures()[mi]; if (!ms) return;
      const target = this._target(mi); if (!target) return;
      target.chords = target.chords || [];
      this.history.begin();
      if (rawText) {
        // 編輯指定槽；該槽不存在且 index=0 時才建（保持既有其他和弦槽不動）
        let c = target.chords[chordIndex || 0];
        if (!c) c = {
          id: uid("ch"), anchorType: "event", anchorId: target.id, offsetTick: 0,
          rawText: "", parsed: null, position: "above", transposeWithScore: true,
          provenance: { source: "manual", reviewStatus: "needs_review" },
        };
        c.anchorId = target.id; c.rawText = rawText; c.parsed = null; // §10.2 解析失敗保持 unknown
        target.chords[chordIndex || 0] = c;
      } else if (chordIndex != null) {
        // 只清指定槽（其他和弦保留）
        target.chords.splice(chordIndex, 1);
      } else {
        target.chords = [];
      }
      this._commit("chord_set");
      this.select(mi, target.id);
    }
    // 小節內追加一個新和弦槽（整排並列；附加到游標所在事件或該小節第一個音符）
    addChordSlot(mi, tick, rawText) {
      const ms = this.store.allMeasures()[mi]; if (!ms) return;
      let target = null;
      if (tick != null) {
        target = ms.events.find(e => tick >= e.startTick && tick < e.startTick + e.durationTicks);
      }
      if (!target) target = ms.events.find(e => e.type === "note" || e.type === "rest");
      if (!target) return;
      target.chords = target.chords || [];
      this.history.begin();
      target.chords.push({
        id: uid("ch"), anchorType: "event", anchorId: target.id, offsetTick: 0,
        rawText: rawText || "", parsed: null, position: "above", transposeWithScore: true,
        provenance: { source: "manual", reviewStatus: "needs_review" },
      });
      this._commit("chord_add");
      this.select(mi, target.id);
    }
    // 點到指法圖時：選取該槽（讓屬性面板顯示其編輯欄）
    selectChordSlot(mi, eventId, chordIndex) {
      this.store.selection = { measureIndex: mi, eventId, chordIndex };
      this.render();
      this._props();
    }
    deleteChordSlot(mi, chordIndex) {
      const ms = this.store.allMeasures()[mi]; if (!ms) return;
      const target = this._target(mi); if (!target) return;
      this.history.begin();
      (target.chords || []).splice(chordIndex, 1);
      this._commit("chord_delete");
      this.select(mi, target.id);
    }
    setEventLyric(mi, text) {
      const ms = this.store.allMeasures()[mi]; if (!ms) return;
      const target = this._target(mi); if (!target) return;
      this.history.begin();
      if (text) {
        const l = (target.lyrics && target.lyrics[0]) || {
          id: uid("lr"), verse: 1, label: "", text: "", syllabic: "single", extend: false,
          provenance: { source: "manual", reviewStatus: "needs_review" },
        };
        l.text = text;
        target.lyrics = [l];
      } else {
        target.lyrics = [];
      }
      this._commit("lyric_set");
      this.select(mi, target.id);
    }
    // §整排輸入：小節「簡譜行」整行覆寫 — 空格分隔 token → 事件
    // 保留既有事件的身份：第 i 個 token 對應第 i 個事件（改音級/臨時記號/附點/延音/休止），
    // token 比事件多 → 新增事件（接續 tick）；比事件少 → 尾部多餘事件移除（可復原）。
    setMeasureNotesRow(mi, text) {
      const ms = this.store.allMeasures()[mi]; if (!ms) return;
      const toks = String(text || "").trim().split(/\s+/).filter(Boolean);
      this.history.begin();
      const old = JSON.parse(JSON.stringify(ms.events));
      ms.events = [];
      let tick = 0;
      for (let i = 0; i < toks.length; i++) {
        const tok = toks[i];
        const prev = old[i];
        let ev;
        if (/^[#b]?\d/.test(tok)) {
          const p = parseNoteToken(tok, (prev && prev.notation && prev.notation.duration) || this.store.duration);
          ev = prev && prev.type !== "unknown" ? prev : this._newNote(mi, tick, p.degree);
          ev.type = p.degree === 0 ? "rest" : "note";
          ev.startTick = tick;
          ev.pitch = { degree: p.degree, accidental: p.accidental, octave: prev && prev.pitch ? prev.pitch.octave : 0, midi: null };
          ev.notation = { duration: p.durationName, dots: p.dots, tieStart: p.tie, tieStop: p.tie };
          ev.durationTicks = p.durationTicks;
          ev.durationStatus = "reviewed";
          ev.unknownText = "";
          ev.provenance = ev.provenance || prov();
          tick += ev.durationTicks;
        } else {
          // 非數字 token（如 OMR 的 "G？"）：誠實保留為 unknown，不臆測
          ev = prev && prev.type === "unknown" ? prev : {
            id: uid("ev"), type: "unknown", startTick: tick,
            durationTicks: this._durTicks(), durationStatus: "needs_review",
            unknownText: tok, lyrics: [], chords: [], annotations: [],
            provenance: prev && prev.provenance ? prev.provenance : prov(),
          };
          tick += ev.durationTicks;
        }
        ms.events.push(ev);
      }
      this._commit("notes_row_set");
      this.store.cursor = { measureIndex: mi, tick: 0 };
      this.store.selection = ms.events[0] ? { measureIndex: mi, eventId: ms.events[0].id, chordIndex: undefined } : null;
      this._props();
    }
    // §整排輸入：小節「歌詞行」整行覆寫 — 空格分隔音節 → 各事件 lyrics[0]
    setMeasureLyricsRow(mi, text) {
      const ms = this.store.allMeasures()[mi]; if (!ms) return;
      const toks = String(text || "").trim() ? String(text).trim().split(/\s+/) : [];
      this.history.begin();
      (ms.events || []).forEach((ev, i) => {
        const t = toks[i] || "";
        if (t) {
          const l = (ev.lyrics && ev.lyrics[0]) || {
            id: uid("lr"), verse: 1, label: "", text: "", syllabic: "single", extend: false,
            provenance: { source: "manual", reviewStatus: "needs_review" },
          };
          l.text = t;
          ev.lyrics = [l];
        } else {
          ev.lyrics = [];
        }
      });
      this._commit("lyric_row_set");
      this.store.selection = null;
    }
    _durTicks() {
      const D = { whole: 1920, half: 960, quarter: 480, eighth: 240, sixteenth: 120, thirtysecond: 60 };
      return D[this.store.duration] != null ? D[this.store.duration] : 480;
    }
    markReview(mi, status) {
      const ms = this.store.allMeasures()[mi]; if (!ms) return;
      const target = this._target(mi); if (!target) return;
      this.history.begin();
      target.provenance = target.provenance || prov();
      target.provenance.reviewStatus = status;
      target.provenance.reviewedByUser = true;
      this._commit("review_" + status);
      this.select(mi, target.id);
    }
    deleteSelected() {
      const sel = this.store.selection; if (!sel) return;
      const ms = this.store.allMeasures()[sel.measureIndex]; if (!ms) return;
      const i = ms.events.findIndex(e => e.id === sel.eventId);
      if (i < 0) return;
      this.history.begin();
      ms.events.splice(i, 1);
      this.store.selection = null;
      this._commit("event_delete");
    }
    moveNote(mi, tick) {
      const sel = this.store.selection; const ms = this.store.allMeasures()[mi];
      if (!sel || !ms) return;
      const ev = ms.events.find(e => e.id === sel.eventId); if (!ev) return;
      this.history.begin();
      ev.startTick = tick;
      this._commit("event_move");
      this.select(mi, ev.id);
    }
    addMeasure() {
      const p = this.store.firstPart(); if (!p) return;
      this.history.begin();
      const n = p.measures.length + 1;
      p.measures.push({
        id: uid("m"), number: n,
        timeSignatureOverride: null, keyOverride: null, rhythmGroupingOverride: null,
        events: [],
        barline: { left: "single", right: "single", repeatStart: false, repeatEnd: false, final: true },
        provenance: { source: "omr", page: null, bbox: null, confidence: 1.0 },
      });
      this._commit("measure_add");
      this.store.cursor = { measureIndex: n - 1, tick: 0 };
    }
    deleteLastMeasure() {
      const p = this.store.firstPart();
      if (p && p.measures.length > 1) {
        this.history.begin();
        p.measures.pop();
        this._commit("measure_delete");
      }
    }
    duplicateMeasure() {
      const sel = this.store.selection; const p = this.store.firstPart();
      if (!sel || !p) return;
      const src = p.measures[sel.measureIndex]; if (!src) return;
      this.history.begin();
      const dup = JSON.parse(JSON.stringify(src));
      dup.id = uid("m"); dup.number = p.measures.length + 1;
      dup.events.forEach(e => {
        e.id = uid("ev");
        (e.chords || []).forEach(c => { c.id = uid("ch"); c.anchorId = e.id; });
        (e.lyrics || []).forEach(l => { l.id = uid("lr"); });
      });
      p.measures.splice(sel.measureIndex + 1, 0, dup);
      this._commit("measure_duplicate");
    }
    _props() {
      const el = document.getElementById("ss-props");
      if (!el) return;
      const sel = this.store.selection;
      if (!sel) { el.innerHTML = '<p class="ss-faint">未選取事件。點音符以查看/編輯。</p>'; return; }
      const ms = this.store.allMeasures()[sel.measureIndex];
      const ev = ms && ms.events.find(e => e.id === sel.eventId);
      if (!ev) { el.innerHTML = '<p class="ss-faint">未選取事件。</p>'; return; }
      const conf = ev.provenance && ev.provenance.confidence;
      const acc = ev.pitch ? (ev.pitch.accidental === 1 ? "#" : ev.pitch.accidental === -1 ? "b" : "") : "";
      const lyricsTxt = (ev.lyrics && ev.lyrics.map(l => l.text).join(" ") || "");
      const dot = ev.notation && ev.notation.dots;
      // 和弦槽（整排並列）：逐槽顯示
      const chords = ev.chords || [];
      const selChordIdx = (this.store.selection && this.store.selection.chordIndex) || 0;
      const chordRows = chords.map((c, i) => `
        <div class="ss-prop-row"><span class="k">和弦${i + 1}</span>
          <input data-chord-edit="${i}" value="${(c.rawText || "").replace(/"/g, "&quot;")}" placeholder="如 C、F#m7/G" style="width:104px">
          <button class="ss-btn ss-chord-del" data-chord-del="${i}" title="刪此槽" style="padding:2px 6px">✕</button>
        </div>`).join("") || '<div class="ss-prop-row"><span class="k">和弦</span><span class="ss-faint">（無）</span></div>';
      el.innerHTML = `
        <div class="ss-prop-row"><span class="k">小節</span><span>${sel.measureIndex + 1}</span></div>
        <div class="ss-prop-row"><span class="k">類型</span><span>${ev.type}</span></div>
        <div class="ss-prop-row"><span class="k">音級</span><span>${ev.pitch ? acc + ev.pitch.degree : "—"}</span></div>
        <div class="ss-prop-row"><span class="k">時值</span><span>${(ev.notation && ev.notation.duration || "—") + (dot ? "•" : "")}</span></div>
        <div class="ss-prop-row"><span class="k">tick</span><span>${ev.startTick}</span></div>
        <div class="ss-prop-row"><span class="k">信心</span><span>${conf != null ? (conf * 100).toFixed(0) + "%" : "n/a"}</span></div>
        <div class="ss-prop-row"><span class="k">來源</span><span>${(ev.provenance && ev.provenance.source) || "—"}</span></div>
        <div class="ss-prop-row"><span class="k">審查</span><span>${(ev.provenance && ev.provenance.reviewStatus) || "—"}</span></div>
        ${chordRows}
        <button class="ss-btn ss-chord-add" style="width:100%;margin:4px 0">＋ 和弦（追加並列）</button>
        <div class="ss-prop-row"><label class="k">歌詞</label>
          <input id="ss-prop-lyric" value="${lyricsTxt.replace(/"/g, "&quot;")}" placeholder="歌詞" style="width:110px"></div>
        <div style="display:flex;gap:4px;margin-top:6px">
          <button class="ss-btn" id="ss-prop-del" style="flex:1">刪除事件</button>
          <button class="ss-btn" id="ss-prop-verify" style="flex:1" title="標記已人工確認">✓ 確認</button>
        </div>`;
      document.getElementById("ss-prop-del").onclick = () => this.deleteSelected();
      document.getElementById("ss-prop-verify").onclick = () => this.markReview(sel.measureIndex, "verified");
      document.getElementById("ss-prop-lyric").addEventListener("change", e => this.setEventLyric(sel.measureIndex, e.target.value.trim()));
      // 和弦逐槽編輯（change 保存）
      el.querySelectorAll("[data-chord-edit]").forEach(inp => {
        inp.addEventListener("change", e => {
          const i = +e.target.dataset.chordEdit;
          this.setEventChord(sel.measureIndex, e.target.value.trim(), i);
        });
      });
      el.querySelectorAll("[data-chord-del]").forEach(btn => {
        btn.addEventListener("click", () => this.deleteChordSlot(sel.measureIndex, +btn.dataset.chordDel));
      });
      const addBtn = el.querySelector(".ss-chord-add");
      if (addBtn) addBtn.addEventListener("click", () => this.addChordSlot(sel.measureIndex, null, ""));
    }
  }
  window.ScoreStudioInteraction = { Interaction, notesRowText, lyricsRowText, parseNoteToken };
})();
