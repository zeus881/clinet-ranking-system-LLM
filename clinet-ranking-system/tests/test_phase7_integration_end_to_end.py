import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import pandas as pd

from api import app as api_module
from extraction.structured_extractor import StructuredProfile
from main import run_pipeline
from models.schemas import Company


class TestPhase7IntegrationEndToEnd(unittest.TestCase):
    @patch("main.print_health_report")
    @patch("main.check_system_health")
    @patch("main.load_companies")
    @patch("main.extract_structured")
    @patch("main.crawl_company_website")
    @patch("main.summarize_text")
    def test_pipeline_to_api_end_to_end_without_fake_fallback(
        self,
        mock_summarize,
        mock_crawl,
        mock_extract,
        mock_load_companies,
        _mock_health,
        _mock_print,
    ):
        long_text = (
            "Zoho CRM is a customer relationship management platform. "
            "It supports sales automation and lead management workflows. "
            "Zoho CRM platform provides service integration and analytics. "
        ) * 10  # ensure >= MIN_TEXT_CHARS

        mock_load_companies.return_value = [
            Company(name="Zoho Corporation", website="https://www.zoho.com")
        ]
        # Use current crawler return format
        mock_crawl.return_value = {
            "all": long_text,
            "products": "Zoho CRM product page",
            "services": "",
            "specifications": "",
            "quality": "GOOD",
        }
        mock_extract.return_value = StructuredProfile(
            products=["Zoho CRM"],
            services=[],
            technologies=["AI", "Automation"],
            industry="CRM Software",
            use_cases=["lead management", "sales automation"],
            confidence=0.80,
        )
        mock_summarize.return_value = "Zoho CRM helps manage leads and supports automation."

        with tempfile.TemporaryDirectory() as tmp:
            csv_out = Path(tmp) / "ranked_companies.csv"
            json_out = Path(tmp) / "ranked_companies.json"
            run_pipeline(
                input_file="unused.xlsx",
                csv_output=str(csv_out),
                json_output=str(json_out),
            )

            self.assertTrue(csv_out.exists())
            self.assertTrue(json_out.exists())

            frame = pd.read_csv(csv_out)
            self.assertGreater(len(frame), 0)
            first = frame.iloc[0]
            self.assertTrue(str(first.get("products", "")).strip())

            structured_products = json.loads(str(first.get("products", "[]")))
            self.assertIsInstance(structured_products, list)
            self.assertTrue(structured_products)

            client = api_module.app.test_client()
            with patch("api.app.JSON_PATH", json_out), \
                 patch("api.app.CSV_PATH", csv_out), \
                 patch("api.app.is_data_stale", return_value=False):
                response = client.get("/companies")

            payload = response.get_json()
            self.assertEqual(response.status_code, 200)
            self.assertEqual(payload["status"], "success")
            self.assertIsInstance(payload["data"], list)
            self.assertGreater(len(payload["data"]), 0)

            row = payload["data"][0]
            self.assertEqual(row["company_name"], "Zoho Corporation")
            self.assertIsInstance(row["products"], list)
            self.assertTrue(row["products"])


if __name__ == "__main__":
    unittest.main()
