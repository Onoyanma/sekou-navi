"""時間計測の集計のテスト（ダミーデータで動作を確認する。実際の実験結果ではない）。"""

import unittest
from pathlib import Path

from evaluation.analyze_time_experiment import (
    TIME_LIMIT_SECONDS,
    load_rows,
    render_markdown,
    summarize,
)

DUMMY = Path(__file__).resolve().parent.parent / "evaluation" / "sample" / "time_experiment_dummy.csv"


class TimeExperimentTest(unittest.TestCase):
    def test_failures_count_as_the_time_limit(self):
        rows = load_rows(DUMMY)
        failed = [r for r in rows if not r.success]
        self.assertEqual(len(failed), 2)
        self.assertTrue(all(r.seconds == TIME_LIMIT_SECONDS for r in failed))

    def test_summary_splits_methods_and_registration(self):
        summary = summarize(load_rows(DUMMY))
        self.assertEqual(summary["A"]["n"], 4)
        self.assertEqual(summary["B"]["n"], 4)
        self.assertEqual(summary["B_registered"]["n"], 2)
        self.assertEqual(summary["B_unregistered"]["n"], 2)
        # A: 95, 120, 150, 180 -> 中央値 135 / B: 18, 60, 22, 180(失敗) -> 中央値 41
        self.assertAlmostEqual(summary["A"]["median"], 135)
        self.assertAlmostEqual(summary["B"]["median"], 41)
        self.assertGreater(summary["median_reduction"], 0.6)

    def test_invalid_method_is_rejected(self):
        import tempfile

        with tempfile.NamedTemporaryFile("w", suffix=".csv", delete=False, encoding="utf-8") as f:
            f.write("participant,item,method,registered,seconds,success,notes\nU1,P01,C,,10,1,\n")
        with self.assertRaises(ValueError):
            load_rows(Path(f.name))

    def test_markdown_mentions_the_comparison(self):
        text = render_markdown(summarize(load_rows(DUMMY)))
        self.assertIn("中央値の変化", text)
        self.assertIn("検定は行っていない", text)


if __name__ == "__main__":
    unittest.main()
