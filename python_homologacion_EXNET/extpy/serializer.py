"""
Serializador Python -> literal JavaScript.

Ingeniería inversa de Ext.NET:
  * Ext.NET serializa las propiedades C# (PascalCase) a camelCase:
    ``Restaurant.Name`` llega al cliente como ``name``.
  * Los atributos ``mode="Raw"`` de <ext-add> y propiedades como ``Handler``
    o ``Renderer`` se emiten como JavaScript crudo (sin comillas).
  * Los formatos de fecha .NET (``yyyy-MM-dd``) se traducen al formato de
    Ext JS (``Y-m-d``).

Aquí replicamos las tres reglas.
"""
import dataclasses
import datetime as dt
import enum
import json
import re
from decimal import Decimal


class JS(str):
    """JavaScript crudo. Equivale a ``mode="Raw"`` en Ext.NET."""


def camel(name: str) -> str:
    """snake_case -> camelCase (body_padding -> bodyPadding)."""
    if "_" not in name.strip("_"):
        return name
    head, *rest = name.split("_")
    return head + "".join(p[:1].upper() + p[1:] for p in rest if p)


# Tokens de formato .NET -> Ext.Date (orden: los más largos primero)
_NET_DATE_TOKENS = [
    ("yyyy", "Y"), ("yy", "y"),
    ("MMMM", "F"), ("MMM", "M"), ("MM", "m"), ("M", "n"),
    ("dddd", "l"), ("ddd", "D"), ("dd", "d"), ("d", "j"),
    ("HH", "H"), ("H", "G"), ("hh", "h"), ("h", "g"),
    ("mm", "i"), ("ss", "s"), ("tt", "A"),
]
_NET_DATE_RE = re.compile("|".join(re.escape(t) for t, _ in _NET_DATE_TOKENS))


def net_date_format(fmt: str) -> str:
    """Convierte un formato de fecha .NET al de Ext JS: 'yyyy-MM-dd' -> 'Y-m-d'."""
    mapping = dict(_NET_DATE_TOKENS)
    return _NET_DATE_RE.sub(lambda m: mapping[m.group(0)], fmt)


def to_js(value, indent: int = 0) -> str:
    """Convierte un valor Python en un literal JavaScript (JSON + JS crudo)."""
    pad = "  " * (indent + 1)
    end = "  " * indent

    if isinstance(value, JS):
        return str(value)
    if hasattr(value, "to_config"):
        return to_js(value.to_config(), indent)
    if dataclasses.is_dataclass(value) and not isinstance(value, type):
        # Igual que Ext.NET: propiedades del objeto en camelCase
        return to_js({camel(k): v for k, v in dataclasses.asdict(value).items()}, indent)
    if isinstance(value, enum.Enum):
        return to_js(value.value, indent)
    if isinstance(value, (dt.datetime, dt.date)):
        return json.dumps(value.isoformat())
    if isinstance(value, Decimal):
        return str(value)
    if isinstance(value, dict):
        if not value:
            return "{}"
        body = ",\n".join(f"{pad}{json.dumps(str(k))}: {to_js(v, indent + 1)}" for k, v in value.items())
        return "{\n" + body + "\n" + end + "}"
    if isinstance(value, (list, tuple)):
        if not value:
            return "[]"
        body = ",\n".join(pad + to_js(v, indent + 1) for v in value)
        return "[\n" + body + "\n" + end + "]"
    return json.dumps(value)


def to_json_data(value):
    """Versión 'solo datos' (sin JS) para respuestas AJAX tipo AjaxProxy."""
    if dataclasses.is_dataclass(value) and not isinstance(value, type):
        return {k: to_json_data(v) for k, v in dataclasses.asdict(value).items()}
    if isinstance(value, dict):
        return {k: to_json_data(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [to_json_data(v) for v in value]
    if isinstance(value, (dt.datetime, dt.date)):
        return value.isoformat()
    return value
