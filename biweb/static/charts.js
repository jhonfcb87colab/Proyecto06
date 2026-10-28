/* Graficos SVG sin dependencias externas. */
(function () {
  "use strict";

  const NS = "http://www.w3.org/2000/svg";
  const PALETTE = ["#8aa9e6", "#7fc8c2", "#f3b6a6", "#f6d186", "#b8a6e0", "#9ccf9b", "#f2a7c3", "#a9c7e8"];
  const W = 720;
  const H = 340;

  function esc(value) {
    return String(value == null ? "" : value)
      .replace(/&/g, "&amp;")
      .replace(/</g, "&lt;")
      .replace(/>/g, "&gt;")
      .replace(/"/g, "&quot;")
      .replace(/'/g, "&#39;");
  }

  function svgEl(tag, attrs, text) {
    const node = document.createElementNS(NS, tag);
    Object.keys(attrs || {}).forEach((key) => node.setAttribute(key, attrs[key]));
    if (text != null) node.textContent = text;
    return node;
  }

  function color(index) {
    return PALETTE[index % PALETTE.length];
  }

  function format(value, info) {
    if (value === null || value === undefined || value === "") return "—";
    const number = Number(value);
    if (!Number.isFinite(number)) return String(value);
    const f = info || {};
    const decimals = Number.isInteger(f.decimals) ? f.decimals : 0;
    try {
      if (f.format === "currency") {
        return new Intl.NumberFormat("es-ES", {
          style: "currency",
          currency: f.currency || "USD",
          minimumFractionDigits: decimals,
          maximumFractionDigits: decimals,
        }).format(number);
      }
      if (f.format === "percent") return number.toFixed(decimals) + "%";
      if (f.format === "integer") {
        return new Intl.NumberFormat("es-ES", { maximumFractionDigits: 0 }).format(number);
      }
      return new Intl.NumberFormat("es-ES", {
        minimumFractionDigits: decimals,
        maximumFractionDigits: decimals,
      }).format(number);
    } catch (err) {
      return String(value);
    }
  }

  function short(value) {
    const n = Number(value);
    if (!Number.isFinite(n)) return String(value);
    const abs = Math.abs(n);
    if (abs >= 1e9) return (n / 1e9).toFixed(1).replace(".0", "") + "B";
    if (abs >= 1e6) return (n / 1e6).toFixed(1).replace(".0", "") + "M";
    if (abs >= 1e3) return (n / 1e3).toFixed(1).replace(".0", "") + "k";
    return String(Math.round(n * 100) / 100);
  }

  function legend(series) {
    if (!series || series.length <= 1) return "";
    return (
      '<div class="legend">' +
      series
        .map(
          (item, index) =>
            '<span class="legend-item"><i style="background:' + color(index) + '"></i>' + esc(item.name) + "</span>"
        )
        .join("") +
      "</div>"
    );
  }

  function empty(container, reason) {
    container.innerHTML = '<div class="chart-empty">' + esc(reason || "Sin datos para mostrar") + "</div>";
  }

  function svgRoot() {
    return svgEl("svg", { viewBox: "0 0 " + W + " " + H, role: "img", class: "chart-svg" });
  }

  function axesY(svg, margin, min, max, info) {
    const ticks = 4;
    const span = max - min || 1;
    const y = (value) => margin.t + (H - margin.t - margin.b) * (1 - (value - min) / span);
    for (let i = 0; i <= ticks; i += 1) {
      const value = min + (span * i) / ticks;
      const yy = y(value);
      svg.appendChild(
        svgEl("line", { x1: margin.l, x2: W - margin.r, y1: yy, y2: yy, stroke: "#e5e7eb", "stroke-width": 1 })
      );
      const label = svgEl("text", {
        x: margin.l - 10,
        y: yy + 4,
        "text-anchor": "end",
        class: "axis-label",
      });
      label.textContent = info && info.format === "percent" ? value.toFixed(0) + "%" : short(value);
      svg.appendChild(label);
    }
    return y;
  }

  function xLabel(svg, x, y, text, anchor) {
    const label = svgEl("text", { x: x, y: y, "text-anchor": anchor || "middle", class: "axis-label" });
    label.textContent = String(text).slice(0, 16);
    label.appendChild(svgEl("title", {}, String(text)));
    svg.appendChild(label);
  }

  function normalizedSeries(series, labels, percent) {
    const work = series.map((item) => ({ name: item.name, data: item.data.map((v) => Number(v) || 0) }));
    if (!percent) return work;
    labels.forEach((label, index) => {
      let total = 0;
      work.forEach((item) => {
        const value = Math.max(0, item.data[index] || 0);
        total += value;
      });
      work.forEach((item) => {
        item.data[index] = total ? (Math.max(0, item.data[index] || 0) / total) * 100 : 0;
      });
    });
    return work;
  }

  function renderColumn(container, data, options) {
    const opts = options || {};
    const labels = data.labels || [];
    const source = data.series || [];
    if (!labels.length || !source.length) return empty(container, data.reason);
    const percent = !!opts.percent;
    const stacked = !!opts.stacked || percent;
    const series = normalizedSeries(source, labels, percent);
    const info = percent ? Object.assign({}, data.format, { format: "percent" }) : data.format;
    let max;
    let min;
    if (stacked) {
      max = Math.max(0, ...labels.map((label, index) => series.reduce((acc, item) => acc + Math.max(0, item.data[index]), 0)));
      min = 0;
    } else {
      const values = series.reduce((acc, item) => acc.concat(item.data), []);
      max = Math.max(0, ...values);
      min = Math.min(0, ...values);
    }
    if (max === min) max = min + 1;
    const margin = { l: 62, r: 18, t: 20, b: 58 };
    const svg = svgRoot();
    const y = axesY(svg, margin, min, max, info);
    const plotW = W - margin.l - margin.r;
    const groupW = plotW / labels.length;
    const barW = stacked ? groupW * 0.6 : Math.max(2, (groupW * 0.72) / series.length);
    const base = y(Math.max(min, 0));

    labels.forEach((label, index) => {
      const groupX = margin.l + index * groupW;
      let positive = 0;
      series.forEach((item, seriesIndex) => {
        const value = item.data[index] || 0;
        const topValue = stacked ? positive + Math.max(0, value) : value;
        const bottomValue = stacked ? positive : 0;
        if (stacked) positive += Math.max(0, value);
        const top = y(topValue);
        const bottom = stacked ? y(bottomValue) : base;
        const rect = svgEl("rect", {
          x: stacked ? groupX + groupW * 0.2 : groupX + groupW * 0.14 + seriesIndex * barW,
          y: Math.min(top, bottom),
          width: Math.max(1, stacked ? barW : barW - 1.5),
          height: Math.max(1, Math.abs(bottom - top)),
          rx: 3,
          fill: color(seriesIndex),
        });
        rect.appendChild(
          svgEl("title", {}, item.name + " · " + label + ": " + format(value, info))
        );
        svg.appendChild(rect);
      });
      if (labels.length <= 24 || index % Math.ceil(labels.length / 16) === 0) {
        xLabel(svg, groupX + groupW / 2, H - margin.b + 20, label);
      }
    });
    container.innerHTML = legend(source);
    container.appendChild(svg);
  }

  function renderHorizontal(container, data, options) {
    const opts = options || {};
    const labels = data.labels || [];
    const source = data.series || [];
    if (!labels.length || !source.length) return empty(container, data.reason);
    const percent = !!opts.percent;
    const stacked = !!opts.stacked || percent;
    const series = normalizedSeries(source, labels, percent);
    const info = percent ? Object.assign({}, data.format, { format: "percent" }) : data.format;
    let max;
    if (stacked) {
      max = Math.max(1, ...labels.map((label, index) => series.reduce((acc, item) => acc + Math.max(0, item.data[index]), 0)));
    } else {
      max = Math.max(1, ...series.reduce((acc, item) => acc.concat(item.data.map(Math.abs)), []));
    }
    const margin = { l: 120, r: 28, t: 22, b: 30 };
    const svg = svgRoot();
    const plotW = W - margin.l - margin.r;
    const plotH = H - margin.t - margin.b;
    const rowH = plotH / labels.length;
    const barH = stacked ? rowH * 0.62 : Math.max(2, (rowH * 0.7) / series.length);
    const x = (value) => margin.l + (Math.abs(value) / max) * plotW;
    for (let i = 0; i <= 4; i += 1) {
      const value = (max * i) / 4;
      const xx = margin.l + (plotW * i) / 4;
      svg.appendChild(svgEl("line", { x1: xx, x2: xx, y1: margin.t, y2: H - margin.b, stroke: "#e5e7eb", "stroke-width": 1 }));
      const label = svgEl("text", { x: xx, y: H - margin.b + 18, "text-anchor": "middle", class: "axis-label" });
      label.textContent = percent ? value.toFixed(0) + "%" : short(value);
      svg.appendChild(label);
    }
    labels.forEach((label, index) => {
      const rowY = margin.t + index * rowH;
      let positive = 0;
      series.forEach((item, seriesIndex) => {
        const value = item.data[index] || 0;
        const start = stacked ? positive : 0;
        const end = stacked ? positive + Math.max(0, value) : Math.abs(value);
        if (stacked) positive += Math.max(0, value);
        const rect = svgEl("rect", {
          x: x(start),
          y: stacked ? rowY + rowH * 0.18 : rowY + rowH * 0.15 + seriesIndex * barH,
          width: Math.max(1, x(end) - x(start)),
          height: Math.max(1, stacked ? barH : barH - 1.5),
          rx: 3,
          fill: color(seriesIndex),
        });
        rect.appendChild(svgEl("title", {}, item.name + " · " + label + ": " + format(value, info)));
        svg.appendChild(rect);
      });
      const left = svgEl("text", {
        x: margin.l - 10,
        y: rowY + rowH / 2 + 4,
        "text-anchor": "end",
        class: "axis-label",
      });
      left.textContent = String(label).slice(0, 18);
      left.appendChild(svgEl("title", {}, String(label)));
      svg.appendChild(left);
    });
    container.innerHTML = legend(source);
    container.appendChild(svg);
  }

  function renderCombo(container, data) {
    const labels = data.labels || [];
    const series = data.series || [];
    if (!labels.length || !series.length) return empty(container, data.reason);
    const values = series.reduce((acc, item) => acc.concat(item.data.map(Number)), []);
    const max = Math.max(0, ...values);
    const min = Math.min(0, ...values);
    const margin = { l: 62, r: 22, t: 20, b: 58 };
    const svg = svgRoot();
    const y = axesY(svg, margin, min, max || 1, data.format);
    const plotW = W - margin.l - margin.r;
    const groupW = plotW / labels.length;
    const barW = Math.max(2, groupW * 0.52);
    const base = y(Math.max(min, 0));
    const lineSeries = series.slice(1);
    labels.forEach((label, index) => {
      const groupX = margin.l + index * groupW;
      const value = Number(series[0].data[index]) || 0;
      const top = Math.min(y(value), base);
      const rect = svgEl("rect", {
        x: groupX + groupW * 0.24,
        y: top,
        width: barW,
        height: Math.max(1, Math.abs(y(value) - base)),
        rx: 3,
        fill: color(0),
      });
      rect.appendChild(svgEl("title", {}, series[0].name + " · " + label + ": " + format(value, data.format)));
      svg.appendChild(rect);
      if (labels.length <= 24 || index % Math.ceil(labels.length / 16) === 0) {
        xLabel(svg, groupX + groupW / 2, H - margin.b + 20, label);
      }
    });
    const step = labels.length > 1 ? plotW / (labels.length - 1) : 0;
    lineSeries.forEach((item, lineIndex) => {
      const points = item.data.map((value, index) => {
        const xx = margin.l + (labels.length > 1 ? index * step : plotW / 2);
        return [xx, y(Number(value) || 0)];
      });
      svg.appendChild(
        svgEl("path", {
          d: points.map((point, index) => (index === 0 ? "M" : "L") + point[0] + "," + point[1]).join(" "),
          fill: "none",
          stroke: color(lineIndex + 1),
          "stroke-width": 2.5,
        })
      );
      points.forEach((point, index) => {
        const circle = svgEl("circle", { cx: point[0], cy: point[1], r: 3.2, fill: color(lineIndex + 1) });
        circle.appendChild(svgEl("title", {}, item.name + " · " + labels[index] + ": " + format(item.data[index], data.format)));
        svg.appendChild(circle);
      });
    });
    container.innerHTML = legend(series);
    container.appendChild(svg);
  }

  function renderLine(container, data, options) {
    const opts = options || {};
    const labels = data.labels || [];
    const series = data.series || [];
    if (!labels.length || !series.length) return empty(container, data.reason);
    const area = !!opts.area;
    const stacked = !!opts.stacked;
    const margin = { l: 62, r: 22, t: 20, b: 58 };
    const svg = svgRoot();
    const plotW = W - margin.l - margin.r;
    const step = labels.length > 1 ? plotW / (labels.length - 1) : 0;
    const values = [];
    let baseline = labels.map(() => 0);
    const layers = [];
    series.forEach((item) => {
      const current = item.data.map((value, index) => {
        const number = Number(value) || 0;
        const result = stacked ? baseline[index] + number : number;
        values.push(result);
        return result;
      });
      layers.push({ name: item.name, lower: baseline.slice(), upper: current });
      baseline = current;
    });
    const max = Math.max(0, ...values);
    const min = area ? 0 : Math.min(0, ...values);
    const y = axesY(svg, margin, min, max || 1, data.format);
    layers.forEach((layer, index) => {
      const upper = layer.upper.map((value, i) => [margin.l + (labels.length > 1 ? i * step : plotW / 2), y(value)]);
      if (area) {
        const lower = layer.lower
          .map((value, i) => [margin.l + (labels.length > 1 ? i * step : plotW / 2), y(value)])
          .reverse();
        const path =
          upper.map((point, i) => (i === 0 ? "M" : "L") + point[0] + "," + point[1]).join(" ") +
          " " +
          lower.map((point) => "L" + point[0] + "," + point[1]).join(" ") +
          " Z";
        svg.appendChild(svgEl("path", { d: path, fill: color(index), "fill-opacity": 0.28, stroke: "none" }));
      }
      svg.appendChild(
        svgEl("path", {
          d: upper.map((point, i) => (i === 0 ? "M" : "L") + point[0] + "," + point[1]).join(" "),
          fill: "none",
          stroke: color(index),
          "stroke-width": 2.5,
          "stroke-linejoin": "round",
          "stroke-linecap": "round",
        })
      );
      upper.forEach((point, i) => {
        const circle = svgEl("circle", { cx: point[0], cy: point[1], r: labels.length > 40 ? 1.8 : 3.2, fill: color(index) });
        circle.appendChild(svgEl("title", {}, layer.name + " · " + labels[i] + ": " + format(layer.upper[i], data.format)));
        svg.appendChild(circle);
      });
    });
    const every = Math.max(1, Math.ceil(labels.length / 12));
    labels.forEach((label, index) => {
      if (index % every !== 0 && index !== labels.length - 1) return;
      xLabel(svg, margin.l + (labels.length > 1 ? index * step : plotW / 2), H - margin.b + 20, label);
    });
    container.innerHTML = legend(series);
    container.appendChild(svg);
  }

  function arcPath(cx, cy, r, start, end) {
    const p1 = [cx + r * Math.cos(start), cy + r * Math.sin(start)];
    const p2 = [cx + r * Math.cos(end), cy + r * Math.sin(end)];
    const large = end - start > Math.PI ? 1 : 0;
    return (
      "M " + cx + " " + cy + " L " + p1[0] + " " + p1[1] +
      " A " + r + " " + r + " 0 " + large + " 1 " + p2[0] + " " + p2[1] + " Z"
    );
  }

  function renderPie(container, data) {
    const labels = data.labels || [];
    const first = (data.series || [])[0];
    if (!labels.length || !first) return empty(container, data.reason);
    let entries = labels.map((label, index) => ({ label: label, value: Math.abs(Number(first.data[index]) || 0) }));
    entries = entries.filter((entry) => entry.value > 0).sort((a, b) => b.value - a.value);
    if (entries.length > 8) {
      const rest = entries.slice(7).reduce((acc, entry) => acc + entry.value, 0);
      entries = entries.slice(0, 7).concat([{ label: "Otros", value: rest }]);
    }
    const total = entries.reduce((acc, entry) => acc + entry.value, 0);
    if (!total) return empty(container, data.reason);
    const doughnut = data.type === "doughnut";
    const cx = 210;
    const cy = H / 2;
    const r = 118;
    const svg = svgRoot();
    let angle = -Math.PI / 2;
    entries.forEach((entry, index) => {
      const slice = (entry.value / total) * Math.PI * 2;
      const path = svgEl("path", {
        d: arcPath(cx, cy, r, angle, angle + slice),
        fill: color(index),
        stroke: "#ffffff",
        "stroke-width": 2,
      });
      path.appendChild(
        svgEl("title", {}, entry.label + ": " + format(entry.value, data.format) + " (" + ((entry.value / total) * 100).toFixed(1) + "%)")
      );
      svg.appendChild(path);
      angle += slice;
    });
    if (doughnut) {
      svg.appendChild(svgEl("circle", { cx: cx, cy: cy, r: r * 0.55, fill: "#ffffff" }));
      const centerValue = svgEl("text", { x: cx, y: cy - 2, "text-anchor": "middle", class: "pie-center-value" });
      centerValue.textContent = short(total);
      svg.appendChild(centerValue);
      const centerLabel = svgEl("text", { x: cx, y: cy + 20, "text-anchor": "middle", class: "axis-label" });
      centerLabel.textContent = data.y || "total";
      svg.appendChild(centerLabel);
    }
    const list = document.createElement("div");
    list.className = "pie-legend";
    list.innerHTML = entries
      .map(
        (entry, index) =>
          '<div class="pie-row"><i style="background:' + color(index) + '"></i><span class="pie-name">' +
          esc(entry.label) + '</span><span class="pie-value">' + esc(format(entry.value, data.format)) +
          " · " + ((entry.value / total) * 100).toFixed(1) + "%</span></div>"
      )
      .join("");
    container.innerHTML = "";
    container.appendChild(svg);
    container.appendChild(list);
  }

  function renderTable(container, data) {
    const columns = data.columns || [];
    const rows = data.rows || [];
    if (!columns.length) return empty(container, data.reason);
    const head = columns.map((column) => "<th>" + esc(column) + "</th>").join("");
    const body = rows
      .map((row) => {
        const cells = columns
          .map((column) => {
            const value = row[column];
            const numeric = typeof value === "number";
            return "<td" + (numeric ? ' class="num"' : "") + ">" + esc(numeric ? format(value, data.format) : value) + "</td>";
          })
          .join("");
        return "<tr>" + cells + "</tr>";
      })
      .join("");
    container.innerHTML =
      '<div class="table-wrap"><table><thead><tr>' + head + "</tr></thead><tbody>" +
      (body || '<tr><td colspan="' + columns.length + '">Sin filas</td></tr>') +
      "</tbody></table></div>" +
      (data.truncated ? '<p class="hint">Vista limitada a ' + rows.length + " filas.</p>" : "");
  }

  function renderKpi(container, data) {
    const value = format(data.value, data.format);
    container.innerHTML =
      '<div class="kpi"><div class="kpi-value">' + esc(value) +
      '</div><div class="kpi-label">' + esc(data.label || data.y || "") +
      '</div><div class="kpi-meta">' + esc(String(data.rows || 0)) + " filas · " + esc(data.agg || "") + "</div></div>";
  }

  function renderMultiRow(container, data) {
    const items = data.items || [];
    if (!items.length) return empty(container, data.reason);
    container.innerHTML =
      '<div class="multi-row">' +
      items
        .map(
          (item) =>
            '<div class="multi-item"><span>' + esc(item.label) + "</span><strong>" +
            esc(format(item.value, data.format)) + "</strong></div>"
        )
        .join("") +
      "</div>";
  }

  function renderScatter(container, data) {
    const points = data.points || [];
    if (!points.length) return empty(container, data.reason);
    const xs = points.map((point) => point.x);
    const ys = points.map((point) => point.y);
    const xMin = Math.min(...xs);
    const xMax = Math.max(...xs);
    const yMin = Math.min(...ys);
    const yMax = Math.max(...ys);
    const sizes = points.map((point) => Number(point.size) || 1);
    const sizeMax = Math.max(1, ...sizes);
    const margin = { l: 64, r: 22, t: 22, b: 54 };
    const svg = svgRoot();
    const y = axesY(svg, margin, yMin, yMax, data.format);
    const plotW = W - margin.l - margin.r;
    const x = (value) => margin.l + ((value - xMin) / (xMax - xMin || 1)) * plotW;
    for (let i = 0; i <= 4; i += 1) {
      const value = xMin + ((xMax - xMin) * i) / 4;
      const xx = margin.l + (plotW * i) / 4;
      svg.appendChild(
        svgEl("line", { x1: xx, x2: xx, y1: margin.t, y2: H - margin.b, stroke: "#eef1f5", "stroke-width": 1 })
      );
      const label = svgEl("text", { x: xx, y: H - margin.b + 18, "text-anchor": "middle", class: "axis-label" });
      label.textContent = short(value);
      svg.appendChild(label);
    }
    points.forEach((point) => {
      const bubble = data.type === "bubble";
      const radius = bubble ? 4 + (Math.sqrt(Math.abs(point.size) || 1) / Math.sqrt(sizeMax)) * 20 : 5;
      const circle = svgEl("circle", {
        cx: x(point.x),
        cy: y(point.y),
        r: radius,
        fill: bubble ? "rgba(127,200,194,0.62)" : "rgba(138,169,230,0.78)",
        stroke: bubble ? "#4f9e98" : "#5c7fc2",
        "stroke-width": 1,
      });
      circle.appendChild(svgEl("title", {}, point.label + " · x: " + short(point.x) + " · y: " + format(point.y, data.format)));
      svg.appendChild(circle);
    });
    container.innerHTML = '<p class="hint">' + esc(data.x_field || "x") + " / " + esc(data.y_field || "y") + "</p>";
    container.appendChild(svg);
  }

  function renderWaterfall(container, data) {
    const labels = data.labels || [];
    const first = (data.series || [])[0];
    if (!labels.length || !first) return empty(container, data.reason);
    const values = first.data.map((value) => Number(value) || 0);
    let running = 0;
    const points = values.map((value, index) => {
      const start = running;
      running += value;
      return { label: labels[index], value: value, start: start, end: running };
    });
    const min = Math.min(0, ...points.map((point) => Math.min(point.start, point.end)));
    const max = Math.max(0, ...points.map((point) => Math.max(point.start, point.end)));
    const margin = { l: 62, r: 18, t: 20, b: 58 };
    const svg = svgRoot();
    const y = axesY(svg, margin, min, max || 1, data.format);
    const plotW = W - margin.l - margin.r;
    const groupW = plotW / points.length;
    const barW = Math.max(4, groupW * 0.58);
    points.forEach((point, index) => {
      const top = y(Math.max(point.start, point.end));
      const bottom = y(Math.min(point.start, point.end));
      const rect = svgEl("rect", {
        x: margin.l + index * groupW + (groupW - barW) / 2,
        y: top,
        width: barW,
        height: Math.max(1, bottom - top),
        rx: 3,
        fill: point.value >= 0 ? "#7fc8c2" : "#f3b6a6",
      });
      rect.appendChild(svgEl("title", {}, point.label + ": " + format(point.value, data.format)));
      svg.appendChild(rect);
      if (index < points.length - 1) {
        const nextY = y(point.end);
        svg.appendChild(
          svgEl("line", {
            x1: margin.l + index * groupW + (groupW + barW) / 2,
            x2: margin.l + (index + 1) * groupW + (groupW - barW) / 2,
            y1: nextY,
            y2: nextY,
            stroke: "#b7c0cc",
            "stroke-dasharray": "3 3",
          })
        );
      }
      xLabel(svg, margin.l + index * groupW + groupW / 2, H - margin.b + 20, point.label);
    });
    container.innerHTML = "";
    container.appendChild(svg);
  }

  function renderFunnel(container, data) {
    const labels = data.labels || [];
    const first = (data.series || [])[0];
    if (!labels.length || !first) return empty(container, data.reason);
    const values = first.data.map((value) => Math.abs(Number(value) || 0));
    const max = Math.max(1, ...values);
    const svg = svgRoot();
    const top = 20;
    const bottom = H - 20;
    const rowH = (bottom - top) / labels.length;
    values.forEach((value, index) => {
      const width = 80 + (value / max) * (W - 260);
      const x = (W - 170 - width) / 2;
      const y = top + index * rowH;
      const path = svgEl("path", {
        d:
          "M " + x + " " + y + " L " + (x + width) + " " + y +
          " L " + (x + width - 8) + " " + (y + rowH - 4) +
          " L " + (x + 8) + " " + (y + rowH - 4) + " Z",
        fill: color(index),
        opacity: 0.9,
      });
      path.appendChild(svgEl("title", {}, labels[index] + ": " + format(value, data.format)));
      svg.appendChild(path);
      const label = svgEl("text", { x: W - 150, y: y + rowH / 2 + 4, class: "axis-label" });
      label.textContent = String(labels[index]).slice(0, 22);
      svg.appendChild(label);
      const amount = svgEl("text", { x: W - 20, y: y + rowH / 2 + 4, "text-anchor": "end", class: "axis-label" });
      amount.textContent = format(value, data.format);
      svg.appendChild(amount);
    });
    container.innerHTML = "";
    container.appendChild(svg);
  }

  function renderTreemap(container, data) {
    const labels = data.labels || [];
    const first = (data.series || [])[0];
    if (!labels.length || !first) return empty(container, data.reason);
    let items = labels
      .map((label, index) => ({ label: label, value: Math.abs(Number(first.data[index]) || 0) }))
      .filter((item) => item.value > 0)
      .sort((a, b) => b.value - a.value);
    if (!items.length) return empty(container, data.reason);
    const tiles = [];
    function layout(entries, x, y, width, height, vertical) {
      if (!entries.length) return;
      if (entries.length === 1) {
        tiles.push({ item: entries[0], x: x, y: y, width: width, height: height });
        return;
      }
      const total = entries.reduce((acc, entry) => acc + entry.value, 0);
      let acc = 0;
      let split = 1;
      for (let i = 0; i < entries.length - 1; i += 1) {
        acc += entries[i].value;
        split = i + 1;
        if (acc >= total / 2) break;
      }
      const firstPart = entries.slice(0, split);
      const secondPart = entries.slice(split);
      const ratio = firstPart.reduce((sum, entry) => sum + entry.value, 0) / total;
      if (vertical) {
        const w1 = width * ratio;
        layout(firstPart, x, y, w1, height, false);
        layout(secondPart, x + w1, y, width - w1, height, false);
      } else {
        const h1 = height * ratio;
        layout(firstPart, x, y, width, h1, true);
        layout(secondPart, x, y + h1, width, height - h1, true);
      }
    }
    layout(items, 0, 0, W, H, true);
    const svg = svgRoot();
    tiles.forEach((tile, index) => {
      const rect = svgEl("rect", {
        x: tile.x + 1,
        y: tile.y + 1,
        width: Math.max(1, tile.width - 2),
        height: Math.max(1, tile.height - 2),
        rx: 4,
        fill: color(index),
        stroke: "#ffffff",
        "stroke-width": 1,
      });
      rect.appendChild(svgEl("title", {}, tile.item.label + ": " + format(tile.item.value, data.format)));
      svg.appendChild(rect);
      if (tile.width > 70 && tile.height > 28) {
        const text = svgEl("text", { x: tile.x + 8, y: tile.y + 20, class: "treemap-label" });
        text.textContent = String(tile.item.label).slice(0, Math.floor(tile.width / 8));
        svg.appendChild(text);
        const value = svgEl("text", { x: tile.x + 8, y: tile.y + 38, class: "axis-label" });
        value.textContent = short(tile.item.value);
        svg.appendChild(value);
      }
    });
    container.innerHTML = "";
    container.appendChild(svg);
  }

  function polar(cx, cy, r, angle) {
    return [cx + r * Math.cos(angle), cy + r * Math.sin(angle)];
  }

  function arcStroke(cx, cy, r, start, end) {
    const p1 = polar(cx, cy, r, start);
    const p2 = polar(cx, cy, r, end);
    const large = end - start > Math.PI ? 1 : 0;
    return "M " + p1[0] + " " + p1[1] + " A " + r + " " + r + " 0 " + large + " 1 " + p2[0] + " " + p2[1];
  }

  function renderGauge(container, data) {
    const max = Number(data.max) || 100;
    const value = Number(data.value) || 0;
    const ratio = Math.max(0, Math.min(1, value / (max || 1)));
    const cx = W / 2;
    const cy = H - 52;
    const r = 150;
    const start = Math.PI * 0.75;
    const end = Math.PI * 2.25;
    const svg = svgRoot();
    svg.appendChild(
      svgEl("path", {
        d: arcStroke(cx, cy, r, start, end),
        fill: "none",
        stroke: "#e5e9ef",
        "stroke-width": 24,
        "stroke-linecap": "round",
      })
    );
    svg.appendChild(
      svgEl("path", {
        d: arcStroke(cx, cy, r, start, start + (end - start) * ratio),
        fill: "none",
        stroke: "#7fc8c2",
        "stroke-width": 24,
        "stroke-linecap": "round",
      })
    );
    const angle = start + (end - start) * ratio;
    const needle = polar(cx, cy, r - 36, angle);
    svg.appendChild(svgEl("line", { x1: cx, y1: cy, x2: needle[0], y2: needle[1], stroke: "#31415a", "stroke-width": 3 }));
    svg.appendChild(svgEl("circle", { cx: cx, cy: cy, r: 8, fill: "#31415a" }));
    const valueText = svgEl("text", { x: cx, y: cy - 34, "text-anchor": "middle", class: "gauge-value" });
    valueText.textContent = format(value, data.format);
    svg.appendChild(valueText);
    const labelText = svgEl("text", { x: cx, y: cy - 8, "text-anchor": "middle", class: "axis-label" });
    labelText.textContent = data.label || "";
    svg.appendChild(labelText);
    const maxText = svgEl("text", { x: cx, y: cy + 32, "text-anchor": "middle", class: "axis-label" });
    maxText.textContent = "max " + format(max, data.format);
    svg.appendChild(maxText);
    container.innerHTML = "";
    container.appendChild(svg);
  }

  function renderPareto(container, data) {
    const labels = data.labels || [];
    const first = (data.series || [])[0];
    if (!labels.length || !first) return empty(container, data.reason);
    const values = first.data.map((value) => Math.abs(Number(value) || 0));
    const cumulative = data.cumulative || [];
    const max = Math.max(1, ...values);
    const margin = { l: 62, r: 58, t: 20, b: 58 };
    const svg = svgRoot();
    const y = axesY(svg, margin, 0, max, data.format);
    const plotW = W - margin.l - margin.r;
    const groupW = plotW / labels.length;
    const barW = Math.max(4, groupW * 0.62);
    labels.forEach((label, index) => {
      const value = values[index];
      const rect = svgEl("rect", {
        x: margin.l + index * groupW + (groupW - barW) / 2,
        y: y(value),
        width: barW,
        height: Math.max(1, y(0) - y(value)),
        rx: 3,
        fill: color(0),
      });
      rect.appendChild(svgEl("title", {}, label + ": " + format(value, data.format)));
      svg.appendChild(rect);
      xLabel(svg, margin.l + index * groupW + groupW / 2, H - margin.b + 20, label);
    });
    const step = labels.length > 1 ? plotW / (labels.length - 1) : 0;
    const points = cumulative.map((value, index) => [margin.l + (labels.length > 1 ? index * step : plotW / 2), margin.t + ((H - margin.t - margin.b) * (1 - Number(value) / 100))]);
    svg.appendChild(
      svgEl("path", {
        d: points.map((point, index) => (index === 0 ? "M" : "L") + point[0] + "," + point[1]).join(" "),
        fill: "none",
        stroke: "#f0a05a",
        "stroke-width": 2.5,
      })
    );
    points.forEach((point, index) => {
      const circle = svgEl("circle", { cx: point[0], cy: point[1], r: 3.2, fill: "#f0a05a" });
      circle.appendChild(svgEl("title", {}, "Acumulado: " + cumulative[index] + "%"));
      svg.appendChild(circle);
    });
    [0, 50, 100].forEach((value) => {
      const label = svgEl("text", { x: W - margin.r + 10, y: margin.t + ((H - margin.t - margin.b) * (1 - value / 100)) + 4, class: "axis-label" });
      label.textContent = value + "%";
      svg.appendChild(label);
    });
    container.innerHTML = "";
    container.appendChild(svg);
  }

  function renderCorrelation(container, data) {
    const columns = data.columns || [];
    const matrix = data.matrix || [];
    if (!columns.length || !matrix.length) return empty(container, data.reason);
    const cell = Math.min(58, (W - 160) / columns.length, (H - 70) / columns.length);
    const startX = 150;
    const startY = 44;
    const svg = svgRoot();
    columns.forEach((name, index) => {
      const label = svgEl("text", { x: startX + index * cell + cell / 2, y: 22, "text-anchor": "middle", class: "axis-label" });
      label.textContent = String(name).slice(0, 9);
      label.appendChild(svgEl("title", {}, name));
      svg.appendChild(label);
      const row = svgEl("text", { x: startX - 10, y: startY + index * cell + cell / 2 + 4, "text-anchor": "end", class: "axis-label" });
      row.textContent = String(name).slice(0, 14);
      row.appendChild(svgEl("title", {}, name));
      svg.appendChild(row);
      matrix[index].forEach((value, j) => {
        const intensity = Math.min(1, Math.abs(Number(value) || 0));
        const fill = value >= 0
          ? "rgba(82,132,214," + (0.1 + intensity * 0.8) + ")"
          : "rgba(214,92,76," + (0.1 + intensity * 0.8) + ")";
        const rect = svgEl("rect", {
          x: startX + j * cell + 1,
          y: startY + index * cell + 1,
          width: cell - 2,
          height: cell - 2,
          rx: 3,
          fill: fill,
        });
        rect.appendChild(svgEl("title", {}, columns[index] + " / " + columns[j] + ": " + Number(value).toFixed(2)));
        svg.appendChild(rect);
        const text = svgEl("text", {
          x: startX + j * cell + cell / 2,
          y: startY + index * cell + cell / 2 + 4,
          "text-anchor": "middle",
          class: "cell-label",
          fill: intensity > 0.55 ? "#ffffff" : "#2c3a4f",
        });
        text.textContent = Number(value).toFixed(1);
        svg.appendChild(text);
      });
    });
    container.innerHTML = "";
    container.appendChild(svg);
  }

  function renderInfluencers(container, data) {
    const items = data.influencers || [];
    if (!items.length) return empty(container, data.reason);
    const max = Math.max(0.01, ...items.map((item) => Math.abs(item.score)));
    const center = 430;
    const margin = { l: 150, r: 40, t: 20, b: 20 };
    const rowH = (H - margin.t - margin.b) / items.length;
    const svg = svgRoot();
    svg.appendChild(svgEl("line", { x1: center, x2: center, y1: margin.t, y2: H - margin.b, stroke: "#cdd5df" }));
    items.forEach((item, index) => {
      const width = (Math.abs(item.score) / max) * (W - margin.l - margin.r - 30);
      const y = margin.t + index * rowH + rowH * 0.2;
      const rect = svgEl("rect", {
        x: item.score >= 0 ? center : center - width,
        y: y,
        width: Math.max(1, width),
        height: Math.max(4, rowH * 0.6),
        rx: 3,
        fill: item.score >= 0 ? "#7fc8c2" : "#f3b6a6",
      });
      rect.appendChild(svgEl("title", {}, item.field + " · score " + item.score + " · impacto " + item.impact + "%"));
      svg.appendChild(rect);
      const label = svgEl("text", { x: 10, y: y + rowH * 0.33, class: "axis-label" });
      label.textContent = String(item.field).slice(0, 20);
      svg.appendChild(label);
      const value = svgEl("text", {
        x: item.score >= 0 ? center + width + 6 : center - width - 6,
        y: y + rowH * 0.33,
        "text-anchor": item.score >= 0 ? "start" : "end",
        class: "axis-label",
      });
      value.textContent = (item.score >= 0 ? "+" : "") + item.score.toFixed(2);
      svg.appendChild(value);
    });
    container.innerHTML = '<p class="hint">Objetivo: ' + esc(data.target || "") + "</p>";
    container.appendChild(svg);
  }

  function renderMap(container, data) {
    const svg = svgRoot();
    const points = data.points || [];
    const regions = data.regions || [];
    svg.appendChild(svgEl("rect", { x: 0, y: 0, width: W, height: H, fill: "#eef5f9", rx: 8 }));
    for (let i = 1; i < 8; i += 1) {
      svg.appendChild(svgEl("line", { x1: (W * i) / 8, x2: (W * i) / 8, y1: 0, y2: H, stroke: "#dbe8ef" }));
    }
    for (let i = 1; i < 4; i += 1) {
      svg.appendChild(svgEl("line", { x1: 0, x2: W, y1: (H * i) / 4, y2: (H * i) / 4, stroke: "#dbe8ef" }));
    }
    if (points.length) {
      const values = points.map((point) => Math.abs(Number(point.value) || 0));
      const max = Math.max(1, ...values);
      points.forEach((point) => {
        const x = 40 + ((Number(point.lon) + 180) / 360) * (W - 80);
        const y = 20 + ((90 - Number(point.lat)) / 180) * (H - 40);
        const radius = data.type === "map_bubble" ? 4 + (Math.abs(Number(point.value) || 0) / max) * 18 : 5;
        const circle = svgEl("circle", {
          cx: x,
          cy: y,
          r: radius,
          fill: "rgba(127,200,194,0.7)",
          stroke: "#3b8f89",
          "stroke-width": 1,
        });
        circle.appendChild(svgEl("title", {}, point.label + " · " + format(point.value, data.format)));
        svg.appendChild(circle);
      });
      container.innerHTML = '<p class="hint">Mapa esquematico · ' + esc(data.lat_field || "lat") + " / " + esc(data.lon_field || "lon") + "</p>";
    } else if (regions.length) {
      const max = Math.max(1, ...regions.map((region) => Math.abs(Number(region.value) || 0)));
      const columns = Math.ceil(Math.sqrt(regions.length));
      const rows = Math.ceil(regions.length / columns);
      const cellW = (W - 20) / columns;
      const cellH = (H - 20) / rows;
      regions.forEach((region, index) => {
        const col = index % columns;
        const row = Math.floor(index / columns);
        const intensity = 0.15 + (Math.abs(Number(region.value) || 0) / max) * 0.75;
        const rect = svgEl("rect", {
          x: 10 + col * cellW + 2,
          y: 10 + row * cellH + 2,
          width: cellW - 4,
          height: cellH - 4,
          rx: 4,
          fill: "rgba(82,132,214," + intensity + ")",
        });
        rect.appendChild(svgEl("title", {}, region.name + ": " + format(region.value, data.format)));
        svg.appendChild(rect);
        if (cellW > 70) {
          const label = svgEl("text", { x: 10 + col * cellW + 8, y: 10 + row * cellH + 20, class: "treemap-label" });
          label.textContent = String(region.name).slice(0, 16);
          svg.appendChild(label);
        }
      });
      container.innerHTML = '<p class="hint">Mapa coropletico esquematico · ' + esc(data.label_field || "region") + "</p>";
    } else {
      return empty(container, data.reason);
    }
    container.appendChild(svg);
  }

  function renderSlicer(container, data) {
    const values = data.values || [];
    if (!values.length) return empty(container, data.reason);
    container.innerHTML =
      '<div class="slicer"><div class="slicer-head">' + esc(data.field || "Segmentador") +
      '<button type="button" class="link" data-slicer-clear="1">Limpiar</button></div><div class="slicer-values">' +
      values
        .map(
          (value) =>
            '<button type="button" class="slicer-chip" data-slicer-value="' + esc(value) + '">' + esc(value) + "</button>"
        )
        .join("") +
      "</div></div>";
    const chips = Array.from(container.querySelectorAll("[data-slicer-value]"));
    function emit() {
      const selected = chips.filter((chip) => chip.classList.contains("active")).map((chip) => chip.dataset.slicerValue);
      container.dispatchEvent(
        new CustomEvent("biweb:filter", {
          bubbles: true,
          detail: { dataset_id: data.dataset_id, field: data.field, values: selected },
        })
      );
    }
    chips.forEach((chip) => {
      chip.addEventListener("click", () => {
        chip.classList.toggle("active");
        emit();
      });
    });
    const clear = container.querySelector("[data-slicer-clear]");
    if (clear) {
      clear.addEventListener("click", () => {
        chips.forEach((chip) => chip.classList.remove("active"));
        emit();
      });
    }
  }

  function renderFilterPanel(container, data) {
    const filters = data.filters || [];
    if (!filters.length) return empty(container, data.reason);
    container.innerHTML =
      '<div class="filter-panel"><div class="slicer-head">Panel de filtros</div>' +
      filters
        .map(
          (filter) =>
            '<details class="filter-group" open><summary>' + esc(filter.field) + "</summary><div class=\"filter-values\">" +
            filter.values
              .map(
                (value) =>
                  '<label class="check"><input type="checkbox" data-filter-field="' + esc(filter.field) +
                  '" data-filter-value="' + esc(value) + '"><span>' + esc(value) + "</span></label>"
              )
              .join("") +
            "</div></details>"
        )
        .join("") +
      "</div>";
    container.querySelectorAll("[data-filter-field]").forEach((checkbox) => {
      checkbox.addEventListener("change", () => {
        const field = checkbox.dataset.filterField;
        const values = Array.from(container.querySelectorAll('[data-filter-field="' + CSS.escape(field) + '"]:checked')).map(
          (item) => item.dataset.filterValue
        );
        container.dispatchEvent(
          new CustomEvent("biweb:filter", {
            bubbles: true,
            detail: { dataset_id: data.dataset_id, field: field, values: values },
          })
        );
      });
    });
  }

  function safeUrl(value) {
    const url = String(value || "").trim();
    if (/^(https?:)?\/\//i.test(url) || url.startsWith("/") || url.startsWith("#")) return url;
    return "";
  }

  function renderInteraction(container, data) {
    const type = data.type;
    const label = data.label || data.text || data.tooltip || "Accion";
    const url = safeUrl(data.url);
    if (type === "tooltip") {
      container.innerHTML =
        '<div class="chart-tooltip"><strong>' + esc(label) + "</strong><p>" +
        esc(data.tooltip || data.text || "Sin texto de ayuda") + "</p></div>";
      return;
    }
    if (type === "bookmark") {
      const bookmarkId = data.widget_id == null ? "" : String(data.widget_id);
      const actions = bookmarkId
        ? '<div class="bookmark-actions">' +
          '<button type="button" class="btn" data-bookmark-action="save" data-bookmark-id="' + esc(bookmarkId) + '">Guardar estado</button>' +
          '<button type="button" class="btn primary" data-bookmark-action="apply" data-bookmark-id="' + esc(bookmarkId) + '">Restaurar</button>' +
          "</div>"
        : "";
      container.innerHTML =
        '<div class="nav-card"><span class="nav-kind">Marcador</span>' +
        "<strong>" + esc(label) + "</strong>" +
        (data.tooltip ? "<p>" + esc(data.tooltip) + "</p>" : "") +
        actions +
        (url ? '<a class="btn" href="' + esc(url) + '" target="_blank" rel="noopener">Abrir enlace</a>' : "") +
        "</div>";
      return;
    }
    if (type === "nav_buttons") {
      container.innerHTML =
        '<div class="nav-card"><span class="nav-kind">Navegacion</span>' +
        "<strong>" + esc(label) + "</strong>" +
        (data.tooltip ? "<p>" + esc(data.tooltip) + "</p>" : "") +
        (url ? '<a class="btn primary" href="' + esc(url) + '" target="_blank" rel="noopener">Abrir</a>' : "") +
        "</div>";
      return;
    }
    empty(container, "Configura el tipo de interaccion");
  }

  function renderHierarchy(container, data) {
    const root = data.tree;
    if (!root) return empty(container, data.reason || "Sin jerarquia para mostrar");
    const rows = [];
    function walk(node, depth) {
      rows.push({ node: node, depth: depth });
      if (depth < 3 && Array.isArray(node.children)) {
        node.children.forEach((child) => walk(child, depth + 1));
      }
    }
    walk(root, 0);
    const visible = rows.slice(0, 24);
    const max = Math.max(1, ...visible.map((row) => Math.abs(Number(row.node.value) || 0)));
    const rowH = (H - 20) / visible.length;
    const svg = svgRoot();
    visible.forEach((row, index) => {
      const y = 10 + index * rowH;
      const text = svgEl("text", {
        x: 12 + row.depth * 22,
        y: y + rowH / 2 + 4,
        class: row.depth === 0 ? "tree-root" : "axis-label",
      });
      text.textContent = String(row.node.label).slice(0, 24);
      text.appendChild(svgEl("title", {}, String(row.node.label)));
      svg.appendChild(text);
      const barX = 260 + row.depth * 18;
      const barW = Math.max(1, (Math.abs(Number(row.node.value) || 0) / max) * (W - barX - 90));
      svg.appendChild(
        svgEl("rect", {
          x: barX,
          y: y + rowH * 0.24,
          width: barW,
          height: Math.max(3, rowH * 0.52),
          rx: 3,
          fill: color(row.depth),
          "fill-opacity": row.depth === 0 ? 0.95 : 0.7,
        })
      );
      const value = svgEl("text", { x: W - 12, y: y + rowH / 2 + 4, "text-anchor": "end", class: "axis-label" });
      value.textContent = format(row.node.value, data.format);
      svg.appendChild(value);
      if (row.depth > 0) {
        svg.appendChild(
          svgEl("line", {
            x1: 12 + (row.depth - 1) * 22 + 6,
            x2: 12 + row.depth * 22 - 4,
            y1: y + rowH / 2,
            y2: y + rowH / 2,
            stroke: "#cbd5e1",
            "stroke-width": 1,
          })
        );
      }
    });
    container.innerHTML =
      '<p class="hint">Raiz: ' + esc(root.label) + (rows.length > visible.length ? " · vista parcial" : "") + "</p>";
    container.appendChild(svg);
  }

  function renderQna(container, data) {
    const question = data.question || "Pregunta";
    if (!data.labels || !data.labels.length) return empty(container, data.reason || "No se pudo interpretar la pregunta");
    const chartBox = document.createElement("div");
    chartBox.className = "qna-chart";
    renderColumn(chartBox, Object.assign({}, data, { type: "column_grouped" }), {});
    container.innerHTML = '<div class="qna-question">' + esc(question) + "</div>";
    container.appendChild(chartBox);
  }

  function render(container, data) {
    if (!container) return;
    container.classList.add("chart");
    if (!data) return empty(container, "Widget sin datos");
    if (data.empty) return empty(container, data.reason);
    const type = data.type || "column_grouped";
    if (["table", "matrix"].includes(type)) return renderTable(container, data);
    if (type === "decomposition" || type === "decomp_tree") return renderHierarchy(container, data);
    if (["kpi", "card"].includes(type)) return renderKpi(container, data);
    if (type === "multi_row") return renderMultiRow(container, data);
    if (type === "combo") return renderCombo(container, data);
    if (type === "line") return renderLine(container, data, {});
    if (type === "area") return renderLine(container, data, { area: true });
    if (type === "area_stacked") return renderLine(container, data, { area: true, stacked: true });
    if (type === "scatter" || type === "bubble") return renderScatter(container, data);
    if (type === "waterfall") return renderWaterfall(container, data);
    if (type === "funnel") return renderFunnel(container, data);
    if (type === "pie" || type === "doughnut") return renderPie(container, data);
    if (type === "treemap") return renderTreemap(container, data);
    if (type === "gauge") return renderGauge(container, data);
    if (type === "pareto") return renderPareto(container, data);
    if (type === "correlation") return renderCorrelation(container, data);
    if (type === "key_influencers") return renderInfluencers(container, data);
    if (type === "qna") return renderQna(container, data);
    if (["map_basic", "map_choropleth", "map_bubble", "map_arcgis"].includes(type)) return renderMap(container, data);
    if (type === "slicer") return renderSlicer(container, data);
    if (type === "filter_panel") return renderFilterPanel(container, data);
    if (["nav_buttons", "bookmark", "tooltip"].includes(type)) return renderInteraction(container, data);
    if (type === "bar_stacked") return renderHorizontal(container, data, { stacked: true });
    if (type === "bar_100") return renderHorizontal(container, data, { stacked: true, percent: true });
    if (type === "bar_grouped") return renderHorizontal(container, data, {});
    if (type === "column_stacked") return renderColumn(container, data, { stacked: true });
    if (type === "column_100") return renderColumn(container, data, { stacked: true, percent: true });
    return renderColumn(container, data, {});
  }

  window.BICharts = { render: render, format: format, esc: esc };
})();
