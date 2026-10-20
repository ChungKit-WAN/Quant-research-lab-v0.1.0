"""Monthly cross-sectional research rankings, without simulated executions.

Month anchors are the last supplied date, including explicitly marked empty bars.
They are not an independently verified exchange calendar: a market-wide
outage with no rows at all cannot be detected here. The as_of calendar month is
always excluded, including when as_of itself is a calendar month end.
"""

from collections.abc import Mapping
from numbers import Integral

import numpy as np
import pandas as pd

from .registry import IMPLEMENTED_SPECS


DEFAULT_WEIGHTS = {"momentum": 0.30, "reversal": 0.10, "risk": 0.40, "liquidity": 0.20}
GROUPS = tuple(DEFAULT_WEIGHTS)
FACTOR_IDS = tuple(spec.id for spec in IMPLEMENTED_SPECS)
OUTPUT_COLUMNS = [
    "date", "ticker", "eligible", "reason", "score", "rank", "rank_percentile",
    "rolling_mean_rank", "rolling_mean_percentile", "rolling_rank",
    "rolling_eligible", "rolling_reason",
] + [f"group_score_{group}" for group in GROUPS]


def _dates(values, label):
    parsed = pd.to_datetime(values, errors="raise")
    if parsed.isna().any():
        raise ValueError(f"{label} must not contain missing dates")
    if parsed.dt.tz is not None:
        raise ValueError(f"{label} must contain timezone-naive daily dates")
    if not parsed.eq(parsed.dt.normalize()).all():
        raise ValueError(f"{label} must contain daily dates without time of day")
    return parsed


def _frame(frame, required, label):
    if not isinstance(frame, pd.DataFrame):
        raise TypeError(f"{label} must be a pandas DataFrame")
    missing = set(required) - set(frame.columns)
    if missing:
        raise ValueError(f"{label} missing columns: {sorted(missing)}")
    result = frame.copy()
    result["date"] = _dates(result["date"], f"{label}.date")
    if result["ticker"].isna().any() or not result["ticker"].map(
        lambda value: isinstance(value, str) and bool(value.strip()) and value == value.strip()
    ).all():
        raise ValueError(f"{label}.ticker must contain nonempty, trimmed strings")
    if result.duplicated(["date", "ticker"]).any():
        raise ValueError(f"{label} contains duplicate date/ticker observations")
    return result


def _universe(frame):
    if frame is None:
        return None
    required = {"ticker", "effective_from", "effective_to"}
    if not isinstance(frame, pd.DataFrame) or not required.issubset(frame.columns):
        raise ValueError("universe requires ticker/effective_from/effective_to columns")
    if frame.empty:
        raise ValueError("universe must not be empty; use None for the supplied-price universe")
    result = frame.loc[:, ["ticker", "effective_from", "effective_to"]].copy()
    if result.ticker.isna().any() or not result.ticker.map(
        lambda value: isinstance(value, str) and bool(value.strip()) and value == value.strip()
    ).all():
        raise ValueError("universe.ticker must contain nonempty, trimmed strings")
    result["effective_from"] = _dates(result.effective_from, "universe.effective_from")
    # Blank end dates mean membership remains open. Starts must always be known.
    ends = result.effective_to.replace(r"^\s*$", pd.NaT, regex=True)
    result["effective_to"] = pd.to_datetime(ends, errors="raise")
    supplied_ends = result.effective_to.dropna()
    if len(supplied_ends):
        _dates(supplied_ends, "universe.effective_to")
    if (result.effective_to.notna() & (result.effective_to <= result.effective_from)).any():
        raise ValueError("universe intervals require effective_to > effective_from")
    for ticker, history in result.groupby("ticker"):
        previous_end = None
        for row in history.sort_values("effective_from").itertuples(index=False):
            if previous_end is not None and row.effective_from < previous_end:
                raise ValueError(f"universe has overlapping membership intervals for {ticker}")
            previous_end = row.effective_to if pd.notna(row.effective_to) else pd.Timestamp.max
    return result


def build_monthly_rankings(prices, factors, as_of, weights=None, ranking_window=3,
                           min_stocks=3, universe=None):
    """Score complete observations on common monthly anchors, then smooth ranks.

    All 65 implemented indicators must be finite before a stock is eligible.
    Every factor is direction-adjusted and percentile-scored within the same
    eligible cross-section. A group score is its indicators' arithmetic mean;
    score is the explicit weighted sum of the four groups (higher is better).
    Rank percentiles use (average_tie_rank - 1)/(n - 1), hence 0 is best.

    Missing/nontrading anchor quotes are not replaced with earlier quotes. An
    insufficient eligible cross-section produces reasons, not spurious ranks.
    Rolling results require ranking_window consecutive valid calendar months,
    including the current row. Mean percentiles determine rolling_rank; raw mean
    ranks remain available for interpretation when the universe size changes.

    Optional membership intervals are [effective_from, effective_to), with blank
    end dates allowed. Supplying a file does not verify its provenance, accuracy,
    or that it represents any particular historical index.
    """
    if as_of is None or pd.isna(as_of):
        raise ValueError("as_of must be an explicit date")
    cutoff = pd.Timestamp(as_of)
    if pd.isna(cutoff):
        raise ValueError("as_of must be an explicit date")
    if cutoff.tzinfo is not None:
        raise ValueError("as_of must be a timezone-naive date")
    if not isinstance(ranking_window, Integral) or isinstance(ranking_window, bool) or ranking_window < 1:
        raise ValueError("ranking_window must be a positive integer")
    if not isinstance(min_stocks, Integral) or isinstance(min_stocks, bool) or min_stocks < 2:
        raise ValueError("min_stocks must be an integer >= 2")
    supplied_weights = DEFAULT_WEIGHTS if weights is None else weights
    if not isinstance(supplied_weights, Mapping) or set(supplied_weights) != set(GROUPS):
        raise ValueError(f"weights must explicitly contain exactly these groups: {GROUPS}")
    try:
        checked_weights = {key: float(value) for key, value in supplied_weights.items()}
    except (TypeError, ValueError) as exc:
        raise ValueError("weights must be finite nonnegative numbers summing to 1") from exc
    if not all(np.isfinite(value) and value >= 0 for value in checked_weights.values()) or not np.isclose(
        sum(checked_weights.values()), 1.0, rtol=0, atol=1e-10
    ):
        raise ValueError("weights must be finite nonnegative numbers summing to 1")

    p = _frame(prices, ("date", "ticker", "close", "adj_close", "volume"), "prices")
    f = _frame(factors, ("date", "ticker", *FACTOR_IDS), "factors")
    members = _universe(universe)
    month_limit = cutoff.to_period("M").start_time
    p = p.loc[p.date < month_limit].copy()
    f = f.loc[f.date < month_limit].copy()
    if p.empty:
        return pd.DataFrame(columns=OUTPUT_COLUMNS)
    for column in ("close", "adj_close", "volume"):
        p[column] = pd.to_numeric(p[column], errors="raise").replace([np.inf, -np.inf], np.nan)
    f[list(FACTOR_IDS)] = f[list(FACTOR_IDS)].apply(pd.to_numeric, errors="raise").replace(
        [np.inf, -np.inf], np.nan
    )
    p["month"] = p.date.dt.to_period("M")
    anchors = p.groupby("month").date.max()
    first_seen = p.groupby("ticker").date.min()
    months = pd.period_range(p.date.min().to_period("M"), cutoff.to_period("M") - 1, freq="M")
    group_ids = {group: [s.id for s in IMPLEMENTED_SPECS if s.group == group] for group in GROUPS}
    directions = pd.Series({spec.id: spec.direction for spec in IMPLEMENTED_SPECS})
    rows = []
    for month in months:
        has_anchor = month in anchors.index
        anchor = anchors.loc[month] if has_anchor else month.end_time.normalize()
        candidates = set(first_seen.index[first_seen <= anchor])
        active_members = None
        if members is not None:
            active = (members.effective_from <= anchor) & (
                members.effective_to.isna() | (anchor < members.effective_to)
            )
            active_members = set(members.loc[active, "ticker"])
            candidates.update(active_members)
        index = pd.Index(sorted(candidates), name="ticker")
        snapshot = p.loc[p.date.eq(anchor)].set_index("ticker").reindex(index)
        values = f.loc[f.date.eq(anchor)].set_index("ticker").reindex(index)[list(FACTOR_IDS)]
        frame = pd.DataFrame(index=index)
        frame["date"] = anchor
        reasons = pd.Series("", index=index, dtype=object)

        def reject(mask, code):
            previous = reasons.loc[mask]
            reasons.loc[mask] = previous + previous.ne("").map({True: ";", False: ""}) + code

        if not has_anchor:
            reject(pd.Series(True, index=index), "no_market_observations_in_month")
        missing_quote = snapshot.date.isna()
        reject(missing_quote, "missing_anchor_quote")
        invalid_quote = (~missing_quote) & (
            ~snapshot.close.gt(0) | ~snapshot.adj_close.gt(0)
        )
        reject(invalid_quote, "invalid_anchor_price")
        reject((~missing_quote) & ~snapshot.volume.gt(0), "nonpositive_or_missing_anchor_volume")
        if active_members is not None:
            reject(pd.Series(~index.isin(active_members), index=index), "not_in_universe")
        for group, ids in group_ids.items():
            reject(values[ids].isna().any(axis=1), f"incomplete_factors:{group}")
            frame[f"group_score_{group}"] = np.nan
        valid = reasons.eq("")
        count = int(valid.sum())
        frame["score"] = np.nan
        frame["rank"] = np.nan
        frame["rank_percentile"] = np.nan
        if count < min_stocks:
            reject(valid, f"insufficient_eligible_stocks:{count}<{min_stocks}")
            valid = reasons.eq("")
        else:
            adjusted = values.loc[valid].mul(directions, axis=1)
            factor_scores = (adjusted.rank(method="average", ascending=True) - 1) / (count - 1)
            for group, ids in group_ids.items():
                frame.loc[valid, f"group_score_{group}"] = factor_scores[ids].mean(axis=1)
            frame.loc[valid, "score"] = sum(
                frame.loc[valid, f"group_score_{group}"] * checked_weights[group] for group in GROUPS
            )
            frame.loc[valid, "rank"] = frame.loc[valid, "score"].rank(method="average", ascending=False)
            frame.loc[valid, "rank_percentile"] = (frame.loc[valid, "rank"] - 1) / (count - 1)
        frame["eligible"] = valid
        frame["reason"] = reasons.mask(reasons.eq(""), "ok")
        rows.append(frame.reset_index())

    result = pd.concat(rows, ignore_index=True).sort_values(["ticker", "date"])
    # The loop emits every calendar month after a ticker's first observation.
    # NaNs remain in that grid, so missing months cannot be skipped by rolling.
    for source, target in (("rank", "rolling_mean_rank"), ("rank_percentile", "rolling_mean_percentile")):
        result[target] = result.groupby("ticker", sort=False)[source].transform(
            lambda series: series.rolling(ranking_window, min_periods=ranking_window).mean()
        )
    result["rolling_eligible"] = result.eligible & result.rolling_mean_percentile.notna()
    result["rolling_mean_rank"] = result.rolling_mean_rank.where(result.rolling_eligible)
    result["rolling_mean_percentile"] = result.rolling_mean_percentile.where(result.rolling_eligible)
    result["rolling_rank"] = result.groupby("date").rolling_mean_percentile.rank(method="average")
    result["rolling_reason"] = np.where(
        result.rolling_eligible, "ok", f"requires_{ranking_window}_consecutive_valid_months"
    )
    return result.sort_values(["date", "ticker"])[OUTPUT_COLUMNS].reset_index(drop=True)
