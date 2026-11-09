import unittest
from datetime import datetime

from emporio_agent.store_hours import STORE_TIMEZONE, describe_status, is_open, next_opening


def at(year, month, day, hour, minute=0):
    return datetime(year, month, day, hour, minute, tzinfo=STORE_TIMEZONE)


MONDAY = (2026, 11, 9)
FRIDAY = (2026, 11, 13)
SATURDAY = (2026, 11, 14)
SUNDAY = (2026, 11, 15)


class IsOpenTest(unittest.TestCase):
    def test_weekdays(self):
        self.assertFalse(is_open(at(*MONDAY, 8, 59)))
        self.assertTrue(is_open(at(*MONDAY, 9)))
        self.assertTrue(is_open(at(*MONDAY, 17, 59)))
        self.assertFalse(is_open(at(*MONDAY, 18)))

    def test_saturday_closes_early(self):
        self.assertTrue(is_open(at(*SATURDAY, 12, 59)))
        self.assertFalse(is_open(at(*SATURDAY, 13)))

    def test_sunday_is_closed(self):
        self.assertFalse(is_open(at(*SUNDAY, 10)))


class NextOpeningTest(unittest.TestCase):
    def test_before_opening_is_the_same_day(self):
        self.assertEqual(next_opening(at(*MONDAY, 7)), at(*MONDAY, 9))

    def test_after_closing_is_the_next_day(self):
        self.assertEqual(next_opening(at(*MONDAY, 20)), at(2026, 11, 10, 9))

    def test_friday_night_is_saturday(self):
        self.assertEqual(next_opening(at(*FRIDAY, 19)), at(*SATURDAY, 9))

    def test_saturday_afternoon_skips_sunday(self):
        self.assertEqual(next_opening(at(*SATURDAY, 14)), at(2026, 11, 16, 9))


class DescribeStatusTest(unittest.TestCase):
    def test_open(self):
        self.assertIn("OPEN until 18:00", describe_status(at(*MONDAY, 10)))

    def test_closed_gives_the_return_time(self):
        status = describe_status(at(*SUNDAY, 10))
        self.assertIn("CLOSED", status)
        self.assertIn("Monday, 2026-11-16 at 09:00", status)


if __name__ == "__main__":
    unittest.main()
