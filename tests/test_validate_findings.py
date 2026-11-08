"""Behavioral tests for the offline, standard-library ledger validator."""

import copy
import importlib.util
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "skills" / "wuhan-gangwan-report-review" / "scripts" / "validate_findings.py"
EXAMPLE = ROOT / "examples" / "findings.synthetic.json"
SPEC = importlib.util.spec_from_file_location("validate_findings", SCRIPT)
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)


class LedgerTests(unittest.TestCase):
    def setUp(self):
        self.ledger = json.loads(EXAMPLE.read_text(encoding="utf-8"))

    def errors(self):
        return MODULE.validate(self.ledger)

    def cli(self, raw, *args):
        return subprocess.run([sys.executable, str(SCRIPT), "-", *args], input=raw,
                              stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=False)

    def test_example_and_empty_findings_pass(self):
        self.assertEqual(self.errors(), [])
        self.ledger["findings"] = []
        self.assertEqual(self.errors(), [])

    def test_unique_ids_are_enforced(self):
        self.ledger["findings"].append(copy.deepcopy(self.ledger["findings"][0]))
        self.assertTrue(any("ID 重复" in error for error in self.errors()))

    def test_schema_version_is_exact_integer_one(self):
        for bad in [True, 1.0, "1", 2, None]:
            with self.subTest(bad=bad):
                self.ledger["schema_version"] = bad
                self.assertTrue(self.errors())

    def test_sha256_format_and_source_types(self):
        for bad in ["g" * 64, "a" * 63, "a" * 65, 0, None]:
            with self.subTest(bad=bad):
                self.ledger["source"]["sha256"] = bad
                self.assertTrue(self.errors())
        self.ledger["source"]["sha256"] = "ABCDEF0123456789" * 4
        self.assertEqual(self.errors(), [])
        self.ledger["source"] = []
        self.assertTrue(self.errors())

    def test_enums_and_required_fields(self):
        original = copy.deepcopy(self.ledger)
        for key, value in [("category", "unknown"), ("severity", "high"), ("status", "done"),
                           ("category", []), ("observed", " "), ("action", None)]:
            with self.subTest(key=key, value=value):
                self.ledger = copy.deepcopy(original)
                self.ledger["findings"][0][key] = value
                self.assertTrue(self.errors())
        self.ledger = original
        del self.ledger["findings"][0]["basis"]
        self.assertTrue(self.errors())

    def test_unknown_fields_do_not_hide_typographical_errors(self):
        self.ledger["findings"][0]["statuz"] = "confirmed"
        self.assertTrue(any("statuz" in error for error in self.errors()))

    def test_single_anchor_not_array(self):
        self.ledger["findings"][0]["anchor"] = [{"format": "pdf", "quote": "示例"}]
        self.assertTrue(self.errors())

    def test_anchor_needs_quote_or_locator_not_just_page(self):
        anchor = {"format": "pdf", "page1": 1}
        self.ledger["findings"][0]["anchor"] = anchor
        self.assertTrue(self.errors())
        anchor["quote"] = "虚构内容"
        self.assertEqual(self.errors(), [])
        del anchor["quote"]
        anchor["locator"] = "表1第2行"
        self.assertEqual(self.errors(), [])
        anchor["quote"] = " "
        self.assertTrue(self.errors())

    def test_pages_are_positive_integer_not_boolean(self):
        anchor = self.ledger["findings"][0]["anchor"]
        for value in [0, -1, 1.2, True, "2", None]:
            with self.subTest(value=value):
                anchor["page1"] = value
                self.assertTrue(self.errors())
        del anchor["page1"]
        self.assertEqual(self.errors(), [])

    def test_valid_formats_and_docx_locator(self):
        for fmt in ["pdf", "doc", "docx"]:
            self.ledger["findings"][0]["anchor"] = {"format": fmt, "locator": "虚构表1第1格"}
            self.assertEqual(self.errors(), [])
        self.ledger["findings"][0]["anchor"]["format"] = "txt"
        self.assertTrue(self.errors())

    def test_bbox_numeric_finite_order_and_dimension(self):
        anchor = self.ledger["findings"][0]["anchor"]
        bad_boxes = [[1, 2, 3], [1, 2, 3, 4, 5], [0, 0, 0, 1], [0, 2, 1, 1],
                     [-1, 0, 1, 1], [0, False, 1, 1], [0, 0, "1", 1],
                     [0, 0, float("inf"), 1], [0, float("nan"), 1, 2], "0,0,1,1"]
        for value in bad_boxes:
            with self.subTest(value=value):
                anchor["bbox"] = value
                self.assertTrue(self.errors())
        anchor["bbox"] = [0, 0.5, 12.25, 24]
        self.assertEqual(self.errors(), [])

    def test_confirmed_standard_requires_verified_true(self):
        finding = self.ledger["findings"][1]
        finding["status"] = "confirmed"
        self.assertTrue(self.errors())
        finding["basis"][0]["verified"] = True
        self.assertEqual(self.errors(), [])
        for value in ["true", 1, None]:
            finding["basis"][0]["verified"] = value
            self.assertTrue(self.errors())

    def test_unverified_standard_allowed_for_pending_or_conditional(self):
        finding = self.ledger["findings"][1]
        for status in ["pending", "conditional"]:
            finding["status"] = status
            finding["basis"][0]["verified"] = False
            self.assertEqual(self.errors(), [])

    def test_basis_types_and_unknown_fields(self):
        finding = self.ledger["findings"][0]
        for value in [None, {}, [None], [{"kind": "law", "citation": "演示", "verified": True}]]:
            with self.subTest(value=value):
                finding["basis"] = value
                self.assertTrue(self.errors())
        finding["basis"] = []
        self.assertEqual(self.errors(), [])

    def test_calculation_types_not_truth_or_expression_execution(self):
        calc = self.ledger["findings"][0]["calculation"]
        calc["expression"] = "DO NOT EXECUTE THIS TEXT"
        calc["result"] = -987  # Intentionally wrong arithmetic still structurally valid.
        self.assertEqual(self.errors(), [])
        calc["result"] = True
        self.assertTrue(self.errors())
        calc["result"] = 90
        calc["inputs"]["total"] = float("inf")
        self.assertTrue(self.errors())
        calc["inputs"]["total"] = "20"
        self.assertTrue(self.errors())

    def test_parser_rejects_nonfinite_constants_and_duplicate_keys(self):
        for text in ["NaN", "Infinity", "-Infinity", '{"x":1,"x":2}']:
            with self.subTest(text=text):
                with self.assertRaises(ValueError):
                    MODULE.parse_json(text)

    def test_overflowing_json_number_is_rejected_after_parsing(self):
        raw = json.dumps(self.ledger).replace('"result": 90', '"result": 1e999')
        self.assertTrue(MODULE.validate(MODULE.parse_json(raw)))

    def test_cli_bom_and_chinese_output_are_utf8(self):
        result = self.cli(b"\xef\xbb\xbf" + json.dumps(self.ledger, ensure_ascii=False).encode("utf-8"))
        self.assertEqual(result.returncode, 0, result.stderr.decode("utf-8"))
        self.assertIn("结构校验通过", result.stdout.decode("utf-8"))
        self.assertEqual(result.stderr, b"")

    def test_cli_structure_error_is_one_and_json_result_is_parseable(self):
        self.ledger["findings"][0]["id"] = ""
        result = self.cli(json.dumps(self.ledger).encode("utf-8"), "--json")
        self.assertEqual(result.returncode, 1)
        response = json.loads(result.stdout.decode("utf-8"))
        self.assertFalse(response["valid"])
        self.assertTrue(response["errors"])
        self.assertIn("仅检查", response["limitation"])

    def test_cli_parse_and_encoding_errors_are_two(self):
        for raw in [b"{", b"\xff", b"NaN"]:
            with self.subTest(raw=raw):
                result = self.cli(raw, "--json")
                self.assertEqual(result.returncode, 2)
                self.assertFalse(json.loads(result.stdout.decode("utf-8"))["valid"])
                self.assertNotIn(b"Traceback", result.stderr)

    def test_cli_missing_file_and_no_writes(self):
        with tempfile.TemporaryDirectory() as folder:
            directory = Path(folder)
            result = subprocess.run([sys.executable, str(SCRIPT), str(directory / "missing.json")],
                                    capture_output=True, check=False)
            self.assertEqual(result.returncode, 2)
            self.assertEqual(list(directory.iterdir()), [])
            self.assertNotIn(b"Traceback", result.stderr)

    def test_cli_file_read_preserves_ledger_bytes(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "纯虚构台账.json"
            raw = EXAMPLE.read_bytes()
            path.write_bytes(raw)
            result = subprocess.run([sys.executable, str(SCRIPT), str(path), "--json"],
                                    capture_output=True, check=False)
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertEqual(path.read_bytes(), raw)
            self.assertEqual(list(Path(folder).iterdir()), [path])


if __name__ == "__main__":
    unittest.main()
