"""Almacen de metadatos (SQLite). Separado del motor de datos."""
from __future__ import annotations

import json
import re
import sqlite3
import unicodedata
from contextlib import contextmanager
from datetime import datetime, timezone
from typing import Any, Iterator

from .config import METADATA_DB, ensure_dirs

SCHEMA = """
CREATE TABLE IF NOT EXISTS connections (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL UNIQUE,
    kind TEXT NOT NULL,
    config TEXT NOT NULL DEFAULT '{}',
    created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS datasets (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    connection_id INTEGER NOT NULL REFERENCES connections(id) ON DELETE CASCADE,
    name TEXT NOT NULL,
    sql TEXT NOT NULL,
    fields TEXT NOT NULL DEFAULT '[]',
    created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS dashboards (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL,
    slug TEXT NOT NULL UNIQUE,
    description TEXT NOT NULL DEFAULT '',
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS widgets (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    dashboard_id INTEGER NOT NULL REFERENCES dashboards(id) ON DELETE CASCADE,
    dataset_id INTEGER REFERENCES datasets(id) ON DELETE SET NULL,
    title TEXT NOT NULL,
    chart_type TEXT NOT NULL DEFAULT 'bar',
    config TEXT NOT NULL DEFAULT '{}',
    x INTEGER,
    y INTEGER,
    w INTEGER NOT NULL DEFAULT 3,
    h INTEGER NOT NULL DEFAULT 2,
    created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS model_items (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    connection_id INTEGER REFERENCES connections(id) ON DELETE CASCADE,
    dataset_id INTEGER REFERENCES datasets(id) ON DELETE CASCADE,
    kind TEXT NOT NULL,
    name TEXT NOT NULL,
    expression TEXT NOT NULL DEFAULT '',
    config TEXT NOT NULL DEFAULT '{}',
    created_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_model_dataset ON model_items(dataset_id);
CREATE INDEX IF NOT EXISTS idx_model_kind ON model_items(kind);
CREATE TABLE IF NOT EXISTS table_aliases (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    connection_id INTEGER NOT NULL REFERENCES connections(id) ON DELETE CASCADE,
    table_name TEXT NOT NULL,
    alias TEXT NOT NULL,
    created_at TEXT NOT NULL,
    UNIQUE(connection_id, table_name)
);
CREATE TABLE IF NOT EXISTS api_scripts (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL UNIQUE,
    description TEXT NOT NULL DEFAULT '',
    code TEXT NOT NULL,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);
"""

JSON_FIELDS = {
    "connections": ("config",),
    "datasets": ("fields",),
    "dashboards": (),
    "widgets": ("config",),
    "model_items": ("config",),
}


def now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def slugify(value: str) -> str:
    value = unicodedata.normalize("NFKD", value).encode("ascii", "ignore").decode()
    value = re.sub(r"[^a-zA-Z0-9]+", "-", value).strip("-").lower()
    return value or "dashboard"


@contextmanager
def session() -> Iterator[sqlite3.Connection]:
    ensure_dirs()
    con = sqlite3.connect(METADATA_DB, timeout=10)
    con.row_factory = sqlite3.Row
    con.execute("PRAGMA foreign_keys=ON")
    try:
        yield con
        con.commit()
    except Exception:
        con.rollback()
        raise
    finally:
        con.close()


def _table_columns(con: sqlite3.Connection, table: str) -> set[str]:
    return {row["name"] for row in con.execute(f"PRAGMA table_info({table})")}


def _pack_widgets(con: sqlite3.Connection, multiply_width: bool = False) -> None:
    """Asigna x/y a widgets sin posicion usando una cuadricula de 12 columnas."""
    dashboard_ids = [
        row["dashboard_id"]
        for row in con.execute(
            "SELECT DISTINCT dashboard_id FROM widgets WHERE x IS NULL OR y IS NULL"
        )
    ]
    for dashboard_id in dashboard_ids:
        rows = con.execute(
            "SELECT id, w, h FROM widgets WHERE dashboard_id=? ORDER BY id",
            (dashboard_id,),
        ).fetchall()
        x = 0
        y = 0
        row_height = 0
        for row in rows:
            width = int(row["w"] or 1)
            height = int(row["h"] or 1)
            if multiply_width:
                width = min(12, max(1, width * 3))
            width = max(1, min(width, 12))
            height = max(1, min(height, 6))
            if x + width > 12:
                y += row_height
                x = 0
                row_height = 0
            if row["id"] and con.execute(
                "SELECT x, y FROM widgets WHERE id=?", (row["id"],)
            ).fetchone()[0] is None:
                con.execute(
                    "UPDATE widgets SET x=?, y=?, w=?, h=? WHERE id=?",
                    (x, y, width, height, row["id"]),
                )
            x += width
            row_height = max(row_height, height)
            if x >= 12:
                y += row_height
                x = 0
                row_height = 0


def init_db() -> None:
    with session() as con:
        con.executescript(SCHEMA)
        widget_columns = _table_columns(con, "widgets")
        migrated = False
        if "x" not in widget_columns:
            con.execute("ALTER TABLE widgets ADD COLUMN x INTEGER")
            migrated = True
        if "y" not in widget_columns:
            con.execute("ALTER TABLE widgets ADD COLUMN y INTEGER")
            migrated = True
        _pack_widgets(con, multiply_width=migrated)


def _decode(table: str, row: sqlite3.Row | None) -> dict | None:
    if row is None:
        return None
    data = dict(row)
    for field in JSON_FIELDS.get(table, ()):
        try:
            data[field] = json.loads(data.get(field) or "{}")
        except (TypeError, json.JSONDecodeError):
            data[field] = {} if field == "config" else []
    return data


def _all(table: str, where: str = "", params: tuple = (), order: str = "id") -> list[dict]:
    query = f"SELECT * FROM {table}"
    if where:
        query += f" WHERE {where}"
    query += f" ORDER BY {order}"
    with session() as con:
        return [_decode(table, row) for row in con.execute(query, params)]


def _get(table: str, pk: int) -> dict | None:
    with session() as con:
        return _decode(table, con.execute(f"SELECT * FROM {table} WHERE id=?", (pk,)).fetchone())


def _fetch(con: sqlite3.Connection, table: str, pk: int) -> dict:
    return _decode(table, con.execute(f"SELECT * FROM {table} WHERE id=?", (pk,)).fetchone())  # type: ignore[return-value]


# ---------------------------------------------------------------- connections
def list_connections() -> list[dict]:
    return _all("connections", order="name")


def get_connection(pk: int) -> dict | None:
    return _get("connections", pk)


def create_connection(name: str, kind: str, config: dict) -> dict:
    with session() as con:
        cur = con.execute(
            "INSERT INTO connections(name, kind, config, created_at) VALUES(?,?,?,?)",
            (name, kind, json.dumps(config), now()),
        )
        return _fetch(con, "connections", cur.lastrowid)


def update_connection(pk: int, name: str, kind: str, config: dict) -> dict | None:
    with session() as con:
        con.execute(
            "UPDATE connections SET name=?, kind=?, config=? WHERE id=?",
            (name, kind, json.dumps(config), pk),
        )
    return get_connection(pk)


def delete_connection(pk: int) -> None:
    with session() as con:
        con.execute("DELETE FROM connections WHERE id=?", (pk,))


# ------------------------------------------------------------------- datasets
def list_datasets() -> list[dict]:
    return _all("datasets", order="name")


def get_dataset(pk: int) -> dict | None:
    return _get("datasets", pk)


def create_dataset(connection_id: int, name: str, sql: str, fields: list[dict]) -> dict:
    with session() as con:
        cur = con.execute(
            "INSERT INTO datasets(connection_id, name, sql, fields, created_at) VALUES(?,?,?,?,?)",
            (connection_id, name, sql, json.dumps(fields), now()),
        )
        return _fetch(con, "datasets", cur.lastrowid)


def update_dataset(pk: int, connection_id: int, name: str, sql: str, fields: list[dict]) -> dict | None:
    with session() as con:
        con.execute(
            "UPDATE datasets SET connection_id=?, name=?, sql=?, fields=? WHERE id=?",
            (connection_id, name, sql, json.dumps(fields), pk),
        )
    return get_dataset(pk)


def delete_dataset(pk: int) -> None:
    with session() as con:
        con.execute("DELETE FROM datasets WHERE id=?", (pk,))


# ----------------------------------------------------------------- dashboards
def list_dashboards() -> list[dict]:
    return _all("dashboards", order="name")


def get_dashboard(pk: int) -> dict | None:
    return _get("dashboards", pk)


def create_dashboard(name: str, description: str = "") -> dict:
    base = slugify(name)
    slug = base
    with session() as con:
        suffix = 2
        while con.execute("SELECT 1 FROM dashboards WHERE slug=?", (slug,)).fetchone():
            slug = f"{base}-{suffix}"
            suffix += 1
        stamp = now()
        cur = con.execute(
            "INSERT INTO dashboards(name, slug, description, created_at, updated_at)"
            " VALUES(?,?,?,?,?)",
            (name, slug, description, stamp, stamp),
        )
        return _fetch(con, "dashboards", cur.lastrowid)


def update_dashboard(pk: int, name: str, description: str) -> dict | None:
    with session() as con:
        con.execute(
            "UPDATE dashboards SET name=?, description=?, updated_at=? WHERE id=?",
            (name, description, now(), pk),
        )
    return get_dashboard(pk)


def delete_dashboard(pk: int) -> None:
    with session() as con:
        con.execute("DELETE FROM dashboards WHERE id=?", (pk,))


# -------------------------------------------------------------------- widgets
def list_widgets(dashboard_id: int) -> list[dict]:
    return _all("widgets", "dashboard_id=?", (dashboard_id,), order="id")


def get_widget(pk: int) -> dict | None:
    return _get("widgets", pk)


def create_widget(
    dashboard_id: int,
    dataset_id: int | None,
    title: str,
    chart_type: str,
    config: dict,
    w: int = 3,
    h: int = 2,
    x: int | None = None,
    y: int | None = None,
) -> dict:
    with session() as con:
        cur = con.execute(
            "INSERT INTO widgets(dashboard_id, dataset_id, title, chart_type, config, x, y, w, h, created_at)"
            " VALUES(?,?,?,?,?,?,?,?,?,?)",
            (dashboard_id, dataset_id, title, chart_type, json.dumps(config), x, y, w, h, now()),
        )
        con.execute("UPDATE dashboards SET updated_at=? WHERE id=?", (now(), dashboard_id))
        return _fetch(con, "widgets", cur.lastrowid)


def update_widget(
    pk: int,
    dataset_id: int | None,
    title: str,
    chart_type: str,
    config: dict,
    w: int,
    h: int,
    x: int | None = None,
    y: int | None = None,
) -> dict | None:
    with session() as con:
        row = con.execute("SELECT dashboard_id FROM widgets WHERE id=?", (pk,)).fetchone()
        con.execute(
            "UPDATE widgets SET dataset_id=?, title=?, chart_type=?, config=?, w=?, h=?, x=?, y=? WHERE id=?",
            (dataset_id, title, chart_type, json.dumps(config), w, h, x, y, pk),
        )
        if row:
            con.execute("UPDATE dashboards SET updated_at=? WHERE id=?", (now(), row["dashboard_id"]))
    return get_widget(pk)


def update_widget_layout(pk: int, x: int, y: int, w: int, h: int) -> dict | None:
    with session() as con:
        row = con.execute("SELECT dashboard_id FROM widgets WHERE id=?", (pk,)).fetchone()
        con.execute(
            "UPDATE widgets SET x=?, y=?, w=?, h=? WHERE id=?",
            (x, y, w, h, pk),
        )
        if row:
            con.execute("UPDATE dashboards SET updated_at=? WHERE id=?", (now(), row["dashboard_id"]))
    return get_widget(pk)


def delete_widget(pk: int) -> None:
    with session() as con:
        con.execute("DELETE FROM widgets WHERE id=?", (pk,))


def touch_dashboard(pk: int) -> None:
    with session() as con:
        con.execute("UPDATE dashboards SET updated_at=? WHERE id=?", (now(), pk))


# ---------------------------------------------------------------- model items
def list_model_items(kind: str | None = None, dataset_id: int | None = None) -> list[dict]:
    clauses = []
    params: list[Any] = []
    if kind:
        clauses.append("kind=?")
        params.append(kind)
    if dataset_id:
        clauses.append("dataset_id=?")
        params.append(dataset_id)
    where = " AND ".join(clauses)
    return _all("model_items", where, tuple(params), order="kind, name")


def get_model_item(pk: int) -> dict | None:
    return _get("model_items", pk)


def create_model_item(
    kind: str,
    name: str,
    expression: str = "",
    dataset_id: int | None = None,
    connection_id: int | None = None,
    config: dict | None = None,
) -> dict:
    with session() as con:
        cur = con.execute(
            "INSERT INTO model_items(connection_id, dataset_id, kind, name, expression, config, created_at)"
            " VALUES(?,?,?,?,?,?,?)",
            (
                connection_id,
                dataset_id,
                kind,
                name,
                expression,
                json.dumps(config or {}),
                now(),
            ),
        )
        return _fetch(con, "model_items", cur.lastrowid)


def update_model_item(
    pk: int,
    kind: str,
    name: str,
    expression: str,
    dataset_id: int | None,
    connection_id: int | None,
    config: dict | None,
) -> dict | None:
    with session() as con:
        con.execute(
            "UPDATE model_items SET connection_id=?, dataset_id=?, kind=?, name=?, expression=?, config=?"
            " WHERE id=?",
            (connection_id, dataset_id, kind, name, expression, json.dumps(config or {}), pk),
        )
    return get_model_item(pk)


def delete_model_item(pk: int) -> None:
    with session() as con:
        con.execute("DELETE FROM model_items WHERE id=?", (pk,))


# --------------------------------------------------------------- table aliases
def list_table_aliases(connection_id: int | None = None) -> list[dict]:
    if connection_id is None:
        return _all("table_aliases", order="connection_id, table_name")
    return _all("table_aliases", "connection_id=?", (connection_id,), order="table_name")


def set_table_alias(connection_id: int, table_name: str, alias: str | None) -> None:
    alias = (alias or "").strip()
    with session() as con:
        if not alias:
            con.execute(
                "DELETE FROM table_aliases WHERE connection_id=? AND table_name=?",
                (connection_id, table_name),
            )
            return
        con.execute(
            "INSERT INTO table_aliases(connection_id, table_name, alias, created_at)"
            " VALUES(?,?,?,?) ON CONFLICT(connection_id, table_name)"
            " DO UPDATE SET alias=excluded.alias, created_at=excluded.created_at",
            (connection_id, table_name, alias[:120], now()),
        )


# ------------------------------------------------------------------ api scripts
def list_api_scripts() -> list[dict]:
    return _all("api_scripts", order="name")


def get_api_script(pk: int) -> dict | None:
    return _get("api_scripts", pk)


def create_api_script(name: str, description: str, code: str) -> dict:
    stamp = now()
    with session() as con:
        cur = con.execute(
            "INSERT INTO api_scripts(name, description, code, created_at, updated_at)"
            " VALUES(?,?,?,?,?)",
            (name, description, code, stamp, stamp),
        )
        return _fetch(con, "api_scripts", cur.lastrowid)


def update_api_script(pk: int, name: str, description: str, code: str) -> dict | None:
    with session() as con:
        con.execute(
            "UPDATE api_scripts SET name=?, description=?, code=?, updated_at=? WHERE id=?",
            (name, description, code, now(), pk),
        )
    return get_api_script(pk)


def delete_api_script(pk: int) -> None:
    with session() as con:
        con.execute("DELETE FROM api_scripts WHERE id=?", (pk,))
