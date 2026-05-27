import unittest
from unittest.mock import patch

from llm.summarizer import summarize_text
from main import _normalize_summary
from processing.text_processing import clean_text, merge_page_texts


class TestPhase3ProcessingSummarization(unittest.TestCase):
    def test_clean_text(self):
        text = "Hello\n\nWorld   !!! ###"
        cleaned = clean_text(text)
        self.assertEqual(cleaned, "Hello World !!!")

    def test_merge_page_texts(self):
        page_map = {
            "b": "Second page has autonomous robotics and drone navigation systems.",
            "a": "First page describes AI-powered computer vision platform for warehouses.",
        }
        result = merge_page_texts(page_map)
        self.assertIn("First", result)
        self.assertIn("Second", result)

    def test_summarize_fallback(self):
        text = "alpha beta gamma " * 80
        summary = summarize_text(text, max_chars=80)
        self.assertTrue(len(summary) <= 80)
        self.assertTrue(summary.startswith("alpha"))

    def test_normalize_summary_keeps_one_sentence(self):
        structured = {"company_name": "Acme", "industry": "Software"}
        summary = _normalize_summary("Acme builds AI software", structured)
        self.assertEqual(summary, "Acme builds AI software.")


if __name__ == "__main__":
    unittest.main()
