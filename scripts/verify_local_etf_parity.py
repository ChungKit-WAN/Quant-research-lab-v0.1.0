"""Replay local ETF archives without copying their data into the repository.

Usage: python scripts/verify_local_etf_parity.py --archive-dir PATH

The argument is the directory containing the saved ETF JSON reports. Reports
are linked by their canonical hashes, never by private paths stored inside
them. Passing this comparison establishes implementation parity only; it does
not independently authenticate market data or certify point-in-time coverage.
"""

from __future__ import annotations

import argparse
from dataclasses import asdict
import hashlib
import json
from numbers import Real
from pathlib import Path
import sys

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from sector_backtest.pipeline import MonthlyConfig, run_monthly  # noqa: E402


KINDS = ("return_dataset", "wealth_ledger", "rebalance_schedule", "target_weights", "performance")
IGNORED_METADATA = {"implementation_sha256", "input_sha256", "versions"}


def canonical_sha256(value):
    # Same convention as the original database._json: preserve Unicode, sort
    # keys, reject nonfinite JSON values, and retain json.dumps' default spaces.
    encoded = json.dumps(value, ensure_ascii=False, sort_keys=True, allow_nan=False).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def load_inventory(directory):
    if not directory.is_dir():
        raise ValueError("Archive directory does not exist; supply the directory containing ETF report JSON files")
    inventory = {kind: {} for kind in KINDS}
    for kind in KINDS:
        for path in sorted(directory.glob(f"*{kind}*.json")):
            wrapper = json.loads(path.read_text(encoding="utf-8-sig"))
            if not isinstance(wrapper, dict) or not {"report", "canonical_sha256"} <= wrapper.keys():
                raise ValueError(f"Invalid archive wrapper: {path.name}")
            digest = canonical_sha256(wrapper["report"])
            if digest != wrapper["canonical_sha256"]:
                raise ValueError(f"Canonical SHA-256 mismatch: {path.name}")
            inventory[kind][digest] = wrapper["report"]
    return inventory


def linked(inventory, kind, digest):
    if digest not in inventory[kind]:
        raise ValueError(f"Missing linked {kind} report with canonical SHA-256 {digest}")
    return inventory[kind][digest]


def compare(expected, actual, *, atol, rtol):
    """Compare all nested numeric/semantic values with bounded diagnostics."""
    result = {
        "passed": True, "numeric_values": 0, "semantic_values": 0,
        "max_absolute_difference": 0.0, "max_relative_difference": 0.0,
        "mismatch_count": 0, "first_mismatches": [],
    }

    def fail(path, message):
        result["passed"] = False
        result["mismatch_count"] += 1
        if len(result["first_mismatches"]) < 10:
            result["first_mismatches"].append({"field": path, "reason": message})

    def visit(old, new, path):
        if isinstance(old, dict) and isinstance(new, dict):
            if set(old) != set(new):
                fail(path, "Dictionary keys differ")
            for key in sorted(set(old) & set(new)):
                visit(old[key], new[key], f"{path}.{key}")
        elif isinstance(old, list) and isinstance(new, list):
            if len(old) != len(new):
                fail(path, f"Length differs: archive={len(old)}, replay={len(new)}")
            for index, (left, right) in enumerate(zip(old, new)):
                visit(left, right, f"{path}[{index}]")
        elif (isinstance(old, Real) and not isinstance(old, bool)
              and isinstance(new, Real) and not isinstance(new, bool)):
            result["numeric_values"] += 1
            if not np.isfinite(old) or not np.isfinite(new):
                fail(path, "Nonfinite number")
                return
            difference = abs(float(old) - float(new))
            relative = difference / max(abs(float(old)), abs(float(new)), 1e-300)
            result["max_absolute_difference"] = max(result["max_absolute_difference"], difference)
            result["max_relative_difference"] = max(result["max_relative_difference"], relative)
            if difference > atol + rtol * abs(float(old)):
                fail(path, f"Numeric difference {difference:.17g} exceeds tolerance")
        else:
            result["semantic_values"] += 1
            if type(old) is not type(new) or old != new:
                fail(path, "Semantic value or type differs")

    visit(expected, actual, "root")
    return result


def metric_payload(record):
    return {key: value for key, value in record.items() if key not in IGNORED_METADATA}


def verify(directory, *, ledger_sha256=None, expected_events=69, atol=1e-12, rtol=1e-12):
    inventory = load_inventory(directory)
    if ledger_sha256 is None:
        if len(inventory["wealth_ledger"]) != 1:
            raise ValueError("Expected one wealth_ledger report; use --ledger-sha256 to select among multiple archives")
        ledger_sha256 = next(iter(inventory["wealth_ledger"]))
    old_ledger = linked(inventory, "wealth_ledger", ledger_sha256)
    dataset_hash = old_ledger["dataset_sha256"]
    dataset = linked(inventory, "return_dataset", dataset_hash)
    target_hash = old_ledger["target_report_sha256"]
    targets = linked(inventory, "target_weights", target_hash)
    schedule_hash = targets["schedule_report_sha256"]
    schedule = linked(inventory, "rebalance_schedule", schedule_hash)
    if targets["dataset_sha256"] != dataset_hash or schedule["dataset_sha256"] != dataset_hash:
        raise ValueError("Target/schedule reports refer to a different price dataset")
    payload = dataset["adjusted_prices"]
    prices = pd.DataFrame(payload["values"], index=pd.to_datetime(payload["dates"]), columns=payload["columns"])
    config = MonthlyConfig()
    if (list(config.tickers) != old_ledger["tickers"]
            or list(config.tickers) != targets["tickers"]
            or list(config.tickers) != schedule["tickers"]):
        raise ValueError("Archive ticker order differs from the default ETF configuration")
    replay = run_monthly(prices, config)
    old_events = [{
        "signal": event["signal_session"], "execution": event["execution_session"],
        "window_first": event["window"]["first_return_session"],
        "window_last": event["window"]["last_return_session"],
        "window_observations": event["window"]["return_observations"],
        "returns_sha256": event["window"]["returns_sha256"],
    } for event in schedule["events"]]
    checks = {"schedule": compare(old_events, replay["schedule"], atol=atol, rtol=rtol)}
    checks["event_count"] = compare(expected_events, len(replay["schedule"]), atol=0, rtol=0)
    if set(old_ledger["paths"]) != set(replay["strategies"]):
        raise ValueError("Archive/replay strategy names differ")
    strategy_results = {}
    for strategy, new_path in replay["strategies"].items():
        old_path = old_ledger["paths"][strategy]
        strategy_checks = {
            "daily": compare(old_path["daily"], new_path["daily"], atol=atol, rtol=rtol),
            "daily_nav": compare([row["nav"] for row in old_path["daily"]],
                                 [row["nav"] for row in new_path["daily"]], atol=atol, rtol=rtol),
            "daily_cost": compare([row["transaction_cost"] for row in old_path["daily"]],
                                  [row["transaction_cost"] for row in new_path["daily"]], atol=atol, rtol=rtol),
            "daily_weights": compare([row["weights"] for row in old_path["daily"]],
                                     [row["weights"] for row in new_path["daily"]], atol=atol, rtol=rtol),
            "target_weights": compare(
                [record["target_weights"][strategy] for record in targets["records"]],
                [trade["execution"]["inputs"]["target_weights"] for trade in new_path["trades"]],
                atol=atol, rtol=rtol,
            ),
        }
        strategy_results[strategy] = {
            "daily_rows": len(new_path["daily"]), "rebalance_count": new_path["rebalance_count"],
            "archive_final_nav": old_path["final_nav"], "replay_final_nav": new_path["final_nav"],
            "checks": strategy_checks,
        }

    performance_matches = {
        digest: report for digest, report in inventory["performance"].items()
        if report.get("ledger_report_sha256") == ledger_sha256
    }
    if len(performance_matches) > 1:
        raise ValueError("Multiple distinct performance reports refer to this ledger; use an unambiguous archive directory")
    metric_checks = {}
    performance_hash = None
    if performance_matches:
        performance_hash, performance = next(iter(performance_matches.items()))
        old_metrics = {(row["strategy"], row["period"]): row for row in performance["records"]}
        new_metrics = {(row["strategy"], row["period"]): row for row in replay["metrics"]}
        if (len(old_metrics) != len(performance["records"]) or set(old_metrics) != set(new_metrics)):
            raise ValueError("Performance record keys differ or contain duplicate strategy/period pairs")
        for key, record in old_metrics.items():
            metric_checks["/".join(key)] = compare(
                metric_payload(record), metric_payload(new_metrics[key]), atol=atol, rtol=rtol,
            )
    all_checks = list(checks.values()) + list(metric_checks.values())
    all_checks.extend(check for result in strategy_results.values() for check in result["checks"].values())
    return {
        "schema_version": "local_etf_portability_parity_v1",
        "passed": all(check["passed"] for check in all_checks),
        "scope": "Replay parity against locally saved ETF archives; not independent market-data authentication",
        "limitations": [
            "Canonical hashes detect content changes relative to saved digests, not data-provider truth.",
            "The comparison inherits the archived fixed universe and adjusted-price data limitations.",
            "Implementation and input fingerprints and dependency versions are excluded from metric comparisons.",
        ],
        "outer_canonical_hashes_verified": True,
        "source_report_hashes": {"return_dataset": dataset_hash, "wealth_ledger": ledger_sha256,
                                 "target_weights": target_hash, "rebalance_schedule": schedule_hash,
                                 "performance": performance_hash},
        "config": asdict(config), "tolerance": {"absolute": atol, "relative": rtol},
        "price_rows": len(prices), "first_price_session": prices.index[0].strftime("%Y-%m-%d"),
        "last_price_session": prices.index[-1].strftime("%Y-%m-%d"),
        "schedule_events": len(replay["schedule"]), "checks": checks,
        "strategies": strategy_results,
        "performance_status": "compared" if performance_matches else "no_linked_performance_archive",
        "performance_checks": metric_checks,
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--archive-dir", required=True, type=Path)
    parser.add_argument("--ledger-sha256", help="Select a ledger when the directory contains multiple runs")
    parser.add_argument("--expected-events", type=int, default=69)
    parser.add_argument("--output", type=Path, default=Path("outputs/parity.json"))
    args = parser.parse_args()
    if args.expected_events < 1:
        parser.error("--expected-events must be positive")
    try:
        result = verify(args.archive_dir, ledger_sha256=args.ledger_sha256, expected_events=args.expected_events)
    except (OSError, ValueError, KeyError, TypeError) as exc:
        parser.exit(2, f"Archive verification failed: {exc}\n")
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, ensure_ascii=False, sort_keys=True, indent=2, allow_nan=False) + "\n",
                           encoding="utf-8")
    print(json.dumps({"passed": result["passed"], "schedule_events": result["schedule_events"],
                      "performance_records": len(result["performance_checks"]),
                      "max_absolute_difference": max(
                          check["max_absolute_difference"]
                          for item in result["strategies"].values() for check in item["checks"].values()),
                      "output": str(args.output)}, ensure_ascii=False))
    return 0 if result["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
