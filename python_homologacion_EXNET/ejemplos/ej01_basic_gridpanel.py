"""
EJEMPLO 1 - GridPanel declarativo (markup -> Python)
Original: src/Pages/samples/kitchen_sink/gridpanels/basic_gridpanel/index.cshtml

    <ext-gridPanel title="Restaurants" frame="true" width="480" height="360">
        <store>
            <ext-store data="KitchenSink.Restaurants.GetAllRestaurants()">
                <model><ext-model><fields>
                    <ext-dataField name="name" /> ...
                    <ext-dataField name="rating" type="Int" />
                </fields></ext-model></model>
                <sorters>
                    <ext-sorter property="cuisine" direction="DESC" />
                    <ext-sorter property="name" />
                </sorters>
            </ext-store>
        </store>
        <columns>
            <ext-column text="Name" flex="1" dataIndex="name" />
            <ext-column text="Cuisine" flex="1" dataIndex="cuisine" />
        </columns>
    </ext-gridPanel>

Regla de homologación: cada etiqueta <ext-X> es una clase X(...), cada atributo
es un kwarg snake_case, y cada elemento hijo (<store>, <columns>) es un kwarg.
"""
from extpy import Column, DataField, ExtPage, GridPanel, PageResult, Sorter, Store

from .kitchen_sink_data import get_all_restaurants

page = ExtPage("kitchen_sink/gridpanels/basic_gridpanel", "Basic GridPanel", __file__)


@page.on_get
def on_get():
    grid = GridPanel(
        title="Restaurants",
        frame=True,
        width=480,
        height=360,
        store=Store(
            data=get_all_restaurants(),      # dataclasses -> JSON camelCase, como Ext.NET
            fields=[
                DataField("name"),
                DataField("cuisine"),
                DataField("description"),
                DataField("rating", type="Int"),
            ],
            sorters=[Sorter("cuisine", "DESC"), Sorter("name")],
        ),
        columns=[
            Column(text="Name", flex=1, data_index="name"),
            Column(text="Cuisine", flex=1, data_index="cuisine"),
        ],
    )
    return PageResult(grid)
