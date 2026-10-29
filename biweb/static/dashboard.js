/* Capa de UI: alterna diseno (autoria) y visualizacion (solo lectura). */
(function () {
  "use strict";

  const cfg = window.BIWEB || {};
  const dashboardId = cfg.dashboardId;
  const state = {
    mode: cfg.initialMode === "design" && cfg.designEnabled && cfg.canEdit ? "design" : "view",
    data: null,
    editingWidget: null,
    editingDataset: null,
    editingConnection: null,
    editingModel: null,
    editingScript: null,
    filters: {},
    tables: [],
    tablesConnection: null,
    pendingLayout: null,
    pendingModelId: null,
    modelRelated: [],
    widgetMeasureRelated: [],
    modelExpanded: {},
    widgetMeasureExpanded: {},
    loading: false,
    designPanel: "visualizations",
  };

  const $ = (selector) => document.querySelector(selector);
  const $$ = (selector, root) => Array.from((root || document).querySelectorAll(selector));
  const esc = (window.BICharts && window.BICharts.esc) || ((v) => String(v == null ? "" : v));

  const canvas = $("#canvas");
  const shell = $("#shell");
  const panel = $("#design-panel");
  const sampleCache = new Map();

  // ------------------------------------------------------------- utilidades
  let toastTimer = null;
  function toast(message, kind) {
    const box = $("#toast");
    if (!box) return;
    box.textContent = message;
    box.className = "toast " + (kind || "info");
    box.hidden = false;
    clearTimeout(toastTimer);
    toastTimer = setTimeout(() => {
      box.hidden = true;
    }, 4200);
  }

  function fail(err) {
    console.error(err);
    toast(err && err.message ? err.message : "Error inesperado", "error");
  }

  function designHeaders() {
    const headers = { "Content-Type": "application/json" };
    const meta = document.querySelector('meta[name="csrf-token"]');
    if (meta) headers["X-CSRF-Token"] = meta.content;
    if (state.mode === "design") headers["X-BI-Mode"] = "design";
    const token = localStorage.getItem("biweb-design-token");
    if (token) headers["X-Design-Token"] = token;
    return headers;
  }

  async function api(path, options, retried) {
    const opts = Object.assign({}, options || {});
    opts.headers = Object.assign(designHeaders(), opts.headers || {});
    if (opts.body instanceof FormData) {
      delete opts.headers["Content-Type"];
    } else if (opts.body && typeof opts.body !== "string") {
      opts.body = JSON.stringify(opts.body);
    }
    const res = await fetch(path, opts);
    let body = null;
    try {
      body = await res.json();
    } catch (err) {
      body = null;
    }
    if (!res.ok) {
      const error = new Error((body && body.error) || res.statusText || "Error " + res.status);
      error.code = body && body.code;
      error.status = res.status;
      if (error.code === "design_token" && !retried) {
        const token = window.prompt("Este servidor exige un token de diseno:");
        if (token) {
          localStorage.setItem("biweb-design-token", token);
          const input = $("#design-token");
          if (input) input.value = token;
          return api(path, options, true);
        }
      }
      throw error;
    }
    return body;
  }

  function option(value, label, selected) {
    const opt = document.createElement("option");
    opt.value = value == null ? "" : String(value);
    opt.textContent = label == null ? String(value) : label;
    if (selected != null && String(selected) === String(opt.value)) opt.selected = true;
    return opt;
  }

  function fillSelect(select, items, options) {
    const settings = options || {};
    if (!select) return;
    const previous = settings.value != null ? settings.value : select.value;
    select.innerHTML = "";
    if (settings.placeholder != null) select.appendChild(option("", settings.placeholder, ""));
    items.forEach((item) => select.appendChild(option(item.value, item.label, previous)));
    if (settings.placeholder == null && !select.value && items.length) select.value = String(items[0].value);
  }

  function datasetFields(datasetId) {
    const datasets = (state.data && state.data.datasets) || [];
    const dataset = datasets.find((d) => String(d.id) === String(datasetId));
    return (dataset && dataset.fields) || [];
  }

  function datasetById(datasetId) {
    const datasets = (state.data && state.data.datasets) || [];
    return datasets.find((d) => String(d.id) === String(datasetId)) || null;
  }

  // ------------------------------------------------ contexto de medidas Python
  function insertAtCursor(selector, text) {
    const area = $(selector);
    if (!area) return;
    const start = area.selectionStart == null ? area.value.length : area.selectionStart;
    const end = area.selectionEnd == null ? area.value.length : area.selectionEnd;
    const before = area.value.slice(0, start);
    const after = area.value.slice(end);
    const pad = before && !/\s$/.test(before) ? " " : "";
    area.value = before + pad + text + after;
    const cursor = (before + pad + text).length;
    area.focus();
    area.setSelectionRange(cursor, cursor);
    area.dispatchEvent(new Event("input"));
  }

  function insertMeasureSnippet(text) {
    insertAtCursor("#w-measure-expression", text);
  }

  function insertModelSnippet(text) {
    insertAtCursor("#model-expression", text);
  }

  const JOIN_TYPES = ["inner", "left", "right", "outer"];

  function normalizeJoinType(value) {
    const how = String(value || "inner").toLowerCase();
    return JOIN_TYPES.includes(how) ? how : "inner";
  }

  function normalizeRelatedTables(raw) {
    if (!Array.isArray(raw)) return [];
    const out = [];
    const usedAliases = new Set();
    raw.forEach((entry) => {
      const id = entry && typeof entry === "object" ? entry.id : entry;
      const numericId = Number(id);
      if (!Number.isFinite(numericId) || numericId <= 0) return;
      let alias = entry && typeof entry === "object" ? String(entry.alias || "") : "";
      if (!/^t(?:[2-9]|[1-9]\d+)$/.test(alias) || usedAliases.has(alias)) {
        alias = "";
      }
      if (!alias) {
        let number = 2;
        while (usedAliases.has("t" + number)) number += 1;
        alias = "t" + number;
      }
      usedAliases.add(alias);
      out.push({
        id: numericId,
        alias: alias,
        left_key: entry && typeof entry === "object" ? String(entry.left_key || entry.primary_key || "") : "",
        right_key: entry && typeof entry === "object" ? String(entry.right_key || entry.related_key || "") : "",
        how: normalizeJoinType(entry && typeof entry === "object" ? entry.how || entry.join : "inner"),
      });
    });
    return out;
  }

  function nextRelatedAlias(related) {
    const used = new Set((related || []).map((item) => item.alias));
    let number = 2;
    while (used.has("t" + number)) number += 1;
    return "t" + number;
  }

  function relatedAliasFor(related, datasetId) {
    const found = (related || []).find((item) => String(item.id) === String(datasetId));
    return found ? found.alias : "";
  }

  function relatedEntryFor(related, datasetId) {
    return (related || []).find((item) => String(item.id) === String(datasetId)) || null;
  }

  function commonJoinKeys(primaryId, relatedId) {
    const primaryFields = datasetFields(primaryId) || [];
    const relatedFields = datasetFields(relatedId) || [];
    const relatedNames = new Set(relatedFields.map((field) => field.name));
    const common = primaryFields.filter((field) => relatedNames.has(field.name));
    const preferred = ["id", "codigo", "code", "clave", "key", "cliente_id", "customer_id"];
    const preferredMatch = common.find((field) => preferred.includes(String(field.name).toLowerCase()));
    const chosen = preferredMatch || common[0];
    return chosen ? { left_key: chosen.name, right_key: chosen.name } : { left_key: "", right_key: "" };
  }

  function withJoinDefaults(primaryId, related) {
    return (related || []).map((entry) => {
      if (entry.left_key || entry.right_key) {
        return Object.assign({}, entry, {
          left_key: entry.left_key || entry.right_key,
          right_key: entry.right_key || entry.left_key,
        });
      }
      return Object.assign({}, entry, commonJoinKeys(primaryId, entry.id));
    });
  }

  function setRelatedSelection(related, primaryId, datasetId, selected) {
    const current = related || [];
    const exists = current.some((item) => String(item.id) === String(datasetId));
    if (selected && !exists) {
      const keys = commonJoinKeys(primaryId, datasetId);
      return current.concat([
        {
          id: Number(datasetId),
          alias: nextRelatedAlias(current),
          left_key: keys.left_key,
          right_key: keys.right_key,
          how: "inner",
        },
      ]);
    }
    if (!selected && exists) {
      return current.filter((item) => String(item.id) !== String(datasetId));
    }
    return current;
  }

  function updateRelatedJoin(related, datasetId, patch) {
    return (related || []).map((item) => {
      if (String(item.id) !== String(datasetId)) return item;
      return Object.assign({}, item, patch || {});
    });
  }

  function joinExpression(entry, source) {
    if (!entry) return null;
    const left = String(entry.left_key || entry.right_key || "").trim();
    const right = String(entry.right_key || entry.left_key || "").trim();
    if (!left || !right) return null;
    const args = [source || "rows", entry.alias, JSON.stringify(left), JSON.stringify(right)];
    const how = normalizeJoinType(entry.how);
    if (how !== "inner") args.push(JSON.stringify(how));
    return "merge(" + args.join(", ") + ")";
  }

  function chainedJoinExpression(related, source) {
    let expression = source || "rows";
    let applied = 0;
    (related || []).forEach((entry) => {
      const next = joinExpression(entry, expression);
      if (!next) return;
      expression = next;
      applied += 1;
    });
    return applied ? expression : null;
  }

  function relatedConfig(related) {
    return (related || []).map((item) => ({
      id: item.id,
      alias: item.alias,
      left_key: item.left_key || "",
      right_key: item.right_key || "",
      how: normalizeJoinType(item.how),
    }));
  }

  function modelTableSources(primaryId, related) {
    const sources = [];
    const primary = datasetById(primaryId);
    if (primary) sources.push({ dataset: primary, alias: "rows", primary: true });
    (related || []).forEach((item) => {
      if (String(item.id) === String(primaryId)) return;
      const dataset = datasetById(item.id);
      if (dataset) sources.push({ dataset: dataset, alias: item.alias, primary: false });
    });
    return sources;
  }

  function parseQuickFieldValue(value) {
    try {
      const parsed = JSON.parse(value);
      if (Array.isArray(parsed) && parsed.length === 2) {
        return { alias: String(parsed[0]), field: String(parsed[1]) };
      }
    } catch (err) {
      // compatibilidad con valores simples anteriores
    }
    return { alias: "rows", field: value == null ? "" : String(value) };
  }

  function fillQuickFieldSelect(select, sources) {
    if (!select) return;
    const previous = select.value;
    select.innerHTML = "";
    const usable = (sources || []).filter((source) => (source.dataset.fields || []).length);
    if (!usable.length) {
      select.appendChild(option("", "Sin campos", ""));
      return;
    }
    usable.forEach((source) => {
      const group = document.createElement("optgroup");
      group.label = (source.primary ? "Principal" : source.alias) + " · " + source.dataset.name;
      (source.dataset.fields || []).forEach((field) => {
        const value = JSON.stringify([source.alias, field.name]);
        group.appendChild(option(value, field.name + " (" + (field.type || "text") + ")", previous));
      });
      select.appendChild(group);
    });
    if (!select.value && select.options.length) select.selectedIndex = 0;
  }

  function renderTableTree(container, options) {
    if (!container) return;
    const settings = options || {};
    const datasets = (state.data && state.data.datasets) || [];
    const primaryId = settings.primaryId == null ? "" : String(settings.primaryId);
    const primaryExists = datasets.some((dataset) => String(dataset.id) === primaryId);
    const related = settings.related || [];
    const expanded = settings.expanded || {};
    container.innerHTML = "";
    if (settings.focusEl) {
      const previousFocus = settings.focusEl.value;
      settings.focusEl.innerHTML = "";
      settings.focusEl.appendChild(option("", "Todas las tablas", ""));
      datasets.forEach((dataset) => {
        settings.focusEl.appendChild(option(dataset.id, dataset.name, previousFocus));
      });
    }
    if (!primaryExists) {
      container.innerHTML = '<p class="hint">Selecciona un dataset principal para ver las tablas y columnas.</p>';
      if (settings.metaEl) settings.metaEl.textContent = "Sin tablas";
      return;
    }
    datasets.forEach((dataset) => {
      const isPrimary = String(dataset.id) === primaryId;
      const relatedAlias = relatedAliasFor(related, dataset.id);
      const selected = isPrimary || Boolean(relatedAlias);
      const alias = isPrimary ? "t1" : relatedAlias;
      const expandedKey = String(dataset.id);
      const startsOpen = Object.prototype.hasOwnProperty.call(expanded, expandedKey)
        ? Boolean(expanded[expandedKey])
        : selected;
      const node = document.createElement("div");
      node.dataset.datasetId = String(dataset.id);
      node.className = "table-node" + (selected ? " selected" : "") + (isPrimary ? " primary" : "");
      const head = document.createElement("div");
      head.className = "table-node-head";
      const check = document.createElement("input");
      check.type = "checkbox";
      check.checked = selected;
      check.disabled = isPrimary;
      check.setAttribute("aria-label", "Usar tabla " + dataset.name);
      check.addEventListener("change", () => {
        expanded[expandedKey] = true;
        if (settings.onToggle) settings.onToggle(dataset.id, check.checked);
      });
      head.appendChild(check);
      const toggle = document.createElement("button");
      toggle.type = "button";
      toggle.className = "tree-toggle";
      toggle.setAttribute("aria-expanded", startsOpen ? "true" : "false");
      toggle.textContent = startsOpen ? "▾" : "▸";
      head.appendChild(toggle);
      const title = document.createElement("span");
      title.className = "table-node-title";
      title.textContent = dataset.name;
      head.appendChild(title);
      const badges = document.createElement("span");
      badges.className = "table-node-badges";
      if (alias) {
        const aliasBadge = document.createElement("span");
        aliasBadge.className = "alias-badge";
        aliasBadge.textContent = alias === "t1" ? "rows · t1" : alias;
        badges.appendChild(aliasBadge);
      }
      const fields = dataset.fields || [];
      const fieldBadge = document.createElement("span");
      fieldBadge.className = "id-badge";
      fieldBadge.textContent = fields.length + " col.";
      badges.appendChild(fieldBadge);
      head.appendChild(badges);
      if (selected) {
        const use = document.createElement("button");
        use.type = "button";
        use.className = "link tree-use";
        use.textContent = "Insertar tabla";
        use.addEventListener("click", () => {
          if (settings.onInsert) settings.onInsert(alias === "t1" ? "rows" : alias);
        });
        head.appendChild(use);
      }
      node.appendChild(head);
      const columns = document.createElement("div");
      columns.className = "table-columns";
      if (!fields.length) {
        const empty = document.createElement("p");
        empty.className = "hint";
        empty.textContent = "Sin columnas detectadas.";
        columns.appendChild(empty);
      }
      fields.forEach((field) => {
        const button = document.createElement("button");
        button.type = "button";
        button.className = "table-column type-" + (field.type || "text");
        button.innerHTML = "<span>" + esc(field.name) + "</span><small>" + esc(field.type || "text") + "</small>";
        button.title =
          "Insertar \"" +
          field.name +
          "\" de " +
          (alias === "t1" ? "rows" : alias);
        button.addEventListener("click", () => {
          if (settings.onInsert) settings.onInsert(JSON.stringify(field.name));
        });
        columns.appendChild(button);
      });
      columns.hidden = !startsOpen;
      const setOpen = (open) => {
        columns.hidden = !open;
        toggle.textContent = open ? "▾" : "▸";
        toggle.setAttribute("aria-expanded", open ? "true" : "false");
        expanded[expandedKey] = open;
      };
      toggle.addEventListener("click", (event) => {
        event.stopPropagation();
        setOpen(columns.hidden);
      });
      head.addEventListener("click", (event) => {
        if (event.target.closest("input, button, a")) return;
        setOpen(columns.hidden);
      });
      node.appendChild(columns);
      container.appendChild(node);
    });
    if (settings.metaEl) {
      const count = 1 + related.filter((item) => datasets.some((dataset) => String(dataset.id) === String(item.id))).length;
      settings.metaEl.textContent = count + (count === 1 ? " tabla" : " tablas");
    }
  }

  function focusTable(containerSelector, datasetId) {
    const container = $(containerSelector);
    if (!container || !datasetId) return;
    const node = container.querySelector('[data-dataset-id="' + CSS.escape(String(datasetId)) + '"]');
    if (!node) return;
    const toggle = node.querySelector(".tree-toggle");
    const columns = node.querySelector(".table-columns");
    if (toggle && columns && columns.hidden) toggle.click();
    node.classList.add("tree-focus");
    node.scrollIntoView({ block: "nearest", behavior: "smooth" });
    setTimeout(() => node.classList.remove("tree-focus"), 1400);
  }

  function renderJoinEditor(container, options) {
    if (!container) return;
    const settings = options || {};
    const primaryId = settings.primaryId;
    const related = settings.related || [];
    const primary = datasetById(primaryId);
    const currentRelated = () => (settings.getRelated ? settings.getRelated() : related);
    container.innerHTML = "";
    if (!primary || !related.length) return;
    const head = document.createElement("div");
    head.className = "join-head";
    head.innerHTML = "<span>Cruces configurados</span>";
    container.appendChild(head);
    related.forEach((entry) => {
      const dataset = datasetById(entry.id);
      if (!dataset) return;
      const card = document.createElement("div");
      card.className = "join-card";
      const cardHead = document.createElement("div");
      cardHead.className = "join-card-head";
      cardHead.innerHTML =
        '<span class="alias-badge">' +
        esc(entry.alias) +
        "</span><span>" +
        esc(dataset.name) +
        "</span><small class=\"hint\">" +
        (dataset.fields || []).length +
        " columnas</small>";
      card.appendChild(cardHead);
      const grid = document.createElement("div");
      grid.className = "join-grid";
      const left = document.createElement("label");
      left.appendChild(document.createTextNode("Llave en tabla principal"));
      left.appendChild(
        fieldSelect(
          (primary.fields || []).map((field) => field.name),
          entry.left_key,
          "Selecciona llave",
          (value) => settings.onChange && settings.onChange(entry.id, { left_key: value })
        )
      );
      const right = document.createElement("label");
      right.appendChild(document.createTextNode("Llave en " + entry.alias));
      right.appendChild(
        fieldSelect(
          (dataset.fields || []).map((field) => field.name),
          entry.right_key,
          "Selecciona llave",
          (value) => settings.onChange && settings.onChange(entry.id, { right_key: value })
        )
      );
      const how = document.createElement("label");
      how.appendChild(document.createTextNode("Tipo de cruce"));
      const howSelect = document.createElement("select");
      [
        ["inner", "Interior"],
        ["left", "Izquierda"],
        ["right", "Derecha"],
        ["outer", "Exterior"],
      ].forEach((pair) => howSelect.appendChild(option(pair[0], pair[1], entry.how)));
      howSelect.addEventListener("change", () => {
        if (settings.onChange) settings.onChange(entry.id, { how: howSelect.value });
      });
      how.appendChild(howSelect);
      grid.appendChild(left);
      grid.appendChild(right);
      grid.appendChild(how);
      card.appendChild(grid);
      const actions = document.createElement("div");
      actions.className = "join-actions";
      const insert = document.createElement("button");
      insert.type = "button";
      insert.className = "link";
      insert.textContent = "Insertar este cruce";
      insert.addEventListener("click", () => {
        const latest = relatedEntryFor(currentRelated(), entry.id) || entry;
        const expression = joinExpression(latest);
        if (!expression) {
          toast("Elige la llave de la tabla principal y la de " + entry.alias, "error");
          return;
        }
        if (settings.onInsert) settings.onInsert(expression);
      });
      actions.appendChild(insert);
      const remove = document.createElement("button");
      remove.type = "button";
      remove.className = "link danger";
      remove.textContent = "Quitar tabla";
      remove.addEventListener("click", () => {
        if (settings.onRemove) settings.onRemove(entry.id);
      });
      actions.appendChild(remove);
      card.appendChild(actions);
      container.appendChild(card);
    });
    const bulk = document.createElement("button");
    bulk.type = "button";
    bulk.className = "ghost";
    bulk.textContent = "Insertar cruce encadenado (" + related.length + " tabla(s))";
    bulk.addEventListener("click", () => {
      const expression = chainedJoinExpression(currentRelated());
      if (!expression) {
        toast("Configura las llaves de las tablas para generar el cruce", "error");
        return;
      }
      if (settings.onInsert) settings.onInsert(expression);
    });
    container.appendChild(bulk);
  }

  function fieldSelect(names, value, placeholder, onChange) {
    const select = document.createElement("select");
    select.appendChild(option("", placeholder, ""));
    (names || []).forEach((name) => select.appendChild(option(name, name, value)));
    select.value = value || "";
    select.addEventListener("change", () => onChange(select.value));
    return select;
  }

  function renderMeasureSample(data) {
    const box = $("#w-measure-sample");
    if (!box) return;
    box.hidden = false;
    box.innerHTML = "";
    const caption = document.createElement("p");
    caption.className = "hint";
    caption.textContent =
      "Muestra del dataframe: " +
      (data.rows ? data.rows.length : 0) +
      " fila(s)" +
      (data.truncated ? " (vista limitada)" : "");
    box.appendChild(caption);
    const table = document.createElement("div");
    box.appendChild(table);
    window.BICharts.render(table, {
      type: "table",
      columns: data.columns || [],
      rows: data.rows || [],
      format: { format: "number", decimals: 2 },
      truncated: false,
    });
  }

  function loadMeasureSample(datasetId) {
    const box = $("#w-measure-sample");
    if (!box) return;
    if (!datasetId) {
      box.hidden = true;
      box.innerHTML = "";
      return;
    }
    const key = String(datasetId);
    if (sampleCache.has(key)) {
      renderMeasureSample(sampleCache.get(key));
      return;
    }
    box.hidden = false;
    box.innerHTML = '<p class="hint">Cargando muestra del dataframe...</p>';
    api("/api/datasets/" + encodeURIComponent(key) + "/sample?limit=4")
      .then((data) => {
        sampleCache.set(key, data);
        if ($("#w-dataset") && String($("#w-dataset").value) === key) renderMeasureSample(data);
      })
      .catch((err) => {
        if ($("#w-dataset") && String($("#w-dataset").value) !== key) return;
        box.innerHTML = '<p class="hint">No se pudo cargar la muestra: ' + esc(err.message) + "</p>";
      });
  }

  function relatedSummary(related) {
    if (!related || !related.length) {
      return "Marca tablas adicionales para cruzarlas. Al desplegar cada tabla veras sus columnas.";
    }
    return (
      "Tablas cruzadas: " +
      related
        .map((item) => {
          const relatedDataset = datasetById(item.id);
          return item.alias + " = " + (relatedDataset ? relatedDataset.name : item.id);
        })
        .join(", ") +
      ". Usa esos alias en la expresion."
    );
  }

  function renderMeasureContext() {
    const name = $("#w-measure-dataset-name");
    const meta = $("#w-measure-dataset-meta");
    const tree = $("#w-measure-tables");
    const hint = $("#w-measure-fields-hint");
    if (!name || !meta || !tree || !hint) return;
    const datasetId = $("#w-dataset") ? $("#w-dataset").value : "";
    const dataset = datasetById(datasetId);
    if (!dataset) {
      name.textContent = "Sin dataset";
      meta.textContent = "Sin campos";
      tree.innerHTML = '<p class="hint">Selecciona un dataset principal para ver tablas y columnas.</p>';
      hint.textContent = "Selecciona un dataset para ver sus campos.";
      const focus = $("#w-measure-table-focus");
      if (focus) focus.innerHTML = "";
      const joins = $("#w-measure-joins");
      if (joins) joins.innerHTML = "";
      fillQuickFieldSelect($("#w-quick-field"), []);
      loadMeasureSample(null);
      return;
    }
    const filtered = state.widgetMeasureRelated.filter((item) => String(item.id) !== String(datasetId));
    state.widgetMeasureRelated = withJoinDefaults(datasetId, filtered);
    const related = state.widgetMeasureRelated;
    const sources = modelTableSources(datasetId, related);
    const fields = dataset.fields || [];
    name.textContent = dataset.name;
    meta.textContent = fields.length + " campos · " + (1 + related.length) + " tabla(s)";
    renderTableTree(tree, {
      primaryId: datasetId,
      related: related,
      expanded: state.widgetMeasureExpanded,
      focusEl: $("#w-measure-table-focus"),
      onToggle: (id, selected) => {
        state.widgetMeasureRelated = setRelatedSelection(
          state.widgetMeasureRelated,
          datasetId,
          id,
          selected
        );
        renderMeasureContext();
      },
      onInsert: (text) => insertMeasureSnippet(text),
    });
    hint.textContent = relatedSummary(related);
    renderJoinEditor($("#w-measure-joins"), {
      primaryId: datasetId,
      related: related,
      getRelated: () => state.widgetMeasureRelated,
      onChange: (id, patch) => {
        state.widgetMeasureRelated = updateRelatedJoin(state.widgetMeasureRelated, id, patch);
        hint.textContent = relatedSummary(state.widgetMeasureRelated);
      },
      onRemove: (id) => {
        state.widgetMeasureRelated = setRelatedSelection(
          state.widgetMeasureRelated,
          datasetId,
          id,
          false
        );
        renderMeasureContext();
      },
      onInsert: (text) => insertMeasureSnippet(text),
    });
    fillQuickFieldSelect($("#w-quick-field"), sources);
    loadMeasureSample(datasetId);
  }

  function insertWidgetQuickMeasure() {
    const parsed = parseQuickFieldValue($("#w-quick-field") ? $("#w-quick-field").value : "");
    const field = parsed.field;
    const op = $("#w-quick-op") ? $("#w-quick-op").value : "sum";
    if (!field) {
      toast("Elige un campo del dataframe", "error");
      return;
    }
    const functions = {
      sum: "sum_field",
      avg: "avg_field",
      count: "count_field",
      count_distinct: "distinct_field",
      min: "min_field",
      max: "max_field",
      median: "median_field",
      stdev: "stdev_field",
    };
    const tableVar = parsed.alias || "rows";
    const expression = (functions[op] || functions.sum) + "(" + tableVar + ", " + JSON.stringify(field) + ")";
    const area = $("#w-measure-expression");
    if (area) {
      area.value = expression;
      area.focus();
      area.setSelectionRange(expression.length, expression.length);
    }
    if ($("#w-measure-kind")) $("#w-measure-kind").value = "measure";
    if ($("#w-measure-name") && !$("#w-measure-name").value.trim()) {
      $("#w-measure-name").value = op + " " + field + (tableVar !== "rows" ? " · " + tableVar : "");
    }
    toast("Expresion insertada");
  }

  function positionMeasureTooltip() {
    const button = $("#w-measure-help");
    const tip = $("#w-measure-tooltip");
    if (!button || !tip || tip.hidden) return;
    const rect = button.getBoundingClientRect();
    const width = Math.min(340, window.innerWidth - 24);
    tip.style.maxWidth = width + "px";
    let left = rect.right - width;
    left = Math.max(12, Math.min(left, window.innerWidth - width - 12));
    let top = rect.bottom + 8;
    if (top + tip.offsetHeight > window.innerHeight - 12) {
      top = Math.max(12, rect.top - tip.offsetHeight - 8);
    }
    tip.style.left = left + "px";
    tip.style.top = top + "px";
  }

  function setMeasureTooltip(open) {
    const button = $("#w-measure-help");
    const tip = $("#w-measure-tooltip");
    if (!button || !tip) return;
    tip.hidden = !open;
    button.setAttribute("aria-expanded", open ? "true" : "false");
    if (open) positionMeasureTooltip();
  }

  function modelItemsFor(datasetId) {
    const items = (state.data && state.data.model_items) || [];
    if (!datasetId) return items;
    return items.filter((item) => String(item.dataset_id) === String(datasetId));
  }

  function modelKindLabel(kind) {
    const pairs = (state.data && state.data.model_kinds) || [];
    const found = pairs.find((pair) => pair[0] === kind);
    return found ? found[1] : kind;
  }

  function modelOutputFields(item) {
    if (!item) return [];
    const config = item.config || {};
    if (item.kind === "measure") return [{ name: item.name, type: "number" }];
    if (item.kind === "column") return [{ name: config.name || "calculada", type: "number" }];
    if (item.kind === "table_created") {
      const columns = config.columns || [];
      const sample = (config.rows || [])[0] || {};
      return columns.map((name) => ({
        name: name,
        type: typeof sample[name] === "number" ? "number" : "text",
      }));
    }
    return [];
  }

  function chartGroups() {
    return (state.data && state.data.chart_groups) || [];
  }

  function chartLabel(value) {
    for (const group of chartGroups()) {
      const found = (group.types || []).find((type) => type.value === value);
      if (found) return found.label;
    }
    return value;
  }

  function defaultChart() {
    const groups = chartGroups();
    return groups.length && groups[0].types.length ? groups[0].types[0].value : "table";
  }

  function normalizeChartType(value) {
    return value === "bar" ? "column_grouped" : value;
  }

  function renderChartOptions() {
    const select = $("#w-chart");
    const groups = chartGroups();
    if (!select || !groups.length) return;
    const previous = select.value;
    select.innerHTML = "";
    groups.forEach((group) => {
      const box = document.createElement("optgroup");
      box.label = group.name;
      (group.types || []).forEach((type) => box.appendChild(option(type.value, type.label, previous)));
      select.appendChild(box);
    });
    if (!select.value && groups[0] && groups[0].types.length) select.value = groups[0].types[0].value;
  }

  // ------------------------------------------------------------------- load
  async function load(silent) {
    if (!dashboardId) return;
    if (!silent) sampleCache.clear();
    state.loading = true;
    try {
      const path =
        state.mode === "design"
          ? "/api/dashboards/" + dashboardId + "/design"
          : "/api/dashboards/" + dashboardId + "/render";
      state.data = await api(path);
      renderAll();
      if (!silent) $("#stamp") && ($("#stamp").textContent = "Actualizado " + new Date().toLocaleTimeString("es-ES"));
    } catch (err) {
      if (!silent) fail(err);
    } finally {
      state.loading = false;
    }
  }

  // ---------------------------------------------------------------- render
  function renderAll() {
    const view = state.mode !== "design";
    shell.classList.toggle("view-mode", view);
    updateModeButtons();
    renderHeader();
    if (!view) renderDesignPanels();
    renderCanvas();
  }

  function renderHeader() {
    const dash = (state.data && state.data.dashboard) || {};
    const title = $("#dash-title");
    if (title) title.textContent = dash.name || "Tablero";
    const desc = $("#dash-description");
    if (desc) desc.textContent = dash.description || "Sin descripcion";
    document.title = (dash.name || "Tablero") + " · BI Web";
    const badge = $("#mode-badge");
    if (badge) {
      badge.textContent = viewLabel();
      badge.className = "badge " + (state.mode === "design" ? "badge-design" : "badge-view");
    }
  }

  function viewLabel() {
    return state.mode === "design" ? "Modo diseno" : "Solo visualizacion";
  }

  function updateModeButtons() {
    $$("#mode-switch [data-mode]").forEach((btn) => {
      const active = btn.dataset.mode === state.mode;
      btn.classList.toggle("active", active);
      btn.setAttribute("aria-pressed", active ? "true" : "false");
      if (btn.dataset.mode === "design" && (!cfg.designEnabled || !cfg.canEdit)) btn.disabled = true;
    });
  }

  function filteredChartData(widget, chart) {
    const datasetId = String(widget.dataset_id || chart.dataset_id || "");
    const filters = state.filters[datasetId];
    if (!filters || !Object.keys(filters).length) return chart;
    if (["slicer", "filter_panel"].includes(chart.type)) return chart;
    let out = chart;
    Object.keys(filters).forEach((field) => {
      const values = (filters[field] || []).map(String);
      if (!values.length) return;
      if (out.columns && out.rows) {
        out = Object.assign({}, out, {
          rows: out.rows.filter((row) => values.includes(String(row[field]))),
        });
      }
      if (out.labels && out.series && out.x === field) {
        const labels = out.labels;
        const series = out.series;
        const cumulative = out.cumulative;
        const keep = [];
        labels.forEach((label, index) => {
          if (values.includes(String(label))) keep.push(index);
        });
        out = Object.assign({}, out, {
          labels: keep.map((index) => labels[index]),
          series: series.map((item) => Object.assign({}, item, { data: keep.map((index) => item.data[index]) })),
        });
        if (cumulative) out.cumulative = keep.map((index) => cumulative[index]);
      }
    });
    return out;
  }

  function restoreFilterUi(widget, data, box) {
    const datasetId = String(widget.dataset_id || data.dataset_id || "");
    const filters = state.filters[datasetId] || {};
    if (data.type === "slicer") {
      const selected = (filters[data.field] || []).map(String);
      box.querySelectorAll("[data-slicer-value]").forEach((chip) => {
        chip.classList.toggle("active", selected.includes(String(chip.dataset.slicerValue)));
      });
    }
    if (data.type === "filter_panel") {
      box.querySelectorAll("[data-filter-field]").forEach((checkbox) => {
        const selected = (filters[checkbox.dataset.filterField] || []).map(String);
        checkbox.checked = selected.includes(String(checkbox.dataset.filterValue));
      });
    }
  }

  function applyFilterEvent(detail) {
    if (!detail) return;
    const datasetId = String(detail.dataset_id == null ? "" : detail.dataset_id);
    const field = detail.field;
    if (!datasetId || !field) return;
    const current = state.filters[datasetId] || {};
    const values = (detail.values || []).map(String);
    if (values.length) current[field] = values;
    else delete current[field];
    if (Object.keys(current).length) state.filters[datasetId] = current;
    else delete state.filters[datasetId];
    renderActiveFilters();
    renderCanvas();
  }

  function clampInt(value, min, max, fallback) {
    const number = parseInt(value, 10);
    if (!Number.isFinite(number)) return fallback;
    return Math.max(min, Math.min(max, number));
  }

  function applyWidgetLayout(card, widget) {
    const w = clampInt(widget.w, 1, 12, 3);
    const h = clampInt(widget.h, 1, 6, 2);
    const hasX = widget.x != null && widget.x !== "";
    const hasY = widget.y != null && widget.y !== "";
    const x = hasX ? clampInt(widget.x, 0, 12 - w, 0) : null;
    const y = hasY ? Math.max(0, clampInt(widget.y, 0, 999, 0)) : null;
    card.style.gridColumn = x == null ? "span " + w : x + 1 + " / span " + w;
    card.style.gridRow = y == null ? "span " + h : y + 1 + " / span " + h;
    return { x: x, y: y, w: w, h: h };
  }

  function saveWidgetLayout(card, widget, layout) {
    const payload = { x: layout.x, y: layout.y, w: layout.w, h: layout.h };
    return api("/api/widgets/" + widget.id + "/layout", { method: "PUT", body: payload })
      .then((row) => {
        widget.x = row.x;
        widget.y = row.y;
        widget.w = row.w;
        widget.h = row.h;
        applyWidgetLayout(card, widget);
        toast("Disposicion guardada");
      })
      .catch((err) => {
        fail(err);
        return load();
      });
  }

  function bindWidgetMove(card, head, widget) {
    head.classList.add("widget-drag");
    head.title = "Arrastra para mover el widget";
    head.addEventListener("pointerdown", (event) => {
      if (state.mode !== "design" || event.button !== 0) return;
      if (event.target.closest("button, a, input, select, textarea")) return;
      event.preventDefault();
      const rect = canvas.getBoundingClientRect();
      const gap = 14;
      const cellW = (rect.width - gap * 11) / 12;
      const rowH = 180;
      const startX = widget.x == null ? 0 : Number(widget.x);
      const startY = widget.y == null ? 0 : Number(widget.y);
      const w = clampInt(widget.w, 1, 12, 3);
      const h = clampInt(widget.h, 1, 6, 2);
      const originX = event.clientX;
      const originY = event.clientY;
      let preview = { x: startX, y: startY, w: w, h: h };
      let moved = false;
      card.classList.add("dragging");
      document.body.classList.add("widget-moving");

      const onMove = (moveEvent) => {
        const dx = Math.round((moveEvent.clientX - originX) / (cellW + gap));
        const dy = Math.round((moveEvent.clientY - originY) / (rowH + gap));
        const nx = Math.max(0, Math.min(12 - w, startX + dx));
        const ny = Math.max(0, startY + dy);
        if (nx === preview.x && ny === preview.y) return;
        moved = true;
        preview = { x: nx, y: ny, w: w, h: h };
        card.style.gridColumn = nx + 1 + " / span " + w;
        card.style.gridRow = ny + 1 + " / span " + h;
      };
      const onUp = () => {
        window.removeEventListener("pointermove", onMove);
        window.removeEventListener("pointerup", onUp);
        window.removeEventListener("pointercancel", onUp);
        card.classList.remove("dragging");
        document.body.classList.remove("widget-moving");
        if (moved) saveWidgetLayout(card, widget, preview);
      };
      window.addEventListener("pointermove", onMove);
      window.addEventListener("pointerup", onUp);
      window.addEventListener("pointercancel", onUp);
    });
  }

  function bindWidgetResize(card, handle, widget) {
    handle.addEventListener("pointerdown", (event) => {
      if (state.mode !== "design" || event.button !== 0) return;
      event.preventDefault();
      event.stopPropagation();
      const rect = canvas.getBoundingClientRect();
      const gap = 14;
      const cellW = (rect.width - gap * 11) / 12;
      const rowH = 180;
      const x = widget.x == null ? 0 : Number(widget.x);
      const y = widget.y == null ? 0 : Number(widget.y);
      const startW = clampInt(widget.w, 1, 12, 3);
      const startH = clampInt(widget.h, 1, 6, 2);
      const originX = event.clientX;
      const originY = event.clientY;
      let preview = { x: x, y: y, w: startW, h: startH };
      let moved = false;
      card.classList.add("resizing");
      document.body.classList.add("widget-moving");

      const onMove = (moveEvent) => {
        const dw = Math.round((moveEvent.clientX - originX) / (cellW + gap));
        const dh = Math.round((moveEvent.clientY - originY) / (rowH + gap));
        const w = Math.max(1, Math.min(12 - x, startW + dw));
        const h = Math.max(1, Math.min(6, startH + dh));
        if (w === preview.w && h === preview.h) return;
        moved = true;
        preview = { x: x, y: y, w: w, h: h };
        card.style.gridColumn = x + 1 + " / span " + w;
        card.style.gridRow = y + 1 + " / span " + h;
      };
      const onUp = () => {
        window.removeEventListener("pointermove", onMove);
        window.removeEventListener("pointerup", onUp);
        window.removeEventListener("pointercancel", onUp);
        card.classList.remove("resizing");
        document.body.classList.remove("widget-moving");
        if (moved) saveWidgetLayout(card, widget, preview);
      };
      window.addEventListener("pointermove", onMove);
      window.addEventListener("pointerup", onUp);
      window.addEventListener("pointercancel", onUp);
    });
  }

  function renderCanvas() {
    if (!canvas) return;
    canvas.innerHTML = "";
    const widgets = (state.data && state.data.widgets) || [];
    if (!widgets.length) {
      const box = document.createElement("div");
      box.className = "canvas-empty";
      box.innerHTML =
        "<h3>Este tablero esta vacio</h3><p>" +
        (state.mode === "design"
          ? "Abre Visualizaciones para agregar graficos, o Datos para administrar las fuentes."
          : "El autor aun no agrego widgets.") +
        "</p>";
      canvas.appendChild(box);
      return;
    }
    widgets.forEach((widget) => {
      const card = document.createElement("article");
      card.className = "widget";
      card.dataset.widgetId = widget.id;
      applyWidgetLayout(card, widget);

      const head = document.createElement("header");
      head.className = "widget-head";
      const title = document.createElement("h3");
      title.textContent = widget.title || "Widget";
      head.appendChild(title);

      if (state.mode === "design") {
        const actions = document.createElement("div");
        actions.className = "widget-actions";
        const edit = document.createElement("button");
        edit.type = "button";
        edit.className = "link";
        edit.dataset.widgetEdit = widget.id;
        edit.textContent = "Editar";
        const remove = document.createElement("button");
        remove.type = "button";
        remove.className = "link danger";
        remove.dataset.widgetDelete = widget.id;
        remove.textContent = "Eliminar";
        actions.appendChild(edit);
        actions.appendChild(remove);
        head.appendChild(actions);
        bindWidgetMove(card, head, widget);
      }
      card.appendChild(head);

      const chartBox = document.createElement("div");
      chartBox.className = "widget-chart";
      const chartData = filteredChartData(widget, widget.chart_data || {});
      window.BICharts.render(chartBox, chartData);
      restoreFilterUi(widget, chartData, chartBox);
      card.appendChild(chartBox);

      const foot = document.createElement("footer");
      foot.className = "widget-foot";
      const data = widget.chart_data || {};
      const bits = [];
      if (widget.dataset_name) bits.push(widget.dataset_name);
      if (data.agg) bits.push(data.agg);
      if (data.row_count != null) bits.push(data.row_count + " filas");
      foot.textContent = bits.join(" · ");
      card.appendChild(foot);

      if (state.mode === "design") {
        const resize = document.createElement("div");
        resize.className = "widget-resize";
        resize.title = "Arrastra para redimensionar";
        card.appendChild(resize);
        bindWidgetResize(card, resize, widget);
      }

      canvas.appendChild(card);
    });
  }

  // -------------------------------------------------------- panel de diseno
  function renderDesignPanels() {
    if (!state.data) return;
    renderDashboardForm();
    renderConnections();
    renderDatasets();
    renderImportPanel();
    renderPalette();
    renderTools();
    renderWidgetFormOptions();
    renderActiveFilters();
    const tokenBox = $("#token-box");
    if (tokenBox) tokenBox.hidden = !cfg.tokenRequired;
    const tokenInput = $("#design-token");
    if (tokenInput && !tokenInput.value) {
      tokenInput.value = localStorage.getItem("biweb-design-token") || "";
    }
  }

  function initializeDesignPanels() {
    const source = $("#design-source");
    if (!source) return;
    const destinations = {
      visualizations: $("#design-pane-visualizations"),
      data: $("#design-pane-data"),
      filters: $("#design-pane-filters"),
      dashboard: $("#design-pane-dashboard"),
    };
    const placements = [
      ["#palette-section", "visualizations"],
      ["#w-form", "visualizations"],
      ["#connections-section", "data"],
      ["#datasets-section", "data"],
      ["#import-section", "data"],
      ["#tools-section", "data"],
      ["#token-box", "dashboard"],
      ["#dashboard-section", "dashboard"],
      [".danger-zone", "dashboard"],
    ];
    placements.forEach(([selector, panelName]) => {
      const element = source.querySelector(selector);
      const destination = destinations[panelName];
      if (!element || !destination) return;
      const section = element.matches(".side-section") ? element : element.closest(".side-section");
      destination.appendChild(section || element);
    });
    source.remove();
    setDesignPanel(state.designPanel);
  }

  function setDesignPanel(name) {
    const panes = $$("[data-design-pane]");
    if (!panes.some((pane) => pane.dataset.designPane === name)) return;
    state.designPanel = name;
    $$("[data-design-panel]").forEach((button) => {
      const active = button.dataset.designPanel === name;
      button.classList.toggle("active", active);
      button.setAttribute("aria-pressed", active ? "true" : "false");
    });
    panes.forEach((pane) => {
      pane.hidden = pane.dataset.designPane !== name;
    });
  }

  function renderActiveFilters() {
    const list = $("#active-filter-list");
    const clearAll = $("#clear-filters");
    if (!list) return;
    list.innerHTML = "";
    const entries = Object.entries(state.filters).flatMap(([datasetId, fields]) =>
      Object.entries(fields).map(([field, values]) => ({ datasetId, field, values }))
    );
    if (clearAll) clearAll.disabled = entries.length === 0;
    if (!entries.length) {
      list.innerHTML = '<p class="hint">No hay filtros activos.</p>';
      return;
    }
    entries.forEach(({ datasetId, field, values }) => {
      const dataset = datasetById(datasetId);
      const item = document.createElement("div");
      item.className = "list-item active-filter";
      const detail = document.createElement("div");
      detail.className = "list-main";
      const title = document.createElement("strong");
      title.textContent = field;
      const description = document.createElement("small");
      description.textContent =
        (dataset ? dataset.name : "Dataset " + datasetId) +
        " · " +
        (values || []).join(", ");
      detail.append(title, description);
      const clear = document.createElement("button");
      clear.type = "button";
      clear.className = "link";
      clear.textContent = "Quitar";
      clear.dataset.filterClear = "field";
      clear.dataset.datasetId = datasetId;
      clear.dataset.filterField = field;
      clear.setAttribute("aria-label", "Quitar filtro " + field);
      item.append(detail, clear);
      list.appendChild(item);
    });
  }

  // ------------------------------------------------------------- paleta
  const CHART_ICONS = {
    table: '<rect x="3" y="4" width="18" height="16" rx="2"/><path d="M3 9h18M9 9v11M15 9v11"/>',
    number: '<path d="M6 20V10M4 12h4M13 20l3.5-10M12 20h5M19 7l2 2-2 2"/>',
    hbars: '<path d="M4 6h12M4 12h8M4 18h16"/>',
    vbars: '<path d="M5 20V10M11 20V4M17 20v-7M3 20h18"/>',
    line: '<path d="M3 17l5-6 4 3 5-8 4 4"/><path d="M3 20h18"/>',
    dots: '<circle cx="6" cy="16" r="2"/><circle cx="12" cy="9" r="2"/><circle cx="18" cy="14" r="2"/><path d="M3 20h18"/>',
    steps: '<path d="M4 17h4V9h4V5h8"/><path d="M3 20h18"/>',
    funnel: '<path d="M3 5h18l-6 7v7l-6 2v-9z"/>',
    pie: '<circle cx="12" cy="12" r="8"/><path d="M12 4v8l6 5"/>',
    treemap: '<rect x="3" y="4" width="8" height="7"/><rect x="13" y="4" width="8" height="4"/><rect x="13" y="10" width="8" height="10"/><rect x="3" y="13" width="8" height="7"/>',
    gauge: '<path d="M4 17a8 8 0 1 1 16 0"/><path d="M12 17l4-6"/>',
    spark: '<path d="M3 12h4l2-5 3 10 3-7 2 2h4"/>',
    question: '<circle cx="12" cy="12" r="9"/><path d="M9.5 9a2.5 2.5 0 1 1 4 2c-.9.7-1.5 1.2-1.5 2.5"/><path d="M12 17h.01"/>',
    pin: '<path d="M12 21s6-5.4 6-10a6 6 0 1 0-12 0c0 4.6 6 10 6 10z"/><circle cx="12" cy="11" r="2.2"/>',
    filter: '<path d="M4 5h16l-6 7v6l-4 2v-8z"/>',
    link: '<path d="M10 14a4 4 0 0 0 5.7 0l2.3-2.3a4 4 0 0 0-5.7-5.7L11 7.3"/><path d="M14 10a4 4 0 0 0-5.7 0L6 12.3a4 4 0 0 0 5.7 5.7L13 16.7"/>',
  };

  const CHART_HELP = {
    table: "Filas y columnas del dataset.",
    matrix: "Resumen cruzado por filas y columnas.",
    kpi: "Una metrica clave en una tarjeta.",
    card: "Resumen numerico con etiqueta.",
    multi_row: "Varias metricas en tarjetas.",
    decomposition: "Desglose jerarquico de una metrica.",
    decomp_tree: "Arbol de contribucion por dimensiones.",
    bar: "Barras horizontales para comparar categorias.",
    column: "Columnas verticales para comparar categorias.",
    combo: "Columnas y linea en el mismo eje.",
    line: "Evolucion de una metrica en el tiempo.",
    area: "Tendencia con area acumulada.",
    scatter: "Relacion entre dos metricas.",
    bubble: "Relacion con un tercer campo de tamano.",
    waterfall: "Aportes positivos y negativos.",
    funnel: "Etapas de un proceso.",
    pie: "Proporcion del total por categoria.",
    doughnut: "Proporcion del total con centro libre.",
    treemap: "Proporcion mediante areas anidadas.",
    gauge: "Avance frente a un objetivo.",
    pareto: "Contribucion ordenada con acumulado.",
    key_influencers: "Variables que mas influyen en una metrica.",
    qna: "Pregunta en lenguaje natural sobre el dataset.",
    correlation: "Matriz de correlacion entre metricas.",
    map_basic: "Puntos geograficos por latitud/longitud.",
    map_choropleth: "Regiones coloreadas por metrica.",
    map_bubble: "Burbujas geograficas por tamano.",
    map_arcgis: "Mapa con capas externas.",
    slicer: "Filtro de una dimension para el tablero.",
    filter_panel: "Panel de varios filtros.",
    nav_buttons: "Botones de navegacion entre tableros.",
    bookmark: "Guarda y restaura el estado de filtros.",
    tooltip: "Nota o ayuda contextual.",
  };

  function chartIcon(chart) {
    const type = String(chart || "");
    let key = "vbars";
    if (["table", "matrix", "decomposition", "decomp_tree"].includes(type)) key = "table";
    else if (["kpi", "card", "multi_row"].includes(type)) key = "number";
    else if (type === "qna") key = "question";
    else if (type === "correlation") key = "table";
    else if (type.startsWith("bar")) key = "hbars";
    else if (type.startsWith("column") || type.startsWith("combo")) key = "vbars";
    else if (type.startsWith("line") || type.startsWith("area")) key = "line";
    else if (["scatter", "bubble"].includes(type)) key = "dots";
    else if (type === "waterfall") key = "steps";
    else if (type === "funnel") key = "funnel";
    else if (["pie", "doughnut"].includes(type)) key = "pie";
    else if (type === "treemap") key = "treemap";
    else if (["gauge", "pareto"].includes(type)) key = "gauge";
    else if (type === "key_influencers") key = "spark";
    else if (type.startsWith("map")) key = "pin";
    else if (["slicer", "filter_panel"].includes(type)) key = "filter";
    else if (["nav_buttons", "bookmark", "tooltip"].includes(type)) key = "link";
    return (
      '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" ' +
      'stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">' +
      (CHART_ICONS[key] || CHART_ICONS.vbars) +
      "</svg>"
    );
  }

  function chartHelp(chart, groupName) {
    return CHART_HELP[chart] || (groupName ? groupName + ": visualizacion del dataset." : "Visualizacion del dataset.");
  }

  function defaultSize(chart) {
    if (["table", "matrix", "correlation", "decomposition", "decomp_tree"].includes(chart)) {
      return { w: 12, h: 3 };
    }
    if (chart.startsWith("map")) return { w: 6, h: 4 };
    if (["kpi", "card", "multi_row", "gauge", "slicer", "filter_panel", "nav_buttons", "bookmark", "tooltip"].includes(chart)) {
      return { w: 3, h: 2 };
    }
    if (["line", "area", "area_stacked", "scatter", "bubble", "combo", "combo_dual"].includes(chart)) {
      return { w: 6, h: 3 };
    }
    return { w: 4, h: 3 };
  }

  function renderPalette() {
    const host = $("#chart-palette");
    if (!host) return;
    host.innerHTML = "";
    const groups = chartGroups();
    if (!groups.length) {
      host.innerHTML = '<p class="hint">Sin tipos de grafico disponibles.</p>';
      return;
    }
    groups.forEach((group) => {
      const title = document.createElement("div");
      title.className = "palette-group";
      title.textContent = group.name;
      host.appendChild(title);
      (group.types || []).forEach((type) => {
        const button = document.createElement("button");
        button.type = "button";
        button.className = "palette-item";
        button.draggable = true;
        button.dataset.chartType = type.value;
        button.innerHTML = chartIcon(type.value) + "<span>" + esc(type.label) + "</span>";
        button.addEventListener("click", () => beginWidgetFromPalette(type.value));
        button.addEventListener("dragstart", (event) => {
          state.paletteDragging = true;
          event.dataTransfer.effectAllowed = "copy";
          event.dataTransfer.setData("application/x-biweb-chart", type.value);
          event.dataTransfer.setData("text/plain", type.value);
        });
        button.addEventListener("dragend", () => {
          state.paletteDragging = false;
          canvas && canvas.classList.remove("drop-target");
        });
        button.addEventListener("mouseenter", (event) =>
          showPaletteTip(event, type.label, chartHelp(type.value, group.name))
        );
        button.addEventListener("mousemove", (event) => positionPaletteTip(event));
        button.addEventListener("mouseleave", hidePaletteTip);
        host.appendChild(button);
      });
    });
  }

  function showPaletteTip(event, label, text) {
    const tip = $("#palette-tooltip");
    if (!tip) return;
    tip.innerHTML = "<strong>" + esc(label) + "</strong>" + esc(text);
    tip.hidden = false;
    positionPaletteTip(event);
  }

  function positionPaletteTip(event) {
    const tip = $("#palette-tooltip");
    if (!tip || tip.hidden) return;
    const pad = 10;
    const width = tip.offsetWidth || 220;
    const height = tip.offsetHeight || 60;
    let left = event.clientX + 14;
    let top = event.clientY + 14;
    if (left + width > window.innerWidth - pad) left = event.clientX - width - 14;
    if (top + height > window.innerHeight - pad) top = event.clientY - height - 14;
    tip.style.left = Math.max(pad, left) + "px";
    tip.style.top = Math.max(pad, top) + "px";
  }

  function hidePaletteTip() {
    const tip = $("#palette-tooltip");
    if (tip) tip.hidden = true;
  }

  function beginWidgetFromPalette(chart, layout) {
    if (state.paletteDragging) return;
    resetWidgetForm();
    state.pendingLayout = layout || null;
    const size = defaultSize(chart);
    let w = layout ? layout.w : size.w;
    let h = layout ? layout.h : size.h;
    w = Math.max(1, Math.min(12, w || 3));
    h = Math.max(1, Math.min(6, h || 2));
    const x = layout ? Math.max(0, Math.min(12 - w, layout.x || 0)) : "";
    const y = layout ? Math.max(0, layout.y || 0) : "";
    renderChartOptions();
    const select = $("#w-chart");
    if (select && Array.prototype.some.call(select.options, (opt) => opt.value === chart)) {
      select.value = chart;
    }
    const datasets = (state.data && state.data.datasets) || [];
    const standalone = ["nav_buttons", "bookmark", "tooltip"].includes(chart);
    if (datasets.length) {
      $("#w-dataset").value = datasets[0].id;
    } else if (!standalone) {
      toast("Crea un dataset antes de configurar este grafico", "error");
    }
    $("#w-title").value = chartLabel(chart);
    $("#w-pos-x").value = x;
    $("#w-pos-y").value = y;
    $("#w-w").value = w;
    $("#w-h").value = h;
    renderWidgetFormOptions();
    applyChartTypeUI();
    const form = $("#w-form");
    if (form) {
      form.scrollIntoView({ behavior: "smooth", block: "center" });
      form.classList.add("palette-focus");
      setTimeout(() => form.classList.remove("palette-focus"), 1200);
    }
    const title = $("#w-title");
    if (title) title.focus();
    toast("Ajusta la configuracion y guarda el widget");
  }

  function layoutFromPointer(event) {
    if (!canvas) return { x: 0, y: 0 };
    const rect = canvas.getBoundingClientRect();
    const gap = 14;
    const cellW = (rect.width - gap * 11) / 12;
    const rowH = 180;
    const x = Math.max(0, Math.min(11, Math.floor((event.clientX - rect.left) / (cellW + gap))));
    const y = Math.max(0, Math.floor((event.clientY - rect.top) / (rowH + gap)));
    return { x: x, y: y };
  }

  // ------------------------------------------------- importacion de tablas
  function renderImportPanel() {
    const select = $("#imp-connection");
    if (!select) return;
    const connections = (state.data && state.data.connections) || [];
    const current = state.tablesConnection || select.value;
    fillSelect(
      select,
      connections.map((c) => ({ value: c.id, label: c.name + " (" + (c.kind || "sql") + ")" })),
      { placeholder: "Selecciona una fuente", value: current }
    );
    if (current && connections.some((c) => String(c.id) === String(current))) {
      select.value = String(current);
    }
    renderTables();
    renderScripts();
  }

  function aliasFor(connectionId, table) {
    const aliases = (state.data && state.data.table_aliases) || [];
    const found = aliases.find(
      (item) => String(item.connection_id) === String(connectionId) && item.table_name === table
    );
    return found ? found.alias : "";
  }

  function renderTables() {
    const host = $("#imp-tables");
    if (!host) return;
    host.innerHTML = "";
    if (!state.tables.length) {
      host.innerHTML =
        '<p class="hint">Selecciona una fuente y pulsa "Listar tablas".</p>';
      return;
    }
    state.tables.forEach((table) => {
      const row = document.createElement("div");
      row.className = "table-row";
      const name = document.createElement("span");
      name.className = "table-name";
      name.textContent = table;
      name.title = table;
      const input = document.createElement("input");
      input.placeholder = "alias";
      input.value = aliasFor(state.tablesConnection, table);
      input.dataset.aliasInput = table;
      const canAlias = !state.data || state.data.can_manage_connections !== false;
      const canDataset = !state.data || state.data.can_manage_datasets !== false;
      row.appendChild(name);
      if (canAlias) row.append(input);
      if (canAlias) {
        const save = document.createElement("button");
        save.type = "button";
        save.className = "link";
        save.dataset.aliasSave = table;
        save.textContent = "Alias";
        row.appendChild(save);
      }
      if (canDataset) {
        const use = document.createElement("button");
        use.type = "button";
        use.className = "link";
        use.dataset.tableDataset = table;
        use.textContent = "Dataset";
        row.appendChild(use);
      }
      host.appendChild(row);
    });
  }

  function loadTables() {
    const select = $("#imp-connection");
    const connectionId = select ? Number(select.value) : 0;
    if (!connectionId) {
      toast("Selecciona una fuente", "error");
      return;
    }
    state.tablesConnection = connectionId;
    const host = $("#imp-tables");
    if (host) host.innerHTML = '<p class="hint">Leyendo tablas...</p>';
    api("/api/connections/" + connectionId + "/tables")
      .then((res) => {
        state.tables = res.tables || [];
        renderTables();
      })
      .catch((err) => {
        state.tables = [];
        renderTables();
        fail(err);
      });
  }

  function saveTableAlias(table) {
    const row = $("#imp-tables").querySelector('[data-alias-input="' + CSS.escape(table) + '"]');
    const alias = row ? row.value.trim() : "";
    api("/api/tables/alias", {
      method: "PUT",
      body: { connection_id: state.tablesConnection, table: table, alias: alias },
    })
      .then((res) => {
        state.data.table_aliases = res.aliases || [];
        renderTables();
        toast(alias ? "Alias guardado" : "Alias eliminado");
      })
      .catch(fail);
  }

  function useTableAsDataset(table) {
    const alias = aliasFor(state.tablesConnection, table);
    const conn = $("#ds-connection");
    if (!conn) return;
    resetDatasetForm();
    conn.value = String(state.tablesConnection);
    $("#ds-name").value = alias || table;
    $("#ds-sql").value = "SELECT * FROM " + table;
    const form = $("#ds-form");
    if (form) form.scrollIntoView({ behavior: "smooth", block: "center" });
    toast("Revisa el SQL y guarda el dataset");
  }

  // ----------------------------------------------------- scripts de API
  function renderScripts() {
    const select = $("#imp-script");
    if (!select) return;
    const items = (state.data && state.data.api_scripts) || [];
    fillSelect(
      select,
      items.map((item) => ({ value: item.id, label: item.name })),
      { placeholder: "Nuevo script" }
    );
    if (state.editingScript) {
      const exists = items.some((item) => String(item.id) === String(state.editingScript));
      if (exists) select.value = String(state.editingScript);
    }
  }

  function fillScript(script) {
    state.editingScript = script ? script.id : null;
    $("#imp-script-name").value = script ? script.name || "" : "";
    $("#imp-script-desc").value = script ? script.description || "" : "";
    $("#imp-script-code").value = script ? script.code || "" : "";
    if (!script) $("#imp-script-result").hidden = true;
    const select = $("#imp-script");
    if (select) select.value = script ? String(script.id) : "";
  }

  function saveScript() {
    const name = $("#imp-script-name").value.trim();
    const description = $("#imp-script-desc").value.trim();
    const code = $("#imp-script-code").value.trim();
    if (!name || !code) {
      toast("Nombre y codigo son obligatorios", "error");
      return;
    }
    const request = state.editingScript
      ? api("/api/import/scripts/" + state.editingScript, {
          method: "PUT",
          body: { name: name, description: description, code: code },
        })
      : api("/api/import/scripts", {
          method: "POST",
          body: { name: name, description: description, code: code },
        });
    request
      .then((row) => {
        state.editingScript = row.id;
        toast("Script guardado");
        return load();
      })
      .catch(fail);
  }

  function deleteScript() {
    if (!state.editingScript) {
      toast("Selecciona un script guardado", "error");
      return;
    }
    if (!window.confirm("¿Eliminar este script de API?")) return;
    api("/api/import/scripts/" + state.editingScript, { method: "DELETE" })
      .then(() => {
        fillScript(null);
        toast("Script eliminado");
        return load();
      })
      .catch(fail);
  }

  function runScript(preview) {
    const code = $("#imp-script-code").value.trim();
    if (!code) {
      toast("Escribe el codigo del script", "error");
      return;
    }
    const name = $("#imp-script-name").value.trim() || "api_import";
    const table = $("#imp-script-table").value.trim();
    const out = $("#imp-script-result");
    if (out) {
      out.hidden = false;
      out.className = "result";
      out.textContent = preview ? "Ejecutando y leyendo muestra..." : "Ejecutando e importando...";
    }
    api("/api/import/script/run", {
      method: "POST",
      body: { code: code, name: name, table: table, preview: !!preview },
    })
      .then((res) => {
        if (preview) {
          if (out) {
            out.className = "result ok";
            out.textContent =
              res.row_count +
              " filas · " +
              res.columns.length +
              " columnas · " +
              res.elapsed_ms +
              " ms\n" +
              res.columns.join(", ") +
              "\n\n" +
              JSON.stringify(res.rows, null, 2);
          }
          toast("Vista previa lista");
          return null;
        }
        if (out) {
          out.className = "result ok";
          out.textContent =
            "Tabla " + res.table.table + ": " + res.table.rows + " filas importadas.";
        }
        toast("Datos importados desde la API");
        return load();
      })
      .catch((err) => {
        if (out) {
          out.className = "result error";
          out.textContent = err.message;
        }
        fail(err);
      });
  }

  function submitFileImport(event) {
    event.preventDefault();
    const input = $("#imp-file");
    const file = input && input.files && input.files[0];
    if (!file) {
      toast("Selecciona un archivo", "error");
      return;
    }
    const out = $("#imp-file-result");
    if (out) {
      out.hidden = false;
      out.className = "result";
      out.textContent = "Importando " + file.name + "...";
    }
    const formData = new FormData();
    formData.append("file", file);
    formData.append("name", $("#imp-name").value.trim());
    formData.append("table", $("#imp-table").value.trim());
    api("/api/import/file", { method: "POST", body: formData })
      .then((res) => {
        if (out) {
          out.className = "result ok";
          out.textContent =
            "Tabla " + res.table.table + ": " + res.table.rows + " filas · " +
            res.table.columns.length + " columnas · " + res.elapsed_ms + " ms";
        }
        toast("Archivo importado");
        return load();
      })
      .catch((err) => {
        if (out) {
          out.className = "result error";
          out.textContent = err.message;
        }
        fail(err);
      });
  }

  function renderDashboardForm() {
    const dash = state.data.dashboard || {};
    const name = $("#dash-name");
    if (name && document.activeElement !== name) name.value = dash.name || "";
    const desc = $("#dash-desc");
    if (desc && desc.tagName === "TEXTAREA" && document.activeElement !== desc) desc.value = dash.description || "";
  }

  function renderConnections() {
    const list = $("#conn-list");
    const connections = state.data.connections || [];
    if (list) {
      list.innerHTML = "";
      if (!connections.length) {
        list.innerHTML = '<p class="hint">Sin conexiones. Agrega una abajo.</p>';
      }
      connections.forEach((conn) => {
        const item = document.createElement("div");
        item.className = "list-item";
        const detail =
          conn.kind === "sqlite"
            ? conn.config.path || ""
            : [conn.config.host, conn.config.database].filter(Boolean).join(" / ");
        item.innerHTML =
          '<div class="list-main"><strong>' +
          esc(conn.name) +
          '</strong><small>' +
          esc(conn.kind) +
          (detail ? " · " + esc(detail) : "") +
          "</small></div>" +
          '<div class="row"><button type="button" class="link" data-conn-edit="' +
          conn.id +
          '">Editar</button><button type="button" class="link danger" data-conn-delete="' +
          conn.id +
          '">Quitar</button></div>';
        list.appendChild(item);
      });
    }
    const select = $("#ds-connection");
    fillSelect(
      select,
      connections.map((c) => ({ value: c.id, label: c.name + " (" + c.kind + ")" })),
      { placeholder: connections.length ? null : "Sin conexiones" }
    );
  }

  function renderDatasets() {
    const list = $("#ds-list");
    const datasets = state.data.datasets || [];
    if (list) {
      list.innerHTML = "";
      if (!datasets.length) {
        list.innerHTML = '<p class="hint">Sin datasets. Guarda un SELECT abajo.</p>';
      }
      datasets.forEach((ds) => {
        const item = document.createElement("div");
        item.className = "list-item";
        item.innerHTML =
          '<div class="list-main"><strong>' +
          esc(ds.name) +
          "</strong><small>" +
          esc((ds.fields || []).length) +
          " campos</small></div>" +
          '<div class="row"><button type="button" class="link" data-ds-edit="' +
          ds.id +
          '">Editar</button><button type="button" class="link danger" data-ds-delete="' +
          ds.id +
          '">Quitar</button></div>';
        list.appendChild(item);
      });
    }
    const select = $("#w-dataset");
    fillSelect(
      select,
      datasets.map((d) => ({ value: d.id, label: d.name })),
      { placeholder: "Selecciona un dataset" }
    );
  }

  function renderWidgetFormOptions() {
    renderChartOptions();
    const datasetId = $("#w-dataset").value;
    const modelsForDataset = modelItemsFor(datasetId);
    const selectedModelId = $("#w-model").value;
    const selectedModel = modelsForDataset.find((item) => String(item.id) === String(selectedModelId));
    const fields = datasetFields(datasetId).slice();
    modelOutputFields(selectedModel).forEach((field) => {
      if (!fields.some((existing) => existing.name === field.name)) fields.push(field);
    });
    const all = fields.map((f) => ({ value: f.name, label: f.name + " (" + f.type + ")" }));
    const numeric = fields.filter((f) => f.type === "number").map((f) => ({ value: f.name, label: f.name }));
    const models = modelsForDataset.map((item) => ({
      value: item.id,
      label: "[" + modelKindLabel(item.kind) + "] " + item.name,
    }));
    const previous = {
      x: $("#w-x").value,
      y: $("#w-y").value,
      series: $("#w-series").value,
      size: $("#w-size").value,
      label: $("#w-label-field").value,
      lat: $("#w-lat").value,
      lon: $("#w-lon").value,
      model: $("#w-model").value,
    };
    fillSelect($("#w-x"), all, { placeholder: "—" });
    fillSelect($("#w-y"), numeric.length ? numeric : all, { placeholder: "—" });
    fillSelect($("#w-series"), all, { placeholder: "Sin serie" });
    fillSelect($("#w-size"), numeric.length ? numeric : all, { placeholder: "Sin tamano" });
    fillSelect($("#w-label-field"), all, { placeholder: "Sin etiqueta" });
    fillSelect($("#w-lat"), all, { placeholder: "Sin latitud" });
    fillSelect($("#w-lon"), all, { placeholder: "Sin longitud" });
    fillSelect($("#w-model"), models, { placeholder: "Sin modelo" });
    restoreValue($("#w-x"), previous.x);
    restoreValue($("#w-y"), previous.y);
    restoreValue($("#w-series"), previous.series);
    restoreValue($("#w-size"), previous.size);
    restoreValue($("#w-label-field"), previous.label);
    restoreValue($("#w-lat"), previous.lat);
    restoreValue($("#w-lon"), previous.lon);
    restoreValue($("#w-model"), previous.model);
    applyChartTypeUI();
    renderMeasureContext();
  }

  function restoreValue(select, value) {
    if (!select || !value) return;
    if (Array.prototype.some.call(select.options, (opt) => opt.value === value)) select.value = value;
  }

  function applyChartTypeUI() {
    const chart = $("#w-chart").value;
    const tableLike = ["table", "matrix", "decomposition", "decomp_tree"].includes(chart);
    const noDims = ["kpi", "card", "multi_row", "gauge", "correlation", "key_influencers", "nav_buttons", "bookmark", "tooltip"].includes(chart);
    const point = ["scatter", "bubble"].includes(chart);
    const map = ["map_basic", "map_choropleth", "map_bubble", "map_arcgis"].includes(chart);
    const interaction = ["slicer", "nav_buttons", "bookmark", "tooltip", "filter_panel"].includes(chart);
    const x = $("#w-x");
    const y = $("#w-y");
    const series = $("#w-series");
    const agg = $("#w-agg");
    if (x) x.disabled = tableLike || noDims;
    if (series) series.disabled = tableLike || noDims || point || map || interaction;
    if (y) y.disabled = tableLike || ["correlation", "key_influencers", "nav_buttons", "bookmark", "tooltip", "filter_panel", "slicer"].includes(chart);
    if (agg) agg.disabled = tableLike || interaction;
    if ($("#w-size")) $("#w-size").disabled = !point;
    if ($("#w-label-field")) $("#w-label-field").disabled = !point;
    if ($("#w-lat")) $("#w-lat").disabled = !map;
    if ($("#w-lon")) $("#w-lon").disabled = !map;
    if ($("#w-max")) $("#w-max").disabled = !["gauge", "map_basic", "map_bubble", "map_choropleth", "map_arcgis"].includes(chart);
    if ($("#w-target")) $("#w-target").disabled = chart !== "gauge";
    if ($("#w-question")) $("#w-question").disabled = chart !== "qna";
    if ($("#w-text")) $("#w-text").disabled = !interaction;
    if ($("#w-url")) $("#w-url").disabled = !interaction;
    if ($("#w-tooltip")) $("#w-tooltip").disabled = !interaction;
    const hint = $("#w-hint");
    if (hint) {
      if (tableLike) hint.textContent = "Muestra las filas del dataset. Usa el limite para controlar el volumen.";
      else if (point) hint.textContent = "Elige los campos X/Y y, en burbujas, el campo de tamano.";
      else if (map) hint.textContent = "Indica latitud/longitud o un campo de region con una metrica.";
      else if (chart === "qna") hint.textContent = "Escribe una pregunta; se intentan detectar campos y agregacion.";
      else if (interaction) hint.textContent = "Configura texto, URL o tooltip para la interaccion.";
      else if (chart === "gauge") hint.textContent = "La metrica se agrega y se contrasta con el maximo/objetivo.";
      else if (noDims) hint.textContent = "Este grafico resume el dataset sin dimension o usa todas las metricas numericas.";
      else hint.textContent = "Dimension en X, metrica en Y y agregacion opcional por serie.";
    }
  }

  // ------------------------------------------------------------- widgets UI
  function fillWidgetForm(widget) {
    setDesignPanel("visualizations");
    state.editingWidget = widget.id;
    state.widgetMeasureRelated = [];
    state.widgetMeasureExpanded = {};
    $("#w-id").value = widget.id;
    $("#w-title").value = widget.title || "";
    $("#w-dataset").value = widget.dataset_id || "";
    renderWidgetFormOptions();
    $("#w-chart").value = normalizeChartType(widget.chart_type || defaultChart());
    if (!$("#w-chart").value) $("#w-chart").value = defaultChart();
    renderWidgetFormOptions();
    const config = widget.config || {};
    if (config.x) $("#w-x").value = config.x;
    if (config.y) $("#w-y").value = config.y;
    if (config.series) $("#w-series").value = config.series;
    if (config.model_item_id) $("#w-model").value = config.model_item_id;
    if (config.size) $("#w-size").value = config.size;
    if (config.label_field) $("#w-label-field").value = config.label_field;
    if (config.lat) $("#w-lat").value = config.lat;
    if (config.lon) $("#w-lon").value = config.lon;
    $("#w-agg").value = config.agg || "sum";
    $("#w-format").value = config.format || "number";
    $("#w-limit").value = config.limit || "";
    $("#w-max").value = config.max != null ? config.max : "";
    $("#w-target").value = config.target != null ? config.target : "";
    $("#w-question").value = config.question || "";
    $("#w-text").value = config.text || config.nav_label || "";
    $("#w-url").value = config.url || config.nav_url || "";
    $("#w-tooltip").value = config.tooltip || "";
    $("#w-w").value = widget.w || 3;
    $("#w-h").value = widget.h || 2;
    $("#w-pos-x").value = widget.x == null ? "" : widget.x;
    $("#w-pos-y").value = widget.y == null ? "" : widget.y;
    state.pendingLayout = null;
    $("#w-measure-name").value = "";
    $("#w-measure-expression").value = "";
    $("#w-measure-result").innerHTML = "";
    applyChartTypeUI();
    const button = $("#w-form button[type=submit]");
    if (button) button.textContent = "Actualizar widget";
    $("#w-cancel").hidden = false;
    $("#w-form").scrollIntoView({ behavior: "smooth", block: "nearest" });
  }

  function resetWidgetForm() {
    state.editingWidget = null;
    state.widgetMeasureRelated = [];
    state.widgetMeasureExpanded = {};
    const form = $("#w-form");
    if (form) form.reset();
    $("#w-id").value = "";
    $("#w-chart").value = defaultChart();
    $("#w-agg").value = "sum";
    $("#w-format").value = "number";
    $("#w-w").value = "3";
    $("#w-h").value = "2";
    $("#w-pos-x").value = "";
    $("#w-pos-y").value = "";
    state.pendingLayout = null;
    $("#w-measure-name").value = "";
    $("#w-measure-expression").value = "";
    $("#w-measure-result").innerHTML = "";
    const button = $("#w-form button[type=submit]");
    if (button) button.textContent = "Guardar widget";
    $("#w-cancel").hidden = true;
    renderWidgetFormOptions();
  }

  function collectWidget() {
    const chart = $("#w-chart").value;
    const config = {};
    const text = {
      x: $("#w-x").value,
      y: $("#w-y").value,
      series: $("#w-series").value,
      size: $("#w-size").value,
      label_field: $("#w-label-field").value,
      lat: $("#w-lat").value,
      lon: $("#w-lon").value,
      question: $("#w-question").value.trim(),
      text: $("#w-text").value.trim(),
      url: $("#w-url").value.trim(),
      tooltip: $("#w-tooltip").value.trim(),
    };
    Object.keys(text).forEach((key) => {
      if (text[key]) config[key] = text[key];
    });
    const modelId = parseInt($("#w-model").value, 10);
    if (Number.isFinite(modelId) && modelId > 0) config.model_item_id = modelId;
    if (chart !== "table") config.agg = $("#w-agg").value || "sum";
    config.format = $("#w-format").value || "number";
    const limit = parseInt($("#w-limit").value, 10);
    if (Number.isFinite(limit) && limit > 0) config.limit = limit;
    const maximum = parseFloat($("#w-max").value);
    if (Number.isFinite(maximum)) config.max = maximum;
    const target = parseFloat($("#w-target").value);
    if (Number.isFinite(target)) config.target = target;
    if (["kpi", "card", "nav_buttons", "bookmark", "tooltip"].includes(chart)) {
      config.label = $("#w-title").value.trim() || config.y;
    }
    if (["nav_buttons", "bookmark", "tooltip"].includes(chart)) {
      if (config.text) config.nav_label = config.text;
      if (config.url) config.nav_url = config.url;
    }
    Object.keys(config).forEach((key) => config[key] === undefined && delete config[key]);
    const w = clampInt($("#w-w").value, 1, 12, 3);
    const h = clampInt($("#w-h").value, 1, 6, 2);
    const payload = {
      title: $("#w-title").value.trim(),
      dataset_id: $("#w-dataset").value ? Number($("#w-dataset").value) : null,
      chart_type: chart,
      config: config,
      w: w,
      h: h,
    };
    const rawX = $("#w-pos-x").value;
    const rawY = $("#w-pos-y").value;
    if (rawX !== "" && Number.isFinite(parseInt(rawX, 10))) {
      payload.x = Math.max(0, Math.min(12 - w, parseInt(rawX, 10)));
    }
    if (rawY !== "" && Number.isFinite(parseInt(rawY, 10))) {
      payload.y = Math.max(0, parseInt(rawY, 10));
    }
    return payload;
  }

  function createWidgetMeasure() {
    const datasetId = Number($("#w-dataset").value) || null;
    if (!datasetId) {
      toast("Selecciona un dataset para crear la medida", "error");
      return;
    }
    const name = $("#w-measure-name").value.trim();
    const kind = $("#w-measure-kind").value;
    const expression = $("#w-measure-expression").value.trim();
    if (!name || !expression) {
      toast("Indica nombre y expresion de la medida", "error");
      return;
    }
    const out = $("#w-measure-result");
    if (out) out.innerHTML = '<p class="hint">Creando medida...</p>';
    api("/api/model/items", {
      method: "POST",
      body: {
        kind: kind,
        dataset_id: datasetId,
        name: name,
        expression: expression,
        config: {
          name: name,
          tables: relatedConfig(state.widgetMeasureRelated),
        },
      },
    })
      .then((row) => {
        state.pendingModelId = row.id;
        toast("Medida creada");
        return load();
      })
      .then(() => {
        if (!state.pendingModelId) return;
        const select = $("#w-model");
        if (select) {
          select.value = String(state.pendingModelId);
          renderWidgetFormOptions();
          select.value = String(state.pendingModelId);
        }
        if (out) {
          out.innerHTML = '<p class="result ok">Medida aplicada: ' + esc(name) + "</p>";
        }
        state.pendingModelId = null;
        applyChartTypeUI();
      })
      .catch((err) => {
        if (out) out.innerHTML = '<p class="result error">' + esc(err.message) + "</p>";
      });
  }

  // ------------------------------------------------------------- herramientas
  function renderTools() {
    renderToolsDatasets();
    renderModelFormOptions();
    renderModelItems();
  }

  function renderToolsDatasets() {
    const list = $("#tools-dataset-list");
    if (!list) return;
    const datasets = (state.data && state.data.datasets) || [];
    list.innerHTML = "";
    if (!datasets.length) {
      list.innerHTML = '<p class="hint">Sin datasets. Crea uno en la seccion Datasets.</p>';
      return;
    }
    datasets.forEach((ds) => {
      const fields = ds.fields || [];
      const numeric = fields.filter((f) => f.type === "number").length;
      const item = document.createElement("div");
      item.className = "list-item";
      item.innerHTML =
        '<div class="list-main"><strong>' +
        esc(ds.name) +
        "</strong><small>" +
        fields.length +
        " campos · " +
        numeric +
        " numericos</small></div>" +
        '<div class="row"><button type="button" class="link" data-tools-model="' +
        ds.id +
        '">Modelar</button><button type="button" class="link" data-tools-profile="' +
        ds.id +
        '">Perfil</button></div>';
      list.appendChild(item);
    });
  }

  function renderModelFormOptions() {
    if (!$("#model-form")) return;
    const datasets = (state.data && state.data.datasets) || [];
    const kinds = (state.data && state.data.model_kinds) || [
      ["measure", "Medida"],
      ["column", "Columna calculada"],
      ["table_calc", "Tabla calculada"],
      ["table_created", "Tabla creada"],
    ];
    const kindValue = $("#model-kind").value;
    fillSelect(
      $("#model-kind"),
      kinds.map((pair) => ({ value: pair[0], label: pair[1] })),
      { value: kindValue }
    );
    const datasetValue = $("#model-dataset").value;
    fillSelect(
      $("#model-dataset"),
      datasets.map((ds) => ({ value: ds.id, label: ds.name })),
      { placeholder: datasets.length ? null : "Sin datasets" }
    );
    if (!datasetValue && datasets.length) $("#model-dataset").value = String(datasets[0].id);
    else restoreValue($("#model-dataset"), datasetValue);
    const datasetId = $("#model-dataset").value;
    const filtered = state.modelRelated.filter((item) => String(item.id) !== String(datasetId));
    state.modelRelated = withJoinDefaults(datasetId, filtered);
    const sources = modelTableSources(datasetId, state.modelRelated);
    const tableHint = $("#model-table-hint");
    renderTableTree($("#model-table-tree"), {
      primaryId: datasetId,
      related: state.modelRelated,
      expanded: state.modelExpanded,
      focusEl: $("#model-table-focus"),
      metaEl: $("#model-tables-meta"),
      onToggle: (id, selected) => {
        state.modelRelated = setRelatedSelection(
          state.modelRelated,
          datasetId,
          id,
          selected
        );
        renderModelFormOptions();
      },
      onInsert: (text) => insertModelSnippet(text),
    });
    if (tableHint) tableHint.textContent = relatedSummary(state.modelRelated);
    renderJoinEditor($("#model-joins"), {
      primaryId: datasetId,
      related: state.modelRelated,
      getRelated: () => state.modelRelated,
      onChange: (id, patch) => {
        state.modelRelated = updateRelatedJoin(state.modelRelated, id, patch);
        if (tableHint) tableHint.textContent = relatedSummary(state.modelRelated);
      },
      onRemove: (id) => {
        state.modelRelated = setRelatedSelection(state.modelRelated, datasetId, id, false);
        renderModelFormOptions();
      },
      onInsert: (text) => insertModelSnippet(text),
    });
    fillQuickFieldSelect($("#quick-field"), sources);
    applyModelKindUI();
  }

  function applyModelKindUI() {
    const kind = $("#model-kind").value;
    const created = kind === "table_created";
    const box = $("#model-created-box");
    if (box) {
      box.hidden = !created;
      if (created) box.open = true;
    }
    const expression = $("#model-expression");
    if (expression) expression.disabled = created;
    const tablesPanel = $("#model-tables-panel");
    if (tablesPanel) tablesPanel.hidden = created;
    if ($("#quick-add")) $("#quick-add").disabled = !$("#quick-field").value || created;
  }

  function renderModelItems() {
    const list = $("#model-items-list");
    if (!list) return;
    const items = (state.data && state.data.model_items) || [];
    list.innerHTML = "";
    if (!items.length) {
      list.innerHTML = '<p class="hint">Sin medidas, columnas ni tablas de modelado.</p>';
      return;
    }
    items.forEach((item) => {
      const ds = datasetById(item.dataset_id);
      const config = item.config || {};
      const relatedCount = Array.isArray(config.tables) ? config.tables.length : 0;
      const row = document.createElement("div");
      row.className = "list-item model-item";
      const expr = item.expression ? item.expression.slice(0, 90) : JSON.stringify(config);
      row.innerHTML =
        '<div class="list-main"><strong>' +
        esc(item.name) +
        '</strong><small>' +
        esc(modelKindLabel(item.kind)) +
        (ds ? " · " + esc(ds.name) : "") +
        (relatedCount ? " · +" + relatedCount + " tabla(s)" : "") +
        "</small><code>" +
        esc(expr) +
        "</code></div>" +
        '<div class="row"><button type="button" class="link" data-model-use="' +
        item.id +
        '">Usar</button><button type="button" class="link" data-model-edit="' +
        item.id +
        '">Editar</button><button type="button" class="link danger" data-model-delete="' +
        item.id +
        '">Quitar</button></div>';
      list.appendChild(row);
    });
  }

  function setToolsTab(name) {
    $$("[data-tools-tab]").forEach((button) => button.classList.toggle("active", button.dataset.toolsTab === name));
    $$("[data-tools-pane]").forEach((pane) => {
      pane.hidden = pane.dataset.toolsPane !== name;
    });
  }

  function modelPayload(requireName) {
    const kind = $("#model-kind").value;
    const datasetId = $("#model-dataset").value;
    const name = $("#model-name").value.trim();
    const expression = $("#model-expression").value.trim();
    if (!datasetId) throw new Error("Selecciona un dataset");
    if (requireName && !name) throw new Error("Escribe un nombre");
    if (kind !== "table_created" && !expression) throw new Error("Escribe una expresion Python");
    const config = {};
    if (kind === "table_created") {
      const columns = $("#model-columns").value.split(",").map((v) => v.trim()).filter(Boolean);
      const raw = $("#model-rows").value.trim() || "[]";
      let rows;
      try {
        rows = JSON.parse(raw);
      } catch (err) {
        throw new Error("Las filas JSON no son validas: " + err.message);
      }
      if (!Array.isArray(rows)) throw new Error("Las filas deben ser un arreglo JSON");
      config.columns = columns;
      config.rows = rows;
    } else {
      config.tables = relatedConfig(state.modelRelated);
    }
    return { kind: kind, dataset_id: Number(datasetId), name: name, expression: expression, config: config };
  }

  function resetModelForm() {
    state.editingModel = null;
    state.modelRelated = [];
    state.modelExpanded = {};
    const form = $("#model-form");
    if (form) form.reset();
    $("#model-id").value = "";
    $("#model-name").value = "";
    $("#model-expression").value = "";
    $("#model-columns").value = "";
    $("#model-rows").value = "";
    $("#model-preview-out").innerHTML = "";
    $("#model-cancel").hidden = true;
    $("#model-form button[type=submit]").textContent = "Guardar modelo";
    renderModelFormOptions();
  }

  function fillModelForm(item) {
    setDesignPanel("data");
    state.editingModel = item.id;
    $("#model-id").value = item.id;
    renderModelFormOptions();
    $("#model-kind").value = item.kind;
    $("#model-dataset").value = item.dataset_id || "";
    const config = item.config || {};
    state.modelRelated = normalizeRelatedTables(config.tables);
    renderModelFormOptions();
    $("#model-name").value = item.name || "";
    $("#model-expression").value = item.expression || "";
    $("#model-columns").value = (config.columns || []).join(", ");
    $("#model-rows").value = config.rows ? JSON.stringify(config.rows, null, 2) : "";
    applyModelKindUI();
    $("#model-preview-out").innerHTML = "";
    $("#model-cancel").hidden = false;
    $("#model-form button[type=submit]").textContent = "Actualizar modelo";
    setToolsTab("model");
    $("#model-form").scrollIntoView({ behavior: "smooth", block: "nearest" });
  }

  function showModelPreview(result) {
    const out = $("#model-preview-out");
    if (!out) return;
    out.innerHTML = "";
    const summary = document.createElement("p");
    summary.className = "hint";
    summary.textContent =
      (result.kind || "") +
      " · filas origen: " +
      (result.source_rows != null ? result.source_rows : "—") +
      (result.source_truncated ? " (truncado)" : "");
    out.appendChild(summary);
    if (result.model_tables && result.model_tables.length) {
      const tables = document.createElement("p");
      tables.className = "hint";
      tables.textContent =
        "Tablas usadas: " +
        result.model_tables
          .map((item) => {
            const join =
              item.primary || !item.left_key
                ? ""
                : " · cruce " +
                  (item.how || "inner") +
                  " [" +
                  item.left_key +
                  " → " +
                  (item.right_key || item.left_key) +
                  "]";
            return (
              item.alias +
              " = " +
              item.name +
              " (" +
              (item.rows != null ? item.rows : "—") +
              " filas)" +
              join
            );
          })
          .join(" · ");
      out.appendChild(tables);
    }
    if (result.kind === "measure") {
      const value = document.createElement("div");
      value.className = "model-value";
      value.textContent = result.value == null ? "—" : result.value;
      out.appendChild(value);
      return;
    }
    if (result.columns && result.rows) {
      const box = document.createElement("div");
      box.className = "mini-table";
      window.BICharts.render(box, {
        type: "table",
        columns: result.columns,
        rows: result.rows,
        format: { format: "number", decimals: 2 },
        truncated: result.truncated,
      });
      out.appendChild(box);
    }
  }

  function insertQuickMeasure() {
    const parsed = parseQuickFieldValue($("#quick-field").value);
    const field = parsed.field;
    const op = $("#quick-op").value;
    if (!field) {
      toast("Elige un campo para la medida rapida", "error");
      return;
    }
    const quoted = JSON.stringify(field);
    const tableVar = parsed.alias || "rows";
    const expressions = {
      sum: "sum_field(" + tableVar + ", " + quoted + ")",
      avg: "avg_field(" + tableVar + ", " + quoted + ")",
      count: "count_field(" + tableVar + ", " + quoted + ")",
      count_distinct: "distinct_field(" + tableVar + ", " + quoted + ")",
      min: "min_field(" + tableVar + ", " + quoted + ")",
      max: "max_field(" + tableVar + ", " + quoted + ")",
      median: "median_field(" + tableVar + ", " + quoted + ")",
      stdev: "stdev_field(" + tableVar + ", " + quoted + ")",
    };
    $("#model-kind").value = "measure";
    applyModelKindUI();
    $("#model-expression").value = expressions[op] || expressions.sum;
    if (!$("#model-name").value.trim()) {
      $("#model-name").value = op + " " + field + (tableVar !== "rows" ? " · " + tableVar : "");
    }
    toast("Medida rapida insertada");
  }

  function useModelInWidget(itemId) {
    const item = ((state.data && state.data.model_items) || []).find((model) => String(model.id) === String(itemId));
    if (!item) return;
    resetWidgetForm();
    $("#w-dataset").value = item.dataset_id || "";
    renderWidgetFormOptions();
    const wanted = item.kind === "measure" ? "card" : "table";
    $("#w-chart").value = wanted;
    if (!$("#w-chart").value) $("#w-chart").value = defaultChart();
    renderWidgetFormOptions();
    $("#w-model").value = item.id;
    renderWidgetFormOptions();
    const outputs = modelOutputFields(item);
    if (outputs.length && ["measure", "column"].includes(item.kind)) {
      $("#w-y").value = outputs[0].name;
    }
    $("#w-title").value = item.name;
    applyChartTypeUI();
    $("#w-form").scrollIntoView({ behavior: "smooth", block: "nearest" });
    toast("Modelo listo para el widget");
  }

  async function loadProfile() {
    const out = $("#profile-out");
    const datasetId = $("#model-dataset").value;
    if (!out) return;
    if (!datasetId) {
      toast("Selecciona un dataset", "error");
      return;
    }
    out.innerHTML = '<p class="hint">Analizando...</p>';
    try {
      const result = await api("/api/model/profile?dataset_id=" + encodeURIComponent(datasetId));
      const profile = result.profile || {};
      out.innerHTML = "";
      const metrics = document.createElement("div");
      metrics.className = "profile-metrics";
      [
        ["Filas", profile.rows],
        ["Columnas", profile.columns],
        ["Numericas", profile.numeric_columns],
        ["Nulos", profile.null_cells],
        ["Tamano", profile.estimated_label],
      ].forEach((pair) => {
        const box = document.createElement("div");
        box.className = "profile-metric";
        box.innerHTML = "<strong>" + esc(pair[1]) + "</strong><span>" + esc(pair[0]) + "</span>";
        metrics.appendChild(box);
      });
      out.appendChild(metrics);
      const box = document.createElement("div");
      box.className = "mini-table";
      window.BICharts.render(box, {
        type: "table",
        columns: ["name", "type", "distinct", "nulls", "count", "min", "max"],
        rows: profile.fields || [],
        format: { format: "number", decimals: 2 },
      });
      out.appendChild(box);
    } catch (err) {
      out.innerHTML = "";
      const pre = document.createElement("pre");
      pre.className = "result error";
      pre.textContent = err.message;
      out.appendChild(pre);
    }
  }

  // ---------------------------------------------------------- datasets/conn
  function readConnectionForm() {
    const kind = $("#conn-kind").value;
    const config = {};
    if (kind === "sqlite") {
      config.path = $("#conn-path").value.trim();
    } else if (kind === "bigquery") {
      config.project = $("#conn-project").value.trim();
      config.dataset = $("#conn-bq-dataset").value.trim();
      config.location = $("#conn-location").value.trim();
      config.credentials = $("#conn-credentials").value.trim();
    } else {
      config.host = $("#conn-host").value.trim();
      const port = parseInt($("#conn-port").value, 10);
      if (Number.isFinite(port)) config.port = port;
      config.database = $("#conn-database").value.trim();
      config.user = $("#conn-user").value.trim();
      config.password = $("#conn-password").value;
      if (["postgres", "supabase"].includes(kind)) {
        config.sslmode = $("#conn-sslmode").value;
      }
      if (kind === "sqlserver") {
        config.driver = $("#conn-driver").value.trim() || "ODBC Driver 18 for SQL Server";
        config.encrypt = $("#conn-encrypt").value;
        config.trust_server_certificate = $("#conn-trust-cert").value;
        config.trusted_connection = $("#conn-trusted").checked ? "yes" : "no";
      }
    }
    return { name: $("#conn-name").value.trim(), kind: kind, config: config };
  }

  function applyConnectionKind() {
    const kind = $("#conn-kind").value;
    $$(".kind-fields").forEach((group) => {
      const kinds = (group.dataset.kinds || "").split(/\s+/);
      const parentVisible = !group.parentElement.closest(".kind-fields[hidden]");
      group.hidden = !(kinds.includes(kind) && parentVisible);
    });
    const ports = { postgres: "5432", supabase: "5432", mysql: "3306", sqlserver: "1433", oracle: "1521" };
    const port = $("#conn-port");
    if (port && ports[kind] && !port.value) port.placeholder = ports[kind];
  }

  function resetConnectionForm() {
    state.editingConnection = null;
    $("#conn-form").reset();
    $("#conn-id").value = "";
    $("#conn-result").hidden = true;
    $("#conn-cancel").hidden = true;
    $("#conn-form button[type=submit]").textContent = "Guardar";
    applyConnectionKind();
  }

  function fillConnectionForm(conn) {
    state.editingConnection = conn.id;
    $("#conn-id").value = conn.id;
    $("#conn-name").value = conn.name;
    $("#conn-kind").value = conn.kind;
    applyConnectionKind();
    const cfg = conn.config || {};
    if (conn.kind === "sqlite") {
      $("#conn-path").value = cfg.path || "";
    } else if (conn.kind === "bigquery") {
      $("#conn-project").value = cfg.project || "";
      $("#conn-bq-dataset").value = cfg.dataset || "";
      $("#conn-location").value = cfg.location || "";
      $("#conn-credentials").value = cfg.credentials || "";
    } else {
      $("#conn-host").value = cfg.host || "";
      $("#conn-port").value = cfg.port || "";
      $("#conn-database").value = cfg.database || "";
      $("#conn-user").value = cfg.user || "";
      $("#conn-password").value = cfg.password || "";
      if (["postgres", "supabase"].includes(conn.kind)) {
        $("#conn-sslmode").value = cfg.sslmode || (conn.kind === "supabase" ? "require" : "prefer");
      }
      if (conn.kind === "sqlserver") {
        $("#conn-driver").value = cfg.driver || "ODBC Driver 18 for SQL Server";
        $("#conn-encrypt").value = cfg.encrypt || "yes";
        $("#conn-trust-cert").value = cfg.trust_server_certificate || "yes";
        $("#conn-trusted").checked = String(cfg.trusted_connection || "no").toLowerCase() === "yes";
      }
    }
    $("#conn-result").hidden = true;
    $("#conn-cancel").hidden = false;
    $("#conn-form button[type=submit]").textContent = "Actualizar";
  }

  function previewDataset(showIn) {
    const connectionId = $("#ds-connection").value;
    const sql = $("#ds-sql").value.trim();
    if (!connectionId || !sql) {
      toast("Elige una conexion y escribe SQL", "error");
      return;
    }
    const target = showIn || $("#ds-preview-out");
    target.innerHTML = '<p class="hint">Ejecutando...</p>';
    api("/api/datasets/preview", {
      method: "POST",
      body: { connection_id: Number(connectionId), sql: sql, limit: 20 },
    })
      .then((result) => {
        target.innerHTML = "";
        const summary = document.createElement("p");
        summary.className = "hint";
        summary.textContent =
          result.columns.length +
          " columnas · " +
          result.rows.length +
          " filas" +
          (result.truncated ? " (vista parcial)" : "") +
          " · " +
          result.elapsed_ms +
          " ms";
        target.appendChild(summary);
        const box = document.createElement("div");
        box.className = "mini-table";
        window.BICharts.render(box, {
          type: "table",
          columns: result.columns,
          rows: result.rows,
          format: { format: "number", decimals: 2 },
          truncated: result.truncated,
        });
        target.appendChild(box);
      })
      .catch((err) => {
        target.innerHTML = "";
        const pre = document.createElement("pre");
        pre.className = "result error";
        pre.textContent = err.message;
        target.appendChild(pre);
      });
  }

  function fillDatasetForm(dataset) {
    state.editingDataset = dataset.id;
    $("#ds-id").value = dataset.id;
    $("#ds-name").value = dataset.name;
    $("#ds-sql").value = dataset.sql || "";
    $("#ds-connection").value = dataset.connection_id;
    $("#ds-preview-out").innerHTML = "";
    $("#ds-cancel").hidden = false;
    $("#ds-form button[type=submit]").textContent = "Actualizar dataset";
    $("#ds-form").scrollIntoView({ behavior: "smooth", block: "nearest" });
  }

  function resetDatasetForm() {
    state.editingDataset = null;
    $("#ds-form").reset();
    $("#ds-id").value = "";
    $("#ds-preview-out").innerHTML = "";
    $("#ds-cancel").hidden = true;
    $("#ds-form button[type=submit]").textContent = "Guardar dataset";
  }

  // --------------------------------------------------------------- eventos
  function setMode(mode) {
    if (mode === "design" && (!cfg.designEnabled || !cfg.canEdit)) {
      toast("El modo diseno esta deshabilitado", "error");
      return;
    }
    if (mode === state.mode) return;
    state.mode = mode;
    const url = new URL(window.location.href);
    url.searchParams.set("mode", mode);
    window.history.replaceState({}, "", url.toString());
    resetWidgetForm();
    resetDatasetForm();
    resetConnectionForm();
    load();
  }

  function bind() {
    $$("#mode-switch [data-mode]").forEach((btn) => {
      btn.addEventListener("click", () => setMode(btn.dataset.mode));
    });

    const refresh = $("#refresh");
    if (refresh) refresh.addEventListener("click", () => load());

    // token
    const tokenInput = $("#design-token");
    if (tokenInput) {
      tokenInput.addEventListener("change", () => {
        const value = tokenInput.value.trim();
        if (value) localStorage.setItem("biweb-design-token", value);
        else localStorage.removeItem("biweb-design-token");
        toast("Token guardado en este navegador");
      });
    }

    // dashboard
    const dashForm = $("#dash-form");
    if (dashForm) {
      dashForm.addEventListener("submit", (event) => {
        event.preventDefault();
        api("/api/dashboards/" + dashboardId, {
          method: "PUT",
          body: { name: $("#dash-name").value.trim(), description: $("#dash-desc").value.trim() },
        })
          .then(() => {
            toast("Tablero actualizado");
            return load();
          })
          .catch(fail);
      });
    }

    // conexiones
    const connKind = $("#conn-kind");
    if (connKind) connKind.addEventListener("change", applyConnectionKind);

    const connForm = $("#conn-form");
    if (connForm) {
      connForm.addEventListener("submit", (event) => {
        event.preventDefault();
        const payload = readConnectionForm();
        const request = state.editingConnection
          ? api("/api/connections/" + state.editingConnection, { method: "PUT", body: payload })
          : api("/api/connections", { method: "POST", body: payload });
        request
          .then(() => {
            toast("Conexion guardada");
            resetConnectionForm();
            return load();
          })
          .catch(fail);
      });
    }

    const connTest = $("#conn-test");
    if (connTest) {
      connTest.addEventListener("click", () => {
        const payload = readConnectionForm();
        const result = $("#conn-result");
        result.hidden = false;
        result.className = "result";
        result.textContent = "Probando...";
        const testPayload = Object.assign({}, payload);
        if (state.editingConnection) testPayload.id = state.editingConnection;
        api("/api/connections/test", { method: "POST", body: testPayload })
          .then((res) => {
            result.textContent = res.message + " (" + res.elapsed_ms + " ms)";
            result.className = "result " + (res.ok ? "ok" : "error");
          })
          .catch((err) => {
            result.textContent = err.message;
            result.className = "result error";
          });
      });
    }

    const connCancel = $("#conn-cancel");
    if (connCancel) connCancel.addEventListener("click", resetConnectionForm);

    const connList = $("#conn-list");
    if (connList) {
      connList.addEventListener("click", (event) => {
        const edit = event.target.closest("[data-conn-edit]");
        const remove = event.target.closest("[data-conn-delete]");
        if (edit) {
          const conn = (state.data.connections || []).find((c) => String(c.id) === edit.dataset.connEdit);
          if (conn) fillConnectionForm(conn);
        }
        if (remove) {
          if (!window.confirm("¿Quitar esta conexion? Se eliminaran sus datasets.")) return;
          api("/api/connections/" + remove.dataset.connDelete, { method: "DELETE" })
            .then(() => {
              toast("Conexion eliminada");
              return load();
            })
            .catch(fail);
        }
      });
    }

    const importBtn = $("#import-btn");
    if (importBtn) {
      importBtn.addEventListener("click", () => {
        const raw = $("#import-payload").value.trim();
        const out = $("#import-result");
        out.hidden = false;
        let payload;
        try {
          payload = JSON.parse(raw);
        } catch (err) {
          out.className = "result error";
          out.textContent = "JSON invalido: " + err.message;
          return;
        }
        api("/api/connections/import", { method: "POST", body: payload })
          .then((res) => {
            out.className = "result ok";
            out.textContent =
              "Creadas: " + res.created.length + " · Actualizadas: " + res.updated.length + " · Fallidas: " + res.failed.length +
              (res.failed.length ? "\n" + JSON.stringify(res.failed, null, 2) : "");
            if (res.created.length || res.updated.length) load();
          })
          .catch((err) => {
            out.className = "result error";
            out.textContent = err.message;
          });
      });
    }

    // datasets
    const dsForm = $("#ds-form");
    if (dsForm) {
      dsForm.addEventListener("submit", (event) => {
        event.preventDefault();
        const payload = {
          connection_id: Number($("#ds-connection").value),
          name: $("#ds-name").value.trim(),
          sql: $("#ds-sql").value.trim(),
        };
        if (!payload.connection_id || !payload.name || !payload.sql) {
          toast("Completa conexion, nombre y SQL", "error");
          return;
        }
        const request = state.editingDataset
          ? api("/api/datasets/" + state.editingDataset, { method: "PUT", body: payload })
          : api("/api/datasets", { method: "POST", body: payload });
        request
          .then(() => {
            toast("Dataset guardado");
            resetDatasetForm();
            return load();
          })
          .catch(fail);
      });
    }

    const dsPreview = $("#ds-preview-btn");
    if (dsPreview) dsPreview.addEventListener("click", () => previewDataset());
    const dsCancel = $("#ds-cancel");
    if (dsCancel) dsCancel.addEventListener("click", resetDatasetForm);

    const dsList = $("#ds-list");
    if (dsList) {
      dsList.addEventListener("click", (event) => {
        const edit = event.target.closest("[data-ds-edit]");
        const remove = event.target.closest("[data-ds-delete]");
        if (edit) {
          const dataset = (state.data.datasets || []).find((d) => String(d.id) === edit.dataset.dsEdit);
          if (dataset) fillDatasetForm(dataset);
        }
        if (remove) {
          if (!window.confirm("¿Eliminar este dataset? Los widgets que lo usan quedaran vacios.")) return;
          api("/api/datasets/" + remove.dataset.dsDelete, { method: "DELETE" })
            .then(() => {
              toast("Dataset eliminado");
              return load();
            })
            .catch(fail);
        }
      });
    }

    // widgets
    const wDataset = $("#w-dataset");
    if (wDataset) {
      wDataset.addEventListener("change", () => {
        state.widgetMeasureRelated = [];
        state.widgetMeasureExpanded = {};
        renderWidgetFormOptions();
      });
    }
    const wChart = $("#w-chart");
    if (wChart) wChart.addEventListener("change", applyChartTypeUI);
    const wModel = $("#w-model");
    if (wModel) wModel.addEventListener("change", () => renderWidgetFormOptions());

    const wForm = $("#w-form");
    if (wForm) {
      wForm.addEventListener("submit", (event) => {
        event.preventDefault();
        const payload = collectWidget();
        const standalone = ["nav_buttons", "bookmark", "tooltip"].includes(payload.chart_type);
        if (!payload.dataset_id && !standalone) {
          toast("Selecciona un dataset", "error");
          return;
        }
        const request = state.editingWidget
          ? api("/api/widgets/" + state.editingWidget, { method: "PUT", body: payload })
          : api("/api/dashboards/" + dashboardId + "/widgets", { method: "POST", body: payload });
        request
          .then(() => {
            toast(state.editingWidget ? "Widget actualizado" : "Widget agregado");
            resetWidgetForm();
            return load();
          })
          .catch(fail);
      });
    }
    const wCancel = $("#w-cancel");
    if (wCancel) wCancel.addEventListener("click", resetWidgetForm);

    const measureCreate = $("#w-measure-create");
    if (measureCreate) measureCreate.addEventListener("click", createWidgetMeasure);

    const measureHelp = $("#w-measure-help");
    if (measureHelp) {
      measureHelp.addEventListener("click", (event) => {
        event.stopPropagation();
        const tip = $("#w-measure-tooltip");
        setMeasureTooltip(tip ? tip.hidden : false);
      });
    }
    const widgetQuickAdd = $("#w-quick-add");
    if (widgetQuickAdd) widgetQuickAdd.addEventListener("click", insertWidgetQuickMeasure);
    document.addEventListener("click", (event) => {
      const tip = $("#w-measure-tooltip");
      if (!tip || tip.hidden) return;
      if (tip.contains(event.target) || (measureHelp && measureHelp.contains(event.target))) return;
      setMeasureTooltip(false);
    });
    document.addEventListener("keydown", (event) => {
      if (event.key === "Escape") setMeasureTooltip(false);
    });
    window.addEventListener("resize", positionMeasureTooltip);
    window.addEventListener("scroll", positionMeasureTooltip, true);

    // importacion: tablas, archivos y scripts
    const impConnection = $("#imp-connection");
    if (impConnection) {
      impConnection.addEventListener("change", () => {
        state.tables = [];
        state.tablesConnection = Number(impConnection.value) || null;
        renderTables();
      });
    }
    const impList = $("#imp-list-btn");
    if (impList) impList.addEventListener("click", loadTables);

    const impTables = $("#imp-tables");
    if (impTables) {
      impTables.addEventListener("click", (event) => {
        const save = event.target.closest("[data-alias-save]");
        const use = event.target.closest("[data-table-dataset]");
        if (save) saveTableAlias(save.dataset.aliasSave);
        if (use) useTableAsDataset(use.dataset.tableDataset);
      });
    }

    const impFileForm = $("#imp-file-form");
    if (impFileForm) impFileForm.addEventListener("submit", submitFileImport);

    const scriptSelect = $("#imp-script");
    if (scriptSelect) {
      scriptSelect.addEventListener("change", () => {
        const id = scriptSelect.value;
        if (!id) {
          fillScript(null);
          return;
        }
        const script = ((state.data && state.data.api_scripts) || []).find(
          (item) => String(item.id) === String(id)
        );
        if (script) fillScript(script);
      });
    }
    const scriptNew = $("#imp-script-new");
    if (scriptNew) scriptNew.addEventListener("click", () => fillScript(null));
    const scriptSave = $("#imp-script-save");
    if (scriptSave) scriptSave.addEventListener("click", saveScript);
    const scriptDelete = $("#imp-script-delete");
    if (scriptDelete) scriptDelete.addEventListener("click", deleteScript);
    const scriptPreview = $("#imp-script-preview");
    if (scriptPreview) scriptPreview.addEventListener("click", () => runScript(true));
    const scriptRun = $("#imp-script-run");
    if (scriptRun) scriptRun.addEventListener("click", () => runScript(false));

    if (canvas) {
      canvas.addEventListener("dragover", (event) => {
        if (state.mode !== "design") return;
        const types = Array.from(event.dataTransfer.types || []);
        if (!types.includes("application/x-biweb-chart") && !types.includes("text/plain")) return;
        event.preventDefault();
        event.dataTransfer.dropEffect = "copy";
        canvas.classList.add("drop-target");
      });
      canvas.addEventListener("dragleave", (event) => {
        if (!event.relatedTarget || !canvas.contains(event.relatedTarget)) {
          canvas.classList.remove("drop-target");
        }
      });
      canvas.addEventListener("drop", (event) => {
        if (state.mode !== "design") return;
        const type =
          event.dataTransfer.getData("application/x-biweb-chart") ||
          event.dataTransfer.getData("text/plain");
        canvas.classList.remove("drop-target");
        state.paletteDragging = false;
        if (!type) return;
        event.preventDefault();
        const pos = layoutFromPointer(event);
        const size = defaultSize(type);
        const w = Math.max(1, Math.min(12, size.w));
        const x = Math.max(0, Math.min(12 - w, pos.x));
        beginWidgetFromPalette(type, { x: x, y: pos.y, w: w, h: size.h });
      });

      canvas.addEventListener("biweb:filter", (event) => applyFilterEvent(event.detail));
      canvas.addEventListener("click", (event) => {
        const bookmark = event.target.closest("[data-bookmark-action]");
        if (bookmark) {
          const key = "biweb:bookmark:" + dashboardId + ":" + bookmark.dataset.bookmarkId;
          try {
            if (bookmark.dataset.bookmarkAction === "save") {
              window.localStorage.setItem(key, JSON.stringify(state.filters || {}));
              toast("Estado guardado en el marcador");
            } else {
              const raw = window.localStorage.getItem(key);
              if (!raw) {
                toast("Este marcador aun no tiene un estado guardado");
                return;
              }
              state.filters = JSON.parse(raw) || {};
              renderActiveFilters();
              renderCanvas();
              toast("Estado restaurado desde el marcador");
            }
          } catch (err) {
            toast("No se pudo acceder al almacenamiento local");
          }
          return;
        }
        const edit = event.target.closest("[data-widget-edit]");
        const remove = event.target.closest("[data-widget-delete]");
        if (edit) {
          const widget = (state.data.widgets || []).find((w) => String(w.id) === edit.dataset.widgetEdit);
          if (widget) fillWidgetForm(widget);
        }
        if (remove) {
          if (!window.confirm("¿Eliminar este widget?")) return;
          api("/api/widgets/" + remove.dataset.widgetDelete, { method: "DELETE" })
            .then(() => {
              toast("Widget eliminado");
              return load();
            })
            .catch(fail);
        }
      });
    }

    // herramientas y modelado
    $$("[data-design-panel]").forEach((button) => {
      button.addEventListener("click", () => setDesignPanel(button.dataset.designPanel));
    });

    const activeFilters = $("#active-filter-list");
    if (activeFilters) {
      activeFilters.addEventListener("click", (event) => {
        const clear = event.target.closest("[data-filter-clear]");
        if (!clear) return;
        const datasetId = clear.dataset.datasetId;
        const field = clear.dataset.filterField;
        if (!datasetId || !field || !state.filters[datasetId]) return;
        delete state.filters[datasetId][field];
        if (!Object.keys(state.filters[datasetId]).length) delete state.filters[datasetId];
        renderActiveFilters();
        renderCanvas();
      });
    }

    const clearFilters = $("#clear-filters");
    if (clearFilters) {
      clearFilters.addEventListener("click", () => {
        state.filters = {};
        renderActiveFilters();
        renderCanvas();
      });
    }

    $$("[data-tools-tab]").forEach((button) => {
      button.addEventListener("click", () => setToolsTab(button.dataset.toolsTab));
    });

    const toolsDatasets = $("#tools-dataset-list");
    if (toolsDatasets) {
      toolsDatasets.addEventListener("click", (event) => {
        const modelBtn = event.target.closest("[data-tools-model]");
        const profileBtn = event.target.closest("[data-tools-profile]");
        if (modelBtn) {
          setToolsTab("model");
          $("#model-dataset").value = modelBtn.dataset.toolsModel;
          renderModelFormOptions();
          $("#model-name").focus();
        }
        if (profileBtn) {
          setToolsTab("profile");
          $("#model-dataset").value = profileBtn.dataset.toolsProfile;
          renderModelFormOptions();
          loadProfile();
        }
      });
    }

    const modelKind = $("#model-kind");
    if (modelKind) modelKind.addEventListener("change", applyModelKindUI);
    const modelDataset = $("#model-dataset");
    if (modelDataset) {
      modelDataset.addEventListener("change", () => {
        state.modelRelated = [];
        state.modelExpanded = {};
        renderModelFormOptions();
        if (!$("[data-tools-pane=profile]").hidden) loadProfile();
      });
    }
    const modelTableFocus = $("#model-table-focus");
    if (modelTableFocus) {
      modelTableFocus.addEventListener("change", () => {
        focusTable("#model-table-tree", modelTableFocus.value);
      });
    }
    const measureTableFocus = $("#w-measure-table-focus");
    if (measureTableFocus) {
      measureTableFocus.addEventListener("change", () => {
        focusTable("#w-measure-tables", measureTableFocus.value);
      });
    }
    const quickField = $("#quick-field");
    if (quickField) quickField.addEventListener("change", applyModelKindUI);
    const quickAdd = $("#quick-add");
    if (quickAdd) quickAdd.addEventListener("click", insertQuickMeasure);

    const modelPreviewBtn = $("#model-preview-btn");
    if (modelPreviewBtn) {
      modelPreviewBtn.addEventListener("click", () => {
        let payload;
        try {
          payload = modelPayload(false);
        } catch (err) {
          toast(err.message, "error");
          return;
        }
        const out = $("#model-preview-out");
        out.innerHTML = '<p class="hint">Evaluando...</p>';
        api("/api/model/preview", {
          method: "POST",
          body: Object.assign({ limit: 20 }, payload),
        })
          .then(showModelPreview)
          .catch((err) => {
            out.innerHTML = "";
            const pre = document.createElement("pre");
            pre.className = "result error";
            pre.textContent = err.message;
            out.appendChild(pre);
          });
      });
    }

    const modelForm = $("#model-form");
    if (modelForm) {
      modelForm.addEventListener("submit", (event) => {
        event.preventDefault();
        let payload;
        try {
          payload = modelPayload(true);
        } catch (err) {
          toast(err.message, "error");
          return;
        }
        const request = state.editingModel
          ? api("/api/model/items/" + state.editingModel, { method: "PUT", body: payload })
          : api("/api/model/items", { method: "POST", body: payload });
        request
          .then(() => {
            toast(state.editingModel ? "Modelo actualizado" : "Modelo guardado");
            resetModelForm();
            return load();
          })
          .catch(fail);
      });
    }
    const modelCancel = $("#model-cancel");
    if (modelCancel) modelCancel.addEventListener("click", resetModelForm);

    const modelItemsList = $("#model-items-list");
    if (modelItemsList) {
      modelItemsList.addEventListener("click", (event) => {
        const use = event.target.closest("[data-model-use]");
        const edit = event.target.closest("[data-model-edit]");
        const remove = event.target.closest("[data-model-delete]");
        const items = (state.data && state.data.model_items) || [];
        if (use) useModelInWidget(use.dataset.modelUse);
        if (edit) {
          const item = items.find((model) => String(model.id) === edit.dataset.modelEdit);
          if (item) fillModelForm(item);
        }
        if (remove) {
          if (!window.confirm("¿Eliminar este elemento de modelado?")) return;
          api("/api/model/items/" + remove.dataset.modelDelete, { method: "DELETE" })
            .then(() => {
              toast("Modelo eliminado");
              return load();
            })
            .catch(fail);
        }
      });
    }

    const profileRefresh = $("#profile-refresh");
    if (profileRefresh) profileRefresh.addEventListener("click", loadProfile);

    // zona de riesgo
    const resetDemo = $("#reset-demo");
    if (resetDemo) {
      resetDemo.addEventListener("click", () => {
        if (!window.confirm("Esto borra TODOS los tableros, datasets y conexiones. ¿Continuar?")) return;
        api("/api/demo/reset", { method: "POST" })
          .then((res) => {
            toast("Demo restaurada");
            window.location.href = "/d/" + res.dashboard_id + "?mode=design";
          })
          .catch(fail);
      });
    }
    const deleteDashboard = $("#delete-dashboard");
    if (deleteDashboard) {
      deleteDashboard.addEventListener("click", () => {
        if (!window.confirm("¿Eliminar este tablero y todos sus widgets?")) return;
        api("/api/dashboards/" + dashboardId, { method: "DELETE" })
          .then(() => {
            window.location.href = "/";
          })
          .catch(fail);
      });
    }
  }

  // refresco silencioso en modo visualizacion
  setInterval(() => {
    if (state.mode === "view" && !document.hidden && !state.loading) load(true);
  }, 60000);

  initializeDesignPanels();
  bind();
  applyConnectionKind();
  load();
})();
