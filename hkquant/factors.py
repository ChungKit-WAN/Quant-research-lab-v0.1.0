"""Historical-only, per-stock price/volume indicators.

Outputs are unstandardized observations; registry.direction is only a hypothesis.
Missing history stays missing. Financial candidates are intentionally not emitted.
"""

import numpy as np
import pandas as pd

from .registry import IMPLEMENTED_SPECS


def _divide(numerator: pd.Series, denominator: pd.Series) -> pd.Series:
    return numerator.div(denominator.where(denominator.ne(0)))


def _drawdown(values: np.ndarray) -> np.ndarray:
    return 1.0 - values / np.maximum.accumulate(values)


def _one_stock(frame: pd.DataFrame) -> pd.DataFrame:
    p = frame["adj_close"].where(frame["adj_close"].gt(0))
    close = frame["close"].where(frame["close"].gt(0))
    volume = frame["volume"].where(frame["volume"].ge(0))
    amount = close * volume
    r = p.pct_change(fill_method=None)
    # Comparisons must preserve missing returns: NaN is not a zero-return day.
    positive = r.gt(0).astype(float).where(r.notna())
    negative = r.lt(0).astype(float).where(r.notna())
    values: dict[str, pd.Series] = {}

    for n in (21, 42, 63, 126, 189, 252):
        # Require an uninterrupted history, not merely two available endpoints.
        enough = p.rolling(n + 1, min_periods=n + 1).count().eq(n + 1)
        values[f"mom_return_{n}"] = (_divide(p, p.shift(n)) - 1).where(enough)
    for n in (63, 126, 189, 252):
        enough = p.rolling(n + 1, min_periods=n + 1).count().eq(n + 1)
        values[f"mom_skip21_{n}"] = (_divide(p.shift(21), p.shift(n)) - 1).where(enough)
    for n in (21, 63, 126, 252):
        values[f"mom_ma_distance_{n}"] = _divide(p, p.rolling(n).mean()) - 1
    for fast, slow in ((21, 63), (21, 126), (63, 126), (63, 252)):
        values[f"mom_ma_ratio_{fast}_{slow}"] = _divide(p.rolling(fast).mean(), p.rolling(slow).mean()) - 1
    for n in (63, 126):
        values[f"mom_positive_days_{n}"] = positive.rolling(n).mean()

    for n in (1, 3, 5, 10):
        enough = p.rolling(n + 1, min_periods=n + 1).count().eq(n + 1)
        values[f"rev_return_{n}"] = (_divide(p, p.shift(n)) - 1).where(enough)
    for n in (21, 63):
        values[f"rev_price_zscore_{n}"] = _divide(p - p.rolling(n).mean(), p.rolling(n).std(ddof=1))
    delta = p.diff()
    for n in (14, 28):
        gains = delta.clip(lower=0).rolling(n).mean()
        movement = delta.abs().rolling(n).mean()
        rsi = 100 * _divide(gains, movement)
        # A fully observed flat window is neutral; absent history remains NaN.
        values[f"rev_rsi_{n}"] = rsi.mask(movement.eq(0), 50.0)
    for n in (5, 10):
        values[f"rev_negative_days_{n}"] = negative.rolling(n).mean()

    for n in (20, 60, 120, 252):
        values[f"risk_volatility_{n}"] = r.rolling(n).std(ddof=1) * np.sqrt(252)
    for n in (20, 60, 120):
        values[f"risk_downside_{n}"] = np.sqrt(r.clip(upper=0).pow(2).rolling(n).mean() * 252)
    for n in (63, 126, 252):
        values[f"risk_max_drawdown_{n}"] = p.rolling(n).apply(lambda x: float(_drawdown(x).max()), raw=True)
    values["risk_ulcer_63"] = p.rolling(63).apply(lambda x: float(np.sqrt(np.mean(_drawdown(x) ** 2))), raw=True)
    for n in (60, 126):
        values[f"risk_tail_loss_{n}"] = -r.rolling(n).quantile(0.05)
    values["risk_negative_days_63"] = negative.rolling(63).mean()
    values["risk_vol_of_vol_60"] = (r.rolling(20).std(ddof=1) * np.sqrt(252)).rolling(60).std(ddof=1)

    for n in (20, 60, 120):
        values[f"liq_amount_{n}"] = amount.rolling(n).mean()
        values[f"liq_volume_{n}"] = volume.rolling(n).mean()
        values[f"liq_amihud_{n}"] = _divide(r.abs(), amount / 1e6).rolling(n).mean()
    for n in (20, 60):
        values[f"liq_volume_cv_{n}"] = _divide(volume.rolling(n).std(ddof=1), volume.rolling(n).mean())
    for fast, slow in ((5, 20), (20, 60)):
        values[f"liq_volume_ratio_{fast}_{slow}"] = _divide(volume.rolling(fast).mean(), volume.rolling(slow).mean())
        values[f"liq_amount_ratio_{fast}_{slow}"] = _divide(amount.rolling(fast).mean(), amount.rolling(slow).mean())
    for n in (20, 60):
        values[f"liq_zero_volume_{n}"] = volume.eq(0).astype(float).where(volume.notna()).rolling(n).mean()
        values[f"liq_return_volume_corr_{n}"] = r.rolling(n).corr(volume)
    values["liq_price_impact_60"] = _divide(r.rolling(60).std(ddof=1), amount.rolling(60).mean() / 1e6)

    calculated = pd.DataFrame(values, index=frame.index).replace([np.inf, -np.inf], np.nan)
    # A stale/zero-volume quote cannot create a current actionable factor score.
    eligible = volume.gt(0) & p.notna() & close.notna()
    calculated.loc[~eligible, :] = np.nan
    columns = [spec.id for spec in IMPLEMENTED_SPECS]
    return pd.concat([frame[["date", "ticker"]], calculated[columns]], axis=1)


def compute_factors(prices: pd.DataFrame, *, missing_sessions=None) -> pd.DataFrame:
    """Return date, ticker and 65 raw indicators, sorted by ticker then date.

    Required columns: date, ticker, open, high, low, close, adj_close, volume.
    Windows mean supplied daily observations, without filling missing sessions.
    Duplicate stock/date records are rejected rather than silently combined.
    OHLC prices are accepted for the data contract; these indicators do not use
    open/high/low. Invalid non-positive close/adj_close values remain unavailable.
    Optional missing_sessions contains date/ticker records for known empty bars.
    They become all-missing observations, so windows cannot jump across a gap.
    Callers must filter both prices and markers to their explicit date cutoff.
    """
    required = {"date", "ticker", "open", "high", "low", "close", "adj_close", "volume"}
    missing = required.difference(prices.columns)
    if missing:
        raise ValueError(f"Missing required price columns: {', '.join(sorted(missing))}")
    columns = ["date", "ticker"] + [spec.id for spec in IMPLEMENTED_SPECS]
    if prices.empty:
        return pd.DataFrame(columns=columns)
    data = prices.loc[:, ["date", "ticker", "open", "high", "low", "close", "adj_close", "volume"]].copy()
    if missing_sessions:
        markers = pd.DataFrame(missing_sessions).loc[:, ["date", "ticker"]]
        markers["date"] = pd.to_datetime(markers.date, errors="raise")
        data = pd.concat([data, markers.reindex(columns=data.columns)], ignore_index=True)
    if data["ticker"].isna().any() or data["date"].isna().any():
        raise ValueError("date and ticker must not be missing")
    data["date"] = pd.to_datetime(data["date"], errors="raise")
    data["ticker"] = data["ticker"].astype(str)
    if data.duplicated(["date", "ticker"]).any():
        raise ValueError("Duplicate ticker/date observations are not allowed")
    for column in ("open", "high", "low", "close", "adj_close", "volume"):
        data[column] = pd.to_numeric(data[column], errors="raise").replace([np.inf, -np.inf], np.nan)
    data = data.sort_values(["ticker", "date"], kind="stable").reset_index(drop=True)
    chunks = [_one_stock(frame) for _, frame in data.groupby("ticker", sort=False)]
    return pd.concat(chunks, ignore_index=True)[columns]
