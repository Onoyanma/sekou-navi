"""画像検索の併用評価と、画像スコアの基準値のテスト。"""

import unittest

import numpy as np

from evaluation.evaluate_hybrid import image_only_ranking, pessimistic_rank
from tests.stubs import install_stubs, use_temporary_storage

use_temporary_storage()
install_stubs()

from services import matching  # noqa: E402


def merge_image_only(similarity, image_type="その他"):
    product = {"id": 1, "maker": "", "model_number": "AB-100", "product_name": ""}
    results = matching.merge_similar_search_results(
        [{"product": product, "similarity": similarity, "image_type": image_type}],
        [], "", [], [], [],
    )
    return results[0]["combined_score"]


class PessimisticRankTest(unittest.TestCase):
    def test_ties_count_against_the_target(self):
        scored = [(50.0, "AB-100"), (50.0, "CD-200"), (10.0, "EF-300")]
        self.assertEqual(pessimistic_rank("CD-200", scored), 2)

    def test_missing_or_zero_score_is_not_found(self):
        self.assertIsNone(pessimistic_rank("ZZ-1", [(50.0, "AB-100")]))
        self.assertIsNone(pessimistic_rank("AB-100", [(0.0, "AB-100")]))


class ImageOnlyRankingTest(unittest.TestCase):
    def test_best_image_per_product_wins_and_threshold_applies(self):
        a = np.array([1.0, 0.0])
        registered = [
            ("AB100", np.array([0.6, 0.8])),   # 類似度 0.6
            ("AB100", np.array([0.9, 0.436])), # 類似度 0.9 -> こちらが採用される
            ("CD200", np.array([0.0, 1.0])),   # 類似度 0.0 -> 足切り
        ]
        ranking = image_only_ranking(a, registered, min_similarity=0.25)
        self.assertEqual([m for _, m in ranking], ["AB100"])
        self.assertAlmostEqual(ranking[0][0], 0.9)


class ImageScoreBaselineTest(unittest.TestCase):
    def setUp(self):
        self.original = matching.IMAGE_SCORE_BASELINE

    def tearDown(self):
        matching.IMAGE_SCORE_BASELINE = self.original

    def test_similarity_at_baseline_adds_nothing(self):
        matching.IMAGE_SCORE_BASELINE = 0.7
        self.assertAlmostEqual(merge_image_only(0.7), 0.0)
        self.assertAlmostEqual(merge_image_only(0.5), 0.0)

    def test_perfect_similarity_gets_full_score(self):
        matching.IMAGE_SCORE_BASELINE = 0.7
        self.assertAlmostEqual(merge_image_only(1.0), 50.0)

    def test_zero_baseline_keeps_proportional_scoring(self):
        matching.IMAGE_SCORE_BASELINE = 0.0
        self.assertAlmostEqual(merge_image_only(0.5), 25.0)


if __name__ == "__main__":
    unittest.main()
