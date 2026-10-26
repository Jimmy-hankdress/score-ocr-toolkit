/* ScoreStudio 狀態儲存 — 所有狀態來自載入的 document（§6.2 可序列化的核心）
   對齊真實 ScoreDocument v1（app/scorestudio/__init__.py）：
   - 版本鎖在 doc.audit.revision
   - scoreSettings = {key:{tonic,mode,display}, timeSignature:{beats,beatType}, tempo:{bpm,...}, ticksPerQuarter}
   - 事件時值在 ev.notation.duration + ev.notation.dots；ev.durationTicks 已算好
   - 和弦/歌詞是事件的子物件 ev.chords[]/ev.lyrics[]
*/
(function () {
  const DURATION_TICKS = { whole: 1920, half: 960, quarter: 480, eighth: 240, sixteenth: 120, thirtysecond: 60 };
  const TICKS_PER_QUARTER = 480;

  function measureTicks(doc) {
    // 4/4 = 1920 ticks（一整小節）。依拍號 × (tpq*4 / beatType)
    const s = doc && doc.scoreSettings;
    if (!s || !s.timeSignature) return TICKS_PER_QUARTER * 4;
    const ts = s.timeSignature;
    const beats = ts.beats || 4, bt = ts.beatType || 4;
    return beats * s.ticksPerQuarter * 4 / bt;
  }

  class Store {
    constructor() {
      this.docId = null;
      this.doc = null;
      this.selection = null;      // { measureIndex, eventId }（measureIndex 0-based）
      this.cursor = { measureIndex: 0, tick: 0 };
      this.mode = "note";
      this.duration = "quarter";
      this.settings = { zoom: 1.0, countIn: 2 };
      this.dirty = false;
      this.saveState = "idle";    // idle|saving|saved|error|conflict
      this.validation = null;     // {ok, summary, checks[], exportWarnings[]}
      this.listeners = [];
    }
    get revision() {
      return this.doc && this.doc.audit && this.doc.audit.revision;
    }
    set revision(v) {
      if (this.doc && this.doc.audit) this.doc.audit.revision = v;
    }
    subscribe(fn) { this.listeners.push(fn); }
    emit() { this.listeners.forEach(fn => fn()); }
    firstPart() { return this.doc && this.doc.parts && this.doc.parts[0]; }
    allMeasures() {
      const p = this.firstPart();
      return p ? p.measures : [];
    }
    measureTicks() { return measureTicks(this.doc); }
    tickWidthPx(ev) {
      const z = this.settings.zoom;
      const ticks = ev.durationTicks || (DURATION_TICKS[ev.notation && ev.notation.duration] || 480);
      return (ticks / TICKS_PER_QUARTER) * 34 * z; // 四分音符=34px 基礎
    }
    measureWidthPx(m) {
      const base = m.events.reduce((s, e) => s + ((e.durationTicks || 480) / TICKS_PER_QUARTER), 0) * 34;
      return Math.max(120, base + 30) * this.settings.zoom;
    }
    findEvent(eventId) {
      const ms = this.allMeasures();
      for (let i = 0; i < ms.length; i++) {
        const ev = ms[i].events.find(e => e.id === eventId);
        if (ev) return { mi: i, event: ev };
      }
      return null;
    }
  }

  // validator 回傳 { checks: [{measure(1-based), status, ...}] }；轉成 0-based 索引 map
  function statusesOf(rep) {
    const map = {};
    if (rep && Array.isArray(rep.checks)) for (const c of rep.checks) map[c.measure - 1] = c.status;
    return map;
  }

  window.ScoreStudioStore = { Store, statusesOf, DURATION_TICKS, TICKS_PER_QUARTER, measureTicks };
})();
