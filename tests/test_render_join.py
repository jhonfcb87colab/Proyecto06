import os
import re
import tempfile
import unittest


class RenderJoinTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls._tmp = tempfile.TemporaryDirectory()
        os.environ["BIWEB_VAR"] = cls._tmp.name
        os.environ["BIWEB_DEMO_USERS"] = "0"
        from biweb.app import app

        cls.app = app

    @classmethod
    def tearDownClass(cls):
        cls._tmp.cleanup()

    def login(self):
        client = self.app.test_client()
        page = client.get("/login").get_data(as_text=True)
        match = re.search(r'name="csrf_token" value="([^"]+)"', page)
        self.assertIsNotNone(match)
        response = client.post(
            "/login",
            data={
                "username": "admin",
                "password": os.environ.get("BIWEB_ADMIN_PASSWORD", "admin123"),
                "csrf_token": match.group(1),
            },
        )
        self.assertIn(response.status_code, (301, 302))
        with client.session_transaction() as session:
            csrf = session["csrf"]
        return client, {
            "X-BI-Mode": "design",
            "X-CSRF-Token": csrf,
            "Content-Type": "application/json",
        }

    def test_saved_measure_with_related_table_renders_in_widget(self):
        client, headers = self.login()
        datasets = client.get("/api/datasets", headers={"X-BI-Mode": "design"}).get_json()
        primary = datasets[0]

        response = client.post(
            "/api/datasets",
            headers=headers,
            json={
                "connection_id": primary["connection_id"],
                "name": "Regiones de prueba",
                "sql": "SELECT DISTINCT region FROM sales ORDER BY region",
            },
        )
        self.assertIn(response.status_code, (200, 201))
        related = response.get_json()

        expression = 'sum_field(merge(rows, t2, "region", "region", "left"), "revenue")'
        response = client.post(
            "/api/model/items",
            headers=headers,
            json={
                "kind": "measure",
                "dataset_id": primary["id"],
                "name": "Ingreso cruzado",
                "expression": expression,
                "config": {
                    "tables": [
                        {
                            "id": related["id"],
                            "alias": "t2",
                            "left_key": "region",
                            "right_key": "region",
                            "how": "left",
                        }
                    ]
                },
            },
        )
        self.assertIn(response.status_code, (200, 201))
        model = response.get_json()
        self.assertEqual(model["config"]["tables"][0]["left_key"], "region")

        dashboard = client.post(
            "/api/dashboards",
            headers=headers,
            json={"name": "Cruce de prueba", "description": ""},
        ).get_json()
        widget = client.post(
            f"/api/dashboards/{dashboard['id']}/widgets",
            headers=headers,
            json={
                "dataset_id": primary["id"],
                "title": "Ingreso cruzado",
                "chart_type": "kpi",
                "config": {"model_item_id": model["id"]},
                "w": 3,
                "h": 2,
            },
        ).get_json()

        payload = client.get(f"/api/dashboards/{dashboard['id']}/render").get_json()
        rendered = next(item for item in payload["widgets"] if item["id"] == widget["id"])
        self.assertFalse((rendered["chart_data"] or {}).get("error"))
        self.assertGreater(rendered["chart_data"]["value"], 0)


if __name__ == "__main__":
    unittest.main()
