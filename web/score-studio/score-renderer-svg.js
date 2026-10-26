/* ScoreStudio SVG 渲染器（§8.1/§8.3：可選取、data-*、縮放捲動） */
(function () {
  const { Layout, measureWidthPx } = window.ScoreStudioLayout;

  class SVGRenderer {
    constructor(store) {
      this.store = store;
      this.layout = new Layout(store);
      this.container = document.getElementById("ss-canvas");
      this.zoom = store.settings.zoom;
    }
    render() {
      this.layout.render(this.container);
    }
    setZoom(z) {
      z = Math.max(0.5, Math.min(2.5, Math.round(z * 10) / 10));
      this.store.settings.zoom = z;
      this.render();
      const label = document.getElementById("ss-zoom-label");
      if (label) label.textContent = Math.round(z * 100) + "%";
    }
    focusMeasure(mi) {
      const wrap = document.getElementById("ss-canvas-wrap");
      const el = this.container.querySelector(`[data-measure-index="${mi}"]`);
      if (wrap && el) {
        const x = parseFloat(el.getBoundingClientRect().left - wrap.getBoundingClientRect().left);
        wrap.scrollTo({ left: Math.max(0, x - 60), behavior: "smooth" });
      }
    }
  }
  window.ScoreStudioRenderer = { SVGRenderer };
})();
