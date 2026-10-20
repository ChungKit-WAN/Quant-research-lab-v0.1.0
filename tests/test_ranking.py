import unittest

import numpy as np
import pandas as pd
from pandas.testing import assert_frame_equal

from hkquant.ranking import build_monthly_rankings
from hkquant.registry import IMPLEMENTED_SPECS


def inputs(dates=("2023-01-31", "2023-02-28", "2023-03-31"), tickers=("A", "B", "C", "D")):
    prices, factors = [], []
    for date in dates:
        for i, ticker in enumerate(tickers):
            prices.append({"date": pd.Timestamp(date), "ticker": ticker, "close": 100.0,
                           "adj_close": 100.0, "volume": 1_000.0})
            row = {"date": pd.Timestamp(date), "ticker": ticker}
            row.update({spec.id: i * spec.direction for spec in IMPLEMENTED_SPECS})
            factors.append(row)
    return pd.DataFrame(prices), pd.DataFrame(factors)


class MonthlyRankingTests(unittest.TestCase):
    def test_direction_percentile_and_rolling(self):
        p, f = inputs()
        result = build_monthly_rankings(p, f, "2023-04-01")
        march = result[result.date.eq("2023-03-31")].set_index("ticker")
        self.assertEqual(march.loc["D", "score"], 1.0)
        self.assertEqual(march.loc["D", "rank"], 1.0)
        self.assertEqual(march.loc["D", "rank_percentile"], 0.0)
        self.assertEqual(march.loc["A", "rolling_mean_percentile"], 1.0)
        self.assertEqual(march.loc["D", "rolling_rank"], 1.0)
        self.assertTrue(result[result.date < "2023-03-01"].rolling_rank.isna().all())

    def test_future_rows_including_new_ticker_do_not_change_history(self):
        p, f = inputs()
        before = build_monthly_rankings(p, f, "2023-04-01")
        future_p, future_f = inputs(("2023-04-28", "2023-05-31"), ("A", "B", "C", "D", "NEW"))
        after = build_monthly_rankings(pd.concat([p, future_p]), pd.concat([f, future_f]), "2023-06-01")
        assert_frame_equal(before, after[after.date < "2023-04-01"].reset_index(drop=True))

    def test_current_calendar_month_always_excluded(self):
        p, f = inputs()
        result = build_monthly_rankings(p, f, "2023-03-31")
        self.assertEqual(result.date.max(), pd.Timestamp("2023-02-28"))

    def test_missing_entire_month_breaks_rolling(self):
        p, f = inputs(("2023-01-31", "2023-03-31", "2023-04-28"))
        result = build_monthly_rankings(p, f, "2023-05-01")
        february = result[result.date.eq("2023-02-28")]
        self.assertTrue(february.reason.str.contains("no_market_observations").all())
        self.assertTrue(result.rolling_rank.isna().all())

    def test_missing_anchor_and_zero_volume_never_use_stale_ranks(self):
        p, f = inputs()
        # D has a March quote, but only before the common market anchor.
        p.loc[p.ticker.eq("D") & p.date.eq("2023-03-31"), "date"] = pd.Timestamp("2023-03-30")
        f.loc[f.ticker.eq("D") & f.date.eq("2023-03-31"), "date"] = pd.Timestamp("2023-03-30")
        result = build_monthly_rankings(p, f, "2023-04-01")
        d = result[(result.ticker == "D") & (result.date == "2023-03-31")].iloc[0]
        self.assertIn("missing_anchor_quote", d.reason)
        self.assertTrue(pd.isna(d.rolling_rank))
        p, f = inputs()
        p.loc[p.ticker.eq("D") & p.date.eq("2023-03-31"), "volume"] = 0
        d = build_monthly_rankings(p, f, "2023-04-01").iloc[-1]
        self.assertIn("nonpositive", d.reason)
        self.assertTrue(pd.isna(d["rank"]))

    def test_one_missing_factor_disqualifies_not_silently_reweighted(self):
        p, f = inputs()
        f.loc[f.ticker.eq("D") & f.date.eq("2023-02-28"), IMPLEMENTED_SPECS[0].id] = np.nan
        result = build_monthly_rankings(p, f, "2023-04-01")
        d = result[result.ticker.eq("D")]
        self.assertIn("incomplete_factors:momentum", d.iloc[1].reason)
        self.assertTrue(d.rolling_rank.isna().all())

    def test_group_weights_do_not_depend_on_indicator_count(self):
        p, f = inputs(("2023-01-31",))
        # A is best on all 15 risk indicators and worst on all other groups.
        for spec in IMPLEMENTED_SPECS:
            if spec.group == "risk":
                f[spec.id] = list(reversed(f[spec.id].tolist()))
        weights = {"momentum": .1, "reversal": .1, "risk": .7, "liquidity": .1}
        result = build_monthly_rankings(p, f, "2023-02-01", weights=weights).set_index("ticker")
        self.assertAlmostEqual(result.loc["A", "score"], .7)
        self.assertAlmostEqual(result.loc["D", "score"], .3)
        self.assertEqual(result.loc["A", "rank"], 1)

    def test_small_cross_section_and_ties(self):
        p, f = inputs(tickers=("A", "B"))
        result = build_monthly_rankings(p, f, "2023-04-01")
        self.assertTrue(result["rank"].isna().all())
        self.assertTrue(result.reason.str.contains("insufficient_eligible_stocks:2<3").all())
        p, f = inputs()
        for spec in IMPLEMENTED_SPECS:
            f[spec.id] = 5.0
        result = build_monthly_rankings(p, f, "2023-04-01")
        self.assertTrue(result["rank"].eq(2.5).all())
        self.assertTrue(result.rank_percentile.eq(.5).all())

    def test_membership_is_from_inclusive_to_exclusive(self):
        p, f = inputs()
        universe = pd.DataFrame([
            {"ticker": ticker, "effective_from": "2023-01-01", "effective_to": None}
            for ticker in ("A", "B", "C")
        ] + [{"ticker": "D", "effective_from": "2023-02-28", "effective_to": "2023-03-31"}])
        result = build_monthly_rankings(p, f, "2023-04-01", universe=universe)
        d = result[result.ticker.eq("D")]
        self.assertEqual(d.eligible.tolist(), [False, True, False])
        self.assertTrue(d.rolling_rank.isna().all())

    def test_empty_or_ambiguous_parameters_fail_clearly(self):
        p, f = inputs()
        for params in ({"weights": {}}, {"ranking_window": 0}, {"min_stocks": 1},
                       {"universe": pd.DataFrame(columns=["ticker", "effective_from", "effective_to"])}):
            with self.subTest(params=params), self.assertRaises(ValueError):
                build_monthly_rankings(p, f, "2023-04-01", **params)
        with self.assertRaises(ValueError):
            build_monthly_rankings(pd.concat([p, p.iloc[:1]]), f, "2023-04-01")


if __name__ == "__main__":
    unittest.main()
