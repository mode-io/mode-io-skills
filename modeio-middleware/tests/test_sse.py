#!/usr/bin/env python3

import sys
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
PACKAGE_ROOT = REPO_ROOT / "modeio-middleware"

sys.path.insert(0, str(PACKAGE_ROOT))

from modeio_middleware.core.sse import iter_sse_events, serialize_sse_event  # noqa: E402


class TestSseHelpers(unittest.TestCase):
    def test_iter_sse_events_parses_multiline_json_event(self):
        raw_lines = [
            b"event: response.delta",
            b"id: evt-1",
            b"data: {\"delta\":",
            b"data: \"hello\"}",
            b"",
        ]

        events = list(iter_sse_events(raw_lines))

        self.assertEqual(len(events), 1)
        event = events[0]
        self.assertEqual(event["event_name"], "response.delta")
        self.assertEqual(event["event_id"], "evt-1")
        self.assertEqual(event["data_type"], "json")
        self.assertEqual(event["payload"]["delta"], "hello")

    def test_serialize_sse_event_preserves_metadata_and_done_marker(self):
        payload = serialize_sse_event(
            {
                "event_name": "response.completed",
                "event_id": "evt-2",
                "retry": "1000",
                "data_type": "done",
            }
        ).decode("utf-8")

        self.assertIn("event: response.completed", payload)
        self.assertIn("id: evt-2", payload)
        self.assertIn("retry: 1000", payload)
        self.assertIn("data: [DONE]", payload)
        self.assertTrue(payload.endswith("\n\n"))


if __name__ == "__main__":
    unittest.main()
