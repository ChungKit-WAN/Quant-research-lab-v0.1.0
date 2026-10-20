def rebalance_synthetic_portfolio(units, prices, target_weights, *, cash,
                                  cost_bps=5.0, max_weight=0.25):
    """Simulate one self-financing close rebalance using adjusted-price units."""
    import hashlib
    import inspect
    import json
    import math
    import numbers
    import numpy as np
    import pandas as pd
    from pandas.api.types import is_bool_dtype, is_complex_dtype, is_numeric_dtype

    def require(condition, message):
        if not condition:
            raise ValueError(message)

    def digest(value):
        encoded = json.dumps(value, ensure_ascii=False, sort_keys=True, allow_nan=False)
        return hashlib.sha256(encoded.encode("utf-8")).hexdigest()

    require(isinstance(prices, pd.Series) and len(prices) >= 2, "Prices must be a Series")
    labels = prices.index.tolist()
    require(prices.index.is_unique and all(isinstance(x, str) and x and x == x.strip()
            for x in labels), "Asset labels must be unique nonempty strings")
    for series in (units, prices, target_weights):
        require(isinstance(series, pd.Series) and series.index.tolist() == labels,
                "Units, prices and targets must have identical ordered labels")
        require(is_numeric_dtype(series.dtype) and not is_bool_dtype(series.dtype)
                and not is_complex_dtype(series.dtype), "Inputs must be real numeric Series")
    for value in (cash, cost_bps, max_weight):
        require(isinstance(value, numbers.Real) and not isinstance(value, (bool, np.bool_))
                and np.isfinite(value), "Cash, cost and cap must be finite real numbers")
    require(cash >= 0 and 0 <= cost_bps < 10000, "Invalid cash or cost rate")
    require(1.0 / len(labels) <= max_weight <= 1.0, "Infeasible target weight cap")
    old_units, price, target = [s.to_numpy(dtype=float, copy=True)
                                for s in (units, prices, target_weights)]
    require(all(np.isfinite(x).all() for x in (old_units, price, target)), "Non-finite input")
    require((old_units >= 0).all() and (price > 0).all(), "Units must be nonnegative; prices positive")
    target_sum = math.fsum(target.tolist())
    tolerance = 2e-12
    require((target >= 0).all() and target.max() <= max_weight + 1e-12
            and abs(target_sum - 1.0) <= 1e-12, "Invalid target weights")
    current_values = old_units * price
    require(np.isfinite(current_values).all(), "Position valuation overflow")
    nav_before = math.fsum([float(cash), *current_values.tolist()])
    require(np.isfinite(nav_before) and nav_before > 0, "Positive finite NAV is required")
    current_fraction = current_values / nav_before
    rate = float(cost_bps) / 10000.0

    # y scales the target positions relative to pre-trade NAV.
    def budget(y):
        desired = target * y
        return math.fsum(desired.tolist()) + rate * math.fsum(
            np.abs(desired - current_fraction).tolist()
        )

    low, high = 0.0, 1.0 / target_sum
    iterations = 0
    unchanged = cash == 0 and np.array_equal(target, current_fraction)
    if unchanged or budget(high) <= 1.0:
        low = high
    else:
        require(budget(low) < 1.0 <= budget(high), "Unable to bracket the funding equation")
        for iterations in range(1, 101):
            middle = (low + high) / 2.0
            if budget(middle) <= 1.0:
                low = middle
            else:
                high = middle
            if high - low <= 8 * np.finfo(float).eps * max(1.0, high):
                break
        else:
            raise ValueError("Funding equation did not converge")

    # Recompute actual units and the cash ledger; retain positive cash dust.
    for guard_steps in range(5):
        new_units = old_units.copy() if unchanged else ((target * low) * nav_before) / price
        require(np.isfinite(new_units).all() and (new_units >= 0).all(), "Invalid new units")
        require(not ((target > 0) & (new_units == 0)).any(), "New units underflow")
        post_values = new_units * price
        trade_units = new_units - old_units
        trade_values = trade_units * price
        require(np.isfinite(post_values).all() and np.isfinite(trade_values).all(),
                "Trade valuation overflow")
        buy_notional = math.fsum(np.maximum(trade_values, 0.0).tolist())
        sell_notional = math.fsum(np.maximum(-trade_values, 0.0).tolist())
        fee = rate * (buy_notional + sell_notional)
        cash_after = math.fsum([float(cash), *(-trade_values).tolist(), -fee])
        if cash_after >= 0:
            break
        require(not unchanged, "Unchanged portfolio has a cash deficit")
        low -= max(16 * np.finfo(float).eps, 2 * abs(cash_after) / nav_before / (1 - rate))
        require(low > 0, "Unable to fund trades without borrowing")
    else:
        raise ValueError("Unable to eliminate floating-point cash deficit")

    nav_after = math.fsum([cash_after, *post_values.tolist()])
    require(np.isfinite(nav_after) and nav_after > 0 and np.isfinite(fee), "Invalid post-trade NAV")
    actual_weights = post_values / nav_after
    funding_error = abs(math.fsum([nav_before, -nav_after, -fee])) / nav_before
    weight_error = float(np.max(np.abs(actual_weights - target)))
    require(funding_error <= tolerance and cash_after / nav_after <= tolerance
            and weight_error <= tolerance, "Self-financing or target-weight check failed")
    require(actual_weights.max() <= max_weight + tolerance, "Post-trade cap check failed")
    inputs = {
        "tickers": labels, "units": old_units.tolist(), "prices": price.tolist(),
        "target_weights": target.tolist(), "cash": float(cash),
        "cost_bps": float(cost_bps), "max_weight": float(max_weight),
    }
    return {
        "schema_version": "synthetic_self_financing_rebalance_v1",
        "accounting": "synthetic_adjusted_price_wealth_not_raw_share_cash_ledger",
        "inputs": inputs, "inputs_sha256": digest(inputs),
        "nav_before": nav_before, "nav_after": nav_after,
        "new_units": new_units.tolist(), "post_position_values": post_values.tolist(),
        "trade_units": trade_units.tolist(), "trade_notionals": trade_values.tolist(),
        "buy_notional": buy_notional, "sell_notional": sell_notional,
        "total_traded_notional": buy_notional + sell_notional,
        "transaction_cost": fee, "cash_after": cash_after,
        "actual_weights": actual_weights.tolist(), "target_weight_sum_error": abs(target_sum - 1.0),
        "funding_error_relative": funding_error, "maximum_target_weight_error": weight_error,
        "relative_tolerance": tolerance, "iterations": iterations,
        "cash_roundoff_guard_steps": guard_steps,
        "cash_residual_retained": True, "self_financing_verified": True,
        "target_weights_verified": True, "corporate_actions_applied_again": False,
        "implementation_sha256": hashlib.sha256(
            inspect.getsource(rebalance_synthetic_portfolio).encode("utf-8")
        ).hexdigest(),
        "versions": {"numpy": np.__version__, "pandas": pd.__version__},
    }