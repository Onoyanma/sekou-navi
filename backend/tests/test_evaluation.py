"""精度評価スクリプトの指標計算のテスト。"""

import unittest
from pathlib import Path

from evaluation.evaluate_ocr import (
    CaseResult,
    edit_distance,
    normalize_model,
    summarize,
)


def result(rank, distance=0, expected="ABC123", maker="TOTO", detected="TOTO"):
    return CaseResult(
        image="x.jpg",
        expected=expected,
        expected_maker=maker,
        candidates=[],
        detected_maker=detected,
        rank=rank,
        top1_distance=distance,
        seconds=0.1,
    )


class EvaluationTest(unittest.TestCase):
    def test_normalize_ignores_separators_and_case(self):
        self.assertEqual(normalize_model("vd-15 zc13"), "VD15ZC13")

    def test_edit_distance(self):
        self.assertEqual(edit_distance("ABC", "ABC"), 0)
        self.assertEqual(edit_distance("LH1234", "LHI234"), 1)
        self.assertEqual(edit_distance("", "AB"), 2)

    def test_summarize_top_k_and_not_found(self):
        metrics = summarize([result(1), result(3, 2), result(None, 6)])
        self.assertAlmostEqual(metrics["top1_accuracy"], 1 / 3)
        self.assertAlmostEqual(metrics["top3_accuracy"], 2 / 3)
        self.assertAlmostEqual(metrics["not_found_rate"], 1 / 3)
        self.assertAlmostEqual(metrics["char_error_rate_top1"], 8 / 18)

    def test_maker_accuracy(self):
        metrics = summarize([result(1), result(1, detected="LIXIL")])
        self.assertAlmostEqual(metrics["maker_accuracy"], 0.5)

    def test_sample_dataset_runs_end_to_end(self):
        from evaluation.evaluate_ocr import run

        sample = Path(__file__).resolve().parent.parent / "evaluation" / "sample"
        report = run(sample, use_stubs=True)
        self.assertEqual(report.total, 6)
        self.assertGreaterEqual(report.metrics["top3_accuracy"], 0.5)


if __name__ == "__main__":
    unittest.main()
