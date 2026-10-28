"""Importacion de archivos (CSV/Parquet) y APIs a una base SQLite local.

Los scripts de API se ejecutan en un subproceso aislado, con timeout y un
directorio temporal. Siguen siendo codigo Python arbitrario: solo deben poder
crearlos administradores de confianza.
"""
from __future__ import annotations

import io
import json
import os
import re
import sqlite3
import subprocess
import sys
import tempfile
import time
from pathlib import Path
from typing import Any

from .config import API_SCRIPT_TIMEOUT, IMPORT_MAX_ROWS, IMPORTED_DB, ensure_dirs
from .data_sources import AppError, _jsonable

MAX_SCRIPT_LENGTH = 200_000
SUPPORTED_EXTENSIONS = {".csv", ".tsv", ".txt", ".parquet"}

_SCRIPT_PREAMBLE = """\
import json
import os
import sys
try:
    import requests
except Exception:
    requests = None
try:
    import pandas as pd
except Exception:
    pd = None
try:
    import polars as pl
except Exception:
    pl = None
"""

_SCRIPT_EPILOGUE = """\

_out = os.environ.get("BIWEB_API_OUT")
_value = globals().get("result")
if _value is None:
    _value = globals().get("df")
if _value is None:
    _value = globals().get("rows")
if hasattr(_value, "to_dicts"):
    _value = _value.to_dicts()
elif hasattr(_value, "to_dict"):
    try:
        _value = _value.to_dict(orient="records")
    except TypeError:
        _value = _value.to_dict()
if _value is None:
    _value = []
with open(_out, "w", encoding="utf-8") as _fh:
    json.dump(_value, _fh, ensure_ascii=False, default=str)
"""


def sanitize_table_name(value: str | None) -> str:
    base = Path(str(value or "imported")).stem
    base = re.sub(r"[^A-Za-z0-9_]+", "_", base).strip("_")
    if not base:
        base = "imported"
    if base[0].isdigit():
        base = "t_" + base
    return base[:60]


def _quote(name: str) -> str:
    return '"' + str(name).replace('"', '""') + '"'


def _dedupe_columns(names: list[str]) -> list[str]:
    seen: dict[str, int] = {}
    out: list[str] = []
    for raw in names:
        base = str(raw or "col")
        if base in seen:
            seen[base] += 1
            out.append(f"{base}_{seen[base]}")
        else:
            seen[base] = 0
            out.append(base)
    return out


def _normalize_rows(value: Any) -> tuple[list[dict], list[str]]:
    """Convierte DataFrame/list/dict de una API o archivo en filas JSONables."""
    if value is None:
        return [], []
    if hasattr(value, "to_dicts"):
        value = value.to_dicts()
    elif hasattr(value, "to_dict"):
        try:
            value = value.to_dict(orient="records")
        except TypeError:
            value = value.to_dict()
    if isinstance(value, dict):
        for key in ("rows", "data", "items", "results", "records"):
            if isinstance(value.get(key), list):
                value = value[key]
                break
        else:
            if isinstance(value.get("columns"), list) and isinstance(value.get("rows"), list):
                columns = [str(c) for c in value["columns"]]
                value = [dict(zip(columns, row)) for row in value["rows"]]
            else:
                value = [value]
    if not isinstance(value, list):
        raise AppError("El resultado de la API debe ser una lista de objetos o un DataFrame")
    rows: list[dict] = []
    columns: list[str] = []
    for item in value:
        if isinstance(item, dict):
            row = {str(k): _jsonable(v) for k, v in item.items()}
        else:
            row = {"value": _jsonable(item)}
        for key in row:
            if key not in columns:
                columns.append(key)
        rows.append(row)
    return rows, columns


def _connect_imported() -> sqlite3.Connection:
    ensure_dirs()
    con = sqlite3.connect(IMPORTED_DB, timeout=10)
    con.row_factory = sqlite3.Row
    return con


def load_rows(table_name: str, rows: list[dict], columns: list[str] | None = None) -> dict:
    """Reemplaza la tabla indicada en var/imported.db con las filas recibidas."""
    if len(rows) > IMPORT_MAX_ROWS:
        raise AppError(
            f"La importacion supera el maximo de {IMPORT_MAX_ROWS} filas",
            status=413,
            code="too_many_rows",
        )
    table = sanitize_table_name(table_name)
    order = _dedupe_columns(list(columns or []))
    for row in rows:
        for key in row:
            if key not in order:
                order.append(key)
    if not order:
        order = ["value"]
    ensure_dirs()
    try:
        import pandas as pd  # type: ignore
    except ImportError:
        pd = None
    if pd is not None:
        frame = pd.DataFrame(rows)
        if list(frame.columns) != order:
            frame = frame.reindex(columns=order)
        con = _connect_imported()
        try:
            frame.to_sql(table, con=con, if_exists="replace", index=False, chunksize=500)
        finally:
            con.close()
        return {"table": table, "rows": int(len(frame)), "columns": order}
    con = _connect_imported()
    try:
        con.execute("DROP TABLE IF EXISTS " + _quote(table))
        definitions = []
        for column in order:
            values = [row.get(column) for row in rows]
            numeric = all(
                value is None or isinstance(value, (int, float)) and not isinstance(value, bool)
                for value in values
            )
            definitions.append(_quote(column) + (" REAL" if numeric else " TEXT"))
        con.execute("CREATE TABLE " + _quote(table) + " (" + ", ".join(definitions) + ")")
        placeholders = ",".join("?" for _ in order)
        con.executemany(
            "INSERT INTO " + _quote(table) + " (" + ",".join(_quote(c) for c in order) + ")"
            " VALUES (" + placeholders + ")",
            [tuple(row.get(column) for column in order) for row in rows],
        )
        con.commit()
    finally:
        con.close()
    return {"table": table, "rows": len(rows), "columns": order}


def _read_delimited(data: bytes, separator: str) -> tuple[list[dict], list[str]]:
    try:
        import pandas as pd  # type: ignore
    except ImportError:
        pd = None
    if pd is not None:
        try:
            frame = pd.read_csv(io.BytesIO(data), sep=separator, low_memory=False)
        except UnicodeDecodeError:
            frame = pd.read_csv(io.BytesIO(data), sep=separator, encoding="latin-1", low_memory=False)
        return _normalize_rows(frame)
    import csv

    text = data.decode("utf-8-sig", errors="replace")
    reader = csv.DictReader(io.StringIO(text), delimiter=separator)
    rows, columns = _normalize_rows(list(reader))
    return rows, columns or list(reader.fieldnames or [])


def read_upload(filename: str, data: bytes) -> dict:
    """Lee un CSV/TSV/Parquet subido y devuelve filas normalizadas."""
    suffix = Path(filename or "").suffix.lower()
    if suffix not in SUPPORTED_EXTENSIONS:
        raise AppError(
            "Formato no soportado. Usa CSV, TSV o Parquet",
            status=415,
            code="unsupported_file",
        )
    started = time.monotonic()
    if suffix == ".parquet":
        try:
            import pandas as pd  # type: ignore
        except ImportError as exc:
            raise AppError(
                "Para importar Parquet instala pandas y pyarrow: pip install pandas pyarrow",
                status=501,
                code="driver_missing",
            ) from exc
        try:
            frame = pd.read_parquet(io.BytesIO(data))
        except Exception as exc:  # noqa: BLE001
            raise AppError(f"No se pudo leer el Parquet: {exc}", status=422, code="file_error") from exc
        rows, columns = _normalize_rows(frame)
    else:
        rows, columns = _read_delimited(data, "\t" if suffix == ".tsv" else ",")
    if len(rows) > IMPORT_MAX_ROWS:
        raise AppError(
            f"El archivo supera el maximo de {IMPORT_MAX_ROWS} filas",
            status=413,
            code="too_many_rows",
        )
    if not rows:
        raise AppError("El archivo no contiene filas", status=422, code="empty_file")
    return {
        "rows": rows,
        "columns": columns,
        "elapsed_ms": round((time.monotonic() - started) * 1000),
    }


def run_api_script(code: str, timeout: int | None = None) -> dict:
    """Ejecuta un script Python en un subproceso y devuelve su `result`.

    El script debe dejar el resultado en `result` (lista de dicts o DataFrame).
    """
    code = (code or "").strip()
    if not code:
        raise AppError("El script esta vacio")
    if len(code) > MAX_SCRIPT_LENGTH:
        raise AppError("El script es demasiado largo")
    timeout = max(1, min(int(timeout or API_SCRIPT_TIMEOUT), 120))
    started = time.monotonic()
    with tempfile.TemporaryDirectory(prefix="biweb-api-") as tmp:
        script_path = Path(tmp) / "script.py"
        out_path = Path(tmp) / "result.json"
        script_path.write_text(_SCRIPT_PREAMBLE + "\n" + code + "\n" + _SCRIPT_EPILOGUE, encoding="utf-8")
        env = os.environ.copy()
        env["BIWEB_API_OUT"] = str(out_path)
        env["PYTHONIOENCODING"] = "utf-8"
        env.pop("BIWEB_SECRET_KEY", None)
        try:
            proc = subprocess.run(
                [sys.executable, str(script_path)],
                cwd=tmp,
                env=env,
                capture_output=True,
                text=True,
                timeout=timeout,
            )
        except subprocess.TimeoutExpired as exc:
            raise AppError(
                f"El script supero el tiempo limite de {timeout} s",
                status=408,
                code="script_timeout",
            ) from exc
        if proc.returncode != 0:
            detail = (proc.stderr or proc.stdout or "").strip()[-1200:]
            raise AppError(
                f"El script fallo: {detail or 'sin detalle'}",
                status=422,
                code="script_error",
            )
        if not out_path.exists():
            raise AppError("El script no produjo un resultado", status=422, code="script_result")
        try:
            raw = json.loads(out_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            raise AppError("El resultado del script no es JSON valido", status=422, code="script_result") from exc
    rows, columns = _normalize_rows(raw)
    if len(rows) > IMPORT_MAX_ROWS:
        raise AppError(
            f"El resultado supera el maximo de {IMPORT_MAX_ROWS} filas",
            status=413,
            code="too_many_rows",
        )
    return {
        "rows": rows,
        "columns": columns,
        "elapsed_ms": round((time.monotonic() - started) * 1000),
        "stdout": (proc.stdout or "")[-4000:],
    }


def dataset_sql(table_name: str) -> str:
    return "SELECT * FROM " + _quote(sanitize_table_name(table_name))
