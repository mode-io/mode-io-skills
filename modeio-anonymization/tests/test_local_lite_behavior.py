#!/usr/bin/env python3

import sys
import unittest
from pathlib import Path
from unittest.mock import patch

SCRIPTS_DIR = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(SCRIPTS_DIR))

import anonymize  # noqa: E402
import detect_local  # noqa: E402


class TestLocalLiteBehavior(unittest.TestCase):
    def test_lite_mode_uses_local_detector_without_network(self):
        text = "Email: alice@example.com, Phone: 415-555-1234"

        with patch("anonymize.requests.post") as mock_post:
            result = anonymize.anonymize(text, level="lite")

        mock_post.assert_not_called()
        self.assertTrue(result.get("success"))

        data = result.get("data", {})
        self.assertEqual(data.get("mode"), "local-regex")
        self.assertTrue(data.get("hasPII"))

        anonymized = data.get("anonymizedContent", "")
        self.assertIn("[EMAIL_1]", anonymized)
        self.assertIn("[PHONE_1]", anonymized)

    def test_us_phone_formats_are_detected(self):
        samples = [
            "415-555-1234",
            "(415) 555-1234",
            "415.555.1234",
            "415 555 1234",
            "+1 415 555 1234",
            "4155551234",
            "+1 (415) 555-1234 ext 22",
        ]

        for sample in samples:
            with self.subTest(sample=sample):
                result = detect_local.detect_sensitive_local(f"Contact: {sample}")
                phone_items = [item for item in result["items"] if item["type"] == "phone"]
                self.assertGreaterEqual(len(phone_items), 1)
                self.assertIn("[PHONE_1]", result["sanitizedText"])

    def test_non_phone_lookalike_is_not_detected_as_phone(self):
        text = "Order number 415-555-12345 should remain unchanged."
        result = detect_local.detect_sensitive_local(text)

        phone_items = [item for item in result["items"] if item["type"] == "phone"]
        self.assertEqual(phone_items, [])

    def test_ssn_format_is_not_misclassified_as_phone(self):
        text = "SSN: 123-45-6789"
        result = detect_local.detect_sensitive_local(text)

        phone_items = [item for item in result["items"] if item["type"] == "phone"]
        ssn_items = [item for item in result["items"] if item["type"] == "ssn"]

        self.assertEqual(phone_items, [])
        self.assertGreaterEqual(len(ssn_items), 1)


if __name__ == "__main__":
    unittest.main()
