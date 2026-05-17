# 施工ナビ

施工現場向けの商品検索・登録支援アプリです。  
商品画像・型番ラベル画像からAIが型番やカテゴリを推定し、施工説明書検索や商品管理を効率化します。

---

## 主な機能

### AI簡単登録
- 商品画像をアップロードまたはカメラ撮影
- OCRによる型番読み取り
- AIによる型番候補推定
- メーカー自動判定
- カテゴリ自動判定
- タグ自動判定
- 重複商品候補表示
- 既存商品への画像追加

### 商品検索
- メーカー検索
- 型番検索
- フリーワード検索
- タグ検索
- 類似画像検索
- OCR統合検索

### 商品管理
- 商品編集
- 複数画像管理
- 画像種類管理
- 商品削除

### 画像AI機能
- OCR型番認識
- 類似画像検索
- 型番補正AI
- AIスコア表示

---

## 使用技術

- Python
- Streamlit
- SQLite
- EasyOCR
- SentenceTransformers
- FAISS
- Pillow
- pandas
- scikit-learn

---

## 起動方法

### 1. ライブラリインストール

bash pip install -r requirements.txt 

### 2. アプリ起動

bash streamlit run app.py 

---

## ディレクトリ構成

text sekou_navi/ ├ app.py ├ products.db ├ images/ ├ temp_images/ ├ ai_search_images/ ├ requirements.txt └ README.md 

---

## 今後の改善予定

- AI商品名推定強化
- AI施工説明書検索強化
- OCR精度向上
- スマホUI最適化
- クラウド対応
- ユーザー別データ管理

---

## 開発目的

施工現場では、型番確認や施工説明書検索に時間がかかる課題があります。  
本アプリは、OCR・画像検索・AI推定を活用し、現場での検索や登録作業を高速化することを目的として開発しています。
=======
# sekou-navi