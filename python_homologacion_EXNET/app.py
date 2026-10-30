"""
Explorador de ejemplos (homólogo de Program.cs + Startup.cs + TreeBuilder.cs + Pages/Index.cshtml).

    Program.Main / Startup.Configure   -> create_app()
    services.AddExtNet(), UseExtNet()  -> app.register_blueprint(extpy_bp)
    TreeBuilder.EnumerateExamples()    -> descubrimiento de módulos ejemplos.ej*
    TreeBuilder.PrettifyValue()        -> prettify()

Ejecutar:  python app.py   ->  http://127.0.0.1:5000/
"""
import importlib
import pkgutil
from pathlib import Path

from flask import Flask, Response, abort, redirect

import ejemplos
from extpy import (REGISTRY, ExtPage, JS, Listener, PageResult, Panel, TreeNode, TreePanel,
                   Viewport, extpy_bp)


def prettify(value: str) -> str:
    """TreeBuilder.PrettifyValue: 'basic_gridpanel' -> 'Basic Gridpanel'."""
    return value.replace("_", " ").title()


def discover_examples():
    for mod in pkgutil.iter_modules(ejemplos.__path__):
        if mod.name.startswith("ej"):
            importlib.import_module(f"ejemplos.{mod.name}")


def build_examples_tree():
    """Agrupa las páginas por categoría/subcategoría, como TreeBuilder.MapExamples."""
    root: dict = {}
    for page in sorted((p for p in REGISTRY if p.listed), key=lambda p: p.path):
        *folders, leaf = page.path.split("/")
        node = root
        for folder in folders:
            node = node.setdefault(folder, {})
        node[leaf] = page

    def to_nodes(tree: dict):
        nodes = []
        for name, value in tree.items():
            if isinstance(value, ExtPage):
                nodes.append(TreeNode(value.title, leaf=True, path=value.url_prefix + "/",
                                      source=f"/source/{value.path}"))
            else:
                nodes.append(TreeNode(prettify(name), expanded=True, children=to_nodes(value)))
        return nodes

    return TreeNode("Examples", expanded=True, children=to_nodes(root))


explorer = ExtPage("explorer", "Ext.NET -> Python", listed=False)


@explorer.on_get
def explorer_get():
    return PageResult(Viewport(layout="border", items=[
        TreePanel(
            region="west", width=320, split=True, title="Ejemplos homologados",
            root_visible=False, use_arrows=True, root=build_examples_tree(),
            listeners={"itemclick": Listener("""
                if (!record.isLeaf()) { return; }
                App.ExamplesPane.setTitle(record.get('text'));
                App.ExampleFrame.getEl().dom.src = record.get('path');
                App.SourceButton.sourceUrl = record.get('source');
                App.SourceButton.enable();""")},
        ),
        Panel(
            id="ExamplesPane", region="center", layout="fit", title="Seleccione un ejemplo",
            tbar=[{"xtype": "tbfill"}, {
                "xtype": "button", "id": "SourceButton", "text": "Ver código Python", "disabled": True,
                "handler": JS("function (b) { window.open(b.sourceUrl, '_blank'); }"),
            }],
            items=[{"xtype": "component", "id": "ExampleFrame",
                    "autoEl": {"tag": "iframe", "src": "about:blank",
                               "style": "border:0;width:100%;height:100%"}}],
        ),
    ]))


def create_app() -> Flask:
    discover_examples()
    app = Flask(__name__)
    app.register_blueprint(extpy_bp)
    for page in REGISTRY:
        app.register_blueprint(page.blueprint)

    @app.route("/")
    def home():
        return redirect(explorer.url_prefix + "/")

    @app.route("/source/<path:example>")
    def source(example):
        page = next((p for p in REGISTRY if p.path == example and p.source_file), None)
        if page is None:
            abort(404)
        return Response(Path(page.source_file).read_text(encoding="utf-8"), mimetype="text/plain")

    return app


if __name__ == "__main__":
    create_app().run(debug=True)
