import unittest
import json

from extraction.schema_extractor import extract_structured_company_info


class TestPhase3StructuredProductExtraction(unittest.TestCase):
    def test_extracts_product_and_specification_from_simple_text(self):
        text = "Zoho CRM helps manage leads. It supports automation."
        structured = extract_structured_company_info(
            company_name="Zoho",
            website="https://zoho.com",
            cleaned_text=text,
        )

        products = json.loads(structured["products"] or "[]")
        names = [item.get("name", "") for item in products]
        self.assertIn("Zoho CRM", names)
        specs = " ".join(item.get("specifications", "") for item in products)
        self.assertIn("manage leads", specs.lower())
        self.assertIn("automation", specs.lower())

    def test_returns_empty_product_fields_when_no_product_signal(self):
        text = "We are a company focused on long-term customer success and trust."
        structured = extract_structured_company_info(
            company_name="Acme",
            website="https://acme.com",
            cleaned_text=text,
        )

        self.assertIsNone(structured["products"])
        self.assertIsNone(structured["product_specifications"])

    def test_discards_generic_non_specific_product_names(self):
        text = "The platform supports teams. This solution includes workflow automation."
        structured = extract_structured_company_info(
            company_name="Generic Inc",
            website="https://generic.com",
            cleaned_text=text,
        )

        products = structured["products"] or ""
        self.assertNotIn("The", products)
        self.assertNotIn("This", products)

    def test_maps_multiple_products_with_nearby_specs(self):
        text = (
            "Zoho CRM helps manage leads. It supports automation. "
            "Analytics Platform provides data-driven insights. It offers custom dashboards."
        )
        structured = extract_structured_company_info(
            company_name="Zoho",
            website="https://zoho.com",
            cleaned_text=text,
        )
        products = json.loads(structured["products"] or "[]")
        by_name = {item.get("name", ""): item.get("specifications", "") for item in products}
        self.assertIn("Zoho CRM", by_name)
        self.assertIn("Analytics Platform", by_name)
        self.assertIn("automation", by_name["Zoho CRM"].lower())
        self.assertIn("dashboards", by_name["Analytics Platform"].lower())


if __name__ == "__main__":
    unittest.main()
