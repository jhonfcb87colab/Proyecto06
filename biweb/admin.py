"""Panel de administracion: usuarios, roles, accesos y auditoria."""
from __future__ import annotations

from flask import Blueprint, flash, g, redirect, render_template, request, url_for

from . import auth, store

bp = Blueprint("admin", __name__, url_prefix="/admin")


def _as_bool(value) -> bool:
    return str(value or "").lower() in {"1", "true", "on", "yes"}


def _active_admin_count() -> int:
    return sum(
        1
        for user in auth.list_users()
        if user["role_slug"] == "administrador" and user["is_active"]
    )


@bp.get("")
@auth.require_permissions("admin.users")
def users():
    edit_id = request.args.get("edit", type=int)
    edit_user = auth.get_user_by_id(edit_id) if edit_id else None
    return render_template(
        "admin/users.html",
        section="users",
        users=auth.list_users(),
        roles=auth.list_roles(),
        edit_user=edit_user,
    )


@bp.post("/users")
@auth.require_permissions("admin.users")
def user_create():
    try:
        user = auth.create_user(
            str(request.form.get("username") or "").strip(),
            request.form.get("password") or "",
            request.form.get("role_id", type=int) or 0,
            str(request.form.get("full_name") or "").strip(),
            str(request.form.get("email") or "").strip(),
            _as_bool(request.form.get("is_active")),
        )
    except ValueError as exc:
        flash(str(exc), "error")
    else:
        auth.log_audit("user.create", target=user["username"], detail={"role": user["role_slug"]})
        flash(f"Usuario {user['username']} creado.", "info")
    return redirect(url_for("admin.users"))


@bp.post("/users/<int:user_id>")
@auth.require_permissions("admin.users")
def user_update(user_id: int):
    target = auth.get_user_by_id(user_id)
    role = auth.get_role(request.form.get("role_id", type=int) or 0)
    if not target:
        flash("Usuario no encontrado.", "error")
        return redirect(url_for("admin.users"))
    if not role:
        flash("Rol no valido.", "error")
        return redirect(url_for("admin.users", edit=user_id))
    is_active = _as_bool(request.form.get("is_active"))
    if user_id == g.user["id"] and not is_active:
        flash("No puedes desactivar tu propio usuario.", "error")
        return redirect(url_for("admin.users", edit=user_id))
    if target["role_slug"] == "administrador" and role["slug"] != "administrador":
        if target["is_active"] and _active_admin_count() <= 1:
            flash("Debe quedar al menos un administrador activo.", "error")
            return redirect(url_for("admin.users", edit=user_id))
    password = request.form.get("password") or ""
    if password:
        try:
            auth.validate_password(password)
        except ValueError as exc:
            flash(str(exc), "error")
            return redirect(url_for("admin.users", edit=user_id))
    try:
        auth.update_user(
            user_id,
            role["id"],
            str(request.form.get("full_name") or ""),
            str(request.form.get("email") or ""),
            is_active,
        )
        if password:
            auth.set_password(user_id, password)
    except ValueError as exc:
        flash(str(exc), "error")
        return redirect(url_for("admin.users", edit=user_id))
    auth.log_audit(
        "user.update",
        target=target["username"],
        detail={"role": role["slug"], "active": is_active, "password_changed": bool(password)},
    )
    flash("Usuario actualizado.", "info")
    return redirect(url_for("admin.users"))


@bp.post("/users/<int:user_id>/delete")
@auth.require_permissions("admin.users")
def user_delete(user_id: int):
    target = auth.get_user_by_id(user_id)
    try:
        auth.delete_user(user_id, g.user["id"])
    except ValueError as exc:
        flash(str(exc), "error")
    else:
        auth.log_audit("user.delete", target=target["username"] if target else str(user_id))
        flash("Usuario eliminado.", "info")
    return redirect(url_for("admin.users"))


@bp.get("/roles")
@auth.require_permissions("admin.roles")
def roles():
    edit_id = request.args.get("edit", type=int)
    edit_role = auth.get_role(edit_id) if edit_id else None
    selected = auth.role_permission_keys(edit_role["id"]) if edit_role else set()
    return render_template(
        "admin/roles.html",
        section="roles",
        roles=auth.list_roles(),
        permission_groups=auth.PERMISSION_GROUPS,
        edit_role=edit_role,
        selected_permissions=selected,
    )


@bp.post("/roles")
@auth.require_permissions("admin.roles")
def role_create():
    try:
        role = auth.create_role(
            str(request.form.get("name") or ""),
            str(request.form.get("description") or ""),
            request.form.getlist("permissions"),
        )
    except ValueError as exc:
        flash(str(exc), "error")
    else:
        auth.log_audit(
            "role.create",
            target=role["name"],
            detail={"id": role["id"], "permissions": len(auth.role_permission_keys(role["id"]))},
        )
        flash("Rol creado.", "info")
    return redirect(url_for("admin.roles"))


@bp.post("/roles/<int:role_id>")
@auth.require_permissions("admin.roles")
def role_update(role_id: int):
    role = auth.get_role(role_id)
    if not role:
        flash("Rol no encontrado.", "error")
        return redirect(url_for("admin.roles"))
    try:
        auth.set_role_permissions(role_id, request.form.getlist("permissions"))
    except ValueError as exc:
        flash(str(exc), "error")
    else:
        auth.log_audit(
            "role.update",
            target=role["name"],
            detail={"permissions": sorted(auth.role_permission_keys(role_id))},
        )
        flash("Permisos del rol actualizados.", "info")
    return redirect(url_for("admin.roles"))


@bp.post("/roles/<int:role_id>/delete")
@auth.require_permissions("admin.roles")
def role_delete(role_id: int):
    role = auth.get_role(role_id)
    try:
        auth.delete_role(role_id)
    except ValueError as exc:
        flash(str(exc), "error")
    else:
        auth.log_audit("role.delete", target=role["name"] if role else str(role_id))
        flash("Rol eliminado.", "info")
    return redirect(url_for("admin.roles"))


@bp.get("/access")
@auth.require_permissions("access.manage")
def access():
    matrix = auth.access_map()
    return render_template(
        "admin/access.html",
        section="access",
        users=auth.list_users(),
        dashboards=store.list_dashboards(),
        matrix=matrix,
    )


@bp.post("/access")
@auth.require_permissions("access.manage")
def access_save():
    users = auth.list_users()
    dashboards = store.list_dashboards()
    changes = 0
    for user in users:
        if user["role_slug"] == "administrador" or "dashboards.view_all" in user["permissions"]:
            continue
        for dashboard in dashboards:
            field = f"access__{user['id']}__{dashboard['id']}"
            if field not in request.form:
                continue
            level = request.form.get(field) or None
            if level not in {None, "view", "edit"}:
                continue
            if auth.access_level(user["id"], dashboard["id"]) != level:
                auth.set_access(user["id"], dashboard["id"], level, g.user["id"])
                changes += 1
    auth.log_audit("access.update", detail={"changes": changes})
    flash(f"Accesos actualizados ({changes} cambios).", "info")
    return redirect(url_for("admin.access"))


@bp.get("/audit")
@auth.require_permissions("monitoring.audit")
def audit():
    username = str(request.args.get("username") or "").strip()
    action = str(request.args.get("action") or "").strip()
    limit = request.args.get("limit", type=int) or 200
    return render_template(
        "admin/audit.html",
        section="audit",
        entries=auth.list_audit(username=username or None, action=action or None, limit=limit),
        actions=auth.audit_actions(),
        username=username,
        action=action,
        limit=limit,
    )


@bp.post("/reset-demo")
@auth.require_permissions("system.reset")
def reset_demo():
    from .seed import reset as seed_reset

    result = seed_reset()
    auth.log_audit("system.reset", detail=result)
    flash("Datos de demostracion restaurados. Revisa los accesos de los tableros.", "info")
    return redirect(url_for("index"))
