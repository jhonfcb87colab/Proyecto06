"""Datos de demostracion: SQLite de ventas + dashboard inicial."""
from __future__ import annotations

import random
import sqlite3
from datetime import date

from . import store
from .config import SAMPLE_DB, ensure_dirs

DATASET_SQL = (
    "SELECT month, region, product, channel, units, revenue, cost, margin\n"
    "FROM sales\n"
    "ORDER BY month, region, product, channel"
)

FIELDS = [
    {"name": "month", "type": "date"},
    {"name": "region", "type": "text"},
    {"name": "product", "type": "text"},
    {"name": "channel", "type": "text"},
    {"name": "units", "type": "number"},
    {"name": "revenue", "type": "number"},
    {"name": "cost", "type": "number"},
    {"name": "margin", "type": "number"},
]

REGIONS = ["Norte", "Sur", "Centro", "Este", "Oeste"]
PRODUCTS = ["Atlas", "Borealis", "Cobalt", "Delta"]
CHANNELS = ["Online", "Retail", "Partner"]
REGION_FACTOR = {"Norte": 1.15, "Sur": 0.9, "Centro": 1.25, "Este": 1.0, "Oeste": 0.95}
CHANNEL_FACTOR = {"Online": 1.1, "Retail": 1.0, "Partner": 0.85}
BASE_PRICE = {"Atlas": 120.0, "Borealis": 85.0, "Cobalt": 210.0, "Delta": 45.0}


def _months() -> list[str]:
    out = []
    year, month = 2025, 10
    for _ in range(12):
        out.append(f"{year:04d}-{month:02d}")
        month += 1
        if month > 12:
            month = 1
            year += 1
    return out


def create_sample_db(force: bool = False) -> None:
    ensure_dirs()
    if SAMPLE_DB.exists() and not force:
        return
    if SAMPLE_DB.exists():
        SAMPLE_DB.unlink()
    rng = random.Random(42)
    con = sqlite3.connect(SAMPLE_DB)
    try:
        con.executescript(
            """
            CREATE TABLE sales (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                month TEXT NOT NULL,
                region TEXT NOT NULL,
                product TEXT NOT NULL,
                channel TEXT NOT NULL,
                units INTEGER NOT NULL,
                revenue REAL NOT NULL,
                cost REAL NOT NULL,
                margin REAL NOT NULL
            );
            CREATE INDEX idx_sales_month ON sales(month);
            CREATE INDEX idx_sales_region ON sales(region);
            """
        )
        rows = []
        season = {"10": 1.05, "11": 1.2, "12": 1.35, "01": 0.9, "02": 0.95, "03": 1.1}
        for month in _months():
            for region in REGIONS:
                for product in PRODUCTS:
                    for channel in CHANNELS:
                        base = rng.randint(18, 140)
                        factor = (
                            REGION_FACTOR[region]
                            * CHANNEL_FACTOR[channel]
                            * season.get(month[-2:], 1.0)
                            * rng.uniform(0.82, 1.18)
                        )
                        units = max(1, int(round(base * factor)))
                        revenue = round(units * BASE_PRICE[product] * rng.uniform(0.94, 1.06), 2)
                        cost = round(revenue * (0.55 + rng.uniform(-0.04, 0.07)), 2)
                        rows.append(
                            (month, region, product, channel, units, revenue, cost, round(revenue - cost, 2))
                        )
        con.executemany(
            "INSERT INTO sales(month, region, product, channel, units, revenue, cost, margin)"
            " VALUES(?,?,?,?,?,?,?,?)",
            rows,
        )
        con.commit()
    finally:
        con.close()


def _widget(
    dashboard_id: int,
    dataset_id: int,
    title: str,
    chart_type: str,
    config: dict,
    w: int,
    h: int,
    x: int,
    y: int,
):
    store.create_widget(dashboard_id, dataset_id, title, chart_type, config, w, h, x, y)


def seed_metadata(force_sample: bool = False) -> dict:
    store.init_db()
    create_sample_db(force=force_sample)
    if store.list_dashboards():
        return {"seeded": False, "reason": "ya existen dashboards"}

    existing = {c["name"]: c for c in store.list_connections()}
    connection = existing.get("Demo SQLite")
    if not connection:
        connection = store.create_connection("Demo SQLite", "sqlite", {"path": str(SAMPLE_DB)})
    dataset = store.create_dataset(
        connection["id"],
        "Ventas (demo)",
        DATASET_SQL,
        FIELDS,
    )
    dashboard = store.create_dashboard(
        "Ventas 2026",
        "Tablero de ejemplo generado por el seed. Cambia a modo diseno para editarlo.",
    )
    did, sid = dashboard["id"], dataset["id"]
    _widget(
        did, sid, "Ingresos totales", "kpi",
        {"y": "revenue", "agg": "sum", "format": "currency", "currency": "USD", "label": "Ingresos totales"},
        3, 2, 0, 0,
    )
    _widget(
        did, sid, "Unidades vendidas", "kpi",
        {"y": "units", "agg": "sum", "format": "integer", "label": "Unidades vendidas"},
        3, 2, 3, 0,
    )
    _widget(
        did, sid, "Mix por canal", "pie",
        {"x": "channel", "y": "revenue", "agg": "sum", "format": "currency"},
        3, 2, 6, 0,
    )
    _widget(
        did, sid, "Top productos", "bar",
        {"x": "product", "y": "units", "agg": "sum", "sort": "value_desc", "format": "integer"},
        3, 2, 9, 0,
    )
    _widget(
        did, sid, "Ingresos por region", "bar",
        {"x": "region", "y": "revenue", "agg": "sum", "sort": "value_desc", "format": "currency", "limit": 8},
        6, 3, 0, 2,
    )
    _widget(
        did, sid, "Tendencia mensual", "line",
        {"x": "month", "y": "revenue", "agg": "sum", "format": "currency"},
        6, 3, 6, 2,
    )
    _widget(
        did, sid, "Detalle de ventas", "table",
        {"limit": 100, "format": "number"},
        12, 3, 0, 5,
    )
    return {"seeded": True, "dashboard_id": did, "dataset_id": sid, "connection_id": connection["id"]}


def reset() -> dict:
    with store.session() as con:
        con.execute("DELETE FROM widgets")
        con.execute("DELETE FROM dashboards")
        con.execute("DELETE FROM datasets")
        con.execute("DELETE FROM connections")
    result = seed_metadata(force_sample=True)
    try:
        from . import auth

        auth.grant_demo_access()
    except Exception:  # noqa: BLE001 - el reset no debe fallar si aun no hay auth
        pass
    return result


def today() -> str:
    return date.today().isoformat()
