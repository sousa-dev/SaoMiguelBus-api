from django.test import SimpleTestCase

from mcp_server.validation import parse_day, parse_start


class ValidationTests(SimpleTestCase):
    def test_parse_day_accepts_day_types_and_iso_dates(self):
        self.assertEqual(parse_day('weekday'), 'weekday')
        self.assertEqual(parse_day('saturday'), 'saturday')
        self.assertEqual(parse_day('sunday'), 'sunday')
        self.assertEqual(parse_day('2026-09-14'), '2026-09-14')

    def test_parse_day_rejects_unknown_values(self):
        with self.assertRaises(ValueError):
            parse_day('tomorrow')

    def test_parse_start_accepts_zero_padded_24_hour_times(self):
        self.assertEqual(parse_start('09:05'), '09:05')
        self.assertEqual(parse_start('23:59'), '23:59')

    def test_parse_start_rejects_invalid_times(self):
        for value in ('9:05', '24:00', '12:60', 'noon'):
            with self.subTest(value=value), self.assertRaises(ValueError):
                parse_start(value)