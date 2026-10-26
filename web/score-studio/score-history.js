/* ScoreStudio Undo/Redo — 快照式歷史（§4/§6.2：完整 document 快照，不靠 DOM）
   標準 pre-mutation 模式：
   - 改動前：history.begin() 記下「改動前」快照到 base
   - 改動後：history.commit(label) 把 base 推入 past、清 future
   - undo：當前 doc 快照 → future；pop past 還原
   - redo：當前 doc 快照 → past；pop future 還原
*/
(function () {
  const MAX = 60;
  class History {
    constructor(store, onChange) {
      this.store = store; this.onChange = onChange;
      this.past = []; this.future = []; this.base = null;
    }
    _snap() { return JSON.stringify(this.store.doc); }
    begin() {
      // 只有尚未記錄 base 時記一次（一次改動一次 base）
      if (this.base == null) this.base = this._snap();
    }
    commit(label) {
      if (this.base != null) {
        this.past.push({ label, snap: this.base });
        if (this.past.length > MAX) this.past.shift();
        this.future.length = 0;
        this.base = null;
      }
      this.onChange && this.onChange();
    }
    canUndo() { return this.past.length > 0; }
    canRedo() { return this.future.length > 0; }
    undo() {
      if (!this.canUndo()) return false;
      this.future.push({ label: "redo", snap: this._snap() });
      const last = this.past.pop();
      this.store.doc = JSON.parse(last.snap);
      this.store.dirty = true;
      this.onChange && this.onChange();
      return true;
    }
    redo() {
      if (!this.canRedo()) return false;
      this.past.push({ label: "undo", snap: this._snap() });
      const last = this.future.pop();
      this.store.doc = JSON.parse(last.snap);
      this.store.dirty = true;
      this.onChange && this.onChange();
      return true;
    }
    clear() { this.past = []; this.future = []; this.base = null; }
  }
  window.ScoreStudioHistory = { History };
})();
