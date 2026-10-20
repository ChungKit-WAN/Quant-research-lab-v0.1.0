def calculate_period_performance(daily_records, *, tickers, annualization_sessions=252):
    """Summarize a contiguous net-of-cost ledger slice; never reset its capital."""
    import hashlib
    import inspect
    import json
    import math
    import numbers
    from datetime import date
    from decimal import Decimal
    import numpy as np

    def require(condition, message):
        if not condition:
            raise ValueError(message)

    def fingerprint(value):
        text = json.dumps(value, ensure_ascii=False, sort_keys=True, allow_nan=False)
        return hashlib.sha256(text.encode("utf-8")).hexdigest()

    def real(value):
        require(isinstance(value, numbers.Real) and not isinstance(value, (bool, np.bool_))
                and math.isfinite(value), "Ledger values must be finite real numbers")
        return float(value)

    require(isinstance(annualization_sessions, numbers.Integral)
            and not isinstance(annualization_sessions, (bool, np.bool_))
            and annualization_sessions > 0, "Annualization sessions must be a positive integer")
    require(isinstance(tickers, (list, tuple)) and len(tickers) > 0
            and all(isinstance(t, str) and t and t == t.strip() for t in tickers)
            and len(set(tickers)) == len(tickers), "Unique nonempty ticker labels are required")
    require(isinstance(daily_records, (list, tuple)) and len(daily_records) >= 2,
            "At least two consecutive daily ledger records are required")
    fields = ("previous_nav", "nav", "net_return", "market_pnl_from_old_units",
              "transaction_cost", "buy_notional", "sell_notional", "cash")
    rows, last_date, last_nav = [], None, None
    tolerance = 2e-12
    for source in daily_records:
        require(isinstance(source, dict) and all(k in source for k in
                (*fields, "session", "weights", "trade_number")), "Incomplete ledger record")
        session = source["session"]
        require(isinstance(session, str) and date.fromisoformat(session).isoformat() == session,
                "Session must be an ISO date")
        require(last_date is None or session > last_date, "Sessions must be ordered and unique")
        row = {k: real(source[k]) for k in fields}
        previous, nav, ret = row["previous_nav"], row["nav"], row["net_return"]
        require(previous > 0 and nav > 0 and ret > -1, "Invalid NAV or net return")
        require(last_nav is None or previous == last_nav, "NAV chain is broken between records")
        require(all(row[k] >= 0 for k in ("transaction_cost", "buy_notional", "sell_notional", "cash")),
                "Cash, fees and trade notionals must be nonnegative")
        require(abs(ret - (nav / previous - 1)) <= tolerance, "Return differs from NAV ratio")
        require(abs(math.fsum([previous, row["market_pnl_from_old_units"],
                              -row["transaction_cost"], -nav]))
                <= tolerance * max(previous, nav), "P&L, transaction cost and NAV do not reconcile")
        raw_weights = source["weights"]
        require(isinstance(raw_weights, (list, tuple)) and len(raw_weights) == len(tickers),
                "Weight labels and values differ")
        weights = [real(v) for v in raw_weights]
        require(all(w >= 0 for w in weights)
                and abs(math.fsum([*weights, row["cash"] / nav]) - 1) <= tolerance,
                "Closing weights and cash do not sum to one")
        trade = source["trade_number"]
        require(trade is None or (isinstance(trade, numbers.Integral)
                and not isinstance(trade, (bool, np.bool_)) and trade > 0), "Invalid trade number")
        require(trade is not None or all(row[k] == 0 for k in
                ("transaction_cost", "buy_notional", "sell_notional")), "Unscheduled trading amounts")
        row.update(session=session, weights=weights, trade_number=None if trade is None else int(trade))
        rows.append(row)
        last_date, last_nav = session, nav

    n = len(rows)
    opening, closing = rows[0]["previous_nav"], rows[-1]["nav"]
    returns = np.asarray([r["net_return"] for r in rows], dtype=float)
    navs = np.asarray([opening, *[r["nav"] for r in rows]], dtype=float)
    log_growth = math.log(closing) - math.log(opening)
    require(abs(math.fsum(math.log1p(r) for r in returns) - log_growth) <= 1e-10,
            "Compounded returns differ from NAV growth")
    annualized_volatility = float(np.std(returns, ddof=1) * math.sqrt(annualization_sessions))
    net_cagr = math.expm1(log_growth * annualization_sessions / n)
    maximum_drawdown = float(np.max(1 - navs / np.maximum.accumulate(navs)))
    losses = sorted((-float(r) for r in returns), reverse=True)
    mass = Decimal(n) * Decimal("0.05")
    whole = int(mass)
    fraction = float(mass - whole)
    tail_sum = math.fsum([*losses[:whole], fraction * losses[whole]])
    cvar = tail_sum / float(mass)
    bought = math.fsum(r["buy_notional"] for r in rows)
    sold = math.fsum(r["sell_notional"] for r in rows)
    fees = math.fsum(r["transaction_cost"] for r in rows)
    traded = math.fsum([bought, sold])
    weights = np.asarray([r["weights"] for r in rows], dtype=float)
    sector_weights = {
        t: {"first_close": float(weights[0, j]), "last_close": float(weights[-1, j]),
            "mean_close": float(np.mean(weights[:, j])), "minimum_close": float(np.min(weights[:, j])),
            "maximum_close": float(np.max(weights[:, j]))}
        for j, t in enumerate(tickers)
    }
    result = {
        "schema_version": "net_ledger_period_performance_v1",
        "first_session": rows[0]["session"], "last_session": rows[-1]["session"], "observations": n,
        "opening_nav": opening, "closing_nav": closing, "net_total_return": math.expm1(log_growth),
        "annualized_volatility": annualized_volatility, "net_cagr": net_cagr,
        "maximum_drawdown": maximum_drawdown, "daily_loss_cvar_95": cvar,
        "tail_observation_mass": float(mass), "buy_notional": bought, "sell_notional": sold,
        "traded_notional": traded, "transaction_costs": fees,
        "traded_notional_over_opening_nav": traded / opening,
        "transaction_costs_over_opening_nav": fees / opening,
        "rebalance_count": sum(r["trade_number"] is not None for r in rows),
        "sector_weights": sector_weights,
        "conventions": {
            "annualization_sessions": int(annualization_sessions), "volatility_ddof": 1,
            "cagr": "trading_session_annualized_net_growth_not_calendar_year_cagr",
            "opening_nav": "previous_nav_of_first_selected_day",
            "drawdown": "positive_magnitude_within_period_including_opening_nav",
            "cvar": "mean_of_exact_worst_5_percent_mass_of_daily_negative_net_returns",
            "cvar_negative_values": "retained_not_clipped",
            "traded_notional": "buy_plus_sell_not_halved_not_annualized",
            "money_units": "same_as_source_ledger_initial_capital_not_dollar_claim",
            "sector_weights": "actual_post_trade_close_weights_equal_weighted_over_sessions",
            "target_cap": "only_at_rebalance_daily_weights_may_drift_above_cap",
        },
        "input_sha256": fingerprint({"tickers": list(tickers), "daily": rows}),
        "ledger_consistency_verified": True,
        "implementation_sha256": hashlib.sha256(
            inspect.getsource(calculate_period_performance).encode("utf-8")).hexdigest(),
        "versions": {"numpy": np.__version__},
    }
    fingerprint(result)
    return result