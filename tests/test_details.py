import unittest

from crs import details, load


class DetailsTest(unittest.TestCase):
    def test_education_for_software_developers(self):
        rows = details.education("15-1252.00")
        self.assertEqual(rows[0], ("Sarjana (S1/D4)", 85))
        self.assertTrue(all(percent >= 5 for _, percent in rows))

    def test_every_occupation_has_details_and_translated_labels(self):
        english = set(details.WORK_STYLE_LABELS)
        codes = load().codes
        # O*NET 31.0 has no education data for 9 of the 878 occupations; the page hides that section.
        self.assertGreaterEqual(sum(bool(details.education(code)) for code in codes), len(codes) - 9)
        for code in codes:
            styles = details.work_styles(code)
            self.assertEqual(len(styles), 5, code)
            self.assertFalse(set(styles) & (english - set(details.WORK_STYLE_LABELS.values())), code)

    def test_software_prefers_in_demand(self):
        names = details.software("15-1252.00")
        self.assertLessEqual(len(names), 12)
        self.assertIn("C++", details.software("15-1252.00", limit=200))
        self.assertEqual(details.software("00-0000.00"), [])


if __name__ == "__main__":
    unittest.main()
