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


if __name__ == "__main__":
    unittest.main()
