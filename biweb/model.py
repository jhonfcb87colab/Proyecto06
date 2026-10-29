"""Modelado ligero: medidas, columnas y tablas calculadas con Python.

No pretende ser un motor DAX completo. Las expresiones se validan con un
subconjunto de Python y se ejecutan sobre las filas de un dataset.
"""
from __future__ import annotations

import ast
import math
import statistics
from datetime import date, datetime, time as dt_time
from decimal import Decimal
from typing import Any

MAX_EXPRESSION_LENGTH = 4_000
MAX_AST_NODES = 600

QUICK_MEASURES = {
    "sum": "Suma",
    "avg": "Promedio",
    "count": "Conteo",
    "distinct": "Conteo distinto",
    "min": "Minimo",
    "max": "Maximo",
    "median": "Mediana",
    "stdev": "Desviacion estandar",
}


class ModelError(ValueError):
    pass


def _jsonable(value: Any) -> Any:
    if value is None or isinstance(value, (str, int, bool)):
        return value
    if isinstance(value, float):
        return value if math.isfinite(value) else None
    if isinstance(value, Decimal):
        number = float(value)
        return number if math.isfinite(number) else None
    if isinstance(value, (datetime, date, dt_time)):
        return value.isoformat()
    if isinstance(value, (bytes, bytearray, memoryview)):
        return bytes(value).hex()
    return str(value)


def _number(value: Any) -> float | None:
    if isinstance(value, bool):
        return 1.0 if value else 0.0
    if isinstance(value, (int, float)):
        number = float(value)
        return number if math.isfinite(number) else None
    if isinstance(value, Decimal):
        number = float(value)
        return number if math.isfinite(number) else None
    if isinstance(value, str):
        try:
            return float(value.replace(",", "").strip())
        except ValueError:
            return None
    return None


def _values(rows: list[dict], field: str | None) -> list[Any]:
    if not field:
        return list(rows)
    return [row.get(field) for row in rows]


def _numbers(rows: list[dict], field: str | None) -> list[float]:
    return [n for n in (_number(v) for v in _values(rows, field)) if n is not None]


def sum_field(rows: list[dict], field: str | None = None) -> float:
    return float(sum(_numbers(rows, field)))


def avg_field(rows: list[dict], field: str | None = None) -> float:
    values = _numbers(rows, field)
    return float(sum(values) / len(values)) if values else 0.0


def count_field(rows: list[dict], field: str | None = None) -> int:
    if not field:
        return len(rows)
    return sum(1 for value in _values(rows, field) if value is not None and value != "")


def distinct_field(rows: list[dict], field: str | None = None) -> int:
    return len({str(v) for v in _values(rows, field) if v is not None and v != ""})


def min_field(rows: list[dict], field: str | None = None) -> float:
    values = _numbers(rows, field)
    return float(min(values)) if values else 0.0


def max_field(rows: list[dict], field: str | None = None) -> float:
    values = _numbers(rows, field)
    return float(max(values)) if values else 0.0


def median_field(rows: list[dict], field: str | None = None) -> float:
    values = _numbers(rows, field)
    return float(statistics.median(values)) if values else 0.0


def stdev_field(rows: list[dict], field: str | None = None) -> float:
    values = _numbers(rows, field)
    return float(statistics.pstdev(values)) if len(values) > 1 else 0.0


def value_at(rows: list[dict], field: str, index: int = 0) -> Any:
    try:
        return rows[int(index)].get(field)
    except (IndexError, TypeError, ValueError):
        return None


def field(row: dict, name: str, default: Any = None) -> Any:
    return row.get(name, default)


def ifelse(condition: Any, when_true: Any, when_false: Any) -> Any:
    return when_true if condition else when_false


def coalesce(*values: Any) -> Any:
    for value in values:
        if value is not None and value != "":
            return value
    return None


def pct(value: Any, total: Any) -> float:
    number = _number(value) or 0.0
    base = _number(total) or 0.0
    return (number / base * 100.0) if base else 0.0


def derive(rows: list[dict], name: str, expression: str) -> list[dict]:
    out = []
    for row in rows:
        new_row = dict(row)
        new_row[name] = evaluate(expression, rows, row)
        out.append(new_row)
    return out


def sort_rows(rows: list[dict], field_name: str, desc: bool = True) -> list[dict]:
    def key(row: dict):
        value = row.get(field_name)
        number = _number(value)
        return (number is None, number if number is not None else 0.0, str(value or ""))

    return sorted(rows, key=key, reverse=bool(desc))


def limit_rows(rows: list[dict], count: int = 100) -> list[dict]:
    return list(rows)[: max(0, int(count))]


def _merge_key(row: dict, field_name: str) -> Any:
    value = row.get(field_name)
    try:
        hash(value)
    except TypeError:
        return str(value)
    return value


def _merge_row(
    left_row: dict | None,
    right_row: dict | None,
    left_key: str | None,
    right_key: str | None,
) -> dict:
    out = dict(left_row or {})
    for key, value in (right_row or {}).items():
        if right_row is not None and key == right_key and key == left_key:
            continue
        target = key
        if target in out:
            base = f"{key}_right"
            target = base
            suffix = 2
            while target in out:
                target = f"{base}{suffix}"
                suffix += 1
        out[target] = value
    return out


def merge(
    left: list[dict],
    right: list[dict],
    left_key: str,
    right_key: str | None = None,
    how: str = "inner",
) -> list[dict]:
    """Cruza dos tablas por una llave y devuelve una lista de filas."""
    if not isinstance(left, list) or not isinstance(right, list):
        raise ValueError("merge espera dos listas de filas")
    mode = str(how or "inner").strip().lower()
    if mode not in {"inner", "left", "right", "outer"}:
        raise ValueError("how debe ser inner, left, right u outer")
    right_key = right_key or left_key
    index: dict[Any, list[tuple[int, dict]]] = {}
    for position, row in enumerate(right):
        if not isinstance(row, dict):
            continue
        key = _merge_key(row, right_key)
        if key is not None:
            index.setdefault(key, []).append((position, row))
    matched: set[int] = set()
    out: list[dict] = []
    for left_row in left:
        if not isinstance(left_row, dict):
            continue
        key = _merge_key(left_row, left_key)
        matches = index.get(key, []) if key is not None else []
        if matches:
            for position, right_row in matches:
                matched.add(position)
                out.append(_merge_row(left_row, right_row, left_key, right_key))
        elif mode in {"left", "outer"}:
            out.append(_merge_row(left_row, None, left_key, right_key))
    if mode in {"right", "outer"}:
        for position, right_row in enumerate(right):
            if position in matched or not isinstance(right_row, dict):
                continue
            out.append(_merge_row(None, right_row, left_key, right_key))
    return out


def inner_join(left: list[dict], right: list[dict], left_key: str, right_key: str | None = None) -> list[dict]:
    """Atajo de merge con cruce interior."""
    return merge(left, right, left_key, right_key, "inner")


def left_join(left: list[dict], right: list[dict], left_key: str, right_key: str | None = None) -> list[dict]:
    """Atajo de merge conservando todas las filas de la tabla izquierda."""
    return merge(left, right, left_key, right_key, "left")


def right_join(left: list[dict], right: list[dict], left_key: str, right_key: str | None = None) -> list[dict]:
    """Atajo de merge conservando todas las filas de la tabla derecha."""
    return merge(left, right, left_key, right_key, "right")


def outer_join(left: list[dict], right: list[dict], left_key: str, right_key: str | None = None) -> list[dict]:
    """Atajo de merge con cruce exterior completo."""
    return merge(left, right, left_key, right_key, "outer")


def append_rows(*tables: list[dict]) -> list[dict]:
    """Une verticalmente varias tablas en una sola lista de filas."""
    out: list[dict] = []
    for index, table in enumerate(tables):
        if not isinstance(table, list):
            raise ValueError(f"La tabla {index + 1} debe ser una lista de filas")
        out.extend(dict(row) for row in table if isinstance(row, dict))
    return out


def union_tables(*tables: list[dict]) -> list[dict]:
    """Alias de append_rows para unir tablas verticalmente."""
    return append_rows(*tables)


def cross_tables(left: list[dict], right: list[dict]) -> list[dict]:
    """Producto cartesiano entre dos tablas."""
    if not isinstance(left, list) or not isinstance(right, list):
        raise ValueError("cross_tables espera dos listas de filas")
    out: list[dict] = []
    for left_row in left:
        if not isinstance(left_row, dict):
            continue
        for right_row in right:
            if not isinstance(right_row, dict):
                continue
            out.append(_merge_row(left_row, right_row, None, None))
    return out


SAFE_FUNCS = {
    "sum_field": sum_field,
    "avg_field": avg_field,
    "count_field": count_field,
    "distinct_field": distinct_field,
    "min_field": min_field,
    "max_field": max_field,
    "median_field": median_field,
    "stdev_field": stdev_field,
    "value_at": value_at,
    "field": field,
    "ifelse": ifelse,
    "coalesce": coalesce,
    "pct": pct,
    "derive": derive,
    "sort_rows": sort_rows,
    "limit_rows": limit_rows,
    "merge": merge,
    "join_tables": merge,
    "inner_join": inner_join,
    "left_join": left_join,
    "right_join": right_join,
    "outer_join": outer_join,
    "append_rows": append_rows,
    "union_tables": union_tables,
    "cross_tables": cross_tables,
    "abs": abs,
    "round": round,
    "len": len,
    "min": min,
    "max": max,
    "sum": sum,
    "float": float,
    "int": int,
    "str": str,
    "sqrt": math.sqrt,
    "log": math.log,
    "exp": math.exp,
    "floor": math.floor,
    "ceil": math.ceil,
    "pow": pow,
}

SAFE_NAMES = {
    "True": True,
    "False": False,
    "None": None,
    "pi": math.pi,
    "e": math.e,
}

_ALLOWED_NODES = (
    ast.Expression,
    ast.Constant,
    ast.Name,
    ast.Load,
    ast.BinOp,
    ast.UnaryOp,
    ast.BoolOp,
    ast.Compare,
    ast.IfExp,
    ast.Subscript,
    ast.Slice,
    ast.List,
    ast.Tuple,
    ast.Dict,
    ast.Call,
    ast.keyword,
    ast.Add,
    ast.Sub,
    ast.Mult,
    ast.Div,
    ast.FloorDiv,
    ast.Mod,
    ast.Pow,
    ast.UAdd,
    ast.USub,
    ast.Not,
    ast.And,
    ast.Or,
    ast.Eq,
    ast.NotEq,
    ast.Lt,
    ast.LtE,
    ast.Gt,
    ast.GtE,
    ast.In,
    ast.NotIn,
)


def _validate(tree: ast.AST, context_names: set[str]) -> None:
    nodes = list(ast.walk(tree))
    if len(nodes) > MAX_AST_NODES:
        raise ModelError("La expresion es demasiado compleja")
    for node in nodes:
        if not isinstance(node, _ALLOWED_NODES):
            raise ModelError(f"Construccion no permitida: {type(node).__name__}")
        if isinstance(node, ast.Call):
            if not isinstance(node.func, ast.Name) or node.func.id not in SAFE_FUNCS:
                raise ModelError("Solo se pueden usar las funciones permitidas")
            if any(isinstance(arg, ast.Starred) for arg in node.args):
                raise ModelError("No se permite el desempaquetado de argumentos")
        if isinstance(node, ast.Name):
            if node.id not in SAFE_FUNCS and node.id not in SAFE_NAMES and node.id not in context_names:
                raise ModelError(f"Nombre no permitido: {node.id}")


def _compile_expression(expression: str, extra_names: set[str] | None = None):
    expression = (expression or "").strip()
    if not expression:
        raise ModelError("La expresion Python esta vacia")
    if len(expression) > MAX_EXPRESSION_LENGTH:
        raise ModelError("La expresion es demasiado larga")
    try:
        tree = ast.parse(expression, mode="eval")
    except SyntaxError as exc:
        raise ModelError(f"Expresion Python invalida: {exc.msg}") from exc
    names = {"rows", "row", "tables"}
    if extra_names:
        names.update(extra_names)
    _validate(tree, names)
    return compile(tree, "<model>", "eval")


def validate_expression(expression: str, extra_names: set[str] | None = None) -> None:
    """Valida la sintaxis y las operaciones permitidas sin ejecutar la expresion."""
    _compile_expression(expression, extra_names)


def evaluate(
    expression: str,
    rows: list[dict],
    row: dict | None = None,
    tables: dict[str, list[dict]] | None = None,
) -> Any:
    table_map: dict[str, list[dict]] = {}
    extra_names: set[str] = set()
    if isinstance(tables, dict):
        for alias, table_rows in tables.items():
            if not isinstance(alias, str) or not alias.isidentifier():
                continue
            if alias in {"rows", "row", "tables"} or alias in SAFE_FUNCS or alias in SAFE_NAMES:
                continue
            if not isinstance(table_rows, list):
                continue
            table_map[alias] = table_rows
            extra_names.add(alias)
    compiled = _compile_expression(expression, extra_names)
    scope = {**SAFE_FUNCS, **SAFE_NAMES, "rows": rows, "row": row, "tables": table_map}
    scope.update(table_map)
    try:
        return eval(compiled, {"__builtins__": {}}, scope)
    except ModelError:
        raise
    except Exception as exc:  # noqa: BLE001
        raise ModelError(f"Error evaluando la expresion: {exc}") from exc


def _profile_column(rows: list[dict], name: str) -> dict:
    values = [row.get(name) for row in rows]
    present = [value for value in values if value is not None and value != ""]
    numbers = [n for n in (_number(v) for v in present) if n is not None]
    distinct = len({str(v) for v in present})
    kind = "number" if present and len(numbers) == len(present) else "text"
    column = {
        "name": name,
        "type": kind,
        "distinct": distinct,
        "nulls": len(values) - len(present),
        "count": len(present),
        "sample": [_jsonable(v) for v in present[:3]],
    }
    if numbers:
        column["min"] = round(min(numbers), 6)
        column["max"] = round(max(numbers), 6)
        column["sum"] = round(sum(numbers), 6)
        column["avg"] = round(sum(numbers) / len(numbers), 6)
    return column


def profile(rows: list[dict], columns: list[str] | None = None) -> dict:
    if not columns:
        columns = list(rows[0].keys()) if rows else []
    columns = list(columns)
    per_column = [_profile_column(rows, name) for name in columns]
    numeric = [c for c in per_column if c["type"] == "number"]
    distinct_sum = sum(c["distinct"] for c in per_column)
    nulls = sum(c["nulls"] for c in per_column)
    estimated = max(1, len(rows) * max(1, len(columns)) * 24)
    return {
        "rows": len(rows),
        "columns": len(columns),
        "numeric_columns": len(numeric),
        "text_columns": len(columns) - len(numeric),
        "distinct_total": distinct_sum,
        "null_cells": nulls,
        "estimated_bytes": estimated,
        "estimated_label": _bytes_label(estimated),
        "fields": per_column,
    }


def _bytes_label(value: int) -> str:
    size = float(value)
    for unit in ("B", "KB", "MB", "GB", "TB"):
        if size < 1024 or unit == "TB":
            return f"{size:.1f} {unit}"
        size /= 1024
    return f"{value} B"


def preview(
    kind: str,
    expression: str,
    rows: list[dict],
    columns: list[str] | None = None,
    config: dict | None = None,
    limit: int = 50,
    tables: dict[str, list[dict]] | None = None,
) -> dict:
    kind = (kind or "measure").strip().lower()
    config = dict(config or {})
    limit = max(1, min(int(limit or 50), 50_000))
    columns = list(columns or (list(rows[0].keys()) if rows else []))

    if kind == "measure":
        value = evaluate(expression, rows, tables=tables)
        return {"kind": kind, "value": _jsonable(value), "rows": len(rows)}

    if kind == "column":
        name = str(config.get("name") or "calculada").strip() or "calculada"
        out = []
        for row in rows[:limit]:
            new_row = dict(row)
            new_row[name] = _jsonable(evaluate(expression, rows, row, tables=tables))
            out.append(new_row)
        return {
            "kind": kind,
            "column": name,
            "columns": columns + ([name] if name not in columns else []),
            "rows": out,
            "row_count": len(out),
            "truncated": len(rows) > limit,
        }

    if kind == "table_calc":
        result = evaluate(expression, rows, tables=tables)
        if not isinstance(result, list):
            raise ModelError("La tabla calculada debe devolver una lista de filas")
        result = [row for row in result if isinstance(row, dict)]
        out_columns: list[str] = []
        for row in result:
            for key in row.keys():
                if key not in out_columns:
                    out_columns.append(key)
        out_rows = [{key: _jsonable(row.get(key)) for key in out_columns} for row in result[:limit]]
        return {
            "kind": kind,
            "columns": out_columns,
            "rows": out_rows,
            "row_count": len(result),
            "truncated": len(result) > limit,
        }

    if kind == "table_created":
        out_columns = [str(c) for c in config.get("columns") or []]
        source_rows = config.get("rows") or []
        if not isinstance(source_rows, list):
            raise ModelError("config.rows debe ser una lista de objetos")
        if not out_columns and source_rows:
            for row in source_rows:
                if isinstance(row, dict):
                    for key in row.keys():
                        if key not in out_columns:
                            out_columns.append(key)
        out_rows = []
        for row in source_rows[:limit]:
            if isinstance(row, dict):
                out_rows.append({key: _jsonable(row.get(key)) for key in out_columns})
        return {
            "kind": kind,
            "columns": out_columns,
            "rows": out_rows,
            "row_count": len(source_rows),
            "truncated": len(source_rows) > limit,
        }

    raise ModelError(f"Tipo de modelo no soportado: {kind}")
