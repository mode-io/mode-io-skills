#!/usr/bin/env python3

import sys
import unittest
from pathlib import Path

SCRIPTS_DIR = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(SCRIPTS_DIR))

import precommit_scan  # noqa: E402


class TestPrecommitScan(unittest.TestCase):
    def test_parse_staged_added_lines_tracks_paths_and_line_numbers(self):
        diff = """diff --git a/app.py b/app.py
index 1111111..2222222 100644
--- a/app.py
+++ b/app.py
@@ -10,0 +11,2 @@
+email = \"alice@example.com\"
+print(\"ok\")
@@ -20,1 +22,0 @@
-old_value = 1
"""
        added = precommit_scan.parse_staged_added_lines(diff)
        self.assertEqual(len(added), 2)
        self.assertEqual(added[0].path, "app.py")
        self.assertEqual(added[0].line_number, 11)
        self.assertEqual(added[1].line_number, 12)

    def test_collect_findings_detects_medium_risk_email(self):
        added_lines = [
            precommit_scan.AddedLine(
                path="app.py",
                line_number=8,
                content='email = "alice@example.com"',
            )
        ]

        findings = precommit_scan.collect_findings(
            added_lines,
            profile="balanced",
            minimum_risk_level="medium",
            allowlist_rules=None,
            blocklist_rules=None,
            threshold_overrides=None,
        )
        self.assertGreaterEqual(len(findings), 1)
        self.assertEqual(findings[0]["path"], "app.py")
        self.assertEqual(findings[0]["line"], 8)
        self.assertEqual(findings[0]["type"], "email")

    def test_collect_findings_high_filter_skips_email(self):
        added_lines = [
            precommit_scan.AddedLine(
                path="app.py",
                line_number=9,
                content='email = "alice@example.com"',
            )
        ]
        findings = precommit_scan.collect_findings(
            added_lines,
            profile="balanced",
            minimum_risk_level="high",
            allowlist_rules=None,
            blocklist_rules=None,
            threshold_overrides=None,
        )
        self.assertEqual(findings, [])

    def test_collect_findings_high_filter_keeps_ssn(self):
        added_lines = [
            precommit_scan.AddedLine(
                path="personal.txt",
                line_number=3,
                content="ssn: 123-45-6789",
            )
        ]
        findings = precommit_scan.collect_findings(
            added_lines,
            profile="balanced",
            minimum_risk_level="high",
            allowlist_rules=None,
            blocklist_rules=None,
            threshold_overrides=None,
        )
        self.assertEqual(len(findings), 1)
        self.assertEqual(findings[0]["riskLevel"], "high")

    def test_format_findings_report_truncates(self):
        findings = [
            {
                "path": "a.py",
                "line": 1,
                "type": "email",
                "riskLevel": "medium",
                "detectionSource": "regex",
            },
            {
                "path": "b.py",
                "line": 2,
                "type": "ssn",
                "riskLevel": "high",
                "detectionSource": "regex",
            },
        ]
        report = precommit_scan.format_findings_report(findings, max_findings=1)
        self.assertIn("a.py:1", report)
        self.assertIn("... and 1 more finding(s)", report)


if __name__ == "__main__":
    unittest.main()
