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


def _compile_expression(expression: str):
    expression = (expression or "").strip()
    if not expression:
        raise ModelError("La expresion Python esta vacia")
    if len(expression) > MAX_EXPRESSION_LENGTH:
        raise ModelError("La expresion es demasiado larga")
    try:
        tree = ast.parse(expression, mode="eval")
    except SyntaxError as exc:
        raise ModelError(f"Expresion Python invalida: {exc.msg}") from exc
    _validate(tree, {"rows", "row"})
    return compile(tree, "<model>", "eval")


def validate_expression(expression: str) -> None:
    """Valida la sintaxis y las operaciones permitidas sin ejecutar la expresion."""
    _compile_expression(expression)


def evaluate(expression: str, rows: list[dict], row: dict | None = None) -> Any:
    compiled = _compile_expression(expression)
    try:
        return eval(
            compiled,
            {"__builtins__": {}},
            {**SAFE_FUNCS, **SAFE_NAMES, "rows": rows, "row": row},
        )
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
) -> dict:
    kind = (kind or "measure").strip().lower()
    config = dict(config or {})
    limit = max(1, min(int(limit or 50), 50_000))
    columns = list(columns or (list(rows[0].keys()) if rows else []))

    if kind == "measure":
        value = evaluate(expression, rows)
        return {"kind": kind, "value": _jsonable(value), "rows": len(rows)}

    if kind == "column":
        name = str(config.get("name") or "calculada").strip() or "calculada"
        out = []
        for row in rows[:limit]:
            new_row = dict(row)
            new_row[name] = _jsonable(evaluate(expression, rows, row))
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
        result = evaluate(expression, rows)
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
