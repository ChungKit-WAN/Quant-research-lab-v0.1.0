"""One command interface for monthly ETF allocation and equity factor research."""

import argparse
import io
import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd

from hkquant.data import load_prices_csv
from sector_backtest.pipeline import MonthlyConfig, demo_prices, run_monthly
from . import __version__
from .report import export_report, sha256

STOCKS = ("AAPL", "MSFT", "GOOGL", "AMZN", "NVDA", "META", "JPM", "JNJ", "XOM", "PG")


def wide_from_long(frame):
    required = {"date", "ticker", "adj_close"}
    if not required.issubset(frame):
        raise ValueError("ETF CSV requires date,ticker,adj_close columns")
    frame = frame.loc[:, ["date", "ticker", "adj_close"]].copy()
    if frame["ticker"].isna().any() or not frame["ticker"].map(
        lambda value: isinstance(value, str) and bool(value) and value == value.strip()
    ).all():
        raise ValueError("ticker must contain nonempty trimmed strings")
    frame["date"] = pd.to_datetime(frame["date"], errors="raise")
    if frame.duplicated(["date", "ticker"]).any():
        raise ValueError("Duplicate date/ticker rows")
    frame["adj_close"] = pd.to_numeric(frame["adj_close"], errors="raise")
    return frame.pivot(index="date", columns="ticker", values="adj_close").sort_index()


def synthetic_long(config, family):
    wide = demo_prices(config)
    long = wide.rename_axis("date").reset_index().melt(id_vars="date", var_name="ticker", value_name="adj_close")
    if family == "stocks":
        rng = np.random.default_rng(1019)
        long["close"] = long["adj_close"]
        long["open"] = long["close"] * (1 + rng.normal(0, .002, len(long)))
        long["high"] = long[["open", "close"]].max(axis=1) * 1.005
        long["low"] = long[["open", "close"]].min(axis=1) * .995
        long["volume"] = rng.integers(500000, 5000000, len(long))
    return long.sort_values(["date", "ticker"]).reset_index(drop=True)


def parser():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--version", action="version", version=__version__)
    commands = p.add_subparsers(dest="command", required=True)
    for command in ("demo", "run"):
        sub = commands.add_parser(command, help="Synthetic offline demonstration" if command == "demo" else "Run on a supplied CSV")
        sub.add_argument("--family", choices=("etf", "stocks"), default="etf")
        sub.add_argument("--config", type=Path, help="MonthlyConfig JSON; see configs/")
        sub.add_argument("--output", type=Path, required=True, help="New or empty output directory")
        sub.add_argument("--top-n", type=int, default=4, help="Number of stocks selected (stocks only)")
        sub.add_argument("--ranking-window", type=int, default=3, help="Consecutive monthly ranks to average (stocks only)")
        if command == "run":
            sub.add_argument("--prices", type=Path, required=True)
    return p


def main(argv=None):
    args = parser().parse_args(argv)
    try:
        if args.output.exists() and (not args.output.is_dir() or any(args.output.iterdir())):
            raise ValueError("Output must be new or empty; choose another --output to preserve earlier runs")
        config = MonthlyConfig(**json.loads(args.config.read_text(encoding="utf-8-sig"))) if args.config else (
            MonthlyConfig(tickers=STOCKS) if args.family == "stocks" else MonthlyConfig())
        demo_csv = None
        if args.command == "demo":
            long = synthetic_long(config, args.family)
            demo_csv = long.to_csv(index=False, date_format="%Y-%m-%d", lineterminator="\n").encode("utf-8")
            raw = demo_csv
            # Parse the same serialized bytes supplied to CSV users. The demo
            # and a subsequent run on demo_prices.csv share numerical inputs.
            long = pd.read_csv(io.BytesIO(raw), dtype={"ticker": str}, float_precision="round_trip")
            data_kind = "synthetic_demo"
            source = "Deterministic synthetic fixture (seed 20261019; OHLCV seed 1019)"
        else:
            raw = args.prices.read_bytes()
            long = pd.read_csv(io.BytesIO(raw), dtype={"ticker": str}, float_precision="round_trip")
            data_kind = "user_supplied_adjusted_prices"
            source = args.prices.name
        if args.family == "stocks":
            from .stock import run_factor_monthly
            result = run_factor_monthly(long, config, top_n=args.top_n, ranking_window=args.ranking_window)
        else:
            result = run_monthly(wide_from_long(long), config)
        report = export_report(result, args.output, data_kind=data_kind,
                               input_sha256=sha256(raw), source_label=source, demo_csv=demo_csv)
        print(f"v{__version__} | {args.family} | {data_kind}")
        print(f"Report: {report.resolve()}")
        print(f"Strategies: {', '.join(result['strategies'])}; monthly events: {len(result['schedule'])}")
        return 0
    except (ValueError, TypeError, KeyError, OSError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
