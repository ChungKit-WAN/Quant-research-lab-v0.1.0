"""US equity source snapshots -> raw SQLite -> calculations -> derived SQLite."""

from __future__ import annotations

import argparse
from dataclasses import asdict
from datetime import datetime
import hashlib
import io
from importlib.metadata import version
import json
from pathlib import Path
import platform
import sqlite3
import sys
from zoneinfo import ZoneInfo

try:
    import pandas as pd
    from hkquant.data import fetch_yahoo, load_prices_csv
    from hkquant.database import save_ingestion, read_ingestion, save_calculation, database_status
    from hkquant.factors import compute_factors
    from hkquant.ranking import build_monthly_rankings
    from hkquant.registry import FACTOR_SPECS, IMPLEMENTED_SPECS
    from hkquant.report import write_report
except ImportError as exc:
    raise SystemExit(f"Missing dependency: {exc}\nRun setup.ps1 first.") from exc

ROOT = Path(__file__).resolve().parent


def as_path(value):
    path = Path(value)
    return path.resolve() if path.is_absolute() else (ROOT / path).resolve()


def date_only(value):
    parsed = datetime.strptime(value, "%Y-%m-%d")
    if parsed.strftime("%Y-%m-%d") != value:
        raise ValueError("Dates must use YYYY-MM-DD")
    return pd.Timestamp(parsed)


def code_hash():
    files = [Path(__file__), *sorted((ROOT / "hkquant").glob("*.py")), ROOT / "requirements.txt"]
    digest = hashlib.sha256()
    for path in files:
        digest.update(path.relative_to(ROOT).as_posix().encode())
        digest.update(path.read_bytes())
    return digest.hexdigest()


def ingest(config, args):
    tickers = [item.strip().upper() for item in config["tickers"]]
    today = datetime.now(ZoneInfo("America/New_York")).date().isoformat()
    start, end = args.start or config["start"], args.end or config.get("end") or today
    if date_only(start) >= date_only(end):
        raise ValueError("start must precede end; end is exclusive")
    if args.prices is None and date_only(end) > date_only(today):
        raise ValueError("The download end date cannot be in the future")
    if not tickers or len(set(tickers)) != len(tickers):
        raise ValueError("The configured ticker list must be nonempty and unique")
    payloads = []
    quality_events = []
    metadata = {
        "market": config["market"], "start": start, "end_exclusive": end,
        "universe_label": config["universe_label"], "requested_tickers": tickers,
        "source_layer": "Provider DataFrame snapshot (or original imported CSV bytes), not exchange tick data or raw HTTP packets",
        "quality_events": quality_events,
        "missing_data_policy": config.get("missing_bar_policy", "reject"),
    }

    def capture(ticker, frame):
        payloads.append((ticker, "yfinance_table_csv_utf8", frame.to_csv(index=True).encode("utf-8")))

    raw_path = as_path(config["raw_database"])
    try:
        if args.prices:
            source_file = Path(args.prices).resolve()
            source_bytes = source_file.read_bytes()
            payloads.append((source_file.name, "original_csv_bytes", source_bytes))
            prices = load_prices_csv(io.BytesIO(source_bytes))
            metadata.update(source="User-supplied CSV; provenance not independently verified", input_file=str(source_file))
        else:
            import yfinance as yf
            yf.set_tz_cache_location(str(ROOT / "data" / "provider_cache"))
            print(f"1/4 Downloading public daily prices for {len(tickers)} US stocks...", flush=True)
            prices, provider = fetch_yahoo(tickers, start, end, raw_sink=capture,
                missing_bar_policy=config.get("missing_bar_policy", "reject"), quality_sink=quality_events.append)
            metadata.update(provider)
        # Preserve source payloads exactly; store a validated queryable view too.
        metadata["observed_tickers"] = sorted(prices.ticker.unique().tolist())
        raw_id = save_ingestion(raw_path, prices, payloads, metadata)
    except Exception as exc:
        failed_id = save_ingestion(raw_path, None, payloads, metadata, status="failed", error=str(exc))
        raise RuntimeError(f"Ingestion failed. Attempt and any received source tables retained as {failed_id}: {exc}") from exc
    print(f"2/4 Raw database saved: {raw_id} ({len(prices):,} rows, {len(payloads)} original payloads)", flush=True)
    if quality_events:
        print(f"Data quality: {len(quality_events)} empty price bars preserved and flagged; no replacement prices generated.", flush=True)
    return raw_id


def prepare_calculation_prices(prices, source, start, end):
    """Keep known missing dates inside [start,end), including month boundaries."""
    frame = prices.loc[(prices.date >= start) & (prices.date < end)].copy()
    known_gaps = [{"date": event["date"], "ticker": event["ticker"]}
                  for event in source.get("quality_events", []) if event["issue"] == "empty_price_bar"]
    if known_gaps:
        markers = pd.DataFrame(known_gaps)
        markers["date"] = pd.to_datetime(markers.date)
        markers = markers.loc[(markers.date >= start) & (markers.date < end)]
        frame = pd.concat([frame, markers.reindex(columns=frame.columns)], ignore_index=True)
    return frame.sort_values(["ticker", "date"]).reset_index(drop=True)


def calculate(config, args, raw_id=None):
    raw_path = as_path(config["raw_database"])
    raw_id, prices, source = read_ingestion(raw_path, raw_id or args.raw_run)
    as_of = args.as_of or source.get("end_exclusive")
    if as_of is None:
        raise ValueError("Provide --as-of for a snapshot without an end date")
    cutoff = date_only(as_of)
    requested_end = date_only(source["end_exclusive"])
    if requested_end < cutoff.to_period("M").start_time:
        raise ValueError("Raw snapshot end does not cover all completed months before as_of")
    start = date_only(args.start or source.get("start", config["start"]))
    calculation_prices = prepare_calculation_prices(prices, source, start, min(cutoff, requested_end))
    prices = prices.loc[(prices.date >= start) & (prices.date < min(cutoff, requested_end))].copy()
    if calculation_prices.empty:
        raise ValueError("No usable raw rows remain before the cutoff")
    print(f"3/4 Reading raw database and computing {len(IMPLEMENTED_SPECS)} indicators...", flush=True)
    factors = compute_factors(calculation_prices)
    monthly = build_monthly_rankings(calculation_prices, factors, as_of=as_of,
        weights=config["group_weights"], ranking_window=config["ranking_window"], min_stocks=config["min_stocks"])
    actual_config = dict(config, as_of=as_of, tickers_used=sorted(calculation_prices.ticker.unique().tolist()), calculation_start=str(start.date()), calculation_end_exclusive=str(min(cutoff, requested_end).date()))
    actual_config["runtime_versions"] = {"python": platform.python_version(), "pandas": pd.__version__,
                                         "numpy": version("numpy"), "sqlite": sqlite3.sqlite_version}
    calc_path = as_path(config["calculated_database"])
    calc_id = save_calculation(calc_path, raw_id, raw_path, factors, monthly,
        actual_config, source, code_hash())
    print(f"4/4 Calculated database saved: {calc_id} ({len(factors):,} daily factor rows)", flush=True)
    export(config, args, prices, monthly, source, raw_id, calc_id, actual_config)
    return calc_id


def export(config, args, prices, monthly, source, raw_id, calc_id, actual_config):
    output = as_path(args.output)
    output.mkdir(parents=True, exist_ok=True)
    pd.DataFrame(asdict(s) for s in FACTOR_SPECS).to_csv(output / "factor_registry.csv", index=False, encoding="utf-8-sig")
    monthly.to_csv(output / "monthly_rankings.csv", index=False, date_format="%Y-%m-%d", encoding="utf-8-sig")
    coverage = prices.groupby("ticker").agg(first_date=("date","min"),last_date=("date","max"),observations=("date","size")).reset_index()
    coverage.to_csv(output / "data_coverage.csv", index=False, date_format="%Y-%m-%d", encoding="utf-8-sig")
    limits = [
        "This is a US data-storage and indicator pipeline, not a portfolio return backtest.",
        "The default ten stocks are a selected fixed sample, not the historical S&P 500 or the whole US market; selection and survivorship bias remain.",
        "100 candidates are registered, 65 price/volume indicators computed, 35 financial indicators remain SQL NULL and marked awaiting_pit_fundamentals.",
        "Preserved raw means the provider's returned table or imported CSV bytes. yfinance already processes Yahoo responses; this is not an exchange-original feed.",
        "Yahoo may revise historical prices and adjustment factors. Preserving acquisition snapshots allows revisions to be investigated but does not reconstruct information available before acquisition.",
        "Provider Close may be split-adjusted. close*volume is an approximate turnover proxy, not verified dollar turnover.",
        "Windows count supplied observations; there is no independent US exchange-calendar missing-session audit. Month anchors are last observed dates.",
        "Explicitly quarantined empty source bars are retained as missing factor observations, so rolling windows do not skip across those known gaps. No prices are invented.",
        "Factor directions and group weights are unvalidated research assumptions. No execution, fees, cash, portfolio risk, or return statistics are produced.",
    ]
    latest = monthly.loc[monthly.date.eq(monthly.date.max())].sort_values(["rolling_rank","rank","ticker"],na_position="last") if len(monthly) else monthly.copy()
    latest.to_csv(output / "latest_rankings.csv",index=False,date_format="%Y-%m-%d",encoding="utf-8-sig")
    manifest = {
        "market": config["market"], "stage":"raw_to_calculated_databases",
        "raw_run_id":raw_id,"calculation_id":calc_id,
        "raw_database":str(as_path(config["raw_database"])),
        "calculated_database":str(as_path(config["calculated_database"])),
        "code_sha256":code_hash(),"config":actual_config,"as_of":actual_config["as_of"],
        "source":source,"limitations":limits,"candidate_count":100,"implemented_count":65,
        "awaiting_financial_data":35,"ticker_count":len(actual_config["tickers_used"]),
        "latest_month_anchor":str(monthly.date.max().date()) if len(monthly) else "Unavailable",
        "latest_eligible":int(latest.eligible.sum()) if len(latest) else 0,
        "latest_rolling_eligible":int(latest.rolling_eligible.sum()) if len(latest) else 0,
        "database_status":database_status(as_path(config["raw_database"]),as_path(config["calculated_database"])),
    }
    (output / "manifest.json").write_text(json.dumps(manifest,ensure_ascii=False,indent=2),encoding="utf-8")
    write_report(output / "report.html",latest,coverage,manifest)
    print(f"Report: {output / 'report.html'}")


def parser():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument("command",nargs="?",choices=["run","ingest","calculate","status"],default="run")
    p.add_argument("--config",default=str(ROOT/"config.json"))
    p.add_argument("--prices",help="Archive an original CSV instead of downloading")
    p.add_argument("--raw-run",help="Explicit raw batch for offline recalculation")
    p.add_argument("--start")
    p.add_argument("--end",help="Exclusive source end date")
    p.add_argument("--as-of",help="Only earlier complete calendar months can be ranked")
    p.add_argument("--output",default="outputs/us_latest")
    return p


def main():
    args=parser().parse_args()
    config=json.loads(Path(args.config).read_text(encoding="utf-8-sig"))
    if config.get("market") != "US":
        raise ValueError("This entry point currently uses US market dates; use market=US")
    if as_path(config["raw_database"]) == as_path(config["calculated_database"]):
        raise ValueError("Raw and calculated databases must be separate files")
    if args.command == "status":
        print(json.dumps(database_status(as_path(config["raw_database"]),as_path(config["calculated_database"])),ensure_ascii=False,indent=2))
    elif args.command == "ingest":
        ingest(config,args)
    elif args.command == "calculate":
        calculate(config,args)
    else:
        calculate(config,args,ingest(config,args))


if __name__ == "__main__":
    if hasattr(sys.stdout,"reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    try:
        main()
    except Exception as exc:
        print(f"ERROR: {exc}",file=sys.stderr)
        raise SystemExit(1) from exc
