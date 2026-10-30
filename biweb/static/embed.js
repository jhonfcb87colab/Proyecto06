/*
 * Puente entre una pagina y el escritorio (workspace.js) cuando la pagina corre
 * dentro de una ventana. Equivale al registro App.* de extpy.js: desde el iframe
 * se llama a window.top.BIWorkspace.open(...) para abrir otra ventana.
 */
(() => {
  if (!document.documentElement.classList.contains("embedded")) return;
  const ws = window.top.BIWorkspace;

  // Sesion vencida: el login no debe quedar atrapado dentro de una ventana
  if (document.body.classList.contains("auth-page")) {
    // Recargar el escritorio lo manda al login con next=/workspace
    window.top.location.reload();
    return;
  }

  // Tableros, disenador y enlaces "nueva pestana" se abren como ventanas nuevas
  const OPEN_AS_WINDOW = /^\/(view|d)\/\d+/;
  document.addEventListener("click", (event) => {
    if (event.defaultPrevented || event.button !== 0 || event.ctrlKey || event.metaKey || event.shiftKey) return;
    const link = event.target.closest("a[href]");
    if (!link) return;
    const url = new URL(link.href, window.location.href);
    if (url.origin !== window.location.origin) return;
    if (link.target !== "_blank" && !link.dataset.window && !OPEN_AS_WINDOW.test(url.pathname)) return;
    event.preventDefault();
    const text = (link.dataset.window || link.closest("article")?.querySelector("h3")?.textContent || link.textContent).trim();
    ws.open({ url: url.pathname + url.search, title: text, icon: "chart" });
  });
})();
