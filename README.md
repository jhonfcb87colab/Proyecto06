# BI Web + analisis del instalador de Power BI

Dos piezas independientes en este directorio:

1. **`scripts/`** — verificacion y extraccion del instalador `PBIDesktopSetup_x64.exe`.
2. **`biweb/`** — aplicacion web Flask de BI con **dos capas conmutables**: autoria
   (diseno) y visualizacion (solo lectura), con **login, roles y permisos**.

> El instalador es un bootstrapper firmado de Microsoft. Los scripts solo lo
> inspeccionan/extraen; no lo ejecutan ni alteran. El contenido extraido sigue
> siendo propiedad de Microsoft (ver seccion Legal).

---

## 1. Arrancar la aplicacion

Requisitos: Python 3.10+ y Flask 3.

```bash
pip install -r requirements.txt
python3 run.py
# http://localhost:5000  ->  inicia sesion con admin / admin123
```

La primera ejecucion crea `var/` con:

- `var/sample.db` — SQLite de demostracion (720 filas de ventas, 12 meses).
- `var/biweb.db` — metadatos (conexiones, datasets, tableros, widgets, usuarios,
  roles, permisos, accesos y auditoria).
- `var/secret.key` — clave de sesion generada automaticamente.
- Un tablero **Ventas 2026** con 7 widgets listos.

### Usuarios iniciales

| Usuario | Contrasena | Rol |
|---|---|---|
| `admin` | `admin123` | Administrador |
| `auditor` | `auditor123` | Auditor |
| `dev` | `dev12345` | Desarrollador |
| `viewer` | `viewer123` | Usuario de visualizacion |

**Cambia estas contrasenas antes de exponer la aplicacion.** `admin` puede
hacerlo desde `Mi cuenta`; los demas usuarios pueden cambiar la suya, y el
administrador puede restablecerlas desde el panel de usuarios. Define
`BIWEB_ADMIN_PASSWORD` en el primer arranque para no usar `admin123`. Los
usuarios demo se desactivan con `BIWEB_DEMO_USERS=0`.

Si ya tienes Flask instalado:

```bash
python3 -c "import flask; print(flask.__version__)"
```

### ⚙️ Variables de entorno

| Variable | Valor por defecto | Uso |
|---|---|---|
| `BIWEB_HOST` | `0.0.0.0` | Interfaz de escucha |
| `BIWEB_PORT` | `5000` | Puerto |
| `BIWEB_DEBUG` | `0` | `1` activa el modo debug de Flask |
| `BIWEB_VAR` | `./var` | Carpeta de datos y metadatos |
| `BIWEB_DESIGN` | `1` | `0` deshabilita toda la autoria (servidor solo visualizacion) |
| `BIWEB_DESIGN_TOKEN` | vacio | Exige `X-Design-Token` para leer/escribir la capa de diseno |
| `BIWEB_MAX_ROWS` | `20000` | Maximo de filas por consulta |
| `BIWEB_QUERY_TIMEOUT_MS` | `8000` | Timeout de consultas SQLite |
| `BIWEB_IMPORT_MAX_ROWS` | `200000` | Maximo de filas por importacion de archivo o API |
| `BIWEB_MAX_UPLOAD_MB` | `64` | Tamano maximo de subida en MB |
| `BIWEB_API_TIMEOUT` | `30` | Timeout en segundos de los scripts de API |
| `BIWEB_SQLITE_ROOTS` | vacio | Rutas permitidas para conexiones SQLite (separadas por `:`) |
| `BIWEB_SECRET_KEY` | autogenerada | Clave de sesion; en produccion define una fija y secreta |
| `BIWEB_ADMIN_PASSWORD` | `admin123` | Contrasena inicial del usuario `admin` |
| `BIWEB_DEMO_USERS` | `1` | `0` no crea `auditor`/`dev`/`viewer` |
| `BIWEB_COOKIE_SECURE` | `0` | `1` marca la cookie de sesion como `Secure` (requiere HTTPS) |

Ejemplo de despliegue **solo visualizacion**:

```bash
BIWEB_DESIGN=0 BIWEB_PORT=8080 python3 run.py
```

### Pruebas

```bash
python3 -m unittest discover -s tests -v
```

---

## 2. Los dos modos

Cada tablero se abre en una de tres vistas:

| Capa | URL | Qué permite |
|---|---|---|
| **Diseno / autoria** | `/d/<id>?mode=design` | Crear conexiones, datasets, widgets, layout; ver SQL |
| **Visualizacion** | `/d/<id>?mode=view` | Solo render del tablero |
| **Visualizacion pura** | `/view/<id>` | Pagina dedicada, sin panel ni controles de autoria (requiere sesion) |

El conmutador superior cambia en caliente entre **Visualizacion** y **Diseno**.
La capa de visualizacion usa exclusivamente `GET /api/dashboards/<id>/render`,
que **no devuelve conexiones, credenciales ni SQL**.

En modo diseno, la barra lateral separa **Visualizaciones** (paleta y
configuracion de widgets), **Datos** (conexiones, datasets, tablas, importacion
y modelado), **Filtros** (filtros activos) y **Tablero** (ajustes generales).
Asi las herramientas de los widgets no quedan mezcladas con las fuentes de datos.

La separacion tambien se aplica en el servidor:

- Toda escritura de contenido (conexiones, datasets, tableros y widgets) exige
  `X-BI-Mode: design` (y token, si esta configurado). Las acciones de
  administracion solo exigen sesion, permiso y CSRF.
- Las lecturas de autoria (`/design`, `/api/connections`, `/api/datasets`,
  `/api/connections/<id>/tables`) estan protegidas por `BIWEB_DESIGN` y el token.
- `BIWEB_DESIGN=0` bloquea la autoria por completo.
- Todas las rutas salvo `/login`, `/api/health` y los estaticos requieren sesion.
- Los metodos `POST`/`PUT`/`PATCH`/`DELETE` exigen el token CSRF de la sesion.

---

## 2.1 Login, roles y permisos

Antes de mostrar cualquier módulo, la app exige iniciar sesión. Los roles base son:

| Rol | Alcance |
|---|---|
| **Administrador** | Todos los permisos, incluidos usuarios, roles, accesos, monitoreo y sistema. No se puede limitar. |
| **Auditor** | Ve todos los tableros, conexiones/datasets en modo lectura y la auditoría; no modifica nada. |
| **Desarrollador** | Crea tableros, edita visualizaciones, gestiona conexiones/datasets y usa la consola SQL. Solo edita tableros con acceso `edit`. |
| **Usuario de visualización** | Solo ve los tableros asignados. |

Los permisos se agrupan en tableros, alcance global, datos, monitoreo y
administracion. El administrador puede crear roles adicionales y ajustar sus
permisos; `Administrador` siempre conserva todos.

El acceso a cada tablero se concede **por usuario** en
`/admin/access`: `Sin acceso`, `Ver` o `Editar`. Los tableros nuevos dan
automaticamente acceso `edit` a su creador. `Administrador` y los roles con
`dashboards.view_all` no necesitan asignacion individual. Los cambios de
usuarios, roles, accesos, contenido y sesiones quedan registrados en
`/admin/audit`.

> 🎨 La UI usa una paleta pastel minimalista centralizada en variables CSS (`--bg`, `--surface`, `--primary`, `--accent`, etc.) en `static/style.css`.

---

## 3. Arquitectura

```text
Navegador
  |-- /view/<id>            (solo graficos, auto-refresh 45 s)
  |-- /d/<id>?mode=view     (render)
  |-- /d/<id>?mode=design   (editor)
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
  |-- imports.py       CSV, TSV, Parquet y scripts de API
  |-- seed.py          demo reproducible
  |
  +-- var/biweb.db     metadatos
  +-- var/sample.db    datos demo
  +-- var/imported.db  tablas importadas
```

Frontend sin dependencias externas: HTML/Jinja + CSS + JS y graficos SVG propios
(`static/charts.js`). No usa CDN ni build step.

### 🔄 Flujo de datos

1. En diseno guardas una **conexion** (SQLite/PostgreSQL/MySQL/SQL Server).
2. Guardas un **dataset**: un `SELECT`/`WITH` de solo lectura. El servidor lo
   ejecuta y deduce los campos (texto/numero/fecha).
3. Creas **widgets**: dataset + tipo + `x`/`y`/`serie`/agregacion + formato.
4. El endpoint `render` ejecuta cada dataset una sola vez (cache por request),
   agrega y devuelve `chart_data` listo para pintar.
5. La vista de lectura renderiza ese JSON sin acceso a la capa de autoria.
6. Los roles **Desarrollo** y **Administrador** pueden abrir `/console` para
   ejecutar SQL de lectura o escritura directamente sobre una conexion y copiar
   el equivalente en Python.

### 🐍 Expresiones de modelado en Python

Las medidas, columnas calculadas y tablas derivadas usan **expresiones Python**
procesadas por `biweb/model.py`; no se ejecuta DAX ni se acepta codigo Python
arbitrario. Es una capa de calculo sencilla sobre las filas que devuelve un
dataset, no un motor semantico compatible con DAX. Las consultas de origen
siguen siendo SQL `SELECT`/`WITH`.

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

El evaluador permite operaciones y funciones de una lista controlada (por
ejemplo `sum_field`, `avg_field`, `count_field`, `distinct_field`, `field`,
`ifelse`, `coalesce` y `pct`). Las expresiones se validan al guardarlas y se
pueden probar desde el editor. No permite imports, acceso a atributos ni
sentencias completas de Python.

---

## 4. API principal

| Método | Ruta | Acceso |
|---|---|---|
| `GET` | `/api/health` | publica |
| `GET` | `/api/state` | sesion (tableros visibles del usuario) |
| `GET/POST` | `/api/connections` | `connections.view` / `connections.manage` + diseno |
| `PUT/DELETE` | `/api/connections/<id>` | `connections.manage` + diseno |
| `POST` | `/api/connections/test` | `connections.manage` + diseno |
| `POST` | `/api/connections/import` | `connections.manage` + diseno |
| `GET` | `/api/connections/<id>/tables` | `connections.view` + diseno |
| `GET/POST` | `/api/datasets` | `datasets.view` / `datasets.manage` + diseno |
| `PUT/DELETE` | `/api/datasets/<id>` | `datasets.manage` + diseno |
| `POST` | `/api/datasets/preview` | `datasets.manage` + diseno |
| `POST` | `/api/sql/execute` | `sql.console` + rol Desarrollo/Administrador + diseno |
| `GET` | `/console` | `sql.console` + rol Desarrollo/Administrador |
| `GET/POST` | `/api/dashboards` | `dashboards.view` / `dashboards.create` + diseno |
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

Cabeceras:

```http
X-BI-Mode: design
X-Design-Token: <token>      # solo si BIWEB_DESIGN_TOKEN esta definido
X-CSRF-Token: <token>        # obligatorio en POST/PUT/PATCH/DELETE
Cookie: session=...          # sesión iniciada en /login
```

El token CSRF esta en `<meta name="csrf-token">` y en el campo `csrf_token` de
cada formulario. La API devuelve `401 auth_required` sin sesion y
`403 forbidden` si falta el permiso.

Importar conexiones (mismo formato que la UI):

```json
{
  "connections": [
    {
      "name": "Demo",
      "kind": "sqlite",
      "config": { "path": "var/sample.db" }
    },
    {
      "name": "DW",
      "kind": "postgres",
      "config": {
        "host": "db.local",
        "port": 5432,
        "database": "dw",
        "user": "lector",
        "password": "***",
        "sslmode": "require"
      }
    },
    {
      "name": "ERP",
      "kind": "sqlserver",
      "config": {
        "host": "sql.local",
        "port": 1433,
        "database": "ERP",
        "user": "lector",
        "password": "***",
        "driver": "ODBC Driver 18 for SQL Server",
        "encrypt": "yes",
        "trust_server_certificate": "yes"
      }
    }
  ]
}
```

`kind` acepta alias: `mssql`/`sql server` se normalizan a `sqlserver`,
`postgresql` a `postgres` y `mariadb` a `mysql`. Para SQL Server tambien se
admite `trusted_connection: "yes"` (autenticacion de Windows), en cuyo caso no
se envian usuario ni contrasena.

Motores soportados:

- **SQLite** incluido (archivo abierto en modo `ro` para datasets).
- **SQL Server**: `pip install pyodbc` y el
  [Microsoft ODBC Driver for SQL Server](https://learn.microsoft.com/sql/connect/odbc/download-odbc-driver-for-sql-server)
  instalado en el sistema (por defecto `ODBC Driver 18 for SQL Server`).
- **PostgreSQL** y **Supabase**: `pip install psycopg2-binary`. Supabase usa el
  host `db.<proyecto>.supabase.co`, puerto 5432, base `postgres` y SSL `require`.
- **MySQL/MariaDB**: `pip install PyMySQL`.
- **Oracle**: `pip install oracledb` (service name en el campo base de datos).
- **BigQuery**: `pip install google-cloud-bigquery` y credenciales ADC o la ruta
  a un JSON de service account.

Los drivers de red no estan instalados por defecto; la app responde con un error
claro (`driver_missing`) si faltan.

La importacion de archivos crea tablas en `var/imported.db` (o en
`BIWEB_VAR/imported.db`) y un dataset sobre una conexion llamada
`Datos importados`. Los scripts de API se ejecutan en un subproceso aislado con
timeout y solo estan disponibles para quien tenga el permiso `import.api`
(administradores por defecto). Deben dejar el resultado en `result`, `df` o
`rows`.

---

## 5. Seguridad

Pensado como base para desarrollo/intranet, no como SaaS multiusuario:

- Los **datasets** solo aceptan `SELECT`/`WITH`, una sentencia, sin DDL/DML ni
  `PRAGMA`/`ATTACH`. SQLite se abre con `mode=ro`, `PRAGMA query_only=ON`,
  timeout y limite de filas. PostgreSQL/MySQL usan transacciones de solo lectura
  y `statement_timeout`.
- La **consola SQL** (`/console`) es una funcion de desarrollo: solo los roles
  `Desarrollo` y `Administrador` pueden usarla, siempre en modo diseno y con el
  permiso `sql.console`. El modo lectura solo permite SELECT/WITH y revierte la
  transaccion; el modo escritura permite DML/DDL y hace commit.
- La consola bloquea comandos de sistema/administracion peligrosos
  (`xp_cmdshell`, `sp_configure`, `BACKUP/RESTORE`, `OPENROWSET`, etc.), pero no
  sustituye el control de permisos del motor: crea un usuario de base de datos
  dedicado y con los privilegios minimos necesarios.
- Las consultas se ejecutan con la identidad de la conexion: para dashboards
  **usa siempre un usuario de base de datos con permisos de solo lectura**.
- Hay login local con sesiones Flask, contrasenas con hash (PBKDF2/scrypt de
  Werkzeug), CSRF, roles y permisos. No incluye MFA ni recuperacion por correo.
- Usa HTTPS y `BIWEB_COOKIE_SECURE=1` fuera de localhost. La cookie se renueva
  con actividad y expira tras 12 horas sin uso.
- No hay limite de intentos de login. Si expones la app a Internet, pon un proxy
  con rate limiting, TLS y, si aplica, SSO (OIDC/SAML).
- La contrasena inicial `admin123` es solo para el primer arranque.
- Las contrasenas de conexion se guardan en `var/biweb.db` sin cifrar; en
  produccion usa variables de entorno/vault y una base de metadatos cifrada.
- `BIWEB_DESIGN_TOKEN` protege la autoria, pero viaja en una cabecera: usa HTTPS.
- Restringe la ruta SQLite permitida si el servidor es multiusuario.

Produccion:

```bash
pip install gunicorn
BIWEB_DESIGN_TOKEN=... gunicorn -w 2 -b 0.0.0.0:8000 "biweb.app:app"
```

---

## 6. Scripts de extraccion del instalador

```bash
# Inspección (hash, PE, versión, firmas, contenedores)
python3 scripts/verify_bundle.py
python3 scripts/verify_bundle.py --json

# Extraer los CAB y las firmas tal cual (sin dependencias)
python3 scripts/carve_bundle.py --out extracted

# Orquestar todo y descomprimir si hay herramientas
./scripts/extract_bundle.sh
```

El script de extraccion detecta, en orden: `dark.exe` (WiX), `cabextract`,
`7z/7za`. Si no hay ninguno, deja los `.cab` crudos y las firmas en `extracted/`
y muestra las alternativas (incluido `PBIDesktopSetup_x64.exe /layout` en Windows).

Los CAB usan compresion **LZX** con flags propios de Burn (`0x1503`). Si
`cabextract` falla, la ruta mas fiable es WiX:

```bat
dark.exe PBIDesktopSetup_x64.exe -x C:\extraido
```

Con el MSI ya extraido, para ver su contenido instalado:

```bat
msiexec /a PBIDesktop.msi /qb TARGETDIR=C:\extraido
```

### Resultado del analisis de `PBIDesktopSetup_x64.exe`

- SHA-256: `8ffccf627d383dcb6aa0dc8138a536b76af86246f0a730e1df103c1fe7883109`
- PE32 GUI (stub x86), subsistema GUI, seccion `.wixburn`.
- WiX Burn **3.11.1.2318**.
- Producto: **Microsoft PowerBI Desktop (x64)** version **2.95.983.0**.
- Firma Authenticode de **Microsoft Corporation**, timestamp 2021-07-29.
- Contenedor UX: CAB de 257.388 bytes con 35 archivos (motor/bootstrapper).
- Payload: CAB de 364.528.939 bytes con un archivo `a0` de 375.431.168 bytes
  (el MSI comprimido).
- El `.exe` real solo ocupa ~1 MB; el resto es payload.

Este analisis **no** convierte el binario en una app web. Una reimplementacion
web es un desarrollo nuevo; los binarios/assets de Microsoft no deben reutilizarse
en un producto propio.

---

## 7. Estructura

```
.
├── PBIDesktopSetup_x64.exe
├── run.py
├── requirements.txt
├── README.md
├── scripts/
│   ├── verify_bundle.py
│   ├── carve_bundle.py
│   └── extract_bundle.sh
├── biweb/
│   ├── app.py
│   ├── admin.py
│   ├── analytics.py
│   ├── auth.py
│   ├── config.py
│   ├── data_sources.py
│   ├── imports.py
│   ├── model.py
│   ├── security.py
│   ├── seed.py
│   ├── store.py
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
└── extracted/      # salida de los scripts de extraccion
```
