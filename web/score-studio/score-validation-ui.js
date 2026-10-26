/* ScoreStudio 拍數驗證 UI（§14）— 小節狀態＋未解決 OMR＋可匯出報告 */
(function () {
  class ValidationUI {
    constructor(store, api, docId) {
      this.store = store; this.api = api; this.docId = docId;
    }
    async run() {
      try {
        const rep = await this.api.doc(this.docId).validate();
        this.store.validation = rep;
        this._renderStatuses(rep);
        this._renderChips(rep);
        return rep;
      } catch (e) {
        if (e.status === 409) return null; // 版本已變，下次重存後再驗
        this.store.validation = { summary: "驗證失敗：" + e.message, statuses: {}, checks: [] };
        this._renderStatuses(this.store.validation);
        return null;
      }
    }
    _renderStatuses(rep) {
      const el = document.getElementById("ss-validation");
      const statuses = window.ScoreStudioStore.statusesOf(rep);
      const labels = { valid: "ok", underfilled: "short", overflow: "over", unresolved_omr: "unres", unknown_duration: "unres" };
      let html = "";
      for (const [mi, s] of Object.entries(statuses)) {
        if (s !== "valid") html += `<span class="ss-chip ${labels[s] || s}" title="小節 ${+mi + 1}">小節${+mi + 1}:${labels[s] || s}</span>`;
      }
      el.innerHTML = html || '<span class="ss-faint">全部小節拍數正常</span>';
    }
    _renderChips(rep) {
      const el = document.getElementById("ss-validation-summary");
      if (!rep || !rep.checks) return;
      const n = rep.checks.filter(c => c.status !== "valid").length;
      el.textContent = n ? `${n} 小節有拍數問題` : "拍數全數正常";
      el.style.color = n ? "var(--bad)" : "var(--good)";
    }
    // 匯出前問題報告（§15.3）
    reportIssues() {
      const rep = this.store.validation;
      if (!rep || !rep.checks) return [];
      const items = [];
      for (const c of rep.checks) {
        if (c.status === "valid" && !c.issues.length) continue;
        const kinds = (c.issues || []).map(i => i.kind).join(", ");
        items.push({ measure: c.measure - 1, status: c.status, reasons: kinds || (c.status !== "valid" ? c.status : "") });
      }
      return items;
    }
  }
  window.ScoreStudioValidationUI = { ValidationUI };
})();
