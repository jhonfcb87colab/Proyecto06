"""
EJEMPLO 6 - GridPanel con paginado y ordenamiento remoto (AjaxProxy)
Original: src/Pages/samples/gridpanel/Paging_and_Sorting/Page/

    <ext-store remoteSort="true" pageSize="5" autoLoad="true">
        <proxy>
            <ext-ajaxProxy url="Page/ReadData">
                <reader><ext-jsonReader x-rootProperty="Data" x-totalProperty="TotalRecords"/></reader>
            </ext-ajaxProxy>
        </proxy>
    ...
    public ContentResult OnGetReadData(int start, int limit, string sort) {
        var sortInfo = JsonSerializer.Deserialize<List<SortInfo>>(sort, ...)[0];
        var data = Plant.PlantsPaging(start, limit, sortInfo.Property, ...);
        return Content(JsonSerializer.Serialize(data));
    }

Homologación:
  OnGetReadData                     -> @page.route("/ReadData")
  System.Text.Json (PascalCase)     -> claves explícitas "Common", "Botanical"...
  Reflection GetProperty(sort)      -> diccionario / getattr
  <ext-add key="features" mode="Raw"> -> features=JS(...)
"""
import json
from dataclasses import dataclass
from datetime import date

from flask import jsonify, request

from extpy import (AjaxProxy, Column, DataField, DateColumn, ExtPage, GridPanel, JS,
                   PageResult, PagingToolbar, Sorter, Store)

page = ExtPage("gridpanel/paging_and_sorting/page", "GridPanel with Remote Paging and Sorting", __file__)

HEAD = """
<style>
    .x-grid-rowbody p { margin: 5px 5px 10px 5px !important; color: gray; font-size: small; }
</style>
<script>
    var commonNameRenderer = function (value) { return "<b>" + value + "</b>"; };
</script>"""

# Ext.NET: var gridFeaturesBlock = @"[Ext.create(""Ext.grid.feature.RowBody"", {...})]"
GRID_FEATURES = JS("""[{
    ftype: "rowbody",
    getAdditionalData: function (data, idx, record, orig) {
        return { rowBodyColspan: record.getFields().length, rowBody: '<p>' + data.Notes + '</p>' };
    }
}]""")


@dataclass
class Plant:
    common: str
    botanical: str
    zone: str
    color_code: str
    light: str
    price: float
    availability: date
    indoor: bool

    @property
    def notes(self) -> str:
        return (f"The <b>{self.common}</b> has the botanical name <i>{self.botanical}</i>, "
                f"costing US${self.price:.2f} and being more appropriate to be in a "
                f"{self.light.lower()} environment. It is fresh in stock, production since "
                f"{self.availability.strftime('%B %d, %Y')}. It is "
                f"{'okay' if self.indoor else '<b>not recommended</b>'} to be grown indoors.")

    def to_row(self) -> dict:
        # System.Text.Json serializa con PascalCase: el cliente espera esas claves
        return {"Common": self.common, "Botanical": self.botanical, "Zone": self.zone,
                "ColorCode": self.color_code, "Light": self.light, "Price": self.price,
                "Availability": self.availability.isoformat(), "Indoor": self.indoor,
                "Notes": self.notes}


def get_plants() -> list[Plant]:
    today = date.today()
    y = today.year - (1 if today.month <= 8 else 0)
    raw = [
        ("Bloodroot", "Sanguinaria canadensis", "4", "E7E7E7", "Mostly Shady", 2.44, (3, 15), True),
        ("Columbine", "Aquilegia canadensis", "3", "E7E7E7", "Mostly Shady", 9.37, (3, 6), True),
        ("Marsh Marigold", "Caltha palustris", "4", "F5F5F5", "Mostly Sunny", 6.81, (5, 17), False),
        ("Cowslip", "Caltha palustris", "4", "E7E7E7", "Mostly Shady", 9.90, (3, 6), True),
        ("Dutchman's-Breeches", "Dicentra cucullaria", "3", "E7E7E7", "Mostly Shady", 6.44, (1, 20), True),
        ("Ginger, Wild", "Asarum canadense", "3", "E7E7E7", "Mostly Shady", 9.03, (4, 18), True),
        ("Hepatica", "Hepatica americana", "4", "E7E7E7", "Mostly Shady", 4.45, (1, 26), True),
        ("Liverleaf", "Hepatica americana", "4", "E7E7E7", "Mostly Shady", 3.99, (1, 2), True),
        ("Jack-In-The-Pulpit", "Arisaema triphyllum", "4", "E7E7E7", "Mostly Shady", 3.23, (2, 1), True),
        ("Mayapple", "Podophyllum peltatum", "3", "E7E7E7", "Mostly Shady", 2.98, (6, 5), True),
        ("Phlox, Woodland", "Phlox divaricata", "3", "EEEEEE", "Sun or Shade", 2.80, (1, 22), False),
        ("Phlox, Blue", "Phlox divaricata", "3", "EEEEEE", "Sun or Shade", 5.59, (2, 16), False),
        ("Spring-Beauty", "Claytonia Virginica", "7", "E7E7E7", "Mostly Shady", 6.59, (2, 1), True),
        ("Trillium", "Trillium grandiflorum", "5", "EEEEEE", "Sun or Shade", 3.90, (4, 29), False),
        ("Wake Robin", "Trillium grandiflorum", "5", "EEEEEE", "Sun or Shade", 3.20, (2, 21), False),
        ("Violet, Dog-Tooth", "Erythronium americanum", "4", "E1E1E1", "Shade", 9.04, (2, 1), True),
        ("Trout Lily", "Erythronium americanum", "4", "E1E1E1", "Shade", 6.94, (3, 24), True),
        ("Adder's-Tongue", "Erythronium americanum", "4", "E1E1E1", "Shade", 9.58, (4, 13), True),
        ("Anemone", "Anemone blanda", "6", "E7E7E7", "Mostly Shady", 8.86, (12, 26), True),
        ("Grecian Windflower", "Anemone blanda", "6", "E7E7E7", "Mostly Shady", 9.16, (7, 10), True),
        ("Bee Balm", "Monarda didyma", "4", "E1E1E1", "Shade", 4.59, (5, 3), True),
        ("Bergamot", "Monarda didyma", "4", "E1E1E1", "Shade", 7.16, (4, 27), True),
        ("Black-Eyed Susan", "Rudbeckia hirta", "Annual", "FFFFFF", "Sunny", 9.80, (6, 18), False),
        ("Buttercup", "Ranunculus", "4", "E1E1E1", "Shade", 2.57, (6, 10), True),
        ("Crowfoot", "Ranunculus", "4", "E1E1E1", "Shade", 9.34, (4, 3), True),
        ("Butterfly Weed", "Asclepias tuberosa", "Annual", "FFFFFF", "Sunny", 2.78, (6, 30), False),
        ("Cinquefoil", "Potentilla", "Annual", "E1E1E1", "Shade", 7.06, (5, 25), True),
        ("Primrose", "Oenothera", "3 - 5", "FFFFFF", "Sunny", 6.56, (1, 30), False),
        ("Gentian", "Gentiana", "4", "EEEEEE", "Sun or Shade", 7.81, (5, 18), False),
        ("Blue Gentian", "Gentiana", "4", "EEEEEE", "Sun or Shade", 8.56, (5, 2), False),
        ("Jacob's Ladder", "Polemonium caeruleum", "Annual", "E1E1E1", "Shade", 9.26, (2, 21), True),
        ("Greek Valerian", "Polemonium caeruleum", "Annual", "E1E1E1", "Shade", 4.36, (7, 14), True),
        ("California Poppy", "Eschscholzia californica", "Annual", "FFFFFF", "Sunny", 7.89, (3, 27), False),
        ("Shooting Star", "Dodecatheon", "Annual", "E7E7E7", "Mostly Shady", 8.60, (5, 13), True),
        ("Snakeroot", "Cimicifuga", "Annual", "E1E1E1", "Shade", 5.63, (7, 11), True),
    ]
    return [Plant(c, b, z, cc, l, p, date(y, m, d), i) for c, b, z, cc, l, p, (m, d), i in raw]


def plants_paging(start: int, limit: int, sort: str | None, direction: str) -> dict:
    rows = [p.to_row() for p in get_plants()]
    if sort and rows and sort in rows[0]:
        # CaseInsensitiveComparer.Default.Compare(a, b) * direction
        key = (lambda r: r[sort].lower()) if isinstance(rows[0][sort], str) else (lambda r: r[sort])
        rows.sort(key=key, reverse=(direction == "DESC"))
    page_rows = rows if start < 0 or limit < 0 else rows[start:start + limit]
    return {"Data": page_rows, "TotalRecords": len(rows)}


@page.route("/ReadData")
def read_data():
    start = request.args.get("start", 0, type=int)
    limit = request.args.get("limit", -1, type=int)
    sort_info = (json.loads(request.args.get("sort", "[]")) or [{}])[0]
    return jsonify(plants_paging(start, limit, sort_info.get("property"), sort_info.get("direction", "ASC")))


@page.on_get
def on_get():
    grid = GridPanel(
        title="Plants",
        frame=True,
        store=Store(
            remote_sort=True,
            page_size=5,
            auto_load=True,
            proxy=AjaxProxy(page.url("ReadData"), root_property="Data", total_property="TotalRecords"),
            fields=[
                DataField("Common", type="String"), DataField("Botanical", type="String"),
                DataField("Zone", type="Int"), DataField("ColorCode", type="String"),
                DataField("Price", type="Float"), DataField("Availability", type="Date"),
                DataField("Indoor", type="Bool"), DataField("Notes", type="String"),
            ],
            sorters=[Sorter("Common", "ASC")],
        ),
        columns=[
            Column(data_index="Common", text="Common Name", flex=1, renderer=JS("commonNameRenderer")),
            Column(data_index="Botanical", text="Botanical", width=230),
            Column(data_index="Light", text="Light", width=130),
            Column(data_index="Price", text="Price", width=100, align="right"),
            DateColumn(data_index="Availability", text="Available", width=117, format="yyyy-MM-dd"),
            Column(data_index="Indoor", text="Indoor?", width=90),
        ],
        sel_model={"type": "rowmodel", "mode": "MULTI"},
        features=GRID_FEATURES,
        bbar=PagingToolbar(display_info=True, display_msg="Displaying plants {0} - {1} of {2}",
                           empty_msg="No plants to display"),
    )
    body = ("<h1>Grid Panel with remote Paging and Sorting</h1>"
            "<p>The grid below pulls every displayed page from the server.</p>"
            "<p>When sorting, it requests the page again so the server can provide the correct "
            "page contents given that sorting order.</p>")
    return PageResult(grid, head=HEAD, body=body)
