"""Agregacion y preparacion de datos para los widgets."""
from __future__ import annotations

import math
import re
from typing import Any

DATE_RE = re.compile(r"^\d{4}[-/]\d{1,2}([-/]\d{1,2})?([T ]\d{2}:\d{2}(:\d{2})?)?")
AGGREGATIONS = {"sum", "avg", "min", "max", "count", "count_distinct"}

TABLE_TYPES = {"table", "matrix"}
KPI_TYPES = {"kpi", "card"}
POINT_TYPES = {"scatter", "bubble"}
MAP_TYPES = {"map_basic", "map_choropleth", "map_bubble", "map_arcgis"}
INTERACTION_TYPES = {"slicer", "nav_buttons", "bookmark", "tooltip", "filter_panel"}
MERGE_SERIES = {"pie", "doughnut", "funnel", "treemap", "pareto"}

CHART_TYPES = {
    "table",
    "matrix",
    "decomposition",
    "decomp_tree",
    "kpi",
    "card",
    "multi_row",
    "bar",
    "bar_grouped",
    "bar_stacked",
    "bar_100",
    "column_grouped",
    "column_stacked",
    "column_100",
    "combo",
    "line",
    "area",
    "area_stacked",
    "scatter",
    "bubble",
    "waterfall",
    "funnel",
    "pie",
    "doughnut",
    "treemap",
    "gauge",
    "pareto",
    "key_influencers",
    "qna",
    "correlation",
    "map_basic",
    "map_choropleth",
    "map_bubble",
    "map_arcgis",
    "slicer",
    "nav_buttons",
    "bookmark",
    "tooltip",
    "filter_panel",
}


def _is_number(value: Any) -> bool:
    return isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(float(value))


def _to_number(value: Any) -> float | None:
    if isinstance(value, bool):
        return 1.0 if value else 0.0
    if isinstance(value, (int, float)):
        number = float(value)
        return number if math.isfinite(number) else None
    if isinstance(value, str):
        try:
            return float(value.replace(",", "").strip())
        except ValueError:
            return None
    return None


def infer_fields(columns: list[str], rows: list[dict], sample: int = 300) -> list[dict]:
    fields = []
    for column in columns:
        values = [row.get(column) for row in rows[:sample] if row.get(column) is not None]
        kind = "text"
        if values and all(_is_number(v) for v in values):
            kind = "number"
        elif values and all(isinstance(v, str) and DATE_RE.match(v) for v in values):
            kind = "date"
        fields.append({"name": column, "type": kind})
    return fields


def _aggregate(values: list[Any], agg: str) -> float:
    if agg == "count":
        return float(len(values))
    if agg == "count_distinct":
        return float(len({str(v) for v in values if v is not None}))
    numbers = [n for n in (_to_number(v) for v in values) if n is not None]
    if not numbers:
        return 0.0
    if agg == "avg":
        return sum(numbers) / len(numbers)
    if agg == "min":
        return min(numbers)
    if agg == "max":
        return max(numbers)
    return float(sum(numbers))


def _widget_config(widget: dict) -> dict:
    return widget.get("config") or {}


def _guess_columns(columns: list[str], rows: list[dict], config: dict) -> tuple[str | None, str | None]:
    fields = infer_fields(columns, rows)
    numeric = [f["name"] for f in fields if f["type"] == "number"]
    other = [f["name"] for f in fields if f["type"] != "number"]
    x = config.get("x") or (other[0] if other else (columns[0] if columns else None))
    y = config.get("y") or (numeric[0] if numeric else None)
    return x, y


def _aggregation(config: dict) -> str:
    agg = str(config.get("agg") or "sum").lower()
    return agg if agg in AGGREGATIONS else "sum"


def _format_info(config: dict) -> dict:
    return {
        "format": config.get("format") or "number",
        "decimals": int(config.get("decimals") or 0),
        "currency": config.get("currency") or "USD",
        "max": config.get("max"),
        "target": config.get("target"),
    }


def empty_chart(widget: dict, reason: str = "Sin datos") -> dict:
    chart_type = widget.get("chart_type", "table")
    base = {
        "type": chart_type,
        "labels": [],
        "series": [],
        "rows": [],
        "columns": [],
        "points": [],
        "items": [],
        "reason": reason,
        "empty": True,
    }
    if chart_type in KPI_TYPES:
        base.update({"value": None, "label": _widget_config(widget).get("label") or ""})
    return base


def _raw_table(chart_type: str, columns, rows, config, format_info) -> dict:
    limit = int(config.get("limit") or 200)
    return {
        "type": chart_type,
        "columns": columns,
        "rows": rows[:limit],
        "row_count": len(rows),
        "truncated": len(rows) > limit,
        "format": format_info,
    }


def _grouped(
    rows: list[dict],
    columns: list[str],
    config: dict,
    format_info: dict,
    chart_type: str,
    question: str | None = None,
) -> dict:
    x, y = _guess_columns(columns, rows, config)
    agg = _aggregation(config)
    series_field = config.get("series") or None
    limit = int(config.get("limit") or 0)
    sort = str(config.get("sort") or "none")
    if not rows or not x:
        result = empty_chart({"chart_type": chart_type, "config": config})
        if question:
            result["question"] = question
        return result

    labels: list[str] = []
    series_names: list[str] = []
    buckets: dict[str, dict[str, list[Any]]] = {}
    for row in rows:
        label_value = row.get(x)
        label = "(vacio)" if label_value is None else str(label_value)
        if label not in buckets:
            buckets[label] = {}
            labels.append(label)
        series_value = row.get(series_field) if series_field else None
        series_name = "(todas)" if not series_field else ("(vacio)" if series_value is None else str(series_value))
        if series_name not in buckets[label]:
            buckets[label][series_name] = []
            if series_name not in series_names:
                series_names.append(series_name)
        value = row.get(y) if y else 1
        buckets[label][series_name].append(value)

    def total_for(label: str) -> float:
        return sum(abs(_aggregate(buckets.get(label, {}).get(name, []), agg)) for name in series_names)

    if sort == "value_desc" or chart_type in {"pareto", "funnel"}:
        labels.sort(key=total_for, reverse=True)
    elif sort == "value_asc":
        labels.sort(key=total_for)
    elif sort == "label_desc":
        labels.sort(reverse=True)
    elif sort == "label_asc":
        labels.sort()

    if limit:
        labels = labels[:limit]

    series = [
        {
            "name": name,
            "data": [round(_aggregate(buckets.get(label, {}).get(name, []), agg), 6) for label in labels],
        }
        for name in series_names
    ]

    if chart_type in MERGE_SERIES and len(series) > 1:
        merged = [round(sum(v for v in values), 6) for values in zip(*[s["data"] for s in series])]
        series = [{"name": y or "valor", "data": merged}]

    result = {
        "type": chart_type,
        "labels": labels,
        "series": series,
        "x": x,
        "y": y,
        "agg": agg,
        "format": format_info,
        "row_count": len(rows),
        "truncated": bool(config.get("_truncated")),
        "reason": None if labels else "Sin datos para los campos elegidos",
    }
    if question:
        result["question"] = question
    if chart_type == "pareto" and series and labels:
        values = series[0]["data"]
        total = sum(abs(Number(v)) for v in values) or 1
        running = 0.0
        cumulative = []
        for value in values:
            running += abs(Number(value))
            cumulative.append(round((running / total) * 100, 4))
        result["cumulative"] = cumulative
    return result


def _matrix(rows, columns, config, format_info):
    x, y = _guess_columns(columns, rows, config)
    field_types = {field["name"]: field["type"] for field in infer_fields(columns, rows)}
    series_field = config.get("series")
    if series_field not in columns:
        series_field = next(
            (name for name in columns if name != x and field_types.get(name) != "number"),
            None,
        )
    if not rows or not x:
        return _raw_table("matrix", columns, rows, config, format_info)
    agg = _aggregation(config)
    labels = []
    column_names = []
    buckets: dict[str, dict[str, list[Any]]] = {}
    for row in rows:
        label = row.get(x)
        label = "(vacio)" if label is None else str(label)
        if label not in buckets:
            buckets[label] = {}
            labels.append(label)
        if series_field:
            column = row.get(series_field)
            column = "(vacio)" if column is None else str(column)
        else:
            column = y or "Valor"
        if column not in buckets[label]:
            buckets[label][column] = []
            if column not in column_names:
                column_names.append(column)
        buckets[label][column].append(row.get(y) if y else 1)
    limit = int(config.get("limit") or 200)
    labels = labels[:limit]
    out_rows = []
    for label in labels:
        value_row = {x: label}
        total = 0.0
        for column in column_names:
            value = round(_aggregate(buckets[label].get(column, []), agg), 6)
            value_row[column] = value
            total += value
        if len(column_names) > 1:
            value_row["Total"] = round(total, 6)
        out_rows.append(value_row)
    out_columns = [x] + column_names + (["Total"] if len(column_names) > 1 else [])
    return {
        "type": "matrix",
        "columns": out_columns,
        "rows": out_rows,
        "row_count": len(labels),
        "truncated": len(buckets) > len(labels),
        "format": format_info,
        "x": x,
        "y": y,
        "series": series_field,
        "agg": agg,
    }


def _hierarchy(rows, columns, config, format_info, chart_type):
    grouped = _grouped(rows, columns, config, format_info, chart_type)
    labels = grouped.get("labels") or []
    series = grouped.get("series") or []
    if not labels or not series:
        return grouped
    children = []
    total = 0.0
    for index, label in enumerate(labels):
        branches = []
        subtotal = 0.0
        for item in series:
            value = Number(item["data"][index])
            subtotal += value
            if item["name"] != "(todas)":
                branches.append({"label": item["name"], "value": value})
        total += subtotal
        children.append({"label": label, "value": subtotal, "children": branches})
    grouped["type"] = chart_type
    grouped["tree"] = {
        "label": config.get("label") or grouped.get("x") or "Total",
        "value": total,
        "children": children,
    }
    return grouped


def Number(value: Any) -> float:
    number = _to_number(value)
    return 0.0 if number is None else number


def _multi_row(rows, columns, config, format_info, chart_type):
    fields = [f for f in infer_fields(columns, rows) if f["type"] == "number"][:6]
    agg = _aggregation(config)
    items = [
        {
            "label": field["name"],
            "value": round(_aggregate([row.get(field["name"]) for row in rows], agg), 6),
        }
        for field in fields
    ]
    return {
        "type": chart_type,
        "items": items,
        "format": format_info,
        "agg": agg,
        "row_count": len(rows),
        "reason": None if items else "El dataset no tiene columnas numericas",
    }


def _scatter(rows, columns, config, format_info, chart_type):
    fields = infer_fields(columns, rows)
    numeric = [f["name"] for f in fields if f["type"] == "number"]
    text = [f["name"] for f in fields if f["type"] != "number"]
    if len(numeric) < 2:
        return {
            "type": chart_type,
            "points": [],
            "reason": "Se necesitan al menos dos columnas numericas",
            "format": format_info,
        }
    x_field = config.get("x") if config.get("x") in numeric else numeric[0]
    y_field = config.get("y") if config.get("y") in numeric and config.get("y") != x_field else next(
        (name for name in numeric if name != x_field), numeric[0]
    )
    size_field = config.get("size") if config.get("size") in numeric else None
    label_field = (
        config.get("label_field")
        if config.get("label_field") in columns
        else (config.get("label") if config.get("label") in columns else (text[0] if text else None))
    )
    limit = int(config.get("limit") or 500)
    points = []
    for index, row in enumerate(rows[:limit]):
        xv = _to_number(row.get(x_field))
        yv = _to_number(row.get(y_field))
        if xv is None or yv is None:
            continue
        size = _to_number(row.get(size_field)) if size_field else 1.0
        label = row.get(label_field) if label_field else f"Fila {index + 1}"
        points.append(
            {
                "x": round(xv, 6),
                "y": round(yv, 6),
                "size": abs(size or 1.0),
                "label": str(label),
            }
        )
    return {
        "type": chart_type,
        "points": points,
        "x_field": x_field,
        "y_field": y_field,
        "size_field": size_field,
        "format": format_info,
        "row_count": len(points),
        "reason": None if points else "Sin puntos con coordenadas numericas",
    }


def _find_field(columns: list[str], *needles: str) -> str | None:
    for column in columns:
        low = column.lower()
        if any(needle in low for needle in needles):
            return column
    return None


def _map(rows, columns, config, format_info, chart_type):
    lat_field = config.get("lat") or _find_field(columns, "lat", "latitude")
    lon_field = config.get("lon") or _find_field(columns, "lon", "lng", "longitude")
    value_field = config.get("y") if config.get("y") in columns else next(
        (f["name"] for f in infer_fields(columns, rows) if f["type"] == "number"), None
    )
    label_field = config.get("x") if config.get("x") in columns else next(
        (f["name"] for f in infer_fields(columns, rows) if f["type"] != "number"), None
    )
    if chart_type == "map_choropleth" and label_field and value_field:
        lat_field = None
        lon_field = None
    limit = int(config.get("limit") or 500)
    points = []
    if lat_field and lon_field:
        for index, row in enumerate(rows[:limit]):
            lat = _to_number(row.get(lat_field))
            lon = _to_number(row.get(lon_field))
            if lat is None or lon is None:
                continue
            points.append(
                {
                    "lat": lat,
                    "lon": lon,
                    "value": Number(row.get(value_field)) if value_field else 1,
                    "label": str(row.get(label_field) if label_field else f"Fila {index + 1}"),
                }
            )
    regions = []
    if not points and label_field and value_field:
        agg = _aggregation(config)
        buckets: dict[str, list[Any]] = {}
        for row in rows[:limit]:
            label = str(row.get(label_field) if row.get(label_field) is not None else "(vacio)")
            buckets.setdefault(label, []).append(row.get(value_field))
        regions = [
            {"name": label, "value": round(_aggregate(values, agg), 6)}
            for label, values in sorted(buckets.items())
        ]
    return {
        "type": chart_type,
        "points": points,
        "regions": regions,
        "lat_field": lat_field,
        "lon_field": lon_field,
        "value_field": value_field,
        "label_field": label_field,
        "format": format_info,
        "row_count": len(points) or len(regions),
        "reason": None
        if points or regions
        else "Indica columnas de latitud/longitud o una region y un valor",
    }


def _correlation(rows, columns, config, format_info, chart_type):
    numeric = [f["name"] for f in infer_fields(columns, rows) if f["type"] == "number"][:8]
    if len(numeric) < 2:
        return {"type": chart_type, "matrix": [], "columns": [], "reason": "Se necesitan dos columnas numericas"}
    values = {name: [_to_number(row.get(name)) for row in rows] for name in numeric}
    matrix = []
    for a in numeric:
        line_values = []
        for b in numeric:
            pairs = [
                (x, y)
                for x, y in zip(values[a], values[b])
                if x is not None and y is not None
            ]
            line_values.append(round(_pearson(pairs), 4))
        matrix.append(line_values)
    return {"type": chart_type, "columns": numeric, "matrix": matrix, "row_count": len(rows), "format": format_info}


def _pearson(pairs: list[tuple[float, float]]) -> float:
    if len(pairs) < 2:
        return 0.0
    xs = [p[0] for p in pairs]
    ys = [p[1] for p in pairs]
    mx = sum(xs) / len(xs)
    my = sum(ys) / len(ys)
    cov = sum((x - mx) * (y - my) for x, y in pairs)
    vx = sum((x - mx) ** 2 for x in xs)
    vy = sum((y - my) ** 2 for y in ys)
    if vx <= 0 or vy <= 0:
        return 0.0
    return cov / math.sqrt(vx * vy)


def _influencers(rows, columns, config, format_info, chart_type):
    numeric = [f["name"] for f in infer_fields(columns, rows) if f["type"] == "number"]
    if len(numeric) < 2:
        return {
            "type": chart_type,
            "influencers": [],
            "reason": "Se necesitan dos columnas numericas",
        }
    target = config.get("y") if config.get("y") in numeric else numeric[-1]
    values_target = [_to_number(row.get(target)) for row in rows]
    result = []
    for name in numeric:
        if name == target:
            continue
        pairs = [
            (x, y)
            for x, y in zip([_to_number(row.get(name)) for row in rows], values_target)
            if x is not None and y is not None
        ]
        score = _pearson(pairs)
        result.append(
            {
                "field": name,
                "score": round(score, 4),
                "impact": round(abs(score) * 100, 2),
                "direction": "positiva" if score >= 0 else "negativa",
            }
        )
    result.sort(key=lambda item: abs(item["score"]), reverse=True)
    return {
        "type": chart_type,
        "target": target,
        "influencers": result[:8],
        "row_count": len(rows),
        "reason": None if result else "No hay suficientes columnas para comparar",
    }


def _qna(rows, columns, config, format_info, chart_type):
    question = str(config.get("question") or config.get("label") or "Pregunta sin definir").strip()
    lower = question.lower()
    config = dict(config)
    if not config.get("agg"):
        if any(word in lower for word in ("promedio", "media", "avg")):
            config["agg"] = "avg"
        elif any(word in lower for word in ("conteo", "cuantos", "cuantas", "count")):
            config["agg"] = "count"
        elif any(word in lower for word in ("maximo", "max", "mayor")):
            config["agg"] = "max"
        elif any(word in lower for word in ("minimo", "min", "menor")):
            config["agg"] = "min"
        else:
            config["agg"] = "sum"
    fields = infer_fields(columns, rows)
    if not config.get("x"):
        for field in fields:
            if field["type"] != "number" and field["name"].lower() in lower:
                config["x"] = field["name"]
                break
    if not config.get("y"):
        for field in fields:
            if field["type"] == "number" and field["name"].lower() in lower:
                config["y"] = field["name"]
                break
    if not config.get("y") and config.get("agg") != "count":
        config["y"] = next((f["name"] for f in fields if f["type"] == "number"), None)
    return _grouped(rows, columns, config, format_info, chart_type, question=question)


def _slicer(rows, columns, config, format_info, chart_type):
    field = config.get("x") or config.get("field")
    if field not in columns:
        field = next((f["name"] for f in infer_fields(columns, rows) if f["type"] != "number"), None)
    if not field:
        return {"type": chart_type, "field": None, "values": [], "reason": "No hay campos de texto para segmentar"}
    values = []
    seen = set()
    for row in rows:
        value = row.get(field)
        if value is None or value == "":
            continue
        text = str(value)
        if text not in seen:
            seen.add(text)
            values.append(text)
        if len(values) >= 100:
            break
    return {"type": chart_type, "field": field, "values": sorted(values), "format": format_info}


def _filter_panel(rows, columns, config, format_info, chart_type):
    fields = []
    for field in infer_fields(columns, rows):
        if field["type"] == "number":
            continue
        values = []
        seen = set()
        for row in rows:
            value = row.get(field["name"])
            if value is None or value == "":
                continue
            text = str(value)
            if text not in seen:
                seen.add(text)
                values.append(text)
            if len(values) >= 25:
                break
        if values:
            fields.append({"field": field["name"], "values": sorted(values)})
        if len(fields) >= 5:
            break
    return {
        "type": chart_type,
        "filters": fields,
        "format": format_info,
        "reason": None if fields else "No hay campos de texto para filtrar",
    }


def _interaction(chart_type, config, format_info):
    return {
        "type": chart_type,
        "label": config.get("label") or config.get("nav_label") or "",
        "url": config.get("url") or config.get("nav_url") or "",
        "tooltip": config.get("tooltip") or config.get("text") or "",
        "widget_id": config.get("_widget_id"),
        "format": format_info,
    }


def build_chart_data(widget: dict, result: dict) -> dict:
    chart_type = widget.get("chart_type") or "column_grouped"
    if chart_type not in CHART_TYPES:
        chart_type = "column_grouped"
    config = _widget_config(widget)
    rows: list[dict] = result.get("rows") or []
    columns: list[str] = result.get("columns") or []
    if not columns and rows:
        columns = list(rows[0].keys())
    config = dict(config)
    config["_truncated"] = bool(result.get("truncated"))
    config["_widget_id"] = widget.get("id")
    format_info = _format_info(config)

    if chart_type == "matrix":
        return _matrix(rows, columns, config, format_info)
    if chart_type in {"decomposition", "decomp_tree"}:
        return _hierarchy(rows, columns, config, format_info, chart_type)
    if chart_type in TABLE_TYPES:
        return _raw_table(chart_type, columns, rows, config, format_info)
    if chart_type in KPI_TYPES:
        x, y = _guess_columns(columns, rows, config)
        values = [row.get(y) for row in rows] if y else [1] * len(rows)
        agg = _aggregation(config)
        return {
            "type": chart_type,
            "value": _aggregate(values, agg),
            "label": config.get("label") or y or "Registros",
            "rows": len(rows),
            "format": format_info,
            "x": x,
            "y": y,
            "agg": agg,
        }
    if chart_type == "multi_row":
        return _multi_row(rows, columns, config, format_info, chart_type)
    if chart_type == "gauge":
        x, y = _guess_columns(columns, rows, config)
        values = [row.get(y) for row in rows] if y else [1] * len(rows)
        agg = _aggregation(config)
        value = _aggregate(values, agg)
        numbers = [n for n in (_to_number(v) for v in values) if n is not None]
        suggested = max(numbers) if numbers else 100.0
        maximum = _to_number(config.get("max"))
        return {
            "type": chart_type,
            "value": value,
            "max": maximum if maximum and maximum > 0 else max(abs(value), suggested, 1),
            "label": config.get("label") or y or "Valor",
            "format": format_info,
            "agg": agg,
        }
    if chart_type in POINT_TYPES:
        return _scatter(rows, columns, config, format_info, chart_type)
    if chart_type in MAP_TYPES:
        return _map(rows, columns, config, format_info, chart_type)
    if chart_type == "correlation":
        return _correlation(rows, columns, config, format_info, chart_type)
    if chart_type == "key_influencers":
        return _influencers(rows, columns, config, format_info, chart_type)
    if chart_type == "qna":
        return _qna(rows, columns, config, format_info, chart_type)
    if chart_type == "slicer":
        return _slicer(rows, columns, config, format_info, chart_type)
    if chart_type == "filter_panel":
        return _filter_panel(rows, columns, config, format_info, chart_type)
    if chart_type in INTERACTION_TYPES:
        return _interaction(chart_type, config, format_info)
    return _grouped(rows, columns, config, format_info, chart_type)
