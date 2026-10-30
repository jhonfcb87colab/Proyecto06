"""
Homologación de la capa "Direct" de Ext.NET.

Ext.NET (ingeniería inversa del protocolo):
  * [DirectModel] + [Direct] OnPostEdit(...)  -> genera en el cliente
    ``App.direct.Edit(id, field, oldValue, newValue)`` que hace un POST a
    ``?handler=Edit`` y ejecuta el script devuelto por el servidor.
  * <DirectEvents><Click pageHandler="DoSomething"/>  -> un listener ``click``
    que hace POST al handler ``OnPostDoSomething``.
  * ``this.X().Toast(...)`` / ``this.X().AddScript(...)`` + ``return this.Direct()``
    -> el servidor acumula instrucciones JS y las devuelve en la respuesta.

En Python: POST JSON a ``<url de la página>/direct/<Nombre>`` y la respuesta
``{"script": "...", "result": ...}`` la ejecuta ``static/extpy.js``.
"""
from flask import jsonify

from .serializer import JS, camel, to_js


class DurationMessage(dict):
    """<ext-durationMessage Duration="1000" Message="..." />"""

    def __init__(self, duration: int, message: str):
        super().__init__(duration=duration, message=message)


class EventMask(dict):
    """<EventMask><ext-eventMask msg="..."><DurationMessages>...</ext-eventMask>"""

    def __init__(self, msg="Working...", duration_messages=None, **extra):
        super().__init__(msg=msg, **{camel(k): v for k, v in extra.items()})
        if duration_messages:
            self["durationMessages"] = list(duration_messages)


class DirectEvent:
    """<Click pageHandler="DoSomething" method="POST"> dentro de <DirectEvents>.

    ``extra_params``: dict nombre -> expresión JS evaluada en el cliente
    (equivale a <ExtraParams><ext-add key="..." value="App.Txt.getValue()" mode="Raw"/>).
    """

    def __init__(self, handler: str, event_mask=None, extra_params=None, confirmation=None):
        self.handler, self.event_mask = handler, event_mask
        self.extra_params, self.confirmation = extra_params or {}, confirmation

    def render(self, event: str):
        params = "{" + ", ".join(f"{k!r}: ({v})" for k, v in self.extra_params.items()) + "}"
        opts = {}
        if self.event_mask is not None:
            opts["eventMask"] = self.event_mask
        if self.confirmation:
            opts["confirmation"] = self.confirmation
        return {"fn": JS(
            f"function () {{ ExtPy.request({to_js(self.handler)}, {params}, {to_js(opts)}); }}"
        )}


class DirectResponse:
    """Equivalente a ``this.X()`` + ``return this.Direct(result)``."""

    def __init__(self, result=None):
        self.result = result
        self.scripts: list[str] = []

    # this.X().AddScript("...")
    def add_script(self, script: str):
        self.scripts.append(script.rstrip(";") + ";")
        return self

    # this.X().Toast("...")
    def toast(self, html: str, title: str | None = None, align: str = "t"):
        cfg = {"html": html, "align": align}
        if title:
            cfg["title"] = title
        return self.add_script(f"Ext.toast({to_js(cfg)})")

    # this.X().Msg.Alert(title, msg).Show()
    def alert(self, title: str, message: str):
        return self.add_script(f"Ext.Msg.alert({to_js(title)}, {to_js(message)})")

    # this.GetCmp<Label>("Label1").Html = "..." -> App.Label1.setHtml(...)
    def call(self, component_id: str, method: str, *args):
        return self.add_script(f"App.{component_id}.{method}({', '.join(to_js(a) for a in args)})")

    def to_flask(self):
        return jsonify({"script": "\n".join(self.scripts), "result": self.result})
