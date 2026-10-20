import unittest
from collections import Counter

import numpy as np
import pandas as pd
from pandas.testing import assert_frame_equal

from hkquant.factors import compute_factors
from hkquant.registry import FACTOR_SPECS, IMPLEMENTED_SPECS


def sample_prices(periods=320, ticker="0005.HK"):
    day = np.arange(periods, dtype=float)
    close = 100 * np.exp(0.0002 * day + 0.03 * np.sin(day / 9))
    return pd.DataFrame({
        "date": pd.bdate_range("2020-01-01", periods=periods),
        "ticker": ticker,
        "open": close * 0.999,
        "high": close * 1.01,
        "low": close * 0.99,
        "close": close,
        "adj_close": close,
        "volume": 100_000 + (day % 11) * 1_000,
    })


class FactorTests(unittest.TestCase):
    def test_quarantined_bar_keeps_gap_in_windows_without_inventing_prices(self):
        data = sample_prices()
        gap = {"date": str(data.loc[100, "date"].date()), "ticker": data.loc[100, "ticker"]}
        actual = compute_factors(data.drop(index=100), missing_sessions=[gap])
        data.loc[100, ["open", "high", "low", "close", "adj_close", "volume"]] = np.nan
        expected = compute_factors(data)
        assert_frame_equal(actual, expected)
        self.assertTrue(actual.drop(columns=["date", "ticker"]).iloc[100].isna().all())
        self.assertTrue(pd.isna(actual.loc[101, "rev_return_1"]))
        self.assertTrue(pd.isna(actual.loc[110, "mom_return_21"]))

    def test_catalog_is_honest_about_100_candidates(self):
        self.assertEqual(len(FACTOR_SPECS), 100)
        self.assertEqual(len({spec.id for spec in FACTOR_SPECS}), 100)
        self.assertEqual(Counter(spec.group for spec in FACTOR_SPECS), {
            "momentum": 20, "reversal": 10, "risk": 15, "liquidity": 20,
            "value": 15, "quality": 10, "growth": 10,
        })
        self.assertEqual(len(IMPLEMENTED_SPECS), 65)
        for spec in FACTOR_SPECS:
            self.assertRegex(spec.id, r"^[a-z][a-z0-9_]*$")
            self.assertIn(spec.direction, (-1, 1))
        pending = [s for s in FACTOR_SPECS if s.status == "awaiting_pit_fundamentals"]
        self.assertEqual(len(pending), 35)
        calculated = compute_factors(sample_prices())
        self.assertTrue(all(s.id not in calculated for s in pending))

    def test_appending_future_does_not_change_historical_factors(self):
        prices = pd.concat([sample_prices(ticker="0005.HK"), sample_prices(ticker="0700.HK")])
        cutoff = pd.Timestamp("2021-01-29")
        history = prices.loc[prices.date <= cutoff]
        expected = compute_factors(history)
        # Deliberately extreme future values would expose accidental backward fill.
        prices.loc[prices.date > cutoff, ["close", "adj_close"]] *= 50
        actual = compute_factors(prices)
        actual = actual.loc[actual.date <= cutoff].reset_index(drop=True)
        assert_frame_equal(expected, actual)

    def test_each_indicator_requires_its_documented_history(self):
        factors = compute_factors(sample_prices())
        for spec in IMPLEMENTED_SPECS:
            with self.subTest(factor=spec.id):
                self.assertTrue(factors[spec.id].iloc[:spec.min_observations - 1].isna().all())
                self.assertTrue(np.isfinite(factors[spec.id].iloc[spec.min_observations - 1]))

    def test_returns_use_adjusted_prices_and_amount_uses_raw_prices(self):
        data = sample_prices(periods=22)
        data["adj_close"] = np.arange(100.0, 122.0)
        data["close"] = 50.0
        data["volume"] = 1_000.0
        factors = compute_factors(data)
        self.assertAlmostEqual(factors.loc[21, "mom_return_21"], 0.21)
        self.assertAlmostEqual(factors.loc[21, "rev_return_1"], 121 / 120 - 1)
        self.assertAlmostEqual(factors.loc[21, "liq_amount_20"], 50_000.0)
        self.assertAlmostEqual(factors.loc[21, "rev_rsi_14"], 100.0)

    def test_drawdown_is_peak_to_later_trough_within_window(self):
        data = sample_prices(periods=63)
        data["adj_close"] = [100.0, 80.0, 120.0] + [90.0] * 60
        self.assertAlmostEqual(compute_factors(data).loc[62, "risk_max_drawdown_63"], 0.25)

    def test_zero_volume_is_not_scored_and_flat_series_has_no_infinities(self):
        data = sample_prices()
        data[["open", "high", "low", "close", "adj_close"]] = 100.0
        data["volume"] = 1_000.0
        data.loc[280, "volume"] = 0
        factors = compute_factors(data)
        numeric = factors.drop(columns=["date", "ticker"])
        self.assertFalse(np.isinf(numeric.to_numpy()).any())
        self.assertTrue(numeric.loc[280].isna().all())
        self.assertEqual(factors.loc[279, "rev_rsi_14"], 50.0)
        self.assertEqual(factors.loc[279, "risk_volatility_60"], 0.0)
        self.assertTrue(pd.isna(factors.loc[279, "rev_price_zscore_21"]))

    def test_missing_prices_are_not_filled(self):
        data = sample_prices()
        data.loc[100, "adj_close"] = np.nan
        original = data.copy(deep=True)
        factors = compute_factors(data)
        self.assertTrue(pd.isna(factors.loc[101, "rev_return_1"]))
        self.assertTrue(pd.isna(factors.loc[110, "mom_return_21"]))
        assert_frame_equal(data, original)

    def test_stocks_are_isolated_and_duplicates_rejected(self):
        first, second = sample_prices(), sample_prices(ticker="0700.HK")
        second["adj_close"] *= 8
        combined = pd.concat([first, second]).sample(frac=1, random_state=7)
        factors = compute_factors(combined)
        only_first = factors.loc[factors.ticker == "0005.HK"].reset_index(drop=True)
        assert_frame_equal(only_first, compute_factors(first))
        with self.assertRaisesRegex(ValueError, "Duplicate"):
            compute_factors(pd.concat([first, first.iloc[:1]]))


if __name__ == "__main__":
    unittest.main()
