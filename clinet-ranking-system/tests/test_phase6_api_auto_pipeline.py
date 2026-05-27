import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import pandas as pd

from api import app as api_module


class TestPhase6ApiAutoPipeline(unittest.TestCase):
    def setUp(self):
        self.client = api_module.app.test_client()

    def _write_csv(self, path: Path, rows: list[dict]) -> None:
        pd.DataFrame(rows).to_csv(path, index=False)

    def _sample_rows(self):
        return [
            {
                "company_name": "Acme",
                "website": "https://acme.com",
                "industry": "Software",
                "products": '[{"name":"Acme CRM","specifications":"Lead management"}]',
                "product_specifications": "Lead management",
                "technologies": "AI",
                "price_range": "Quoted",
                "contact_email": "hello@acme.com",
                "phone": "123",
                "address": "Earth",
                "description": "desc",
                "summary": "summary",
                "score": 0.5,
            }
        ]

    def test_companies_returns_success_when_data_exists(self):
        with tempfile.TemporaryDirectory() as tmp:
            csv_path = Path(tmp) / "ranked_companies.csv"
            json_path = Path(tmp) / "ranked_companies.json"
            self._write_csv(csv_path, self._sample_rows())

            with patch("api.app.CSV_PATH", csv_path), \
                 patch("api.app.JSON_PATH", json_path), \
                 patch("api.app.is_data_stale", return_value=False):
                response = self.client.get("/companies")

            self.assertEqual(response.status_code, 200)
            self.assertEqual(response.get_json()["status"], "success")

    def test_companies_starts_pipeline_when_no_data(self):
        with tempfile.TemporaryDirectory() as tmp:
            csv_path = Path(tmp) / "ranked_companies.csv"
            json_path = Path(tmp) / "ranked_companies.json"

            with patch("api.app.CSV_PATH", csv_path), \
                 patch("api.app.JSON_PATH", json_path), \
                 patch("api.app.run_pipeline_async") as mock_run:
                response = self.client.get("/companies")

            self.assertIn(response.status_code, (200, 202))
            mock_run.assert_called_once()

    def test_companies_returns_valid_json(self):
        with tempfile.TemporaryDirectory() as tmp:
            csv_path = Path(tmp) / "ranked_companies.csv"
            json_path = Path(tmp) / "ranked_companies.json"
            self._write_csv(csv_path, self._sample_rows())

            with patch("api.app.CSV_PATH", csv_path), \
                 patch("api.app.JSON_PATH", json_path), \
                 patch("api.app.is_data_stale", return_value=False):
                response = self.client.get("/companies")
                payload = response.get_json()

            self.assertEqual(response.status_code, 200)
            self.assertEqual(payload["status"], "success")
            self.assertIsInstance(payload["data"], list)

    def test_refresh_starts_pipeline(self):
        with patch("api.app.run_pipeline_async") as mock_run:
            mock_run.return_value = True
            response = self.client.get("/refresh")
            payload = response.get_json()
            self.assertEqual(response.status_code, 200)
            self.assertEqual(payload["status"], "success")
            mock_run.assert_called_once()

    def test_status_endpoint(self):
        response = self.client.get("/status")
        payload = response.get_json()
        self.assertEqual(response.status_code, 200)
        self.assertIn("running", payload)


if __name__ == "__main__":
    unittest.main()
