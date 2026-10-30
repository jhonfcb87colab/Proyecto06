"""
EJEMPLO 3 - BorderLayout construido en "code-behind" (estilo imperativo)
Original: src/Pages/samples/layout/borderlayout/complex_in_codebehind/index.cshtml.cs

    var west = new Panel { Title = "West", Region = RegionType.West, Width = 270,
                           Collapsible = true, Layout = LayoutType.Accordion };
    west.Items.Add(pnlNavigation);
    ...
    Window1 = new Window { Title = "Complex Layout", Layout = LayoutType.Border,
                           Items = { west, east, center, south } };

    // index.cshtml
    <ext-window model="Model.Window1" />

Notas:
  * ``Variant = Variant.Light`` y ``Rounded = false`` son propiedades exclusivas
    del tema Spotless de Ext.NET; no existen en Ext JS y se omiten.
  * ``TabPosition = Dock.Bottom`` -> tab_position="bottom".
"""
from extpy import ExtPage, Panel, TabPanel, Window

page = ExtPage("layout/borderlayout/complex_in_codebehind", "Complex BorderLayout", __file__)


@page.on_get
def on_get():
    # WEST REGION
    west = Panel(title="West", region="west", width=270, max_width=360,
                 collapsible=True, layout="accordion")
    west.add(
        Panel(title="Navigation", body_padding=18, html="Navigation"),
        Panel(title="Settings", body_padding=18, html="Some settings in here"),
    )

    # CENTER REGION
    center = TabPanel(active_tab=0, region="center", plain=True)
    center.add(
        Panel(title="Center Tab 1", body_padding=18, html="Hello ..."),
        Panel(title="Center Tab 2", body_padding=18, html="... World"),
    )

    # EAST REGION
    east = Panel(title="East", region="east", width=270, min_width=180,
                 layout="fit", collapsible=True)
    tp_east = TabPanel(active_tab=1, tab_position="bottom", plain=True)
    tp_east.add(
        Panel(title="Tab 1", body_padding=18, html="East Tab 1"),
        Panel(title="Tab 2", body_padding=18, html="East Tab 2"),
    )
    east.add(tp_east)

    # SOUTH REGION
    south = Panel(title="South", height=180, body_padding=18, html="South",
                  collapsible=True, collapsed=True, region="south")

    # MAIN WINDOW
    window1 = Window(
        title="Complex Layout",
        width=960,
        height=640,
        auto_show=True,
        collapsible=True,
        layout="border",
        items=[west, east, center, south],
    )
    return window1
