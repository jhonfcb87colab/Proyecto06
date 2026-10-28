"""Capa de conexiones: prueba, introspeccion y ejecucion SQL.

Los datasets usan `run_query` (solo lectura). La consola de desarrollo usa
`execute_sql`, que opcionalmente permite DML/DDL y commit.
"""
from __future__ import annotations

import math
import sqlite3
import time
from datetime import date, datetime, time as dt_time
from decimal import Decimal
from pathlib import Path
from typing import Any

from .config import BASE_DIR, METADATA_DB, QUERY_TIMEOUT_MS, SAMPLE_DB, SQLITE_ROOTS
from .security import SqlValidationError, validate_console_sql, validate_readonly_sql

SUPPORTED_KINDS = {"sqlite", "postgres", "supabase", "mysql", "sqlserver", "oracle", "bigquery"}
KIND_ALIASES = {
    "sqlserver": "sqlserver",
    "sql-server": "sqlserver",
    "sql server": "sqlserver",
    "mssql": "sqlserver",
    "postgres": "postgres",
    "postgresql": "postgres",
    "supabase": "supabase",
    "mysql": "mysql",
    "mariadb": "mysql",
    "sqlite": "sqlite",
    "oracle": "oracle",
    "oracledb": "oracle",
    "bigquery": "bigquery",
    "big query": "bigquery",
}
SECRET_KEYS = ("password", "passwd", "secret", "token", "apikey", "api_key")
DEFAULT_SQLSERVER_DRIVER = "ODBC Driver 18 for SQL Server"


class AppError(Exception):
    def __init__(self, message: str, status: int = 400, code: str = "bad_request"):
        super().__init__(message)
        self.message = message
        self.status = status
        self.code = code


def _as_int(value: Any, default: int) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def canonical_kind(kind: str | None) -> str:
    key = str(kind or "").strip().lower().replace("_", " ")
    return KIND_ALIASES.get(key, key)


def normalize_config(kind: str, config: dict | None) -> dict:
    kind = canonical_kind(kind)
    config = dict(config or {})
    if kind not in SUPPORTED_KINDS:
        raise AppError(f"Tipo de conexion no soportado: {kind}")
    if kind == "sqlite":
        raw = str(config.get("path") or SAMPLE_DB).strip()
        path = Path(raw).expanduser()
        if not path.is_absolute():
            path = (BASE_DIR / path).resolve()
        else:
            path = path.resolve()
        if path == METADATA_DB.resolve():
            raise AppError(
                "No se permite conectar a la base de metadatos de BI Web",
                status=403,
                code="protected_path",
            )
        if SQLITE_ROOTS and not any(
            path == root or root in path.parents for root in SQLITE_ROOTS
        ):
            raise AppError(
                "La ruta SQLite esta fuera de BIWEB_SQLITE_ROOTS",
                status=403,
                code="protected_path",
            )
        return {"path": str(path)}
    if kind in {"postgres", "supabase"}:
        host = str(config.get("host") or "").strip()
        database = str(config.get("database") or "").strip()
        user = str(config.get("user") or "").strip()
        if not (host and database and user):
            raise AppError(f"{kind.title()} requiere host, database y user")
        return {
            "host": host,
            "port": _as_int(config.get("port"), 5432),
            "database": database,
            "user": user,
            "password": str(config.get("password") or ""),
            "sslmode": str(config.get("sslmode") or ("require" if kind == "supabase" else "prefer")),
        }
    if kind == "oracle":
        host = str(config.get("host") or "").strip()
        database = str(config.get("database") or "").strip()
        user = str(config.get("user") or "").strip()
        if not (host and database and user):
            raise AppError("Oracle requiere host, service name (database) y user")
        return {
            "host": host,
            "port": _as_int(config.get("port"), 1521),
            "database": database,
            "user": user,
            "password": str(config.get("password") or ""),
        }
    if kind == "bigquery":
        project = str(config.get("project") or "").strip()
        if not project:
            raise AppError("BigQuery requiere project")
        return {
            "project": project,
            "dataset": str(config.get("dataset") or "").strip(),
            "location": str(config.get("location") or "").strip(),
            "credentials": str(config.get("credentials") or "").strip(),
        }
    if kind == "sqlserver":
        host = str(config.get("host") or "").strip()
        database = str(config.get("database") or "").strip()
        user = str(config.get("user") or "").strip()
        trusted = str(config.get("trusted_connection") or "no").strip().lower()
        trusted = "yes" if trusted in {"1", "true", "yes", "y", "si", "s"} else "no"
        if not host or not database:
            raise AppError("SQL Server requiere host y database")
        if trusted != "yes" and not user:
            raise AppError("SQL Server requiere user o trusted_connection=yes")
        return {
            "host": host,
            "port": _as_int(config.get("port"), 1433),
            "database": database,
            "user": user,
            "password": str(config.get("password") or ""),
            "driver": str(config.get("driver") or DEFAULT_SQLSERVER_DRIVER).strip(),
            "encrypt": str(config.get("encrypt") or "yes").strip(),
            "trust_server_certificate": str(config.get("trust_server_certificate") or "yes").strip(),
            "trusted_connection": trusted,
            "timeout": _as_int(config.get("timeout"), 5),
        }
    host = str(config.get("host") or "").strip()
    database = str(config.get("database") or "").strip()
    user = str(config.get("user") or "").strip()
    if not (host and database and user):
        raise AppError("MySQL requiere host, database y user")
    return {
        "host": host,
        "port": _as_int(config.get("port"), 3306),
        "database": database,
        "user": user,
        "password": str(config.get("password") or ""),
        "charset": str(config.get("charset") or "utf8mb4"),
    }


def redact_config(config: dict) -> dict:
    clean = {}
    for key, value in (config or {}).items():
        if any(part in key.lower() for part in SECRET_KEYS) and value:
            clean[key] = "********"
        else:
            clean[key] = value
    return clean


def public_connection(row: dict) -> dict:
    return {
        "id": row["id"],
        "name": row["name"],
        "kind": row["kind"],
        "config": redact_config(row.get("config") or {}),
        "created_at": row.get("created_at"),
    }


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


def _dedupe_columns(columns: list[str]) -> list[str]:
    seen: dict[str, int] = {}
    out = []
    for name in columns:
        base = name or "col"
        if base in seen:
            seen[base] += 1
            out.append(f"{base}_{seen[base]}")
        else:
            seen[base] = 0
            out.append(base)
    return out


def _rows_to_dicts(cursor, limit: int) -> tuple[list[dict], list[str], bool]:
    columns = _dedupe_columns([d[0] for d in cursor.description or []])
    fetched = cursor.fetchmany(limit + 1)
    truncated = len(fetched) > limit
    rows = []
    for row in fetched[:limit]:
        if isinstance(row, sqlite3.Row):
            rows.append({columns[i]: _jsonable(row[i]) for i in range(len(columns))})
        else:
            rows.append({columns[i]: _jsonable(row[i]) for i in range(len(columns))})
    return rows, columns, truncated


# ------------------------------------------------------------------ sqlite
def _sqlite_connect(config: dict, readonly: bool = True) -> sqlite3.Connection:
    path = Path(config["path"])
    if not path.exists():
        raise AppError(f"No existe el archivo SQLite: {path}", status=404)
    if readonly:
        uri = path.as_uri() + "?mode=ro"
        con = sqlite3.connect(uri, uri=True, timeout=5)
        con.execute("PRAGMA query_only=ON")
    else:
        con = sqlite3.connect(str(path), timeout=5)
    con.row_factory = sqlite3.Row
    return con


def _install_deadline(con: sqlite3.Connection, timeout_ms: int) -> None:
    deadline = time.monotonic() + timeout_ms / 1000

    def handler() -> int:
        return 1 if time.monotonic() > deadline else 0

    con.set_progress_handler(handler, 20_000)


def _postgres_connect(config: dict, timeout_ms: int, readonly: bool = True):
    try:
        import psycopg2  # type: ignore
    except ImportError as exc:
        raise AppError(
            "Driver PostgreSQL no instalado. Ejecuta: pip install psycopg2-binary",
            status=501,
            code="driver_missing",
        ) from exc
    con = psycopg2.connect(
        host=config["host"],
        port=config["port"],
        dbname=config["database"],
        user=config["user"],
        password=config["password"],
        sslmode=config.get("sslmode", "prefer"),
        connect_timeout=5,
        options=f"-c statement_timeout={timeout_ms}",
    )
    con.set_session(readonly=readonly, autocommit=False)
    return con


def _mysql_connect(config: dict, timeout_ms: int, readonly: bool = True):
    try:
        import pymysql  # type: ignore
    except ImportError as exc:
        raise AppError(
            "Driver MySQL no instalado. Ejecuta: pip install PyMySQL",
            status=501,
            code="driver_missing",
        ) from exc
    con = pymysql.connect(
        host=config["host"],
        port=config["port"],
        database=config["database"],
        user=config["user"],
        password=config["password"],
        charset=config.get("charset", "utf8mb4"),
        connect_timeout=5,
        read_timeout=max(1, timeout_ms // 1000),
        autocommit=False,
    )
    if readonly:
        with con.cursor() as cur:
            cur.execute("SET SESSION TRANSACTION READ ONLY")
    return con


def _odbc_escape(value: Any) -> str:
    text = "" if value is None else str(value)
    if any(ch in text for ch in ";{}"):
        return "{" + text.replace("}", "}}") + "}"
    return text


def _sqlserver_connect(config: dict, timeout_ms: int):
    try:
        import pyodbc  # type: ignore
    except ImportError as exc:
        raise AppError(
            "Driver SQL Server no instalado. Ejecuta: pip install pyodbc "
            "y instala el Microsoft ODBC Driver for SQL Server",
            status=501,
            code="driver_missing",
        ) from exc
    driver = str(config.get("driver") or DEFAULT_SQLSERVER_DRIVER).strip()
    if driver.startswith("{") and driver.endswith("}"):
        driver = driver[1:-1]
    driver = driver.replace("}", "}}")
    server = str(config["host"])
    port = config.get("port")
    if port and "," not in server and "\\" not in server:
        server = f"{server},{port}"
    parts = [
        f"DRIVER={{{driver}}}",
        f"SERVER={_odbc_escape(server)}",
        f"DATABASE={_odbc_escape(config['database'])}",
        f"Encrypt={_odbc_escape(config.get('encrypt', 'yes'))}",
        f"TrustServerCertificate={_odbc_escape(config.get('trust_server_certificate', 'yes'))}",
    ]
    trusted = str(config.get("trusted_connection", "no")).lower() == "yes"
    if trusted:
        parts.append("Trusted_Connection=yes")
    else:
        parts.append(f"UID={_odbc_escape(config.get('user', ''))}")
        parts.append(f"PWD={_odbc_escape(config.get('password', ''))}")
    try:
        con = pyodbc.connect(
            ";".join(parts),
            timeout=max(1, _as_int(config.get("timeout"), 5)),
            autocommit=False,
        )
    except pyodbc.Error as exc:
        message = str(exc)
        if "SSPI" in message or "Kerberos" in message:
            raise AppError(
                "SQL Server no pudo usar la autenticacion de Windows: este equipo no tiene "
                "credenciales Kerberos. Desmarca Trusted_Connection y usa usuario/contrasena "
                "SQL, o configura Kerberos (krb5.conf y kinit) para autenticacion integrada.",
                status=422,
                code="windows_auth_unavailable",
            ) from exc
        raise AppError(
            f"No se pudo conectar a SQL Server: {message}",
            status=422,
            code="connection_error",
        ) from exc
    try:
        con.timeout = max(1, timeout_ms // 1000)
    except (AttributeError, ValueError):
        pass
    return con


def _oracle_connect(config: dict, timeout_ms: int, readonly: bool = True):
    try:
        import oracledb  # type: ignore
    except ImportError as exc:
        raise AppError(
            "Driver Oracle no instalado. Ejecuta: pip install oracledb",
            status=501,
            code="driver_missing",
        ) from exc
    dsn = f"{config['host']}:{config['port']}/{config['database']}"
    con = oracledb.connect(
        user=config["user"],
        password=config["password"],
        dsn=dsn,
    )
    try:
        con.call_timeout = max(1, timeout_ms)
    except (AttributeError, ValueError):
        pass
    if readonly:
        with con.cursor() as cur:
            cur.execute("SET TRANSACTION READ ONLY")
    return con


def _bigquery_client(config: dict):
    try:
        from google.cloud import bigquery  # type: ignore
    except ImportError as exc:
        raise AppError(
            "Driver BigQuery no instalado. Ejecuta: pip install google-cloud-bigquery",
            status=501,
            code="driver_missing",
        ) from exc
    kwargs = {"project": config["project"]}
    if config.get("location"):
        kwargs["location"] = config["location"]
    credentials = config.get("credentials")
    if credentials:
        try:
            from google.oauth2 import service_account  # type: ignore
        except ImportError as exc:
            raise AppError(
                "Faltan dependencias de credenciales de BigQuery",
                status=501,
                code="driver_missing",
            ) from exc
        kwargs["credentials"] = service_account.Credentials.from_service_account_file(credentials)
    return bigquery.Client(**kwargs)


def _bigquery_query(config: dict, sql: str, limit: int, timeout_ms: int) -> tuple[list[dict], list[str], bool]:
    client = _bigquery_client(config)
    job_config = None
    if config.get("dataset"):
        from google.cloud import bigquery  # type: ignore

        job_config = bigquery.QueryJobConfig(
            default_dataset=f"{config['project']}.{config['dataset']}"
        )
    job = client.query(sql, job_config=job_config)
    result = job.result(timeout=max(1, timeout_ms // 1000))
    columns = [field.name for field in result.schema]
    rows = []
    truncated = False
    for index, row in enumerate(result):
        if index >= limit:
            truncated = True
            break
        values = [row[i] for i in range(len(columns))]
        rows.append({columns[i]: _jsonable(values[i]) for i in range(len(columns))})
    return rows, columns, truncated


def _connect_any(kind: str, config: dict, timeout_ms: int, readonly: bool = True):
    if kind in {"postgres", "supabase"}:
        return _postgres_connect(config, timeout_ms, readonly=readonly)
    if kind == "mysql":
        return _mysql_connect(config, timeout_ms, readonly=readonly)
    if kind == "sqlserver":
        return _sqlserver_connect(config, timeout_ms)
    if kind == "oracle":
        return _oracle_connect(config, timeout_ms, readonly=readonly)
    raise AppError(f"Motor no soportado: {kind}", status=501, code="driver_missing")


# --------------------------------------------------------------------- API
def test_connection(kind: str, config: dict | None) -> dict:
    kind = canonical_kind(kind)
    cfg = normalize_config(kind, config)
    started = time.monotonic()
    try:
        if kind == "sqlite":
            con = _sqlite_connect(cfg)
            try:
                con.execute("SELECT 1").fetchone()
            finally:
                con.close()
        elif kind == "bigquery":
            client = _bigquery_client(cfg)
            client.query("SELECT 1").result()
        elif kind in {"postgres", "supabase", "mysql", "sqlserver", "oracle"}:
            con = _connect_any(kind, cfg, 5000)
            try:
                with con.cursor() as cur:
                    cur.execute("SELECT 1 FROM DUAL" if kind == "oracle" else "SELECT 1")
                    cur.fetchone()
            finally:
                con.close()
        return {
            "ok": True,
            "message": "Conexion correcta",
            "elapsed_ms": round((time.monotonic() - started) * 1000),
            "config": redact_config(cfg),
        }
    except AppError:
        raise
    except Exception as exc:  # noqa: BLE001
        return {
            "ok": False,
            "message": f"No se pudo conectar: {exc}",
            "elapsed_ms": round((time.monotonic() - started) * 1000),
            "config": redact_config(cfg),
        }


def run_query(row: dict, sql: str, limit: int = 5000, timeout_ms: int | None = None) -> dict:
    try:
        clean = validate_readonly_sql(sql)
    except SqlValidationError as exc:
        raise AppError(str(exc), status=400, code="unsafe_sql") from exc

    timeout_ms = timeout_ms or QUERY_TIMEOUT_MS
    started = time.monotonic()
    kind = canonical_kind(row["kind"])
    config = normalize_config(kind, row.get("config") or {})

    try:
        if kind == "sqlite":
            con = _sqlite_connect(config)
            try:
                _install_deadline(con, timeout_ms)
                cur = con.execute(clean)
                rows, columns, truncated = _rows_to_dicts(cur, limit)
            finally:
                con.close()
        elif kind == "bigquery":
            rows, columns, truncated = _bigquery_query(config, clean, limit, timeout_ms)
        elif kind in {"postgres", "supabase", "mysql", "sqlserver", "oracle"}:
            con = _connect_any(kind, config, timeout_ms)
            try:
                with con.cursor() as cur:
                    cur.execute(clean)
                    rows, columns, truncated = _rows_to_dicts(cur, limit)
                con.rollback()
            finally:
                con.close()
    except AppError:
        raise
    except Exception as exc:  # noqa: BLE001
        message = str(exc)
        if "interrupted" in message.lower():
            raise AppError("La consulta excedio el tiempo limite", status=408, code="timeout") from exc
        raise AppError(f"Error ejecutando la consulta: {message}", status=422, code="query_error") from exc

    return {
        "rows": rows,
        "columns": columns,
        "row_count": len(rows),
        "truncated": truncated,
        "elapsed_ms": round((time.monotonic() - started) * 1000),
    }


def execute_sql(
    row: dict,
    sql: str,
    mode: str = "read",
    limit: int = 500,
    timeout_ms: int | None = None,
) -> dict:
    """Ejecuta un script SQL para la consola de desarrollo.

    mode="read" solo permite SELECT/WITH y siempre revierte la transaccion.
    mode="write" permite DML/DDL y hace commit al terminar sin errores.
    """
    mode = (mode or "read").strip().lower()
    if mode not in {"read", "write"}:
        raise AppError("Modo de ejecucion no valido (read/write)", status=400)
    allow_write = mode == "write"
    try:
        statements = validate_console_sql(sql, allow_write)
    except SqlValidationError as exc:
        raise AppError(str(exc), status=400, code="unsafe_sql") from exc

    timeout_ms = timeout_ms or QUERY_TIMEOUT_MS
    limit = max(1, min(int(limit or 500), 20000))
    kind = canonical_kind(row["kind"])
    config = normalize_config(kind, row.get("config") or {})
    started = time.monotonic()
    results: list[dict] = []
    committed = False

    try:
        if kind == "sqlite":
            con = _sqlite_connect(config, readonly=not allow_write)
            try:
                for index, statement in enumerate(statements, start=1):
                    _install_deadline(con, timeout_ms)
                    cur = con.execute(statement)
                    if cur.description:
                        rows, columns, truncated = _rows_to_dicts(cur, limit)
                        results.append(
                            {
                                "index": index,
                                "statement": statement,
                                "type": "query",
                                "columns": columns,
                                "rows": rows,
                                "row_count": len(rows),
                                "truncated": truncated,
                            }
                        )
                    else:
                        rowcount = getattr(cur, "rowcount", None)
                        results.append(
                            {
                                "index": index,
                                "statement": statement,
                                "type": "command",
                                "rowcount": rowcount if rowcount is not None and rowcount >= 0 else None,
                            }
                        )
                if allow_write:
                    con.commit()
                    committed = True
                else:
                    con.rollback()
            finally:
                con.close()
        elif kind == "bigquery":
            client = _bigquery_client(config)
            for index, statement in enumerate(statements, start=1):
                job = client.query(statement)
                result = job.result(timeout=max(1, timeout_ms // 1000))
                columns = [field.name for field in result.schema]
                if columns:
                    rows = []
                    truncated = False
                    for row_index, row in enumerate(result):
                        if row_index >= limit:
                            truncated = True
                            break
                        rows.append({columns[i]: _jsonable(row[i]) for i in range(len(columns))})
                    results.append(
                        {
                            "index": index,
                            "statement": statement,
                            "type": "query",
                            "columns": columns,
                            "rows": rows,
                            "row_count": len(rows),
                            "truncated": truncated,
                        }
                    )
                else:
                    results.append(
                        {
                            "index": index,
                            "statement": statement,
                            "type": "command",
                            "rowcount": getattr(job, "num_dml_affected_rows", None),
                        }
                    )
            committed = bool(allow_write)
        else:
            con = _connect_any(kind, config, timeout_ms, readonly=not allow_write)
            try:
                with con.cursor() as cur:
                    for index, statement in enumerate(statements, start=1):
                        cur.execute(statement)
                        if cur.description:
                            rows, columns, truncated = _rows_to_dicts(cur, limit)
                            results.append(
                                {
                                    "index": index,
                                    "statement": statement,
                                    "type": "query",
                                    "columns": columns,
                                    "rows": rows,
                                    "row_count": len(rows),
                                    "truncated": truncated,
                                }
                            )
                        else:
                            rowcount = getattr(cur, "rowcount", None)
                            results.append(
                                {
                                    "index": index,
                                    "statement": statement,
                                    "type": "command",
                                    "rowcount": rowcount if rowcount is not None and rowcount >= 0 else None,
                                }
                            )
                if allow_write:
                    con.commit()
                    committed = True
                else:
                    con.rollback()
            finally:
                con.close()
    except AppError:
        raise
    except Exception as exc:  # noqa: BLE001
        message = str(exc)
        if "interrupted" in message.lower() or "timed out" in message.lower():
            raise AppError("La ejecucion excedio el tiempo limite", status=408, code="timeout") from exc
        raise AppError(f"Error ejecutando SQL: {message}", status=422, code="query_error") from exc

    return {
        "mode": mode,
        "committed": committed,
        "statements": results,
        "statement_count": len(results),
        "elapsed_ms": round((time.monotonic() - started) * 1000),
    }


def introspect(row: dict) -> list[dict]:
    kind = canonical_kind(row["kind"])
    config = normalize_config(kind, row.get("config") or {})
    try:
        if kind == "sqlite":
            con = _sqlite_connect(config)
            try:
                tables = con.execute(
                    "SELECT name, type FROM sqlite_master"
                    " WHERE type IN ('table','view') AND name NOT LIKE 'sqlite_%'"
                    " ORDER BY name"
                ).fetchall()
                result = []
                for table in tables:
                    name = table["name"]
                    quoted = '"' + name.replace('"', '""') + '"'
                    cols = con.execute(f"PRAGMA table_info({quoted})").fetchall()
                    result.append(
                        {
                            "name": name,
                            "type": table["type"],
                            "columns": [
                                {
                                    "name": c["name"],
                                    "type": c["type"] or "",
                                    "primary_key": bool(c["pk"]),
                                }
                                for c in cols
                            ],
                        }
                    )
                return result
            finally:
                con.close()
        if kind in {"postgres", "supabase"}:
            con = _postgres_connect(config, 5000)
            try:
                with con.cursor() as cur:
                    cur.execute(
                        "SELECT table_name FROM information_schema.tables"
                        " WHERE table_schema NOT IN ('pg_catalog','information_schema')"
                        " ORDER BY table_name"
                    )
                    names = [r[0] for r in cur.fetchall()]
                    out = []
                    for name in names:
                        cur.execute(
                            "SELECT column_name, data_type FROM information_schema.columns"
                            " WHERE table_name=%s ORDER BY ordinal_position",
                            (name,),
                        )
                        out.append(
                            {
                                "name": name,
                                "type": "table",
                                "columns": [
                                    {"name": c, "type": t, "primary_key": False} for c, t in cur.fetchall()
                                ],
                            }
                        )
                con.rollback()
                return out
            finally:
                con.close()
        if kind == "sqlserver":
            con = _sqlserver_connect(config, 5000)
            try:
                with con.cursor() as cur:
                    cur.execute(
                        "SELECT c.TABLE_SCHEMA, c.TABLE_NAME, c.COLUMN_NAME, c.DATA_TYPE,"
                        " CASE WHEN kcu.COLUMN_NAME IS NULL THEN 0 ELSE 1 END AS is_pk"
                        " FROM INFORMATION_SCHEMA.COLUMNS c"
                        " LEFT JOIN INFORMATION_SCHEMA.TABLE_CONSTRAINTS tc"
                        "   ON tc.TABLE_SCHEMA=c.TABLE_SCHEMA AND tc.TABLE_NAME=c.TABLE_NAME"
                        "   AND tc.CONSTRAINT_TYPE='PRIMARY KEY'"
                        " LEFT JOIN INFORMATION_SCHEMA.KEY_COLUMN_USAGE kcu"
                        "   ON kcu.CONSTRAINT_NAME=tc.CONSTRAINT_NAME"
                        "   AND kcu.TABLE_SCHEMA=c.TABLE_SCHEMA AND kcu.TABLE_NAME=c.TABLE_NAME"
                        "   AND kcu.COLUMN_NAME=c.COLUMN_NAME"
                        " ORDER BY c.TABLE_SCHEMA, c.TABLE_NAME, c.ORDINAL_POSITION"
                    )
                    rows = cur.fetchall()
                con.rollback()
                grouped: dict[tuple[str, str], list[dict]] = {}
                for schema, table, column, dtype, is_pk in rows:
                    key = (schema, table)
                    grouped.setdefault(key, []).append(
                        {"name": column, "type": dtype or "", "primary_key": bool(is_pk)}
                    )
                return [
                    {
                        "name": table if schema == "dbo" else f"{schema}.{table}",
                        "type": "table",
                        "columns": columns,
                    }
                    for (schema, table), columns in grouped.items()
                ]
            finally:
                con.close()
        if kind == "oracle":
            con = _oracle_connect(config, 5000)
            try:
                with con.cursor() as cur:
                    cur.execute(
                        "SELECT table_name FROM user_tables ORDER BY table_name"
                    )
                    names = [r[0] for r in cur.fetchall()]
                    out = []
                    for name in names:
                        cur.execute(
                            "SELECT column_name, data_type FROM user_tab_columns"
                            " WHERE table_name=:1 ORDER BY column_id",
                            (name,),
                        )
                        out.append(
                            {
                                "name": name,
                                "type": "table",
                                "columns": [
                                    {"name": c, "type": t, "primary_key": False}
                                    for c, t in cur.fetchall()
                                ],
                            }
                        )
                con.rollback()
                return out
            finally:
                con.close()
        if kind == "bigquery":
            client = _bigquery_client(config)
            dataset = config.get("dataset") or ""
            if not dataset:
                return []
            return [
                {
                    "name": table.table_id,
                    "type": "table",
                    "columns": [
                        {
                            "name": field.name,
                            "type": field.field_type,
                            "primary_key": False,
                        }
                        for field in table.schema
                    ],
                }
                for table in client.list_tables(dataset)
            ]
        con = _mysql_connect(config, 5000)
        try:
            with con.cursor() as cur:
                cur.execute("SHOW TABLES")
                names = [r[0] for r in cur.fetchall()]
                out = []
                for name in names:
                    cur.execute(f"SHOW COLUMNS FROM `{name.replace('`','``')}`")
                    out.append(
                        {
                            "name": name,
                            "type": "table",
                            "columns": [
                                {"name": r[0], "type": r[1], "primary_key": r[3] == "PRI"}
                                for r in cur.fetchall()
                            ],
                        }
                    )
            con.rollback()
            return out
        finally:
            con.close()
    except AppError:
        raise
    except Exception as exc:  # noqa: BLE001
        raise AppError(f"No se pudo inspeccionar el esquema: {exc}", status=422, code="introspect_error") from exc
