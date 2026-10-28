"""Validacion de SQL para datasets y consola de desarrollo.

`validate_readonly_sql` protege los datasets. `validate_console_sql` admite
escritura para los roles de desarrollo/administracion, divide scripts y bloquea
comandos de sistema peligrosos. Ninguna de las dos sustituye a un usuario de
base de datos con privilegios minimos.
"""
from __future__ import annotations

import re

MAX_SQL_LENGTH = 100_000
MAX_STATEMENTS = 50

GO_LINE = re.compile(r"^\s*GO\s*(?:\d+)?\s*;?\s*$", re.IGNORECASE)
CONSOLE_FORBIDDEN = re.compile(
    r"\b("
    r"xp_cmdshell|sp_configure|openrowset|opendatasource|openquery|"
    r"shutdown|bulk\s+insert|backup\s+(?:database|log)|restore\s+(?:database|log)"
    r")\b",
    re.IGNORECASE,
)

FORBIDDEN = re.compile(
    r"\b("
    r"insert|update|delete|drop|create|alter|truncate|replace|merge|"
    r"attach|detach|pragma|vacuum|reindex|analyze|"
    r"grant|revoke|call|execute|exec|copy|into|"
    r"outfile|dumpfile|load_file|xp_cmdshell|pg_read_file|pg_sleep|"
    r"benchmark|sleep|shutdown"
    r")\b",
    re.IGNORECASE,
)


class SqlValidationError(ValueError):
    pass


def _strip_comments(sql: str) -> str:
    out: list[str] = []
    i, n = 0, len(sql)
    quote: str | None = None
    while i < n:
        ch = sql[i]
        if quote:
            out.append(ch)
            if ch == quote:
                if i + 1 < n and sql[i + 1] == quote:
                    out.append(sql[i + 1])
                    i += 2
                    continue
                quote = None
            i += 1
            continue
        if ch in "'\"`":
            quote = ch
            out.append(ch)
            i += 1
            continue
        if sql.startswith("--", i):
            j = sql.find("\n", i)
            i = n if j < 0 else j
            out.append(" ")
            continue
        if sql.startswith("/*", i):
            j = sql.find("*/", i + 2)
            if j < 0:
                raise SqlValidationError("Comentario /* sin cerrar")
            i = j + 2
            out.append(" ")
            continue
        out.append(ch)
        i += 1
    return "".join(out)


def _mask_literals(sql: str) -> str:
    out: list[str] = []
    i, n = 0, len(sql)
    quote: str | None = None
    while i < n:
        ch = sql[i]
        if quote:
            if ch == quote:
                if i + 1 < n and sql[i + 1] == quote:
                    i += 2
                    continue
                quote = None
                out.append(ch)
            else:
                out.append(" ")
            i += 1
            continue
        if ch in "'\"`":
            quote = ch
            out.append(ch)
        else:
            out.append(ch)
        i += 1
    return "".join(out)


def validate_readonly_sql(sql: str) -> str:
    if not sql or not sql.strip():
        raise SqlValidationError("La consulta esta vacia")
    if len(sql) > MAX_SQL_LENGTH:
        raise SqlValidationError("La consulta es demasiado larga")

    clean = _strip_comments(sql).strip()
    while clean.endswith(";"):
        clean = clean[:-1].rstrip()
    if ";" in _mask_literals(clean):
        raise SqlValidationError("Solo se permite una sentencia por consulta")

    first = re.match(r"\s*([a-zA-Z]+)", clean)
    if not first or first.group(1).upper() not in {"SELECT", "WITH"}:
        raise SqlValidationError("Solo se permiten consultas SELECT / WITH")

    match = FORBIDDEN.search(_mask_literals(clean))
    if match:
        raise SqlValidationError(f"Palabra no permitida en modo lectura: {match.group(0)}")
    return clean


def split_statements(sql: str) -> list[str]:
    """Divide un script en sentencias respetando literales, comentarios y GO."""
    if not sql or not sql.strip():
        raise SqlValidationError("El script SQL esta vacio")
    if len(sql) > MAX_SQL_LENGTH:
        raise SqlValidationError("El script SQL es demasiado largo")

    statements: list[str] = []
    buf: list[str] = []
    i, n = 0, len(sql)
    quote: str | None = None
    line_comment = False
    block_comment = False
    at_line_start = True

    def flush() -> None:
        raw = "".join(buf).strip()
        buf.clear()
        if not raw:
            return
        if not _strip_comments(raw).strip(" ;\t\r\n"):
            return
        statements.append(raw.rstrip(" ;\t\r\n"))

    while i < n:
        if at_line_start and not quote and not line_comment and not block_comment:
            end = sql.find("\n", i)
            end = n if end < 0 else end
            if GO_LINE.match(sql[i:end]):
                flush()
                i = min(end + 1, n)
                at_line_start = True
                continue

        ch = sql[i]
        nxt = sql[i + 1] if i + 1 < n else ""

        if line_comment:
            buf.append(ch)
            i += 1
            if ch == "\n":
                line_comment = False
                at_line_start = True
            continue

        if block_comment:
            buf.append(ch)
            if ch == "*" and nxt == "/":
                buf.append(nxt)
                i += 2
                block_comment = False
                at_line_start = False
            else:
                i += 1
                at_line_start = ch == "\n"
            continue

        if quote:
            buf.append(ch)
            if quote == "]" and ch == "]":
                if nxt == "]":
                    buf.append(nxt)
                    i += 2
                else:
                    quote = None
                    i += 1
            elif quote != "]" and ch == quote:
                if nxt == quote:
                    buf.append(nxt)
                    i += 2
                else:
                    quote = None
                    i += 1
            else:
                i += 1
            at_line_start = ch == "\n"
            continue

        if ch == "-" and nxt == "-":
            buf.append(ch)
            buf.append(nxt)
            i += 2
            line_comment = True
            at_line_start = False
            continue
        if ch == "/" and nxt == "*":
            buf.append(ch)
            buf.append(nxt)
            i += 2
            block_comment = True
            at_line_start = False
            continue
        if ch in "'\"`":
            quote = ch
            buf.append(ch)
            i += 1
            at_line_start = False
            continue
        if ch == "[":
            quote = "]"
            buf.append(ch)
            i += 1
            at_line_start = False
            continue
        if ch == ";":
            flush()
            i += 1
            at_line_start = False
            continue

        buf.append(ch)
        i += 1
        at_line_start = ch == "\n"

    if quote:
        raise SqlValidationError("Hay un literal o identificador sin cerrar")
    if block_comment:
        raise SqlValidationError("Comentario /* sin cerrar")
    flush()

    if not statements:
        raise SqlValidationError("El script no contiene sentencias")
    if len(statements) > MAX_STATEMENTS:
        raise SqlValidationError(f"El script supera el maximo de {MAX_STATEMENTS} sentencias")
    return statements


def validate_console_sql(sql: str, allow_write: bool) -> list[str]:
    """Valida un script para la consola SQL (solo roles de desarrollo/admin)."""
    statements = split_statements(sql)
    if not allow_write:
        for statement in statements:
            validate_readonly_sql(statement)
        return statements
    for statement in statements:
        masked = _mask_literals(_strip_comments(statement))
        match = CONSOLE_FORBIDDEN.search(masked)
        if match:
            raise SqlValidationError(f"Comando no permitido en la consola: {match.group(0)}")
    return statements
