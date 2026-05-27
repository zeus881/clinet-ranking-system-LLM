import unittest

import numpy as np

from embedding.embeddings import cosine_similarity
from models.schemas import Company
from ranking.ranker import rank_companies


class TestPhase4EmbeddingRanking(unittest.TestCase):
    def test_cosine_similarity(self):
        a = np.array([1.0, 1.0, 0.0])
        b = np.array([1.0, 0.8, 0.0])
        c = np.array([0.0, 0.0, 1.0])
        self.assertGreater(cosine_similarity(a, b), cosine_similarity(a, c))

    def test_rank_companies_orders_by_score(self):
        companies = [
            Company(name="AcmeAI", website="https://acme.ai"),
            Company(name="BuildCo", website="https://build.co"),
        ]
        summaries = {
            "https://acme.ai": "autonomous robotics drone defense edge AI computer vision",
            "https://build.co": "cement and steel supplier traditional construction",
        }
        structured = {
            "https://acme.ai": {
                "industry": "Defense AI",
                "products_list": ["NaviCore"],
                "services_list": [],
                "technologies_list": ["Computer Vision", "LiDAR", "SLAM"],
                "use_cases_list": ["autonomous navigation"],
                "confidence": 0.85,
            },
            "https://build.co": {
                "industry": "Construction",
                "products_list": [],
                "services_list": [],
                "technologies_list": [],
                "use_cases_list": [],
                "confidence": 0.30,
            },
        }
        ranked = rank_companies(companies, summaries, structured)
        self.assertEqual(ranked[0].company.name, "AcmeAI")
        self.assertGreater(ranked[0].score, ranked[1].score)


if __name__ == "__main__":
    unittest.main()
