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

## DB 照合込みの評価

OCR で型番を読み切れなくても、登録済み商品の型番に近ければアプリは正しい商品を見つけられます。そこで、実際の照合ロジック（`score_product_from_ocr`）まで含めた精度も測ります。

```bash
python -m evaluation.evaluate_ocr --dataset evaluation/dataset --catalog-db ../products.db
```

- 写真の正解商品はすべて「登録済み」として扱い、`--catalog-db` の商品を紛らわしい邪魔者として加えます（登録数が増えるほど難しくなります）。
- 同点の商品は正解より上に並んだものとして数えます（登録順の偶然で 1 位にならないようにするため）。
- 「未登録の商品を撮ったとき」は、正解を DB から除いて最高スコアを見ます。合格スコア（`--threshold`、既定 50）以上なら別の商品を自信ありげに返したことになり、**誤受理**として数えます。

| 指標 | 意味 |
|---|---|
| 商品 Top-k 正解率 | 照合結果の上位 k 件に正しい商品が入った割合 |
| 見つけられた割合 | 登録済みの商品を、合格スコア以上で見つけられた割合 |
| 誤受理率 | 未登録の商品を、別の商品と取り違えた割合 |

## OCR と画像検索（CLIP）の併用評価

```bash
python -m evaluation.evaluate_hybrid --dataset evaluation/dataset --catalog-db ../products.db --cache evaluation/results/ocr_cache.json
```

同じ写真で「テキストのみ」「画像のみ」「併用（アプリの挙動）」を比べます。ある写真を問い合わせにしたとき、登録済みの画像は「その写真以外すべて」とします（leave-one-out）。`--cache` は OCR 結果の保存先で、再実行が速くなります（OCR のコードを変えたら消してください）。`--min-similarity` と `--image-baseline` で、画像の足切りと点数の基準値を変えて試せます。

注意: 同じ商品の写真は同じ部屋・同じ端末で撮った取り直しなので、画像検索には有利な条件です。別の角度・別の場所で撮った写真でも測るのが望ましいです。
