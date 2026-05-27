import unittest
from unittest.mock import patch

import pandas as pd

from health.health_check import check_system_health
from input.loader import load_companies


class TestPhase1InputHealth(unittest.TestCase):
    @patch("input.loader.Path.exists", return_value=True)
    @patch("input.loader.pd.read_excel")
    def test_load_companies_valid(self, mock_read_excel, _mock_exists):
        mock_read_excel.return_value = pd.DataFrame(
            {"Company": ["Acme"], "Website": ["https://acme.com"]}
        )
        companies = load_companies("dummy.xlsx")
        self.assertEqual(len(companies), 1)
        self.assertEqual(companies[0].name, "Acme")

    @patch("input.loader.Path.exists", return_value=True)
    @patch("input.loader.pd.read_excel")
    def test_load_companies_accepts_company_name_header(self, mock_read_excel, _mock_exists):
        mock_read_excel.return_value = pd.DataFrame(
            {"Company Name": ["Acme"], "Website": ["https://acme.com"]}
        )
        companies = load_companies("dummy.xlsx")
        self.assertEqual(len(companies), 1)
        self.assertEqual(companies[0].name, "Acme")

    @patch("input.loader.Path.exists", return_value=True)
    @patch("input.loader.pd.read_excel")
    def test_load_companies_invalid_columns(self, mock_read_excel, _mock_exists):
        mock_read_excel.return_value = pd.DataFrame({"Name": ["Acme"]})
        with self.assertRaises(ValueError):
            load_companies("dummy.xlsx")

    @patch("input.loader.Path.exists", return_value=True)
    @patch("input.loader.pd.read_excel")
    def test_load_companies_deduplicates_normalized_website(self, mock_read_excel, _mock_exists):
        mock_read_excel.return_value = pd.DataFrame(
            {
                "Company": ["Acme", "Acme"],
                "Website": ["https://www.acme.com", "http://acme.com/path"],
            }
        )
        companies = load_companies("dummy.xlsx")
        self.assertEqual(len(companies), 1)

    @patch("health.health_check.requests.get")
    @patch("health.health_check.pd.read_excel")
    @patch("health.health_check.Path.exists", return_value=True)
    def test_health_report(self, _mock_exists, mock_read_excel, mock_get):
        mock_read_excel.return_value = pd.DataFrame({"Company": ["A", "B"]})
        mock_get.return_value.status_code = 200
        report = check_system_health("dummy.xlsx")
        self.assertTrue(report.input_file_exists)
        self.assertTrue(report.spreadsheet_readable)
        self.assertEqual(report.company_count, 2)
        self.assertTrue(report.internet_connectivity)


if __name__ == "__main__":
    unittest.main()
