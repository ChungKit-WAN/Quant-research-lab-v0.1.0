"""Daily price input, validation, and optional Yahoo Finance downloads.

The canonical input deliberately separates ``close`` (the provider's Close)
from ``adj_close`` (the provider's adjusted price). Close may already reflect
historical split adjustments and is not guaranteed to be an original trade.
Missing adjusted prices are
never replaced with raw closes, and missing sessions are never forward filled.
"""

from __future__ import annotations

from datetime import date, datetime, timezone
import importlib
from pathlib import Path
import re
from typing import Any, BinaryIO

import numpy as np
import pandas as pd


PRICE_COLUMNS = [
    "date", "ticker", "open", "high", "low", "close", "adj_close", "volume"
]
NUMERIC_COLUMNS = ["open", "high", "low", "close", "adj_close", "volume"]
_YAHOO_COLUMNS = {
    "Open": "open",
    "High": "high",
    "Low": "low",
    "Close": "close",
    "Adj Close": "adj_close",
    "Volume": "volume",
}


class DataValidationError(ValueError):
    """The supplied data cannot safely be used as daily historical prices."""


class DataDownloadError(RuntimeError):
    """At least one requested ticker could not be downloaded completely."""


def _local_trading_date(value: Any) -> pd.Timestamp:
    """Keep the exchange-local calendar day when removing a timezone."""
    if pd.isna(value) or isinstance(value, (bool, int, float, np.number)):
        raise ValueError("A date must be a non-empty calendar date, not a number.")
    stamp = pd.Timestamp(value)
    if pd.isna(stamp):
        raise ValueError("A date must not be NaT.")
    if stamp.tzinfo is not None:
        stamp = stamp.tz_localize(None)
    return stamp.normalize()


def validate_prices(df: pd.DataFrame) -> pd.DataFrame:
    """Return sorted, validated canonical prices without filling missing data.

    ``date`` represents an exchange-local trading day, so timezone removal does
    not shift a Hong Kong midnight into the preceding UTC date. All prices must
    be finite and positive; volume must be finite and nonnegative. There can be
    at most one row per ticker and trading day. No assumption about today's date
    is made, allowing deterministic historical tests.
    """
    if not isinstance(df, pd.DataFrame):
        raise DataValidationError("Prices must be a pandas DataFrame.")
    if not df.columns.is_unique:
        raise DataValidationError("Price column names must be unique.")
    missing = [column for column in PRICE_COLUMNS if column not in df.columns]
    if missing:
        raise DataValidationError("Missing required price columns: " + ", ".join(missing))
    if df.empty:
        raise DataValidationError("Price data is empty.")

    prices = df.loc[:, PRICE_COLUMNS].copy()
    valid_tickers = prices["ticker"].map(
        lambda value: isinstance(value, str) and bool(value.strip())
    )
    if not valid_tickers.all():
        raise DataValidationError("Every ticker must be a non-empty string.")
    prices["ticker"] = prices["ticker"].str.strip()
    try:
        prices["date"] = pd.to_datetime(
            [_local_trading_date(value) for value in prices["date"]], errors="raise"
        )
    except (TypeError, ValueError, OverflowError) as exc:
        raise DataValidationError("Invalid trading date: " + str(exc)) from exc

    duplicates = prices.duplicated(["ticker", "date"], keep=False)
    if duplicates.any():
        example = prices.loc[duplicates, ["ticker", "date"]].iloc[0]
        raise DataValidationError(
            f"Duplicate ticker/date: {example['ticker']} {example['date'].date()}."
        )

    for column in NUMERIC_COLUMNS:
        if prices[column].map(lambda value: isinstance(value, (bool, np.bool_))).any():
            raise DataValidationError(f"{column} must contain numbers, not booleans.")
        try:
            values = pd.to_numeric(prices[column], errors="raise").astype(float)
        except (TypeError, ValueError, OverflowError) as exc:
            raise DataValidationError(f"{column} contains nonnumeric values.") from exc
        if not np.isfinite(values.to_numpy()).all():
            raise DataValidationError(f"{column} contains missing or nonfinite values.")
        if column == "volume":
            if (values < 0).any():
                raise DataValidationError("volume must be nonnegative.")
        elif (values <= 0).any():
            raise DataValidationError(f"{column} must be strictly positive.")
        prices[column] = values

    invalid_range = (
        (prices["high"] < prices[["open", "close", "low"]].max(axis=1))
        | (prices["low"] > prices[["open", "close", "high"]].min(axis=1))
    )
    if invalid_range.any():
        raise DataValidationError("Invalid OHLC range: low <= open/close <= high is required.")
    return prices.sort_values(["ticker", "date"]).reset_index(drop=True)


def load_prices_csv(path: str | Path | BinaryIO) -> pd.DataFrame:
    """Read a UTF-8 CSV using the canonical schema and preserve ticker zeros."""
    try:
        raw = pd.read_csv(path, dtype={"ticker": "string"}, encoding="utf-8-sig")
    except (pd.errors.ParserError, pd.errors.EmptyDataError, UnicodeError) as exc:
        raise DataValidationError(f"Cannot parse price CSV: {exc}") from exc
    return validate_prices(raw)


def _parse_request_date(value: str, name: str) -> date:
    if not isinstance(value, str) or not re.fullmatch(r"\d{4}-\d{2}-\d{2}", value):
        raise ValueError(f"{name} must use YYYY-MM-DD format.")
    try:
        return date.fromisoformat(value)
    except ValueError as exc:
        raise ValueError(f"Invalid {name}: {value}.") from exc


def _download_one(yf: Any, ticker: str, start: str, end: str, raw_sink=None,
                  missing_bar_policy="reject", quality_sink=None) -> pd.DataFrame:
    last_error: Exception | None = None
    raw: pd.DataFrame | None = None
    # A failed response gets one retry. Invalid price data is never repaired.
    for _attempt in range(2):
        try:
            raw = yf.download(
                tickers=ticker,
                start=start,
                end=end,
                interval="1d",
                auto_adjust=False,
                actions=False,
                multi_level_index=False,
                threads=False,
                progress=False,
                keepna=True,
                timeout=20,
            )
            if not isinstance(raw, pd.DataFrame):
                raise DataDownloadError(f"Yahoo returned a non-DataFrame response for {ticker}.")
            if raw.empty:
                raise DataDownloadError(f"Yahoo returned no price data for {ticker}.")
            break
        except Exception as exc:
            last_error = exc
            raw = None
    if raw is None:
        raise DataDownloadError(
            f"Download failed for {ticker} after 2 attempts; no reduced stock pool was returned. "
            f"Last error: {last_error}"
        ) from last_error
    if raw_sink is not None:
        raw_sink(ticker, raw.copy(deep=True))
    if isinstance(raw.columns, pd.MultiIndex) or not raw.columns.is_unique:
        raise DataDownloadError(f"Unexpected Yahoo column layout for {ticker}.")
    missing = [column for column in _YAHOO_COLUMNS if column not in raw.columns]
    if missing:
        raise DataDownloadError(
            f"Yahoo data for {ticker} is missing columns: {', '.join(missing)}. "
            "Adjusted close cannot be replaced with raw close."
        )
    if not isinstance(raw.index, pd.DatetimeIndex):
        raise DataDownloadError(f"Yahoo daily data for {ticker} must have a DatetimeIndex.")
    frame = raw.loc[:, list(_YAHOO_COLUMNS)].rename(columns=_YAHOO_COLUMNS).copy()
    frame.insert(0, "ticker", ticker)
    frame.insert(0, "date", raw.index)
    # Only wholly empty bars with zero volume can be quarantined explicitly.
    # Partial/bad prices remain fatal. The unmodified response was captured above.
    dates = pd.DatetimeIndex([_local_trading_date(value) for value in raw.index])
    if not dates.is_unique:
        raise DataDownloadError(f"Duplicate Yahoo dates for {ticker}.")
    if ((dates < pd.Timestamp(start)) | (dates >= pd.Timestamp(end))).any():
        raise DataDownloadError(f"Yahoo returned dates outside [{start}, {end}) for {ticker}.")
    if missing_bar_policy == "quarantine_empty":
        empty = frame[["open", "high", "low", "close", "adj_close"]].isna().all(axis=1) & frame.volume.eq(0)
        for day in dates[empty.to_numpy()]:
            if quality_sink is not None:
                quality_sink({"ticker": ticker, "date": day.strftime("%Y-%m-%d"),
                              "issue": "empty_price_bar", "action": "Retain original; exclude invalid bar; preserve missing factor observation"})
        frame = frame.loc[~empty].copy()
    try:
        validated = validate_prices(frame)
    except DataValidationError as exc:
        raise DataDownloadError(f"Invalid Yahoo price data for {ticker}: {exc}") from exc
    if ((validated["date"] < pd.Timestamp(start)) | (validated["date"] >= pd.Timestamp(end))).any():
        raise DataDownloadError(f"Yahoo returned dates outside [{start}, {end}) for {ticker}.")
    return validated


def fetch_yahoo(tickers: list[str], start: str, end: str, *, raw_sink=None,
                missing_bar_policy="reject", quality_sink=None) -> tuple[pd.DataFrame, dict]:
    """Fetch each requested symbol; fail rather than silently drop a symbol.

    Yahoo's end date is exclusive. Downloads are sequential and have bounded
    retries. yfinance is imported only here, so local CSV use requires no network
    access or installation of the optional downloader.
    """
    if missing_bar_policy not in ("reject", "quarantine_empty"):
        raise ValueError("missing_bar_policy must be reject or quarantine_empty")
    if not isinstance(tickers, list) or not tickers:
        raise ValueError("tickers must be a non-empty list of ticker strings.")
    if any(not isinstance(ticker, str) or not ticker.strip() for ticker in tickers):
        raise ValueError("Every requested ticker must be a non-empty string.")
    requested = [ticker.strip().upper() for ticker in tickers]
    if len(set(requested)) != len(requested):
        raise ValueError("Requested tickers must be unique.")
    start_date = _parse_request_date(start, "start")
    end_date = _parse_request_date(end, "end")
    if end_date <= start_date:
        raise ValueError("end must be later than start (end is exclusive).")
    try:
        yf = importlib.import_module("yfinance")
    except ImportError as exc:
        raise DataDownloadError(
            "Yahoo download requires yfinance. Install the project's download dependencies "
            "or use a local CSV."
        ) from exc

    quality_events = []

    def record_quality(event):
        quality_events.append(event)
        if quality_sink is not None:
            quality_sink(dict(event))

    frames = [_download_one(yf, ticker, start, end, raw_sink=raw_sink,
                            missing_bar_policy=missing_bar_policy, quality_sink=record_quality)
              for ticker in requested]
    combined = validate_prices(pd.concat(frames, ignore_index=True))
    metadata = {
        "source": "Yahoo Finance via yfinance",
        "yfinance_version": getattr(yf, "__version__", "unknown"),
        "requested_tickers": requested,
        "start": start,
        "end_exclusive": end,
        "retrieved_at_utc": datetime.now(timezone.utc).isoformat(),
        "auto_adjust": False,
        "actions": False,
        "missing_data_policy": missing_bar_policy,
        "quality_events": quality_events,
        "date_policy": "Exchange-local calendar date; timezone removed without UTC conversion.",
        "rows_by_ticker": {str(key): int(value) for key, value in combined.groupby("ticker").size().items()},
        "raw_data_limitations": [
            "Research data, not a point-in-time historical database or an execution feed.",
            "Yahoo prices and adjustment factors can be revised retrospectively.",
            "Adjusted close follows Yahoo's provider conventions; corporate actions are not independently verified.",
            "The requested symbols are a user-selected pool, not historical index constituents.",
            "Complete delisted-stock histories and survivorship-bias-free coverage are not guaranteed.",
            "Available history may start after the requested start date, for example after an IPO.",
        ],
    }
    return combined, metadata
