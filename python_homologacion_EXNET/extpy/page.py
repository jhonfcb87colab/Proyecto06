"""
ExtPage: equivalente a una Razor Page de Ext.NET (index.cshtml + IndexModel).

    Razor Pages (Ext.NET)                   Flask (extpy)
    ------------------------------------    -----------------------------------
    @page "{handler?}" + IndexModel         page = ExtPage(...)
    public void OnGet()                     @page.on_get  -> devuelve componentes
    [Direct] OnPostEdit(...)                @page.direct_method
    OnPostDoSomething() (DirectEvent)       @page.direct_handler
    OnGetReadData(...) (AjaxProxy)          @page.route("/ReadData")
    services.AddExtNet()/UseExtNet()        app.register_blueprint(extpy_bp)
"""
import inspect
import os

from flask import Blueprint, Response, request, url_for

from .direct import DirectResponse
from .serializer import JS, to_js

# Ext.NET 7 incrusta Ext JS 7 (licencia comercial de Sencha). Por defecto se usa
# Ext JS 6.0.0 GPLv3 desde cdnjs; para producción apunte EXTJS_BASE a su copia
# licenciada de Ext JS 7.x (misma estructura de carpetas).
EXTJS_BASE = os.environ.get("EXTJS_BASE", "https://cdnjs.cloudflare.com/ajax/libs/extjs/6.0.0")
EXTJS_THEME = os.environ.get("EXTJS_THEME", "triton")

# Blueprint de recursos (equivale a app.UseExtNetResources)
extpy_bp = Blueprint("extpy", __name__, static_folder="static", static_url_path="/extpy")

_TEMPLATE = """<!DOCTYPE html>
<html>
<head>
    <meta charset="utf-8">
    <title>{title} - ExtPy Examples</title>
    <link rel="stylesheet" href="{base}/classic/theme-{theme}/resources/theme-{theme}-all.css">
    <script src="{base}/ext-all.js"></script>
    <script src="{base}/classic/theme-{theme}/theme-{theme}.js"></script>
    <script src="{runtime}"></script>
    <link rel="stylesheet" href="{css}">
{head}
</head>
<body>
{body}
<script>
Ext.onReady(function () {{
    ExtPy.boot({boot});
{direct_stubs}
{creates}
}});
</script>
</body>
</html>"""

# Componentes que no se "renderizan en sitio" (Ext.NET tampoco les pone renderTo)
_FLOATING = {"window", "viewport"}

# Registro global de páginas (lo usa el explorador, equivalente a TreeBuilder)
REGISTRY: list["ExtPage"] = []


class ExtPage:
    def __init__(self, path: str, title: str, source_file: str | None = None, listed: bool = True):
        self.path = path.strip("/")                    # p.ej. "gridpanel/editable/editor_with_directmethod"
        self.title = title
        self.source_file = source_file
        self.listed = listed
        self.url_prefix = "/samples/" + self.path
        self.blueprint = Blueprint(self.path.replace("/", "__"), __name__, url_prefix=self.url_prefix)
        self._on_get = None
        self._direct_methods: dict[str, inspect.Signature] = {}
        self.blueprint.add_url_rule("/", "index", self._render_get)
        self.blueprint.add_url_rule("/direct/<name>", "direct", self._dispatch_direct, methods=["POST"])
        self._handlers: dict[str, callable] = {}
        REGISTRY.append(self)

    # --- Decoradores -------------------------------------------------------
    def on_get(self, fn):
        """``fn() -> PageResult | Component | list[Component]``"""
        self._on_get = fn
        return fn

    def direct_method(self, fn=None, *, name=None):
        """[Direct] public IActionResult OnPostX(...) -> App.direct.X(...) en el cliente."""
        def deco(f):
            n = name or f.__name__
            self._handlers[n] = f
            self._direct_methods[n] = inspect.signature(f)
            return f
        return deco(fn) if fn else deco

    def direct_handler(self, fn=None, *, name=None):
        """OnPostX invocado desde un DirectEvent (sin stub App.direct)."""
        def deco(f):
            self._handlers[name or f.__name__] = f
            return f
        return deco(fn) if fn else deco

    def route(self, rule, **options):
        """Endpoint libre (p.ej. OnGetReadData para un AjaxProxy)."""
        return self.blueprint.route(rule, **options)

    def url(self, sub=""):
        return self.url_prefix + "/" + sub.lstrip("/")

    # --- Pipeline ---------------------------------------------------------
    def _dispatch_direct(self, name):
        fn = self._handlers.get(name)
        if fn is None:
            return Response(f"Direct handler '{name}' no existe", status=404)
        params = request.get_json(silent=True) or {}
        sig = inspect.signature(fn)
        accepts_kwargs = any(p.kind is p.VAR_KEYWORD for p in sig.parameters.values())
        kwargs = params if accepts_kwargs else {k: v for k, v in params.items() if k in sig.parameters}
        result = fn(**kwargs)
        if isinstance(result, DirectResponse):
            return result.to_flask()
        return DirectResponse(result).to_flask()

    def _render_get(self):
        result = self._on_get() if self._on_get else PageResult()
        if not isinstance(result, PageResult):
            result = PageResult(components=result)
        return render_page(self, result)


class PageResult:
    """Lo que devuelve on_get: componentes + HTML/JS adicional del .cshtml."""

    def __init__(self, components=None, head="", body="", duration_messages=None):
        if components is None:
            components = []
        elif not isinstance(components, (list, tuple)):
            components = [components]
        self.components = list(components)
        self.head, self.body = head, body
        self.duration_messages = duration_messages or []   # <ext-resourcemanager><DirectEventDurationMessages>


def render_page(page: ExtPage, result: PageResult) -> str:
    stubs = []
    for name, sig in page._direct_methods.items():
        args = list(sig.parameters)
        payload = "{" + ", ".join(f"{a}: {a}" for a in args) + "}"
        stubs.append(
            f"    App.direct.{name} = function ({', '.join(args + ['opts'])}) "
            f"{{ return ExtPy.request({to_js(name)}, {payload}, opts); }};"
        )

    creates = []
    for cmp in result.components:
        cfg = cmp.to_config()
        if cfg.get("xtype") not in _FLOATING and not cfg.get("floating"):
            cfg.setdefault("renderTo", JS("Ext.getBody()"))
        creates.append(f"    Ext.widget({to_js(cfg, 1)});")

    boot = {"baseUrl": page.url_prefix, "durationMessages": result.duration_messages}
    html = _TEMPLATE.format(
        title=page.title,
        base=EXTJS_BASE,
        theme=EXTJS_THEME,
        runtime=url_for("extpy.static", filename="extpy.js"),
        css=url_for("extpy.static", filename="examples.css"),
        head=result.head,
        body=result.body,
        boot=to_js(boot, 1),
        direct_stubs="\n".join(stubs),
        creates="\n".join(creates),
    )
    return Response(html, mimetype="text/html")
