# 施工ナビ

[![CI](https://github.com/Onoyanma/sekou-navi/actions/workflows/ci.yml/badge.svg)](https://github.com/Onoyanma/sekou-navi/actions/workflows/ci.yml)

施工現場向けの **商品検索・登録支援アプリ** です。
商品写真や型番ラベル・バーコードから型番やメーカー・カテゴリを推定し、施工説明書の検索や商品管理を効率化します。

## 開発の背景

施工現場では、設備の型番確認や施工説明書の検索に時間がかかるという課題があります。
本アプリは OCR・画像検索・バーコード読み取りを組み合わせ、現場での検索・登録作業を短時間で行えるようにすることを目的に開発しています。

## 主な機能

### 登録
- 商品画像のアップロード / カメラ撮影
- OCR による型番読み取りと、型番候補の推定・補正
- メーカー・カテゴリ・タグの自動判定
- バーコードスキャンによるクイック登録
- 入力補完（オートコンプリート）、重複商品候補の表示

### 検索
- メーカー・型番・フリーワード・タグ検索
- 類似画像検索（画像の埋め込みベクトルによる類似度検索）
- OCR 統合検索、AI 検索、バーコード検索

### 管理
- 商品の編集・削除
- 1 商品に複数画像を登録、画像種類の管理

## 構成

```
sekou_navi/
├── frontend/       # Next.js (React / TypeScript / Tailwind CSS) の Web UI
├── backend/        # FastAPI の REST API（OCR・類似検索・商品管理）
│   ├── main.py     # API エンドポイント
│   ├── ai.py       # 型番抽出・商品名推定・自動タグ付けのロジック
│   ├── database.py # DB スキーマの作成・移行、保存先の設定
│   └── tests/      # API・DB のテスト
├── .github/workflows/ci.yml  # GitHub Actions（テスト・Lint・型チェック・ビルド）
├── app.py          # 旧版（Streamlit 版プロトタイプ）
└── requirements.txt
```

| 区分 | 使用技術 |
|---|---|
| フロントエンド | Next.js 16, React 19, TypeScript, Tailwind CSS, @zxing/browser（バーコード読み取り） |
| バックエンド | Python, FastAPI, SQLite |
| 画像・AI | EasyOCR, SentenceTransformers, scikit-learn, Pillow |

## 起動方法

### バックエンド

```bash
cd backend
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
uvicorn main:app --reload --port 8000
```

### フロントエンド

```bash
cd frontend
npm install
npm run dev
```

ブラウザで http://localhost:3000 を開きます。
初回起動時に DB（`products.db`）と画像フォルダは自動で作成されます。

### 設定（環境変数）

| 変数 | 用途 | 既定値 |
|---|---|---|
| `NEXT_PUBLIC_API_BASE_URL` | フロントエンドが呼び出す API の URL（`frontend/.env.local` に記述） | `http://127.0.0.1:8000` |
| `SEKOU_DB_PATH` | SQLite ファイルの場所 | `products.db` |
| `SEKOU_IMAGE_DIR` | 商品画像の保存先 | `images/` |
| `SEKOU_TEMP_DIR` | OCR・類似検索用の一時画像の保存先（解析後に自動削除） | `temp_images/` |
| `SEKOU_CORS_ORIGINS` | API へのアクセスを許可するフロントエンドの URL（カンマ区切り） | `http://localhost:3000,http://127.0.0.1:3000` |

## テスト

```bash
# バックエンド（OCR・埋め込みモデルはスタブに置き換えて高速に実行）
cd backend
pip install -r requirements-test.txt
python -m unittest discover -s tests -t . -v

# フロントエンド
cd frontend
npm run lint
npx tsc --noEmit
```

GitHub に push すると、GitHub Actions で上記のテスト・Lint・型チェック・本番ビルドが自動で実行されます。

## 工夫した点

- **OCR と画像検索の組み合わせ**：型番ラベルの文字（OCR）と商品写真の見た目（CLIP による画像埋め込み）の両方から候補を探し、スコアを統合して提示
- **キーワード検索と意味検索のハイブリッド**：型番の部分一致・表記ゆれに強いあいまい検索と、多言語文埋め込みによる自然文検索を組み合わせ
- **現場での入力の手間を減らす**：バーコード / QR の読み取り、メーカー・カテゴリ・タグの自動判定、入力補完
- **安全性**：アップロードされたファイル名の無害化（パストラバーサル対策）、一時ファイルの自動削除

## 旧版（Streamlit 版）

最初のプロトタイプは Streamlit で作成しました（`app.py`）。
デモ: https://sekou-navi-byr4khuzh6qfyxofcxkuq9.streamlit.app/

## 今後の改善予定

- 施工説明書検索の強化
- OCR・型番推定の精度向上
- スマートフォン向け UI の最適化
- クラウドへのデプロイ、ユーザー別データ管理
