"""Persistence tests: preservation, lineage, atomic failure, and SQL NULLs."""

from contextlib import contextmanager
from pathlib import Path
import sqlite3
import tempfile
import unittest

import pandas as pd

from hkquant.database import save_ingestion, read_ingestion, save_calculation, database_status
from hkquant.ranking import OUTPUT_COLUMNS
from hkquant.registry import FACTOR_SPECS, IMPLEMENTED_SPECS


def prices():
    return pd.DataFrame([
        dict(date="2025-01-02",ticker="AAPL",open=99.75,high=102.5,low=99.0,close=101.123456789,adj_close=100.987654321,volume=123456),
        dict(date="2025-01-03",ticker="AAPL",open=101.0,high=103.0,low=100.0,close=102.0,adj_close=101.87,volume=234567),
    ])


@contextmanager
def connection(path):
    conn = sqlite3.connect(path)
    try:
        with conn:
            yield conn
    finally:
        conn.close()


class DatabaseTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.raw = Path(self.tmp.name)/"raw.sqlite"
        self.calc = Path(self.tmp.name)/"calculated.sqlite"
        self.payload = b"original,bytes\r\nAAPL,101.123456789\r\n"

    def tearDown(self):
        self.tmp.cleanup()

    def ingest(self):
        return save_ingestion(self.raw,prices(),[("AAPL","original_csv_bytes",self.payload)],{"source":"test fixture"})

    def test_roundtrip_preserves_bytes_and_price_precision(self):
        identifier=self.ingest()
        actual_id,actual,meta=read_ingestion(self.raw,identifier)
        self.assertEqual(identifier,actual_id)
        self.assertEqual(actual.iloc[0].close,101.123456789)
        self.assertEqual(meta["source"],"test fixture")
        with connection(self.raw) as conn:
            self.assertEqual(conn.execute("SELECT content FROM source_payloads").fetchone()[0],self.payload)

    def test_downloads_are_new_snapshots_and_cannot_overwrite(self):
        first=self.ingest()
        second=self.ingest()
        self.assertNotEqual(first,second)
        self.assertEqual(read_ingestion(self.raw,first)[0],first)
        self.assertEqual(read_ingestion(self.raw)[0],second)
        with connection(self.raw) as conn:
            self.assertEqual(conn.execute("SELECT COUNT(*) FROM daily_bars").fetchone()[0],4)
            with self.assertRaisesRegex(sqlite3.IntegrityError,"Append-only"):
                conn.execute("UPDATE daily_bars SET close=1")
            with self.assertRaisesRegex(sqlite3.IntegrityError,"Append-only"):
                conn.execute("DELETE FROM source_payloads")
            for table in ("source_payloads", "daily_bars", "ingestion_runs"):
                with self.subTest(table=table), self.assertRaisesRegex(sqlite3.IntegrityError,"Append-only"):
                    conn.execute(f"INSERT OR REPLACE INTO {table} SELECT * FROM {table} LIMIT 1")

    def test_failed_download_retains_payload_but_is_not_selected(self):
        complete=self.ingest()
        failed=save_ingestion(self.raw,None,[("AAPL","csv",self.payload)],{},status="failed",error="missing MSFT")
        self.assertEqual(read_ingestion(self.raw)[0],complete)
        with self.assertRaisesRegex(ValueError,"Not a complete"):
            read_ingestion(self.raw,failed)
        with connection(self.raw) as conn:
            self.assertEqual(conn.execute("SELECT error FROM ingestion_runs WHERE raw_run_id=?",(failed,)).fetchone()[0],"missing MSFT")

    def test_invalid_payload_rolls_back_the_whole_batch(self):
        self.ingest()
        with self.assertRaises(TypeError):
            save_ingestion(self.raw,prices(),[("bad","csv","not bytes")],{})
        with connection(self.raw) as conn:
            self.assertEqual(conn.execute("SELECT COUNT(*) FROM ingestion_runs").fetchone()[0],1)

    def test_integrity_check_detects_changed_source_after_trigger_removed(self):
        identifier=self.ingest()
        with connection(self.raw) as conn:
            conn.execute("DROP TRIGGER prevent_source_payloads_update")
            conn.execute("UPDATE source_payloads SET content=?",(b"tampered",))
        with self.assertRaisesRegex(ValueError,"SHA-256"):
            read_ingestion(self.raw,identifier)

    def test_calculations_keep_versions_and_pending_fields_null(self):
        raw_id=self.ingest()
        _,raw,metadata=read_ingestion(self.raw,raw_id)
        factors=raw[["date","ticker"]].copy()
        for spec in IMPLEMENTED_SPECS:
            factors[spec.id]=0.125
        # Lack of a complete month is permitted: raw and daily factors still persist.
        monthly=pd.DataFrame(columns=OUTPUT_COLUMNS)
        first=save_calculation(self.calc,raw_id,self.raw,factors,monthly,{"version":1},metadata,"code1")
        second=save_calculation(self.calc,raw_id,self.raw,factors,monthly,{"version":2},metadata,"code2")
        self.assertNotEqual(first,second)
        pending=next(s.id for s in FACTOR_SPECS if s.status!="implemented")
        with connection(self.calc) as conn:
            self.assertEqual(conn.execute("SELECT COUNT(*) FROM calculation_runs").fetchone()[0],2)
            self.assertEqual(conn.execute("SELECT COUNT(*) FROM factor_definitions").fetchone()[0],200)
            self.assertIsNone(conn.execute(f'SELECT "{pending}" FROM factor_values LIMIT 1').fetchone()[0])
            self.assertEqual(conn.execute("SELECT raw_run_id FROM calculation_runs WHERE calculation_id=?",(first,)).fetchone()[0],raw_id)
            with self.assertRaises(sqlite3.IntegrityError):
                conn.execute("DELETE FROM factor_values")
        status=database_status(self.raw,self.calc)
        self.assertEqual(status["calculated"]["rows"]["factor_values"],4)


if __name__ == "__main__":
    unittest.main()
