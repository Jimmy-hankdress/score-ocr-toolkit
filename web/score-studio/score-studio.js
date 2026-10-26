/* ScoreStudio 主程式（§4/§5：先載入 document，再綁事件）
   對齊真實契約：
   - 版本鎖 doc.audit.revision；PUT {expectedRevision, document} → {ok, revision, validation}
   - scoreSettings.key.tonic / timeSignature{beats,beatType} / tempo.bpm
   - 快照：POST /snapshot {note} → {ok, snapshot:name}；GET /history → {snapshots:[{name,ts}]}
   - 還原：POST /restore/{name} → {ok, revision}
   - 舊版：/editor/legacy/{docId}
*/
(function () {
  const { api } = window.ScoreStudioAPI;
  const { Store } = window.ScoreStudioStore;
  const { History } = window.ScoreStudioHistory;
  const { Interaction } = window.ScoreStudioInteraction;
  const { RowEditor } = window.ScoreStudioRowEditor;
  const { Keyboard } = window.ScoreStudioKeyboard;
  const { SVGRenderer } = window.ScoreStudioRenderer;
  const { Playback } = window.ScoreStudioPlayback;
  const { SourcePanel } = window.ScoreStudioSourcePanel;
  const { ValidationUI } = window.ScoreStudioValidationUI;

  const params = new URLSearchParams(location.search);
  const pathMatch = location.pathname.match(/\/editor\/studio\/([^/?#]+)/);
  let docId = params.get("doc") || params.get("project") || (pathMatch ? decodeURIComponent(pathMatch[1]) : null);

  const store = new Store();
  store.docId = docId;
  const history = new History(store, null);
  const renderer = new SVGRenderer(store);
  let validationUI = new ValidationUI(store, api, docId);
  let rowEditor = null;
  let autoSaveTimer = null;

  // SVG＋整排行編輯器同步刷新（任何 render 路徑都用此函式）
  function refreshAll() {
    renderer.render();
    if (rowEditor) rowEditor.renderRows();
  }

  function onDirty() {
    if (autoSaveTimer) clearTimeout(autoSaveTimer);
    autoSaveTimer = setTimeout(save, 1000); // §17.1 自動儲存
  }

  async function save(manual) {
    if (!store.doc) return;
    setSaveState("saving");
    try {
      const r = await api.doc(docId).putScore(store.doc, store.revision);
      store.revision = r.revision;
      store.dirty = false;
      setSaveState("saved");
      await validationUI.run();
    } catch (e) {
      if (e.status === 409) {
        setSaveState("conflict");
        showConflict(e.actualRevision);
      } else {
        setSaveState("error", e.message);
      }
    }
  }

  function setSaveState(s, msg) {
    const bar = document.getElementById("ss-save-state");
    const top = document.getElementById("ss-saved-state");
    const map = { idle: "尚未儲存", saving: "儲存中…", saved: "已儲存", error: "儲存失敗", conflict: "版本衝突" };
    if (bar) {
      bar.textContent = (map[s] || s) + (msg ? "：" + msg : "");
      bar.className = s === "error" || s === "conflict" ? "err" : s === "saved" ? "ok" : "";
    }
    if (top) top.textContent = map[s] || s;
  }

  function showConflict(serverRev) {
    const msg = document.getElementById("ss-conflict-msg");
    if (msg) msg.textContent = `伺服器端版本已變（目前 v${store.revision}，伺服器 v${serverRev}）。請載入最新版，或另存本機副本。`;
    document.getElementById("ss-conflict-dialog").showModal();
  }

  (async function init() {
    try {
      if (!docId || docId === "default") {
        const res = await fetch("/api/projects");
        const items = res.ok ? await res.json() : [];
        if (items && items.length > 0) {
          docId = items[0].id || items[0].docId;
        } else {
          const cr = await fetch("/api/projects", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ title: "未命名樂譜" })
          });
          if (cr.ok) {
            const newDoc = await cr.json();
            docId = newDoc.id;
          }
        }
        store.docId = docId;
        validationUI = new ValidationUI(store, api, docId);
      }
      if (!docId) {
        const el = document.getElementById("ss-empty");
        if (el) { el.style.display = "block"; el.textContent = "用法：/score-studio/?doc=<專案ID>"; }
        return;
      }
      const doc = await api.doc(docId).score();
      store.doc = doc;
      document.getElementById("ss-title").textContent = doc.title || docId;
      const set = doc.scoreSettings || {};
      document.getElementById("ss-key").value = (set.key && set.key.tonic) || "C";
      const ts = set.timeSignature;
      document.getElementById("ss-tsig").value = ts ? ts.beats + "/" + ts.beatType : "4/4";
      document.getElementById("ss-tempo").value = (set.tempo && set.tempo.bpm) || 80;

      const interaction = new Interaction(store, history, refreshAll, () => validationUI.run());
      rowEditor = new RowEditor(store, interaction);
      new Keyboard(store, interaction, history, refreshAll, z => renderer.setZoom(z));
      const playback = new Playback(store, refreshAll, mi => renderer.focusMeasure(mi));
      const source = new SourcePanel(store, docId, refreshAll);

      wireControls(interaction, playback, source, () => save(true));

      history.onChange = onDirty;
      refreshAll();
      await validationUI.run();
      source.renderMarks();
      setSaveState("idle");
      // 注意：window.ScoreStudioInteraction 是模組命名空間（IIFE 已掛上），不可用實例覆蓋
      window.ScoreStudioMain = { save: () => save(true), togglePlay: () => playback.toggle(),
                                 interaction, store, renderer, validationUI };
    } catch (e) {
      const el = document.getElementById("ss-empty");
      if (el) { el.style.display = "block"; el.textContent = "載入失敗：" + e.message; }
    }
  })();

  function wireControls(interaction, playback, source, doSave) {
    document.querySelectorAll(".ss-mode").forEach(btn => {
      btn.addEventListener("click", () => {
        store.mode = btn.dataset.mode;
        document.querySelectorAll(".ss-mode").forEach(b => b.classList.toggle("active", b === btn));
      });
    });
    document.querySelectorAll(".ss-duration-group button").forEach(btn => {
      btn.addEventListener("click", () => {
        store.duration = btn.dataset.dur;
        document.querySelectorAll(".ss-duration-group button").forEach(b => b.classList.toggle("active", b === btn));
      });
    });
    // 樂譜設定（§13.2 顯示調性變更＝音級與實際 MIDI 音高不變）
    document.getElementById("ss-key").addEventListener("change", e => {
      const tonic = e.target.value.trim().toUpperCase() || "C";
      if (!store.doc.scoreSettings) store.doc.scoreSettings = {};
      store.doc.scoreSettings.key = { tonic, mode: "major", display: "1=" + tonic };
      onDirty();
    });
    document.getElementById("ss-tempo").addEventListener("change", e => {
      const s = store.doc.scoreSettings;
      s.tempo = s.tempo || { beatUnit: "quarter", text: "" };
      s.tempo.bpm = Math.max(20, Math.min(240, +e.target.value || 80));
      onDirty();
    });
    document.getElementById("ss-tsig").addEventListener("change", e => {
      const m = e.target.value.match(/^(\d{1,2})\s*\/\s*(\d{1,2})$/);
      if (m) {
        const s = store.doc.scoreSettings;
        s.timeSignature = { beats: +m[1], beatType: +m[2] };
        onDirty();
      }
    });
    document.getElementById("ss-transpose-display").addEventListener("change", e => {
      const s = store.doc.scoreSettings;
      s.displayTransposeSemitones = e.target.checked ? 1 : 0;
      onDirty();
    });
    document.getElementById("ss-add-measure").addEventListener("click", () => interaction.addMeasure());
    document.getElementById("ss-del-measure").addEventListener("click", () => interaction.deleteLastMeasure());
    document.getElementById("ss-dup-measure").addEventListener("click", () => interaction.duplicateMeasure());
    document.getElementById("ss-undo").addEventListener("click", () => { if (history.undo()) { refreshAll(); validationUI.run(); } });
    document.getElementById("ss-redo").addEventListener("click", () => { if (history.redo()) { refreshAll(); validationUI.run(); } });
    document.getElementById("ss-save").addEventListener("click", doSave);
    document.getElementById("ss-snapshot").addEventListener("click", async () => {
      await save();
      const label = prompt("快照名稱：", "手動快照");
      if (label == null) return;
      await api.doc(docId).snapshot(label || "手動快照");
      loadHistory();
    });
    document.getElementById("ss-export").addEventListener("click", async () => {
      const fmt = document.getElementById("ss-export-format").value;
      if (store.dirty) { await save(); if (store.dirty) return; }
      const issues = validationUI.reportIssues();
      if (issues.length && fmt === "musicxml") { showExportReport(issues, fmt); return; }
      doExport(fmt, issues);
    });
    document.getElementById("ss-legacy-link").addEventListener("click", e => {
      e.preventDefault();
      location.href = "/?project=" + encodeURIComponent(docId);
    });
    loadHistory();
  }

  async function loadHistory() {
    let snaps = [];
    try {
      const data = await api.doc(docId).history();
      snaps = (data && data.snapshots) || [];
    } catch { /* 尚無快照 */ }
    const el = document.getElementById("ss-history");
    el.innerHTML = "";
    for (const s of snaps.slice(-12).reverse()) {
      const div = document.createElement("div");
      div.className = "ss-hitem";
      div.textContent = s.name + "（" + new Date(s.ts * 1000).toLocaleString("zh-TW") + "）";
      div.title = "點擊回復到此快照";
      div.addEventListener("click", async () => {
        if (!confirm("回復到快照 " + s.name + "？目前未存盤的改動會被覆蓋。")) return;
        await api.doc(docId).restore(s.name);
        store.doc = await api.doc(docId).score();
        history.clear();
        refreshAll();
        await validationUI.run();
        setSaveState("saved");
      });
      el.appendChild(div);
    }
  }

  function showExportReport(issues, fmt) {
    const dlg = document.getElementById("ss-report-dialog");
    const ul = document.getElementById("ss-report-list");
    ul.innerHTML = "";
    for (const it of issues.slice(0, 60)) {
      const li = document.createElement("li");
      li.textContent = `小節 ${it.measure + 1}：${it.status}${it.reasons ? "（" + it.reasons + "）" : ""}`;
      ul.appendChild(li);
    }
    dlg.showModal();
    document.getElementById("ss-report-cancel").onclick = () => dlg.close();
    document.getElementById("ss-report-continue").onclick = () => { dlg.close(); doExport(fmt, issues); };
  }

  async function doExport(fmt, issues) {
    try {
      await api.doc(docId).download(docId, fmt, (store.doc && store.doc.title) || docId);
      const el = document.getElementById("ss-export-report");
      el.textContent = "已匯出 " + fmt.toUpperCase() + ((issues && issues.length) ? `（附 ${issues.length} 項警告）` : "");
      el.style.color = "var(--good)";
    } catch (e) {
      const el = document.getElementById("ss-export-report");
      el.textContent = "匯出失敗：" + e.message;
      el.style.color = "var(--bad)";
    }
  }

  document.getElementById("ss-conflict-reload").addEventListener("click", async () => {
    document.getElementById("ss-conflict-dialog").close();
    store.doc = await api.doc(docId).score();
    history.clear();
    refreshAll();
    await validationUI.run();
    setSaveState("idle");
  });
  document.getElementById("ss-conflict-local").addEventListener("click", () => {
    document.getElementById("ss-conflict-dialog").close();
    const blob = new Blob([JSON.stringify(store.doc, null, 2)], { type: "application/json" });
    const a = document.createElement("a");
    a.href = URL.createObjectURL(blob);
    a.download = docId + ".local-score.json";
    a.click();
    setSaveState("error", "已另存本機副本，請載入最新版後重放改動");
  });
})();
