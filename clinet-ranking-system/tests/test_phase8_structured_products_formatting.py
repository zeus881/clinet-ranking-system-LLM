import json
import unittest

from extraction.schema_extractor import extract_structured_company_info


class TestPhase8StructuredProductsFormatting(unittest.TestCase):
    def test_products_are_structured_json(self):
        text = (
            "Zoho CRM helps manage leads and supports automation. "
            "AI Test Automation platform includes smart workflows and reporting. "
            "Analytics Platform provides data-driven insights and dashboards."
        )
        structured = extract_structured_company_info(
            company_name="Zoho",
            website="https://zoho.com",
            cleaned_text=text,
        )
        products_raw = structured["products"]
        self.assertIsNotNone(products_raw)
        products = json.loads(products_raw or "[]")
        self.assertTrue(isinstance(products, list))
        self.assertGreaterEqual(len(products), 2)
        self.assertLessEqual(len(products), 6)
        self.assertTrue(all("name" in item and "specifications" in item for item in products))

    def test_specifications_are_short_and_not_paragraphs(self):
        text = (
            "Zoho CRM helps manage leads and supports automation in teams across regions. "
            "Zoho CRM helps manage leads and supports automation in teams across regions. "
            "Analytics Platform provides data-driven insights."
        )
        structured = extract_structured_company_info(
            company_name="Zoho",
            website="https://zoho.com",
            cleaned_text=text,
        )
        products = json.loads(structured["products"] or "[]")
        for item in products:
            specs = item.get("specifications", "")
            self.assertLessEqual(len(specs.split()), 20)
            self.assertLessEqual(len(specs), 140)

    def test_no_more_than_six_products(self):
        text = " ".join(
            [
                "Alpha CRM helps manage leads.",
                "Beta Platform supports automation.",
                "Gamma Solution includes analytics.",
                "Delta Service enables reporting.",
                "Epsilon Suite offers workflows.",
                "Zeta Platform provides monitoring.",
                "Eta Solution powers integrations.",
            ]
        )
        structured = extract_structured_company_info(
            company_name="Acme",
            website="https://acme.com",
            cleaned_text=text,
        )
        products = json.loads(structured["products"] or "[]")
        self.assertLessEqual(len(products), 6)

    def test_no_duplicate_products_and_no_repeated_spec_chunks(self):
        text = (
            "Zoho CRM helps manage leads and supports automation. "
            "Zoho CRM helps manage leads and supports automation. "
            "Zoho CRM helps manage leads and supports automation."
        )
        structured = extract_structured_company_info(
            company_name="Zoho",
            website="https://zoho.com",
            cleaned_text=text,
        )
        products = json.loads(structured["products"] or "[]")
        names = [item.get("name", "") for item in products]
        self.assertEqual(len(names), len(set(name.lower() for name in names)))
        if products:
            specs = products[0].get("specifications", "")
            chunks = [chunk.strip().lower() for chunk in specs.split(",") if chunk.strip()]
            self.assertEqual(len(chunks), len(set(chunks)))


if __name__ == "__main__":
    unittest.main()
