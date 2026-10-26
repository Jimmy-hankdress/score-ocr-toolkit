/* ScoreStudio 播放（§10）— 本地 WebAudio 合成，不下載音色（§1.2 離線）
   對齊真實 schema：tempo=bpm、pitch:{degree:int, accidental:int(+1/-1/0), octave:int}，
   時值 ticksPerQuarter=480；MIDI 音高依 doc.scoreSettings.key.tonic 計算。
*/
(function () {
  const { _DEGREE_SEMITONE = { 1: 0, 2: 2, 3: 4, 4: 5, 5: 7, 6: 9, 7: 11 },
          _TONIC_TO_MIDI = { C: 60, G: 62, D: 64, A: 66, E: 68, B: 70, "F#": 64, F: 59, Bb: 66, Eb: 63, Ab: 58, Db: 56 } } = {};
  const mtof = m => 440 * Math.pow(2, (m - 69) / 12);

  class Playback {
    constructor(store, render, focusMeasure) {
      this.store = store; this.render = render; this.focusMeasure = focusMeasure;
      this.ctx = null; this.playing = false; this.practice = false;
      this.countIn = 2;
      this.timer = null;
      this._bind();
    }
    _bind() {
      const playBtn = document.getElementById("ss-play");
      if (playBtn) playBtn.addEventListener("click", () => this.toggle());
      const pBtn = document.getElementById("ss-practice");
      if (pBtn) pBtn.addEventListener("click", () => {
        this.practice = !this.practice;
        pBtn.classList.toggle("active", this.practice);
      });
      const ci = document.getElementById("ss-countin");
      if (ci) ci.addEventListener("change", e => { this.countIn = +e.target.value; });
    }
    _ensureCtx() { if (!this.ctx) this.ctx = new (window.AudioContext || window.webkitAudioContext)(); }
    _bpm() {
      const t = this.store.doc && this.store.doc.scoreSettings && this.store.doc.scoreSettings.tempo;
      return (t && t.bpm) || 80;
    }
    _tonicMidi() {
      const key = this.store.doc && this.store.doc.scoreSettings && this.store.doc.scoreSettings.key;
      return (key && _TONIC_TO_MIDI[key.tonic]) || 60;
    }
    _freq(ev) {
      const p = ev.pitch;
      if (!p) return mtof(60);
      const deg = _DEGREE_SEMITONE[p.degree] != null ? _DEGREE_SEMITONE[p.degree] : 0;
      const midi = this._tonicMidi() + deg + (p.accidental || 0) + (p.octave || 0) * 12;
      return mtof(midi);
    }
    _tickSec(ticks) {
      return ticks / 480 * (60 / this._bpm());
    }
    _playTick(durationTicks, freq, startSec, t0) {
      const ctx = this.ctx;
      const dur = this._tickSec(durationTicks);
      const osc = ctx.createOscillator();
      const gain = ctx.createGain();
      osc.type = "triangle";
      osc.frequency.value = freq;
      gain.gain.setValueAtTime(0.16, t0 + startSec);
      gain.gain.exponentialRampToValueAtTime(0.001, t0 + startSec + dur);
      osc.connect(gain); gain.connect(ctx.destination);
      osc.start(t0 + startSec);
      osc.stop(t0 + startSec + dur);
    }
    toggle() { if (this.playing) this.stop(); else this.play(); }
    play() {
      if (this.playing) return;
      this._ensureCtx();
      if (this.ctx.resume) this.ctx.resume();
      this.playing = true;
      const btn = document.getElementById("ss-play");
      if (btn) btn.textContent = "⏸ 停止";
      const msList = this.store.allMeasures();
      let idx = Math.max(0, this.practice ? this.store.cursor.measureIndex - this.countIn : this.store.cursor.measureIndex);
      const t0 = this.ctx.currentTime;
      const self = this;
      const step = () => {
        if (!self.playing || idx >= msList.length) { self.stop(); return; }
        const ms = msList[idx];
        self.focusMeasure && self.focusMeasure(idx);
        const cp = document.getElementById("ss-cursor-pos");
        if (cp) cp.textContent = `小節 ${(ms.number || idx + 1)}`;
        let sec = 0;
        for (const ev of ms.events) {
          const durSec = self._tickSec(ev.durationTicks || 480);
          if (self.practice) {
            self._playTick(ev.durationTicks || 480, 880, sec, t0); // 節拍器
          } else if (ev.type === "note" && ev.pitch && ev.pitch.degree !== 0) {
            self._playTick(ev.durationTicks || 480, self._freq(ev), sec, t0);
          }
          sec += durSec;
        }
        idx += 1;
        self.timer = setTimeout(step, sec * 1000 + 30);
      };
      step();
    }
    stop() {
      this.playing = false;
      clearTimeout(this.timer);
      const btn = document.getElementById("ss-play");
      if (btn) btn.textContent = "▶ 播放";
    }
  }
  window.ScoreStudioPlayback = { Playback };
})();
