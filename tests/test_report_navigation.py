"""Portable ETF drill-down links preserve language, sorting values and sample scope."""

from html import unescape
import json
from pathlib import Path
import re
import tempfile
import unittest

from quant_research.report import (
    WEIGHT_FIELDS, _report_navigation, _sector_navigation, _sortable_table,
)


class ReportNavigationTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.output = self.root / "etf"
        self.output.mkdir()
        self.sectors = [
            {"id": ticker, "name_en": f"Sector {ticker}", "name_zh": f"行业 {ticker}",
             "stocks": [{"ticker": f"S{index}"}]}
            for index, ticker in enumerate(("XLB", "XLC", "XLE", "XLF", "XLI", "XLK",
                                           "XLP", "XLRE", "XLU", "XLV", "XLY"))
        ]

    def make_dashboard(self):
        (self.root / "dashboard_data.json").write_text(
            json.dumps({"sectors": self.sectors}), encoding="utf-8")
        (self.root / "sectors").mkdir()
        for suffix in ("en", "zh"):
            (self.root / f"report_{suffix}.html").write_text("overview", encoding="utf-8")
            for sector in self.sectors:
                (self.root / "sectors" / f'{sector["id"]}_{suffix}.html').write_text(
                    "sector ranking", encoding="utf-8")

    def test_each_etf_opens_its_existing_sector_page_in_the_same_language(self):
        self.make_dashboard()
        for language, suffix in (("en", "en"), ("zh-CN", "zh")):
            with self.subTest(language=language):
                overview, links = _report_navigation(self.output, language)
                self.assertEqual(overview, f"../report_{suffix}.html")
                self.assertEqual(len(links), 11)
                navigation = _sector_navigation(links, language)
                self.assertEqual(navigation.count('class="sector-card"'), 11)
                for sector in self.sectors:
                    self.assertIn(f'href="../sectors/{sector["id"]}_{suffix}.html"', navigation)
                for href in re.findall(r'href="([^"]+)"', navigation):
                    self.assertTrue((self.output / unescape(href)).is_file(), href)
                if language == "en":
                    self.assertIn("configured research sample", navigation)
                    self.assertIn("not complete or historical ETF holdings", navigation)

    def test_ticker_drill_down_preserves_raw_sort_value_and_skips_other_stocks(self):
        self.make_dashboard()
        _, links = _report_navigation(self.output, "en")
        table = _sortable_table(
            [{"ticker": "XLK", "mean_close": .2}, {"ticker": "AAPL", "mean_close": .1}],
            ["ticker", "mean_close"], WEIGHT_FIELDS, "en", "weights", links,
        )
        self.assertIn('data-sort-value="XLK"><a class="etf-link" href="../sectors/XLK_en.html"', table)
        self.assertIn('data-sort-value="AAPL">AAPL</td>', table)
        self.assertIn('data-sort-value="0.2">20.0000%</td>', table)
        self.assertEqual(table.count('class="etf-link"'), 1)

    def test_standalone_or_incomplete_bundle_does_not_emit_missing_targets(self):
        self.assertEqual(_report_navigation(self.output, "en"), (None, {}))
        self.make_dashboard()
        (self.root / "sectors" / "XLK_en.html").unlink()
        overview, links = _report_navigation(self.output, "en")
        self.assertEqual(overview, "../report_en.html")
        self.assertNotIn("XLK", links)
        self.assertEqual(len(links), 10)
        self.assertEqual(_sector_navigation({}, "en"), "")

    def test_sector_ids_cannot_escape_the_bundle_and_labels_are_escaped(self):
        self.make_dashboard()
        self.sectors[0]["id"] = "../outside"
        (self.root / "dashboard_data.json").write_text(
            json.dumps({"sectors": self.sectors}), encoding="utf-8")
        with self.assertRaisesRegex(ValueError, "safe filename"):
            _report_navigation(self.output, "en")
        html = _sector_navigation(
            {"XLK": {"href": "../sectors/XLK_en.html", "name": "<script>bad</script>", "stock_count": 5}}, "en")
        self.assertNotIn("<script>", html)
        self.assertIn("&lt;script&gt;bad&lt;/script&gt;", html)


if __name__ == "__main__":
    unittest.main()
