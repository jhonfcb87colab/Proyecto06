/* Capa de visualizacion pura: sin autoria, sin SQL, sin conexiones. */
(function () {
  "use strict";

  const cfg = window.BIWEB || {};
  const dashboardId = cfg.dashboardId;
  let loading = false;
  let toastTimer = null;

  const $ = (selector) => document.querySelector(selector);

  function toast(message, kind) {
    const box = $("#toast");
    if (!box) return;
    box.textContent = message;
    box.className = "toast " + (kind || "info");
    box.hidden = false;
    clearTimeout(toastTimer);
    toastTimer = setTimeout(() => {
      box.hidden = true;
    }, 4000);
  }

  function renderCanvas(data) {
    const canvas = $("#canvas");
    canvas.innerHTML = "";
    const widgets = data.widgets || [];
    if (!widgets.length) {
      const box = document.createElement("div");
      box.className = "canvas-empty";
      box.innerHTML = "<h3>Tablero sin widgets</h3><p>El autor aun no publico visualizaciones.</p>";
      canvas.appendChild(box);
      return;
    }
    widgets.forEach((widget) => {
      const card = document.createElement("article");
      card.className = "widget";
      const w = Math.max(1, Math.min(12, parseInt(widget.w, 10) || 3));
      const h = Math.max(1, Math.min(6, parseInt(widget.h, 10) || 2));
      const hasX = widget.x != null && widget.x !== "";
      const hasY = widget.y != null && widget.y !== "";
      const x = hasX ? Math.max(0, Math.min(12 - w, parseInt(widget.x, 10) || 0)) : null;
      const y = hasY ? Math.max(0, parseInt(widget.y, 10) || 0) : null;
      card.style.gridColumn = x == null ? "span " + w : x + 1 + " / span " + w;
      card.style.gridRow = y == null ? "span " + h : y + 1 + " / span " + h;
      const head = document.createElement("header");
      head.className = "widget-head";
      const title = document.createElement("h3");
      title.textContent = widget.title || "Widget";
      head.appendChild(title);
      card.appendChild(head);

      const chartBox = document.createElement("div");
      chartBox.className = "widget-chart";
      window.BICharts.render(chartBox, widget.chart_data || {});
      card.appendChild(chartBox);

      const chart = widget.chart_data || {};
      const bits = [];
      if (widget.dataset_name) bits.push(widget.dataset_name);
      if (chart.agg) bits.push(chart.agg);
      if (chart.row_count != null) bits.push(chart.row_count + " filas");
      if (bits.length) {
        const foot = document.createElement("footer");
        foot.className = "widget-foot";
        foot.textContent = bits.join(" · ");
        card.appendChild(foot);
      }
      canvas.appendChild(card);
    });
  }

  function render(data) {
    const dash = data.dashboard || {};
    document.title = (dash.name || "Tablero") + " · Vista";
    const title = $("#view-title");
    if (title) title.textContent = dash.name || "Tablero";
    const desc = $("#view-description");
    if (desc) desc.textContent = dash.description || "Sin descripcion";
    const stamp = $("#view-stamp");
    if (stamp) {
      stamp.textContent = "Actualizado " + new Date(data.generated_at || Date.now()).toLocaleTimeString("es-ES");
    }
    renderCanvas(data);
  }

  async function load(silent) {
    if (loading || !dashboardId) return;
    loading = true;
    try {
      const res = await fetch("/api/dashboards/" + dashboardId + "/render", {
        headers: { "X-BI-Mode": "view" },
        cache: "no-store",
      });
      if (!res.ok) {
        let message = "Error " + res.status;
        try {
          const body = await res.json();
          if (body.error) message = body.error;
        } catch (err) {
          /* ignore */
        }
        throw new Error(message);
      }
      render(await res.json());
    } catch (err) {
      if (!silent) toast(err.message || "No se pudo cargar el tablero", "error");
    } finally {
      loading = false;
    }
  }

  const refresh = $("#view-refresh");
  if (refresh) refresh.addEventListener("click", () => load());

  setInterval(() => {
    if (!document.hidden && !loading) load(true);
  }, 45000);

  load();
})();
