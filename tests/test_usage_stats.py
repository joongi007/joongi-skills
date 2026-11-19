"""Opt-in aggregate usage must remain bounded and never retain request payloads."""

import tempfile
import unittest
from datetime import date, timedelta
from pathlib import Path
from unittest.mock import patch

from joongi_hub.errors import RpcError
from joongi_hub.usage_stats import UsageStats


class UsageStatsTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name).resolve()
        self.stats = UsageStats(self.root / "state")

    def test_disabled_by_default_does_not_create_files(self):
        self.assertFalse(self.stats.record("search", "all", "success", 10))
        self.assertEqual(self.stats.snapshot()["entries"], [])
        self.assertFalse((self.root / "state").exists())

    def test_aggregates_known_identities_without_payload_fields_and_survives_restart(self):
        self.stats.record("call", "notion__fetch", "success", 12, enabled=True)
        self.stats.record("call", "notion__fetch", "success", 19, enabled=True)
        self.stats.record("call", "notion__fetch", "error", 7, enabled=True)
        result = UsageStats(self.root / "state").snapshot(enabled=True)
        self.assertEqual(result["total_count"], 3)
        row = next(item for item in result["entries"] if item["outcome"] == "success")
        self.assertEqual(row["count"], 2)
        self.assertEqual(row["total_duration_ms"], 31)
        self.assertEqual(row["max_duration_ms"], 19)
        self.assertEqual(
            set(row),
            {"day", "kind", "name", "outcome", "count", "total_duration_ms", "max_duration_ms"},
        )
        other = UsageStats(self.root / "another-profile", enabled=True)
        self.assertEqual(other.snapshot()["total_count"], 0)

    def test_untrusted_paths_payloads_and_invalid_timings_are_discarded(self):
        self.stats.set_enabled(True)
        invalid = [
            ("call", "/private/account/token", "success", 1),
            ("query", "credit-card-query", "success", 1),
            ("call", "notion__fetch", "secret error details", 1),
            ("call", "notion__fetch", "success", float("inf")),
            ("call", "notion__fetch", "success", -1),
            ("call", "notion__fetch", "success", True),
            ({}, "notion__fetch", "success", 1),
            ("call", "notion__fetch", {}, 1),
        ]
        for values in invalid:
            self.assertFalse(self.stats.record(*values))
        self.assertFalse(self.stats.path.exists())

    def test_retention_and_key_count_remove_old_records(self):
        day = date(2026, 11, 19)
        self.stats.set_enabled(True)
        with patch("joongi_hub.usage_stats.today", return_value=day - timedelta(days=30)):
            self.stats.record("tool", "old_tool", "success", 1)
        with (
            patch("joongi_hub.usage_stats.today", return_value=day),
            patch("joongi_hub.usage_stats.MAX_KEYS", 3),
        ):
            for number in range(5):
                self.stats.record("tool", f"recent_{number}", "success", number)
            snapshot = self.stats.snapshot()
        self.assertEqual(len(snapshot["entries"]), 3)
        self.assertEqual(
            {row["name"] for row in snapshot["entries"]}, {"recent_2", "recent_3", "recent_4"}
        )
        self.assertEqual(snapshot["total_count"], 3)
        with patch("joongi_hub.usage_stats.today", return_value=day + timedelta(days=31)):
            self.assertEqual(self.stats.snapshot()["entries"], [])

    def test_disable_stops_recording_without_erasing_and_reset_clears_saved_counts(self):
        self.stats.record("skill", "usual-korean", "success", enabled=True)
        self.stats.set_enabled(False)
        self.assertFalse(self.stats.record("skill", "usual-korean", "success"))
        self.assertEqual(self.stats.snapshot()["total_count"], 1)
        self.assertEqual(self.stats.reset()["entries"], [])
        self.assertNotIn(b"usual-korean", self.stats.path.read_bytes())

    def test_corrupt_and_symlinked_databases_fail_closed(self):
        self.stats.directory.mkdir()
        self.stats.path.write_bytes(b"not sqlite")
        with self.assertRaises(RpcError):
            self.stats.snapshot()
        self.stats.path.unlink()
        target = self.root / "keep"
        target.write_text("keep")
        try:
            self.stats.path.symlink_to(target)
        except OSError:
            self.skipTest("Symlink creation is unavailable")
        with self.assertRaises(RpcError):
            self.stats.record("skill", "usual-korean", "success", enabled=True)
        self.assertEqual(target.read_text(), "keep")
