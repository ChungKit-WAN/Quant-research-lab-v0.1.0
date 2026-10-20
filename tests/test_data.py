"""Offline checks for the price-data boundary; no external calls are made."""

from __future__ import annotations

from pathlib import Path
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch

import numpy as np
import pandas as pd

from hkquant.data import (
    DataDownloadError,
    DataValidationError,
    PRICE_COLUMNS,
    fetch_yahoo,
    load_prices_csv,
    validate_prices,
)


def sample_prices() -> pd.DataFrame:
    return pd.DataFrame(
        [
            ["2024-01-03", "0700.HK", 100, 111, 99, 110, 108, 1000],
            ["2024-01-02", "0700.HK", 100, 103, 98, 101, 99, 1200],
        ],
        columns=PRICE_COLUMNS,
    )


def yahoo_prices() -> pd.DataFrame:
    return pd.DataFrame(
        {
            "Open": [100.0, 101.0],
            "High": [103.0, 104.0],
            "Low": [99.0, 100.0],
            "Close": [101.0, 103.0],
            "Adj Close": [99.0, 101.0],
            "Volume": [1200.0, 1100.0],
        },
        index=pd.date_range("2024-01-02", periods=2, tz="Asia/Hong_Kong"),
    )


class PriceValidationTests(unittest.TestCase):
    def test_sorts_and_does_not_mutate_input_or_fill_missing_sessions(self):
        raw = sample_prices()
        raw.loc[0, "date"] = "2024-01-05"
        before = raw.copy(deep=True)
        actual = validate_prices(raw)
        self.assertEqual(actual["date"].dt.strftime("%Y-%m-%d").tolist(), ["2024-01-02", "2024-01-05"])
        self.assertEqual(len(actual), 2)
        pd.testing.assert_frame_equal(raw, before)

    def test_timezone_removal_keeps_hong_kong_trading_day(self):
        raw = sample_prices()
        raw["date"] = pd.to_datetime(raw["date"]).dt.tz_localize("Asia/Hong_Kong")
        actual = validate_prices(raw)
        self.assertIsNone(actual["date"].dt.tz)
        self.assertEqual(actual["date"].iloc[0], pd.Timestamp("2024-01-02"))

    def test_rejects_duplicate_trading_days(self):
        raw = sample_prices()
        raw.loc[1, "date"] = raw.loc[0, "date"]
        with self.assertRaisesRegex(DataValidationError, "Duplicate"):
            validate_prices(raw)

    def test_requires_adjusted_close(self):
        with self.assertRaisesRegex(DataValidationError, "adj_close"):
            validate_prices(sample_prices().drop(columns=["adj_close"]))

    def test_rejects_invalid_values(self):
        for column, value in [
            ("open", 0), ("low", -1), ("adj_close", np.nan), ("close", np.inf),
            ("volume", np.nan), ("volume", -1), ("volume", np.inf),
            ("high", "invalid"), ("volume", True),
        ]:
            with self.subTest(column=column, value=value):
                raw = sample_prices().astype({column: object})
                raw.loc[0, column] = value
                with self.assertRaises(DataValidationError):
                    validate_prices(raw)

    def test_zero_volume_is_valid_without_implying_tradability(self):
        raw = sample_prices()
        raw.loc[0, "volume"] = 0
        self.assertEqual(validate_prices(raw)["volume"].iloc[1], 0)

    def test_rejects_invalid_ohlc_range(self):
        for column, value in [("high", 100), ("low", 105)]:
            raw = sample_prices()
            raw.loc[0, column] = value
            with self.subTest(column=column), self.assertRaisesRegex(DataValidationError, "OHLC"):
                validate_prices(raw)

    def test_rejects_invalid_dates_and_tickers(self):
        for column, value in [("date", "not-a-date"), ("date", None), ("date", 20240101), ("ticker", None), ("ticker", " ")]:
            raw = sample_prices()
            raw[column] = raw[column].astype(object)
            raw.loc[0, column] = value
            with self.subTest(column=column, value=value), self.assertRaises(DataValidationError):
                validate_prices(raw)

    def test_csv_preserves_leading_zero_ticker_and_validates(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "prices.csv"
            raw = sample_prices()
            raw["ticker"] = "00700"
            raw.to_csv(path, index=False, encoding="utf-8-sig")
            actual = load_prices_csv(path)
            self.assertEqual(actual["ticker"].unique().tolist(), ["00700"])
            raw.loc[0, "volume"] = -1
            raw.to_csv(path, index=False)
            with self.assertRaises(DataValidationError):
                load_prices_csv(path)


class YahooDownloadTests(unittest.TestCase):
    def test_empty_bar_policy_preserves_original_and_records_gap(self):
        raw = yahoo_prices()
        raw.iloc[0, :5] = np.nan
        raw.iloc[0, 5] = 0
        original = raw.copy(deep=True)
        captured, events = [], []
        yf = SimpleNamespace(download=Mock(return_value=raw))
        with patch("hkquant.data.importlib.import_module", return_value=yf):
            with self.assertRaises(DataDownloadError):
                fetch_yahoo(["JNJ"], "2024-01-01", "2024-01-05")
            prices, meta = fetch_yahoo(["JNJ"], "2024-01-01", "2024-01-05",
                raw_sink=lambda ticker, frame: captured.append(frame),
                missing_bar_policy="quarantine_empty", quality_sink=events.append)
        pd.testing.assert_frame_equal(captured[0], original)
        self.assertEqual(len(prices), 1)
        self.assertEqual(events[0]["date"], "2024-01-02")
        self.assertEqual(meta["quality_events"], events)

    def test_quarantine_does_not_hide_partial_corruption(self):
        raw = yahoo_prices()
        raw.iloc[0, 0] = np.nan
        yf = SimpleNamespace(download=Mock(return_value=raw))
        with patch("hkquant.data.importlib.import_module", return_value=yf):
            with self.assertRaises(DataDownloadError):
                fetch_yahoo(["JNJ"], "2024-01-01", "2024-01-05", missing_bar_policy="quarantine_empty")

    def test_downloads_all_tickers_and_records_provenance(self):
        yf = SimpleNamespace(__version__="test-version", download=Mock(side_effect=[yahoo_prices(), yahoo_prices()]))
        with patch("hkquant.data.importlib.import_module", return_value=yf):
            prices, metadata = fetch_yahoo(["0700.hk", "9988.HK"], "2024-01-01", "2024-01-05")
        self.assertEqual(set(prices["ticker"]), {"0700.HK", "9988.HK"})
        self.assertEqual(metadata["requested_tickers"], ["0700.HK", "9988.HK"])
        self.assertEqual(metadata["yfinance_version"], "test-version")
        self.assertEqual(metadata["end_exclusive"], "2024-01-05")
        self.assertEqual(metadata["rows_by_ticker"], {"0700.HK": 2, "9988.HK": 2})
        self.assertTrue(metadata["raw_data_limitations"])
        self.assertIsNone(prices["date"].dt.tz)
        for call in yf.download.call_args_list:
            self.assertFalse(call.kwargs["auto_adjust"])
            self.assertFalse(call.kwargs["actions"])
            self.assertFalse(call.kwargs["threads"])
            self.assertFalse(call.kwargs["multi_level_index"])
            self.assertTrue(call.kwargs["keepna"])

    def test_missing_one_ticker_fails_instead_of_shrinking_pool(self):
        yf = SimpleNamespace(download=Mock(side_effect=[yahoo_prices(), pd.DataFrame(), pd.DataFrame()]))
        with patch("hkquant.data.importlib.import_module", return_value=yf):
            with self.assertRaisesRegex(DataDownloadError, "9988.HK.*2 attempts"):
                fetch_yahoo(["0700.HK", "9988.HK"], "2024-01-01", "2024-01-05")
        self.assertEqual(yf.download.call_count, 3)

    def test_retry_can_recover_transient_network_error(self):
        yf = SimpleNamespace(download=Mock(side_effect=[TimeoutError("timeout"), yahoo_prices()]))
        with patch("hkquant.data.importlib.import_module", return_value=yf):
            prices, _ = fetch_yahoo(["0700.HK"], "2024-01-01", "2024-01-05")
        self.assertEqual(len(prices), 2)
        self.assertEqual(yf.download.call_count, 2)

    def test_rejects_missing_adjusted_close_and_invalid_prices(self):
        broken_cases = [yahoo_prices().drop(columns=["Adj Close"]), yahoo_prices()]
        broken_cases[1].iloc[0, broken_cases[1].columns.get_loc("Close")] = 0
        for broken in broken_cases:
            yf = SimpleNamespace(download=Mock(return_value=broken))
            with self.subTest(columns=broken.columns.tolist()):
                with patch("hkquant.data.importlib.import_module", return_value=yf):
                    with self.assertRaises(DataDownloadError):
                        fetch_yahoo(["0700.HK"], "2024-01-01", "2024-01-05")

    def test_rejects_duplicate_yahoo_dates(self):
        raw = yahoo_prices()
        raw.index = pd.DatetimeIndex([raw.index[0], raw.index[0]])
        yf = SimpleNamespace(download=Mock(return_value=raw))
        with patch("hkquant.data.importlib.import_module", return_value=yf):
            with self.assertRaisesRegex(DataDownloadError, "Duplicate"):
                fetch_yahoo(["0700.HK"], "2024-01-01", "2024-01-05")

    def test_rejects_unexpected_index_and_outside_date_range(self):
        for broken in [yahoo_prices().reset_index(drop=True), yahoo_prices().set_axis(pd.date_range("2023-01-01", periods=2))]:
            yf = SimpleNamespace(download=Mock(return_value=broken))
            with patch("hkquant.data.importlib.import_module", return_value=yf):
                with self.assertRaises(DataDownloadError):
                    fetch_yahoo(["0700.HK"], "2024-01-01", "2024-01-05")

    def test_rejects_invalid_requests_before_importing_yfinance(self):
        with patch("hkquant.data.importlib.import_module") as importer:
            for tickers, start, end in [
                ([], "2024-01-01", "2024-01-05"),
                (["0700.HK", "0700.hk"], "2024-01-01", "2024-01-05"),
                (["0700.HK"], "2024-01-05", "2024-01-05"),
                (["0700.HK"], "01/01/2024", "2024-01-05"),
            ]:
                with self.assertRaises(ValueError):
                    fetch_yahoo(tickers, start, end)
            importer.assert_not_called()


if __name__ == "__main__":
    unittest.main()
