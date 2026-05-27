import json
import unittest
from unittest.mock import patch, MagicMock

from crawler.crawler import crawl_company_website, extract_relevant_links
from extraction.schema_extractor import extract_structured_company_info


class MockResp:
    def __init__(self, text: str, status: int = 200):
        self.text = text
        self.status_code = status


class TestPhase2Crawler(unittest.TestCase):
    def test_extract_relevant_links(self):
        html = (
            '<a href="/products?x=1">Products</a>'
            '<a href="/solutions">Solutions</a>'
            '<a href="/privacy">Privacy</a>'
            '<a href="https://external.com/about">External</a>'
            '<a href="/blog">Blog</a>'
        )
        links = extract_relevant_links("https://acme.com", html)
        self.assertIn("https://acme.com/products", links)
        self.assertIn("https://acme.com/solutions", links)
        self.assertNotIn("https://acme.com/privacy", links)
        self.assertTrue(all("external.com" not in link for link in links))

    @patch("crawler.crawler._fetch")
    def test_crawl_returns_section_keys(self, mock_fetch):
        home_html = (
            "<html><body>"
            "<h1>Acme AI Company</h1>"
            "<p>We build autonomous robotics products and AI platforms.</p>"
            '<a href="/products">Products</a>'
            "</body></html>"
        )
        mock_fetch.return_value = home_html
        data = crawl_company_website("https://acme.com", max_pages=1)
        # Current crawler returns section-keyed dict
        self.assertIn("all", data)
        self.assertIn("products", data)
        self.assertIn("services", data)
        self.assertIn("quality", data)

    @patch("crawler.crawler._fetch")
    def test_crawl_accumulates_text_across_pages(self, mock_fetch):
        home_html = (
            "<html><body>"
            "<h1>Acme AI Products</h1>"
            "<p>We build autonomous robotics and AI systems for industry.</p>"
            '<a href="/platform">Platform</a>'
            "</body></html>"
        )
        product_html = (
            "<html><body>"
            "<h2>NaviCore Platform</h2>"
            "<p>NaviCore is an autonomous navigation platform with SLAM and LiDAR.</p>"
            "</body></html>"
        )
        mock_fetch.side_effect = [home_html, product_html]
        data = crawl_company_website("https://acme.com", max_pages=2)
        combined = data.get("all", "")
        self.assertGreater(len(combined), 50)

    def test_product_filter_discards_generic_only_terms(self):
        structured = extract_structured_company_info(
            company_name="Acme",
            website="https://acme.com",
            cleaned_text="platform system solution AI drone platform",
        )
        products = json.loads(structured["products"] or "[]")
        self.assertEqual(products[0]["name"], "Drone Platform")


if __name__ == "__main__":
    unittest.main()
