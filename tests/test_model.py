import unittest

from biweb.model import ModelError, evaluate, preview, validate_expression


class ModelExpressionTests(unittest.TestCase):
    def setUp(self):
        self.rows = [
            {"revenue": 100, "margin": 20, "units": 12, "price": 5},
            {"revenue": 50, "margin": 10, "units": 4, "price": 8},
        ]

    def test_measure_expression_uses_python_helpers(self):
        self.assertEqual(evaluate('sum_field(rows, "revenue")', self.rows), 150.0)
        self.assertEqual(
            evaluate('pct(sum_field(rows, "margin"), sum_field(rows, "revenue"))', self.rows),
            20.0,
        )

    def test_column_expression_receives_current_row(self):
        result = preview(
            "column",
            'field(row, "price", 0) * 1.19',
            self.rows,
            ["price"],
            {"name": "price_with_tax"},
        )
        self.assertAlmostEqual(result["rows"][0]["price_with_tax"], 5.95)
        self.assertAlmostEqual(result["rows"][1]["price_with_tax"], 9.52)

    def test_invalid_syntax_is_rejected_before_save(self):
        with self.assertRaises(ModelError):
            validate_expression("sum_field(rows,")

    def test_arbitrary_python_is_not_an_allowed_expression(self):
        with self.assertRaises(ModelError):
            validate_expression("__import__('os').getcwd()")

    def test_expression_rejects_unknown_names(self):
        with self.assertRaises(ModelError):
            validate_expression("unknown_function(rows)")

    def test_merge_can_cross_two_tables(self):
        clients = [{"id": 1, "segment": "A"}, {"id": 2, "segment": "B"}]
        orders = [{"client_id": 1, "total": 10}, {"client_id": 1, "total": 25}, {"client_id": 9, "total": 7}]
        merged = evaluate(
            'merge(rows, t2, "client_id", "id")',
            orders,
            tables={"t2": clients},
        )
        self.assertEqual([row["total"] for row in merged], [10, 25])
        self.assertEqual([row["segment"] for row in merged], ["A", "A"])
        self.assertEqual(
            evaluate('sum_field(merge(rows, t2, "client_id", "id"), "total")', orders, tables={"t2": clients}),
            35.0,
        )

    def test_merge_supports_left_and_right_joins(self):
        left = [{"id": 1, "value": 10}, {"id": 2, "value": 20}]
        right = [{"id": 1, "label": "uno"}, {"id": 3, "label": "tres"}]
        left_join = evaluate('merge(rows, t2, "id", "id", "left")', left, tables={"t2": right})
        right_join = evaluate('merge(rows, t2, "id", "id", "right")', left, tables={"t2": right})
        self.assertEqual(len(left_join), 2)
        self.assertEqual(len(right_join), 2)
        self.assertEqual(right_join[-1]["label"], "tres")

    def test_join_shortcuts(self):
        clients = [{"id": 1, "segment": "A"}]
        orders = [{"client_id": 1, "total": 10}, {"client_id": 9, "total": 7}]
        self.assertEqual(
            len(evaluate('left_join(rows, t2, "client_id", "id")', orders, tables={"t2": clients})),
            2,
        )
        self.assertEqual(
            len(evaluate('inner_join(rows, t2, "client_id", "id")', orders, tables={"t2": clients})),
            1,
        )
        self.assertEqual(
            len(evaluate('outer_join(rows, t2, "client_id", "id")', orders, tables={"t2": clients})),
            2,
        )
        self.assertEqual(
            evaluate('union_tables(rows, t2)', self.rows, tables={"t2": clients}),
            self.rows + clients,
        )

    def test_append_and_cross_tables(self):
        other = [{"revenue": 25, "margin": 5}]
        appended = evaluate("append_rows(rows, t2)", self.rows, tables={"t2": other})
        crossed = evaluate("cross_tables(rows, t2)", self.rows, tables={"t2": other})
        self.assertEqual(len(appended), 3)
        self.assertEqual(len(crossed), 2)

    def test_table_calc_preview_accepts_related_tables(self):
        other = [{"id": 1, "name": "Norte"}]
        rows = [{"client_id": 1, "total": 10}]
        result = preview(
            "table_calc",
            'merge(rows, t2, "client_id", "id")',
            rows,
            ["client_id", "total"],
            tables={"t2": other},
        )
        self.assertEqual(result["columns"], ["client_id", "total", "id", "name"])
        self.assertEqual(result["rows"][0]["name"], "Norte")


if __name__ == "__main__":
    unittest.main()
