"""Autenticacion, roles, permisos, accesos por tablero y auditoria.

Todo se guarda en la misma base SQLite de metadatos (var/biweb.db).
"""
from __future__ import annotations

import json
import re
import secrets
import sqlite3
from functools import wraps
from typing import Any

from flask import g, request, session
from werkzeug.security import check_password_hash, generate_password_hash

from . import store
from .config import ADMIN_PASSWORD, DEMO_USERS, PASSWORD_MIN_LENGTH

USERNAME_RE = re.compile(r"^[A-Za-z0-9._-]{3,40}$")

PERMISSIONS = [
    ("dashboards.view", "Ver tableros", "Tableros", "Acceder a los tableros asignados"),
    ("dashboards.create", "Crear tableros", "Tableros", "Crear nuevos tableros"),
    ("dashboards.design", "Editar visualizaciones", "Tableros", "Crear y ajustar widgets"),
    ("dashboards.delete", "Eliminar tableros", "Tableros", "Eliminar tableros permitidos"),
    ("dashboards.view_all", "Ver todos los tableros", "Alcance", "Ignorar la asignacion individual"),
    ("dashboards.edit_all", "Editar todos los tableros", "Alcance", "Editar cualquier tablero"),
    ("connections.view", "Ver conexiones", "Datos", "Consultar conexiones (sin secretos)"),
    ("connections.manage", "Gestionar conexiones", "Datos", "Crear, probar y editar conexiones"),
    ("datasets.view", "Ver datasets", "Datos", "Consultar datasets y previsualizar SQL"),
    ("datasets.manage", "Gestionar datasets", "Datos", "Crear, editar y eliminar datasets"),
    ("import.api", "Importar APIs", "Datos", "Administrar scripts Python para importar APIs"),
    ("sql.console", "Consola SQL", "Datos", "Ejecutar SQL de lectura y escritura (solo desarrollo/admin)"),
    ("monitoring.audit", "Ver auditoria", "Monitoreo", "Consultar el registro de acciones"),
    ("admin.users", "Gestionar usuarios", "Administracion", "Crear y editar usuarios"),
    ("admin.roles", "Gestionar roles", "Administracion", "Editar roles y sus permisos"),
    ("access.manage", "Asignar accesos", "Administracion", "Conceder acceso por tablero"),
    ("system.reset", "Restaurar demo", "Sistema", "Borrar datos y regenerar el ejemplo"),
]

PERMISSION_KEYS = [p[0] for p in PERMISSIONS]
PERMISSION_LABELS = {p[0]: p[1] for p in PERMISSIONS}
PERMISSION_GROUPS: dict[str, list[dict]] = {}
for _key, _label, _group, _desc in PERMISSIONS:
    PERMISSION_GROUPS.setdefault(_group, []).append(
        {"key": _key, "label": _label, "description": _desc}
    )

DEFAULT_ROLES = [
    {
        "slug": "administrador",
        "name": "Administrador",
        "description": "Control total: usuarios, roles, diseno, monitoreo y visualizacion.",
        "permissions": set(PERMISSION_KEYS),
    },
    {
        "slug": "auditor",
        "name": "Auditor",
        "description": "Puede ver todos los tableros y la auditoria, sin modificar nada.",
        "permissions": {
            "dashboards.view",
            "dashboards.view_all",
            "connections.view",
            "datasets.view",
            "monitoring.audit",
        },
    },
    {
        "slug": "desarrollador",
        "name": "Desarrollador",
        "description": "Crea tableros y ajusta visualizaciones sobre los tableros asignados.",
        "permissions": {
            "dashboards.view",
            "dashboards.create",
            "dashboards.design",
            "dashboards.delete",
            "connections.view",
            "connections.manage",
            "datasets.view",
            "datasets.manage",
            "sql.console",
        },
    },
    {
        "slug": "visualizador",
        "name": "Usuario de visualizacion",
        "description": "Solo consulta los tableros que el administrador le asigne.",
        "permissions": {"dashboards.view"},
    },
]

SCHEMA = """
CREATE TABLE IF NOT EXISTS roles (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL,
    slug TEXT NOT NULL UNIQUE,
    description TEXT NOT NULL DEFAULT '',
    is_system INTEGER NOT NULL DEFAULT 0,
    created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS permissions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    key TEXT NOT NULL UNIQUE,
    label TEXT NOT NULL,
    grp TEXT NOT NULL,
    description TEXT NOT NULL DEFAULT ''
);
CREATE TABLE IF NOT EXISTS role_permissions (
    role_id INTEGER NOT NULL REFERENCES roles(id) ON DELETE CASCADE,
    permission_id INTEGER NOT NULL REFERENCES permissions(id) ON DELETE CASCADE,
    PRIMARY KEY (role_id, permission_id)
);
CREATE TABLE IF NOT EXISTS users (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    username TEXT NOT NULL UNIQUE COLLATE NOCASE,
    email TEXT NOT NULL DEFAULT '',
    full_name TEXT NOT NULL DEFAULT '',
    password_hash TEXT NOT NULL,
    role_id INTEGER NOT NULL REFERENCES roles(id),
    is_active INTEGER NOT NULL DEFAULT 1,
    created_at TEXT NOT NULL,
    last_login_at TEXT
);
CREATE TABLE IF NOT EXISTS user_dashboard_access (
    user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    dashboard_id INTEGER NOT NULL REFERENCES dashboards(id) ON DELETE CASCADE,
    level TEXT NOT NULL CHECK(level IN ('view','edit')),
    granted_by INTEGER REFERENCES users(id) ON DELETE SET NULL,
    created_at TEXT NOT NULL,
    PRIMARY KEY (user_id, dashboard_id)
);
CREATE TABLE IF NOT EXISTS audit_log (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER,
    username TEXT,
    action TEXT NOT NULL,
    target TEXT,
    detail TEXT,
    ip TEXT,
    created_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_audit_created ON audit_log(created_at);
CREATE INDEX IF NOT EXISTS idx_audit_user ON audit_log(user_id);
"""


class AuthRequired(Exception):
    status = 401


class PermissionDenied(Exception):
    status = 403


# ------------------------------------------------------------------ esquema
def init_auth_db() -> None:
    with store.session() as con:
        con.executescript(SCHEMA)


def _set_role_permissions(con: sqlite3.Connection, role_id: int, keys) -> None:
    con.execute("DELETE FROM role_permissions WHERE role_id=?", (role_id,))
    for key in keys:
        row = con.execute("SELECT id FROM permissions WHERE key=?", (key,)).fetchone()
        if row:
            con.execute(
                "INSERT OR IGNORE INTO role_permissions(role_id, permission_id) VALUES(?,?)",
                (role_id, row["id"]),
            )


def _ensure_role(con: sqlite3.Connection, spec: dict) -> tuple[int, bool]:
    row = con.execute("SELECT id FROM roles WHERE slug=?", (spec["slug"],)).fetchone()
    created = row is None
    if created:
        cur = con.execute(
            "INSERT INTO roles(name, slug, description, is_system, created_at) VALUES(?,?,?,?,?)",
            (spec["name"], spec["slug"], spec["description"], 1, store.now()),
        )
        role_id = cur.lastrowid
        _set_role_permissions(con, role_id, spec["permissions"])
    else:
        role_id = row["id"]
        con.execute("UPDATE roles SET is_system=1 WHERE id=?", (role_id,))
    return role_id, created


def _ensure_user(
    con: sqlite3.Connection,
    username: str,
    password: str,
    role_id: int,
    full_name: str,
    email: str = "",
) -> bool:
    row = con.execute("SELECT id FROM users WHERE username=?", (username,)).fetchone()
    if row:
        return False
    con.execute(
        "INSERT INTO users(username, email, full_name, password_hash, role_id, is_active, created_at)"
        " VALUES(?,?,?,?,?,1,?)",
        (username, email, full_name, hash_password(password), role_id, store.now()),
    )
    return True


def seed_auth() -> dict:
    """Crea permisos, roles base y usuarios iniciales si faltan."""
    init_auth_db()
    created_users = []
    created_roles = []
    with store.session() as con:
        for key, label, group, description in PERMISSIONS:
            con.execute(
                "INSERT INTO permissions(key, label, grp, description) VALUES(?,?,?,?)"
                " ON CONFLICT(key) DO UPDATE SET label=excluded.label, grp=excluded.grp,"
                " description=excluded.description",
                (key, label, group, description),
            )

        role_ids = {}
        for spec in DEFAULT_ROLES:
            role_id, created = _ensure_role(con, spec)
            role_ids[spec["slug"]] = role_id
            if created:
                created_roles.append(spec["slug"])

        # El administrador siempre conserva todos los permisos.
        _set_role_permissions(con, role_ids["administrador"], PERMISSION_KEYS)

        # Migracion: la consola SQL se agrega a los roles base existentes.
        console_perm = con.execute("SELECT id FROM permissions WHERE key='sql.console'").fetchone()
        if console_perm:
            for slug in ("desarrollador", "administrador"):
                role = con.execute("SELECT id FROM roles WHERE slug=?", (slug,)).fetchone()
                if role:
                    con.execute(
                        "INSERT OR IGNORE INTO role_permissions(role_id, permission_id) VALUES(?,?)",
                        (role["id"], console_perm["id"]),
                    )

        admin_exists = con.execute(
            "SELECT 1 FROM users WHERE role_id=?", (role_ids["administrador"],)
        ).fetchone()
        if not admin_exists:
            if _ensure_user(
                con,
                "admin",
                ADMIN_PASSWORD,
                role_ids["administrador"],
                "Administrador",
                "admin@local",
            ):
                created_users.append({"username": "admin", "password": ADMIN_PASSWORD, "role": "administrador"})

        if DEMO_USERS:
            demo = [
                ("auditor", "auditor123", "auditor", "Auditor"),
                ("dev", "dev12345", "desarrollador", "Desarrollador"),
                ("viewer", "viewer123", "visualizador", "Usuario de visualizacion"),
            ]
            for username, password, slug, full_name in demo:
                if _ensure_user(
                    con, username, password, role_ids[slug], full_name, f"{username}@local"
                ):
                    created_users.append({"username": username, "password": password, "role": slug})

    if created_users:
        grant_demo_access()

    return {"users": created_users, "roles": created_roles}


def grant_demo_access() -> None:
    """Asigna acceso demo a dev/viewer sobre los tableros actuales."""
    dev = get_user_by_username("dev")
    viewer = get_user_by_username("viewer")
    if not dev and not viewer:
        return
    for dashboard in store.list_dashboards():
        if dev:
            set_access(dev["id"], dashboard["id"], "edit")
        if viewer:
            set_access(viewer["id"], dashboard["id"], "view")


# ------------------------------------------------------------ contrasenas
def hash_password(password: str) -> str:
    return generate_password_hash(password)


def validate_password(password: str) -> None:
    if not password or len(password) < PASSWORD_MIN_LENGTH:
        raise ValueError(f"La contrasena debe tener al menos {PASSWORD_MIN_LENGTH} caracteres")


def validate_username(username: str) -> None:
    if not USERNAME_RE.match(username or ""):
        raise ValueError("Usuario invalido: usa 3-40 caracteres [A-Za-z0-9._-]")


# ---------------------------------------------------------------- usuarios
def _user_row(row) -> dict | None:
    if row is None:
        return None
    user = dict(row)
    user["permissions"] = permissions_for_role(user["role_id"], user.get("role_slug"))
    user["is_active"] = bool(user["is_active"])
    return user


def get_user_by_id(user_id: int) -> dict | None:
    with store.session() as con:
        row = con.execute(
            "SELECT u.*, r.slug AS role_slug, r.name AS role_name"
            " FROM users u JOIN roles r ON r.id=u.role_id WHERE u.id=?",
            (user_id,),
        ).fetchone()
        return _user_row(row)


def get_user_by_username(username: str) -> dict | None:
    with store.session() as con:
        row = con.execute(
            "SELECT u.*, r.slug AS role_slug, r.name AS role_name"
            " FROM users u JOIN roles r ON r.id=u.role_id WHERE u.username=?",
            (username,),
        ).fetchone()
        return _user_row(row)


def list_users() -> list[dict]:
    with store.session() as con:
        rows = con.execute(
            "SELECT u.*, r.slug AS role_slug, r.name AS role_name"
            " FROM users u JOIN roles r ON r.id=u.role_id ORDER BY u.username"
        ).fetchall()
        return [_user_row(row) for row in rows]


def create_user(
    username: str,
    password: str,
    role_id: int,
    full_name: str = "",
    email: str = "",
    is_active: bool = True,
) -> dict:
    validate_username(username)
    validate_password(password)
    with store.session() as con:
        if not con.execute("SELECT 1 FROM roles WHERE id=?", (role_id,)).fetchone():
            raise ValueError("El rol no existe")
        try:
            cur = con.execute(
                "INSERT INTO users(username, email, full_name, password_hash, role_id, is_active, created_at)"
                " VALUES(?,?,?,?,?,?,?)",
                (
                    username,
                    email.strip(),
                    full_name.strip(),
                    hash_password(password),
                    role_id,
                    1 if is_active else 0,
                    store.now(),
                ),
            )
        except sqlite3.IntegrityError as exc:
            raise ValueError("El nombre de usuario ya existe") from exc
    return get_user_by_id(cur.lastrowid)  # type: ignore[return-value]


def update_user(user_id: int, role_id: int, full_name: str, email: str, is_active: bool) -> None:
    with store.session() as con:
        if not con.execute("SELECT 1 FROM roles WHERE id=?", (role_id,)).fetchone():
            raise ValueError("El rol no existe")
        con.execute(
            "UPDATE users SET role_id=?, full_name=?, email=?, is_active=? WHERE id=?",
            (role_id, full_name.strip(), email.strip(), 1 if is_active else 0, user_id),
        )


def set_password(user_id: int, password: str) -> None:
    validate_password(password)
    with store.session() as con:
        con.execute("UPDATE users SET password_hash=? WHERE id=?", (hash_password(password), user_id))


def change_own_password(user: dict, current: str, new: str) -> None:
    if not check_password_hash(user["password_hash"], current or ""):
        raise ValueError("La contrasena actual no es correcta")
    set_password(user["id"], new)


def delete_user(user_id: int, actor_id: int) -> None:
    if user_id == actor_id:
        raise ValueError("No puedes eliminar tu propio usuario")
    target = get_user_by_id(user_id)
    if not target:
        raise ValueError("Usuario no encontrado")
    with store.session() as con:
        if target["role_slug"] == "administrador":
            count = con.execute(
                "SELECT COUNT(*) AS n FROM users u JOIN roles r ON r.id=u.role_id"
                " WHERE r.slug='administrador' AND u.is_active=1"
            ).fetchone()["n"]
            if count <= 1:
                raise ValueError("Debe quedar al menos un administrador activo")
        con.execute("DELETE FROM users WHERE id=?", (user_id,))


def authenticate(username: str, password: str) -> dict | None:
    user = get_user_by_username(username)
    if not user or not user["is_active"]:
        return None
    if not check_password_hash(user["password_hash"], password or ""):
        return None
    with store.session() as con:
        con.execute("UPDATE users SET last_login_at=? WHERE id=?", (store.now(), user["id"]))
    user["last_login_at"] = store.now()
    return user


# ------------------------------------------------------------------- roles
def permissions_for_role(role_id: int, role_slug: str | None = None) -> set[str]:
    if role_slug == "administrador":
        return set(PERMISSION_KEYS)
    with store.session() as con:
        rows = con.execute(
            "SELECT p.key FROM permissions p"
            " JOIN role_permissions rp ON rp.permission_id=p.id"
            " WHERE rp.role_id=?",
            (role_id,),
        ).fetchall()
        return {row["key"] for row in rows}


def list_roles() -> list[dict]:
    with store.session() as con:
        rows = con.execute(
            "SELECT r.*, (SELECT COUNT(*) FROM users u WHERE u.role_id=r.id) AS user_count"
            " FROM roles r ORDER BY r.is_system DESC, r.name"
        ).fetchall()
        return [dict(row) for row in rows]


def get_role(role_id: int) -> dict | None:
    with store.session() as con:
        row = con.execute("SELECT * FROM roles WHERE id=?", (role_id,)).fetchone()
        return dict(row) if row else None


def role_permission_keys(role_id: int) -> set[str]:
    return permissions_for_role(role_id)


def set_role_permissions(role_id: int, keys: list[str]) -> None:
    role = get_role(role_id)
    if not role:
        raise ValueError("Rol no encontrado")
    if role["slug"] == "administrador":
        raise ValueError("El rol Administrador siempre conserva todos los permisos")
    valid = [key for key in keys if key in PERMISSION_KEYS]
    with store.session() as con:
        _set_role_permissions(con, role_id, valid)


def create_role(name: str, description: str, keys: list[str]) -> dict:
    name = (name or "").strip()
    if len(name) < 3:
        raise ValueError("El nombre del rol debe tener al menos 3 caracteres")
    base = store.slugify(name)
    with store.session() as con:
        slug = base
        suffix = 2
        while con.execute("SELECT 1 FROM roles WHERE slug=?", (slug,)).fetchone():
            slug = f"{base}-{suffix}"
            suffix += 1
        cur = con.execute(
            "INSERT INTO roles(name, slug, description, is_system, created_at) VALUES(?,?,?,0,?)",
            (name, slug, description.strip(), store.now()),
        )
        role_id = cur.lastrowid
        _set_role_permissions(con, role_id, [key for key in keys if key in PERMISSION_KEYS])
    return get_role(role_id)  # type: ignore[return-value]


def delete_role(role_id: int) -> None:
    role = get_role(role_id)
    if not role:
        raise ValueError("Rol no encontrado")
    if role["is_system"]:
        raise ValueError("No se puede eliminar un rol del sistema")
    with store.session() as con:
        count = con.execute("SELECT COUNT(*) AS n FROM users WHERE role_id=?", (role_id,)).fetchone()["n"]
        if count:
            raise ValueError("El rol tiene usuarios asignados")
        con.execute("DELETE FROM roles WHERE id=?", (role_id,))


# ---------------------------------------------------------------- permisos
SQL_CONSOLE_ROLES = {"administrador", "desarrollador"}


def has_perm(user: dict | None, key: str) -> bool:
    return bool(user and key in user.get("permissions", set()))


def can_use_sql_console(user: dict | None) -> bool:
    """La consola SQL solo esta disponible para desarrollo y administracion."""
    return bool(
        user
        and user.get("role_slug") in SQL_CONSOLE_ROLES
        and has_perm(user, "sql.console")
    )


def require_permissions(*keys: str):
    def decorator(fn):
        @wraps(fn)
        def wrapper(*args, **kwargs):
            user = g.get("user")
            if not user:
                raise AuthRequired()
            if not any(has_perm(user, key) for key in keys):
                raise PermissionDenied("No tienes permiso para esta accion")
            return fn(*args, **kwargs)

        return wrapper

    return decorator


# ------------------------------------------------------ acceso por tablero
def access_level(user_id: int, dashboard_id: int) -> str | None:
    with store.session() as con:
        row = con.execute(
            "SELECT level FROM user_dashboard_access WHERE user_id=? AND dashboard_id=?",
            (user_id, dashboard_id),
        ).fetchone()
        return row["level"] if row else None


def set_access(user_id: int, dashboard_id: int, level: str | None, granted_by: int | None = None) -> None:
    with store.session() as con:
        if level not in {"view", "edit"}:
            con.execute(
                "DELETE FROM user_dashboard_access WHERE user_id=? AND dashboard_id=?",
                (user_id, dashboard_id),
            )
            return
        con.execute(
            "INSERT INTO user_dashboard_access(user_id, dashboard_id, level, granted_by, created_at)"
            " VALUES(?,?,?,?,?) ON CONFLICT(user_id, dashboard_id)"
            " DO UPDATE SET level=excluded.level, granted_by=excluded.granted_by",
            (user_id, dashboard_id, level, granted_by, store.now()),
        )


def access_map(user_ids: list[int] | None = None) -> dict[tuple[int, int], str]:
    query = "SELECT user_id, dashboard_id, level FROM user_dashboard_access"
    params: tuple = ()
    if user_ids:
        query += " WHERE user_id IN (" + ",".join("?" for _ in user_ids) + ")"
        params = tuple(user_ids)
    with store.session() as con:
        rows = con.execute(query, params).fetchall()
    return {(row["user_id"], row["dashboard_id"]): row["level"] for row in rows}


def can_view_dashboard(user: dict | None, dashboard_id: int) -> bool:
    if not user or not has_perm(user, "dashboards.view"):
        return False
    if has_perm(user, "dashboards.view_all"):
        return True
    return access_level(user["id"], dashboard_id) in {"view", "edit"}


def can_edit_dashboard(user: dict | None, dashboard_id: int) -> bool:
    if not user or not has_perm(user, "dashboards.design"):
        return False
    if has_perm(user, "dashboards.edit_all"):
        return True
    return access_level(user["id"], dashboard_id) == "edit"


def can_delete_dashboard(user: dict | None, dashboard_id: int) -> bool:
    return bool(user and has_perm(user, "dashboards.delete") and can_edit_dashboard(user, dashboard_id))


def dashboards_for(user: dict | None) -> list[dict]:
    if not user or not has_perm(user, "dashboards.view"):
        return []
    dashboards = store.list_dashboards()
    if has_perm(user, "dashboards.view_all"):
        for dashboard in dashboards:
            dashboard["access_level"] = "edit" if has_perm(user, "dashboards.edit_all") else "view"
            dashboard["can_edit"] = can_edit_dashboard(user, dashboard["id"])
        return dashboards
    levels = {
        key[1]: level for key, level in access_map([user["id"]]).items() if key[0] == user["id"]
    }
    result = []
    for dashboard in dashboards:
        level = levels.get(dashboard["id"])
        if not level:
            continue
        dashboard["access_level"] = level
        dashboard["can_edit"] = level == "edit" and has_perm(user, "dashboards.design")
        result.append(dashboard)
    return result


# ---------------------------------------------------------------- auditoria
def log_audit(
    action: str,
    target: str | None = None,
    detail: Any = None,
    user: dict | None = None,
    username: str | None = None,
) -> None:
    try:
        actor = user or g.get("user")
        if actor:
            user_id = actor.get("id")
            username = username or actor.get("username")
        else:
            user_id = None
        if isinstance(detail, (dict, list)):
            detail = json.dumps(detail, ensure_ascii=False)
        ip = ((request.remote_addr or "")[:64]) if request else ""
        with store.session() as con:
            con.execute(
                "INSERT INTO audit_log(user_id, username, action, target, detail, ip, created_at)"
                " VALUES(?,?,?,?,?,?,?)",
                (user_id, username, action, target, detail, ip, store.now()),
            )
    except Exception:  # noqa: BLE001 - la auditoria nunca debe romper la accion
        pass


def list_audit(username: str | None = None, action: str | None = None, limit: int = 200) -> list[dict]:
    clauses = []
    params: list[Any] = []
    if username:
        clauses.append("username LIKE ?")
        params.append(f"%{username}%")
    if action:
        clauses.append("action = ?")
        params.append(action)
    where = (" WHERE " + " AND ".join(clauses)) if clauses else ""
    params.append(max(1, min(int(limit or 200), 1000)))
    with store.session() as con:
        rows = con.execute(
            f"SELECT * FROM audit_log{where} ORDER BY id DESC LIMIT ?", tuple(params)
        ).fetchall()
        return [dict(row) for row in rows]


def audit_actions() -> list[str]:
    with store.session() as con:
        rows = con.execute("SELECT DISTINCT action FROM audit_log ORDER BY action").fetchall()
        return [row["action"] for row in rows]


# --------------------------------------------------------------------- CSRF
def ensure_csrf() -> str:
    if not session.get("csrf"):
        session["csrf"] = secrets.token_urlsafe(32)
    return session["csrf"]


def csrf_token() -> str:
    return ensure_csrf()


def validate_csrf() -> bool:
    supplied = request.headers.get("X-CSRF-Token") or request.form.get("csrf_token")
    expected = session.get("csrf")
    if not expected or not supplied:
        return False
    return secrets.compare_digest(str(expected), str(supplied))


def login_user(user: dict) -> None:
    session.clear()
    session["user_id"] = user["id"]
    session["csrf"] = secrets.token_urlsafe(32)
    session.permanent = True


def logout_user() -> None:
    session.clear()
