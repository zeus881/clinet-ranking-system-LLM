import unittest

from extraction.schema_extractor import _clean_extraction_text


class TestPhase9LlmCleaning(unittest.TestCase):
    def test_removes_repeated_sentences(self):
        text = (
            "AI platform helps automate testing workflows. "
            "AI platform helps automate testing workflows. "
            "AI platform helps automate testing workflows."
        )
        cleaned = _clean_extraction_text(text)
        lines = [line for line in cleaned.splitlines() if line.strip()]
        self.assertEqual(len(lines), 1)
        self.assertIn("AI platform helps automate testing workflows", lines[0])

    def test_removes_long_paragraph_like_lines(self):
        long_line = " ".join(["This is a very long paragraph"] * 12)
        text = (
            f"{long_line}. "
            "Zoho CRM helps manage leads."
        )
        cleaned = _clean_extraction_text(text)
        self.assertIn("Zoho CRM helps manage leads", cleaned)
        self.assertNotIn("very long paragraph", cleaned)

    def test_limits_output_to_four_lines(self):
        text = (
            "Line one about product platform. "
            "Line two about service automation. "
            "Line three about workflow support. "
            "Line four about technology features. "
            "Line five should be trimmed."
        )
        cleaned = _clean_extraction_text(text)
        lines = [line for line in cleaned.splitlines() if line.strip()]
        self.assertLessEqual(len(lines), 4)
        self.assertNotIn("Line five", cleaned)


if __name__ == "__main__":
    unittest.main()
