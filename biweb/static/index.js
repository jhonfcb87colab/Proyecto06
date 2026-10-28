/* Pantalla de inicio: crear tableros e importar conexiones. */
(function () {
  "use strict";

  const cfg = window.BIWEB || {};
  let toastTimer = null;

  function toast(message, kind) {
    const box = document.getElementById("toast");
    if (!box) return;
    box.textContent = message;
    box.className = "toast " + (kind || "info");
    box.hidden = false;
    clearTimeout(toastTimer);
    toastTimer = setTimeout(() => {
      box.hidden = true;
    }, 4000);
  }

  async function api(path, options, retried) {
    const opts = Object.assign({}, options || {});
    const headers = Object.assign({ "Content-Type": "application/json", "X-BI-Mode": "design" }, opts.headers || {});
    const meta = document.querySelector('meta[name="csrf-token"]');
    if (meta) headers["X-CSRF-Token"] = meta.content;
    const token = localStorage.getItem("biweb-design-token");
    if (token) headers["X-Design-Token"] = token;
    opts.headers = headers;
    if (opts.body && typeof opts.body !== "string") opts.body = JSON.stringify(opts.body);
    const res = await fetch(path, opts);
    let body = null;
    try {
      body = await res.json();
    } catch (err) {
      body = null;
    }
    if (!res.ok) {
      const error = new Error((body && body.error) || res.statusText);
      error.code = body && body.code;
      if (error.code === "design_token" && !retried) {
        const value = window.prompt("Este servidor exige un token de diseno:");
        if (value) {
          localStorage.setItem("biweb-design-token", value);
          return api(path, options, true);
        }
      }
      throw error;
    }
    return body;
  }

  const form = document.getElementById("dashboard-form");
  if (form) {
    form.addEventListener("submit", (event) => {
      event.preventDefault();
      const name = form.elements.name.value.trim();
      const description = form.elements.description.value.trim();
      if (!name) return;
      api("/api/dashboards", { method: "POST", body: { name: name, description: description } })
        .then((dashboard) => {
          window.location.href = "/d/" + dashboard.id + "?mode=design";
        })
        .catch((err) => toast(err.message, "error"));
    });
  }

  const importForm = document.getElementById("import-form");
  if (importForm) {
    importForm.addEventListener("submit", (event) => {
      event.preventDefault();
      let payload;
      try {
        payload = JSON.parse(importForm.elements.payload.value.trim());
      } catch (err) {
        toast("JSON invalido: " + err.message, "error");
        return;
      }
      api("/api/connections/import", { method: "POST", body: payload })
        .then((res) => {
          const message =
            "Creadas " + res.created.length + " · actualizadas " + res.updated.length + " · fallidas " + res.failed.length;
          toast(message, res.failed.length ? "error" : "info");
          if (res.created.length || res.updated.length) {
            setTimeout(() => window.location.reload(), 900);
          }
        })
        .catch((err) => toast(err.message, "error"));
    });
  }

  document.querySelectorAll("[data-delete-dashboard]").forEach((button) => {
    button.addEventListener("click", () => {
      if (!window.confirm("¿Eliminar este tablero y todos sus widgets?")) return;
      api("/api/dashboards/" + button.dataset.deleteDashboard, { method: "DELETE" })
        .then(() => {
          const card = button.closest(".dash-card");
          if (card) card.remove();
          toast("Tablero eliminado");
        })
        .catch((err) => toast(err.message, "error"));
    });
  });

  if (!cfg.designEnabled) {
    document.querySelectorAll("#dashboard-form, #import-form").forEach((node) => {
      node.hidden = true;
    });
  }
})();
