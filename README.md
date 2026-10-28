# 📊 BIWeb

> Aplicación de BI ligera construida con **Flask**: conexiones, datasets, tableros y widgets, con separación estricta entre **diseño** y **visualización**.

---

## 📑 Tabla de contenido

1. [Inicio rápido](#1--inicio-rápido)
2. [Los dos modos](#2--los-dos-modos)
3. [Arquitectura](#3--arquitectura)
4. [API principal](#4--api-principal)
5. [Seguridad](#5--seguridad)
6. [Scripts de extracción del instalador](#6--scripts-de-extracción-del-instalador)
7. [Estructura del proyecto](#7--estructura-del-proyecto)
8. [Legal](#8--legal)

---

## 1. 🚀 Inicio rápido

> [!WARNING]
> **Cambia las contraseñas por defecto antes de exponer la aplicación.**
> - `admin` puede hacerlo desde **Mi cuenta**.
> - Los demás usuarios pueden cambiar la suya.
> - El administrador puede restablecerlas desde el panel de usuarios.
> - Define `BIWEB_ADMIN_PASSWORD` en el primer arranque para no usar `admin123`.
> - Los usuarios demo se desactivan con `BIWEB_DEMO_USERS=0`.

Si ya tienes Flask instalado, puedes verificarlo con:

```bash
python3 -c "import flask; print(flask.__version__)"
```

### ⚙️ Variables de entorno

| Variable | Default | Uso |
|---|---|---|
| `BIWEB_HOST` | `0.0.0.0` | Interfaz de escucha |
| `BIWEB_PORT` | `5000` | Puerto |
| `BIWEB_DEBUG` | `0` | `1` activa el modo debug de Flask |
| `BIWEB_VAR` | `./var` | Carpeta de datos y metadatos |
| `BIWEB_DESIGN` | `1` | `0` deshabilita toda la autoría (servidor solo visualización) |
| `BIWEB_DESIGN_TOKEN` | *(vacío)* | Exige `X-Design-Token` para leer/escribir la capa de diseño |
| `BIWEB_MAX_ROWS` | `20000` | Máximo de filas por consulta |
| `BIWEB_QUERY_TIMEOUT_MS` | `8000` | Timeout de consultas SQLite |
| `BIWEB_IMPORT_MAX_ROWS` | `200000` | Máximo de filas por importación de archivo o API |
| `BIWEB_MAX_UPLOAD_MB` | `64` | Tamaño máximo de subida en MB |
| `BIWEB_API_TIMEOUT` | `30` | Timeout (segundos) de los scripts de API |
| `BIWEB_SQLITE_ROOTS` | *(vacío)* | Rutas permitidas para conexiones SQLite (separadas por `:`) |
| `BIWEB_SECRET_KEY` | *(autogenerada)* | Clave de sesión; en producción define una fija y secreta |
| `BIWEB_ADMIN_PASSWORD` | `admin123` | Contraseña inicial del usuario `admin` |
| `BIWEB_DEMO_USERS` | `1` | `0` no crea `auditor` / `dev` / `viewer` |
| `BIWEB_COOKIE_SECURE` | `0` | `1` marca la cookie de sesión como `Secure` (requiere HTTPS) |

### 👁️ Ejemplo de despliegue solo visualización

```bash
BIWEB_DESIGN=0 BIWEB_PORT=8080 python3 run.py
```

---

## 2. 🎛️ Los dos modos

Cada tablero se abre en una de dos capas:

| Capa | URL | Qué permite |
|---|---|---|
| **Diseño / autoría** | `/d/<id>?mode=design` | Crear conexiones, datasets, widgets, layout; ver SQL |
| **Visualización** | `/d/<id>?mode=view` | Solo render del tablero |
| **Visualización pura** | `/view/<id>` | Página dedicada, sin panel ni controles de autoría (requiere sesión) |

El conmutador superior cambia en caliente entre *Visualización* y *Diseño*.

La capa de visualización usa exclusivamente `GET /api/dashboards/<id>/render`, que **no devuelve conexiones, credenciales ni SQL**.

### 🧭 Barra lateral en modo diseño

| Pestaña | Contenido |
|---|---|
| **Visualizaciones** | Paleta y configuración de widgets |
| **Datos** | Conexiones, datasets, tablas, importación y modelado |
| **Filtros** | Filtros activos |
| **Tablero** | Ajustes generales |

Así las herramientas de los widgets no quedan mezcladas con las fuentes de datos.

### 🔒 La separación también se aplica en el servidor

- Toda escritura de contenido (conexiones, datasets, tableros y widgets) exige `X-BI-Mode: design` (y token, si está configurado).
- Las acciones de administración solo exigen sesión, permiso y CSRF.
- Las lecturas de autoría (`/design`, `/api/connections`, `/api/datasets`, `/api/connections/<id>/tables`) están protegidas por `BIWEB_DESIGN` y el token.
- `BIWEB_DESIGN=0` bloquea la autoría por completo.
- Todas las rutas salvo `/login`, `/api/health` y los estáticos requieren sesión.
- Los métodos `POST/PUT/PATCH/DELETE` exigen el token CSRF de la sesión.

### 2.1 👥 Login, roles y permisos

Antes de mostrar cualquier módulo, la app exige iniciar sesión. Los roles base son:

| Rol | Alcance |
|---|---|
| **Administrador** | Todos los permisos, incluidos usuarios, roles, accesos, monitoreo y sistema. No se puede limitar. |
| **Auditor** | Ve todos los tableros, conexiones/datasets en modo lectura y la auditoría; no modifica nada. |
| **Desarrollador** | Crea tableros, edita visualizaciones, gestiona conexiones/datasets y usa la consola SQL. Solo edita tableros con acceso `edit`. |
| **Usuario de visualización** | Solo ve los tableros asignados. |

Los permisos se agrupan en *tableros*, *alcance global*, *datos*, *monitoreo* y *administración*. El administrador puede crear roles adicionales y ajustar sus permisos; **Administrador** siempre conserva todos.

**Acceso por tablero** — se concede por usuario en `/admin/access`: *Sin acceso*, *Ver* o *Editar*.

- Los tableros nuevos dan automáticamente acceso `edit` a su creador.
- Administrador y los roles con `dashboards.view_all` no necesitan asignación individual.
- Los cambios de usuarios, roles, accesos, contenido y sesiones quedan registrados en `/admin/audit`.

> 🎨 La UI usa una paleta pastel minimalista centralizada en variables CSS (`--bg`, `--surface`, `--primary`, `--accent`, etc.) en `static/style.css`.

---

## 3. 🏗️ Arquitectura

```text
Navegador
  |-- /view/<id>             (solo gráficos, auto-refresh 45 s)
  |-- /d/<id>?mode=view      (render)
  |-- /d/<id>?mode=design    (editor)
        |
        v
Flask (biweb/app.py)
  |-- auth.py          sesión, usuarios, roles, permisos, accesos, auditoría
  |-- admin.py         panel /admin (usuarios, roles, accesos, auditoría)
  |-- store.py         metadatos SQLite (conexiones/datasets/tableros/widgets)
  |-- security.py      valida SQL de solo lectura (SELECT/WITH, una sentencia)
  |-- data_sources.py  prueba/conecta/introspecta/ejecuta (SQLite, PG, MySQL, SQL Server)
  |-- analytics.py     agrega filas y prepara chart_data (kpi/bar/line/pie/table)
  |-- model.py         expresiones Python restringidas para medidas/columnas/tablas
  |-- seed.py          demo reproducible
  |
  +-- var/biweb.db     metadatos
  +-- var/sample.db    datos demo
```

Frontend **sin dependencias externas**: HTML/Jinja + CSS + JS y gráficos SVG propios (`static/charts.js`). No usa CDN ni build step.

### 🔄 Flujo de datos

1. En diseño guardas una **conexión** (SQLite / PostgreSQL / MySQL / SQL Server).
2. Guardas un **dataset**: un `SELECT`/`WITH` de solo lectura. El servidor lo ejecuta y deduce los campos (texto/número/fecha).
3. Creas **widgets**: dataset + tipo + x/y/serie/agregación + formato.
4. El endpoint `render` ejecuta cada dataset una sola vez (caché por request), agrega y devuelve `chart_data` listo para pintar.
5. La vista de lectura renderiza ese JSON sin acceso a la capa de autoría.

Los roles *Desarrollo* y *Administrador* pueden abrir `/console` para ejecutar SQL de lectura o escritura directamente sobre una conexión y copiar el equivalente en Python.

### 🐍 Expresiones de modelado en Python

Las medidas, columnas calculadas y tablas derivadas usan expresiones Python procesadas por `biweb/model.py`; es una capa de cálculo sencilla sobre las filas que devuelve un dataset. Las consultas de origen siguen siendo SQL `SELECT`/`WITH`.

**En una medida**, `rows` es la lista de filas:

```python
sum_field(rows, "revenue")
pct(sum_field(rows, "margin"), sum_field(rows, "revenue"))
```

**En una columna calculada**, `row` es la fila actual:

```python
field(row, "price", 0) * 1.19
ifelse(field(row, "units", 0) > 10, "alto", "bajo")
```

El evaluador permite operaciones y funciones de una lista controlada (por ejemplo `sum_field`, `avg_field`, `count_field`, `distinct_field`, `field`, `ifelse`, `coalesce` y `pct`). Las expresiones se validan al guardarlas y se pueden probar desde el editor. **No** permite imports, acceso a atributos ni sentencias completas de Python.

---

## 4. 🔌 API principal

| Método | Ruta | Acceso |
|---|---|---|
| `GET` | `/api/health` | pública |
| `GET` | `/api/state` | sesión (tableros visibles del usuario) |
| `GET/POST` | `/api/connections` | `connections.view` / `connections.manage` + diseño |
| `PUT/DELETE` | `/api/connections/<id>` | `connections.manage` + diseño |
| `POST` | `/api/connections/test` | `connections.manage` + diseño |
| `POST` | `/api/connections/import` | `connections.manage` + diseño |
| `GET` | `/api/connections/<id>/tables` | `connections.view` + diseño |
| `GET/POST` | `/api/datasets` | `datasets.view` / `datasets.manage` + diseño |
| `PUT/DELETE` | `/api/datasets/<id>` | `datasets.manage` + diseño |
| `POST` | `/api/datasets/preview` | `datasets.manage` + diseño |
| `POST` | `/api/sql/execute` | `sql.console` + rol Desarrollo/Administrador + diseño |
| `GET` | `/console` | `sql.console` + rol Desarrollo/Administrador |
| `GET/POST` | `/api/dashboards` | `dashboards.view` / `dashboards.create` + diseño |
| `GET` | `/api/dashboards/<id>/design` | `dashboards.design` + acceso `edit` |
| `GET` | `/api/dashboards/<id>/render` | `dashboards.view` + acceso al tablero |
| `PUT/DELETE` | `/api/dashboards/<id>` | `dashboards.design/delete` + acceso `edit` |
| `POST` | `/api/dashboards/<id>/widgets` | `dashboards.design` + acceso `edit` |
| `PUT/DELETE` | `/api/widgets/<id>` | `dashboards.design` + acceso `edit` |
| `PUT` | `/api/widgets/<id>/layout` | `dashboards.design` + acceso `edit` |
| `PUT` | `/api/tables/alias` | `connections.manage` + diseño |
| `POST` | `/api/import/file` | `datasets.manage` + diseño (CSV/TSV/Parquet) |
| `GET/POST` | `/api/import/scripts` | `import.api` + diseño |
| `PUT/DELETE` | `/api/import/scripts/<id>` | `import.api` + diseño |
| `POST` | `/api/import/script/run` | `import.api` + diseño (`preview: true` para probar) |
| `POST` | `/api/demo/reset` | `system.reset` + diseño |

### 📨 Cabeceras

```http
X-BI-Mode: design
X-Design-Token: <token>     # solo si BIWEB_DESIGN_TOKEN está definido
X-CSRF-Token: <token>        # obligatorio en POST/PUT/PATCH/DELETE
Cookie: session=...          # sesión iniciada en /login
```

El token CSRF está en `<meta name="csrf-token">` y en el campo `csrf_token` de cada formulario. La API devuelve `401 auth_required` sin sesión y `403 forbidden` si falta el permiso.

### 📥 Importar conexiones (mismo formato que la UI)

```json
{
  "connections": [
    {"name": "Demo", "kind": "sqlite", "config": {"path": "var/sample.db"}},
    {"name": "DW", "kind": "postgres",
     "config": {"host": "db.local", "port": 5432, "database": "dw",
                "user": "lector", "password": "***", "sslmode": "require"}},
    {"name": "ERP", "kind": "sqlserver",
     "config": {"host": "sql.local", "port": 1433, "database": "ERP",
                "user": "lector", "password": "***",
                "driver": "ODBC Driver 18 for SQL Server",
                "encrypt": "yes", "trust_server_certificate": "yes"}}
  ]
}
```

`kind` acepta alias: `mssql` / `sql server` se normalizan a `sqlserver`, `postgresql` a `postgres` y `mariadb` a `mysql`. Para SQL Server también se admite `trusted_connection: "yes"` (autenticación de Windows), en cuyo caso no se envían usuario ni contraseña.

### 🗄️ Motores soportados

| Motor | Requisito |
|---|---|
| **SQLite** | Incluido (archivo abierto en modo `ro` para datasets) |
| **SQL Server** | `pip install pyodbc` + driver ODBC instalado (por defecto *ODBC Driver 18 for SQL Server*) |
| **PostgreSQL / Supabase** | `pip install psycopg2-binary`. Supabase: host `db.<proyecto>.supabase.co`, puerto `5432`, base `postgres`, SSL `require` |
| **MySQL / MariaDB** | `pip install PyMySQL` |
| **Oracle** | `pip install oracledb` (service name en el campo base de datos) |
| **BigQuery** | `pip install google-cloud-bigquery` + credenciales ADC o ruta a un JSON de service account |

Los drivers de red no están instalados por defecto; la app responde con un error claro (`driver_missing`) si faltan.

### 📂 Importación de archivos y scripts

- La importación de archivos crea tablas en `var/imported.db` (o en `BIWEB_VAR/imported.db`) y un dataset sobre una conexión llamada **Datos importados**.
- Los scripts de API se ejecutan en un subproceso aislado con timeout y solo están disponibles para quien tenga el permiso `import.api` (administradores por defecto).
- Deben dejar el resultado en `result`, `df` o `rows`.

---

## 5. 🛡️ Seguridad

> [!NOTE]
> Pensado como base para **desarrollo/intranet**, no como SaaS multiusuario.

### Consultas y consola SQL

- Los datasets solo aceptan `SELECT`/`WITH`, una sentencia, sin DDL/DML ni `PRAGMA`/`ATTACH`.
- SQLite se abre con `mode=ro`, `PRAGMA query_only=ON`, timeout y límite de filas.
- PostgreSQL/MySQL usan transacciones de solo lectura y `statement_timeout`.
- La consola SQL (`/console`) es una función de desarrollo: solo los roles Desarrollo y Administrador pueden usarla, siempre en modo diseño y con el permiso `sql.console`.
  - El modo **lectura** solo permite `SELECT`/`WITH` y revierte la transacción.
  - El modo **escritura** permite DML/DDL y hace commit.
- La consola bloquea comandos de sistema/administración peligrosos (`xp_cmdshell`, `sp_configure`, `BACKUP`/`RESTORE`, `OPENROWSET`, etc.), pero **no sustituye** el control de permisos del motor: crea un usuario de base de datos dedicado y con los privilegios mínimos necesarios.
- Las consultas se ejecutan con la identidad de la conexión: para dashboards usa siempre un usuario de base de datos con permisos de **solo lectura**.

### Sesiones y autenticación

- Login local con sesiones Flask, contraseñas con hash (PBKDF2/scrypt de Werkzeug), CSRF, roles y permisos.
- No incluye MFA ni recuperación por correo.
- Usa HTTPS y `BIWEB_COOKIE_SECURE=1` fuera de localhost. La cookie se renueva con actividad y expira tras 12 horas sin uso.
- **No hay límite de intentos de login.** Si expones la app a Internet, pon un proxy con rate limiting, TLS y, si aplica, SSO (OIDC/SAML).
- La contraseña inicial `admin123` es solo para el primer arranque.

### Secretos y autoría

- Las contraseñas de conexión se guardan en `var/biweb.db` **sin cifrar**; en producción usa variables de entorno/vault y una base de metadatos cifrada.
- `BIWEB_DESIGN_TOKEN` protege la autoría, pero viaja en una cabecera: usa HTTPS.
- Restringe la ruta SQLite permitida (`BIWEB_SQLITE_ROOTS`) si el servidor es multiusuario.

### 🏭 Producción

```bash
pip install gunicorn
BIWEB_DESIGN_TOKEN=... gunicorn -w 2 -b 0.0.0.0:8000 "biweb.app:app"
```

---

## 6. 📦 Scripts de extracción del instalador

```bash
# Inspección (hash, PE, versión, firmas, contenedores)
python3 scripts/verify_bundle.py
python3 scripts/verify_bundle.py --json

# Extraer los CAB y las firmas tal cual (sin dependencias)
python3 scripts/carve_bundle.py --out extracted

# Orquestar todo y descomprimir si hay herramientas
./scripts/extract_bundle.sh
```

El script de extracción detecta, en orden, las herramientas disponibles en el sistema operativo.

---

## 7. 🗂️ Estructura del proyecto

```text
.
├── run.py
├── requirements.txt
├── scripts/
│   ├── verify_bundle.py
│   ├── carve_bundle.py
│   └── extract_bundle.sh
├── biweb/
│   ├── app.py
│   ├── auth.py
│   ├── admin.py
│   ├── config.py
│   ├── store.py
│   ├── security.py
│   ├── data_sources.py
│   ├── analytics.py
│   ├── seed.py
│   ├── templates/
│   │   ├── base.html
│   │   ├── login.html
│   │   ├── account.html
│   │   ├── error.html
│   │   ├── index.html
│   │   ├── dashboard.html
│   │   ├── console.html
│   │   ├── view.html
│   │   └── admin/
│   │       ├── layout.html
│   │       ├── users.html
│   │       ├── roles.html
│   │       ├── access.html
│   │       └── audit.html
│   └── static/
│       ├── style.css
│       ├── charts.js
│       ├── dashboard.js
│       ├── console.js
│       ├── index.js
│       └── viewer.js
├── var/            # creado al arrancar (ignorado por git)
└── extracted/      # salida de los scripts de extracción
```

---

## 8. ⚖️ Legal

Los scripts y herramientas de este repositorio se proporcionan con fines de estudio técnico, análisis de paquetes e interoperabilidad. La aplicación de BI incluida es una implementación independiente construida desde cero con datos de ejemplo generados sintéticamente.
