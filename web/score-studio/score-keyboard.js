/* ScoreStudio 鍵盤層（§8.3 鍵盤表）— 所有改動走 Interaction，不直接改資料
   Q W E R T = 全/二分/四分/八分/十六分；. = 附點；- = 延音/tie
   1-7 = 音級；0 = 休止；# / b / n = 升/降/還原
   Left/Right = 前/後小節；PageUp/PageDown = 跳小節；Up/Down = 八度；Shift+Up/Down = 半音
   Space = 播放；Ctrl+Z 復原；Ctrl+Y / Ctrl+Shift+Z 重做；Ctrl+S 儲存；Ctrl+= / Ctrl+- 縮放；Tab 下一拍
   Escape = 選取模式
*/
(function () {
  const DUR_MAP = { q: "whole", w: "half", e: "quarter", r: "eighth", t: "sixteenth" };

  class Keyboard {
    constructor(store, interaction, history, render, onZoom) {
      this.store = store; this.in = interaction; this.hist = history;
      this.render = render; this.onZoom = onZoom;
      window.addEventListener("keydown", e => this._onKey(e));
    }
    _mi() {
      const arr = this.store.allMeasures();
      return Math.min(this.store.cursor.measureIndex, Math.max(0, arr.length - 1));
    }
    _curAcc() {
      const ms = this.store.allMeasures()[this._mi()];
      const sel = this.store.selection;
      let ev = null;
      if (ms && sel && sel.measureIndex === this._mi()) ev = ms.events.find(x => x.id === sel.eventId);
      if (!ev) ev = ms && ms.events.find(x => x.type === "note");
      return (ev && ev.pitch && ev.pitch.accidental) || 0;
    }
    _onKey(e) {
      if (e.target && (e.target.tagName === "INPUT" || e.target.tagName === "TEXTAREA")) return;
      const k = e.key;
      const ctrl = e.ctrlKey || e.metaKey;

      // Ctrl 組合鍵
      if (ctrl && k.toLowerCase() === "z") {
        e.preventDefault();
        if (e.shiftKey) { if (this.hist.redo()) { this.render(); this.in.validate(); } }
        else { if (this.hist.undo()) { this.render(); this.in.validate(); } }
        return;
      }
      if (ctrl && k.toLowerCase() === "y") { e.preventDefault(); if (this.hist.redo()) { this.render(); this.in.validate(); } return; }
      if (ctrl && k.toLowerCase() === "s") { e.preventDefault(); window.ScoreStudioMain && window.ScoreStudioMain.save(); return; }
      if (ctrl && (k === "=" || k === "+")) { e.preventDefault(); this.onZoom(this.store.settings.zoom + 0.2); return; }
      if (ctrl && k === "-") { e.preventDefault(); this.onZoom(this.store.settings.zoom - 0.2); return; }

      // 游標 / 八度 / 半音
      if (k === "ArrowLeft") { e.preventDefault(); this._page(-1); return; }
      if (k === "ArrowRight") { e.preventDefault(); this._page(1); return; }
      if (k === "PageUp") { e.preventDefault(); this._page(-1); return; }
      if (k === "PageDown") { e.preventDefault(); this._page(1); return; }
      if (k === "ArrowUp") { e.preventDefault(); if (e.shiftKey) this.in.adjustSemitone(this._mi(), 1); else this.in.adjustOctave(this._mi(), 1); return; }
      if (k === "ArrowDown") { e.preventDefault(); if (e.shiftKey) this.in.adjustSemitone(this._mi(), -1); else this.in.adjustOctave(this._mi(), -1); return; }
      if (k === "Home") { this.store.cursor = { measureIndex: 0, tick: 0 }; this.render(); return; }
      if (k === "End") { const a = this.store.allMeasures(); this.store.cursor = { measureIndex: Math.max(0, a.length - 1), tick: 0 }; this.render(); return; }
      if (k === "Tab") { e.preventDefault(); this._advance(1); return; }
      if (k === " ") { e.preventDefault(); window.ScoreStudioMain && window.ScoreStudioMain.togglePlay(); return; }
      if (k === "Escape") { this.store.mode = "select"; this._syncModes(); this.render(); return; }
      // 模式切換（§7）：N 音符 / L 歌詞 / C 和弦 / P 標注 / V 選取
      if (!ctrl && !e.shiftKey) {
        const modeMap = { n: "note", l: "lyric", c: "chord", p: "anno", v: "select" };
        const m = modeMap[k.toLowerCase()];
        if (m && e.key.length === 1) { this.store.mode = m; this._syncModes(); this.render(); return; }
      }

      // 刪除
      if (k === "Backspace" || k === "Delete") { e.preventDefault(); this.in.deleteSelected(); return; }

      // 時值 Q/W/E/R/T
      const dl = k.toLowerCase();
      if (DUR_MAP[dl] && !ctrl && !e.shiftKey && !e.altKey) {
        this.store.duration = DUR_MAP[dl];
        this._syncDurations();
        this.in.setEventDuration(this._mi(), this.store.duration);
        return;
      }
      // 附點「.」／延音「-」
      if (k === ".") { e.preventDefault(); this.in.toggleDot(this._mi()); return; }
      if (k === "-") { e.preventDefault(); this.in.setTie(this._mi(), !this._curTie()); return; }

      // 升降號：# 或 Shift+3 = 升；b / s = 降；n / = = 還原
      const isSharp = k === "#" || (k === "3" && e.shiftKey);
      const isFlat = (k === "b" || k === "s") && !ctrl;
      const isNat = (k === "n" || k === "=") && !ctrl;
      if (isSharp || isFlat || isNat) {
        const target = isSharp ? 1 : isFlat ? -1 : 0;
        this.in.adjustSemitone(this._mi(), target - this._curAcc());
        return;
      }

      // 音級 1-7；0 = 休止
      if (/^[1-7]$/.test(k)) {
        this.in.setEventPitch(this._mi(), +k, this._curAcc(), 0);
        this._advance(1);
        return;
      }
      if (k === "0") {
        this.in.insertRest(this._mi());
        this._advance(1);
        return;
      }
    }
    _curTie() {
      const ms = this.store.allMeasures()[this._mi()];
      const sel = this.store.selection;
      let ev = null;
      if (ms && sel && sel.measureIndex === this._mi()) ev = ms.events.find(x => x.id === sel.eventId);
      if (!ev) ev = ms && ms.events.find(x => x.type === "note");
      return !!(ev && ev.notation && (ev.notation.tieStart || ev.notation.tieStop));
    }
    _advance(steps) {
      const arr = this.store.allMeasures();
      if (!arr.length) return;
      const need = this.store.measureTicks();
      let mi = this.store.cursor.measureIndex;
      let tick = this.store.cursor.tick + steps * 480;
      while (tick >= need && mi < arr.length - 1) { tick -= need; mi += 1; }
      if (mi >= arr.length) { mi = arr.length - 1; tick = 0; }
      this.store.cursor = { measureIndex: mi, tick };
      this.render();
    }
    _page(dir) {
      const arr = this.store.allMeasures();
      this.store.cursor.measureIndex = Math.max(0, Math.min(arr.length - 1, this.store.cursor.measureIndex + dir));
      this.store.cursor.tick = 0;
      this.render();
    }
    _syncModes() {
      document.querySelectorAll(".ss-mode").forEach(b => b.classList.toggle("active", b.dataset.mode === this.store.mode));
    }
    _syncDurations() {
      document.querySelectorAll(".ss-duration-group button").forEach(b => b.classList.toggle("active", b.dataset.dur === this.store.duration));
    }
  }
  window.ScoreStudioKeyboard = { Keyboard };
})();
