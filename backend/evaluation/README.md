# 精度評価

型番ラベル写真に対する OCR・型番推定の精度を数値で測ります。改善の前後を同じデータで比べるための仕組みです。

## 手順

1. `backend/evaluation/dataset/` を作り、型番ラベルの写真と `labels.csv` を置く（形式は `sample/labels.csv` を参照）。
   - 現場の写真は個人情報・社外秘を含みうるため、`dataset/` は Git 管理から外してあります。
2. backend/ で実行する。

```bash
python -m evaluation.evaluate_ocr --dataset evaluation/dataset
```

結果は `evaluation/results/dataset.md`（レポート）と `.json`（ケース別の詳細）に出力されます。

## 指標

| 指標 | 意味 |
|---|---|
| Top-k 正解率 | 正解の型番が候補の上位 k 件に入った割合（ハイフン・大小文字は無視） |
| 文字誤り率 | Top-1 候補と正解の編集距離 ÷ 正解の文字数 |
| メーカー判定の正解率 | OCR 文字列からメーカーを当てられた割合 |
| 処理時間 | 1 枚あたりの平均・p95 |

## OCR を使わずロジックだけ評価する

`labels.csv` の `ocr_texts` に OCR 結果（`|` 区切り）を書くと OCR をスキップし、型番抽出ロジックだけを評価できます。`--stub` を付けると重いモデルを読み込まずに高速に動きます。CI ではこの方式（`sample/`）でテストしています。
