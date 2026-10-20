"""Financial invariants for the monthly sector-ETF research engine.

All observations in this file are synthetic.  The short calendar is specified
independently of the production scheduler so holidays and partial final months
cannot silently become valid month-end signals.
"""

from dataclasses import replace
import unittest

import numpy as np
import pandas as pd
from numpy.testing import assert_allclose
from pandas.testing import assert_frame_equal

from sector_backtest.backtest import simulate_synthetic_wealth_path
from sector_backtest.execution import rebalance_synthetic_portfolio
from sector_backtest.performance import calculate_period_performance
from sector_backtest.pipeline import (
    MonthlyConfig,
    build_monthly_schedule,
    demo_prices,
    run_monthly,
    sessions,
    validate_prices,
)
from sector_backtest.portfolio import solve_capped_minimum_variance
from sector_backtest.risk_models import estimate_covariance_models


TICKERS = ("A", "B", "C", "D")


def small_config():
    return MonthlyConfig(
        tickers=TICKERS,
        lookback=20,
        research_start="2024-03-01",
        holdout_start="2024-04-01",
        cost_bps=5.0,
        max_weight=0.6,
        initial_cash=100.0,
    )


def short_prices():
    """XNYS sessions for January--May 2024, with explicit known holidays."""
    holidays = pd.to_datetime(["2024-01-15", "2024-02-19", "2024-03-29", "2024-05-27"])
    dates = pd.bdate_range("2024-01-02", "2024-05-31").difference(holidays)
    rng = np.random.default_rng(90210)
    returns = rng.normal(
        loc=np.array([0.0010, 0.0003, 0.0005, -0.0001]),
        scale=np.array([0.007, 0.013, 0.018, 0.010]),
        size=(len(dates), len(TICKERS)),
    )
    return pd.DataFrame(100 * np.cumprod(1 + returns, axis=0), index=dates, columns=TICKERS)


def accounting_path():
    """Large price moves expose wrong-close execution and new-position P&L."""
    dates = pd.to_datetime(["2024-02-29", "2024-03-01", "2024-03-04", "2024-03-05", "2024-03-06"])
    prices = pd.DataFrame(
        [[100.0, 100.0], [200.0, 50.0], [220.0, 60.0], [110.0, 120.0], [121.0, 120.0]],
        index=dates, columns=["A", "B"],
    )
    targets = pd.DataFrame([[1.0, 0.0], [0.0, 1.0]], index=dates[[1, 3]], columns=prices.columns)
    return simulate_synthetic_wealth_path(
        prices, targets, initial_cash=100.0, cost_bps=100.0, max_weight=1.0,
    )


class ExecutionAccountingTests(unittest.TestCase):
    def test_entry_cost_is_self_financed_and_first_day_earns_no_price_return(self):
        ledger = accounting_path()
        first = ledger["daily"][0]
        # If costs are 1% of purchases, invested wealth is cash / 1.01.
        expected_nav = 100.0 / 1.01
        self.assertAlmostEqual(first["nav"], expected_nav, places=10)
        self.assertEqual(first["market_pnl_from_old_units"], 0.0)
        self.assertAlmostEqual(first["transaction_cost"], expected_nav * 0.01, places=10)
        self.assertAlmostEqual(first["net_return"], 1 / 1.01 - 1, places=12)
        self.assertGreaterEqual(first["cash"], 0.0)
        self.assertAlmostEqual(first["nav"] + first["transaction_cost"], 100.0, places=10)

    def test_rebalance_day_marks_old_position_before_buying_new_position(self):
        rows = accounting_path()["daily"]
        # A gains 10% on March 4, loses 50% on March 5; B's March 5
        # doubling happened before its purchase and must not benefit the book.
        self.assertAlmostEqual(rows[1]["nav"], (100 / 1.01) * 1.1, places=10)
        self.assertAlmostEqual(rows[2]["nav_before_trade"], rows[1]["nav"] * 0.5, places=10)
        self.assertAlmostEqual(rows[2]["market_pnl_from_old_units"], -rows[1]["nav"] * 0.5, places=10)
        # Complete rotation pays a fee on both the sale and the new purchase.
        expected = rows[2]["nav_before_trade"] * (1 - 0.01) / (1 + 0.01)
        self.assertAlmostEqual(rows[2]["nav"], expected, places=10)
        self.assertAlmostEqual(rows[3]["nav"], rows[2]["nav"], places=10)
        self.assertEqual(rows[3]["market_pnl_from_old_units"], 0.0)

    def test_no_trade_preserves_units_and_a_slice_keeps_opening_capital(self):
        ledger = accounting_path()
        rows = ledger["daily"]
        self.assertEqual(rows[0]["units"], rows[1]["units"])
        self.assertEqual(rows[1]["transaction_cost"], 0.0)
        self.assertEqual(rows[2]["units"], rows[3]["units"])
        self.assertEqual(rows[3]["transaction_cost"], 0.0)
        period = calculate_period_performance(rows[2:], tickers=["A", "B"])
        self.assertEqual(period["opening_nav"], rows[1]["nav"])
        self.assertAlmostEqual(period["net_total_return"], rows[-1]["nav"] / rows[1]["nav"] - 1, places=12)
        # The period starts with a loss, so its opening NAV belongs in drawdown.
        self.assertAlmostEqual(period["maximum_drawdown"], 1 - rows[-1]["nav"] / rows[1]["nav"], places=12)

    def test_full_investment_with_no_change_has_zero_turnover_and_cost(self):
        labels = ["A", "B"]
        result = rebalance_synthetic_portfolio(
            pd.Series([0.5, 0.5], index=labels),
            pd.Series([100.0, 100.0], index=labels),
            pd.Series([0.5, 0.5], index=labels),
            cash=0.0, cost_bps=25.0, max_weight=0.6,
        )
        self.assertEqual(result["transaction_cost"], 0.0)
        self.assertEqual(result["total_traded_notional"], 0.0)
        self.assertEqual(result["new_units"], [0.5, 0.5])
        self.assertEqual(result["nav_after"], 100.0)

    def test_held_units_drift_above_target_cap_until_scheduled_rebalance(self):
        dates = pd.to_datetime(["2024-02-29", "2024-03-01", "2024-03-04", "2024-03-05"])
        prices = pd.DataFrame(
            [[100.0, 100.0], [100.0, 100.0], [200.0, 100.0], [200.0, 100.0]],
            index=dates, columns=["A", "B"],
        )
        targets = pd.DataFrame([[0.5, 0.5], [0.5, 0.5]], index=dates[[1, 3]], columns=prices.columns)
        ledger = simulate_synthetic_wealth_path(
            prices, targets, initial_cash=100.0, cost_bps=0.0, max_weight=0.6,
        )
        entered, drifted, rebalanced = ledger["daily"]
        assert_allclose(entered["units"], [0.5, 0.5], rtol=0, atol=1e-12)
        self.assertEqual(drifted["units"], entered["units"])
        self.assertAlmostEqual(drifted["nav"], 150.0, places=10)
        assert_allclose(drifted["weights"], [2 / 3, 1 / 3], rtol=0, atol=1e-12)
        self.assertGreater(drifted["weights"][0], 0.6)
        self.assertIsNone(drifted["trade_number"])
        self.assertEqual(drifted["buy_notional"] + drifted["sell_notional"], 0.0)
        assert_allclose(rebalanced["units"], [0.375, 0.75], rtol=0, atol=1e-12)
        assert_allclose(rebalanced["weights"], [0.5, 0.5], rtol=0, atol=1e-12)
        self.assertAlmostEqual(rebalanced["nav"], 150.0, places=10)


class CovarianceAndPortfolioTests(unittest.TestCase):
    def test_sample_covariance_and_unconstrained_inverse_variance_solution(self):
        # Orthogonal, zero-mean columns give a diagonal sample covariance.
        values = np.array([[1, 2, 3], [1, -2, -3], [-1, 2, -3], [-1, -2, 3]], dtype=float) * 0.01
        returns = pd.DataFrame(values, index=pd.bdate_range("2024-01-02", periods=4), columns=["A", "B", "C"])
        models = estimate_covariance_models(returns)
        expected = np.diag([4, 16, 36]) * 0.0001 / 3
        assert_allclose(models["sample_covariance"]["values"], expected, rtol=1e-13, atol=1e-18)
        assert_allclose(models["shrunk_covariance"]["values"], expected, rtol=1e-13, atol=1e-18)
        covariance = pd.DataFrame(expected, index=returns.columns, columns=returns.columns)
        result = solve_capped_minimum_variance(covariance, max_weight=1.0)
        # For a positive diagonal matrix, w_i is proportional to 1 / variance_i.
        assert_allclose(result["weights"], np.array([36, 9, 4]) / 49, rtol=0, atol=2e-9)

    def test_binding_cap_has_known_optimum_and_infeasible_cap_is_rejected(self):
        covariance = pd.DataFrame(np.diag([1.0, 4.0, 9.0]), index=["A", "B", "C"], columns=["A", "B", "C"])
        result = solve_capped_minimum_variance(covariance, max_weight=0.5)
        # A binds at 0.5; B:C split the remaining half in inverse-variance ratio 9:4.
        assert_allclose(result["weights"], [0.5, 4.5 / 13, 2 / 13], rtol=0, atol=2e-9)
        with self.assertRaises(ValueError):
            solve_capped_minimum_variance(covariance, max_weight=0.3)

    def test_nonpositive_definite_covariance_is_not_silently_repaired(self):
        covariance = pd.DataFrame([[1.0, 1.0], [1.0, 1.0]], index=["A", "B"], columns=["A", "B"])
        with self.assertRaises(ValueError):
            solve_capped_minimum_variance(covariance, max_weight=1.0)

    def test_correlated_risk_has_known_optimum_at_long_only_boundary(self):
        covariance = pd.DataFrame(
            [[1.0, 2.0, 0.0], [2.0, 9.0, 0.0], [0.0, 0.0, 4.0]],
            index=["A", "B", "C"], columns=["A", "B", "C"],
        )
        # At [0.8, 0, 0.2], covariance @ w is [0.8, 1.6, 0.8].
        # A and C have equal marginal risk; buying B increases variance.
        result = solve_capped_minimum_variance(covariance, max_weight=1.0)
        assert_allclose(result["weights"], [0.8, 0.0, 0.2], rtol=0, atol=2e-9)
        self.assertAlmostEqual(result["estimated_daily_variance"], 0.8, places=10)


class MonthlyCalendarTests(unittest.TestCase):
    def setUp(self):
        self.config = small_config()
        self.prices = short_prices()

    def test_complete_year_matches_independent_holidays_and_keeps_early_closes(self):
        holidays = pd.to_datetime([
            "2024-01-01", "2024-01-15", "2024-02-19", "2024-03-29", "2024-05-27",
            "2024-06-19", "2024-07-04", "2024-09-02", "2024-11-28", "2024-12-25",
        ])
        expected = pd.bdate_range("2024-01-01", "2024-12-31").difference(holidays)
        actual = sessions("2024-01-01", "2024-12-31")
        self.assertEqual(len(actual), 252)
        self.assertTrue(actual.equals(expected))
        for early_close in ("2024-07-03", "2024-11-29", "2024-12-24"):
            self.assertIn(pd.Timestamp(early_close), actual)

    def test_holiday_month_end_signals_and_next_session_execution(self):
        original = self.prices.copy(deep=True)
        validated = validate_prices(self.prices, self.config)
        assert_frame_equal(self.prices, original)
        schedule = build_monthly_schedule(validated, self.config)
        self.assertEqual(schedule["signal"].tolist(), list(pd.to_datetime(["2024-02-29", "2024-03-28", "2024-04-30"])))
        self.assertEqual(schedule["execution"].tolist(), list(pd.to_datetime(["2024-03-01", "2024-04-01", "2024-05-01"])))

    def test_missing_entire_market_session_is_rejected(self):
        for missing in ("2024-02-14", "2024-04-30"):
            with self.subTest(missing=missing), self.assertRaises(ValueError):
                validate_prices(self.prices.drop(pd.Timestamp(missing)), self.config)

    def test_partial_last_month_is_not_mistaken_for_month_end(self):
        partial = self.prices.loc[:"2024-04-29"]
        schedule = build_monthly_schedule(partial, self.config)
        self.assertEqual(schedule["signal"].tolist(), list(pd.to_datetime(["2024-02-29", "2024-03-28"])))
        # A genuine last-session signal without its execution also cannot trade.
        month_end_only = build_monthly_schedule(self.prices.loc[:"2024-04-30"], self.config)
        assert_frame_equal(schedule, month_end_only)

    def test_non_session_dates_and_incomplete_asset_quotes_are_rejected(self):
        holiday_row = self.prices.iloc[0:1].copy()
        holiday_row.index = pd.DatetimeIndex(["2024-03-29"])
        with self.assertRaises(ValueError):
            validate_prices(pd.concat([self.prices, holiday_row]).sort_index(), self.config)
        incomplete = self.prices.copy()
        incomplete.loc["2024-04-01", "B"] = np.nan
        with self.assertRaises(ValueError):
            validate_prices(incomplete, self.config)

    def test_initial_signal_requires_exact_number_of_returns_including_baseline(self):
        signal_position = self.prices.index.get_loc(pd.Timestamp("2024-02-29"))
        enough = self.prices.iloc[signal_position - self.config.lookback:]
        schedule = build_monthly_schedule(enough, self.config)
        self.assertEqual(schedule.iloc[0]["signal"], pd.Timestamp("2024-02-29"))
        with self.assertRaisesRegex(ValueError, "Insufficient history"):
            build_monthly_schedule(enough.iloc[1:], self.config)
        with self.assertRaisesRegex(ValueError, "Missing signal or execution"):
            build_monthly_schedule(self.prices.loc["2024-03-01":], self.config)


class MonthlyPipelineTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.config = small_config()
        cls.prices = short_prices()
        cls.result = run_monthly(cls.prices, cls.config)

    def test_each_strategy_has_continuous_capital_across_holdout_boundary(self):
        self.assertEqual(len(self.result["strategies"]), 3)
        for name, ledger in self.result["strategies"].items():
            with self.subTest(strategy=name):
                daily = ledger["daily"]
                by_session = {row["session"]: row for row in daily}
                previous = by_session["2024-03-28"]
                opening = by_session["2024-04-01"]
                self.assertEqual(opening["previous_nav"], previous["nav"])
                self.assertNotAlmostEqual(opening["previous_nav"], self.config.initial_cash, places=6)
                holdout = next(row for row in self.result["metrics"] if row["strategy"] == name and row["period"] == "holdout")
                self.assertEqual(holdout["opening_nav"], previous["nav"])
                self.assertAlmostEqual(holdout["net_total_return"], daily[-1]["nav"] / previous["nav"] - 1, places=12)
                for prior, current in zip(daily, daily[1:]):
                    self.assertEqual(current["previous_nav"], prior["nav"])
                self.assertEqual([row["session"] for row in ledger["trades"]], ["2024-03-01", "2024-04-01", "2024-05-01"])

    def test_appending_future_prices_preserves_prior_signals_trades_and_nav(self):
        cutoff = "2024-04-16"
        prefix = run_monthly(self.prices.loc[:cutoff], self.config)
        self.assertEqual(prefix["schedule"], [event for event in self.result["schedule"] if event["execution"] <= cutoff])
        self.assertEqual(prefix["target_weights"], [row for row in self.result["target_weights"] if row["execution"] <= cutoff])
        for name, ledger in prefix["strategies"].items():
            with self.subTest(strategy=name):
                complete = self.result["strategies"][name]
                self.assertEqual(ledger["daily"], [row for row in complete["daily"] if row["session"] <= cutoff])
                self.assertEqual(ledger["trades"], [row for row in complete["trades"] if row["session"] <= cutoff])

    def test_execution_day_prices_do_not_leak_into_signal_weights(self):
        changed = self.prices.copy()
        changed.loc["2024-03-01":] *= np.array([3.0, 0.6, 1.2, 0.9])
        alternative = run_monthly(changed, self.config)
        for name, ledger in alternative["strategies"].items():
            with self.subTest(strategy=name):
                first_execution = ledger["trades"][0]["execution"]
                original = self.result["strategies"][name]["trades"][0]["execution"]
                assert_allclose(first_execution["inputs"]["target_weights"], original["inputs"]["target_weights"], rtol=0, atol=0)
                self.assertEqual(ledger["daily"][0]["market_pnl_from_old_units"], 0.0)
                self.assertAlmostEqual(ledger["daily"][0]["nav"], self.config.initial_cash / (1 + self.config.cost_bps / 10000), places=10)

    def test_pipeline_estimation_windows_end_on_signal_and_are_exact_length(self):
        returns = self.prices.pct_change(fill_method=None).iloc[1:]
        for event in self.result["schedule"]:
            window = returns.loc[:event["signal"]].tail(self.config.lookback)
            self.assertEqual(event["window_observations"], self.config.lookback)
            self.assertEqual(event["window_last"], event["signal"])
            self.assertEqual(event["window_first"], window.index[0].strftime("%Y-%m-%d"))
            self.assertLess(event["window_last"], event["execution"])

    def test_holdout_label_does_not_change_any_trade_or_ledger(self):
        # Moving the evaluation cut is a reporting change, not a cash reset or
        # a change in the strategy's information set.
        alternate = run_monthly(self.prices, replace(self.config, holdout_start="2024-04-15"))
        self.assertEqual(alternate["strategies"], self.result["strategies"])
        self.assertEqual(alternate["target_weights"], self.result["target_weights"])

    def test_demo_is_reproducible_and_uses_the_configured_universe(self):
        config = replace(self.config, lookback=20)
        first = demo_prices(config)
        second = demo_prices(config)
        assert_frame_equal(first, second)
        self.assertEqual(first.columns.tolist(), list(config.tickers))
        validate_prices(first, config)


if __name__ == "__main__":
    unittest.main()
