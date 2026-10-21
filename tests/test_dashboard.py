"""Portable report artifacts and exact browser ranking behavior."""

from html import unescape
import json
from pathlib import Path
import re
import shutil
import subprocess
import tempfile
import unittest

import numpy as np
import pandas as pd

from hkquant.registry import FACTOR_SPECS
from quant_research.dashboard import JS, SORT_JS, export_dashboard


def fixture():
    ids = ("XLB", "XLC", "XLE", "XLF", "XLI", "XLK", "XLP", "XLRE", "XLU", "XLV", "XLY")
    sectors = [{"id": key, "name_zh": "行业 " + key, "name_en": "Sector " + key,
                "stocks": [{"ticker": f"{key}{n}", "name": f"Company {key}{n}"} for n in range(3)]}
               for key in ids]
    rankings, factors = [], []
    for i, sector in enumerate(sectors):
        for n, stock in enumerate(sector["stocks"]):
            rankings.append({"ticker": stock["ticker"], "date": "2026-09-30", "score": (i + n) / 35,
                             "rank": 33 - i - n, "rolling_rank": 31 - i - n})
            factors.append({"ticker": stock["ticker"], "date": "2026-09-30",
                            **{spec.id: ((i + 1) * (n + 1) / 100) for spec in FACTOR_SPECS}})
    return sectors, pd.DataFrame(rankings), pd.DataFrame(factors)


class DashboardTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.sectors, self.latest, self.factors = fixture()

    def render(self, **kwargs):
        values = dict(latest=self.latest, factors=self.factors, sectors=self.sectors,
                      manifest={"as_of": "2026-10-21", "latest_month_anchor": "2026-09-30", "data_kind": "synthetic_demo"})
        values.update(kwargs)
        return export_dashboard(self.root, **values)

    def test_bilingual_bundle_has_all_sector_pages_factors_and_working_links(self):
        index = self.render()
        self.assertEqual(index, self.root / "report.html")
        entry = index.read_text(encoding="utf-8")
        self.assertIn('<html lang="en">', entry)
        self.assertEqual(entry, (self.root / "report_en.html").read_text(encoding="utf-8"))
        self.assertIn('id="sector-etfs"', entry)
        for sector in self.sectors:
            self.assertIn(f'class="etf-card" href="sectors/{sector["id"]}_en.html"', entry)
        pages = list((self.root / "sectors").glob("*.html"))
        self.assertEqual(len(pages), 22)
        data = json.loads((self.root / "dashboard_data.json").read_text(encoding="utf-8"))
        self.assertEqual(len(data["rows"]), 33)
        factor_ids = {spec.id for spec in FACTOR_SPECS}
        self.assertEqual(factor_ids, {d["id"] for d in data["definitions"] if d["group"] != "summary"})
        for row in data["rows"]:
            self.assertTrue(factor_ids.issubset(row))
            self.assertTrue(all(row[s.id] is None for s in FACTOR_SPECS if s.status != "implemented"))
        csv = pd.read_csv(self.root / "latest_factors.csv")
        self.assertTrue(factor_ids.issubset(csv.columns))
        for page in [index, self.root / "report_zh.html", self.root / "report_en.html", *pages]:
            content = page.read_text(encoding="utf-8")
            for link in re.findall(r'href="([^"]+)"', content):
                if link.startswith("#"):
                    continue
                self.assertTrue((page.parent / unescape(link)).is_file(), (page, link))
            if page != index:
                embedded = re.search(r'<script type="application/json" id="report-data">(.*?)</script>', content, re.S)
                self.assertIsNotNone(embedded)
                self.assertEqual(json.loads(embedded.group(1)), data)
                self.assertIn('id="direction"', content)
                self.assertIn('value="asc"', content)
                self.assertIn('value="desc"', content)
                self.assertNotRegex(content, r'<(?:script|link)[^>]+(?:src|href)="https?://')
        self.assertIn("SYNTHETIC DEMO", (self.root / "report_en.html").read_text(encoding="utf-8"))
        self.assertIn("XLB · Sector XLB stock rankings", (self.root / "sectors/XLB_en.html").read_text(encoding="utf-8"))

    def test_missing_stock_and_nonfinite_factors_remain_unrankable(self):
        self.factors.loc[0, "mom_return_21"] = np.inf
        self.factors = self.factors.iloc[:-1].copy()
        self.latest = self.latest.iloc[:-1].copy()
        self.render()
        data = json.loads((self.root / "dashboard_data.json").read_text(encoding="utf-8"))
        self.assertIsNone(data["rows"][0]["mom_return_21"])
        missing = data["rows"][-1]
        self.assertIsNone(missing["score"])
        self.assertIsNone(missing["mom_return_21"])
        self.assertEqual(missing["reason"], "missing_snapshot")

    def test_untrusted_names_and_metadata_cannot_end_embedded_script(self):
        attack = '</script><script>alert("bad")</script>'
        self.sectors[0]["stocks"][0]["name"] = attack
        self.sectors[0]["name_zh"] = '<img src=x onerror="alert(1)">'
        self.render(manifest={"source": attack})
        text = (self.root / "report_zh.html").read_text(encoding="utf-8")
        self.assertNotIn(attack, text)
        self.assertNotIn('<img src=x', text)
        self.assertIn('\\u003c/script\\u003e', text)
        data = json.loads((self.root / "dashboard_data.json").read_text(encoding="utf-8"))
        self.assertEqual(data["rows"][0]["name"], attack)

    def test_resource_links_resolve_from_sector_pages(self):
        for path in ("etf/report_zh.html", "etf/report_en.html"):
            target = self.root / path
            target.parent.mkdir(exist_ok=True)
            target.write_text("fixture", encoding="utf-8")
        self.render(links={"etf": {"zh": "etf/report_zh.html", "en": "etf/report_en.html"}})
        self.assertIn('href="../etf/report_en.html"', (self.root / "sectors/XLB_en.html").read_text(encoding="utf-8"))

    def test_bad_snapshots_and_unsafe_links_are_rejected(self):
        with self.assertRaisesRegex(ValueError, "11 unique"):
            self.render(sectors=self.sectors[:-1])
        with self.assertRaisesRegex(ValueError, "one snapshot"):
            self.render(factors=pd.concat([self.factors, self.factors.iloc[:1]]))
        with self.assertRaisesRegex(ValueError, "relative paths"):
            self.render(links={"oops": "javascript:alert(1)"})
        with self.assertRaisesRegex(ValueError, "relative paths"):
            self.render(links={"oops": "../secret"})

    def test_old_factor_snapshot_cannot_be_presented_as_new_month(self):
        self.factors.loc[0, "date"] = "2026-08-31"
        with self.assertRaisesRegex(ValueError, "snapshot dates differ"):
            self.render()

    @unittest.skipUnless(shutil.which("node"), "Node is optional; browser sort integration check")
    def test_actual_browser_sort_is_numeric_missing_last_and_ties_are_stable(self):
        # Execute the same source embedded in HTML, not a Python approximation.
        script_file = self.root / "report.js"
        script_file.write_text(JS, encoding="utf-8")
        subprocess.run([shutil.which("node"), "--check", str(script_file)], check=True, capture_output=True, text=True)
        script = SORT_JS + r'''
const input = [{ticker:'B',v:2},{ticker:'D',v:null},{ticker:'A',v:2},{ticker:'C',v:10},{ticker:'E',v:-4},{ticker:'F',v:NaN}];
console.log(JSON.stringify({asc:rankRows(input,'v','asc'),desc:rankRows(input,'v','desc')}));
'''
        result = subprocess.run([shutil.which("node"), "-e", script], check=True, capture_output=True, text=True)
        orders = json.loads(result.stdout)
        self.assertEqual([x["row"]["ticker"] for x in orders["asc"]], ["E", "A", "B", "C", "D", "F"])
        self.assertEqual([x["rank"] for x in orders["asc"]], [1, 2, 2, 4, None, None])
        self.assertEqual([x["row"]["ticker"] for x in orders["desc"]], ["C", "A", "B", "E", "D", "F"])
        self.assertEqual([x["rank"] for x in orders["desc"]], [1, 2, 2, 4, None, None])


if __name__ == "__main__":
    unittest.main()
