import unittest
from unittest.mock import patch

from extraction.schema_extractor import _extract_with_llm_strict


class _MockResponse:
    def __init__(self, payload: dict, status_code: int = 200):
        self._payload = payload
        self.status_code = status_code

    def json(self):
        return self._payload


class TestPhase4LlmStrictExtraction(unittest.TestCase):
    def test_missing_data_returns_empty(self):
        result = _extract_with_llm_strict("")
        self.assertEqual(result, {"products": [], "technologies": [], "industry": ""})

    @patch("extraction.schema_extractor.requests.post")
    def test_rejects_hallucinated_product_not_in_source(self, mock_post):
        mock_post.return_value = _MockResponse(
            {
                "response": (
                    '{"products":["Fake Product"],'
                    '"technologies":["AI"],"industry":"Software"}'
                )
            }
        )
        source = "Zoho CRM helps manage leads and supports automation."
        result = _extract_with_llm_strict(source)
        self.assertEqual(result["products"], [])
        self.assertEqual(result["technologies"], [])
        self.assertEqual(result["industry"], "")

    @patch("extraction.schema_extractor.requests.post")
    def test_valid_json_and_in_source_values_are_kept(self, mock_post):
        mock_post.return_value = _MockResponse(
            {
                "response": (
                    "```json\n"
                    '{"products":["Zoho CRM"],'
                    '"technologies":["automation"],'
                    '"industry":"CRM platform"}\n'
                    "```"
                )
            }
        )
        source = "Zoho CRM is our CRM platform and supports automation."
        result = _extract_with_llm_strict(source)
        self.assertEqual(result["products"], ["Zoho CRM"])
        self.assertEqual(result["technologies"], ["automation"])
        self.assertEqual(result["industry"], "CRM platform")


if __name__ == "__main__":
    unittest.main()
