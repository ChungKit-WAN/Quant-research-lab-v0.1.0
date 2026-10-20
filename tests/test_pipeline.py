"""Boundary-gap integration tests for the raw snapshot -> factor/rank path."""

import unittest

import numpy as np
import pandas as pd
from pandas.testing import assert_frame_equal

from main import prepare_calculation_prices
from hkquant.factors import compute_factors
from hkquant.ranking import build_monthly_rankings
from hkquant.registry import IMPLEMENTED_SPECS


PRICE_FIELDS = ["open", "high", "low", "close", "adj_close", "volume"]


def sample_prices(dates, tickers=("A", "B", "C")):
    """Deterministic synthetic observations; not an exchange-calendar fixture."""
    frames = []
    day = np.arange(len(dates), dtype=float)
    for position, ticker in enumerate(tickers):
        close = (100 + position * 10) * np.exp(
            0.0002 * day + 0.03 * np.sin(day / (9 + position))
        )
        frames.append(pd.DataFrame({
            "date": pd.DatetimeIndex(dates), "ticker": ticker,
            "open": close * 0.999, "high": close * 1.01,
            "low": close * 0.99, "close": close, "adj_close": close,
            "volume": 100_000 + (day % 11) * (1_000 + position * 100),
        }))
    return pd.concat(frames, ignore_index=True)


def gap(ticker, date):
    return {"ticker": ticker, "date": date, "issue": "empty_price_bar"}


class PipelineBoundaryTests(unittest.TestCase):
    def test_missing_final_month_end_cannot_fall_back_to_previous_quotes(self):
        prices = sample_prices(pd.bdate_range("2023-01-02", "2024-04-29"))
        original = prices.copy(deep=True)
        baseline_factors = compute_factors(prices)
        baseline = build_monthly_rankings(prices, baseline_factors, "2024-05-01")
        previous_anchor = baseline.loc[baseline.date.eq("2024-04-29")]
        self.assertEqual(len(previous_anchor), 3)
        self.assertTrue(previous_anchor.eligible.all())

        source = {"quality_events": [gap(ticker, "2024-04-30") for ticker in ("A", "B", "C")]}
        prepared = prepare_calculation_prices(
            prices, source, pd.Timestamp("2023-01-01"), pd.Timestamp("2024-05-01")
        )
        factors = compute_factors(prepared)
        latest_factors = factors.loc[factors.date.eq("2024-04-30")]
        self.assertEqual(len(latest_factors), 3)
        self.assertTrue(latest_factors[[spec.id for spec in IMPLEMENTED_SPECS]].isna().all().all())

        monthly = build_monthly_rankings(prepared, factors, "2024-05-01")
        self.assertEqual(monthly.date.max(), pd.Timestamp("2024-04-30"))
        latest = monthly.loc[monthly.date.eq("2024-04-30")]
        self.assertEqual(len(latest), 3)
        self.assertFalse(latest.eligible.any())
        self.assertTrue(latest["rank"].isna().all())
        self.assertTrue(latest.rolling_rank.isna().all())
        assert_frame_equal(prices, original)

    def test_explicit_interval_preserves_leading_gap_and_excludes_cutoff(self):
        prices = sample_prices(pd.to_datetime([
            "2024-01-01", "2024-01-03", "2024-01-31", "2024-02-01"
        ]), tickers=("A",))
        source = {"quality_events": [
            gap("A", "2023-12-29"), gap("A", "2024-01-02"),
            gap("A", "2024-02-02"), gap("A", "2024-02-01"),
        ]}
        prepared = prepare_calculation_prices(
            prices, source, pd.Timestamp("2024-01-02"), pd.Timestamp("2024-02-01")
        )
        self.assertEqual(set(prepared.date), set(pd.to_datetime([
            "2024-01-02", "2024-01-03", "2024-01-31"
        ])))
        self.assertEqual(set(prepared.ticker), {"A"})
        leading = prepared.loc[prepared.date.eq("2024-01-02")]
        self.assertEqual(len(leading), 1)
        self.assertTrue(leading[PRICE_FIELDS].isna().all().all())

        factors = compute_factors(prepared)
        self.assertEqual(factors.date.min(), pd.Timestamp("2024-01-02"))
        self.assertTrue(factors.loc[factors.date.eq("2024-01-03"), "rev_return_1"].isna().all())


if __name__ == "__main__":
    unittest.main()
