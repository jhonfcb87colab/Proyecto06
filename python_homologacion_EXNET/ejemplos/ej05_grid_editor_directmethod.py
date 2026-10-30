"""
EJEMPLO 5 - Grid editable que guarda vía DirectMethod
Original: src/Pages/samples/gridpanel/editable/editor_with_directmethod/

    // Cliente (index.cshtml)
    App.direct.Edit(e.record.data.id, e.field, e.originalValue, e.value);

    // Servidor (index.cshtml.cs)
    [DirectModel]
    public class IndexModel : PageModel {
        [Direct]
        public IActionResult OnPostEdit(int id, string field, string oldValue, string newValue) {
            this.X().Toast(string.Format(message, id, field, oldValue, newValue));
            this.X().AddScript("App.GridPanel1.getStore().commitChanges()");
            return this.Direct();
        }
    }

Homologación:
  [Direct] OnPostEdit       -> @page.direct_method  def Edit(...)
  this.X().Toast / AddScript -> DirectResponse().toast(...).add_script(...)
  editorModel="new NumberField()" -> editor=NumberField()

Diferencias encontradas en el original (se corrigen aquí):
  * El formato del mensaje usa {0} dos veces, así que "Property" muestra el id.
  * <ext-model idProperty="ID"> no coincide con el campo serializado "id".
"""
from dataclasses import dataclass
from datetime import date

from extpy import (Column, DataField, DateColumn, DateField, DirectResponse, ExtPage, GridPanel,
                   JS, Listener, NumberField, PageResult, Store, TextField)

page = ExtPage("gridpanel/editable/editor_with_directmethod", "Editor with DirectMethod", __file__)

HEAD = """
<script>
    var template = 'color:{0};';
    var change = function (value, meta) {
        meta.style = Ext.String.format(template, (value > 0) ? "green" : "red");
        return value;
    };
    var pctChange = function (value, meta) {
        meta.style = Ext.String.format(template, (value > 0) ? "green" : "red");
        return value + "%";
    };
    var edit = function (editor, e) {
        if (!(e.value === e.originalValue || (Ext.isDate(e.value) && Ext.Date.isEqual(e.value, e.originalValue)))) {
            App.direct.Edit(e.record.data.id, e.field, e.originalValue, e.value);
        }
    };
</script>"""


@dataclass
class Company:
    id: int
    name: str
    price: float
    change: float
    pct_change: float
    last_change: date


_COMPANIES = [
    ("3m Co", 71.72, 0.02, 0.03), ("Alcoa Inc", 29.01, 0.42, 1.47),
    ("Altria Group Inc", 83.81, 0.28, 0.34), ("American Express Company", 52.55, 0.01, 0.02),
    ("American International Group, Inc.", 64.13, 0.31, 0.49), ("AT&T Inc.", 31.61, -0.48, -1.54),
    ("Boeing Co.", 75.43, 0.53, 0.71), ("Caterpillar Inc.", 67.27, 0.92, 1.39),
    ("Citigroup, Inc.", 49.37, 0.02, 0.04), ("E.I. du Pont de Nemours and Company", 40.48, 0.51, 1.28),
    ("Exxon Mobil Corp", 68.1, -0.43, -0.64), ("General Electric Company", 34.14, -0.08, -0.23),
    ("General Motors Corporation", 30.27, 1.09, 3.74), ("Hewlett-Packard Co.", 36.53, -0.03, -0.08),
    ("Honeywell Intl Inc", 38.77, 0.05, 0.13), ("Intel Corporation", 19.88, 0.31, 1.58),
    ("International Business Machines", 81.41, 0.44, 0.54), ("Johnson & Johnson", 64.72, 0.06, 0.09),
    ("JP Morgan & Chase & Co", 45.73, 0.07, 0.15), ("McDonald's Corporation", 36.76, 0.86, 2.40),
    ("Merck & Co., Inc.", 40.96, 0.41, 1.01), ("Microsoft Corporation", 25.84, 0.14, 0.54),
    ("Pfizer Inc", 27.96, 0.4, 1.45), ("The Coca-Cola Company", 45.07, 0.26, 0.58),
    ("The Home Depot, Inc.", 34.64, 0.35, 1.02), ("The Procter & Gamble Company", 61.91, 0.01, 0.02),
    ("United Technologies Corporation", 63.26, 0.55, 0.88), ("Verizon Communications", 35.57, 0.39, 1.11),
    ("Wal-Mart Stores, Inc.", 45.45, 0.73, 1.63),
]


def grid_data() -> list[Company]:
    today = date.today()
    return [Company(i, n, p, c, pc, today) for i, (n, p, c, pc) in enumerate(_COMPANIES, start=1)]


@page.direct_method
def Edit(id: int, field: str, oldValue, newValue):  # noqa: N802,N803 - nombre expuesto al cliente
    message = ("<h2>Edit Record #{0}</h2><hr/><b>Field:</b> {1}<br />"
               "<b>Old Value:</b> {2}<br /><b>New Value:</b> {3}")
    return (DirectResponse()
            .toast(message.format(id, field, oldValue, newValue))
            .add_script("App.GridPanel1.getStore().commitChanges()"))


@page.on_get
def on_get():
    grid = GridPanel(
        id="GridPanel1",
        title="Editable GridPanel",
        width=800,
        height=480,
        store=Store(
            store_id="Store1",
            id_property="id",
            data=grid_data(),
            fields=[
                DataField("id", type="Int"),
                DataField("name"),
                DataField("price", type="Float"),
                DataField("change", type="Float"),
                DataField("pctChange", type="Float"),
                DataField("lastChange", type="Date"),
            ],
        ),
        columns=[
            Column(text="ID", data_index="id", width=50),
            Column(text="Name", data_index="name", flex=1, editor=TextField()),
            Column(text="Price", data_index="price", renderer=JS("Ext.util.Format.usMoney"), editor=NumberField()),
            Column(text="Change", data_index="change", renderer=JS("change"), editor=NumberField()),
            Column(text="Change", data_index="pctChange", renderer=JS("pctChange"), editor=NumberField()),
            DateColumn(text="Last Updated", data_index="lastChange", format="yyyy-MM-dd", width=125,
                       editor=DateField(format="yyyy-MM-dd")),
        ],
        sel_type="cellmodel",                                     # <ext-cellSelectionModel />
        plugins=[{"ptype": "cellediting",                         # <ext-cellEditingPlugin>
                  "listeners": {"edit": Listener(fn="edit").render("edit")}}],
    )
    return PageResult(grid, head=HEAD, body="<h1>Editable GridPanel With Save To [DirectMethod]</h1>")
