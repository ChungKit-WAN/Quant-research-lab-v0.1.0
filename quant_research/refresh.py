"""Current-date, auditable download -> monthly research -> portable reports."""

from dataclasses import asdict
from datetime import datetime, timezone
import html
import io
import json
from pathlib import Path
import re
import uuid
import webbrowser
from zoneinfo import ZoneInfo

import exchange_calendars as xcals
import numpy as np
import pandas as pd

from hkquant.data import fetch_yahoo, load_prices_csv
from hkquant.database import read_ingestion, save_calculation, save_ingestion
from hkquant.factors import compute_factors
from hkquant.ranking import build_monthly_rankings
from hkquant.registry import FACTOR_SPECS
from sector_backtest.pipeline import MonthlyConfig, TICKERS, run_monthly, sessions
from . import __version__
from .report import export_report, sha256
from .stock import run_factor_monthly

ROOT = Path(__file__).resolve().parents[1]


def default_config():
    source_config = ROOT / "configs" / "refresh.json"
    return source_config if source_config.is_file() else Path(__file__).with_name("default_refresh.json")


def default_workspace():
    return ROOT if (ROOT / "configs" / "refresh.json").is_file() else Path.cwd()


def save_json(path, value):
    Path(path).write_text(json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False), encoding="utf-8")


def resolve_dates(settings, *, as_of=None, now=None):
    """Automatic cutoff uses completed NY sessions plus a two-hour vendor buffer.

    Explicit --as-of is the start of that New York calendar date (exclusive).
    Signals always exclude the as-of month; reporting time is Asia/Shanghai.
    """
    now = pd.Timestamp(now if now is not None else datetime.now(timezone.utc))
    if now.tzinfo is None:
        raise ValueError("now must include a timezone")
    local_today = now.tz_convert("Asia/Shanghai").date()
    if as_of:
        if not re.fullmatch(r"\d{4}-\d{2}-\d{2}", as_of):
            raise ValueError("--as-of must use YYYY-MM-DD")
        cutoff = pd.Timestamp(as_of)
        if cutoff.date() > local_today:
            raise ValueError("--as-of cannot be in the future")
        instant = min(cutoff.tz_localize("America/New_York"), now)
    else:
        cutoff = pd.Timestamp(local_today)
        instant = now
    calendar = xcals.get_calendar("XNYS", start=cutoff-pd.Timedelta(days=20), end=cutoff+pd.Timedelta(days=1))
    available = calendar.schedule.loc[calendar.schedule["close"] + pd.Timedelta(hours=2) <= instant]
    if available.empty:
        raise ValueError("No completed session available before cutoff")
    last = available.index[-1].tz_localize(None)
    last_month = last.to_period("M")
    true_month_end = sessions(last_month.start_time, last_month.end_time.normalize())[-1]
    ranking_cutoff = (last_month + 1).start_time if last == true_month_end else last_month.start_time
    month = cutoff.to_period("M").start_time
    research = month - pd.DateOffset(years=settings["backtest_years"])
    holdout = month - pd.DateOffset(months=settings["holdout_months"])
    if holdout <= research:
        raise ValueError("Holdout must be shorter than the research period")
    return {"as_of": str(cutoff.date()), "ranking_as_of": str(ranking_cutoff.date()), "last_complete_session": str(last.date()),
            "download_start": str((research-pd.DateOffset(years=settings["warmup_years"])).date()),
            "download_end_exclusive": str((last+pd.Timedelta(days=1)).date()),
            "research_start": str(research.date()), "holdout_start": str(holdout.date()),
            "clock_timezone": "Asia/Shanghai", "exchange_timezone": "America/New_York",
            "date_policy": "Completed XNYS close plus 2h; monthly signals exclude current calendar month",
            "resolved_at_utc": now.tz_convert("UTC").isoformat()}


def load_settings(path):
    settings = json.loads(Path(path).read_text(encoding="utf-8-sig"))
    for field in ("backtest_years", "warmup_years", "holdout_months", "lookback", "top_n", "ranking_window"):
        value = settings[field]
        if isinstance(value, bool) or not isinstance(value, int) or value < 1:
            raise ValueError(f"{field} must be a positive integer")
    sectors = settings["sectors"]
    if len(sectors) != 11 or {s["id"] for s in sectors} != set(TICKERS):
        raise ValueError("Configure exactly the eleven sector ETF identifiers")
    stocks = []
    for sector in sectors:
        if not sector["stocks"]:
            raise ValueError("Every sector needs at least one stock")
        for stock in sector["stocks"]:
            ticker = stock["ticker"]
            if not isinstance(ticker, str) or not re.fullmatch(r"[A-Z][A-Z0-9.^=-]{0,14}", ticker):
                raise ValueError(f"Invalid ticker: {ticker}")
            stocks.append(ticker)
    if len(stocks) != len(set(stocks)) or set(stocks) & set(TICKERS):
        raise ValueError("Stock symbols must be unique and separate from ETFs")
    return settings, stocks


def audit_prices(prices, tickers, dates):
    expected = sessions(dates["download_start"], dates["last_complete_session"])
    rows = []
    for ticker in tickers:
        frame = prices.loc[prices.ticker.eq(ticker)].sort_values("date")
        actual = pd.DatetimeIndex(frame.date)
        missing, extra = expected.difference(actual), actual.difference(expected)
        ratio = frame.adj_close / frame.close
        rows.append({"ticker": ticker, "observations": len(frame),
                     "first_date": str(actual.min().date()) if len(actual) else None,
                     "last_date": str(actual.max().date()) if len(actual) else None,
                     "expected_sessions": len(expected), "missing_sessions": len(missing),
                     "extra_sessions": len(extra), "missing_dates": ";".join(missing.strftime("%Y-%m-%d")),
                     "zero_volume_days": int(frame.volume.eq(0).sum()),
                     "min_adjustment_ratio": float(ratio.min()) if len(frame) else None,
                     "max_adjustment_ratio": float(ratio.max()) if len(frame) else None,
                     "status": "passed" if len(actual) and not len(missing) and not len(extra) else "failed"})
    return pd.DataFrame(rows)


def synthetic_prices(tickers, dates):
    """Explicit offline fixture, never substituted for failed live downloads."""
    calendar = sessions(dates["download_start"], dates["last_complete_session"])
    rng = np.random.default_rng(110)
    market = rng.normal(.00015, .006, len(calendar))
    frames = []
    for ticker in tickers:
        close = 100 * np.exp(np.cumsum(market + rng.normal(0, .009, len(calendar))))
        opening = close * (1+rng.normal(0,.002,len(calendar)))
        frames.append(pd.DataFrame({"date": calendar, "ticker": ticker, "open": opening,
            "high": np.maximum(opening,close)*1.005, "low": np.minimum(opening,close)*.995,
            "close":close,"adj_close":close,"volume":rng.integers(500000,5000000,len(calendar))}))
    return pd.concat(frames, ignore_index=True)


def refresh(args):
    settings, stocks = load_settings(args.config or default_config())
    dates = resolve_dates(settings, as_of=args.as_of)
    run_id = datetime.now(ZoneInfo("Asia/Shanghai")).strftime("%Y%m%d-%H%M%S") + "-" + uuid.uuid4().hex[:8]
    workspace = default_workspace()
    root = Path(args.output or workspace / "outputs" / "v011").resolve()
    output = root / "runs" / run_id
    output.mkdir(parents=True, exist_ok=False)
    database_root = Path(args.data_dir or workspace / "data" / "v011").resolve()
    raw_db, calc_db = database_root / "raw_market.sqlite", database_root / "calculated_market.sqlite"
    tickers = [*stocks, *TICKERS]
    kind = "synthetic_demo" if args.demo else ("user_supplied_adjusted_prices" if args.prices else "public_market_data")
    manifest = {"version":__version__,"run_id":run_id,"status":"running","data_kind":kind,
                "created_at_utc":datetime.now(timezone.utc).isoformat(), **dates,"config":settings,
                "candidate_count":100,"implemented_count":65,"awaiting_financial_data":35,
                "ticker_count":len(stocks),"point_in_time_universe":False,
                "independent_data_verification":"not_performed",
                "holdout_status":"chronological partition, not certified unseen",
                "limitations":["Fixed selected sample and manual sector grouping; selection and survivorship biases remain.",
                    "35 financial indicators await point-in-time fundamentals; no fabricated values or rankings.",
                    "Yahoo adjusted data may be revised; sampled rows and calendar checks are not independent price certification.",
                    "No annual-report/SEC filing download is implied; this workflow downloads prices and generates research reports."]}
    payloads = []
    source = {"source":kind, **dates, "requested_tickers":tickers}
    save_json(output / "manifest.json", manifest)
    try:
        print(f"v{__version__} | as-of {dates['as_of']} | latest completed session {dates['last_complete_session']}", flush=True)
        print(f"[1/6] Obtaining {len(stocks)} stocks and 11 sector ETFs...", flush=True)
        try:
            if args.demo:
                prices = synthetic_prices(tickers, dates)
                payloads.append(("synthetic", "synthetic_csv_utf8", prices.to_csv(index=False).encode()))
            elif args.prices:
                raw = Path(args.prices).read_bytes()
                payloads.append((Path(args.prices).name, "original_csv_bytes", raw))
                prices = load_prices_csv(io.BytesIO(raw))
            else:
                import yfinance as yf
                yf.set_tz_cache_location(str(database_root / "provider_cache"))
                source.update(source="Yahoo Finance via yfinance", yfinance_version=yf.__version__,
                              auto_adjust=False, actions=False, quality_events=[])
                def capture(ticker, frame):
                    payloads.append((ticker,"yfinance_table_csv_utf8",frame.to_csv(index=True).encode()))
                    print(f"  received {ticker} ({len(payloads)}/{len(tickers)})", flush=True)
                prices, provider = fetch_yahoo(tickers, dates["download_start"], dates["download_end_exclusive"], raw_sink=capture,
                                               missing_bar_policy="quarantine_empty", quality_sink=source["quality_events"].append)
                source.update(provider)
            if set(prices.ticker) != set(tickers):
                raise ValueError("Input ticker coverage must exactly match the configured stocks and eleven ETFs")
            prices = prices.loc[(prices.date >= pd.Timestamp(dates["download_start"])) &
                                (prices.date < pd.Timestamp(dates["download_end_exclusive"]))].copy()
            raw_id = save_ingestion(raw_db, prices, payloads, source)
        except Exception as exc:
            manifest["failed_raw_run_id"] = save_ingestion(raw_db, None, payloads, source, status="failed", error=str(exc))
            raise
        raw_id, prices, source = read_ingestion(raw_db, raw_id)
        manifest.update(raw_run_id=raw_id, source=source)
        print("[2/6] Checking all expected exchange sessions and archiving price samples...", flush=True)
        audit = audit_prices(prices, tickers, dates)
        audit.to_csv(output / "data_coverage.csv",index=False,encoding="utf-8-sig")
        prices.to_csv(output / "prices_used.csv",index=False,date_format="%Y-%m-%d")
        sample = pd.concat([group.iloc[sorted({0,len(group)//2,len(group)-1})]
                            for _, group in prices.groupby("ticker",sort=True)],ignore_index=True)
        sample.to_csv(output / "price_samples.csv",index=False)
        if not audit.status.eq("passed").all():
            raise ValueError("Incomplete exchange-session coverage: " + ", ".join(audit.loc[audit.status.ne("passed"),"ticker"]) + ". See data_coverage.csv; missing data was not filled.")
        digest = sha256((output / "prices_used.csv").read_bytes())
        stock_prices = prices.loc[prices.ticker.isin(stocks)].copy()
        print("[3/6] Computing factors and completed-month rankings...", flush=True)
        factors = compute_factors(stock_prices)
        monthly = build_monthly_rankings(stock_prices, factors, as_of=dates["ranking_as_of"],weights=settings["group_weights"],
                                         ranking_window=settings["ranking_window"],min_stocks=max(2,settings["top_n"]))
        latest = monthly.loc[monthly.date.eq(monthly.date.max())].copy()
        last_factors = latest[["date","ticker"]].merge(factors,on=["date","ticker"],how="left")
        code_hashes = {str(p.relative_to(ROOT)):sha256(p.read_bytes()) for folder in ("quant_research","hkquant","sector_backtest") for p in sorted((ROOT/folder).glob("*.py"))}
        calc_id = save_calculation(calc_db,raw_id,raw_db,factors,monthly,{**settings,**dates},source,sha256(json.dumps(code_hashes,sort_keys=True).encode()))
        manifest.update(calculation_id=calc_id,code_sha256=code_hashes,input_sha256=digest,
                        latest_month_anchor=str(latest.date.max().date()),latest_eligible=int(latest.eligible.sum()),
                        latest_rolling_eligible=int(latest.rolling_eligible.sum()))
        monthly.to_csv(output/"monthly_rankings.csv",index=False)
        latest.to_csv(output/"latest_rankings.csv",index=False)
        pd.DataFrame(asdict(s) for s in FACTOR_SPECS).to_csv(output/"factor_registry.csv",index=False,encoding="utf-8-sig")
        common = {key:settings[key] for key in ("lookback","cost_bps","max_weight")}
        common.update(research_start=dates["research_start"],holdout_start=dates["holdout_start"])
        stock_config = MonthlyConfig(tickers=tuple(stocks),**common)
        print("[4/6] Running monthly ETF and stock portfolio ledgers...", flush=True)
        etfs = prices.loc[prices.ticker.isin(TICKERS)].pivot(index="date",columns="ticker",values="adj_close")
        portfolio_results = {
            "etf": run_monthly(etfs,MonthlyConfig(**common)),
            "stocks": run_factor_monthly(stock_prices,stock_config,settings["top_n"],settings["ranking_window"],settings["group_weights"]),
        }
        print("[5/6] Running the predefined research validation experiments...",flush=True)
        from .validation import run_validation
        validation = run_validation(stock_prices,stock_config,output/"validation",top_n=settings["top_n"],ranking_window=settings["ranking_window"],
                                    group_weights=settings["group_weights"],data_kind=kind,source_label=source["source"],input_sha256=digest)
        manifest["validation_summary"] = {key:value for key,value in validation.items() if key in ("status","completed_experiments","failed_experiments")}
        print("[6/6] Building the 11 sector pages and bilingual reports...",flush=True)
        from .dashboard import export_dashboard
        manifest["status"] = "complete" if validation["failed_experiments"] == 0 else "partial_failure"
        links = {key:{"zh":f"{key}/{'validation' if key=='validation' else 'report'}_zh.html",
                      "en":f"{key}/{'validation' if key=='validation' else 'report'}_en.html"} for key in ("etf","stocks","validation")}
        report = export_dashboard(output,latest=latest,factors=last_factors,sectors=settings["sectors"],manifest=manifest,links=links)
        # Sector pages exist before portfolio rendering so every drill-down link
        # can be checked against its actual target, including standalone exports.
        for family, result in portfolio_results.items():
            export_report(result,output/family,data_kind=kind,input_sha256=digest,source_label=source["source"])
        manifest["artifacts_sha256"] = {p.relative_to(output).as_posix():sha256(p.read_bytes()) for p in sorted(output.rglob("*")) if p.is_file() and p != output/"manifest.json"}
        save_json(output/"manifest.json",manifest)
        if validation["failed_experiments"]:
            raise RuntimeError(f"{validation['failed_experiments']} validation experiments failed. Review {report}; latest successful report remains unchanged.")
        latest_meta = root / f"latest-{run_id}.tmp"
        save_json(latest_meta,{"run_id":run_id,"report":report.relative_to(root).as_posix(),"as_of":dates["as_of"],"data_kind":kind})
        relative = report.relative_to(root).as_posix()
        latest_html = root / f"report-{run_id}.tmp"
        latest_html.write_text(f'<!doctype html><html lang="en"><meta charset="utf-8"><title>v0.11 latest report</title><meta http-equiv="refresh" content="0;url={html.escape(relative,quote=True)}"><a href="{html.escape(relative,quote=True)}">Open latest report / 打开最新报告</a></html>',encoding="utf-8")
        latest_meta.replace(root / "latest.json")
        latest_html.replace(root / "report.html")
        print(f"Complete: {report}",flush=True)
        if args.open:
            webbrowser.open(report.resolve().as_uri())
        return report
    except Exception as exc:
        manifest.update(status="partial_failure" if manifest.get("status")=="partial_failure" else "failed",error=str(exc))
        save_json(output/"manifest.json",manifest)
        print(f"Run failed; details retained: {output / 'manifest.json'}",flush=True)
        raise
