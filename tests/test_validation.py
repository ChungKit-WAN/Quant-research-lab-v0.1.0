import hashlib
import json
from dataclasses import replace
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import numpy as np
import pandas as pd

from quant_research.validation import experiment_plan, run_validation
from quant_research.stock import _prepare_factor_inputs, _run_factor_monthly_prepared, run_factor_monthly
import quant_research.stock as stock_module
from sector_backtest.pipeline import MonthlyConfig, sessions


class ValidationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.config = MonthlyConfig(tickers=("A", "B", "C", "D"), lookback=253,
                                   research_start="2023-01-01", holdout_start="2023-02-01",
                                   max_weight=0.5, cost_bps=5)
        dates = sessions("2021-01-01", "2023-03-10")
        rng = np.random.default_rng(503)
        frames = []
        for ticker in cls.config.tickers:
            prices = 100 * np.exp(np.cumsum(rng.normal(0.0003, 0.01, len(dates))))
            frames.append(pd.DataFrame({
                "date": dates, "ticker": ticker, "open": prices * 0.999,
                "high": prices * 1.01, "low": prices * 0.99, "close": prices,
                "adj_close": prices, "volume": rng.integers(5000, 100000, len(dates)).astype(float),
            }))
        cls.prices = pd.concat(frames, ignore_index=True)
        cls.temp = tempfile.TemporaryDirectory()
        cls.output = Path(cls.temp.name) / "validation"
        with patch("quant_research.stock.compute_factors", wraps=stock_module.compute_factors) as factors, \
                patch("quant_research.stock.build_monthly_rankings", wraps=stock_module.build_monthly_rankings) as ranks:
            cls.summary = run_validation(cls.prices, cls.config, cls.output, top_n=2,
                                         data_kind="synthetic_demo", source_label="Synthetic test <fixture>")
            cls.factor_computations, cls.ranking_computations = factors.call_count, ranks.call_count

    @classmethod
    def tearDownClass(cls):
        cls.temp.cleanup()

    def test_predeclared_experiments_and_renormalization(self):
        plan = experiment_plan(self.config, top_n=2)
        experiments = plan["experiments"]
        self.assertEqual(len(experiments), 9)
        cost_experiments = [row for row in experiments if row["kind"] in ("cost", "baseline")]
        self.assertEqual([row["config"]["cost_bps"] for row in cost_experiments], [5, 10, 20])
        for row in experiments:
            self.assertEqual(row["config"]["tickers"], self.config.tickers)
            self.assertEqual(row["config"]["holdout_start"], self.config.holdout_start)
            self.assertAlmostEqual(sum(row["group_weights"].values()), 1)
            if row["kind"] == "factor_group":
                self.assertEqual(row["group_weights"][row["removed_group"]], 0)
        self.assertEqual(plan["group_removal_policy"], "zero_score_weight_keep_all_65_factor_eligibility")

    def test_real_suite_retains_every_experiment_and_plan_hash(self):
        self.assertEqual(self.summary["status"], "completed")
        self.assertEqual(self.summary["completed_experiments"], 9)
        self.assertEqual(self.summary["failed_experiments"], 0)
        self.assertEqual(len(list((self.output / "experiments").glob("*.json"))), 9)
        plan_bytes = (self.output / "validation_plan.json").read_bytes()
        self.assertEqual(hashlib.sha256(plan_bytes).hexdigest(), self.summary["plan_sha256"])
        for filename, digest in self.summary["artifacts_sha256"].items():
            self.assertEqual(hashlib.sha256((self.output / filename).read_bytes()).hexdigest(), digest)

    def test_cached_inputs_preserve_independent_results_and_configuration_boundaries(self):
        self.assertEqual(self.factor_computations, 1)
        self.assertEqual(self.ranking_computations, 7)
        direct = run_factor_monthly(self.prices, replace(self.config, cost_bps=10), top_n=2)
        saved = json.loads((self.output / "experiments/cost_10bps.json").read_text(encoding="utf-8"))["result"]
        for name in direct["strategies"]:
            self.assertEqual(direct["strategies"][name]["ledger_sha256"], saved["strategies"][name]["ledger_sha256"])
        prepared = _prepare_factor_inputs(self.prices, self.config)
        with self.assertRaisesRegex(ValueError, "same config apart from cost_bps"):
            _run_factor_monthly_prepared(prepared, replace(self.config, holdout_start="2023-03-01"), top_n=2)

    def test_benchmark_and_holdout_are_aligned_continuous_ledgers(self):
        self.assertFalse(self.summary["unseen_holdout_certified"])
        rows = self.summary["metrics"]
        self.assertTrue(all(row["benchmark_comparable"] for row in rows))
        self.assertTrue(all(row["net_cagr_difference_vs_equal_weight"] == 0 for row in rows
                            if row["strategy"] == "equal_weight"))
        for experiment in self.summary["experiments"]:
            artifact = json.loads((self.output / experiment["artifact"]).read_text(encoding="utf-8"))
            result = artifact["result"]
            for strategy in ("equal_weight", "multifactor_top_n"):
                metrics = {row["period"]: row for row in result["metrics"] if row["strategy"] == strategy}
                self.assertLess(metrics["development"]["last_session"], self.config.holdout_start)
                self.assertGreaterEqual(metrics["holdout"]["first_session"], self.config.holdout_start)
                self.assertEqual(metrics["development"]["closing_nav"], metrics["holdout"]["opening_nav"])
                self.assertEqual(metrics["development"]["observations"] + metrics["holdout"]["observations"],
                                 metrics["full"]["observations"])

    def test_bilingual_reports_include_all_metrics_and_escape_source(self):
        zh = (self.output / "validation_zh.html").read_text(encoding="utf-8")
        en = (self.output / "validation_en.html").read_text(encoding="utf-8")
        self.assertIn("全部分期绩效指标", zh)
        self.assertIn("SYNTHETIC DATA", en)
        self.assertIn("Synthetic test &lt;fixture&gt;", en)
        self.assertIn("not certification of unseen data", en)
        self.assertIn("same universe, cost and execution timing", en)
        for key in self.summary["metrics"][0]:
            self.assertIn(f"<th>{key}</th>", en)
        frame = pd.read_csv(self.output / "validation_metrics.csv")
        self.assertEqual(len(frame), len(self.summary["metrics"]))

    def test_failures_are_preserved_and_remaining_runs_continue(self):
        result = json.loads((self.output / "experiments/baseline.json").read_text(encoding="utf-8"))["result"]
        calls = []
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "failed_suite"

            def runner(prices, config, **kwargs):
                self.assertTrue((path / "validation_plan.json").is_file())
                calls.append(config.cost_bps)
                if config.cost_bps == 10:
                    raise ValueError("controlled test failure")
                return result

            with patch("quant_research.validation._run_factor_monthly_prepared", side_effect=runner):
                summary = run_validation(self.prices, self.config, path, top_n=2)
            self.assertEqual(len(calls), 9)
            self.assertEqual(summary["status"], "partial_failure")
            self.assertEqual(summary["failed_experiments"], 1)
            failed = json.loads((path / "experiments/cost_10bps.json").read_text(encoding="utf-8"))
            self.assertEqual(failed["error"]["message"], "controlled test failure")
            self.assertNotIn("cost_10bps", {row["experiment"] for row in summary["metrics"]})
            self.assertTrue((path / "experiments/without_liquidity.json").is_file())

    def test_preserves_prior_evidence(self):
        before = (self.output / "validation.json").read_bytes()
        with self.assertRaisesRegex(ValueError, "new or empty"):
            run_validation(self.prices, self.config, self.output, top_n=2)
        self.assertEqual((self.output / "validation.json").read_bytes(), before)

    def test_all_failed_suite_still_writes_readable_evidence(self):
        with tempfile.TemporaryDirectory() as folder:
            output = Path(folder) / "all_failed"
            with patch("quant_research.validation._run_factor_monthly_prepared", side_effect=ValueError("bad data")):
                summary = run_validation(self.prices, self.config, output, top_n=2)
            self.assertEqual(summary["status"], "failed")
            self.assertEqual(summary["completed_experiments"], 0)
            self.assertEqual(summary["failed_experiments"], 9)
            self.assertEqual(summary["metrics"], [])
            self.assertTrue(pd.read_csv(output / "validation_metrics.csv").empty)
            self.assertIn("bad data", (output / "validation_zh.html").read_text(encoding="utf-8"))


if __name__ == "__main__":
    unittest.main()
