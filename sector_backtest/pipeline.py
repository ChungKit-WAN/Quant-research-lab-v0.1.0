"""Monthly decisions, daily accounting, and next-session-close execution."""

from dataclasses import asdict, dataclass
from numbers import Integral, Real

import exchange_calendars as xcals
import numpy as np
import pandas as pd

from .backtest import simulate_synthetic_wealth_path
from .performance import calculate_period_performance
from .portfolio import solve_capped_minimum_variance
from .risk_models import estimate_covariance_models

TICKERS = ("XLB", "XLC", "XLE", "XLF", "XLI", "XLK", "XLP", "XLRE", "XLU", "XLV", "XLY")


def _day(value, name):
    date = pd.Timestamp(value)
    if pd.isna(date) or date.tzinfo is not None or date != date.normalize():
        raise ValueError(f"{name} must be a timezone-naive daily date")
    return date


@dataclass(frozen=True)
class MonthlyConfig:
    tickers: tuple[str, ...] = TICKERS
    lookback: int = 504
    research_start: str = "2021-01-01"
    holdout_start: str = "2024-01-01"
    cost_bps: float = 5.0
    max_weight: float = 0.25
    initial_cash: float = 1.0

    def __post_init__(self):
        if isinstance(self.tickers, str):
            raise ValueError("tickers must be a sequence of asset symbols")
        object.__setattr__(self, "tickers", tuple(self.tickers))
        if (len(self.tickers) < 2 or len(set(self.tickers)) != len(self.tickers)
                or not all(isinstance(t, str) and t and t == t.strip() for t in self.tickers)):
            raise ValueError("At least two unique, nonempty ticker strings are required")
        if (isinstance(self.lookback, bool) or not isinstance(self.lookback, Integral)
                or self.lookback <= len(self.tickers)):
            raise ValueError("lookback must be an integer greater than the asset count")
        start = _day(self.research_start, "research_start")
        holdout = _day(self.holdout_start, "holdout_start")
        if start.day != 1 or holdout <= start:
            raise ValueError("research_start must be a month start; holdout_start must be later")
        for name in ("cost_bps", "max_weight", "initial_cash"):
            value = getattr(self, name)
            if isinstance(value, (bool, np.bool_)) or not isinstance(value, Real) or not np.isfinite(value):
                raise ValueError(f"{name} must be a finite real number")
        if not 0 <= self.cost_bps < 10000 or self.initial_cash <= 0:
            raise ValueError("Invalid cost rate or initial cash")
        if not 1 / len(self.tickers) <= self.max_weight <= 1:
            raise ValueError("Infeasible target weight cap")


def sessions(start, end):
    """XNYS is an explicit regular-session proxy for the sector ETFs."""
    calendar = xcals.get_calendar("XNYS", start=start, end=end)
    dates = calendar.sessions
    if dates.tz is not None:
        dates = dates.tz_localize(None)
    return pd.DatetimeIndex(dates[(dates >= pd.Timestamp(start)) & (dates <= pd.Timestamp(end))])


def validate_prices(prices, config):
    if not isinstance(prices, pd.DataFrame) or len(prices) < 3:
        raise ValueError("At least three price sessions are required")
    index = prices.index
    if (not isinstance(index, pd.DatetimeIndex) or index.tz is not None or index.hasnans
            or not index.is_unique or not index.is_monotonic_increasing
            or not (index == index.normalize()).all()):
        raise ValueError("Prices require ordered unique timezone-naive daily session dates")
    if not prices.columns.is_unique or set(prices.columns) != set(config.tickers):
        raise ValueError("Price columns must match the configured universe exactly")
    for dtype in prices.dtypes:
        if (not pd.api.types.is_numeric_dtype(dtype) or pd.api.types.is_bool_dtype(dtype)
                or pd.api.types.is_complex_dtype(dtype)):
            raise ValueError("Prices must be real numeric values")
    frame = prices.loc[:, list(config.tickers)].astype(float).copy()
    if not np.isfinite(frame.to_numpy()).all() or not (frame.to_numpy() > 0).all():
        raise ValueError("Prices must be finite and positive; missing prices are not filled")
    expected = sessions(index[0], index[-1])
    if not index.equals(expected):
        missing = expected.difference(index).strftime("%Y-%m-%d").tolist()
        extra = index.difference(expected).strftime("%Y-%m-%d").tolist()
        raise ValueError(f"XNYS session mismatch: missing={missing[:8]}, extra={extra[:8]}")
    return frame


def build_monthly_schedule(prices, config):
    prices = validate_prices(prices, config)
    start = pd.Timestamp(config.research_start)
    first_month = start.to_period("M") - 1
    # Include the full final month plus its next session to avoid mistaking a
    # truncated CSV's last observed date for an actual month end.
    end = (prices.index[-1].to_period("M") + 2).start_time
    calendar = sessions(first_month.start_time, end)
    anchors = pd.Series(calendar, index=calendar).groupby(calendar.to_period("M")).max()
    initial_signal = anchors.loc[first_month]
    events = []
    for signal in anchors:
        pos = calendar.get_loc(signal)
        if pos + 1 >= len(calendar):
            continue
        execution = calendar[pos + 1]
        if execution < start or execution > prices.index[-1]:
            continue
        if signal not in prices.index or execution not in prices.index:
            raise ValueError("Missing signal or execution session, including initial entry")
        if prices.index.get_loc(signal) < config.lookback:
            raise ValueError(f"Insufficient history at {signal.date()}: need {config.lookback} returns")
        events.append({"signal": signal, "execution": execution})
    if not events or events[0]["signal"] != initial_signal:
        raise ValueError("No complete initial month-end signal and next-session execution")
    if len(prices.loc[events[0]["execution"]:]) < 2:
        raise ValueError("At least two research sessions are required")
    return pd.DataFrame(events)


def run_monthly(prices, config=None):
    config = config or MonthlyConfig()
    prices = validate_prices(prices, config)
    schedule = build_monthly_schedule(prices, config)
    returns = prices.pct_change(fill_method=None).iloc[1:]
    names = ("equal_weight", "sample_min_variance", "shrinkage_min_variance")
    targets = {name: [] for name in names}
    signals = []
    for event in schedule.itertuples(index=False):
        window = returns.loc[:event.signal].tail(config.lookback)
        models = estimate_covariance_models(window)
        targets["equal_weight"].append(np.full(len(config.tickers), 1 / len(config.tickers)))
        for name, model in (("sample_min_variance", "sample_covariance"),
                            ("shrinkage_min_variance", "shrunk_covariance")):
            matrix = models[model]
            covariance = pd.DataFrame(matrix["values"], index=matrix["columns"], columns=matrix["columns"])
            solution = solve_capped_minimum_variance(covariance, max_weight=config.max_weight)
            targets[name].append(solution["weights"])
        signals.append({"signal": event.signal.strftime("%Y-%m-%d"),
                        "execution": event.execution.strftime("%Y-%m-%d"),
                        "window_first": window.index[0].strftime("%Y-%m-%d"),
                        "window_last": window.index[-1].strftime("%Y-%m-%d"),
                        "window_observations": len(window),
                        "returns_sha256": models["input_returns_sha256"]})
    return evaluate_targets(prices, config, schedule, targets, signals)


def evaluate_targets(prices, config, schedule, targets, signals):
    """Shared execution and evaluation for ETF and equity target strategies.

    Target constructors own signal causality. This boundary checks alignment
    against the independently constructed calendar before executing any trades.
    """
    prices = validate_prices(prices, config)
    expected_schedule = build_monthly_schedule(prices, config)
    if not schedule.reset_index(drop=True).equals(expected_schedule):
        raise ValueError("Target schedule differs from the verified monthly calendar")
    if not targets or len(signals) != len(schedule):
        raise ValueError("Complete strategy targets and signal metadata are required")
    for event, metadata in zip(schedule.itertuples(index=False), signals):
        if (metadata["signal"] != event.signal.strftime("%Y-%m-%d")
                or metadata["execution"] != event.execution.strftime("%Y-%m-%d")):
            raise ValueError("Signal metadata differs from execution schedule")
    ledgers, metrics, weights, period_status = {}, [], [], {}
    ledger_prices = prices.loc[schedule.iloc[0].signal:]
    for name in targets:
        if len(targets[name]) != len(schedule):
            raise ValueError("Every scheduled event requires one target vector")
        target = pd.DataFrame(targets[name], index=pd.DatetimeIndex(schedule.execution), columns=config.tickers)
        ledger = simulate_synthetic_wealth_path(
            ledger_prices, target, initial_cash=config.initial_cash,
            cost_bps=config.cost_bps, max_weight=config.max_weight,
        )
        ledgers[name] = ledger
        for event, vector in zip(signals, targets[name]):
            weights.extend({"strategy": name, "signal": event["signal"], "execution": event["execution"],
                            "ticker": ticker, "weight": float(value)}
                           for ticker, value in zip(config.tickers, vector))
        holdout = pd.Timestamp(config.holdout_start)
        for period in ("full", "development", "holdout"):
            rows = [row for row in ledger["daily"] if period == "full"
                    or (period == "development" and pd.Timestamp(row["session"]) < holdout)
                    or (period == "holdout" and pd.Timestamp(row["session"]) >= holdout)]
            period_status[period] = "computed" if len(rows) >= 2 else "fewer_than_two_sessions"
            if len(rows) >= 2:
                metrics.append({"strategy": name, "period": period,
                                **calculate_period_performance(rows, tickers=config.tickers)})
    return {"config": asdict(config), "schedule": signals, "strategies": ledgers,
            "metrics": metrics, "target_weights": weights, "period_status": period_status}


def demo_prices(config=None):
    """Deterministic synthetic test data: never market performance evidence."""
    config = config or MonthlyConfig()
    start = pd.Timestamp(config.research_start) - pd.DateOffset(years=4)
    end = pd.Timestamp(config.holdout_start) + pd.DateOffset(years=1) - pd.Timedelta(days=1)
    dates = sessions(start, end)
    rng = np.random.default_rng(20261019)
    market = rng.normal(0.00015, 0.006, (len(dates), 1))
    noise = rng.normal(0, np.linspace(0.004, 0.012, len(config.tickers)), (len(dates), len(config.tickers)))
    values = 100 * np.exp(np.cumsum(market + noise, axis=0))
    return pd.DataFrame(values, index=dates, columns=config.tickers)
