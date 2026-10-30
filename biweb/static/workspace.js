/*
 * Escritorio BI Web: menu de arbol + ventanas flotantes.
 *
 * Replica, sin dependencias, los patrones de Ext.NET que usa
 * python_homologacion_EXNET:
 *   Viewport(layout="border")   -> .ws-shell: arbol al oeste, escritorio al centro
 *   TreePanel + itemclick       -> renderTree() + open(nodo)
 *   Window(layout="fit")        -> ventana con <iframe>, arrastrable y redimensionable
 *   App.<id>                    -> window.BIWorkspace (lo usan los iframes via embed.js)
 */
(() => {
  const cfg = window.BIWORKSPACE || { tree: [] };
  const $ = (id) => document.getElementById(id);

  const shell = $("ws-shell");
  const treeEl = $("ws-tree");
  const treeEmpty = $("ws-tree-empty");
  const filterInput = $("ws-tree-filter");
  const splitter = $("ws-splitter");
  const desktop = $("ws-desktop");
  const emptyState = $("ws-empty");
  const snapPreview = $("ws-snap-preview");
  const tasksEl = $("ws-tasks");

  const MIN_W = 340;
  const MIN_H = 220;
  const MOBILE = window.matchMedia("(max-width: 760px)");

  const ICONS = {
    folder: '<path d="M10 4H4a2 2 0 0 0-2 2v12a2 2 0 0 0 2 2h16a2 2 0 0 0 2-2V8a2 2 0 0 0-2-2h-8l-2-2Z"/>',
    home: '<path d="M10 20v-6h4v6h5v-8h3L12 3 2 12h3v8h5Z"/>',
    chart: '<path d="M5 9.2h3V19H5V9.2ZM10.6 5h2.8v14h-2.8V5Zm5.6 8H19v6h-2.8v-6Z"/>',
    design: '<path d="M3 17.2V21h3.8L17.8 9.9l-3.7-3.7L3 17.2ZM20.7 7a1 1 0 0 0 0-1.4l-2.3-2.3a1 1 0 0 0-1.4 0l-1.8 1.8 3.7 3.7L20.7 7Z"/>',
    terminal: '<path d="M20 4H4a2 2 0 0 0-2 2v12a2 2 0 0 0 2 2h16a2 2 0 0 0 2-2V6a2 2 0 0 0-2-2Zm0 14H4V8h16v10ZM6.5 16.5 5 15l2.5-2.5L5 10l1.5-1.5 4 4-4 4Zm5.5 0h6v-2h-6v2Z"/>',
    users: '<path d="M16 11a3 3 0 1 0 0-6 3 3 0 0 0 0 6Zm-8 0a3 3 0 1 0 0-6 3 3 0 0 0 0 6Zm0 2c-2.3 0-7 1.2-7 3.5V19h14v-2.5C15 14.2 10.3 13 8 13Zm8 0h-1c1.2.9 2 2 2 3.5V19h6v-2.5c0-2.3-4.7-3.5-7-3.5Z"/>',
    shield: '<path d="M12 1 3 5v6c0 5.6 3.8 10.7 9 12 5.2-1.3 9-6.4 9-12V5l-9-4Zm-2 16-4-4 1.4-1.4 2.6 2.6 6.6-6.6L18 9l-8 8Z"/>',
    key: '<path d="M12.7 10A6 6 0 1 0 7 18a6 6 0 0 0 5.7-4H17v4h4v-4h2v-4H12.7ZM7 14a2 2 0 1 1 0-4 2 2 0 0 1 0 4Z"/>',
    list: '<path d="M3 13h2v-2H3v2Zm0 4h2v-2H3v2Zm0-8h2V7H3v2Zm4 4h14v-2H7v2Zm0 4h14v-2H7v2ZM7 7v2h14V7H7Z"/>',
    user: '<path d="M12 12a4.5 4.5 0 1 0 0-9 4.5 4.5 0 0 0 0 9Zm0 2c-4.4 0-8 2.2-8 5v2h16v-2c0-2.8-3.6-5-8-5Z"/>',
    window: '<path d="M19 4H5a2 2 0 0 0-2 2v12a2 2 0 0 0 2 2h14a2 2 0 0 0 2-2V6a2 2 0 0 0-2-2Zm0 14H5V8h14v10Z"/>',
  };
  const svg = (name) => `<svg viewBox="0 0 24 24" aria-hidden="true">${ICONS[name] || ICONS.window}</svg>`;
  const esc = (s) => String(s).replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" })[c]);

  /* ================================================================ arbol */
  const leafById = new Map();

  function renderTree(nodes, depth = 0) {
    const frag = document.createDocumentFragment();
    nodes.forEach((n) => {
      const li = document.createElement("li");
      li.setAttribute("role", "treeitem");
      li.className = "ws-node";
      li.style.setProperty("--depth", depth);
      const isFolder = Array.isArray(n.children);
      const row = document.createElement("div");
      row.className = "ws-node-row";
      row.tabIndex = -1;
      row.innerHTML =
        (isFolder ? '<span class="ws-caret"><svg viewBox="0 0 24 24"><path d="M9 6l6 6-6 6V6Z"/></svg></span>' : '<span class="ws-caret"></span>') +
        `<span class="ws-node-icon">${svg(n.icon)}</span><span class="ws-node-text">${esc(n.text)}</span>`;
      row.dataset.text = n.text.toLowerCase();
      li.appendChild(row);
      if (isFolder) {
        li.classList.add("is-folder");
        li.setAttribute("aria-expanded", String(Boolean(n.expanded)));
        const group = document.createElement("ul");
        group.setAttribute("role", "group");
        group.className = "ws-group";
        const inner = document.createElement("div");
        inner.className = "ws-group-inner";
        inner.appendChild(renderTree(n.children, depth + 1));
        group.appendChild(inner);
        li.appendChild(group);
      } else {
        li.classList.add("is-leaf");
        li.dataset.id = n.id;
        leafById.set(n.id, { node: n, li });
      }
      frag.appendChild(li);
    });
    return frag;
  }

  function setExpanded(li, expanded) {
    if (li.classList.contains("is-folder")) li.setAttribute("aria-expanded", String(expanded));
  }

  function visibleRows() {
    return [...treeEl.querySelectorAll(".ws-node-row")].filter((row) => row.offsetParent !== null && !row.closest(".is-hidden"));
  }

  function focusRow(row) {
    treeEl.querySelectorAll(".ws-node-row[tabindex='0']").forEach((r) => (r.tabIndex = -1));
    row.tabIndex = 0;
    row.focus();
  }

  function activateItem(li) {
    if (li.classList.contains("is-folder")) {
      setExpanded(li, li.getAttribute("aria-expanded") !== "true");
    } else {
      const entry = leafById.get(li.dataset.id);
      if (entry) open(entry.node);
      if (MOBILE.matches) shell.classList.add("tree-collapsed");
    }
  }

  treeEl.addEventListener("click", (e) => {
    const row = e.target.closest(".ws-node-row");
    if (!row) return;
    focusRow(row);
    activateItem(row.parentElement);
  });

  treeEl.addEventListener("keydown", (e) => {
    const row = e.target.closest(".ws-node-row");
    if (!row) return;
    const li = row.parentElement;
    const rows = visibleRows();
    const idx = rows.indexOf(row);
    const folder = li.classList.contains("is-folder");
    const expanded = li.getAttribute("aria-expanded") === "true";
    let handled = true;
    switch (e.key) {
      case "ArrowDown": if (rows[idx + 1]) focusRow(rows[idx + 1]); break;
      case "ArrowUp": if (rows[idx - 1]) focusRow(rows[idx - 1]); break;
      case "Home": focusRow(rows[0]); break;
      case "End": focusRow(rows[rows.length - 1]); break;
      case "ArrowRight":
        if (folder && !expanded) setExpanded(li, true);
        else if (folder && rows[idx + 1]) focusRow(rows[idx + 1]);
        break;
      case "ArrowLeft": {
        if (folder && expanded) { setExpanded(li, false); break; }
        const parent = li.parentElement.closest(".ws-node.is-folder");
        if (parent) focusRow(parent.querySelector(":scope > .ws-node-row"));
        break;
      }
      case "Enter": case " ": activateItem(li); break;
      default: handled = false;
    }
    if (handled) e.preventDefault();
  });

  // Filtro: muestra coincidencias con sus carpetas padre expandidas
  function applyFilter(query) {
    const q = query.trim().toLowerCase();
    let matches = 0;
    const walk = (li) => {
      const row = li.querySelector(":scope > .ws-node-row");
      const textEl = row.querySelector(".ws-node-text");
      const own = !q || row.dataset.text.includes(q);
      textEl.innerHTML = q && own ? highlight(textEl.textContent, q) : esc(textEl.textContent);
      let childMatch = false;
      if (li.classList.contains("is-folder")) {
        li.querySelectorAll(":scope > .ws-group > .ws-group-inner > .ws-node").forEach((child) => {
          if (walk(child)) childMatch = true;
        });
        if (q) {
          if (!li.dataset.prevExpanded) li.dataset.prevExpanded = li.getAttribute("aria-expanded");
          setExpanded(li, childMatch || own);
        } else if (li.dataset.prevExpanded) {
          setExpanded(li, li.dataset.prevExpanded === "true");
          delete li.dataset.prevExpanded;
        }
      }
      const visible = own || childMatch;
      li.classList.toggle("is-hidden", !visible);
      if (visible && li.classList.contains("is-leaf") && q) matches += 1;
      return visible;
    };
    treeEl.querySelectorAll(":scope > .ws-node").forEach(walk);
    treeEmpty.hidden = !q || matches > 0;
  }
  function highlight(text, q) {
    const i = text.toLowerCase().indexOf(q);
    if (i < 0) return esc(text);
    return esc(text.slice(0, i)) + "<mark>" + esc(text.slice(i, i + q.length)) + "</mark>" + esc(text.slice(i + q.length));
  }
  filterInput.addEventListener("input", () => applyFilter(filterInput.value));
  filterInput.addEventListener("keydown", (e) => {
    if (e.key === "ArrowDown") { e.preventDefault(); const rows = visibleRows(); if (rows[0]) focusRow(rows[0]); }
    if (e.key === "Enter") {
      const first = visibleRows().find((r) => r.parentElement.classList.contains("is-leaf"));
      if (first) activateItem(first.parentElement);
    }
    if (e.key === "Escape") { filterInput.value = ""; applyFilter(""); }
  });

  function markActiveLeaf(id) {
    treeEl.querySelectorAll(".ws-node.is-leaf.is-active").forEach((li) => li.classList.remove("is-active"));
    const entry = id && leafById.get(id);
    if (entry) entry.li.classList.add("is-active");
  }

  /* ============================================================ splitter */
  const prefs = loadPrefs();
  function loadPrefs() {
    try { return JSON.parse(localStorage.getItem(cfg.storageKey + ".prefs")) || {}; } catch (e) { return {}; }
  }
  function savePrefs() {
    try { localStorage.setItem(cfg.storageKey + ".prefs", JSON.stringify(prefs)); } catch (e) { /* sin almacenamiento */ }
  }
  if (prefs.treeWidth) shell.style.setProperty("--ws-tree-w", prefs.treeWidth + "px");
  if (prefs.treeCollapsed || MOBILE.matches) shell.classList.add("tree-collapsed");

  function toggleTree(force) {
    const collapsed = shell.classList.toggle("tree-collapsed", force);
    if (!MOBILE.matches) { prefs.treeCollapsed = collapsed; savePrefs(); }
    if (!collapsed) filterInput.focus({ preventScroll: true });
  }

  splitter.addEventListener("pointerdown", (e) => {
    if (shell.classList.contains("tree-collapsed")) return;
    e.preventDefault();
    splitter.setPointerCapture(e.pointerId);
    desktop.classList.add("ws-busy");
    const startX = e.clientX;
    const startW = $("ws-tree-panel").getBoundingClientRect().width;
    const move = (ev) => {
      const w = Math.min(480, Math.max(200, startW + ev.clientX - startX));
      shell.style.setProperty("--ws-tree-w", w + "px");
      prefs.treeWidth = Math.round(w);
    };
    const up = () => {
      splitter.removeEventListener("pointermove", move);
      desktop.classList.remove("ws-busy");
      savePrefs();
    };
    splitter.addEventListener("pointermove", move);
    splitter.addEventListener("pointerup", up, { once: true });
  });
  splitter.addEventListener("dblclick", () => toggleTree(true));

  /* ============================================================ ventanas */
  const wins = new Map();
  let zTop = 10;
  let activeId = null;
  let cascadeStep = 0;

  function bounds() {
    return desktop.getBoundingClientRect();
  }

  function defaultGeometry() {
    const b = bounds();
    const w = Math.max(MIN_W, Math.min(1180, Math.round(b.width * 0.84)));
    const h = Math.max(MIN_H, Math.min(860, Math.round(b.height * 0.9)));
    const offset = (cascadeStep++ % 6) * 26;
    return {
      x: Math.max(0, Math.round((b.width - w) / 2) - 60 + offset),
      y: Math.max(0, Math.min(16 + offset, b.height - h)),
      w, h,
    };
  }

  function open(node, state) {
    const id = node.id || node.url;
    if (wins.has(id)) {
      const existing = wins.get(id);
      restore(existing);
      focus(existing);
      if (node.url && node.url !== existing.url && !state) navigate(existing, node.url);
      return existing;
    }
    const geo = state || defaultGeometry();
    const win = {
      id,
      url: (state && state.url) || node.url,
      homeUrl: node.url,
      title: node.title || node.text || "Ventana",
      icon: node.icon || "window",
      x: geo.x, y: geo.y, w: geo.w, h: geo.h,
      max: Boolean(state && state.max) || MOBILE.matches,
      min: Boolean(state && state.min),
      snap: (state && state.snap) || null,
    };
    win.el = buildWindow(win);
    win.task = buildTask(win);
    wins.set(id, win);
    desktop.appendChild(win.el);
    tasksEl.appendChild(win.task);
    applyGeometry(win);
    if (win.min) {
      win.el.classList.add("is-min");
      win.task.classList.add("is-min");
    } else {
      loadFrame(win);
      requestAnimationFrame(() => win.el.classList.add("is-open"));
      focus(win);
    }
    refreshEmpty();
    persist();
    return win;
  }

  function buildWindow(win) {
    const el = document.createElement("section");
    el.className = "ws-win";
    el.setAttribute("role", "dialog");
    el.setAttribute("aria-label", win.title);
    el.innerHTML = `
      <header class="ws-win-head">
        <span class="ws-win-icon">${svg(win.icon)}</span>
        <span class="ws-win-title">${esc(win.title)}</span>
        <div class="ws-win-tools">
          <button type="button" data-win="back" title="Atras"><svg viewBox="0 0 24 24"><path d="M20 11H7.8l5.6-5.6L12 4l-8 8 8 8 1.4-1.4L7.8 13H20v-2Z"/></svg></button>
          <button type="button" data-win="reload" title="Recargar"><svg viewBox="0 0 24 24"><path d="M17.6 6.4A8 8 0 1 0 19.7 14h-2.1a6 6 0 1 1-1.4-6.2L13 11h7V4l-2.4 2.4Z"/></svg></button>
          <button type="button" data-win="popout" title="Abrir en pestana nueva"><svg viewBox="0 0 24 24"><path d="M19 19H5V5h7V3H5a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h14a2 2 0 0 0 2-2v-7h-2v7ZM14 3v2h3.6l-9.8 9.8 1.4 1.4L19 6.4V10h2V3h-7Z"/></svg></button>
          <span class="ws-win-sep"></span>
          <button type="button" data-win="min" title="Minimizar"><svg viewBox="0 0 24 24"><path d="M5 17h14v2H5v-2Z"/></svg></button>
          <button type="button" data-win="max" title="Maximizar"><svg viewBox="0 0 24 24"><path class="i-max" d="M5 5h14v14H5V5Zm2 4v8h10V9H7Z"/><path class="i-restore" d="M8 3h13v13h-3v3H5V6h3V3Zm2 3h8v8h1V5h-9v1ZM7 10v7h9v-7H7Z"/></svg></button>
          <button type="button" data-win="close" class="is-close" title="Cerrar"><svg viewBox="0 0 24 24"><path d="M19 6.4 17.6 5 12 10.6 6.4 5 5 6.4l5.6 5.6L5 17.6 6.4 19l5.6-5.6 5.6 5.6 1.4-1.4-5.6-5.6L19 6.4Z"/></svg></button>
        </div>
      </header>
      <div class="ws-win-body">
        <div class="ws-win-loading"></div>
        <iframe title="${esc(win.title)}"></iframe>
      </div>
      ${["n", "s", "e", "w", "ne", "nw", "se", "sw"].map((d) => `<span class="ws-rz ws-rz-${d}" data-rz="${d}"></span>`).join("")}`;

    win.iframe = el.querySelector("iframe");
    win.titleEl = el.querySelector(".ws-win-title");

    el.addEventListener("pointerdown", () => focus(win), true);
    el.querySelector(".ws-win-tools").addEventListener("click", (e) => {
      const btn = e.target.closest("button[data-win]");
      if (!btn) return;
      const action = btn.dataset.win;
      if (action === "close") close(win);
      else if (action === "min") minimize(win);
      else if (action === "max") toggleMax(win);
      else if (action === "reload") reloadFrame(win);
      else if (action === "back") { try { win.iframe.contentWindow.history.back(); } catch (err) { /* nada */ } }
      else if (action === "popout") window.open(currentUrl(win), "_blank", "noopener");
    });

    const head = el.querySelector(".ws-win-head");
    head.addEventListener("dblclick", (e) => { if (!e.target.closest("button")) toggleMax(win); });
    head.addEventListener("pointerdown", (e) => startDrag(win, e));
    el.querySelectorAll("[data-rz]").forEach((h) => h.addEventListener("pointerdown", (e) => startResize(win, e, h.dataset.rz)));

    win.iframe.addEventListener("load", () => onFrameLoad(win));
    return el;
  }

  function buildTask(win) {
    const btn = document.createElement("button");
    btn.type = "button";
    btn.className = "ws-task";
    btn.setAttribute("role", "tab");
    btn.innerHTML = `${svg(win.icon)}<span>${esc(win.title)}</span><i class="ws-task-x" title="Cerrar">&times;</i>`;
    btn.addEventListener("click", (e) => {
      if (e.target.closest(".ws-task-x")) { close(win); return; }
      if (activeId === win.id && !win.min) minimize(win);
      else { restore(win); focus(win); }
    });
    btn.addEventListener("auxclick", (e) => { if (e.button === 1) close(win); });
    return btn;
  }

  function loadFrame(win) {
    if (win.iframe.getAttribute("src")) return;
    win.el.classList.add("is-loading");
    win.iframe.src = win.url;
  }
  function navigate(win, url) {
    win.el.classList.add("is-loading");
    win.iframe.src = url;
  }
  function reloadFrame(win) {
    win.el.classList.add("is-loading");
    try { win.iframe.contentWindow.location.reload(); } catch (e) { win.iframe.src = win.url; }
  }
  function currentUrl(win) {
    try {
      const loc = win.iframe.contentWindow.location;
      if (loc.href !== "about:blank") return loc.pathname + loc.search;
    } catch (e) { /* otro origen */ }
    return win.url;
  }

  function onFrameLoad(win) {
    if (!win.iframe.getAttribute("src")) return; // load de about:blank al insertar el iframe
    win.el.classList.remove("is-loading");
    try {
      const doc = win.iframe.contentDocument;
      const path = win.iframe.contentWindow.location.pathname + win.iframe.contentWindow.location.search;
      win.url = path;
      // Si el usuario navego dentro de la ventana, el titulo sigue al documento
      if (path !== win.homeUrl && doc && doc.title) setTitle(win, cleanTitle(doc.title));
      else if (path === win.homeUrl && win.originalTitle) setTitle(win, win.originalTitle);
      // Atajos de teclado tambien dentro del iframe
      doc.addEventListener("keydown", globalKeys);
      doc.addEventListener("pointerdown", () => focus(win));
    } catch (e) { /* otro origen */ }
    persist();
  }

  function cleanTitle(t) {
    return t.split("·").map((s) => s.trim()).filter((s) => s && s !== "BI Web").join(" · ") || t;
  }
  function setTitle(win, title) {
    if (!win.originalTitle) win.originalTitle = win.title;
    win.title = title;
    win.titleEl.textContent = title;
    win.task.querySelector("span").textContent = title;
    win.el.setAttribute("aria-label", title);
  }

  function applyGeometry(win) {
    const el = win.el;
    el.classList.toggle("is-max", win.max);
    el.classList.toggle("is-snap-left", win.snap === "left" && !win.max);
    el.classList.toggle("is-snap-right", win.snap === "right" && !win.max);
    if (!win.max && !win.snap) {
      el.style.left = win.x + "px";
      el.style.top = win.y + "px";
      el.style.width = win.w + "px";
      el.style.height = win.h + "px";
    }
  }

  function clampIntoView(win) {
    const b = bounds();
    win.w = Math.min(Math.max(MIN_W, win.w), Math.max(MIN_W, b.width));
    win.h = Math.min(Math.max(MIN_H, win.h), Math.max(MIN_H, b.height));
    win.x = Math.min(Math.max(-win.w + 120, win.x), b.width - 120);
    win.y = Math.min(Math.max(0, win.y), b.height - 40);
  }

  function focus(win) {
    if (activeId === win.id && win.el.classList.contains("is-active")) return;
    wins.forEach((w) => { w.el.classList.remove("is-active"); w.task.classList.remove("is-active"); });
    win.el.style.zIndex = ++zTop;
    win.el.classList.add("is-active");
    win.task.classList.add("is-active");
    activeId = win.id;
    markActiveLeaf(win.id);
    win.task.scrollIntoView({ block: "nearest", inline: "nearest" });
  }

  function focusTopmost() {
    const top = [...wins.values()].filter((w) => !w.min).sort((a, b) => b.el.style.zIndex - a.el.style.zIndex)[0];
    if (top) focus(top);
    else { activeId = null; markActiveLeaf(null); wins.forEach((w) => w.task.classList.remove("is-active")); }
  }

  function minimize(win) {
    win.min = true;
    win.el.classList.add("is-min");
    win.el.classList.remove("is-active");
    win.task.classList.add("is-min");
    win.task.classList.remove("is-active");
    if (activeId === win.id) focusTopmost();
    refreshEmpty();
    persist();
  }

  function restore(win) {
    if (!win.min) return;
    win.min = false;
    loadFrame(win);
    win.el.classList.remove("is-min");
    win.el.classList.add("is-open");
    win.task.classList.remove("is-min");
    refreshEmpty();
    persist();
  }

  function toggleMax(win) {
    if (MOBILE.matches) return;
    win.max = !win.max;
    if (!win.max) win.snap = null;
    applyGeometry(win);
    persist();
  }

  function close(win) {
    win.el.classList.add("is-closing");
    win.task.classList.add("is-closing");
    wins.delete(win.id);
    const done = () => { win.el.remove(); win.task.remove(); };
    setTimeout(done, 180);
    if (activeId === win.id) focusTopmost();
    refreshEmpty();
    persist();
  }

  function refreshEmpty() {
    emptyState.classList.toggle("is-hidden", [...wins.values()].some((w) => !w.min));
  }

  /* --- arrastrar, acoplar y redimensionar */
  function snapZone(clientX, clientY) {
    const b = bounds();
    if (clientY - b.top < 6) return "max";
    if (clientX - b.left < 10) return "left";
    if (b.right - clientX < 10) return "right";
    return null;
  }
  function showSnapPreview(zone) {
    if (!zone) { snapPreview.hidden = true; return; }
    snapPreview.hidden = false;
    snapPreview.className = "ws-snap-preview is-" + zone;
  }

  function startDrag(win, e) {
    if (e.button !== 0 || e.target.closest("button") || MOBILE.matches) return;
    e.preventDefault();
    const head = e.currentTarget;
    head.setPointerCapture(e.pointerId);
    desktop.classList.add("ws-busy");
    const b = bounds();
    // Desplazamiento del cursor dentro de la ventana, para que no "salte" al moverla
    let offX = e.clientX - b.left - win.el.offsetLeft;
    let offY = e.clientY - b.top - win.el.offsetTop;
    let moved = false;
    let zone = null;

    const move = (ev) => {
      if (!moved && Math.abs(ev.clientX - e.clientX) + Math.abs(ev.clientY - e.clientY) < 4) return;
      if (!moved) {
        moved = true;
        win.el.classList.add("is-dragging");
        // Arrastrar una ventana maximizada/acoplada la restaura bajo el cursor
        if (win.max || win.snap) {
          offX = Math.round(win.w * (offX / win.el.offsetWidth));
          offY = 18;
          win.max = false;
          win.snap = null;
          applyGeometry(win);
        }
      }
      win.x = Math.round(ev.clientX - b.left - offX);
      win.y = Math.round(ev.clientY - b.top - offY);
      win.x = Math.min(Math.max(-win.w + 120, win.x), b.width - 120);
      win.y = Math.min(Math.max(0, win.y), b.height - 40);
      win.el.style.left = win.x + "px";
      win.el.style.top = win.y + "px";
      zone = snapZone(ev.clientX, ev.clientY);
      showSnapPreview(zone);
    };
    const up = () => {
      head.removeEventListener("pointermove", move);
      desktop.classList.remove("ws-busy");
      win.el.classList.remove("is-dragging");
      showSnapPreview(null);
      if (moved && zone) {
        if (zone === "max") win.max = true;
        else win.snap = zone;
        applyGeometry(win);
      }
      if (moved) persist();
    };
    head.addEventListener("pointermove", move);
    head.addEventListener("pointerup", up, { once: true });
    head.addEventListener("pointercancel", up, { once: true });
  }

  function startResize(win, e, dir) {
    if (e.button !== 0 || win.max || MOBILE.matches) return;
    e.preventDefault();
    e.stopPropagation();
    const handle = e.currentTarget;
    handle.setPointerCapture(e.pointerId);
    desktop.classList.add("ws-busy");
    if (win.snap) {
      // Al redimensionar una ventana acoplada se toma su tamano actual
      win.x = win.el.offsetLeft; win.y = win.el.offsetTop;
      win.w = win.el.offsetWidth; win.h = win.el.offsetHeight;
      win.snap = null;
      applyGeometry(win);
    }
    const start = { x: e.clientX, y: e.clientY, wx: win.x, wy: win.y, ww: win.w, wh: win.h };
    const move = (ev) => {
      const dx = ev.clientX - start.x;
      const dy = ev.clientY - start.y;
      if (dir.includes("e")) win.w = Math.max(MIN_W, start.ww + dx);
      if (dir.includes("s")) win.h = Math.max(MIN_H, start.wh + dy);
      if (dir.includes("w")) {
        win.w = Math.max(MIN_W, start.ww - dx);
        win.x = start.wx + (start.ww - win.w);
      }
      if (dir.includes("n")) {
        win.h = Math.max(MIN_H, start.wh - dy);
        win.y = Math.max(0, start.wy + (start.wh - win.h));
      }
      applyGeometry(win);
    };
    const up = () => {
      handle.removeEventListener("pointermove", move);
      desktop.classList.remove("ws-busy");
      persist();
    };
    handle.addEventListener("pointermove", move);
    handle.addEventListener("pointerup", up, { once: true });
    handle.addEventListener("pointercancel", up, { once: true });
  }

  /* --- organizacion */
  function visibleWins() {
    return [...wins.values()].filter((w) => !w.min).sort((a, b) => a.el.style.zIndex - b.el.style.zIndex);
  }
  function cascade() {
    const list = visibleWins();
    const b = bounds();
    const w = Math.max(MIN_W, Math.round(b.width * 0.7));
    const h = Math.max(MIN_H, Math.round(b.height * 0.75));
    list.forEach((win, i) => {
      Object.assign(win, { max: false, snap: null, x: 24 + i * 30, y: 16 + i * 30, w, h });
      applyGeometry(win);
      focus(win);
    });
    persist();
  }
  function tile() {
    const list = visibleWins();
    if (!list.length) return;
    const b = bounds();
    const cols = Math.ceil(Math.sqrt(list.length));
    const rows = Math.ceil(list.length / cols);
    const gap = 8;
    const cw = Math.floor((b.width - gap * (cols + 1)) / cols);
    const ch = Math.floor((b.height - gap * (rows + 1)) / rows);
    list.forEach((win, i) => {
      Object.assign(win, {
        max: false, snap: null,
        x: gap + (i % cols) * (cw + gap),
        y: gap + Math.floor(i / cols) * (ch + gap),
        w: Math.max(MIN_W, cw), h: Math.max(MIN_H, ch),
      });
      applyGeometry(win);
    });
    persist();
  }

  /* --- persistencia de la sesion de trabajo */
  let persistTimer = null;
  function persist() {
    clearTimeout(persistTimer);
    persistTimer = setTimeout(() => {
      const data = [...wins.values()]
        .sort((a, b) => a.el.style.zIndex - b.el.style.zIndex)
        .map((w) => ({
          id: w.id, url: w.url, homeUrl: w.homeUrl, title: w.originalTitle || w.title, icon: w.icon,
          x: w.x, y: w.y, w: w.w, h: w.h, max: w.max, min: w.min, snap: w.snap,
        }));
      try { localStorage.setItem(cfg.storageKey, JSON.stringify(data)); } catch (e) { /* sin almacenamiento */ }
    }, 250);
  }
  function restoreSession() {
    let saved = [];
    try { saved = JSON.parse(localStorage.getItem(cfg.storageKey)) || []; } catch (e) { saved = []; }
    // Solo se restauran opciones que siguen en el arbol del usuario (los permisos pueden cambiar)
    saved = saved.filter((s) => leafById.has(s.id));
    saved.forEach((s) => {
      const win = open({ id: s.id, url: s.homeUrl || s.url, title: s.title, icon: s.icon }, s);
      clampIntoView(win);
      applyGeometry(win);
    });
    return saved.length > 0;
  }

  /* ========================================================= acciones */
  function runAction(action) {
    switch (action) {
      case "toggle-tree": toggleTree(); break;
      case "expand-all": treeEl.querySelectorAll(".ws-node.is-folder").forEach((li) => setExpanded(li, true)); break;
      case "collapse-all": treeEl.querySelectorAll(".ws-node.is-folder").forEach((li) => setExpanded(li, false)); break;
      case "cascade": cascade(); break;
      case "tile": tile(); break;
      case "show-desktop": wins.forEach((w) => { if (!w.min) minimize(w); }); break;
      case "close-all": wins.forEach((w) => close(w)); break;
    }
  }
  document.addEventListener("click", (e) => {
    const btn = e.target.closest("[data-ws-action]");
    if (btn) runAction(btn.dataset.wsAction);
  });

  // Los accesos de la barra superior abren ventanas en lugar de navegar
  document.querySelectorAll(".topbar a[data-window]").forEach((a) => {
    a.addEventListener("click", (e) => {
      if (e.ctrlKey || e.metaKey || e.shiftKey || e.button !== 0) return;
      e.preventDefault();
      const url = new URL(a.href).pathname;
      const leaf = leafById.get(url);
      open(leaf ? leaf.node : { id: url, url, title: a.dataset.window, icon: "window" });
    });
  });

  function globalKeys(e) {
    if ((e.ctrlKey || e.metaKey) && e.key.toLowerCase() === "k") {
      e.preventDefault();
      window.focus();
      toggleTree(false);
      filterInput.focus();
      filterInput.select();
    }
  }
  document.addEventListener("keydown", globalKeys);

  // Reloj de la barra de tareas
  const clock = $("ws-clock");
  const tick = () => { clock.textContent = new Date().toLocaleTimeString("es", { hour: "2-digit", minute: "2-digit" }); };
  tick();
  setInterval(tick, 30000);

  window.addEventListener("resize", () => {
    wins.forEach((w) => {
      if (MOBILE.matches) w.max = true;
      clampIntoView(w);
      applyGeometry(w);
    });
  });

  /* ============================================================ inicio */
  window.BIWorkspace = {
    open: (node) => open({ ...node, id: node.id || node.url }),
    close: (id) => { const w = wins.get(id); if (w) close(w); },
  };

  treeEl.appendChild(renderTree(cfg.tree));
  const firstRow = treeEl.querySelector(".ws-node-row");
  if (firstRow) firstRow.tabIndex = 0;

  if (!restoreSession() && cfg.homeUrl && leafById.has(cfg.homeUrl)) {
    open(leafById.get(cfg.homeUrl).node);
  }
  refreshEmpty();
})();
