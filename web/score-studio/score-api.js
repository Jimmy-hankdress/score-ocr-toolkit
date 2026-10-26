/* ScoreStudio API client — 離線 REST（§4/§5/§11）
   端點契約（對齊 app/scorestudio/score_studio_routes.py）：
   GET  /projects/{id}/score              → doc dict
   PUT  /projects/{id}/score  {expectedRevision,document} → {ok, revision, validation}
   POST /projects/{id}/score/validate     → {ok, summary, checks[], exportWarnings[]}
   POST /projects/{id}/score/snapshot {note} → {ok, snapshot: name}
   GET  /projects/{id}/score/history       → {snapshots:[{name, ts}]}
   POST /projects/{id}/score/restore/{name} → {ok, revision}
   GET  /projects/{id}/source-pages       → {pages:[{name, path, size}]}
   GET  /projects/{id}/source-map/{eid}  → {eventId, measure, page, bbox, hasBbox, rawToken, confidence, reviewStatus}
   GET  /projects/{id}/export/{fmt}       → {format, content: string}
   舊版：GET /projects/{id}               → legacy project.json
*/
(function () {
  // 同來源（§1.2 離線）：依當前主機/埠解析，避免硬編埠號
  const base = (location.protocol + "//" + location.host) + "/api";

  async function req(method, path, body) {
    const opts = { method, headers: { "Content-Type": "application/json" } };
    if (body !== undefined) opts.body = JSON.stringify(body);
    const res = await fetch(base + path, opts);
    let data = null;
    const text = await res.text();
    try { data = text ? JSON.parse(text) : null; } catch { data = text; }
    if (res.status === 409) {
      const e = new Error("版本衝突（409）");
      e.status = 409;
      e.expectedRevision = data && data.expectedRevision;
      e.actualRevision = data && data.actualRevision;
      throw e;
    }
    if (!res.ok) {
      const e = new Error((data && (data.detail || data.message)) || res.status + " " + res.statusText);
      e.status = res.status; e.data = data;
      throw e;
    }
    return data;
  }

  const api = {
    doc: id => ({
      score: () => req("GET", `/projects/${id}/score`),
      putScore: (doc, expectedRevision) =>
        req("PUT", `/projects/${id}/score`, { expectedRevision: expectedRevision == null ? null : expectedRevision, document: doc }),
      validate: () => req("POST", `/projects/${id}/score/validate`),
      snapshot: note => req("POST", `/projects/${id}/score/snapshot?note=${encodeURIComponent(note || "")}`),
      history: () => req("GET", `/projects/${id}/score/history`),
      restore: name => req("POST", `/projects/${id}/score/restore/${encodeURIComponent(name)}`),
      sourcePages: () => req("GET", `/projects/${id}/source-pages`),
      sourceMap: eventId => req("GET", `/projects/${id}/source-map/${encodeURIComponent(eventId)}`),
      legacy: () => req("GET", `/projects/${id}`),
      // 匯出：端點回傳 {format, content:string}；客戶端轉 Blob 下載
      async download(id, fmt, name) {
        const data = await req("GET", `/projects/${id}/export/${fmt}`);
        const mime = fmt === "musicxml" ? "application/xml" : fmt === "json" ? "application/json" : "text/plain";
        const blob = new Blob([data.content], { type: mime });
        const url = URL.createObjectURL(blob);
        const a = document.createElement("a");
        a.href = url;
        a.download = (name || id) + "." + (fmt === "musicxml" ? "musicxml" : fmt);
        document.body.appendChild(a); a.click(); a.remove();
        setTimeout(() => URL.revokeObjectURL(url), 5000);
        return { ok: true, fmt, content: data.content };
      },
    }),
  };
  window.ScoreStudioAPI = { api, base };
})();
