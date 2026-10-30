"""Escritorio de trabajo: menu de arbol + ventanas (patron Ext.NET Explorer / Desktop).

Homologo de ``TreeBuilder.cs`` + ``Pages/Index.cshtml`` del framework
``python_homologacion_EXNET``: el servidor arma el arbol de navegacion y el
cliente (``static/workspace.js``) lo pinta y abre cada hoja en una ventana.

    Ext.NET / extpy                      biweb
    -----------------------------------  -----------------------------------
    TreePanel(root=TreeNode(...))        build_tree(user) -> lista de nodos
    TreeNode(text, leaf, path)           node(text, url=..., icon=...)
    Listener("itemclick", ...)           BIWorkspace.open(nodo)
    Window(layout="fit", items=[iframe]) ventana flotante con <iframe>
    Viewport(layout="border")            .ws-shell (west = arbol, center = escritorio)

Cada nodo se filtra por permisos aqui mismo: el cliente nunca recibe opciones
que el usuario no puede abrir (las rutas siguen validando por su cuenta).
"""
from __future__ import annotations

from flask import url_for

from . import auth
from .config import DESIGN_ENABLED


def node(text: str, *, url: str | None = None, icon: str = "", children: list | None = None,
         expanded: bool = False, window_id: str | None = None) -> dict:
    item: dict = {"text": text, "icon": icon}
    if children is not None:
        item["children"] = children
        item["expanded"] = expanded
    else:
        item["url"] = url
        # Mismo id => misma ventana (si ya esta abierta se enfoca en vez de duplicarla)
        item["id"] = window_id or url
    return item


def _dashboards_branch(user: dict) -> dict | None:
    if not auth.has_perm(user, "dashboards.view"):
        return None
    children = [node("Resumen de tableros", url=url_for("index"), icon="home")]
    for d in auth.dashboards_for(user):
        view_url = url_for("dashboard_only_view", dashboard_id=d["id"])
        if DESIGN_ENABLED and d.get("can_edit"):
            children.append(node(d["name"], icon="folder", children=[
                node("Visualizar", url=view_url, icon="chart"),
                node("Disenar", url=url_for("dashboard_view", dashboard_id=d["id"], mode="design"),
                     icon="design"),
            ]))
        else:
            children.append(node(d["name"], url=view_url, icon="chart"))
    return node("Tableros", icon="folder", children=children, expanded=True)


def _data_branch(user: dict) -> dict | None:
    children = []
    if DESIGN_ENABLED and auth.can_use_sql_console(user):
        children.append(node("Consola SQL", url=url_for("sql_console"), icon="terminal"))
    if not children:
        return None
    return node("Datos", icon="folder", children=children, expanded=True)


def _admin_branch(user: dict) -> dict | None:
    entries = [
        ("admin.users", "Usuarios", "admin.users", "users"),
        ("admin.roles", "Roles y permisos", "admin.roles", "shield"),
        ("access.manage", "Accesos por tablero", "admin.access", "key"),
        ("monitoring.audit", "Auditoria", "admin.audit", "list"),
    ]
    children = [
        node(label, url=url_for(endpoint), icon=icon)
        for perm, label, endpoint, icon in entries
        if auth.has_perm(user, perm)
    ]
    if not children:
        return None
    return node("Administracion", icon="folder", children=children)


def build_tree(user: dict | None) -> list[dict]:
    if not user:
        return []
    branches = [_dashboards_branch(user), _data_branch(user), _admin_branch(user)]
    tree = [b for b in branches if b]
    tree.append(node("Mi cuenta", icon="folder", children=[
        node("Cambiar contrasena", url=url_for("account"), icon="user"),
    ]))
    return tree
