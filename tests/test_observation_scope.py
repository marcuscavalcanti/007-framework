"""Empty-scope controls use synthetic collectors and never open native logs."""
from datetime import datetime, timezone
from pathlib import Path
import unittest
from unittest import mock

import local_activity
import observatory_history


class ObservationScopeTests(unittest.TestCase):
    def test_no_registered_projects_means_no_log_read_or_pricing_and_drops_cached_rows(self):
        collector = local_activity.ActivityCollector(pricer=mock.Mock())
        collector.pricer.quote.return_value = []
        collector.cursors[Path("/synthetic/old.jsonl")] = (None, 0, None)
        collector.unreadable.add(Path("/synthetic/old.jsonl"))
        with mock.patch.object(collector, "candidates", return_value=[]) as candidates:
            row = collector.collect([], datetime.now(timezone.utc))
        candidates.assert_not_called()
        collector.pricer.quote.assert_not_called()
        self.assertEqual(row["projects"], {})
        self.assertEqual(row["errors"], [])
        self.assertEqual(collector.cursors, {})
        self.assertEqual(collector.unreadable, set())

    def test_opted_out_observatory_does_not_enumerate_or_parse_sessions(self):
        collector = mock.Mock()
        collector.candidates.return_value = []
        self.assertEqual(observatory_history.snapshot(collector, [], set(), None), [])
        collector.candidates.assert_not_called()
        collector.parse.assert_not_called()

    def test_auto_discovery_remains_explicitly_available_with_no_listed_projects(self):
        collector = mock.Mock()
        collector.candidates.return_value = []
        self.assertEqual(observatory_history.snapshot(collector, [], set(), None, auto=True), [])
        collector.candidates.assert_called_once()

    def test_stale_enrollment_with_no_registered_match_does_not_read_logs(self):
        collector = mock.Mock()
        collector.candidates.return_value = []
        entries = [{"project_id": "other", "path": "/synthetic/other"}]
        self.assertEqual(observatory_history.snapshot(collector, entries, {"removed-project"}, None), [])
        collector.candidates.assert_not_called()
