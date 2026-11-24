#!/usr/bin/env python3
import datetime
import unittest

from repowise_freshness_check import evaluate

NOW = datetime.datetime(2026, 11, 17, 12, 0, tzinfo=datetime.timezone.utc)


def status(fetched_at, product="a", harness="b"):
    return {"fetched_at": fetched_at, "product": product, "harness": harness}


class RepowiseFreshnessTests(unittest.TestCase):
    def test_fresh_and_matching(self):
        data = status(NOW.isoformat())
        self.assertEqual(evaluate(data, {"product": "a", "harness": "b"}, NOW, 1800), [])

    def test_rejects_old_status(self):
        data = status((NOW - datetime.timedelta(hours=1)).isoformat())
        errors = evaluate(data, {"product": "a", "harness": "b"}, NOW, 1800)
        self.assertTrue(any("older than" in error for error in errors))

    def test_rejects_drifted_checkout(self):
        data = status(NOW.isoformat())
        errors = evaluate(data, {"product": "old", "harness": "b"}, NOW, 1800)
        self.assertTrue(any("product live=old" in error for error in errors))

    def test_rejects_missing_status(self):
        self.assertEqual(evaluate(None, {}, NOW, 1800), ["missing github-main.json"])


if __name__ == "__main__":
    unittest.main()
