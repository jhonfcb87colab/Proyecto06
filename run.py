#!/usr/bin/env python3
"""Arranca el servidor de BI web.

    python3 run.py                 # http://0.0.0.0:5000
    BIWEB_PORT=8080 python3 run.py

Variables de entorno utiles:
    BIWEB_DESIGN=0            desactiva toda la capa de autoria
    BIWEB_DESIGN_TOKEN=...    exige cabecera X-Design-Token para escribir
    BIWEB_VAR=/ruta           carpeta de datos/metadatos
    BIWEB_ADMIN_PASSWORD=...  contrasena inicial de admin
    BIWEB_DEMO_USERS=0        no crea usuarios demo
    BIWEB_COOKIE_SECURE=1     cookie Secure (requiere HTTPS)
    BIWEB_SECRET_KEY=...      clave de sesion fija en produccion
    BIWEB_MAX_ROWS=20000      limite de filas por consulta
    BIWEB_QUERY_TIMEOUT_MS=8000
"""
import os

from biweb.app import app

if __name__ == "__main__":
    app.run(
        host=os.environ.get("BIWEB_HOST", "0.0.0.0"),
        port=int(os.environ.get("BIWEB_PORT", "5000")),
        debug=os.environ.get("BIWEB_DEBUG", "0") == "1",
    )
