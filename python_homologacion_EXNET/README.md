# Homologación de Ext.NET Classic 7 (ASP.NET Core) a Python

Ingeniería inversa del proyecto `src/` (Ext.NET Examples Explorer) y prueba de
concepto funcional en Python/Flask.

## 1. Qué es realmente este proyecto

| Pieza | Archivo(s) | Rol |
|---|---|---|
| Host ASP.NET Core 7 | `Program.cs`, `Startup.cs`, `Ext.Net.Examples.csproj` | Kestrel, compresión, Razor Pages, `AddExtNet()` / `UseExtNet()` |
| Ext.NET Classic 7.4 (NuGet, **comercial**) | `Ext.NET.Classic`, `Ext.NET.Classic.Charts` | TagHelpers `<ext-*>`, clases C# `Panel`, `GridPanel`…, protocolo Direct |
| Sencha Ext JS 7 (embebido en la DLL) | servido en `/extnet/...` | El framework de UI real, 100 % JavaScript |
| 81 ejemplos | `Pages/samples/<cat>/<subcat>/<ejemplo>/index.cshtml(.cs)` | Una Razor Page por ejemplo |
| Explorador | `TreeBuilder.cs`, `Category.cs`, `Example.cs`, `Pages/Index.cshtml` | Recorre carpetas y arma el árbol de navegación |
| Datos de ejemplo | `KitchenSink/Restaurant(s).cs` | Listas en memoria, sin base de datos |

**Hallazgo clave:** Ext.NET no dibuja nada. Es un **generador de configuración Ext JS**.
`<ext-gridPanel title="X">` y `new GridPanel { Title = "X" }` terminan como
`Ext.create({xtype: 'grid', title: 'X'})` en el navegador. Toda la UI vive en Ext JS.

### Mecanismos internos identificados (los que hay que replicar)

1. **Serialización**: propiedades C# PascalCase → camelCase (`PctChange` → `pctChange`);
   enums → minúsculas (`RegionType.West` → `'west'`); formatos de fecha .NET → Ext
   (`yyyy-MM-dd` → `Y-m-d`); `mode="Raw"` / `Handler` / `Renderer` → JS sin comillas.
2. **Listeners**: `Handler="..."` se envuelve en `function(<firma del evento>){...}`;
   por eso un handler de `itemclick` puede usar `record` directamente.
3. **Registro `App.<id>`**: todo componente con `id` queda accesible como `App.GridPanel1`.
4. **DirectMethods**: `[DirectModel]` + `[Direct] OnPostEdit(...)` genera en el cliente
   `App.direct.Edit(...)` → POST `?handler=Edit` → el servidor responde con un script.
5. **DirectEvents**: `<DirectEvents><Click pageHandler="X">` = listener que hace POST
   a `OnPostX`, con `EventMask` y `DurationMessages`.
6. **Respuesta fluida `this.X()`**: `Toast`, `AddScript`, `Msg.Alert`… se acumulan como JS
   y se devuelven con `return this.Direct()`.
7. **AjaxProxy**: endpoints `OnGetReadData(start, limit, sort)` con el protocolo estándar de Ext JS.

### Uso medido en los 81 ejemplos

`<ext-button>` 289 · `<ext-panel>` 207 · `<ext-add>` (config cruda) 156 · `<ext-textField>` 78 ·
`<ext-menuItem>` 76 · `<ext-treeNode>` 51 · `<ext-column>` 41 · `mode="Raw"` en 25 páginas ·
DirectEvents en 12 · `this.X()` en 9 · Charts en 1 · AjaxProxy en 1 · ViewComponents en 6.

La mayor parte es **UI declarativa pura** (layouts, paneles, formularios), que es lo más fácil de migrar.

## 2. Veredicto de viabilidad

**Sí se puede pasar a Python**, pero la DLL de Ext.NET no se "convierte": se **reemplaza la
capa servidor** y se conserva Ext JS en el cliente.

| Estrategia | Esfuerzo | Fidelidad | Comentario |
|---|---|---|---|
| **A. Ext JS + backend Python (esta PoC)** | Bajo/medio | Alta | Mismo look & feel y mismo JS de cliente. Requiere licencia Ext JS (comercial) o usar Ext JS GPL. |
| B. Ext JS puro + API REST (FastAPI) | Medio | Alta | Mover la definición de UI a JS/Sencha Cmd; Python solo sirve JSON. Mejor a largo plazo si el equipo sabe JS. |
| C. Reescribir UI (React/Vue + AG Grid, o NiceGUI/Reflex en Python) | Alto | Media | Elimina la dependencia de Sencha; es reescritura, no homologación. |

Riesgos y diferencias:

- **Licencias**: Ext.NET y Ext JS 7 son comerciales. La PoC usa Ext JS **6.0.0 GPLv3** de cdnjs;
  para producción, apunte `EXTJS_BASE` a su copia licenciada de Ext JS 7.
- **Tema Spotless** y propiedades `Variant`, `Rounded` e iconos `x-md md-icon-*` son exclusivos de
  Ext.NET; se omiten o hay que sustituirlos por otro tema o iconos.
- **Charts** (`Ext.NET.Classic.Charts`) requieren el paquete de charts de Ext JS.
- Los ViewComponents y el estilo "markup" (TagHelpers) se reemplazan por funciones Python
  que devuelven componentes. Si se quiere sintaxis tipo marcado, se puede hacer con macros Jinja.

## 3. Tabla de homologación

| Ext.NET / ASP.NET Core | Python (`extpy` + Flask) |
|---|---|
| `Program.cs` + `Startup.cs` | `app.create_app()` |
| `services.AddExtNet()` / `app.UseExtNet*()` | `app.register_blueprint(extpy_bp)` |
| `index.cshtml` + `IndexModel : PageModel` | `page = ExtPage("cat/sub/ejemplo", "Título")` |
| `public void OnGet()` | `@page.on_get` |
| `[Direct] OnPostEdit(...)` | `@page.direct_method def Edit(...)` |
| `OnPostDoSomething()` (DirectEvent) | `@page.direct_handler def DoSomething()` |
| `OnGetReadData(...)` | `@page.route("/ReadData")` |
| `<ext-gridPanel title=".." />` / `new GridPanel{Title=..}` | `GridPanel(title="..")` |
| atributo `bodyPadding` / propiedad `BodyPadding` | kwarg `body_padding` |
| `west.Items.Add(p)` | `west.add(p)` |
| `<ext-model><fields><ext-dataField type="Int"/>` | `Store(fields=[DataField("x", type="Int")])` |
| `<ext-ajaxProxy><ext-jsonReader x-rootProperty>` | `AjaxProxy(url, root_property=..)` |
| `<listeners><click handler=".." buffer="30"/>` | `listeners={"click": Listener("..", buffer=30)}` |
| `<DirectEvents><Click pageHandler="X">` | `direct_events={"click": DirectEvent("X")}` |
| `<ext-eventMask><DurationMessages>` | `EventMask(duration_messages=[DurationMessage(..)])` |
| `this.X().Toast(..)` / `.AddScript(..)` | `DirectResponse().toast(..).add_script(..)` |
| `<ext-add key=".." value=".." mode="Raw"/>` | `JS("...")` |
| `TreeBuilder.EnumerateExamples()` | `app.discover_examples()` + `build_examples_tree()` |

## 4. Ejemplos homologados

| # | Archivo Python | Original Ext.NET | Qué demuestra |
|---|---|---|---|
| 1 | `ejemplos/ej01_basic_gridpanel.py` | `kitchen_sink/gridpanels/basic_gridpanel` | Markup declarativo → Python, Store con datos y orden |
| 2 | `ejemplos/ej02_login_form.py` | `kitchen_sink/forms/login` | Viewport, VBox, FormPanel, enums |
| 3 | `ejemplos/ej03_border_layout_codebehind.py` | `layout/borderlayout/complex_in_codebehind` | Estilo code-behind imperativo, BorderLayout |
| 4 | `ejemplos/ej04_treepanel_codebehind.py` | `treepanel/basic/built_in_codebehind` | Árbol desde objetos de dominio, Listeners con firma |
| 5 | `ejemplos/ej05_grid_editor_directmethod.py` | `gridpanel/editable/editor_with_directmethod` | **DirectMethod** + `this.X().Toast/AddScript` |
| 6 | `ejemplos/ej06_grid_remote_paging.py` | `gridpanel/Paging_and_Sorting/Page` | **AjaxProxy**, paginado y ordenamiento remoto |
| 7 | `ejemplos/ej07_directevent_duration_messages.py` | `events/directevents/duration_messages` | **DirectEvents**, EventMask, mensajes por duración |
| — | `app.py` | `TreeBuilder.cs` + `Pages/Index.cshtml` | Explorador con árbol y visor de código |

Cada archivo incluye en su docstring el fragmento C#/Razor original para comparar lado a lado.

Dos defectos del original se corrigieron en el ejemplo 5 (están documentados en el archivo): el
formato del toast repetía `{0}`, y `idProperty="ID"` no coincidía con el campo serializado `id`.

## 5. Ejecutar

```bash
cd python_homologacion
pip install -r requirements.txt
python app.py                       # http://127.0.0.1:5000/
python -m unittest discover -s tests -v
```

Para migrar un ejemplo nuevo: copie un `ejNN_*.py`, cambie la ruta en `ExtPage(...)` y traduzca
cada `<ext-X attr="..">` a `X(attr=..)`. El explorador lo descubre automáticamente.

## 6. Estructura

```
python_homologacion/
├── app.py                 # host + explorador
├── extpy/                 # "Ext.NET en Python"
│   ├── serializer.py      # camelCase, JS crudo, formatos de fecha .NET→Ext
│   ├── components.py      # Panel, GridPanel, Store, Listener, TreeNode...
│   ├── direct.py          # DirectEvent, EventMask, DirectResponse (this.X())
│   ├── page.py            # ExtPage (PageModel), render HTML
│   └── static/extpy.js    # runtime cliente: App.*, App.direct, máscaras
├── ejemplos/              # 7 ejemplos homologados
└── tests/                 # 12 pruebas unitarias/integración
```
