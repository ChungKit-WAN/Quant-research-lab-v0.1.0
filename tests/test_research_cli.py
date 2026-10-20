"""Offline CLI integration checks for reproducible, non-destructive reports."""

from contextlib import redirect_stderr, redirect_stdout
from copy import deepcopy
from dataclasses import asdict
import hashlib
from html import unescape
import io
import json
from pathlib import Path
import re
import tempfile
import unittest

import numpy as np
import pandas as pd

from quant_research.__main__ import main
from quant_research.report import export_report
from sector_backtest.pipeline import MonthlyConfig


def invoke(*arguments):
    stdout, stderr = io.StringIO(), io.StringIO()
    with redirect_stdout(stdout), redirect_stderr(stderr):
        status = main([str(argument) for argument in arguments])
    return status, stdout.getvalue(), stderr.getvalue()


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


class ResearchCliTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temporary = tempfile.TemporaryDirectory()
        cls.addClassCleanup(cls.temporary.cleanup)
        cls.root = Path(cls.temporary.name)
        cls.config = MonthlyConfig(
            tickers=("A", "B", "C", "D"), lookback=20,
            research_start="2024-03-01", holdout_start="2024-04-01",
            cost_bps=5.0, max_weight=0.6, initial_cash=100.0,
        )
        cls.config_path = cls.root / "monthly.json"
        cls.config_path.write_text(json.dumps(asdict(cls.config)), encoding="utf-8")
        cls.demo = cls.root / "demo"
        cls.demo_status, cls.demo_stdout, cls.demo_stderr = invoke(
            "demo", "--family", "etf", "--config", cls.config_path, "--output", cls.demo,
        )
        if cls.demo_status != 0:
            raise AssertionError(cls.demo_stderr)
        cls.results = json.loads((cls.demo / "results.json").read_text(encoding="utf-8"))
        cls.manifest = json.loads((cls.demo / "manifest.json").read_text(encoding="utf-8"))

    def test_demo_writes_report_and_manifest_hashes_match_actual_bytes(self):
        self.assertEqual(self.demo_status, 0)
        self.assertEqual(self.demo_stderr, "")
        self.assertIn("synthetic_demo", self.demo_stdout)
        self.assertIn(str((self.demo / "report.html").resolve()), self.demo_stdout)
        expected = {
            "report.html", "report_zh.html", "report_en.html",
            "results.json", "metrics.csv", "schedule.csv", "target_weights.csv",
            "demo_prices.csv", "manifest.json", "equal_weight_daily.csv",
            "sample_min_variance_daily.csv", "shrinkage_min_variance_daily.csv",
        }
        self.assertEqual({path.name for path in self.demo.iterdir()}, expected)
        self.assertEqual(set(self.manifest["artifacts_sha256"]), expected - {"manifest.json"})
        for name, expected_digest in self.manifest["artifacts_sha256"].items():
            with self.subTest(artifact=name):
                self.assertEqual(digest(self.demo / name), expected_digest)
        self.assertEqual(self.manifest["input_sha256"], digest(self.demo / "demo_prices.csv"))
        self.assertEqual(self.manifest["data_kind"], "synthetic_demo")
        self.assertEqual(self.results["data_kind"], "synthetic_demo")
        self.assertEqual(self.manifest["config"], self.results["config"])
        self.assertIn("SYNTHETIC DATA", self.manifest["limitations"][0])
        report_files = {"zh-CN": "report_zh.html", "en": "report_en.html"}
        self.assertEqual(self.manifest["report_files"], report_files)
        self.assertEqual(self.results["report_files"], report_files)
        self.assertEqual(self.manifest["report_languages"], ["zh-CN", "en"])
        self.assertEqual(self.results["report_languages"], ["zh-CN", "en"])
        self.assertEqual(self.results["limitations_bilingual"], self.manifest["limitations_bilingual"])
        self.assertEqual([pair["en"] for pair in self.manifest["limitations_bilingual"]], self.manifest["limitations"])
        entry = (self.demo / "report.html").read_text(encoding="utf-8")
        reports = {lang: (self.demo / name).read_text(encoding="utf-8")
                   for lang, name in report_files.items()}
        for lang, name in report_files.items():
            with self.subTest(language=lang):
                self.assertIn(f'href="{name}"', entry)
                self.assertRegex(reports[lang], rf'<html\b[^>]*\blang="{lang}"')
                links = re.findall(r'\bhref="([^"]+)"', reports[lang])
                self.assertTrue(links)
                for link in links:
                    if not re.match(r"[a-zA-Z][a-zA-Z0-9+.-]*:", link):
                        target = unescape(link).split("#", 1)[0]
                        if target:
                            self.assertTrue((self.demo / target).is_file(), target)
        zh_report, en_report = reports["zh-CN"], reports["en"]
        self.assertIn("SYNTHETIC DEMO", en_report)
        self.assertNotRegex(en_report, r"[\u3400-\u4dbf\u4e00-\u9fff]")
        for pair in self.manifest["limitations_bilingual"]:
            self.assertTrue(pair["zh"])
            self.assertIn(pair["zh"], unescape(zh_report))
            self.assertNotIn(pair["zh"], unescape(en_report))
            self.assertIn(pair["en"], unescape(en_report))
            self.assertNotIn(pair["en"], unescape(zh_report))
        for zh_label, en_label in (
            ("月度策略，共用交易账本", "Monthly strategies, shared portfolio accounting"),
            ("样本协方差最小方差", "Sample-covariance minimum variance"),
            ("完整研究期", "Full research period"),
            ("研究起始日期", "Research start date"),
        ):
            self.assertIn(zh_label, zh_report)
            self.assertNotIn(en_label, zh_report)
            self.assertIn(en_label, en_report)
            self.assertNotIn(zh_label, en_report)
        # Translation must leave chart series, scales and date labels unchanged.
        chart_series = [
            re.findall(r'<polyline\b[^>]*\bpoints="([^"]+)"', report)
            for report in (zh_report, en_report)
        ]
        self.assertEqual(len(chart_series[0]), 2 * len(self.results["strategies"]))
        self.assertEqual(chart_series[0], chart_series[1])
        chart_labels = [
            re.findall(r'<text\b[^>]*>([-+\d.]+(?:-\d+)*)</text>', report)
            for report in (zh_report, en_report)
        ]
        self.assertTrue(chart_labels[0])
        self.assertEqual(chart_labels[0], chart_labels[1])
        # The first two columns contain translated names; all performance cells match.
        performance_cells = []
        for report in (zh_report, en_report):
            rows = re.findall(r"<tr\b[^>]*>(.*?)</tr>", report, flags=re.S)
            performance_cells.append([
                [unescape(re.sub(r"<[^>]+>", "", cell)).strip() for cell in cells[2:]]
                for row in rows
                if len(cells := re.findall(r"<td\b[^>]*>(.*?)</td>", row, flags=re.S)) == 8
            ])
        self.assertEqual(len(performance_cells[0]), len(self.results["metrics"]))
        self.assertEqual(performance_cells[0], performance_cells[1])
        project = Path(__file__).resolve().parents[1]
        self.assertTrue(self.manifest["source_sha256"])
        for relative_path, expected_digest in self.manifest["source_sha256"].items():
            with self.subTest(source=relative_path):
                self.assertEqual(digest(project / relative_path), expected_digest)
        for package in ("python", "numpy", "pandas", "exchange-calendars", "yfinance"):
            self.assertTrue(self.manifest["versions"][package])

    def test_csv_rerun_reproduces_demo_signals_weights_metrics_and_ledger(self):
        output = self.root / "csv-rerun"
        status, stdout, stderr = invoke(
            "run", "--family", "etf", "--config", self.config_path,
            "--prices", self.demo / "demo_prices.csv", "--output", output,
        )
        self.assertEqual(status, 0, stderr)
        self.assertEqual(stderr, "")
        self.assertIn("user_supplied_adjusted_prices", stdout)
        result = json.loads((output / "results.json").read_text(encoding="utf-8"))
        for key in ("config", "schedule", "target_weights", "metrics", "period_status", "strategies"):
            with self.subTest(result=key):
                self.assertEqual(result[key], self.results[key])
        manifest = json.loads((output / "manifest.json").read_text(encoding="utf-8"))
        self.assertEqual(manifest["input_sha256"], self.manifest["input_sha256"])
        self.assertEqual(manifest["source_label"], "demo_prices.csv")
        self.assertEqual(manifest["data_kind"], "user_supplied_adjusted_prices")
        self.assertFalse((output / "demo_prices.csv").exists())

    def test_nonempty_output_is_rejected_without_changing_existing_evidence(self):
        before = {path.name: path.read_bytes() for path in self.demo.iterdir()}
        status, stdout, stderr = invoke(
            "demo", "--family", "etf", "--config", self.config_path, "--output", self.demo,
        )
        self.assertEqual(status, 2)
        self.assertEqual(stdout, "")
        self.assertIn("ERROR:", stderr)
        self.assertIn("Output must be new or empty", stderr)
        self.assertNotIn("Traceback", stderr)
        self.assertEqual({path.name: path.read_bytes() for path in self.demo.iterdir()}, before)

    def test_output_path_that_is_a_file_is_preserved(self):
        output = self.root / "existing-file"
        original = b"Preserve this earlier research evidence."
        output.write_bytes(original)
        status, _, stderr = invoke("demo", "--output", output)
        self.assertEqual(status, 2)
        self.assertIn("ERROR:", stderr)
        self.assertEqual(output.read_bytes(), original)

    def test_invalid_configs_and_missing_translations_fail_before_writing_reports(self):
        invalid = {
            "malformed-json": "{",
            "unknown-key": json.dumps({**asdict(self.config), "unknown_parameter": 1}),
            "non-object": "[]",
            "too-short-lookback": json.dumps({**asdict(self.config), "lookback": 4}),
            "infeasible-cap": json.dumps({**asdict(self.config), "max_weight": 0.1}),
            "invalid-date": json.dumps({**asdict(self.config), "research_start": "not-a-date"}),
        }
        for label, contents in invalid.items():
            with self.subTest(config=label):
                config = self.root / f"{label}.json"
                config.write_text(contents, encoding="utf-8")
                output = self.root / f"bad-config-{label}"
                status, stdout, stderr = invoke("demo", "--config", config, "--output", output)
                self.assertEqual(status, 2)
                self.assertEqual(stdout, "")
                self.assertIn("ERROR:", stderr)
                self.assertNotIn("Traceback", stderr)
                self.assertFalse(output.exists())
        result = deepcopy(self.results)
        result["limitations"].append("A new research limitation without a Chinese translation.")
        output = self.root / "missing-translation"
        with self.assertRaisesRegex(ValueError, "translation required"):
            export_report(
                result, output, data_kind="synthetic_demo",
                input_sha256=self.manifest["input_sha256"],
                source_label=self.manifest["source_label"],
            )
        self.assertFalse(output.exists())

    def test_invalid_csv_inputs_report_friendly_errors_without_partial_reports(self):
        original = pd.read_csv(self.demo / "demo_prices.csv", dtype={"ticker": str})
        original = original.loc[original.date.between("2024-01-02", "2024-05-31")].copy()
        invalid = {"missing-column": original.drop(columns="adj_close")}
        invalid["duplicate-observation"] = pd.concat([original, original.iloc[:1]], ignore_index=True)
        invalid["missing-session"] = original.loc[original.date.ne("2024-04-03")]
        for label, field, value in (
            ("missing-price", "adj_close", np.nan),
            ("invalid-price", "adj_close", 0.0),
            ("invalid-date", "date", "not-a-date"),
            ("invalid-ticker", "ticker", " A "),
        ):
            bad = original.copy()
            bad.loc[bad.index[0], field] = value
            invalid[label] = bad
        for label, frame in invalid.items():
            with self.subTest(csv=label):
                csv = self.root / f"{label}.csv"
                frame.to_csv(csv, index=False)
                output = self.root / f"bad-csv-{label}"
                status, stdout, stderr = invoke(
                    "run", "--family", "etf", "--config", self.config_path,
                    "--prices", csv, "--output", output,
                )
                self.assertEqual(status, 2)
                self.assertEqual(stdout, "")
                self.assertIn("ERROR:", stderr)
                self.assertNotIn("Traceback", stderr)
                self.assertFalse(output.exists())

    def test_missing_config_or_price_file_reports_friendly_error(self):
        missing = self.root / "absent"
        for mode, option in (("demo", "--config"), ("run", "--prices")):
            with self.subTest(missing=option):
                output = self.root / f"missing-{mode}"
                status, stdout, stderr = invoke(mode, option, missing, "--output", output)
                self.assertEqual(status, 2)
                self.assertEqual(stdout, "")
                self.assertIn("ERROR:", stderr)
                self.assertNotIn("Traceback", stderr)
                self.assertFalse(output.exists())


if __name__ == "__main__":
    unittest.main()
