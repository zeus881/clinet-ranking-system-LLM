import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch, MagicMock

from models.schemas import Company, RankedCompany
from output.writer import write_ranked_to_csv, write_ranked_to_json


class TestPhase5OutputPipeline(unittest.TestCase):
    def test_output_writers(self):
        items = [
            RankedCompany(
                company=Company(name="Acme", website="https://acme.com"),
                score=0.91234,
                summary="AI services",
            )
        ]
        with tempfile.TemporaryDirectory() as tmp:
            csv_path = str(Path(tmp) / "out.csv")
            json_path = str(Path(tmp) / "out.json")

            write_ranked_to_csv(items, csv_path)
            write_ranked_to_json(items, json_path)

            self.assertTrue(Path(csv_path).exists())
            payload = json.loads(Path(json_path).read_text(encoding="utf-8"))
            self.assertIsInstance(payload, list)
            # JSON writer uses "name" key (API normalizer maps it to company_name)
            self.assertEqual(payload[0]["name"], "Acme")
            self.assertIsInstance(payload[0]["products"], list)

    @patch("main.write_ranked_to_json")
    @patch("main.write_ranked_to_csv")
    @patch("main.rank_companies")
    @patch("main.extract_structured")
    @patch("main.crawl_company_website")
    @patch("main.load_companies")
    @patch("main.print_health_report")
    @patch("main.check_system_health")
    def test_run_pipeline(
        self,
        _mock_health,
        _mock_print,
        mock_load,
        mock_crawl,
        mock_extract,
        mock_rank,
        mock_csv,
        mock_json,
    ):
        from extraction.structured_extractor import StructuredProfile

        mock_load.return_value = [Company(name="Acme", website="https://acme.com")]
        mock_crawl.return_value = {
            "all": "Acme builds autonomous AI robots and drone systems for logistics automation. " * 20,
            "products": "",
            "services": "",
            "specifications": "",
            "quality": "GOOD",
        }
        mock_extract.return_value = StructuredProfile(
            products=["AcmeBot"],
            services=[],
            technologies=["Computer Vision"],
            industry="Robotics",
            use_cases=["warehouse automation"],
            confidence=0.75,
        )
        mock_rank.return_value = [
            RankedCompany(
                company=Company(name="Acme", website="https://acme.com"),
                score=1.0,
                summary="summary",
            )
        ]

        from main import run_pipeline
        run_pipeline(input_file="dummy.xlsx")

        mock_csv.assert_called_once()
        mock_json.assert_called_once()


if __name__ == "__main__":
    unittest.main()
