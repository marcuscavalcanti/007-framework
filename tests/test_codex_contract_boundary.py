"""Structural accounting controls from the consolidated bee4188 review."""
from datetime import datetime, timedelta, timezone
import importlib
import itertools
from pathlib import Path
import sys
import unittest


NOW = datetime(2026, 8, 30, 15, tzinfo=timezone.utc)


def counters(prompt, output, **optional):
    return {"input_tokens": prompt, "output_tokens": output, "total_tokens": prompt + output, **optional}


class ContractBoundaryTests(unittest.TestCase):
    def session(self, observations, before=False):
        sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
        try:
            activity = importlib.import_module("local_activity")
        finally:
            sys.path.pop(0)
        log = activity.CodexLog()
        started = (NOW - timedelta(hours=48 if before else 1)).isoformat()
        log.feed({"type": "session_meta", "timestamp": started,
                  "payload": {"id": "structural-control", "cwd": "/synthetic", "timestamp": started}})
        log.feed({"type": "turn_context", "timestamp": started,
                  "payload": {"model": "gpt-5.6-sol", "effort": "xhigh"}})
        for hours, total, last in observations:
            info = {"total_token_usage": total}
            if last is not None:
                info["last_token_usage"] = last
            log.feed({"type": "event_msg", "timestamp": (NOW - timedelta(hours=hours)).isoformat(),
                      "payload": {"type": "token_count", "info": info}})
        return activity, log.result(NOW)

    def test_optional_corruption_preserves_known_primary_diagnostics(self):
        for optional in ({"reasoning_output_tokens": "unknown"}, {"reasoning_output_tokens": -1},
                         {"reasoning_output_tokens": True}, {"reasoning_output_tokens": None},
                         {"cached_input_tokens": None}):
            with self.subTest(optional=optional):
                activity, result = self.session([(0.5, counters(100, 20, **optional), None)])
                self.assertEqual(result["usage"]["total_tokens"], 120)
                self.assertEqual(result["usage"]["input_tokens"], 100)
                self.assertEqual(result["usage"]["output_tokens"], 20)
                self.assertFalse(result["usage"]["usage_complete"])
                self.assertIsNone(activity.pricing_request(result))

    def test_unreported_reasoning_stays_unavailable_without_losing_primary_price(self):
        activity, empty = self.session([])
        self.assertIsNone(empty["usage"]["reasoning_output_tokens"])
        self.assertFalse(empty["usage"]["usage_complete"])
        self.assertIsNone(activity.pricing_request(empty))
        for unreadable in (None, {}, {"input_tokens": False, "output_tokens": 20, "total_tokens": 20},
                           {"input_tokens": 100, "output_tokens": 20, "total_tokens": 119}):
            with self.subTest(unreadable_baseline=unreadable):
                activity, result = self.session([(25, unreadable, None)], before=True)
                self.assertFalse(result["usage"]["usage_complete"])
                self.assertIsNone(result["usage"]["reasoning_output_tokens"])
                self.assertIsNone(activity.pricing_request(result))
        activity, result = self.session([(25, counters(100, 20), None)], before=True)
        self.assertTrue(result["usage"]["usage_complete"])
        self.assertEqual(result["usage"]["reasoning_output_tokens"], 0)
        self.assertIsNotNone(activity.pricing_request(result))
        for optional, expected in (({}, None), ({"reasoning_output_tokens": 0}, 0)):
            with self.subTest(optional=optional):
                activity, result = self.session([(0.5, counters(100, 20, **optional), None)])
                self.assertEqual(result["usage"]["reasoning_output_tokens"], expected)
                self.assertTrue(result["usage"]["usage_complete"])
                self.assertIsNotNone(activity.pricing_request(result))
                self.assertEqual(activity.summarize([result], 24)["reasoning_output_tokens"], expected)

    def test_summary_preserves_optional_unavailability_beside_known_reasoning(self):
        activity, unknown = self.session([(0.5, counters(100, 20), None)])
        _, known = self.session([(0.5, counters(100, 20, reasoning_output_tokens=5), None)])
        summary = activity.summarize([unknown, known], 24)
        self.assertEqual(summary["tokens_total"], 240)
        self.assertIsNone(summary["reasoning_output_tokens"])
        self.assertEqual(summary["usage_incomplete_sessions"], 0)
        self.assertEqual(known["usage"]["reasoning_output_tokens"], 5)

    def test_reset_retains_known_subtotals_across_primary_representations(self):
        for last in (None, counters(100, 20)):
            with self.subTest(last=last):
                activity, result = self.session([(25, counters(100, 20), None),
                                                 (3, counters(200, 40), last),
                                                 (2, counters(0, 0), None),
                                                 (1, counters(100, 20), None)], before=True)
                self.assertEqual(result["usage"]["total_tokens"], 240)
                self.assertFalse(result["usage"]["usage_complete"])
                self.assertIsNone(activity.pricing_request(result))

    def test_internal_duplicate_constraints_are_validated_before_suppression(self):
        total = counters(10, 10, reasoning_output_tokens=10)
        for reasoning, complete in ((0, False), (5, True)):
            with self.subTest(subset_reasoning=reasoning):
                activity, result = self.session([(0.5, total, total),
                                                 (0.4, total, counters(5, 5, reasoning_output_tokens=reasoning))])
                self.assertEqual(result["usage"]["total_tokens"], 20)
                self.assertEqual(result["usage"]["usage_complete"], complete)
                self.assertEqual(activity.pricing_request(result) is not None, complete)
        for reasoning, complete in ((10, True), (11, False)):
            with self.subTest(cumulative_reasoning=reasoning):
                total = counters(10, 10, reasoning_output_tokens=reasoning)
                activity, result = self.session([(25, total, None), (1, total, None)], before=True)
                self.assertEqual(result["usage"]["usage_complete"], complete)
                self.assertEqual(activity.pricing_request(result) is not None, complete)

    def test_duplicate_optional_enrichment_preserves_subset_constraints(self):
        for lower, current, complete in ((5, 4, False), (5, 5, True), (0, 6, False), (0, 5, True)):
            for earlier in (False, True):
                with self.subTest(last_reasoning=lower, current=current, earlier=earlier):
                    observations = [(27, counters(10, 10), counters(5, 5))] if earlier else []
                    observations += [(25, counters(10, 10), counters(5, 5, reasoning_output_tokens=lower)),
                                     (1, counters(20, 20, reasoning_output_tokens=current),
                                      counters(10, 10, reasoning_output_tokens=0))]
                    activity, result = self.session(observations, before=True)
                    self.assertEqual(result["usage"]["usage_complete"], complete)
                    self.assertEqual(result["usage"]["total_tokens"], 20)
                    self.assertEqual(activity.pricing_request(result) is not None, complete)

    def test_optional_omission_does_not_change_duplicate_consumption_identity(self):
        first = counters(100, 20, reasoning_output_tokens=10)
        for optional, complete in (({}, True), ({"reasoning_output_tokens": 10}, True),
                                   ({"reasoning_output_tokens": 0}, False)):
            with self.subTest(optional=optional):
                activity, result = self.session([(0.5, first, first), (0.4, counters(100, 20, **optional), first)])
                self.assertEqual(result["usage"]["total_tokens"], 120)
                self.assertEqual(result["usage"]["usage_complete"], complete)
                self.assertEqual(activity.pricing_request(result) is not None, complete)

    def test_duplicate_representations_match_independent_reasoning_subsets(self):
        for output in range(3):
            last_options = [(None, None)] + [({}, None)]
            last_options += [({"reasoning_output_tokens": reasoning}, None) for reasoning in range(output + 2)]
            for generated in range(output + 1):
                last_options.append((counters(1, generated), generated))
                last_options += [(counters(1, generated, reasoning_output_tokens=reasoning), generated)
                                 for reasoning in range(generated + 2)]
            for initial, current, (last, last_output) in itertools.product(
                    (None, *range(output + 1)), (None, *range(output + 2)), last_options):
                with self.subTest(output=output, initial=initial, current=current, last=last):
                    feasible = set(range(output + 1)) if initial is None else {initial}
                    if current is not None:
                        feasible &= {current}
                    last_reasoning = last.get("reasoning_output_tokens") if last else None
                    if last_reasoning is not None:
                        feasible = {r for r in feasible if r >= last_reasoning and (
                            last_output is None or last_reasoning <= last_output
                            and r - last_reasoning <= output - last_output)}
                    seen = any(value is not None for value in (initial, current, last_reasoning))
                    complete = bool(feasible) and (not seen or len(feasible) == 1)
                    first = counters(2, output, **({} if initial is None else {"reasoning_output_tokens": initial}))
                    second = counters(2, output, **({} if current is None else {"reasoning_output_tokens": current}))
                    activity, result = self.session([(0.5, first, first), (0.4, second, last)])
                    self.assertEqual(result["usage"]["total_tokens"], 2 + output)
                    self.assertEqual(result["usage"]["usage_complete"], complete)
                    self.assertEqual(activity.pricing_request(result) is not None, complete)
                    if complete:
                        expected = next(iter(feasible)) if seen or output == 0 else None
                        self.assertEqual(result["usage"]["reasoning_output_tokens"], expected)


if __name__ == "__main__":
    unittest.main()
