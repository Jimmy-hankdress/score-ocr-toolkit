/* ScoreStudio 整排行編輯器 — 簡譜行／歌詞行「小節整排可輸入」（對齊和弦整排槽）
   每個小節一組：簡譜行（空格分隔，逐拍對應事件）＋歌詞行（空格分隔音節）。
   與 SVG 畫布雙向同步：change/失焦即提交（setMeasureNotesRow/setMeasureLyricsRow），
   Enter 提交並跳下一小節同類欄，支援整篇批量輸入。
   DOM 快取：input 元素固定（只更新值、不重建），避免 commit 重繪竊取焦點。
   誠實原則：非數字 token（如 OMR 的 "G？"）保留為 unknown，不臆測。
*/
(function () {
  const { notesRowText, lyricsRowText } = window.ScoreStudioInteraction;
  const PER_ROW = 4;

  class RowEditor {
    constructor(store, interaction) {
      this.store = store;
      this.in = interaction;
      this.el = document.getElementById("ss-rows");
      this._cells = new Map();   // mi -> { num, notes, lyrics, box }
      this._lines = [];
      this._bind();
    }
    _bind() {
      if (!this.el) return;
      this.el.addEventListener("change", e => {
        const inp = e.target;
        if (!inp || !inp.dataset || inp.dataset.kind == null) return;
        this._sync(inp);
      });
      this.el.addEventListener("keydown", e => this._onKey(e));
      // 焦點離開行輸入（點 SVG、點其他欄、切模式）時：同步離開中的欄
      document.addEventListener("focusout", e => {
        const inp = e.target;
        if (inp && inp.dataset && inp.dataset.kind != null && this.el && this.el.contains(inp)) {
          this._sync(inp);
        }
      });
    }
    _sync(inp) {
      if (!inp || !inp.dataset || inp.dataset.kind == null) return;
      const mi = +inp.dataset.mi;
      const ms = this.store.allMeasures()[mi];
      if (!ms) return;
      const cur = inp.dataset.kind === "notes" ? notesRowText(ms) : lyricsRowText(ms);
      if (inp.value === cur) return;   // 值未變動：不提交、不污染歷史
      if (inp.dataset.kind === "notes") this.in.setMeasureNotesRow(mi, inp.value);
      else this.in.setMeasureLyricsRow(mi, inp.value);
      // setMeasure*Row 已觸發 refreshAll（SVG 重繪＋本 refresh）；input 元素不重建，焦點安全
    }
    _onKey(e) {
      if (e.key !== "Enter") return;
      const inp = e.target;
      if (!inp || inp.tagName !== "INPUT" || inp.dataset.kind == null) return;
      e.preventDefault();
      this._sync(inp);
      const n = this.store.allMeasures().length;
      if (!n) return;
      const nextMi = ((+inp.dataset.mi) + 1) % n;
      const next = this._cells.get(nextMi);
      const target = next ? (inp.dataset.kind === "notes" ? next.notes : next.lyrics) : null;
      (target || inp).focus();
    }
    // 結構變動時呼叫：建立/移除 input 快取；每 frame 只同步值、不重建焦點中的輸入
    refresh() {
      if (!this.el) return;
      const msList = this.store.allMeasures();
      const activeMi = this.store.cursor ? this.store.cursor.measureIndex : -1;

      if (this._cells.size !== msList.length) {
        // 小節數變動 → 重建整列
        this._cells = new Map();
        this._lines = [];
        this.el.innerHTML = "";
        let line = null;
        for (let mi = 0; mi < msList.length; mi++) {
          if (!line || mi % PER_ROW === 0) {
            line = document.createElement("div");
            line.className = "ss-rowline";
            this.el.appendChild(line);
            this._lines.push(line);
          }
          const box = document.createElement("div");
          box.className = "ss-rowcell";
          box.dataset.mi = mi;
          const num = document.createElement("span");
          num.className = "ss-rownum";
          num.textContent = msList[mi].number != null ? msList[mi].number : mi + 1;
          const notes = document.createElement("input");
          notes.className = "ss-notes-input";
          notes.dataset.mi = mi; notes.dataset.kind = "notes";
          notes.placeholder = "簡譜：5 6 1. 2（空格分隔，Enter 下一節）";
          const lyrics = document.createElement("input");
          lyrics.className = "ss-lyric-input";
          lyrics.dataset.mi = mi; lyrics.dataset.kind = "lyrics";
          lyrics.placeholder = "歌詞：所 以（空格分隔，Enter 下一節）";
          box.appendChild(num); box.appendChild(notes); box.appendChild(lyrics);
          line.appendChild(box);
          this._cells.set(mi, { num, notes, lyrics, box });
        }
      }

      // 值同步：只更新「未被聚焦」的 input（焦點中的保留使用者輸入）
      for (let mi = 0; mi < msList.length; mi++) {
        const c = this._cells.get(mi);
        if (!c) continue;
        c.num.textContent = msList[mi].number != null ? msList[mi].number : mi + 1;
        c.box.classList.toggle("active", mi === activeMi);
        if (document.activeElement !== c.notes) c.notes.value = notesRowText(msList[mi]);
        if (document.activeElement !== c.lyrics) c.lyrics.value = lyricsRowText(msList[mi]);
      }

      if (!msList.length) {
        this.el.innerHTML = '<div class="ss-faint ss-rowempty">尚無小節。用左側「＋ 新增小節」建立後，此處即可整排輸入簡譜與歌詞。</div>';
      }
    }
    renderRows() { this.refresh(); }   // 舊名稱相容
  }

  window.ScoreStudioRowEditor = { RowEditor };
})();
