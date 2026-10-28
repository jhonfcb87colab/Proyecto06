"""Aplicacion Flask: capa de autoria (design) + capa de visualizacion (view)."""
from __future__ import annotations

import os
from datetime import timedelta
from functools import wraps
from typing import Any

from flask import Flask, abort, flash, g, jsonify, redirect, render_template, request, session, url_for
from werkzeug.exceptions import HTTPException

from . import auth, model, store
from . import imports as importers
from .admin import bp as admin_bp
from .analytics import CHART_TYPES, build_chart_data, empty_chart, infer_fields
from .model import ModelError
from .config import (
    DESIGN_ENABLED,
    DESIGN_TOKEN,
    IMPORTED_DB,
    MAX_QUERY_ROWS,
    MAX_UPLOAD_BYTES,
    SECRET_KEY,
    SESSION_COOKIE_SECURE,
)
from .data_sources import (
    AppError,
    SUPPORTED_KINDS,
    canonical_kind,
    execute_sql,
    introspect,
    normalize_config,
    public_connection,
    run_query,
    test_connection,
)
from .seed import seed_metadata

CONFIG_KEYS = {
    "x",
    "y",
    "series",
    "agg",
    "limit",
    "sort",
    "format",
    "currency",
    "decimals",
    "label",
    "color",
    "size",
    "lat",
    "lon",
    "max",
    "target",
    "question",
    "field",
    "text",
    "url",
    "nav_label",
    "nav_url",
    "tooltip",
    "label_field",
    "model_item_id",
}
WIDGET_NAMES = {
    "table": "Tabla",
    "matrix": "Matriz",
    "card": "Tarjeta",
    "kpi": "Tarjeta KPI",
    "multi_row": "Tarjeta de varias filas",
    "decomposition": "Desglose jerarquico",
    "bar": "Barras",
    "bar_grouped": "Barras agrupadas",
    "bar_stacked": "Barras apiladas",
    "bar_100": "Barras 100% apiladas",
    "column_grouped": "Columnas agrupadas",
    "column_stacked": "Columnas apiladas",
    "column_100": "Columnas 100% apiladas",
    "combo": "Columnas y lineas combinado",
    "line": "Linea",
    "area": "Area",
    "area_stacked": "Area apilada",
    "scatter": "Dispersion",
    "bubble": "Burbujas",
    "waterfall": "Cascada",
    "funnel": "Embudo",
    "pie": "Circular",
    "doughnut": "Anillos",
    "treemap": "Rectangulos",
    "gauge": "Indicador",
    "pareto": "Pareto",
    "decomp_tree": "Arbol de descomposicion",
    "key_influencers": "Influenciadores clave",
    "qna": "Preguntas y respuestas",
    "correlation": "Matriz de correlacion",
    "map_basic": "Mapa basico",
    "map_choropleth": "Mapa coropletico",
    "map_bubble": "Mapa de burbujas",
    "map_arcgis": "Mapa ArcGIS",
    "slicer": "Segmentador de datos",
    "nav_buttons": "Botones de navegacion",
    "bookmark": "Marcadores",
    "tooltip": "Informacion sobre herramientas",
    "filter_panel": "Panel de filtros",
}
STANDALONE_WIDGETS = {"nav_buttons", "bookmark", "tooltip"}

MODEL_KINDS = {
    "measure": "Medida",
    "column": "Columna calculada",
    "table_calc": "Tabla calculada",
    "table_created": "Tabla creada",
}
CHART_GROUPS = [
    ("Tablas y tarjetas", ["table", "matrix", "card", "kpi", "multi_row", "decomposition"]),
    (
        "Barras y columnas",
        [
            "bar_grouped",
            "bar_stacked",
            "bar_100",
            "column_grouped",
            "column_stacked",
            "column_100",
            "combo",
        ],
    ),
    (
        "Tendencias y distribucion",
        ["line", "area", "area_stacked", "scatter", "bubble", "waterfall", "funnel", "pie", "doughnut", "treemap", "gauge"],
    ),
    ("Analisis avanzados", ["pareto", "decomp_tree", "key_influencers", "qna", "correlation"]),
    ("Mapas y geolocalizacion", ["map_basic", "map_choropleth", "map_bubble", "map_arcgis"]),
    (
        "Interactividad y navegacion",
        ["slicer", "nav_buttons", "bookmark", "tooltip", "filter_panel"],
    ),
]


def _json_body() -> dict:
    data = request.get_json(silent=True)
    if not isinstance(data, dict):
        raise AppError("Se esperaba un objeto JSON", status=400)
    return data


def _is_api() -> bool:
    return request.path.startswith("/api/")


def _safe_next(target: str | None) -> str:
    if target and target.startswith("/") and not target.startswith("//") and "\\" not in target:
        return target
    return url_for("index")


def _current_mode() -> str:
    mode = (request.headers.get("X-BI-Mode") or request.args.get("mode") or "").lower()
    if mode not in {"design", "view"}:
        mode = "view"
    return mode


def require_design(fn):
    @wraps(fn)
    def wrapper(*args, **kwargs):
        if not DESIGN_ENABLED:
            raise AppError("El modo diseno esta deshabilitado en el servidor", 403, "design_disabled")
        explicit = (request.headers.get("X-BI-Mode") or request.args.get("mode") or "").lower()
        if explicit != "design":
            raise AppError("Cambia a modo diseno para editar", 403, "view_mode")
        if DESIGN_TOKEN and request.headers.get("X-Design-Token", "") != DESIGN_TOKEN:
            raise AppError("Token de diseno requerido o invalido", 403, "design_token")
        return fn(*args, **kwargs)

    return wrapper


def require_design_access(fn):
    """Protege lecturas de autoria (SQL, esquemas, conexiones)."""
    @wraps(fn)
    def wrapper(*args, **kwargs):
        if not DESIGN_ENABLED:
            raise AppError("El modo diseno esta deshabilitado en el servidor", 403, "design_disabled")
        if DESIGN_TOKEN and request.headers.get("X-Design-Token", "") != DESIGN_TOKEN:
            raise AppError("Token de diseno requerido o invalido", 403, "design_token")
        return fn(*args, **kwargs)

    return wrapper


def _int(value: Any, default: int | None = None) -> int | None:
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def _parse_widget(payload: dict) -> dict:
    chart_type = str(payload.get("chart_type") or "bar").lower()
    if chart_type not in CHART_TYPES:
        raise AppError(f"Tipo de grafico no soportado: {chart_type}")
    dataset_id = _int(payload.get("dataset_id"), None)
    if dataset_id is not None:
        if not auth.has_perm(g.user, "datasets.view"):
            raise auth.PermissionDenied("No tienes permiso para usar datasets")
        if not store.get_dataset(dataset_id):
            raise AppError("El dataset indicado no existe", status=404)
    config_raw = payload.get("config") or {}
    if not isinstance(config_raw, dict):
        raise AppError("config debe ser un objeto")
    config = {}
    for key in CONFIG_KEYS:
        if key in config_raw:
            config[key] = config_raw[key]
    model_id = _int(config.get("model_item_id"), None)
    if model_id:
        model_item = store.get_model_item(model_id)
        if not model_item:
            raise AppError("El modelo indicado no existe", status=404)
        if dataset_id is not None and model_item["dataset_id"] != dataset_id:
            raise AppError("El modelo pertenece a otro dataset")
        if dataset_id is None:
            dataset_id = model_item["dataset_id"]
            if not store.get_dataset(dataset_id):
                raise AppError("El dataset del modelo ya no existe", status=404)
            if not auth.has_perm(g.user, "datasets.view"):
                raise auth.PermissionDenied("No tienes permiso para usar datasets")
        config["model_item_id"] = model_id
    else:
        config.pop("model_item_id", None)
    if "limit" in config:
        config["limit"] = max(0, min(_int(config["limit"], 0) or 0, MAX_QUERY_ROWS))
    if "decimals" in config:
        config["decimals"] = max(0, min(_int(config["decimals"], 0) or 0, 6))
    title = str(payload.get("title") or "").strip() or WIDGET_NAMES.get(chart_type, "Widget")
    w = max(1, min(_int(payload.get("w"), 3) or 3, 12))
    h = max(1, min(_int(payload.get("h"), 2) or 2, 6))
    x = _int(payload.get("x"), None)
    y = _int(payload.get("y"), None)
    if x is not None:
        x = max(0, min(x, 12 - w))
    if y is not None:
        y = max(0, min(y, 999))
    return {
        "dataset_id": dataset_id,
        "title": title,
        "chart_type": chart_type,
        "config": config,
        "x": x,
        "y": y,
        "w": w,
        "h": h,
    }


def _preview(connection_id: int, sql: str, limit: int = 100) -> dict:
    connection = store.get_connection(connection_id)
    if not connection:
        raise AppError("Conexion no encontrada", status=404)
    result = run_query(connection, sql, limit=limit)
    return {
        "columns": result["columns"],
        "rows": result["rows"],
        "fields": infer_fields(result["columns"], result["rows"]),
        "truncated": result["truncated"],
        "elapsed_ms": result["elapsed_ms"],
    }


def _model_dataset(dataset_id: int, limit: int = MAX_QUERY_ROWS) -> tuple[dict, dict, dict]:
    dataset = store.get_dataset(dataset_id)
    if not dataset:
        raise AppError("Dataset no encontrado", status=404)
    if not auth.has_perm(g.user, "datasets.view"):
        raise auth.PermissionDenied("No tienes permiso para usar datasets")
    connection = store.get_connection(dataset["connection_id"])
    if not connection:
        raise AppError("La conexion del dataset ya no existe", status=404)
    result = run_query(connection, dataset["sql"], limit=limit)
    return dataset, connection, result


IMPORTED_CONNECTION_NAME = "Datos importados"


def _imported_connection() -> dict:
    for connection in store.list_connections():
        if connection["name"] == IMPORTED_CONNECTION_NAME:
            return connection
    return store.create_connection(
        IMPORTED_CONNECTION_NAME,
        "sqlite",
        {"path": str(IMPORTED_DB)},
    )


def _sync_imported_dataset(table: str, display_name: str | None = None) -> dict:
    connection = _imported_connection()
    sql = importers.dataset_sql(table)
    name = (display_name or table).strip()[:80] or table
    preview = _preview(connection["id"], sql, limit=20)
    existing = next((d for d in store.list_datasets() if d["name"] == name), None)
    if existing and existing["connection_id"] == connection["id"]:
        return store.update_dataset(existing["id"], connection["id"], name, sql, preview["fields"])
    if existing:
        suffix = 2
        original = name
        while any(d["name"] == name for d in store.list_datasets()):
            name = f"{original} ({suffix})"
            suffix += 1
    return store.create_dataset(connection["id"], name, sql, preview["fields"])


def _require_dashboard_view(dashboard_id: int) -> dict:
    dashboard = store.get_dashboard(dashboard_id)
    if not dashboard or not auth.can_view_dashboard(g.get("user"), dashboard_id):
        abort(404)
    return dashboard


def _require_dashboard_edit(dashboard_id: int) -> dict:
    dashboard = store.get_dashboard(dashboard_id)
    if not dashboard:
        raise AppError("Dashboard no encontrado", status=404)
    if not auth.can_edit_dashboard(g.get("user"), dashboard_id):
        raise auth.PermissionDenied("No tienes permiso para editar este tablero")
    return dashboard


def _load_design_data(dashboard_id: int) -> tuple[dict, list[dict], dict[int, dict]]:
    dashboard = _require_dashboard_edit(dashboard_id)
    all_datasets = store.list_datasets()
    return dashboard, all_datasets, {d["id"]: d for d in all_datasets}


def _design_payload(dashboard_id: int) -> dict:
    dashboard, datasets, by_id = _load_design_data(dashboard_id)
    widgets = store.list_widgets(dashboard_id)
    rendered = _render_widgets_with(widgets, by_id)
    return {
        "mode": "design",
        "dashboard": dashboard,
        "widgets": rendered,
        "datasets": datasets if auth.has_perm(g.user, "datasets.view") else [],
        "connections": (
            [public_connection(c) for c in store.list_connections()]
            if auth.has_perm(g.user, "connections.view")
            else []
        ),
        "chart_types": list(WIDGET_NAMES.items()),
        "chart_groups": [
            {
                "name": name,
                "types": [{"value": value, "label": WIDGET_NAMES.get(value, value)} for value in values],
            }
            for name, values in CHART_GROUPS
        ],
        "model_kinds": list(MODEL_KINDS.items()),
        "model_items": store.list_model_items()
        if auth.has_perm(g.user, "dashboards.design") and auth.has_perm(g.user, "datasets.view")
        else [],
        "table_aliases": store.list_table_aliases()
        if auth.has_perm(g.user, "connections.view")
        else [],
        "api_scripts": store.list_api_scripts()
        if auth.has_perm(g.user, "import.api")
        else [],
        "import_formats": [".csv", ".tsv", ".parquet"],
        "can_import_api": auth.has_perm(g.user, "import.api"),
        "can_manage_connections": auth.has_perm(g.user, "connections.manage"),
        "can_manage_datasets": auth.has_perm(g.user, "datasets.manage"),
        "design_token_required": bool(DESIGN_TOKEN),
    }


def _render_payload(dashboard_id: int) -> dict:
    dashboard = _require_dashboard_view(dashboard_id)
    datasets = store.list_datasets()
    by_id = {d["id"]: d for d in datasets}
    widgets = store.list_widgets(dashboard_id)
    return {
        "mode": "view",
        "dashboard": dashboard,
        "widgets": _render_widgets_with(widgets, by_id),
        "design_enabled": DESIGN_ENABLED,
        "generated_at": store.now(),
    }


def _apply_model_item(item: dict, result: dict) -> dict:
    kind = item.get("kind")
    expression = item.get("expression") or ""
    config = item.get("config") or {}
    if kind == "measure":
        value = model.evaluate(expression, result["rows"])
        return {"columns": [item["name"]], "rows": [{item["name"]: value}], "truncated": False, "elapsed_ms": 0}
    preview = model.preview(
        kind,
        expression,
        result["rows"],
        result["columns"],
        config,
        limit=MAX_QUERY_ROWS,
    )
    return {
        "columns": preview.get("columns") or [],
        "rows": preview.get("rows") or [],
        "truncated": preview.get("truncated", False),
        "elapsed_ms": result.get("elapsed_ms", 0),
    }


def _render_widgets_with(widgets: list[dict], datasets_by_id: dict[int, dict]) -> list[dict]:
    cache: dict[int, dict] = {}
    model_cache: dict[int, dict] = {}
    connections: dict[int, dict] = {}
    out = []
    for widget in widgets:
        dataset_id = widget.get("dataset_id")
        chart = None
        dataset = datasets_by_id.get(dataset_id) if dataset_id else None
        if dataset is None and widget.get("chart_type") in STANDALONE_WIDGETS:
            chart = build_chart_data(widget, {"rows": [], "columns": []})
        elif dataset is None:
            chart = empty_chart(widget, "El widget no tiene dataset valido")
        else:
            if dataset["connection_id"] not in connections:
                connections[dataset["connection_id"]] = store.get_connection(dataset["connection_id"])
            connection = connections.get(dataset["connection_id"])
            if not connection:
                chart = empty_chart(widget, "Conexion no encontrada")
            else:
                if dataset_id not in cache:
                    try:
                        cache[dataset_id] = run_query(connection, dataset["sql"], limit=MAX_QUERY_ROWS)
                    except AppError as exc:
                        cache[dataset_id] = {"error": exc.message}
                result = cache[dataset_id]
                if "error" in result:
                    chart = empty_chart(widget, result["error"])
                else:
                    model_id = (widget.get("config") or {}).get("model_item_id")
                    if model_id:
                        model_id = _int(model_id, None)
                        if model_id and model_id not in model_cache:
                            model_item = store.get_model_item(model_id)
                            if not model_item or model_item.get("dataset_id") != dataset_id:
                                model_cache[model_id] = {"error": "El modelo aplicado ya no esta disponible"}
                            else:
                                try:
                                    model_cache[model_id] = _apply_model_item(model_item, result)
                                except Exception as exc:  # noqa: BLE001
                                    model_cache[model_id] = {"error": f"Error en el modelo: {exc}"}
                        if model_id:
                            result = model_cache[model_id]
                    if "error" in result:
                        chart = empty_chart(widget, result["error"])
                    else:
                        chart = build_chart_data(widget, result)
        if isinstance(chart, dict):
            chart["dataset_id"] = dataset_id
        item = dict(widget)
        item["dataset_name"] = dataset.get("name") if dataset else None
        item["chart_data"] = chart
        out.append(item)
    return out


def create_app() -> Flask:
    app = Flask(__name__)
    app.config["JSON_SORT_KEYS"] = False
    app.config["MAX_CONTENT_LENGTH"] = MAX_UPLOAD_BYTES
    app.config["SECRET_KEY"] = SECRET_KEY
    app.config["PERMANENT_SESSION_LIFETIME"] = timedelta(hours=12)
    app.config["SESSION_COOKIE_HTTPONLY"] = True
    app.config["SESSION_COOKIE_SAMESITE"] = "Lax"
    app.config["SESSION_COOKIE_SECURE"] = SESSION_COOKIE_SECURE

    store.init_db()
    try:
        seed_metadata()
    except Exception:  # noqa: BLE001
        app.logger.exception("No se pudo sembrar el dashboard demo")
    try:
        auth_seed = auth.seed_auth()
        if auth_seed["users"]:
            app.logger.warning(
                "Usuarios iniciales creados: %s. Cambia las contrasenas por defecto.",
                ", ".join(item["username"] for item in auth_seed["users"]),
            )
    except Exception:  # noqa: BLE001
        app.logger.exception("No se pudo inicializar la autenticacion")

    app.register_blueprint(admin_bp)

    @app.after_request
    def _headers(response):
        if request.path.startswith("/api/"):
            response.headers["Cache-Control"] = "no-store"
        response.headers.setdefault("X-Content-Type-Options", "nosniff")
        response.headers.setdefault("X-Frame-Options", "SAMEORIGIN")
        response.headers.setdefault("Referrer-Policy", "same-origin")
        return response

    @app.before_request
    def _auth_guard():
        g.user = None
        user_id = session.get("user_id")
        if user_id is not None:
            try:
                user = auth.get_user_by_id(int(user_id))
            except (TypeError, ValueError):
                user = None
            if user and user["is_active"]:
                g.user = user
            else:
                session.clear()

        endpoint = request.endpoint or ""
        if endpoint == "static":
            return None
        if endpoint == "health":
            return None
        if endpoint == "login":
            auth.ensure_csrf()
            if request.method == "POST" and not auth.validate_csrf():
                abort(400, description="Token CSRF invalido o ausente")
            return None
        if not g.user:
            if _is_api():
                return jsonify(error="Inicia sesion para continuar", code="auth_required"), 401
            return redirect(url_for("login", next=request.full_path if request.query_string else request.path))
        auth.ensure_csrf()
        if request.method in {"POST", "PUT", "PATCH", "DELETE"} and not auth.validate_csrf():
            if _is_api():
                return jsonify(error="Token CSRF invalido o ausente", code="csrf"), 403
            abort(400, description="Token CSRF invalido o ausente")
        return None

    @app.context_processor
    def _inject_auth():
        user = g.get("user")
        return {
            "current_user": user,
            "csrf_token": auth.csrf_token,
            "can": lambda key: auth.has_perm(user, key),
        }

    @app.errorhandler(auth.AuthRequired)
    def _auth_required(exc: auth.AuthRequired):
        if _is_api():
            return jsonify(error="Inicia sesion para continuar", code="auth_required"), 401
        return redirect(url_for("login", next=request.full_path if request.query_string else request.path))

    @app.errorhandler(auth.PermissionDenied)
    def _permission_denied(exc: auth.PermissionDenied):
        if _is_api():
            return jsonify(error=str(exc) or "Acceso denegado", code="forbidden"), 403
        return render_template("error.html", code=403, message=str(exc) or "Acceso denegado"), 403

    @app.errorhandler(AppError)
    def _app_error(exc: AppError):
        return jsonify(error=exc.message, code=exc.code), exc.status

    @app.errorhandler(Exception)
    def _unexpected(exc: Exception):
        if isinstance(exc, HTTPException):
            if _is_api():
                return jsonify(error=exc.description, code=exc.name.lower()), exc.code
            if exc.code in {400, 404, 405}:
                return (
                    render_template(
                        "error.html",
                        code=exc.code,
                        message="Pagina no encontrada" if exc.code == 404 else exc.description,
                    ),
                    exc.code,
                )
            return exc
        app.logger.exception("Error no controlado")
        if _is_api():
            return jsonify(error="Error interno del servidor", code="internal"), 500
        return render_template("error.html", code=500, message="Error interno del servidor"), 500

    # ------------------------------------------------------ sesion / cuenta
    @app.route("/login", methods=["GET", "POST"])
    def login():
        if g.user and request.method == "GET":
            return redirect(_safe_next(request.args.get("next")))
        target = request.values.get("next", "")
        username = ""
        error = None
        if request.method == "POST":
            username = str(request.form.get("username") or "").strip()
            password = request.form.get("password") or ""
            user = auth.authenticate(username, password)
            if not user:
                auth.log_audit("login_failed", target=username, username=username, detail="credenciales invalidas")
                error = "Usuario o contrasena incorrectos."
            else:
                auth.login_user(user)
                auth.log_audit("login", user=user)
                return redirect(_safe_next(target))
        return render_template("login.html", next=target, username=username, error=error), (401 if error else 200)

    @app.post("/logout")
    def logout():
        auth.log_audit("logout")
        auth.logout_user()
        flash("Sesion cerrada.", "info")
        return redirect(url_for("login"))

    @app.route("/account", methods=["GET", "POST"])
    def account():
        if request.method == "POST":
            current = request.form.get("current_password") or ""
            new = request.form.get("new_password") or ""
            confirm = request.form.get("confirm_password") or ""
            if new != confirm:
                flash("La confirmacion no coincide.", "error")
            else:
                try:
                    auth.change_own_password(g.user, current, new)
                except ValueError as exc:
                    flash(str(exc), "error")
                else:
                    auth.log_audit("account.password")
                    flash("Contrasena actualizada.", "info")
                    return redirect(url_for("account"))
        return render_template("account.html")

    # ---------------------------------------------------------------- vistas
    @app.get("/")
    def index():
        dashboards = auth.dashboards_for(g.user)
        return render_template(
            "index.html",
            dashboards=dashboards,
            connection_count=len(store.list_connections()) if auth.has_perm(g.user, "connections.view") else 0,
            dataset_count=len(store.list_datasets()) if auth.has_perm(g.user, "datasets.view") else 0,
            design_enabled=DESIGN_ENABLED,
            token_required=bool(DESIGN_TOKEN),
            can_create=auth.has_perm(g.user, "dashboards.create"),
            can_import=auth.has_perm(g.user, "connections.manage"),
            can_design_any=any(d.get("can_edit") for d in dashboards),
        )

    @app.get("/view/<int:dashboard_id>")
    def dashboard_only_view(dashboard_id: int):
        dashboard = _require_dashboard_view(dashboard_id)
        return render_template(
            "view.html",
            dashboard=dashboard,
            design_enabled=DESIGN_ENABLED,
        )

    @app.get("/d/<int:dashboard_id>")
    def dashboard_view(dashboard_id: int):
        dashboard = _require_dashboard_view(dashboard_id)
        can_edit = auth.can_edit_dashboard(g.user, dashboard_id)
        mode = _current_mode()
        if mode == "design" and (not DESIGN_ENABLED or not can_edit):
            mode = "view"
        return render_template(
            "dashboard.html",
            dashboard=dashboard,
            initial_mode=mode,
            design_enabled=DESIGN_ENABLED,
            token_required=bool(DESIGN_TOKEN),
            can_edit=can_edit,
        )

    @app.get("/console")
    def sql_console():
        if not auth.can_use_sql_console(g.user):
            raise auth.PermissionDenied(
                "La consola SQL solo esta disponible para los roles Desarrollo y Administrador"
            )
        if not DESIGN_ENABLED:
            return (
                render_template(
                    "error.html",
                    code=403,
                    message="El modo diseno esta deshabilitado en el servidor",
                ),
                403,
            )
        return render_template(
            "console.html",
            design_enabled=DESIGN_ENABLED,
            token_required=bool(DESIGN_TOKEN),
        )

    # ------------------------------------------------------------------- API
    @app.get("/api/health")
    def health():
        return jsonify(ok=True, design_enabled=DESIGN_ENABLED)

    @app.get("/api/state")
    def state():
        mode = _current_mode()
        payload: dict = {
            "mode": mode,
            "design_enabled": DESIGN_ENABLED,
            "design_token_required": bool(DESIGN_TOKEN),
            "dashboards": auth.dashboards_for(g.user),
            "user": {
                "username": g.user["username"],
                "full_name": g.user["full_name"],
                "role": g.user["role_slug"],
                "role_name": g.user["role_name"],
                "permissions": sorted(g.user["permissions"]),
            },
        }
        if mode == "design":
            if DESIGN_TOKEN and request.headers.get("X-Design-Token", "") != DESIGN_TOKEN:
                raise AppError("Token de diseno requerido o invalido", 403, "design_token")
            if auth.has_perm(g.user, "connections.view"):
                payload["connections"] = [public_connection(c) for c in store.list_connections()]
            if auth.has_perm(g.user, "datasets.view"):
                payload["datasets"] = store.list_datasets()
        return jsonify(payload)

    # ------------------------------------------------------------ conexiones
    @app.get("/api/connections")
    @auth.require_permissions("connections.view")
    @require_design_access
    def connections_list():
        return jsonify([public_connection(c) for c in store.list_connections()])

    @app.post("/api/connections")
    @auth.require_permissions("connections.manage")
    @require_design
    def connections_create():
        body = _json_body()
        name = str(body.get("name") or "").strip()
        kind = canonical_kind(body.get("kind"))
        if not name:
            raise AppError("El nombre de la conexion es obligatorio")
        config = normalize_config(kind, body.get("config"))
        try:
            row = store.create_connection(name, kind, config)
        except Exception as exc:  # noqa: BLE001
            if "UNIQUE" in str(exc):
                raise AppError("Ya existe una conexion con ese nombre", status=409) from exc
            raise
        auth.log_audit("connection.create", target=row["name"], detail={"id": row["id"], "kind": row["kind"]})
        return jsonify(public_connection(row)), 201

    @app.put("/api/connections/<int:connection_id>")
    @auth.require_permissions("connections.manage")
    @require_design
    def connections_update(connection_id: int):
        current = store.get_connection(connection_id)
        if not current:
            raise AppError("Conexion no encontrada", status=404)
        body = _json_body()
        name = str(body.get("name") or current["name"]).strip()
        kind = canonical_kind(body.get("kind") or current["kind"])
        incoming = dict(current.get("config") or {})
        incoming.update(body.get("config") or {})
        for key, value in (current.get("config") or {}).items():
            if incoming.get(key) == "********":
                incoming[key] = value
        config = normalize_config(kind, incoming)
        row = store.update_connection(connection_id, name, kind, config)
        auth.log_audit("connection.update", target=name, detail={"id": connection_id, "kind": kind})
        return jsonify(public_connection(row))

    @app.delete("/api/connections/<int:connection_id>")
    @auth.require_permissions("connections.manage")
    @require_design
    def connections_delete(connection_id: int):
        current = store.get_connection(connection_id)
        if not current:
            raise AppError("Conexion no encontrada", status=404)
        auth.log_audit("connection.delete", target=current["name"], detail={"id": connection_id})
        store.delete_connection(connection_id)
        return jsonify(ok=True)

    @app.post("/api/connections/test")
    @auth.require_permissions("connections.manage")
    @require_design
    def connections_test():
        body = _json_body()
        if body.get("id"):
            connection = store.get_connection(_int(body["id"], 0) or 0)
            if not connection:
                raise AppError("Conexion no encontrada", status=404)
            kind = str(body.get("kind") or connection["kind"]).strip().lower()
            stored = connection.get("config") or {}
            config = dict(body.get("config") or stored)
            for key, value in stored.items():
                if config.get(key) == "********":
                    config[key] = value
        else:
            kind = str(body.get("kind") or "").strip().lower()
            config = body.get("config") or {}
        return jsonify(test_connection(kind, config))

    @app.get("/api/connections/<int:connection_id>/tables")
    @auth.require_permissions("connections.view")
    @require_design_access
    def connections_tables(connection_id: int):
        connection = store.get_connection(connection_id)
        if not connection:
            raise AppError("Conexion no encontrada", status=404)
        return jsonify({"tables": introspect(connection)})

    @app.post("/api/connections/import")
    @auth.require_permissions("connections.manage")
    @require_design
    def connections_import():
        body = request.get_json(silent=True)
        if isinstance(body, list):
            items = body
        elif isinstance(body, dict):
            items = body.get("connections")
            if items is None and body.get("kind"):
                items = [body]
        else:
            items = None
        if not isinstance(items, list) or not items:
            raise AppError("Envia {'connections': [...]} con al menos una conexion")
        created, updated, failed = [], [], []
        for item in items:
            try:
                if not isinstance(item, dict):
                    raise AppError("Cada conexion debe ser un objeto")
                name = str(item.get("name") or "").strip()
                kind = canonical_kind(item.get("kind"))
                if not name:
                    raise AppError("Cada conexion necesita nombre")
                if kind not in SUPPORTED_KINDS:
                    raise AppError(f"Tipo no soportado: {kind}")
                config = normalize_config(kind, item.get("config"))
                existing = next((c for c in store.list_connections() if c["name"] == name), None)
                if existing:
                    row = store.update_connection(existing["id"], name, kind, config)
                    updated.append(public_connection(row))
                else:
                    row = store.create_connection(name, kind, config)
                    created.append(public_connection(row))
            except AppError as exc:
                failed.append({"name": item.get("name") if isinstance(item, dict) else None, "error": exc.message})
            except Exception as exc:  # noqa: BLE001
                failed.append({"name": item.get("name") if isinstance(item, dict) else None, "error": str(exc)})
        auth.log_audit(
            "connection.import",
            detail={"created": len(created), "updated": len(updated), "failed": len(failed)},
        )
        return jsonify(created=created, updated=updated, failed=failed)

    # --------------------------------------------------------------- datasets
    @app.get("/api/datasets")
    @auth.require_permissions("datasets.view")
    @require_design_access
    def datasets_list():
        return jsonify(store.list_datasets())

    @app.post("/api/datasets")
    @auth.require_permissions("datasets.manage")
    @require_design
    def datasets_create():
        body = _json_body()
        connection_id = _int(body.get("connection_id"), None)
        if not connection_id:
            raise AppError("connection_id es obligatorio")
        name = str(body.get("name") or "").strip()
        sql = str(body.get("sql") or "").strip()
        if not name or not sql:
            raise AppError("Nombre y SQL son obligatorios")
        preview = _preview(connection_id, sql)
        row = store.create_dataset(connection_id, name, sql, preview["fields"])
        auth.log_audit("dataset.create", target=name, detail={"id": row["id"]})
        return jsonify(row), 201

    @app.put("/api/datasets/<int:dataset_id>")
    @auth.require_permissions("datasets.manage")
    @require_design
    def datasets_update(dataset_id: int):
        current = store.get_dataset(dataset_id)
        if not current:
            raise AppError("Dataset no encontrado", status=404)
        body = _json_body()
        connection_id = _int(body.get("connection_id"), current["connection_id"])
        name = str(body.get("name") or current["name"]).strip()
        sql = str(body.get("sql") or current["sql"]).strip()
        preview = _preview(connection_id, sql)
        row = store.update_dataset(dataset_id, connection_id, name, sql, preview["fields"])
        auth.log_audit("dataset.update", target=name, detail={"id": dataset_id})
        return jsonify(row)

    @app.delete("/api/datasets/<int:dataset_id>")
    @auth.require_permissions("datasets.manage")
    @require_design
    def datasets_delete(dataset_id: int):
        dataset = store.get_dataset(dataset_id)
        if not dataset:
            raise AppError("Dataset no encontrado", status=404)
        auth.log_audit("dataset.delete", target=dataset["name"], detail={"id": dataset_id})
        store.delete_dataset(dataset_id)
        return jsonify(ok=True)

    @app.post("/api/datasets/preview")
    @auth.require_permissions("datasets.manage")
    @require_design
    def datasets_preview():
        body = _json_body()
        if body.get("dataset_id"):
            dataset = store.get_dataset(_int(body["dataset_id"], 0) or 0)
            if not dataset:
                raise AppError("Dataset no encontrado", status=404)
            connection_id, sql = dataset["connection_id"], dataset["sql"]
        else:
            connection_id = _int(body.get("connection_id"), None)
            sql = str(body.get("sql") or "").strip()
        if not connection_id or not sql:
            raise AppError("Indica connection_id y sql")
        limit = max(1, min(_int(body.get("limit"), 50) or 50, 500))
        return jsonify(_preview(connection_id, sql, limit=limit))

    # --------------------------------------------------------- consola SQL
    @app.post("/api/sql/execute")
    @require_design
    def sql_execute():
        if not auth.can_use_sql_console(g.user):
            raise auth.PermissionDenied(
                "La consola SQL solo esta disponible para los roles Desarrollo y Administrador"
            )
        body = _json_body()
        connection_id = _int(body.get("connection_id"), None)
        if not connection_id:
            raise AppError("Indica connection_id")
        connection = store.get_connection(connection_id)
        if not connection:
            raise AppError("Conexion no encontrada", status=404)
        sql = str(body.get("sql") or "").strip()
        if not sql:
            raise AppError("Escribe el codigo SQL a ejecutar")
        mode = str(body.get("mode") or "read").strip().lower()
        if mode not in {"read", "write"}:
            raise AppError("mode debe ser read o write")
        limit = max(1, min(_int(body.get("limit"), 200) or 200, MAX_QUERY_ROWS))
        result = execute_sql(connection, sql, mode=mode, limit=limit)
        auth.log_audit(
            "sql.execute",
            target=connection["name"],
            detail={
                "connection_id": connection_id,
                "kind": connection["kind"],
                "mode": mode,
                "statements": result["statement_count"],
                "committed": result["committed"],
                "sql": sql[:800],
            },
        )
        return jsonify(result)

    # ------------------------------------------------------- modelado Python
    def _model_body() -> dict:
        body = _json_body()
        kind = str(body.get("kind") or "").strip().lower()
        if kind not in MODEL_KINDS:
            raise AppError("kind debe ser measure, column, table_calc o table_created")
        dataset_id = _int(body.get("dataset_id"), None)
        if not dataset_id:
            raise AppError("dataset_id es obligatorio")
        expression = str(body.get("expression") or "").strip()
        if kind != "table_created" and not expression:
            raise AppError("La expresion Python es obligatoria")
        if kind != "table_created":
            try:
                model.validate_expression(expression)
            except ModelError as exc:
                raise AppError(str(exc)) from exc
        config = body.get("config") or {}
        if not isinstance(config, dict):
            raise AppError("config debe ser un objeto")
        return {
            "kind": kind,
            "dataset_id": dataset_id,
            "expression": expression,
            "config": config,
        }

    @app.get("/api/model/items")
    @auth.require_permissions("dashboards.design")
    @require_design
    def model_items_list():
        if not auth.has_perm(g.user, "datasets.view"):
            raise auth.PermissionDenied("No tienes permiso para usar datasets")
        kind = (request.args.get("kind") or "").strip().lower() or None
        if kind and kind not in MODEL_KINDS:
            raise AppError("Tipo de modelo no soportado")
        dataset_id = _int(request.args.get("dataset_id"), None)
        return jsonify({"items": store.list_model_items(kind=kind, dataset_id=dataset_id), "kinds": list(MODEL_KINDS.items())})

    @app.post("/api/model/items")
    @auth.require_permissions("dashboards.design")
    @require_design
    def model_items_create():
        body = _json_body()
        payload = _model_body()
        name = str(body.get("name") or "").strip()
        if not name:
            raise AppError("El nombre es obligatorio")
        dataset, connection, _ = _model_dataset(payload["dataset_id"], limit=1)
        row = store.create_model_item(
            kind=payload["kind"],
            name=name,
            expression=payload["expression"],
            dataset_id=dataset["id"],
            connection_id=connection["id"],
            config=payload["config"],
        )
        auth.log_audit(
            "model.create",
            target=name,
            detail={"id": row["id"], "kind": payload["kind"], "dataset_id": dataset["id"]},
        )
        return jsonify(row), 201

    @app.put("/api/model/items/<int:item_id>")
    @auth.require_permissions("dashboards.design")
    @require_design
    def model_items_update(item_id: int):
        current = store.get_model_item(item_id)
        if not current:
            raise AppError("Elemento de modelo no encontrado", status=404)
        body = _json_body()
        payload = _model_body()
        name = str(body.get("name") or current["name"]).strip()
        dataset, connection, _ = _model_dataset(payload["dataset_id"], limit=1)
        row = store.update_model_item(
            item_id,
            kind=payload["kind"],
            name=name,
            expression=payload["expression"],
            dataset_id=dataset["id"],
            connection_id=connection["id"],
            config=payload["config"],
        )
        auth.log_audit("model.update", target=name, detail={"id": item_id, "kind": payload["kind"]})
        return jsonify(row)

    @app.delete("/api/model/items/<int:item_id>")
    @auth.require_permissions("dashboards.design")
    @require_design
    def model_items_delete(item_id: int):
        if not auth.has_perm(g.user, "datasets.view"):
            raise auth.PermissionDenied("No tienes permiso para usar datasets")
        current = store.get_model_item(item_id)
        if not current:
            raise AppError("Elemento de modelo no encontrado", status=404)
        auth.log_audit("model.delete", target=current["name"], detail={"id": item_id})
        store.delete_model_item(item_id)
        return jsonify(ok=True)

    @app.post("/api/model/preview")
    @auth.require_permissions("dashboards.design")
    @require_design
    def model_preview():
        body = _json_body()
        payload = _model_body()
        limit = max(1, min(_int(body.get("limit"), 50) or 50, 500))
        dataset, _, result = _model_dataset(payload["dataset_id"])
        try:
            preview = model.preview(
                payload["kind"],
                payload["expression"],
                result["rows"],
                result["columns"],
                payload["config"],
                limit=limit,
            )
        except ModelError as exc:
            raise AppError(str(exc)) from exc
        preview["dataset"] = {"id": dataset["id"], "name": dataset["name"]}
        preview["source_rows"] = len(result["rows"])
        preview["source_truncated"] = result.get("truncated", False)
        return jsonify(preview)

    @app.get("/api/model/profile")
    @auth.require_permissions("dashboards.design")
    @require_design
    def model_profile():
        dataset_id = _int(request.args.get("dataset_id"), None)
        if not dataset_id:
            raise AppError("dataset_id es obligatorio")
        dataset, _, result = _model_dataset(dataset_id)
        profile = model.profile(result["rows"], result["columns"])
        return jsonify(
            {
                "dataset": {"id": dataset["id"], "name": dataset["name"]},
                "profile": profile,
                "truncated": result.get("truncated", False),
                "row_count": len(result["rows"]),
            }
        )

    # ------------------------------------------------------------- dashboards
    @app.get("/api/dashboards")
    @auth.require_permissions("dashboards.view")
    def dashboards_list():
        return jsonify(auth.dashboards_for(g.user))

    @app.post("/api/dashboards")
    @auth.require_permissions("dashboards.create")
    @require_design
    def dashboards_create():
        body = _json_body()
        name = str(body.get("name") or "").strip()
        if not name:
            raise AppError("El nombre del dashboard es obligatorio")
        row = store.create_dashboard(name, str(body.get("description") or "").strip())
        auth.set_access(g.user["id"], row["id"], "edit", g.user["id"])
        auth.log_audit("dashboard.create", target=name, detail={"id": row["id"]})
        return jsonify(row), 201

    @app.get("/api/dashboards/<int:dashboard_id>/design")
    @auth.require_permissions("dashboards.design")
    @require_design_access
    def dashboards_design(dashboard_id: int):
        return jsonify(_design_payload(dashboard_id))

    @app.get("/api/dashboards/<int:dashboard_id>/render")
    @auth.require_permissions("dashboards.view")
    def dashboards_render(dashboard_id: int):
        return jsonify(_render_payload(dashboard_id))

    @app.put("/api/dashboards/<int:dashboard_id>")
    @auth.require_permissions("dashboards.design")
    @require_design
    def dashboards_update(dashboard_id: int):
        current = _require_dashboard_edit(dashboard_id)
        body = _json_body()
        name = str(body.get("name") or current["name"]).strip()
        description = str(body.get("description", current["description"]) or "").strip()
        row = store.update_dashboard(dashboard_id, name, description)
        auth.log_audit("dashboard.update", target=name, detail={"id": dashboard_id})
        return jsonify(row)

    @app.delete("/api/dashboards/<int:dashboard_id>")
    @auth.require_permissions("dashboards.delete")
    @require_design
    def dashboards_delete(dashboard_id: int):
        current = _require_dashboard_edit(dashboard_id)
        auth.log_audit("dashboard.delete", target=current["name"], detail={"id": dashboard_id})
        store.delete_dashboard(dashboard_id)
        return jsonify(ok=True)

    # ---------------------------------------------------------------- widgets
    @app.post("/api/dashboards/<int:dashboard_id>/widgets")
    @auth.require_permissions("dashboards.design")
    @require_design
    def widgets_create(dashboard_id: int):
        _require_dashboard_edit(dashboard_id)
        widget = _parse_widget(_json_body())
        row = store.create_widget(
            dashboard_id,
            widget["dataset_id"],
            widget["title"],
            widget["chart_type"],
            widget["config"],
            widget["w"],
            widget["h"],
            widget["x"],
            widget["y"],
        )
        auth.log_audit(
            "widget.create",
            target=widget["title"],
            detail={"id": row["id"], "dashboard_id": dashboard_id, "chart_type": widget["chart_type"]},
        )
        return jsonify(row), 201

    @app.put("/api/widgets/<int:widget_id>")
    @auth.require_permissions("dashboards.design")
    @require_design
    def widgets_update(widget_id: int):
        current = store.get_widget(widget_id)
        if not current:
            raise AppError("Widget no encontrado", status=404)
        _require_dashboard_edit(current["dashboard_id"])
        widget = _parse_widget(_json_body())
        row = store.update_widget(
            widget_id,
            widget["dataset_id"],
            widget["title"],
            widget["chart_type"],
            widget["config"],
            widget["w"],
            widget["h"],
            widget["x"],
            widget["y"],
        )
        auth.log_audit("widget.update", target=widget["title"], detail={"id": widget_id})
        return jsonify(row)

    @app.delete("/api/widgets/<int:widget_id>")
    @auth.require_permissions("dashboards.design")
    @require_design
    def widgets_delete(widget_id: int):
        current = store.get_widget(widget_id)
        if not current:
            raise AppError("Widget no encontrado", status=404)
        _require_dashboard_edit(current["dashboard_id"])
        auth.log_audit("widget.delete", target=current["title"], detail={"id": widget_id})
        store.delete_widget(widget_id)
        return jsonify(ok=True)

    @app.put("/api/widgets/<int:widget_id>/layout")
    @auth.require_permissions("dashboards.design")
    @require_design
    def widgets_layout(widget_id: int):
        current = store.get_widget(widget_id)
        if not current:
            raise AppError("Widget no encontrado", status=404)
        _require_dashboard_edit(current["dashboard_id"])
        body = _json_body()
        w = max(1, min(_int(body.get("w"), current["w"] or 3) or 3, 12))
        h = max(1, min(_int(body.get("h"), current["h"] or 2) or 2, 6))
        x = max(0, min(_int(body.get("x"), current["x"] or 0) or 0, 12 - w))
        y = max(0, min(_int(body.get("y"), current["y"] or 0) or 0, 999))
        row = store.update_widget_layout(widget_id, x, y, w, h)
        return jsonify(row)

    # ------------------------------------------------ tablas, archivos y APIs
    @app.put("/api/tables/alias")
    @auth.require_permissions("connections.manage")
    @require_design
    def tables_alias():
        body = _json_body()
        connection_id = _int(body.get("connection_id"), None)
        table = str(body.get("table") or "").strip()
        if not connection_id or not table:
            raise AppError("Indica connection_id y table")
        if not store.get_connection(connection_id):
            raise AppError("Conexion no encontrada", status=404)
        alias = str(body.get("alias") or "").strip()
        store.set_table_alias(connection_id, table, alias)
        auth.log_audit(
            "table.alias",
            target=table,
            detail={"connection_id": connection_id, "alias": alias},
        )
        return jsonify(ok=True, aliases=store.list_table_aliases(connection_id))

    @app.post("/api/import/file")
    @auth.require_permissions("datasets.manage")
    @require_design
    def import_file():
        upload = request.files.get("file")
        if not upload or not upload.filename:
            raise AppError("Selecciona un archivo CSV, TSV o Parquet")
        data = upload.read()
        if len(data) > MAX_UPLOAD_BYTES:
            raise AppError("El archivo supera el limite configurado", status=413, code="too_large")
        parsed = importers.read_upload(upload.filename, data)
        table = importers.sanitize_table_name(request.form.get("table") or upload.filename)
        result = importers.load_rows(table, parsed["rows"], parsed["columns"])
        dataset = _sync_imported_dataset(
            result["table"],
            request.form.get("name") or result["table"],
        )
        auth.log_audit(
            "import.file",
            target=result["table"],
            detail={"rows": result["rows"], "filename": upload.filename, "dataset_id": dataset["id"]},
        )
        return (
            jsonify(
                table=result,
                dataset=dataset,
                elapsed_ms=parsed.get("elapsed_ms", 0),
            ),
            201,
        )

    def _script_body() -> dict:
        body = _json_body()
        name = str(body.get("name") or "").strip()
        code = str(body.get("code") or "").strip()
        description = str(body.get("description") or "").strip()
        if not name or not code:
            raise AppError("Nombre y codigo del script son obligatorios")
        return {"name": name[:80], "description": description[:240], "code": code}

    @app.get("/api/import/scripts")
    @auth.require_permissions("import.api")
    @require_design_access
    def api_scripts_list():
        return jsonify({"scripts": store.list_api_scripts()})

    @app.post("/api/import/scripts")
    @auth.require_permissions("import.api")
    @require_design
    def api_scripts_create():
        payload = _script_body()
        try:
            row = store.create_api_script(payload["name"], payload["description"], payload["code"])
        except Exception as exc:  # noqa: BLE001
            if "UNIQUE" in str(exc):
                raise AppError("Ya existe un script con ese nombre", status=409) from exc
            raise
        auth.log_audit("api_script.create", target=row["name"], detail={"id": row["id"]})
        return jsonify(row), 201

    @app.put("/api/import/scripts/<int:script_id>")
    @auth.require_permissions("import.api")
    @require_design
    def api_scripts_update(script_id: int):
        if not store.get_api_script(script_id):
            raise AppError("Script no encontrado", status=404)
        payload = _script_body()
        row = store.update_api_script(
            script_id, payload["name"], payload["description"], payload["code"]
        )
        auth.log_audit("api_script.update", target=payload["name"], detail={"id": script_id})
        return jsonify(row)

    @app.delete("/api/import/scripts/<int:script_id>")
    @auth.require_permissions("import.api")
    @require_design
    def api_scripts_delete(script_id: int):
        current = store.get_api_script(script_id)
        if not current:
            raise AppError("Script no encontrado", status=404)
        store.delete_api_script(script_id)
        auth.log_audit("api_script.delete", target=current["name"], detail={"id": script_id})
        return jsonify(ok=True)

    @app.post("/api/import/script/run")
    @auth.require_permissions("import.api")
    @require_design
    def api_script_run():
        body = _json_body()
        script = None
        script_id = _int(body.get("script_id"), None)
        if script_id:
            script = store.get_api_script(script_id)
            if not script:
                raise AppError("Script no encontrado", status=404)
            code = script["code"]
            name = script["name"]
        else:
            code = str(body.get("code") or "").strip()
            name = str(body.get("name") or "api_import").strip()
        if not code:
            raise AppError("Indica script_id o el codigo a ejecutar")
        parsed = importers.run_api_script(code)
        if body.get("preview"):
            return jsonify(
                preview=True,
                columns=parsed["columns"][:60],
                rows=parsed["rows"][:20],
                row_count=len(parsed["rows"]),
                elapsed_ms=parsed["elapsed_ms"],
                stdout=parsed.get("stdout", ""),
            )
        if not parsed["rows"]:
            raise AppError("El script no devolvio filas", status=422, code="empty_result")
        table = importers.sanitize_table_name(body.get("table") or name)
        result = importers.load_rows(table, parsed["rows"], parsed["columns"])
        dataset = _sync_imported_dataset(result["table"], body.get("name") or name)
        auth.log_audit(
            "import.api",
            target=result["table"],
            detail={
                "rows": result["rows"],
                "script_id": script_id,
                "script": name[:120],
                "dataset_id": dataset["id"],
            },
        )
        return jsonify(table=result, dataset=dataset, elapsed_ms=parsed["elapsed_ms"]), 201

    @app.post("/api/demo/reset")
    @auth.require_permissions("system.reset")
    @require_design
    def demo_reset():
        from .seed import reset as seed_reset

        result = seed_reset()
        auth.log_audit("system.reset", detail=result)
        return jsonify(result)

    return app


app = create_app()


if __name__ == "__main__":
    app.run(
        host=os.environ.get("BIWEB_HOST", "0.0.0.0"),
        port=int(os.environ.get("BIWEB_PORT", "5000")),
        debug=os.environ.get("BIWEB_DEBUG", "0") == "1",
    )
