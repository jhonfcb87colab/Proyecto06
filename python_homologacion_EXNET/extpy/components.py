"""
Modelo de componentes equivalente a las clases C# de Ext.NET
(Ext.Net.Panel, Ext.Net.GridPanel, ...) y a los TagHelpers <ext-*>.

Cada clase solo conoce su ``xtype`` de Ext JS; las propiedades se pasan como
kwargs en snake_case y se emiten en camelCase:

    C#      new Panel { Title = "West", BodyPadding = 18 }
    Razor   <ext-panel title="West" bodyPadding="18" />
    Python  Panel(title="West", body_padding=18)
"""
import json

from .serializer import JS, camel, net_date_format, to_js


# Firma de argumentos que Ext.NET inyecta en cada ``Handler`` según el evento.
# (Ext.NET envuelve el Handler en ``function(<args>){ ... }``.)
EVENT_ARGS = {
    "click": ("item", "e"),
    "change": ("item", "newValue", "oldValue"),
    "select": ("item", "record", "index"),
    "itemclick": ("item", "record", "node", "index", "e"),
    "afteritemexpand": ("node", "index", "item"),
    "afteritemcollapse": ("node", "index", "item"),
    "edit": ("editor", "e"),
    "show": ("item",),
    "afterrender": ("item",),
}


class Listener:
    """Equivale a ``<click handler="..." buffer="30" />`` / ``ClickListener``.

    ``handler``: cuerpo JS (Ext.NET lo envuelve en una función).
    ``fn``:      nombre/expresión de una función JS ya existente.
    """

    def __init__(self, handler=None, fn=None, buffer=None, args=None, scope=None):
        self.handler, self.fn, self.buffer, self.args, self.scope = handler, fn, buffer, args, scope

    def render(self, event: str):
        if self.fn:
            fn = JS(self.fn)
        else:
            args = ", ".join(self.args or EVENT_ARGS.get(event.lower(), ("item",)))
            fn = JS(f"function ({args}) {{ {self.handler} }}")
        cfg = {"fn": fn}
        if self.buffer is not None:
            cfg["buffer"] = self.buffer
        if self.scope is not None:
            cfg["scope"] = JS(self.scope)
        return cfg


class Component:
    xtype = None

    def __init__(self, **config):
        self.config = {camel(k): v for k, v in config.items()}

    # --- API estilo "code-behind" (west.Items.Add(panel)) -----------------
    @property
    def items(self) -> list:
        return self.config.setdefault("items", [])

    def add(self, *components):
        self.items.extend(components)
        return self

    def __setitem__(self, key, value):
        self.config[camel(key)] = value

    # --- Serialización ------------------------------------------------------
    def to_config(self) -> dict:
        cfg = {"xtype": self.xtype} if self.xtype else {}
        listeners = {}
        for key, value in self.config.items():
            if key == "listeners":
                listeners.update(value)
            elif key == "directEvents":
                # DirectEvents de Ext.NET = listeners que hacen POST al servidor
                for event, direct_event in value.items():
                    listeners[event] = direct_event
            else:
                cfg[key] = value
        if listeners:
            cfg["listeners"] = {
                ev: (l.render(ev) if hasattr(l, "render") else l) for ev, l in listeners.items()
            }
        return cfg


def _component(name, xtype, base=Component, doc=None):
    cls = type(name, (base,), {"xtype": xtype, "__doc__": doc or f"<ext-{name[:1].lower() + name[1:]}> -> xtype '{xtype}'"})
    return cls


# --- Contenedores ---------------------------------------------------------
Container = _component("Container", "container")
Panel = _component("Panel", "panel")
Window = _component("Window", "window")
Viewport = _component("Viewport", "viewport")
TabPanel = _component("TabPanel", "tabpanel")
FormPanel = _component("FormPanel", "form")
FieldSet = _component("FieldSet", "fieldset")
Toolbar = _component("Toolbar", "toolbar")
PagingToolbar = _component("PagingToolbar", "pagingtoolbar")

# --- Controles ------------------------------------------------------------
Button = _component("Button", "button")
Label = _component("Label", "label")
TextField = _component("TextField", "textfield")
TextArea = _component("TextArea", "textareafield")
NumberField = _component("NumberField", "numberfield")
Checkbox = _component("Checkbox", "checkbox")
ComboBox = _component("ComboBox", "combobox")

# --- Grid / Tree ----------------------------------------------------------
GridPanel = _component("GridPanel", "grid")
TreePanel = _component("TreePanel", "treepanel")
Column = _component("Column", "gridcolumn")


class DateColumn(Column):
    """<ext-dateColumn format="yyyy-MM-dd"> : el formato .NET se traduce a Ext."""
    xtype = "datecolumn"

    def __init__(self, format=None, **config):
        super().__init__(**config)
        if format:
            self.config["format"] = net_date_format(format)


class DateField(Component):
    xtype = "datefield"

    def __init__(self, format=None, **config):
        super().__init__(**config)
        if format:
            self.config["format"] = net_date_format(format)


# --- Datos ----------------------------------------------------------------
_FIELD_TYPES = {"String": "string", "Int": "int", "Float": "float", "Date": "date",
                "Bool": "boolean", "Boolean": "boolean", "Auto": "auto"}


def DataField(name, type=None, **config):
    """<ext-dataField name="rating" type="Int" />"""
    cfg = {"name": name, **{camel(k): v for k, v in config.items()}}
    if type:
        cfg["type"] = _FIELD_TYPES.get(type, type.lower())
    return cfg


class Store(Component):
    """<ext-store>. No es un widget: se emite sin xtype dentro de ``store``."""

    def __init__(self, fields=None, data=None, sorters=None, proxy=None, id_property=None, **config):
        super().__init__(**config)
        self.id_property = id_property
        for key, value in (("fields", fields), ("data", data), ("sorters", sorters), ("proxy", proxy)):
            if value is not None:
                self.config[key] = value

    def to_config(self):
        cfg = dict(self.config)
        if self.id_property and "fields" in cfg:
            # <ext-model idProperty="..."> -> modelo anónimo de Ext JS
            cfg["model"] = JS(
                f"Ext.define(null, {{ extend: 'Ext.data.Model', idProperty: {json.dumps(self.id_property)}, "
                f"fields: {to_js(cfg.pop('fields'))} }})"
            )
        return cfg


def Sorter(property, direction="ASC"):
    return {"property": property, "direction": direction}


def AjaxProxy(url, root_property="data", total_property="total", **extra):
    """<ext-ajaxProxy url="..."><reader><ext-jsonReader .../></reader></ext-ajaxProxy>"""
    return {
        "type": "ajax",
        "url": url,
        "reader": {"type": "json", "rootProperty": root_property, "totalProperty": total_property},
        **{camel(k): v for k, v in extra.items()},
    }


def TreeNode(text, children=None, expanded=None, leaf=None, icon_cls=None, **extra):
    """Ext.Net.TreeNode -> nodo de árbol de Ext JS."""
    node = {"text": text}
    if icon_cls:
        node["iconCls"] = icon_cls
    if expanded is not None:
        node["expanded"] = expanded
    if leaf:
        node["leaf"] = True
    elif children is not None:
        node["children"] = children
    node.update({camel(k): v for k, v in extra.items()})
    return node
