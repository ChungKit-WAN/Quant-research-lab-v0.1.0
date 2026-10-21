"""Monthly stock selection using the common execution and accounting engine.

The supplied CSV is a fixed research universe, not point-in-time historical
membership. Signal generation is causal, but that alone cannot remove universe
selection bias, survivorship bias, or retrospective vendor price adjustments.
"""

from dataclasses import dataclass, field, replace
from numbers import Integral

import numpy as np
import pandas as pd

from hkquant.data import PRICE_COLUMNS, validate_prices as validate_ohlcv
from hkquant.factors import compute_factors
from hkquant.ranking import DEFAULT_WEIGHTS, build_monthly_rankings
from hkquant.registry import IMPLEMENTED_SPECS
from sector_backtest.pipeline import (
    MonthlyConfig,
    build_monthly_schedule,
    evaluate_targets,
    validate_prices,
)


def _validate_selection(config, top_n, ranking_window):
    if not isinstance(config, MonthlyConfig):
        raise TypeError("config must be a MonthlyConfig")
    if (isinstance(top_n, bool) or not isinstance(top_n, Integral)
            or not 1 <= top_n <= len(config.tickers)):
        raise ValueError("top_n must be a positive integer no larger than the universe")
    if 1 / top_n > config.max_weight + 1e-12:
        raise ValueError("Equal-weight top_n allocation exceeds max_weight")
    if (isinstance(ranking_window, bool) or not isinstance(ranking_window, Integral)
            or ranking_window < 1):
        raise ValueError("ranking_window must be a positive integer")


@dataclass
class _PreparedFactorInputs:
    config: MonthlyConfig
    wide: pd.DataFrame
    schedule: pd.DataFrame
    history: pd.DataFrame
    factors: pd.DataFrame
    rankings: dict = field(default_factory=dict)


def _prepare_factor_inputs(long_prices, config):
    """Private, per-run preparation; no persistent or cross-dataset cache."""
    if not isinstance(config, MonthlyConfig):
        raise TypeError("config must be a MonthlyConfig")
    prices = validate_ohlcv(long_prices)
    wide = prices.pivot(index="date", columns="ticker", values="adj_close")
    wide = validate_prices(wide, config)
    schedule = build_monthly_schedule(wide, config)

    # All indicators use trailing observations; cross-sectional scores use one
    # month at a time, and rank smoothing uses only prior/current months. They
    # can therefore be computed once and selected at each exact signal date.
    # Exclude even the last execution row from signal inputs. The ranking API
    # excludes its as_of calendar month, hence the following month's boundary.
    last_signal = schedule.iloc[-1].signal
    history = prices.loc[prices.date <= last_signal].copy()
    factors = compute_factors(history)
    return _PreparedFactorInputs(config, wide, schedule, history, factors)


def _run_factor_monthly_prepared(prepared, config, top_n=4, ranking_window=3, group_weights=None):
    """Reuse validated factors only within one dataset and compatible config.

    Cost changes do not alter signals. The transient ranking cache also keys
    eligibility count, smoothing and all group weights, so ablations cannot
    accidentally reuse baseline scores.
    """
    _validate_selection(config, top_n, ranking_window)
    if not isinstance(prepared, _PreparedFactorInputs):
        raise TypeError("prepared must be internally validated factor inputs")
    if replace(prepared.config, cost_bps=config.cost_bps) != config:
        raise ValueError("Prepared inputs can only be reused with the same config apart from cost_bps")
    wide, schedule, history, factors = prepared.wide, prepared.schedule, prepared.history, prepared.factors
    last_signal = schedule.iloc[-1].signal
    weights = dict(DEFAULT_WEIGHTS if group_weights is None else group_weights)
    cache_key = (int(ranking_window), max(2, top_n), tuple(sorted(weights.items())))
    if cache_key not in prepared.rankings:
        prepared.rankings[cache_key] = build_monthly_rankings(
            history, factors, as_of=(last_signal.to_period("M") + 1).start_time,
            weights=weights, ranking_window=ranking_window,
            min_stocks=max(2, top_n),
        )
    rankings = prepared.rankings[cache_key]
    targets = {"equal_weight": [], "multifactor_top_n": []}
    signals = []
    for event in schedule.itertuples(index=False):
        snapshot = rankings.loc[rankings.date.eq(event.signal)]
        eligible = snapshot.loc[
            snapshot.rolling_eligible & np.isfinite(snapshot.rolling_rank)
        ].sort_values(["rolling_rank", "ticker"], kind="stable")
        if len(eligible) < top_n:
            reasons = sorted(set(snapshot.reason) | set(snapshot.rolling_reason))
            reasons = [reason for reason in reasons if reason != "ok"]
            raise ValueError(
                f"Insufficient eligible stocks at {event.signal.date()}: "
                f"{len(eligible)} < top_n={top_n}; " + "; ".join(reasons)
            )
        selected = eligible.head(top_n)
        selected_tickers = selected.ticker.tolist()
        targets["equal_weight"].append(np.full(len(config.tickers), 1 / len(config.tickers)))
        targets["multifactor_top_n"].append(np.asarray([
            1 / top_n if ticker in selected_tickers else 0.0 for ticker in config.tickers
        ]))
        signals.append({
            "signal": event.signal.strftime("%Y-%m-%d"),
            "execution": event.execution.strftime("%Y-%m-%d"),
            "data_cutoff": event.signal.strftime("%Y-%m-%d"),
            "eligible_stocks": len(eligible),
            "selected_tickers": selected_tickers,
            "selected_rolling_ranks": {
                row.ticker: float(row.rolling_rank) for row in selected.itertuples(index=False)
            },
        })

    result = evaluate_targets(wide, config, schedule, targets, signals)
    result.update({
        "schema_version": "monthly_factor_backtest_v0.1",
        "research_method": "monthly_multifactor_top_n",
        "factor_config": {
            "implemented_factor_count": len(IMPLEMENTED_SPECS),
            "factor_ids": [spec.id for spec in IMPLEMENTED_SPECS],
            "top_n": int(top_n),
            "ranking_window": int(ranking_window),
            "group_weights": {key: float(value) for key, value in weights.items()},
            "selection_order": ["rolling_rank_ascending", "ticker_ascending"],
            "missing_factor_policy": "require_all_65_factors_and_consecutive_valid_months",
            "insufficient_selection_policy": "fail_entire_run",
            "universe_policy": "fixed_user_supplied_csv_universe",
            "point_in_time_universe": False,
            "input_columns": list(PRICE_COLUMNS),
        },
        "limitations": [
            "The fixed supplied universe can contain selection and survivorship bias; "
            "historical membership and delisted-stock coverage are not verified.",
            "Causal signals do not make the vendor data a point-in-time database; "
            "adjusted prices can be revised retrospectively.",
            "Factor directions and group weights are research hypotheses, not validated alpha.",
            "The common ledger uses synthetic adjusted-price wealth, fractional units, "
            "and proportional costs; it is not a raw-share brokerage ledger.",
            "This version uses the XNYS regular-session calendar for a fixed US universe.",
        ],
    })
    return result


def run_factor_monthly(
    long_prices: pd.DataFrame,
    config: MonthlyConfig,
    top_n: int = 4,
    ranking_window: int = 3,
    group_weights: dict[str, float] | None = None,
) -> dict:
    """Rank complete 65-factor observations and buy equal-weighted top stocks.

    Required input columns are ``date,ticker,open,high,low,close,adj_close,volume``.
    Prices must cover every configured asset on every XNYS session. Month-end
    decisions execute at the next session's close through ``evaluate_targets``.
    No missing prices, factor values, or ranking months are filled. If fewer
    than ``top_n`` stocks are eligible at any decision, the whole run fails;
    there is no silent fallback to old holdings, fewer stocks, or cash.

    ``config.lookback`` is the common minimum input-history requirement. Factor
    windows and the consecutive-month ranking window impose additional history
    requirements; they are not truncated to that common lookback.
    """
    _validate_selection(config, top_n, ranking_window)
    return _run_factor_monthly_prepared(
        _prepare_factor_inputs(long_prices, config), config,
        top_n=top_n, ranking_window=ranking_window, group_weights=group_weights)
