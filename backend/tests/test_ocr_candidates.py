"""型番候補の抽出ロジックのテスト（実機の写真で外れた事例を回帰テストにしている）。"""

import unittest

from tests.stubs import install_stubs, use_temporary_storage

use_temporary_storage()
install_stubs()

from services import model_numbers, ocr  # noqa: E402


def candidate_names(texts):
    return [name for name, _ in model_numbers.extract_model_candidates(texts)]


class ModelCandidateTest(unittest.TestCase):
    def test_electrical_specs_are_not_model_numbers(self):
        names = candidate_names(["980W/", "50/60Hz", "455mm", "100V"])
        self.assertEqual(names, [])

    def test_phone_numbers_are_not_model_numbers(self):
        self.assertEqual(candidate_names(["0120-911-026", "0120-1794-11"]), [])

    def test_real_model_beats_specs(self):
        names = candidate_names(["980W/1280W", "RE-CE8-KW", "50/60Hz"])
        self.assertEqual(names[0], "RE-CE8-KW")

    def test_letter_o_between_digits_is_fixed_to_zero(self):
        self.assertEqual(model_numbers.fix_digit_context_letter_o("SL-O13BK"), "SL-013BK")
        self.assertEqual(model_numbers.fix_digit_context_letter_o("12O5"), "1205")

    def test_letter_o_inside_words_is_kept(self):
        self.assertEqual(model_numbers.fix_digit_context_letter_o("MOTOR-X1"), "MOTOR-X1")

    def test_ocr_misread_is_still_reachable_as_variant(self):
        # 8 を B と誤読した型番も、入れ替え候補として残る
        self.assertIn("CEB-KW1", candidate_names(["CE8-KW1"]))

    def test_label_word_boosts_candidates_on_same_line(self):
        scores = dict(model_numbers.extract_model_candidates(["形名 AB-123", "CD-456"]))
        self.assertGreater(scores["AB-123"], scores["CD-456"])

    def test_digit_leading_serial_numbers_rank_lower(self):
        scores = dict(model_numbers.extract_model_candidates(["2264586X", "KC-L50-W"]))
        self.assertGreater(scores["KC-L50-W"], scores["2264586X"])

    def test_variants_per_candidate_are_capped(self):
        variants = model_numbers.generate_ocr_variants("OIOIOIOI-8888")
        self.assertLessEqual(len(variants), model_numbers.MAX_VARIANTS_PER_CANDIDATE + 1)

    def test_appliance_makers_are_detected(self):
        self.assertEqual(model_numbers.detect_maker_from_text(["SHARP", "RE-CE8-KW"]), "SHARP")
        self.assertEqual(model_numbers.detect_maker_from_text(["アイホン"]), "アイホン")

    def test_more_makers_are_detected(self):
        for text, maker in [
            ("KVK", "KVK"),
            ("株式会社SANEI", "SANEI"),
            ("ODELIC", "オーデリック"),
            ("TOSHIBA LIGHTING & TECHNOLOGY", "東芝ライテック"),
            ("TOSHIBA", "東芝"),
            ("日東工業", "日東工業"),
            ("ZOJIRUSHI", "象印"),
        ]:
            self.assertEqual(model_numbers.detect_maker_from_text([text]), maker, text)

    def test_gpu_setting_can_be_forced_by_environment(self):
        import os
        from unittest import mock

        with mock.patch.dict(os.environ, {"SEKOU_OCR_GPU": "0"}):
            self.assertFalse(ocr.use_gpu_for_ocr())
        with mock.patch.dict(os.environ, {"SEKOU_OCR_GPU": "1"}):
            self.assertTrue(ocr.use_gpu_for_ocr())

    def test_tiles_cover_the_whole_image(self):
        from PIL import Image

        tiles = ocr.split_into_tiles(Image.new("RGB", (900, 600)), grid=3, overlap=0.25)
        self.assertEqual(len(tiles), 9)
        self.assertTrue(all(t.shape[0] > 0 and t.shape[1] > 0 for t in tiles))


if __name__ == "__main__":
    unittest.main()
