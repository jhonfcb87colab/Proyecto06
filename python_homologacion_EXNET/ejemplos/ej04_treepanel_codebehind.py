"""
EJEMPLO 4 - TreePanel construido desde objetos de dominio + Listeners
Original: src/Pages/samples/treepanel/basic/built_in_codebehind/index.cshtml.cs

    Listeners = new TreePanelListenerCollection() {
        ItemClick = new ItemClickListener() {
            Handler = "App.lblStatus.setHtml('Node Selected: ...' + record.get('text') ...)" },
        AfterItemExpand = new AfterItemExpandListener() { Handler = "...node.get('text')...",
                                                          Buffer = 30 },
    }

Ingeniería inversa: Ext.NET envuelve cada ``Handler`` en
``function (item, record, node, index, e) { ... }`` según la firma del evento
en Ext JS; por eso el handler puede usar ``record`` o ``node`` directamente.
``Listener`` replica esa tabla de firmas (extpy.components.EVENT_ARGS).
"""
from dataclasses import dataclass, field
from enum import Enum

from extpy import Button, ExtPage, Label, Listener, TreeNode, TreePanel

page = ExtPage("treepanel/basic/built_in_codebehind", "TreePanel built using Python", __file__)


class CompositionType(Enum):
    CONCERTOS = "Concertos"
    QUARTETS = "Quartets"
    SONATAS = "Sonatas"
    SYMPHONIES = "Symphonies"


@dataclass
class Composition:
    type: CompositionType
    pieces: list[str] = field(default_factory=list)


@dataclass
class Composer:
    name: str
    compositions: list[Composition] = field(default_factory=list)


def get_data() -> list[Composer]:
    C = CompositionType
    return [
        Composer("Beethoven", [
            Composition(C.CONCERTOS, ["No. 1 - C", "No. 2 - B-Flat Major", "No. 3 - C Minor",
                                      "No. 4 - G Major", "No. 5 - E-Flat Major"]),
            Composition(C.QUARTETS, ["Six String Quartets", "Three String Quartets",
                                     "Grosse Fugue for String Quartets"]),
            Composition(C.SONATAS, ["Sonata in A Minor", "sonata in F Major"]),
            Composition(C.SYMPHONIES, ["No. 1 - C Major", "No. 2 - D Major", "No. 3 - E-Flat Major",
                                       "No. 4 - B-Flat Major", "No. 5 - C Minor", "No. 6 - F Major",
                                       "No. 7 - A Major", "No. 8 - F Major", "No. 9 - D Minor"]),
        ]),
        Composer("Brahms", [
            Composition(C.CONCERTOS, ["Violin Concerto", "Double Concerto - A Minor",
                                      "Piano Concerto No. 1 - D Minor",
                                      "Piano Concerto No. 2 - B-Flat Major"]),
            Composition(C.QUARTETS, ["Piano Quartet No. 1 - G Minor", "Piano Quartet No. 2 - A Major",
                                     "Piano Quartet No. 3 - C Minor",
                                     "Piano Quartet No. 3 - B-Flat Minor"]),
            Composition(C.SONATAS, ["Two Sonatas for Clarinet - F Minor",
                                    "Two Sonatas for Clarinet - E-Flat Major"]),
            Composition(C.SYMPHONIES, ["No. 1 - C Minor", "No. 2 - D Minor", "No. 3 - F Major",
                                       "No. 4 - E Minor"]),
        ]),
        Composer("Mozart", [
            Composition(C.CONCERTOS, ["Piano Concerto No. 12", "Piano Concerto No. 17",
                                      "Clarinet Concerto", "Violin Concerto No. 5",
                                      "Violin Concerto No. 4"]),
        ]),
    ]


def build_tree():
    return TreeNode("Composers", expanded=True, children=[
        TreeNode(composer.name, children=[
            TreeNode(composition.type.value, children=[
                TreeNode(piece, leaf=True) for piece in composition.pieces
            ])
            for composition in composer.compositions
        ])
        for composer in get_data()
    ])


@page.on_get
def on_get():
    return TreePanel(
        id="TreePanel1",
        title="Catalog",
        width=480,
        height=600,
        frame=True,
        scrollable=True,
        tbar=[
            Button(text="Expand All", listeners={"click": Listener("App.TreePanel1.expandAll();")}),
            Button(text="Collapse All", listeners={"click": Listener("App.TreePanel1.collapseAll();")}),
        ],
        bbar=[Label(id="lblStatus", html="&nbsp;")],
        root=build_tree(),
        listeners={
            "itemclick": Listener(
                "App.lblStatus.setHtml('Node Selected: <strong>' + record.get('text') + '</strong>');"),
            "afteritemexpand": Listener(
                "App.lblStatus.setHtml('Node Expanded: <strong>' + node.get('text') + '</strong>');",
                buffer=30),
            "afteritemcollapse": Listener(
                "App.lblStatus.setHtml('Node Collapsed: <strong>' + node.get('text') + '</strong>');",
                buffer=30),
        },
    )
