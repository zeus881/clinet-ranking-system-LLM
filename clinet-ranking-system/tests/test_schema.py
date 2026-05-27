import csv
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import pandas as pd

from input.loader import load_companies
from models.schemas import Company, RankedCompany
from output.writer import write_ranked_to_csv, write_ranked_to_json


class TestSchemaContract(unittest.TestCase):
    def test_json_keys_and_score_type(self):
        item = RankedCompany(
            company=Company(name="Sky AI Labs", website="https://skyailabs.com"),
            score=0.87,
            summary="Summary",
            products='[{"name":"UAV inspection drones","specifications":"Drone-based inspection"}]',
            technologies="Computer Vision, Edge AI",
        )
        with tempfile.TemporaryDirectory() as tmp:
            path = str(Path(tmp) / "out.json")
            write_ranked_to_json([item], path)
            payload = json.loads(Path(path).read_text(encoding="utf-8"))

        row = payload[0]
        # Current JSON schema keys
        expected_keys = {
            "name", "website", "score", "category", "breakdown", "confidence",
            "industry", "products", "services", "technologies", "use_cases",
            "product_specifications", "price_range", "contact_email", "phone",
            "summary", "recommended_products", "reason",
        }
        self.assertEqual(set(row.keys()), expected_keys)
        self.assertIsInstance(row["score"], float)
        # JSON writer stores products as list of strings (names only)
        self.assertIsInstance(row["products"], list)
        self.assertTrue(row["products"][0])

    def test_csv_stores_products_as_json_string(self):
        item = RankedCompany(
            company=Company(name="Acme", website="https://acme.com"),
            score=0.9,
            summary="summary",
            products='[{"name":"Acme CRM","specifications":"Lead automation"}]',
        )
        with tempfile.TemporaryDirectory() as tmp:
            csv_path = str(Path(tmp) / "out.csv")
            write_ranked_to_csv([item], csv_path)
            with Path(csv_path).open("r", encoding="utf-8", newline="") as f:
                row = next(csv.DictReader(f))

        parsed = json.loads(row["products"])
        self.assertIsInstance(parsed, list)
        self.assertEqual(parsed[0]["name"], "Acme CRM")

    def test_duplicate_handling(self):
        with patch("input.loader.Path.exists", return_value=True), patch(
            "input.loader.pd.read_excel"
        ) as mock_read_excel:
            mock_read_excel.return_value = pd.DataFrame(
                {
                    "Company": ["Acme", "Acme", "Acme"],
                    "Website": [
                        "https://www.acme.com",
                        "http://acme.com/",
                        "https://acme.com/products",
                    ],
                }
            )
            companies = load_companies("dummy.xlsx")
            self.assertEqual(len(companies), 1)

    def test_null_policy_consistency(self):
        item = RankedCompany(
            company=Company(name="Acme", website="https://acme.com"),
            score=1.0,
            summary="summary",
        )
        with tempfile.TemporaryDirectory() as tmp:
            csv_path = str(Path(tmp) / "out.csv")
            json_path = str(Path(tmp) / "out.json")
            write_ranked_to_csv([item], csv_path)
            write_ranked_to_json([item], json_path)

            with Path(csv_path).open("r", encoding="utf-8", newline="") as f:
                row = next(csv.DictReader(f))
            payload = json.loads(Path(json_path).read_text(encoding="utf-8"))

        self.assertEqual(row["industry"], "")
        self.assertIsNone(payload[0]["industry"])


if __name__ == "__main__":
    unittest.main()
