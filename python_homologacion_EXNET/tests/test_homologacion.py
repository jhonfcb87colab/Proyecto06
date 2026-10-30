"""Pruebas de la homologación. Ejecutar: python -m unittest discover -s tests -v"""
import json
import sys
import unittest
from dataclasses import dataclass
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app import create_app  # noqa: E402
from extpy import JS, Listener, Panel, camel, net_date_format, to_js  # noqa: E402
from ejemplos import ej07_directevent_duration_messages as ej07  # noqa: E402


class SerializerTests(unittest.TestCase):
    def test_camel_case(self):
        self.assertEqual(camel("body_padding"), "bodyPadding")
        self.assertEqual(camel("data_index"), "dataIndex")
        self.assertEqual(camel("title"), "title")

    def test_net_date_format(self):
        self.assertEqual(net_date_format("yyyy-MM-dd"), "Y-m-d")
        self.assertEqual(net_date_format("MMMM dd, yyyy HH:mm"), "F d, Y H:i")

    def test_raw_js_is_not_quoted(self):
        self.assertEqual(to_js({"renderer": JS("Ext.util.Format.usMoney")}).replace("\n", "").replace(" ", ""),
                         '{"renderer":Ext.util.Format.usMoney}')

    def test_dataclass_is_camel_cased_like_extnet(self):
        @dataclass
        class Company:
            pct_change: float

        self.assertIn('"pctChange": 1.5', to_js(Company(1.5)))

    def test_component_config(self):
        cfg = Panel(title="West", body_padding=18, region="west").to_config()
        self.assertEqual(cfg, {"xtype": "panel", "title": "West", "bodyPadding": 18, "region": "west"})

    def test_listener_wraps_handler_with_event_signature(self):
        fn = Listener("record.get('text');", buffer=30).render("itemclick")
        self.assertEqual(fn["buffer"], 30)
        self.assertIn("function (item, record, node, index, e)", fn["fn"])


class PagesTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.client = create_app().test_client()

    def get(self, url):
        resp = self.client.get(url)
        self.assertEqual(resp.status_code, 200, url)
        return resp.get_data(as_text=True)

    def test_all_pages_render(self):
        expectations = {
            "/samples/kitchen_sink/gridpanels/basic_gridpanel/": ['"xtype": "grid"', '"Cheesecake Factory"'],
            "/samples/kitchen_sink/forms/login/": ['"xtype": "viewport"', '"inputType": "password"'],
            "/samples/layout/borderlayout/complex_in_codebehind/": ['"layout": "border"', '"region": "west"'],
            "/samples/treepanel/basic/built_in_codebehind/": ['"Beethoven"', "node.get('text')"],
            "/samples/gridpanel/editable/editor_with_directmethod/": ["App.direct.Edit = function (id, field, oldValue, newValue, opts)", '"format": "Y-m-d"'],
            "/samples/gridpanel/paging_and_sorting/page/": ['"type": "ajax"', '"rootProperty": "Data"'],
            "/samples/events/directevents/duration_messages/": ['ExtPy.request("DoSomething"', "App.direct.SomeDirectMethod = function (opts)"],
            "/samples/explorer/": ['"xtype": "treepanel"', "/samples/kitchen_sink/forms/login/"],
        }
        for url, needles in expectations.items():
            html = self.get(url)
            for needle in needles:
                self.assertIn(needle, html, f"{url}: falta {needle}")

    def test_direct_method_edit(self):
        resp = self.client.post("/samples/gridpanel/editable/editor_with_directmethod/direct/Edit",
                                json={"id": 3, "field": "price", "oldValue": 1, "newValue": 2})
        body = resp.get_json()
        self.assertIn("Ext.toast(", body["script"])
        self.assertIn("Edit Record #3", body["script"])
        self.assertIn("App.GridPanel1.getStore().commitChanges();", body["script"])

    def test_remote_paging_and_sorting(self):
        sort = json.dumps([{"property": "Price", "direction": "DESC"}])
        data = self.client.get("/samples/gridpanel/paging_and_sorting/page/ReadData",
                               query_string={"start": 5, "limit": 5, "sort": sort}).get_json()
        self.assertEqual(data["TotalRecords"], 35)
        self.assertEqual(len(data["Data"]), 5)
        prices = [r["Price"] for r in data["Data"]]
        self.assertEqual(prices, sorted(prices, reverse=True))

    def test_direct_event_handler(self):
        ej07.SLEEP_SECONDS = 0
        resp = self.client.post("/samples/events/directevents/duration_messages/direct/DoSomething", json={})
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.get_json(), {"script": "", "result": None})

    def test_unknown_direct_handler(self):
        resp = self.client.post("/samples/kitchen_sink/forms/login/direct/Nope", json={})
        self.assertEqual(resp.status_code, 404)

    def test_source_view(self):
        self.assertIn("ExtPage(", self.get("/source/kitchen_sink/forms/login"))


if __name__ == "__main__":
    unittest.main()
