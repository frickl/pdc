import importlib.util
from pathlib import Path
import unittest

HERE = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("pdc", HERE / "pdc.py")
pdc = importlib.util.module_from_spec(spec)
spec.loader.exec_module(pdc)


class MatchingTests(unittest.TestCase):
    def test_substitution(self):
        self.assertTrue(pdc.edit_distance_one("gmajl.com", "gmail.com"))

    def test_insertion(self):
        self.assertTrue(pdc.edit_distance_one("gimail.com", "gmail.com"))

    def test_deletion(self):
        self.assertTrue(pdc.edit_distance_one("gmal.com", "gmail.com"))

    def test_adjacent_transposition(self):
        self.assertTrue(pdc.edit_distance_one("gmial.com", "gmail.com"))

    def test_tld_one_character_difference(self):
        self.assertTrue(pdc.edit_distance_one("kabelmail.co", "kabelmail.com"))

    def test_two_edits_not_matched(self):
        self.assertFalse(pdc.edit_distance_one("gmaill.co", "gmail.com"))


if __name__ == "__main__":
    unittest.main()
