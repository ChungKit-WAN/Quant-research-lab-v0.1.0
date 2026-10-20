"""Run the first real stage of the HK multi-factor project.

Prices -> 65 available indicators -> grouped monthly scores -> trailing ranks.
This stage deliberately makes no portfolio performance or return claims.
"""

from __future__ import annotations

import argparse
from collections import Counter
from dataclasses import asdict
from datetime import datetime, timedelta, timezone
import hashlib
import json
from pathlib import Path
import sys

try:
    import pandas as pd
    from hkquant import __version__
    from hkquant.data import fetch_yahoo, load_prices_csv
    from hkquant.factors import compute_factors
    from hkquant.ranking import build_monthly_rankings
    from hkquant.registry import FACTOR_SPECS, IMPLEMENTED_SPECS
    from hkquant.report import write_report
except ImportError as exc:
    raise SystemExit(
        f"Missing dependency: {exc}\nRun setup.ps1, then use .venv/Scripts/python.exe main.py"
    ) from exc

ROOT = Path(__file__).resolve().parent


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def save_json(path: Path, value) -> None:
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def parse_date(value: str) -> pd.Timestamp:
    parsed = datetime.strptime(value, "%Y-%m-%d")
    if parsed.strftime("%Y-%m-%d") != value:
        raise ValueError(f"Use YYYY-MM-DD for dates: {value}")
    return pd.Timestamp(parsed)


def obtain_prices(config, start, end, local_csv, refresh):
    if local_csv is not None:
        path = Path(local_csv).resolve()
        return load_prices_csv(path), {
            "source": "User-supplied CSV (source and point-in-time status not independently verified)",
            "input_file": str(path), "input_sha256": digest(path),
            "universe_warning": "Providing historical data does not establish historical index membership.",
        }
    tickers = [ticker.strip().upper() for ticker in config["tickers"]]
    key = hashlib.sha256(json.dumps([tickers, start, end]).encode()).hexdigest()[:20]
    folder = ROOT / "data" / "cache"
    folder.mkdir(parents=True, exist_ok=True)
    csv_path, meta_path = folder / f"{key}.csv", folder / f"{key}.json"
    if csv_path.exists() and meta_path.exists() and not refresh:
        metadata = json.loads(meta_path.read_text(encoding="utf-8"))
        if metadata.get("csv_sha256") != digest(csv_path):
            raise ValueError("Cached prices failed the SHA-256 check. Run with --refresh.")
        print("Reading saved public prices...", flush=True)
        prices = load_prices_csv(csv_path)
        if set(prices.ticker.unique()) != set(tickers):
            raise ValueError("Cached ticker coverage differs from config. Run with --refresh.")
        metadata["cache_reused"] = True
        return prices, metadata
    print(f"Downloading real daily data for {len(tickers)} HK symbols...", flush=True)
    prices, metadata = fetch_yahoo(tickers, start, end)
    prices.to_csv(csv_path, index=False, date_format="%Y-%m-%d", encoding="utf-8-sig")
    metadata["csv_sha256"] = digest(csv_path)
    metadata["cache_reused"] = False
    save_json(meta_path, metadata)
    return prices, metadata


def run(args) -> Path:
    config_path = Path(args.config).resolve()
    config = json.loads(config_path.read_text(encoding="utf-8-sig"))
    output = Path(args.output).resolve()
    output.mkdir(parents=True, exist_ok=True)
    registry = pd.DataFrame(asdict(spec) for spec in FACTOR_SPECS)
    registry.to_csv(output / "factor_registry.csv", index=False, encoding="utf-8-sig")
    if args.catalog_only:
        print(f"100 candidate indicators: {output / 'factor_registry.csv'}")
        return output

    today_hk = datetime.now(timezone(timedelta(hours=8))).date().isoformat()
    start = args.start or config["start"]
    end = args.end or config.get("end") or today_hk
    as_of = args.as_of or end
    if parse_date(start) >= parse_date(end):
        raise ValueError("start must be earlier than end; end is exclusive.")
    parse_date(as_of)
    if parse_date(end) < parse_date(as_of).to_period("M").start_time:
        raise ValueError("end must cover all completed months preceding as_of.")
    if args.prices is None and parse_date(end) > parse_date(today_hk):
        raise ValueError("A public download end date cannot be in the future.")
    prices, source = obtain_prices(config, start, end, args.prices, args.refresh)
    # Apply the same explicit data cutoff to CSV and downloaded inputs.
    cutoff = min(parse_date(end), parse_date(as_of))
    prices = prices.loc[(prices.date >= parse_date(start)) & (prices.date < cutoff)].copy()
    if prices.empty:
        raise ValueError("No price rows remain inside the requested dates.")
    universe = None
    if args.universe:
        universe_path = Path(args.universe).resolve()
        universe = pd.read_csv(universe_path, dtype={"ticker": "string"})
        source["membership_file"] = str(universe_path)
        source["membership_sha256"] = digest(universe_path)
    print(f"Computing 65 available indicators over {len(prices):,} price rows...", flush=True)
    factors = compute_factors(prices)
    monthly = build_monthly_rankings(
        prices, factors, as_of=as_of, weights=config["group_weights"],
        ranking_window=config["ranking_window"], min_stocks=config["min_stocks"],
        universe=universe,
    )
    if monthly.empty:
        raise ValueError("No completed calendar month is available before as_of.")
    latest_date = monthly.date.max()
    latest = monthly.loc[monthly.date.eq(latest_date)].sort_values(
        ["rolling_rank", "rank", "ticker"], na_position="last"
    ).reset_index(drop=True)
    latest_factors = latest[["date", "ticker"]].merge(factors, on=["date", "ticker"], how="left")
    snapshots = {
        "prices_used.csv": prices,
        "monthly_rankings.csv": monthly,
        "latest_rankings.csv": latest,
        "latest_factors.csv": latest_factors,
    }
    if args.save_daily:
        snapshots["daily_factors.csv"] = factors
    for filename, frame in snapshots.items():
        frame.to_csv(output / filename, index=False, date_format="%Y-%m-%d", encoding="utf-8-sig")
    data_coverage = prices.groupby("ticker").agg(
        first_date=("date", "min"), last_date=("date", "max"), observations=("date", "size"),
        zero_volume_days=("volume", lambda values: int(values.eq(0).sum()))
    ).reset_index()
    data_coverage.to_csv(output / "data_coverage.csv", index=False, date_format="%Y-%m-%d", encoding="utf-8-sig")
    incomplete = latest_factors[[s.id for s in IMPLEMENTED_SPECS]].notna().sum().to_dict()
    limits = [
        "This release produces research rankings, not a backtest, portfolio, or trading recommendation.",
        "100 candidates are registered; only 65 price/volume indicators are implemented. 35 financial indicators await historical point-in-time data.",
        "Default tickers are a fixed selected sample, not historical Hang Seng Composite constituents; selection and survivorship bias are unresolved.",
        "Group weights and indicator directions are initial research assumptions, not fitted or validated optimal parameters.",
        "Yahoo adjustments may be revised; total returns and corporate actions are not independently reconciled. close*volume is only a turnover proxy.",
        "Windows count supplied daily observations. An independent HK trading calendar and market-wide missing-session audit are not implemented.",
        "The current as_of month is excluded. Missing anchor quotes and missing consecutive months cannot reuse stale scores.",
        "Trading costs, lot sizes, suspensions at execution, cash, and actual execution are not modeled in this stage.",
    ]
    if universe is not None:
        limits.append("Membership intervals are supplied by the user and applied as [effective_from, effective_to); their provenance has not been verified.")
    manifest = {
        "project_version": __version__,
        "created_at_utc": datetime.now(timezone.utc).isoformat(),
        "stage": "research_rankings_only",
        "candidate_count": len(FACTOR_SPECS), "implemented_count": len(IMPLEMENTED_SPECS),
        "awaiting_financial_data": len(FACTOR_SPECS) - len(IMPLEMENTED_SPECS),
        "counts_by_group": dict(Counter(spec.group for spec in FACTOR_SPECS)),
        "config": config, "requested_start": start, "requested_end_exclusive": end,
        "as_of": as_of, "latest_month_anchor": str(latest_date.date()),
        "price_rows": len(prices), "ticker_count": int(prices.ticker.nunique()),
        "latest_eligible": int(latest.eligible.sum()),
        "latest_rolling_eligible": int(latest.rolling_eligible.sum()),
        "latest_reason_counts": latest.reason.value_counts().to_dict(),
        "latest_finite_count_by_factor": {key: int(value) for key, value in incomplete.items()},
        "source": source, "limitations": limits,
        "sha256": {filename: digest(output / filename) for filename in snapshots},
    }
    save_json(output / "manifest.json", manifest)
    write_report(output / "report.html", latest, data_coverage, manifest)
    print(f"Complete. Month: {latest_date:%Y-%m}; current ranks: {manifest['latest_eligible']}; "
          f"{config['ranking_window']}-month ranks: {manifest['latest_rolling_eligible']}")
    print(f"Report: {output / 'report.html'}")
    print("Status: 65 computed / 35 awaiting financial data; no strategy returns claimed.")
    return output


def parser():
    result = argparse.ArgumentParser(description=__doc__)
    result.add_argument("--config", default=str(ROOT / "configs" / "hk_example.json"))
    result.add_argument("--prices", help="Use your own canonical daily CSV instead of downloading")
    result.add_argument("--universe", help="Optional historical membership CSV")
    result.add_argument("--start", help="First data date, inclusive, YYYY-MM-DD")
    result.add_argument("--end", help="Data end, exclusive, YYYY-MM-DD")
    result.add_argument("--as-of", help="Research cutoff; only earlier calendar months are ranked")
    result.add_argument("--output", default=str(ROOT / "outputs" / "public_sample"))
    result.add_argument("--refresh", action="store_true", help="Refresh downloaded price cache")
    result.add_argument("--save-daily", action="store_true", help="Also write all daily factor values")
    result.add_argument("--catalog-only", action="store_true", help="Export the 100-item catalogue without a download")
    return result


if __name__ == "__main__":
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    try:
        run(parser().parse_args())
    except (ValueError, RuntimeError, OSError, KeyError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        raise SystemExit(1) from exc
