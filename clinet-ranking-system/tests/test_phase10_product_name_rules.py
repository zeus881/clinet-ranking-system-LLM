import json
import unittest

from extraction.schema_extractor import extract_structured_company_info


class TestPhase10ProductNameRules(unittest.TestCase):
    def test_extracts_real_product_name_zoho_crm(self):
        text = "Zoho CRM helps manage leads and automate pipelines."
        structured = extract_structured_company_info(
            company_name="Zoho",
            website="https://zoho.com",
            cleaned_text=text,
        )
        products = json.loads(structured["products"] or "[]")
        names = [item.get("name", "") for item in products]
        self.assertIn("Zoho CRM", names)

    def test_rejects_generic_product_phrases(self):
        text = (
            "Our solutions improve outcomes. "
            "This platform provides services for teams. "
            "The technology supports growth."
        )
        structured = extract_structured_company_info(
            company_name="Generic Co",
            website="https://generic.com",
            cleaned_text=text,
        )
        products = json.loads(structured["products"] or "[]")
        names = [item.get("name", "").lower() for item in products]
        self.assertNotIn("our solutions", names)
        self.assertNotIn("this platform", names)
        self.assertNotIn("technology", names)

    def test_product_names_are_between_two_and_six_words(self):
        text = (
            "Acme Hyper Intelligent Workflow Automation Platform helps teams. "
            "CRM supports sales."
        )
        structured = extract_structured_company_info(
            company_name="Acme",
            website="https://acme.com",
            cleaned_text=text,
        )
        products = json.loads(structured["products"] or "[]")
        for item in products:
            tokens = item.get("name", "").split()
            self.assertGreaterEqual(len(tokens), 2)
            self.assertLessEqual(len(tokens), 6)


if __name__ == "__main__":
    unittest.main()
