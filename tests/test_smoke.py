import csv
import unittest

from emporio_agent import cli
from emporio_agent.config import CSV_TABLES, DATA_DIR, POLICIES_PDF


class SkeletonTest(unittest.TestCase):
    def test_cli_is_importable(self):
        self.assertTrue(callable(cli.main))

    def test_data_files_are_present_and_readable(self):
        self.assertTrue(POLICIES_PDF.is_file())
        for table in CSV_TABLES:
            with open(DATA_DIR / f"{table}.csv", encoding="utf-8-sig", newline="") as f:
                self.assertGreater(len(list(csv.DictReader(f))), 0, table)


if __name__ == "__main__":
    unittest.main()
