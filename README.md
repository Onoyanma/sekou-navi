# 施工ナビ

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
├── frontend/   # Next.js (React / TypeScript / Tailwind CSS) の Web UI
├── backend/    # FastAPI の REST API（OCR・類似検索・商品管理）
│   ├── main.py # API エンドポイント
│   └── ai.py   # 型番抽出・商品名推定などの推定ロジック
├── app.py      # 旧版（Streamlit 版プロトタイプ）
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

ブラウザで http://localhost:3000 を開きます（API は http://127.0.0.1:8000 を参照）。

## 旧版（Streamlit 版）

最初のプロトタイプは Streamlit で作成しました（`app.py`）。
デモ: https://sekou-navi-byr4khuzh6qfyxofcxkuq9.streamlit.app/

## 今後の改善予定

- 施工説明書検索の強化
- OCR・型番推定の精度向上
- スマートフォン向け UI の最適化
- クラウドへのデプロイ、ユーザー別データ管理
