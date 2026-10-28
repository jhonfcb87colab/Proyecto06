/* Consola SQL para roles Desarrollo y Administrador. */
(function () {
  "use strict";

  const cfg = window.BIWEB || {};
  const state = { connections: [], running: false };
  const $ = (selector) => document.querySelector(selector);
  const esc = (window.BICharts && window.BICharts.esc) || ((v) => String(v == null ? "" : v));

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

  function apiHeaders() {
    const headers = { "Content-Type": "application/json", "X-BI-Mode": "design" };
    const meta = document.querySelector('meta[name="csrf-token"]');
    if (meta) headers["X-CSRF-Token"] = meta.content;
    const token = localStorage.getItem("biweb-design-token");
    if (token) headers["X-Design-Token"] = token;
    return headers;
  }

  async function api(path, options, retried) {
    const opts = Object.assign({}, options || {});
    opts.headers = Object.assign(apiHeaders(), opts.headers || {});
    if (opts.body && typeof opts.body !== "string") opts.body = JSON.stringify(opts.body);
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

  function option(value, label) {
    const opt = document.createElement("option");
    opt.value = value == null ? "" : String(value);
    opt.textContent = label == null ? String(value) : label;
    return opt;
  }

  function fillConnections() {
    const select = $("#sql-connection");
    if (!select) return;
    select.innerHTML = "";
    if (!state.connections.length) {
      select.appendChild(option("", "Sin conexiones disponibles"));
      select.disabled = true;
      return;
    }
    select.disabled = false;
    state.connections.forEach((conn) => {
      select.appendChild(option(conn.id, conn.name + " (" + conn.kind + ")"));
    });
    const saved = localStorage.getItem("biweb-sql-connection");
    const match = state.connections.find((conn) => String(conn.id) === String(saved));
    const first = state.connections[0];
    if (match) select.value = String(match.id);
    else if (first) select.value = String(first.id);
  }

  function currentConnection() {
    const id = $("#sql-connection").value;
    return state.connections.find((conn) => String(conn.id) === String(id)) || null;
  }

  async function loadConnections() {
    try {
      state.connections = await api("/api/connections");
      fillConnections();
      if (!state.connections.length) {
        setBadge("Sin conexiones", "badge-view");
        toast("Primero crea una conexion desde el panel de diseno", "error");
      }
    } catch (err) {
      setBadge("Error", "badge-off");
      toast(err.message, "error");
    }
  }

  function setBadge(text, cls) {
    const badge = $("#sql-badge");
    if (!badge) return;
    badge.textContent = text;
    badge.className = "badge " + (cls || "");
  }

  function summary(result) {
    const bits = [
      result.statement_count + " sentencia(s)",
      result.elapsed_ms + " ms",
      result.committed ? "commit realizado" : "sin cambios permanentes",
    ];
    const node = $("#sql-summary");
    if (node) node.textContent = bits.join(" · ");
  }

  function statementBlock(item) {
    const block = document.createElement("section");
    block.className = "console-statement";

    const head = document.createElement("div");
    head.className = "console-statement-head";
    const badge = document.createElement("span");
    badge.className = "badge " + (item.type === "query" ? "badge-view" : "badge-soft");
    badge.textContent = "Sentencia " + item.index + " · " + (item.type === "query" ? "consulta" : "comando");
    head.appendChild(badge);

    const info = document.createElement("span");
    info.className = "hint";
    if (item.type === "query") {
      info.textContent =
        item.row_count +
        " fila(s)" +
        (item.truncated ? " · vista parcial" : "");
    } else {
      info.textContent =
        item.rowcount == null ? "sentencia ejecutada" : "fila(s) afectadas: " + item.rowcount;
    }
    head.appendChild(info);
    block.appendChild(head);

    if (item.type === "query" && item.columns && item.columns.length) {
      const table = document.createElement("div");
      table.className = "mini-table console-table";
      window.BICharts.render(table, {
        type: "table",
        columns: item.columns,
        rows: item.rows || [],
        truncated: item.truncated,
        format: { format: "number", decimals: 2 },
      });
      block.appendChild(table);
    } else if (item.type === "command") {
      const pre = document.createElement("pre");
      pre.className = "result ok";
      pre.textContent =
        item.rowcount == null
          ? "Comando ejecutado correctamente."
          : "Filas afectadas: " + item.rowcount;
      block.appendChild(pre);
    }

    const details = document.createElement("details");
    details.className = "console-sql";
    const sum = document.createElement("summary");
    sum.textContent = "Ver SQL ejecutado";
    const pre = document.createElement("pre");
    pre.className = "result";
    pre.textContent = item.statement || "";
    details.appendChild(sum);
    details.appendChild(pre);
    block.appendChild(details);

    return block;
  }

  function renderResult(result) {
    const box = $("#sql-results");
    if (!box) return;
    box.innerHTML = "";
    summary(result);
    if (!result.statements || !result.statements.length) {
      box.innerHTML = '<p class="empty">No se ejecuto ninguna sentencia.</p>';
      return;
    }
    result.statements.forEach((item) => box.appendChild(statementBlock(item)));
  }

  function renderError(message) {
    const box = $("#sql-results");
    if (!box) return;
    box.innerHTML = "";
    const pre = document.createElement("pre");
    pre.className = "result error";
    pre.textContent = message;
    box.appendChild(pre);
    const node = $("#sql-summary");
    if (node) node.textContent = "Error de ejecucion";
  }

  function setRunning(value) {
    state.running = value;
    const button = $("#sql-run");
    if (button) {
      button.disabled = value;
      button.textContent = value ? "Ejecutando..." : "Ejecutar (Ctrl+Enter)";
    }
    setBadge(value ? "Ejecutando" : "Listo", value ? "badge-design" : "");
  }

  async function run() {
    if (state.running) return;
    const connection = currentConnection();
    const sql = $("#sql-text").value.trim();
    const mode = $("#sql-mode").value;
    if (!connection) {
      toast("Selecciona una conexion", "error");
      return;
    }
    if (!sql) {
      toast("Escribe el codigo SQL", "error");
      return;
    }
    if (mode === "write") {
      const ok = window.confirm(
        "Modo escritura activado.\n\nSe ejecutaran las sentencias y se hara COMMIT si todo termina bien. ¿Continuar?"
      );
      if (!ok) return;
    }
    setRunning(true);
    try {
      const result = await api("/api/sql/execute", {
        method: "POST",
        body: { connection_id: Number(connection.id), sql: sql, mode: mode, limit: 200 },
      });
      renderResult(result);
      setBadge("Completado", "badge-view");
      toast("SQL ejecutado en " + connection.name, "info");
    } catch (err) {
      renderError(err.message);
      setBadge("Error", "badge-off");
      toast(err.message, "error");
    } finally {
      state.running = false;
      const button = $("#sql-run");
      if (button) {
        button.disabled = false;
        button.textContent = "Ejecutar (Ctrl+Enter)";
      }
    }
  }

  function pyString(value) {
    return JSON.stringify(value == null ? "" : String(value));
  }

  function pythonSnippet(connection, sql, mode) {
    const config = connection.config || {};
    const sqlValue = pyString(sql);
    const commit = mode === "write";
    if (connection.kind === "sqlite") {
      return (
        "import sqlite3\n\n" +
        "con = sqlite3.connect(" + pyString(config.path || "var/sample.db") + ")\n" +
        "sql = " + sqlValue + "\n\n" +
        "try:\n" +
        "    cur = con.cursor()\n" +
        "    cur.execute(sql)\n" +
        "    if cur.description:\n" +
        "        for row in cur.fetchmany(200):\n" +
        "            print(row)\n" +
        "    else:\n" +
        "        print(\"Filas afectadas:\", cur.rowcount)\n" +
        (commit ? "    con.commit()\n" : "    con.rollback()\n") +
        "except Exception:\n" +
        "    con.rollback()\n" +
        "    raise\n" +
        "finally:\n" +
        "    con.close()\n"
      );
    }
    if (connection.kind === "sqlserver") {
      const server = config.port ? config.host + "," + config.port : config.host;
      let connStr =
        "DRIVER={ODBC Driver 18 for SQL Server};SERVER=" + server +
        ";DATABASE=" + (config.database || "") +
        ";Encrypt=" + (config.encrypt || "yes") +
        ";TrustServerCertificate=" + (config.trust_server_certificate || "yes");
      if (String(config.trusted_connection || "no").toLowerCase() === "yes") {
        connStr += ";Trusted_Connection=yes";
      } else {
        connStr += ";UID=" + (config.user || "") + ";PWD=********";
      }
      return (
        "import pyodbc\n\n" +
        "conn = pyodbc.connect(\n" +
        "    " + pyString(connStr) + ",\n" +
        "    autocommit=False,\n" +
        ")\n" +
        "# Reemplaza ******** por la contrasena real.\n" +
        "sql = " + sqlValue + "\n\n" +
        "try:\n" +
        "    cur = conn.cursor()\n" +
        "    cur.execute(sql)\n" +
        "    if cur.description:\n" +
        "        for row in cur.fetchmany(200):\n" +
        "            print(row)\n" +
        "    else:\n" +
        "        print(\"Filas afectadas:\", cur.rowcount)\n" +
        (commit ? "    conn.commit()\n" : "    conn.rollback()\n") +
        "except Exception:\n" +
        "    conn.rollback()\n" +
        "    raise\n" +
        "finally:\n" +
        "    conn.close()\n"
      );
    }
    if (connection.kind === "postgres") {
      const dsn =
        "host=" + (config.host || "") +
        " port=" + (config.port || 5432) +
        " dbname=" + (config.database || "") +
        " user=" + (config.user || "") +
        " password=********";
      return (
        "import psycopg2\n\n" +
        "conn = psycopg2.connect(" + pyString(dsn) + ")\n" +
        "conn.set_session(readonly=False, autocommit=False)\n" +
        "# Reemplaza ******** por la contrasena real.\n" +
        "sql = " + sqlValue + "\n\n" +
        "try:\n" +
        "    cur = conn.cursor()\n" +
        "    cur.execute(sql)\n" +
        "    if cur.description:\n" +
        "        for row in cur.fetchmany(200):\n" +
        "            print(row)\n" +
        "    else:\n" +
        "        print(\"Filas afectadas:\", cur.rowcount)\n" +
        (commit ? "    conn.commit()\n" : "    conn.rollback()\n") +
        "except Exception:\n" +
        "    conn.rollback()\n" +
        "    raise\n" +
        "finally:\n" +
        "    conn.close()\n"
      );
    }
    return (
      "import pymysql\n\n" +
      "conn = pymysql.connect(\n" +
      "    host=" + pyString(config.host || "") + ",\n" +
      "    port=" + (config.port || 3306) + ",\n" +
      "    database=" + pyString(config.database || "") + ",\n" +
      "    user=" + pyString(config.user || "") + ",\n" +
      "    password=\"********\",  # reemplaza por la contrasena real\n" +
      "    charset=\"utf8mb4\",\n" +
      "    autocommit=False,\n" +
      ")\n" +
      "sql = " + sqlValue + "\n\n" +
      "try:\n" +
      "    cur = conn.cursor()\n" +
      "    cur.execute(sql)\n" +
      "    if cur.description:\n" +
      "        for row in cur.fetchmany(200):\n" +
      "            print(row)\n" +
      "    else:\n" +
      "        print(\"Filas afectadas:\", cur.rowcount)\n" +
      (commit ? "    conn.commit()\n" : "    conn.rollback()\n") +
      "except Exception:\n" +
      "    conn.rollback()\n" +
      "    raise\n" +
      "finally:\n" +
      "    conn.close()\n"
    );
  }

  function copyText(text) {
    if (navigator.clipboard && navigator.clipboard.writeText) {
      return navigator.clipboard.writeText(text);
    }
    const area = document.createElement("textarea");
    area.value = text;
    area.style.position = "fixed";
    area.style.opacity = "0";
    document.body.appendChild(area);
    area.select();
    const ok = document.execCommand("copy");
    document.body.removeChild(area);
    return ok ? Promise.resolve() : Promise.reject(new Error("No se pudo copiar"));
  }

  function showPython() {
    const connection = currentConnection();
    const sql = $("#sql-text").value.trim();
    if (!connection || !sql) {
      toast("Selecciona una conexion y escribe SQL", "error");
      return;
    }
    const mode = $("#sql-mode").value;
    const code = pythonSnippet(connection, sql, mode);
    const box = $("#sql-results");
    if (box) {
      box.innerHTML = "";
      const head = document.createElement("div");
      head.className = "console-statement-head";
      const badge = document.createElement("span");
      badge.className = "badge badge-soft";
      badge.textContent = "Python · " + connection.kind;
      head.appendChild(badge);
      const hint = document.createElement("span");
      hint.className = "hint";
      hint.textContent = "Reemplaza la contrasena antes de ejecutar";
      head.appendChild(hint);
      box.appendChild(head);
      const pre = document.createElement("pre");
      pre.className = "result console-python";
      pre.textContent = code;
      box.appendChild(pre);
    }
    copyText(code)
      .then(() => toast("Codigo Python copiado al portapapeles", "info"))
      .catch((err) => toast(err.message, "error"));
    const node = $("#sql-summary");
    if (node) node.textContent = "Codigo Python generado";
  }

  function bind() {
    const form = $("#sql-form");
    if (form) {
      form.addEventListener("submit", (event) => {
        event.preventDefault();
        run();
      });
    }
    const text = $("#sql-text");
    if (text) {
      text.addEventListener("keydown", (event) => {
        if ((event.ctrlKey || event.metaKey) && event.key === "Enter") {
          event.preventDefault();
          run();
        }
      });
    }
    const connectionSelect = $("#sql-connection");
    if (connectionSelect) {
      connectionSelect.addEventListener("change", () => {
        if (connectionSelect.value) {
          localStorage.setItem("biweb-sql-connection", connectionSelect.value);
        }
      });
    }
    const python = $("#sql-python");
    if (python) python.addEventListener("click", showPython);
    const clear = $("#sql-clear");
    if (clear) {
      clear.addEventListener("click", () => {
        $("#sql-text").value = "";
        $("#sql-text").focus();
        $("#sql-results").innerHTML = '<p class="empty">Los resultados de cada sentencia apareceran aqui.</p>';
        const node = $("#sql-summary");
        if (node) node.textContent = "";
        setBadge("Listo", "");
      });
    }
    const tokenBox = $("#token-box");
    if (tokenBox) tokenBox.hidden = !cfg.tokenRequired;
    const tokenInput = $("#design-token");
    if (tokenInput) {
      tokenInput.value = localStorage.getItem("biweb-design-token") || "";
      tokenInput.addEventListener("change", () => {
        const value = tokenInput.value.trim();
        if (value) localStorage.setItem("biweb-design-token", value);
        else localStorage.removeItem("biweb-design-token");
        toast("Token guardado en este navegador");
        loadConnections();
      });
    }
  }

  bind();
  loadConnections();
})();
