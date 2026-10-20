"""Append-only source snapshots and a separate versioned calculation database."""

from __future__ import annotations

from dataclasses import asdict
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import sqlite3
import uuid

import pandas as pd

from .data import PRICE_COLUMNS, validate_prices
from .registry import FACTOR_SPECS


def _json(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True, allow_nan=False)


def _sha(value: bytes):
    return hashlib.sha256(value).hexdigest()


def _stamp():
    return datetime.now(timezone.utc).isoformat()


def _connect(path, read_only=False):
    path = Path(path).resolve()
    if read_only:
        if not path.exists():
            raise FileNotFoundError(f"Database not found: {path}")
        conn = sqlite3.connect(path.as_uri() + "?mode=ro", uri=True)
    else:
        path.parent.mkdir(parents=True, exist_ok=True)
        conn = sqlite3.connect(path)
    conn.execute("PRAGMA foreign_keys=ON")
    return conn


def _immutable(conn, tables):
    for table in tables:
        keys = [row[1] for row in sorted(conn.execute(f'PRAGMA table_info("{table}")'), key=lambda r: r[5]) if row[5]]
        duplicate = " AND ".join(f'"{key}" = NEW."{key}"' for key in keys)
        # REPLACE can bypass DELETE triggers when recursive_triggers is off.
        conn.execute(f'''CREATE TRIGGER IF NOT EXISTS prevent_{table}_replace
            BEFORE INSERT ON {table}
            WHEN EXISTS (SELECT 1 FROM {table} WHERE {duplicate})
            BEGIN SELECT RAISE(ABORT, 'Append-only research records cannot be replaced'); END''')
        for operation in ("UPDATE", "DELETE"):
            conn.execute(f'''CREATE TRIGGER IF NOT EXISTS prevent_{table}_{operation.lower()}
                BEFORE {operation} ON {table}
                BEGIN SELECT RAISE(ABORT, 'Append-only research records cannot be changed'); END''')


def _price_bytes(prices):
    return prices[PRICE_COLUMNS].to_csv(index=False, date_format="%Y-%m-%d", float_format="%.17g").encode("utf-8")


def save_ingestion(path, prices, payloads, metadata, *, status="complete", error=None):
    """Archive provider tables/CSV bytes before any factor computation.

    payloads: sequence of (symbol_or_label, format, bytes). All successful runs
    require a preserved payload. Failed downloads may retain partial responses.
    Each call appends a new snapshot even when the requested dates overlap.
    """
    if status not in ("complete", "failed"):
        raise ValueError("Ingestion status must be complete or failed")
    if status == "complete" and not payloads:
        raise ValueError("A successful ingestion must retain original source payloads")
    clean = validate_prices(prices) if prices is not None else None
    if status == "complete" and clean is None:
        raise ValueError("A successful ingestion requires prices")
    run_id = "raw_" + uuid.uuid4().hex
    conn = _connect(path)
    try:
        conn.executescript('''
        CREATE TABLE IF NOT EXISTS ingestion_runs (
          raw_run_id TEXT PRIMARY KEY, created_at_utc TEXT NOT NULL,
          status TEXT NOT NULL CHECK(status IN ('complete','failed')),
          metadata_json TEXT NOT NULL, row_count INTEGER NOT NULL,
          canonical_sha256 TEXT, error TEXT);
        CREATE TABLE IF NOT EXISTS source_payloads (
          raw_run_id TEXT NOT NULL REFERENCES ingestion_runs(raw_run_id),
          payload_number INTEGER NOT NULL, label TEXT NOT NULL, format TEXT NOT NULL,
          content BLOB NOT NULL, sha256 TEXT NOT NULL,
          PRIMARY KEY(raw_run_id,payload_number));
        CREATE TABLE IF NOT EXISTS daily_bars (
          raw_run_id TEXT NOT NULL REFERENCES ingestion_runs(raw_run_id),
          date TEXT NOT NULL, ticker TEXT NOT NULL,
          open REAL NOT NULL, high REAL NOT NULL, low REAL NOT NULL,
          close REAL NOT NULL, adj_close REAL NOT NULL, volume REAL NOT NULL,
          PRIMARY KEY(raw_run_id,ticker,date));
        CREATE INDEX IF NOT EXISTS bars_ticker_date ON daily_bars(ticker,date);
        ''')
        _immutable(conn, ("ingestion_runs", "source_payloads", "daily_bars"))
        with conn:
            conn.execute("INSERT INTO ingestion_runs VALUES (?,?,?,?,?,?,?)", (
                run_id, _stamp(), status, _json(metadata), len(clean) if clean is not None else 0,
                _sha(_price_bytes(clean)) if clean is not None else None, error))
            for number, (label, format_name, content) in enumerate(payloads):
                if not isinstance(content, bytes):
                    raise TypeError("Source payloads must be bytes")
                conn.execute("INSERT INTO source_payloads VALUES (?,?,?,?,?,?)", (
                    run_id, number, str(label), format_name, content, _sha(content)))
            if clean is not None:
                rows = ((run_id, row.date.strftime("%Y-%m-%d"), row.ticker,
                         row.open, row.high, row.low, row.close, row.adj_close, row.volume)
                        for row in clean.itertuples(index=False))
                conn.executemany("INSERT INTO daily_bars VALUES (?,?,?,?,?,?,?,?,?)", rows)
    finally:
        conn.close()
    return run_id


def read_ingestion(path, raw_run_id=None):
    """Read exactly one complete snapshot; never merge conflicting downloads."""
    conn = _connect(path, read_only=True)
    try:
        if raw_run_id is None:
            row = conn.execute("SELECT raw_run_id FROM ingestion_runs WHERE status='complete' ORDER BY created_at_utc DESC,rowid DESC LIMIT 1").fetchone()
            if row is None:
                raise ValueError("No successful raw-data snapshot is available")
            raw_run_id = row[0]
        record = conn.execute("SELECT status,metadata_json,row_count,canonical_sha256 FROM ingestion_runs WHERE raw_run_id=?", (raw_run_id,)).fetchone()
        if record is None or record[0] != "complete":
            raise ValueError(f"Not a complete raw snapshot: {raw_run_id}")
        for content, expected in conn.execute("SELECT content,sha256 FROM source_payloads WHERE raw_run_id=?", (raw_run_id,)):
            if _sha(content) != expected:
                raise ValueError("A source payload failed the SHA-256 check")
        columns = ",".join(PRICE_COLUMNS)
        prices = pd.read_sql_query(f"SELECT {columns} FROM daily_bars WHERE raw_run_id=? ORDER BY ticker,date", conn, params=(raw_run_id,))
        clean = validate_prices(prices)
        if len(clean) != record[2] or _sha(_price_bytes(clean)) != record[3]:
            raise ValueError("Stored daily bars failed the snapshot integrity check")
        metadata = json.loads(record[1])
        metadata["canonical_sha256"] = record[3]
        return raw_run_id, clean, metadata
    finally:
        conn.close()


def save_calculation(path, raw_run_id, raw_database, factors, monthly, config, source_metadata, code_hash):
    """Append a calculation version. Missing/unimplemented values remain SQL NULL."""
    calc_id = "calc_" + uuid.uuid4().hex
    ids = [spec.id for spec in FACTOR_SPECS]
    missing = [s.id for s in FACTOR_SPECS if s.status == "implemented" and s.id not in factors]
    if missing:
        raise ValueError(f"Missing implemented factor columns: {missing}")
    if factors.duplicated(["date", "ticker"]).any():
        raise ValueError("Duplicate factor date/ticker observations")
    factor_defs = _json([asdict(s) for s in FACTOR_SPECS])
    numerical = ",".join(f'"{identifier}" REAL' for identifier in ids)
    conn = _connect(path)
    try:
        conn.executescript(f'''
        CREATE TABLE IF NOT EXISTS calculation_runs (
          calculation_id TEXT PRIMARY KEY, created_at_utc TEXT NOT NULL,
          raw_run_id TEXT NOT NULL, raw_database TEXT NOT NULL,
          config_json TEXT NOT NULL, source_metadata_json TEXT NOT NULL,
          code_sha256 TEXT NOT NULL, factor_catalog_sha256 TEXT NOT NULL,
          factor_rows INTEGER NOT NULL, monthly_rows INTEGER NOT NULL);
        CREATE TABLE IF NOT EXISTS factor_definitions (
          calculation_id TEXT NOT NULL REFERENCES calculation_runs(calculation_id),
          factor_id TEXT NOT NULL, group_name TEXT NOT NULL, label TEXT NOT NULL,
          formula TEXT NOT NULL, direction INTEGER NOT NULL, min_observations INTEGER NOT NULL,
          status TEXT NOT NULL, PRIMARY KEY(calculation_id,factor_id));
        CREATE TABLE IF NOT EXISTS factor_values (
          calculation_id TEXT NOT NULL REFERENCES calculation_runs(calculation_id),
          date TEXT NOT NULL, ticker TEXT NOT NULL, {numerical},
          PRIMARY KEY(calculation_id,ticker,date));
        CREATE INDEX IF NOT EXISTS factor_ticker_date ON factor_values(ticker,date);
        CREATE TABLE IF NOT EXISTS monthly_rankings (
          calculation_id TEXT NOT NULL REFERENCES calculation_runs(calculation_id),
          date TEXT NOT NULL,ticker TEXT NOT NULL,eligible INTEGER NOT NULL,
          reason TEXT,score REAL,rank REAL,rank_percentile REAL,
          rolling_mean_rank REAL,rolling_mean_percentile REAL,rolling_rank REAL,
          rolling_eligible INTEGER NOT NULL,rolling_reason TEXT,
          group_score_momentum REAL,group_score_reversal REAL,group_score_risk REAL,group_score_liquidity REAL,
          PRIMARY KEY(calculation_id,ticker,date));
        ''')
        _immutable(conn, ("calculation_runs", "factor_definitions", "factor_values", "monthly_rankings"))
        wide = factors.reindex(columns=["date", "ticker", *ids]).copy()
        wide["date"] = pd.to_datetime(wide.date).dt.strftime("%Y-%m-%d")
        ranking_columns = ["date", "ticker", "eligible", "reason", "score", "rank", "rank_percentile", "rolling_mean_rank", "rolling_mean_percentile", "rolling_rank", "rolling_eligible", "rolling_reason", "group_score_momentum", "group_score_reversal", "group_score_risk", "group_score_liquidity"]
        ranks = monthly.reindex(columns=ranking_columns).copy()
        ranks["date"] = pd.to_datetime(ranks.date).dt.strftime("%Y-%m-%d")

        def nullable_rows(frame):
            for row in frame.itertuples(index=False, name=None):
                yield (calc_id, *(None if pd.isna(value) else value for value in row))

        with conn:
            conn.execute("INSERT INTO calculation_runs VALUES (?,?,?,?,?,?,?,?,?,?)", (
                calc_id, _stamp(), raw_run_id, str(Path(raw_database).resolve()), _json(config),
                _json(source_metadata), code_hash, _sha(factor_defs.encode()), len(factors), len(monthly)))
            conn.executemany("INSERT INTO factor_definitions VALUES (?,?,?,?,?,?,?,?)", (
                (calc_id,s.id,s.group,s.label,s.formula,s.direction,s.min_observations,s.status) for s in FACTOR_SPECS))
            conn.executemany("INSERT INTO factor_values VALUES (" + ",".join("?" for _ in range(len(ids)+3)) + ")", nullable_rows(wide))
            conn.executemany("INSERT INTO monthly_rankings VALUES (" + ",".join("?" for _ in range(17)) + ")", nullable_rows(ranks))
    finally:
        conn.close()
    return calc_id


def database_status(raw_path, calculated_path):
    result = {}
    for label, path, tables in (
        ("raw", raw_path, ("ingestion_runs", "source_payloads", "daily_bars")),
        ("calculated", calculated_path, ("calculation_runs", "factor_definitions", "factor_values", "monthly_rankings")),
    ):
        path = Path(path)
        item = {"path": str(path.resolve()), "exists": path.exists()}
        if path.exists():
            conn = _connect(path, read_only=True)
            try:
                existing = {row[0] for row in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")}
                item["rows"] = {table: conn.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0] for table in tables if table in existing}
                item["size_bytes"] = path.stat().st_size
            finally:
                conn.close()
        result[label] = item
    return result
