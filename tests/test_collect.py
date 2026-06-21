"""
Tests — pipeline/collect.py
Covers: _compute_retention (pure function) and _query_with_retry (retry logic).
No DB or API calls — all network/DB paths are mocked.
"""
import sys
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

sys.path.insert(0, str(Path(__file__).parents[1]))

from googleapiclient.errors import HttpError

from channelos.pipeline.collect import _compute_retention, _query_with_retry


# ── _compute_retention ────────────────────────────────────────────────────────

class TestComputeRetention(unittest.TestCase):
    def test_normal_calculation(self):
        self.assertEqual(_compute_retention(15.0, 30.0), 50.0)

    def test_capped_at_300_percent(self):
        self.assertEqual(_compute_retention(120.0, 10.0), 300.0)

    def test_none_when_avg_view_sec_is_none(self):
        self.assertIsNone(_compute_retention(None, 30.0))

    def test_none_when_duration_is_none(self):
        self.assertIsNone(_compute_retention(15.0, None))

    def test_none_when_duration_is_zero(self):
        self.assertIsNone(_compute_retention(15.0, 0.0))

    def test_rounds_to_two_decimals(self):
        self.assertEqual(_compute_retention(10.0, 30.0), 33.33)

    def test_full_retention(self):
        self.assertEqual(_compute_retention(30.0, 30.0), 100.0)


# ── _query_with_retry ─────────────────────────────────────────────────────────

def _http_error(status: int) -> HttpError:
    resp = MagicMock()
    resp.status = status
    return HttpError(resp=resp, content=b"error")


class TestQueryWithRetry(unittest.TestCase):
    def test_returns_result_on_first_success(self):
        fn = MagicMock(return_value={"rows": [[1, 2, 3]]})
        result = _query_with_retry(fn, what="test")
        self.assertEqual(result, {"rows": [[1, 2, 3]]})
        fn.assert_called_once()

    def test_retries_on_429(self):
        err = _http_error(429)
        fn = MagicMock(side_effect=[err, err, {"rows": []}])
        sleep = MagicMock()
        result = _query_with_retry(fn, what="test", retries=3, _sleep=sleep)
        self.assertEqual(result, {"rows": []})
        self.assertEqual(fn.call_count, 3)
        self.assertEqual(sleep.call_count, 2)

    def test_retries_on_500(self):
        err = _http_error(500)
        fn = MagicMock(side_effect=[err, {"rows": []}])
        sleep = MagicMock()
        result = _query_with_retry(fn, what="test", retries=3, _sleep=sleep)
        self.assertEqual(result, {"rows": []})
        self.assertEqual(fn.call_count, 2)

    def test_no_retry_on_403(self):
        fn = MagicMock(side_effect=_http_error(403))
        with self.assertRaises(HttpError):
            _query_with_retry(fn, what="test")
        fn.assert_called_once()

    def test_no_retry_on_404(self):
        fn = MagicMock(side_effect=_http_error(404))
        with self.assertRaises(HttpError):
            _query_with_retry(fn, what="test")
        fn.assert_called_once()

    def test_raises_runtime_error_after_max_retries(self):
        fn = MagicMock(side_effect=_http_error(503))
        sleep = MagicMock()
        with self.assertRaises(RuntimeError):
            _query_with_retry(fn, what="test", retries=3, _sleep=sleep)
        self.assertEqual(fn.call_count, 3)

    def test_backoff_delays_are_exponential(self):
        fn = MagicMock(side_effect=_http_error(502))
        sleep = MagicMock()
        with self.assertRaises(RuntimeError):
            _query_with_retry(fn, what="test", retries=3, _sleep=sleep)
        delays = [c.args[0] for c in sleep.call_args_list]
        self.assertEqual(delays, [2, 4])  # 2**1, 2**2
