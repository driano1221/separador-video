import unittest

from app.ui_main_preview import parse_clock


class UiMainScreenTest(unittest.TestCase):
    def test_clock_parser_requires_complete_valid_time(self):
        self.assertEqual(parse_clock("01:12:30"), 4350.0)
        for invalid in ("12:30", "00:75:00", "texto"):
            with self.assertRaises(ValueError):
                parse_clock(invalid)


if __name__ == "__main__":
    unittest.main()
