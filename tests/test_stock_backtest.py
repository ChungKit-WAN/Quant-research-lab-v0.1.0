import unittest
from dataclasses import replace
from unittest.mock import patch

import numpy as np
import pandas as pd

from hkquant.registry import IMPLEMENTED_SPECS
from quant_research.stock import run_factor_monthly
from sector_backtest.backtest import simulate_synthetic_wealth_path
from sector_backtest.pipeline import MonthlyConfig, sessions


class StockBacktestTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.config = MonthlyConfig(
            tickers=("D", "B", "C", "A"), lookback=253,
            research_start="2023-01-01", holdout_start="2023-02-01",
            cost_bps=15.0, max_weight=0.5,
        )
        dates = sessions("2021-01-01", "2023-03-10")
        rng = np.random.default_rng(123)
        prices = 100 * np.exp(np.cumsum(rng.normal(0.0002, 0.01, (len(dates), 4)), axis=0))
        rows = []
        for i, ticker in enumerate(cls.config.tickers):
            rows.append(pd.DataFrame({
                "date": dates, "ticker": ticker, "open": prices[:, i] * 0.999,
                "high": prices[:, i] * 1.01, "low": prices[:, i] * 0.99,
                "close": prices[:, i], "adj_close": prices[:, i],
                "volume": rng.integers(1000, 100000, len(dates)).astype(float),
            }))
        cls.prices = pd.concat(rows, ignore_index=True)

    def test_common_ledger_and_first_entry_cost(self):
        result = run_factor_monthly(self.prices, self.config, top_n=2)
        self.assertEqual(set(result["strategies"]), {"equal_weight", "multifactor_top_n"})
        wide = self.prices.pivot(index="date", columns="ticker", values="adj_close")
        wide = wide.loc[:, list(self.config.tickers)]
        weights = pd.DataFrame(result["target_weights"])
        for name, ledger in result["strategies"].items():
            target = weights.loc[weights.strategy.eq(name)].pivot(
                index="execution", columns="ticker", values="weight"
            ).loc[:, list(self.config.tickers)]
            target.index = pd.to_datetime(target.index)
            direct = simulate_synthetic_wealth_path(
                wide.loc[pd.Timestamp(result["schedule"][0]["signal"]):], target,
                initial_cash=self.config.initial_cash, cost_bps=self.config.cost_bps,
                max_weight=self.config.max_weight,
            )
            self.assertEqual(ledger["ledger_sha256"], direct["ledger_sha256"])
            first = ledger["daily"][0]
            self.assertEqual(first["market_pnl_from_old_units"], 0.0)
            self.assertGreater(first["transaction_cost"], 0.0)
            self.assertAlmostEqual(first["nav"], self.config.initial_cash - first["transaction_cost"])
            self.assertEqual(first["session"], result["schedule"][0]["execution"])
        self.assertEqual(result["factor_config"]["implemented_factor_count"], 65)
        self.assertFalse(result["factor_config"]["point_in_time_universe"])

    def test_future_ohlcv_changes_do_not_change_first_signal(self):
        before = run_factor_monthly(self.prices, self.config, top_n=2)
        signal = pd.Timestamp(before["schedule"][0]["signal"])
        changed = self.prices.copy()
        for i, ticker in enumerate(self.config.tickers):
            mask = changed.date.gt(signal) & changed.ticker.eq(ticker)
            changed.loc[mask, ["open", "high", "low", "close", "adj_close"]] *= 2 + i
            changed.loc[mask, "volume"] *= 10 + i
        after = run_factor_monthly(changed, self.config, top_n=2)
        self.assertEqual(before["schedule"][0], after["schedule"][0])
        first_weights = lambda result: [
            row for row in result["target_weights"] if row["signal"] == signal.strftime("%Y-%m-%d")
        ]
        self.assertEqual(first_weights(before), first_weights(after))

    def test_missing_factor_prevents_reduced_stock_count(self):
        broken = self.prices.copy()
        # Constant volume makes return/volume correlation unavailable, although
        # every OHLCV input and every exchange session is present and valid.
        broken.loc[broken.ticker.eq("A"), "volume"] = 1000.0
        with self.assertRaisesRegex(ValueError, "Insufficient eligible stocks"):
            run_factor_monthly(broken, self.config, top_n=4)

    def test_tied_scores_use_ticker_order(self):
        tied = self.prices[["date", "ticker"]].copy()
        for spec in IMPLEMENTED_SPECS:
            tied[spec.id] = 0.0
        with patch("quant_research.stock.compute_factors", return_value=tied):
            result = run_factor_monthly(self.prices, self.config, top_n=2)
        self.assertTrue(all(event["selected_tickers"] == ["A", "B"] for event in result["schedule"]))

    def test_missing_session_and_invalid_ohlcv_are_rejected(self):
        gap = self.prices.loc[~self.prices.date.eq(pd.Timestamp("2022-06-15"))]
        with self.assertRaisesRegex(ValueError, "session mismatch"):
            run_factor_monthly(gap, self.config, top_n=2)
        bad = self.prices.copy()
        bad.loc[0, "high"] = bad.loc[0, "low"] / 2
        with self.assertRaisesRegex(ValueError, "Invalid OHLC range"):
            run_factor_monthly(bad, self.config, top_n=2)

    def test_weight_cap_and_factor_warmup_are_enforced(self):
        with self.assertRaisesRegex(ValueError, "exceeds max_weight"):
            run_factor_monthly(self.prices, self.config, top_n=1)
        short = self.prices.loc[self.prices.date.ge("2022-08-01")]
        with self.assertRaisesRegex(ValueError, "Insufficient eligible stocks"):
            run_factor_monthly(short, replace(self.config, lookback=60), top_n=2)


if __name__ == "__main__":
    unittest.main()
