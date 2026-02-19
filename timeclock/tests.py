from datetime import datetime

from django.test import SimpleTestCase
from django.utils import timezone

from .services import compute_day_total, format_hhmm, format_punch_time


class TimeSummaryServicesTests(SimpleTestCase):
    def _local_dt(self, year, month, day, hour, minute, second=0):
        naive = datetime(year, month, day, hour, minute, second)
        return timezone.make_aware(naive, timezone.get_current_timezone())

    def test_four_punches_should_total_eight_minutes_and_complete(self):
        punches = [
            self._local_dt(2026, 2, 19, 20, 59),
            self._local_dt(2026, 2, 19, 21, 2),
            self._local_dt(2026, 2, 19, 21, 6),
            self._local_dt(2026, 2, 19, 21, 11),
        ]
        total_seconds, is_incomplete = compute_day_total(punches)
        self.assertEqual(total_seconds, 8 * 60)
        self.assertEqual(format_hhmm(total_seconds), "00:08")
        self.assertFalse(is_incomplete)

    def test_three_punches_should_count_first_pair_and_mark_incomplete(self):
        punches = [
            self._local_dt(2026, 2, 19, 9, 0),
            self._local_dt(2026, 2, 19, 9, 45),
            self._local_dt(2026, 2, 19, 10, 30),
        ]
        total_seconds, is_incomplete = compute_day_total(punches)
        self.assertEqual(total_seconds, 45 * 60)
        self.assertEqual(format_hhmm(total_seconds), "00:45")
        self.assertTrue(is_incomplete)

    def test_two_punches_should_compute_exact_difference(self):
        punches = [
            self._local_dt(2026, 2, 19, 8, 10),
            self._local_dt(2026, 2, 19, 12, 25),
        ]
        total_seconds, is_incomplete = compute_day_total(punches)
        self.assertEqual(total_seconds, (4 * 60 + 15) * 60)
        self.assertEqual(format_hhmm(total_seconds), "04:15")
        self.assertFalse(is_incomplete)

    def test_zero_punches_should_return_zero_time(self):
        total_seconds, is_incomplete = compute_day_total([])
        self.assertEqual(total_seconds, 0)
        self.assertEqual(format_hhmm(total_seconds), "00:00")
        self.assertFalse(is_incomplete)

    def test_format_punch_time_should_hide_seconds(self):
        ts = self._local_dt(2026, 2, 19, 20, 59, 25)
        self.assertEqual(format_punch_time(ts), "20:59")
