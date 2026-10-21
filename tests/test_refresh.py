"""Current-date research must reject incomplete input and preserve provenance."""
from argparse import Namespace
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import pandas as pd

from quant_research.refresh import ROOT, audit_prices, default_config, default_workspace, load_settings, refresh, resolve_dates, synthetic_prices


class RefreshTests(unittest.TestCase):
    def setUp(self):
        self.settings, self.stocks = load_settings(ROOT/"configs"/"refresh.json")

    def test_clock_rolls_month_and_year_and_uses_closed_sessions(self):
        before = resolve_dates(self.settings,now="2026-10-01T19:00:00Z")
        after = resolve_dates(self.settings,now="2026-10-01T22:30:00Z")
        self.assertEqual(before["last_complete_session"],"2026-09-30")
        self.assertEqual(after["last_complete_session"],"2026-10-01")
        self.assertEqual(after["research_start"],"2021-10-01")
        new = resolve_dates(self.settings,now="2027-01-02T12:00:00Z")
        self.assertEqual(new["research_start"],"2022-01-01")
        self.assertEqual(new["holdout_start"],"2025-01-01")
        self.assertEqual(new["last_complete_session"],"2026-12-31")

    def test_shanghai_month_change_does_not_invent_ny_month_end(self):
        before = resolve_dates(self.settings,now="2026-09-30T17:00:00Z")
        self.assertEqual(before["as_of"],"2026-10-01")
        self.assertEqual(before["last_complete_session"],"2026-09-29")
        self.assertEqual(before["ranking_as_of"],"2026-09-01")
        after = resolve_dates(self.settings,now="2026-09-30T22:30:00Z")
        self.assertEqual(after["ranking_as_of"],"2026-10-01")

    def test_wheel_defaults_match_source_config_and_use_writable_cwd(self):
        bundled = ROOT / "quant_research" / "default_refresh.json"
        self.assertEqual(json.loads(bundled.read_text(encoding="utf-8")), self.settings)
        with tempfile.TemporaryDirectory() as folder, patch("quant_research.refresh.ROOT",Path(folder)):
            self.assertEqual(default_config(), bundled)
            self.assertEqual(default_workspace(),Path.cwd())

    def test_explicit_cutoff_is_exclusive_and_future_rejected(self):
        dates = resolve_dates(self.settings,as_of="2026-10-01",now="2026-10-21T12:00:00Z")
        self.assertEqual(dates["last_complete_session"],"2026-09-30")
        with self.assertRaises(ValueError):
            resolve_dates(self.settings,as_of="2027-01-01",now="2026-10-21T12:00:00Z")

    def test_missing_session_and_missing_ticker_are_detected(self):
        dates={"download_start":"2026-09-01","last_complete_session":"2026-09-30"}
        prices=synthetic_prices(["A","B"],dates)
        self.assertTrue(audit_prices(prices,["A","B"],dates).status.eq("passed").all())
        damaged=prices.drop(prices.index[3])
        audit=audit_prices(damaged,["A","B","C"],dates).set_index("ticker")
        self.assertEqual(audit.loc["A","missing_sessions"],1)
        self.assertEqual(audit.loc["C","status"],"failed")

    def test_download_failure_leaves_previous_latest_and_failed_manifest(self):
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder)
            (root/"report.html").write_text("previous report",encoding="utf-8")
            args=Namespace(config=None,as_of="2026-10-01",output=root,data_dir=root/"db",demo=False,prices=None,open=False)
            with patch("quant_research.refresh.fetch_yahoo",side_effect=RuntimeError("provider unavailable")):
                with self.assertRaisesRegex(RuntimeError,"provider unavailable"):
                    refresh(args)
            self.assertEqual((root/"report.html").read_text(),"previous report")
            manifest=json.loads(next((root/"runs").glob("*/manifest.json")).read_text(encoding="utf-8"))
            self.assertEqual(manifest["status"],"failed")
            self.assertIn("failed_raw_run_id",manifest)

    def test_partial_validation_does_not_publish_a_successful_latest(self):
        settings=json.loads(json.dumps(self.settings))
        for sector in settings["sectors"]:
            sector["stocks"]=sector["stocks"][:1]
        stocks=[s["stocks"][0]["ticker"] for s in settings["sectors"]]
        def fake_export(result,output,**kwargs):
            output.mkdir(parents=True)
            for name in ("report.html","report_zh.html","report_en.html"):
                (output/name).write_text("test report")
            return output/"report.html"
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder)
            (root/"report.html").write_text("previous success")
            args=Namespace(config=None,as_of="2026-10-01",output=root,data_dir=root/"db",demo=True,prices=None,open=False)
            with patch("quant_research.refresh.load_settings",return_value=(settings,stocks)), \
                 patch("quant_research.refresh.run_monthly",return_value={}), \
                 patch("quant_research.refresh.run_factor_monthly",return_value={}), \
                 patch("quant_research.refresh.export_report",side_effect=fake_export), \
                 patch("quant_research.validation.run_validation",return_value={"status":"partial_failure","completed_experiments":8,"failed_experiments":1}):
                with self.assertRaisesRegex(RuntimeError,"1 validation experiments failed"):
                    refresh(args)
            self.assertEqual((root/"report.html").read_text(),"previous success")
            self.assertFalse((root/"latest.json").exists())
            manifest=json.loads(next((root/"runs").glob("*/manifest.json")).read_text(encoding="utf-8"))
            self.assertEqual(manifest["status"],"partial_failure")
            self.assertEqual(manifest["validation_summary"]["completed_experiments"],8)
            sample=pd.read_csv(next((root/"runs").glob("*/price_samples.csv")))
            self.assertEqual(sample.ticker.nunique(),22)
            self.assertTrue(sample.groupby("ticker").size().eq(3).all())


if __name__=="__main__":
    unittest.main()
