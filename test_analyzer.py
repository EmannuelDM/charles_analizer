"""
Unit and integration tests for charles_analizer.
"""

import os
import shutil
import tempfile
import unittest
from pathlib import Path

import sys

pkg_dir = Path(__file__).resolve().parent
parent_dir = pkg_dir.parent

if str(parent_dir) not in sys.path:
    sys.path.insert(0, str(parent_dir))
if str(pkg_dir) not in sys.path:
    sys.path.insert(0, str(pkg_dir))

try:
    from charles_analizer.analyzer import CharlesAnalyzer
    from charles_analizer.exporter import CharlesExporter
    from charles_analizer.models import CharlesRequest
    from charles_analizer.parser import CharlesSessionParser
except ImportError:
    from analyzer import CharlesAnalyzer
    from exporter import CharlesExporter
    from models import CharlesRequest
    from parser import CharlesSessionParser


class TestCharlesAnalyzer(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        candidates = [
            Path(__file__).parent / "example_1.chlz",
            Path.cwd() / "example_1.chlz",
            Path("charles_analizer/example_1.chlz"),
            Path(__file__).parent / "charles_analizer" / "example_1.chlz",
        ]
        cls.example_chlz = None
        for c in candidates:
            if c.exists():
                cls.example_chlz = c
                break

        if not cls.example_chlz or not cls.example_chlz.exists():
            raise FileNotFoundError("Missing test file: example_1.chlz")

    def test_parser(self):
        parser = CharlesSessionParser(self.example_chlz)
        requests = parser.parse()
        self.assertGreater(len(requests), 0, "Parser should extract requests from example_1.chlz")
        
        first = requests[0]
        self.assertIsInstance(first, CharlesRequest)
        self.assertEqual(first.id, 0)
        self.assertIsNotNone(first.url)
        self.assertIn("mobile-collector.newrelic.com", first.host)

    def test_analyzer_summary(self):
        analyzer = CharlesAnalyzer.from_file(self.example_chlz)
        summary = analyzer.summary()

        self.assertEqual(summary["total_requests"], 112)
        self.assertEqual(summary["successful_requests"], 109)
        self.assertEqual(summary["failed_requests"], 3)
        self.assertIn(200, summary["status_codes"])
        self.assertIn(400, summary["status_codes"])
        self.assertIn(503, summary["status_codes"])

    def test_analyzer_filtering(self):
        analyzer = CharlesAnalyzer.from_file(self.example_chlz)
        
        # Host filter
        clarovideo_reqs = analyzer.filter(host="clarovideo.net")
        self.assertGreater(len(clarovideo_reqs), 0)

        # Status filter
        status_400 = analyzer.filter(status=400)
        self.assertEqual(len(status_400), 2)

        # Errors filter
        errors = analyzer.get_errors()
        self.assertEqual(len(errors), 3)

    def test_search(self):
        analyzer = CharlesAnalyzer.from_file(self.example_chlz)
        
        # Search URL keyword
        results = analyzer.search("linealpredictive")
        self.assertGreater(len(results), 0)
        
        # Search JSON body content
        results_body = analyzer.search("already_with_susc")
        self.assertEqual(len(results_body), 1)
        self.assertEqual(results_body[0].id, 32)

    def test_request_model_helpers(self):
        req = CharlesRequest(
            id=1,
            scheme="https",
            host="api.example.com",
            port=443,
            path="/v1/test",
            query="param=1",
            response_status=200,
            request_headers={"Content-Type": "application/json", "Authorization": "Bearer token"},
            response_headers={"content-encoding": "gzip"},
            request_sizes={"headers": 100, "body": 200},
            response_sizes={"headers": 150, "body": 1000},
        )

        self.assertTrue(req.is_2xx)
        self.assertFalse(req.is_4xx)
        self.assertEqual(req.status_category, "2xx")
        self.assertEqual(req.total_bytes, 1450)
        self.assertEqual(req.formatted_size, "1.42 KB")
        self.assertEqual(req.get_header("content-type"), "application/json")
        self.assertEqual(req.get_header("CONTENT-ENCODING", response=True), "gzip")

    def test_analyzer_percentiles_and_sorting(self):
        analyzer = CharlesAnalyzer.from_file(self.example_chlz)
        summary = analyzer.summary()

        self.assertIn("percentiles_ms", summary)
        p = summary["percentiles_ms"]
        self.assertIn("p50", p)
        self.assertIn("p90", p)
        self.assertIn("p95", p)
        self.assertIn("p99", p)

        # Sorting by duration descending
        sorted_reqs = analyzer.filter(sort_by="duration", reverse=True)
        self.assertEqual(len(sorted_reqs), len(analyzer.requests))
        self.assertGreaterEqual(sorted_reqs[0].duration_ms, sorted_reqs[-1].duration_ms)

    def test_exporters(self):
        analyzer = CharlesAnalyzer.from_file(self.example_chlz)
        with tempfile.TemporaryDirectory() as tmpdir:
            tmp_path = Path(tmpdir)

            json_out = CharlesExporter.to_json(analyzer.requests, tmp_path / "out.json")
            self.assertTrue(Path(json_out).exists())

            csv_out = CharlesExporter.to_csv(analyzer.requests, tmp_path / "out.csv")
            self.assertTrue(Path(csv_out).exists())

            html_out = CharlesExporter.to_html_report(analyzer.summary(), analyzer.requests, tmp_path / "out.html")
            self.assertTrue(Path(html_out).exists())

            payload_dir = CharlesExporter.export_payloads(analyzer.requests, tmp_path / "payloads")
            self.assertTrue(Path(payload_dir).exists())
            self.assertTrue((Path(payload_dir) / "manifest.json").exists())


if __name__ == "__main__":
    unittest.main()
