def simulate_synthetic_wealth_path(
    prices, target_weights, *, initial_cash=1.0, cost_bps=5.0, max_weight=0.25,
):
    """Mark old units first, then rebalance at the close; keep the path continuous."""
    import inspect
    import json
    import hashlib
    import math
    import numbers
    import numpy as np
    import pandas as pd
    from pandas.api.types import is_bool_dtype, is_complex_dtype, is_numeric_dtype
    from .execution import rebalance_synthetic_portfolio

    def require(condition, message):
        if not condition:
            raise ValueError(message)

    def fingerprint(value):
        text = json.dumps(value, ensure_ascii=False, sort_keys=True, allow_nan=False)
        return hashlib.sha256(text.encode("utf-8")).hexdigest()

    def payload(frame):
        return {"dates": frame.index.strftime("%Y-%m-%d").tolist(),
                "columns": frame.columns.tolist(), "values": frame.to_numpy(dtype=float).tolist()}

    for frame in (prices, target_weights):
        require(isinstance(frame, pd.DataFrame) and not frame.empty, "Nonempty DataFrames are required")
        index = frame.index
        require(isinstance(index, pd.DatetimeIndex) and index.tz is None
                and not index.hasnans and index.is_unique and index.is_monotonic_increasing
                and (index == index.normalize()).all(), "Ordered unique daily session dates are required")
        require(frame.columns.is_unique and all(isinstance(c, str) and c and c == c.strip()
                for c in frame.columns), "Invalid asset labels")
        require(all(is_numeric_dtype(d) and not is_bool_dtype(d) and not is_complex_dtype(d)
                    for d in frame.dtypes), "Real numeric inputs are required")
    tickers = prices.columns.tolist()
    require(len(prices) >= 2 and len(tickers) >= 2 and target_weights.columns.tolist() == tickers,
            "Price and target assets must match; include a baseline price row")
    require(target_weights.index[0] == prices.index[1]
            and target_weights.index.isin(prices.index[1:]).all(), "Targets must start at the first execution session")
    for scalar in (initial_cash, cost_bps, max_weight):
        require(isinstance(scalar, numbers.Real) and not isinstance(scalar, (bool, np.bool_))
                and np.isfinite(scalar), "Cash, cost and cap must be finite real numbers")
    require(initial_cash > 0 and 0 <= cost_bps < 10000
            and 1.0 / len(tickers) <= max_weight <= 1.0, "Invalid cash, cost or cap")
    price_values = prices.to_numpy(dtype=float, copy=True)
    targets = target_weights.to_numpy(dtype=float, copy=True)
    require(np.isfinite(price_values).all() and (price_values > 0).all(), "Prices must be positive and finite")
    require(np.isfinite(targets).all() and (targets >= 0).all()
            and (targets <= max_weight + 1e-12).all()
            and (np.abs(targets.sum(axis=1) - 1.0) <= 1e-12).all(), "Invalid target weights")
    target_positions = {date: i for i, date in enumerate(target_weights.index)}
    units = np.zeros(len(tickers))
    cash = float(initial_cash)
    previous_nav = float(initial_cash)
    tolerance = 2e-12
    daily, trades = [], []
    maximum_daily_error = 0.0
    for i in range(1, len(prices)):
        date = prices.index[i]
        day = date.strftime("%Y-%m-%d")
        try:
            old_units, old_cash = units.copy(), cash
            current_prices = price_values[i]
            before_values = old_units * current_prices
            market_pnl = math.fsum((old_units * (current_prices - price_values[i - 1])).tolist())
            before_nav = math.fsum([old_cash, *before_values.tolist()])
            require(np.isfinite(before_nav) and before_nav > 0, "Invalid marked NAV")
            scale = max(previous_nav, before_nav)
            mark_error = abs(math.fsum([previous_nav, market_pnl, -before_nav])) / scale
            require(mark_error <= tolerance, "Old-position mark does not reconcile")
            fee, bought, sold = 0.0, 0.0, 0.0
            trade_number = None
            if date in target_positions:
                result = rebalance_synthetic_portfolio(
                    pd.Series(old_units, index=tickers), pd.Series(current_prices, index=tickers),
                    pd.Series(targets[target_positions[date]], index=tickers),
                    cash=old_cash, cost_bps=cost_bps, max_weight=max_weight,
                )
                require(abs(result["nav_before"] - before_nav) <= tolerance * scale,
                        "Execution input differs from the old-position mark")
                units = np.asarray(result["new_units"], dtype=float)
                cash = result["cash_after"]
                fee, bought, sold = result["transaction_cost"], result["buy_notional"], result["sell_notional"]
                trade_number = len(trades) + 1
                trades.append({"session": day, "trade_number": trade_number, "execution": result})
            else:
                require(np.array_equal(units, old_units) and cash == old_cash,
                        "Units or cash changed without a scheduled trade")
            position_values = units * current_prices
            nav = math.fsum([cash, *position_values.tolist()])
            require(np.isfinite(nav) and nav > 0 and cash >= 0 and (units >= 0).all(), "Invalid closing state")
            error = abs(math.fsum([previous_nav, market_pnl, -fee, -nav])) / scale
            require(error <= tolerance, "Daily profit, fee and NAV do not reconcile")
            net_return = nav / previous_nav - 1.0
            require(np.isfinite(net_return) and net_return > -1.0, "Invalid daily net return")
            weights = position_values / nav
            require(abs(math.fsum([cash / nav, *weights.tolist()]) - 1.0) <= tolerance,
                    "Closing assets and cash do not sum to NAV")
            maximum_daily_error = max(maximum_daily_error, mark_error, error)
            daily.append({
                "session": day, "previous_nav": previous_nav, "nav_before_trade": before_nav,
                "market_pnl_from_old_units": market_pnl, "transaction_cost": fee,
                "buy_notional": bought, "sell_notional": sold, "nav": nav, "net_return": net_return,
                "cash": cash, "units": units.tolist(), "position_values": position_values.tolist(),
                "weights": weights.tolist(), "trade_number": trade_number,
            })
            previous_nav = nav
        except Exception as exc:
            raise ValueError("Wealth ledger failed on " + day + ": " + str(exc)) from exc

    require(len(trades) == len(target_weights), "Some scheduled trades were not executed")
    net_returns = np.asarray([r["net_return"] for r in daily])
    navs = np.asarray([r["nav"] for r in daily])
    require(np.allclose(np.cumprod(1.0 + net_returns), navs / initial_cash, rtol=1e-10, atol=1e-12),
            "Compounded net returns do not reproduce NAV")
    total_fee = math.fsum(r["transaction_cost"] for r in daily)
    total_pnl = math.fsum(r["market_pnl_from_old_units"] for r in daily)
    require(abs(math.fsum([float(initial_cash), total_pnl, -total_fee, -previous_nav]))
            <= 1e-10 * max(initial_cash, previous_nav), "Whole-path accounting does not reconcile")
    rows = {"daily": daily, "trades": trades}
    return {
        "schema_version": "synthetic_wealth_path_v1",
        "accounting": "synthetic_adjusted_price_wealth_not_raw_share_cash_ledger",
        "tickers": tickers, "baseline_session": prices.index[0].strftime("%Y-%m-%d"),
        "initial_cash": float(initial_cash), "cost_bps": float(cost_bps), "max_target_weight": float(max_weight),
        "prices_sha256": fingerprint(payload(prices)), "target_weights_sha256": fingerprint(payload(target_weights)),
        "daily_rows": len(daily), "rebalance_count": len(trades), **rows,
        "ledger_sha256": fingerprint(rows), "total_transaction_cost": total_fee,
        "total_traded_notional": math.fsum(r["buy_notional"] + r["sell_notional"] for r in daily),
        "final_nav": previous_nav, "final_cash": cash, "final_units": units.tolist(),
        "maximum_daily_accounting_error_relative": maximum_daily_error,
        "daily_accounting_verified": True, "net_return_compounding_verified": True,
        "all_scheduled_trades_executed": True, "units_held_between_rebalances": True,
        "target_cap_applies_at_rebalance_only": True, "terminal_forced_liquidation": False,
        "cash_interest_applied": False, "corporate_actions_applied_again": False,
        "performance_statistics_computed": False,
        "execution_implementation_sha256": trades[0]["execution"]["implementation_sha256"],
        "implementation_sha256": hashlib.sha256(inspect.getsource(simulate_synthetic_wealth_path).encode("utf-8")).hexdigest(),
        "versions": {"numpy": np.__version__, "pandas": pd.__version__},
    }