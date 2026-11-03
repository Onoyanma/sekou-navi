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


class CatalogMatchingTest(unittest.TestCase):
    CATALOG = [
        {"model_number": "AB-100", "maker": "X"},
        {"model_number": "CD-200", "maker": "Y"},
        {"model_number": "EF-300", "maker": "Y"},
    ]

    @staticmethod
    def fake_score(product, candidates, maker, hints):
        # 型番が候補と完全一致なら 100、メーカー一致だけなら 28
        names = {name for name, _ in candidates}
        if product["model_number"] in names:
            return 100.0, ["model"], product["model_number"]
        return (28.0 if maker == product["maker"] else 0.0), [], ""

    def evaluate(self, expected, ocr_texts, maker=""):
        from evaluation.evaluate_ocr import Case, evaluate_case

        case = Case(image="x.jpg", model_number=expected, ocr_texts=ocr_texts)
        return evaluate_case(
            case,
            Path("."),
            read_text=lambda path: [],
            extract_candidates=lambda texts: [(t, 50) for t in texts],
            detect_maker=lambda texts: maker,
            catalog=self.CATALOG,
            score_product=self.fake_score,
        )

    def test_exact_match_is_ranked_first(self):
        result = self.evaluate("CD-200", ["CD-200"])
        self.assertEqual(result.product_rank, 1)
        self.assertEqual(result.closed_set_score, 100.0)

    def test_ties_are_counted_against_us(self):
        # メーカーだけ一致する 2 商品は同点なので、どちらも 1 位とは言えない
        result = self.evaluate("CD-200", ["ZZ-999"], maker="Y")
        self.assertEqual(result.product_rank, 2)

    def test_open_set_score_ignores_the_true_product(self):
        result = self.evaluate("CD-200", ["CD-200"], maker="Y")
        self.assertEqual(result.open_set_top_score, 28.0)

    def test_summary_reports_false_accept_rate(self):
        from evaluation.evaluate_ocr import summarize

        good = self.evaluate("CD-200", ["CD-200"])
        bad = self.evaluate("AB-100", ["CD-200"])  # 正解が登録されていなくても別商品が 100 点
        metrics = summarize([good, bad], threshold=50)
        self.assertAlmostEqual(metrics["product_top1_accuracy"], 0.5)
        self.assertAlmostEqual(metrics["false_accept_rate"], 0.5)

    def test_build_catalog_dedupes_by_normalized_model(self):
        from evaluation.evaluate_ocr import Case, build_catalog

        cases = [Case("a.jpg", "SL-013BK"), Case("b.jpg", "sl013bk")]
        self.assertEqual(len(build_catalog(cases)), 1)
