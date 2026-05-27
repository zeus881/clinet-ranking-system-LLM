import unittest

from extraction.schema_extractor import extract_structured_company_info


class TestPhase11IndustryMapping(unittest.TestCase):
    def test_ai_ml_maps_to_ai_software(self):
        text = "This AI and machine learning software platform powers enterprise workflows."
        structured = extract_structured_company_info(
            company_name="Acme AI",
            website="https://acme.ai",
            cleaned_text=text,
        )
        self.assertEqual(structured["industry"], "AI / Software")

    def test_semiconductor_maps_correctly(self):
        text = "AMD provides GPUs and AI chips for high-performance computing."
        structured = extract_structured_company_info(
            company_name="AMD",
            website="https://amd.com",
            cleaned_text=text,
        )
        self.assertEqual(structured["industry"], "Semiconductor / AI")

    def test_energy_maps_correctly(self):
        text = "The company builds solar energy systems for power generation."
        structured = extract_structured_company_info(
            company_name="EnergyCo",
            website="https://energy.example",
            cleaned_text=text,
        )
        self.assertEqual(structured["industry"], "Energy")


if __name__ == "__main__":
    unittest.main()
