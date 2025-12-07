# 🚀 Quick Start Guide

## 1. アプリを起動

```powershell
uv run streamlit run app.py
```

ブラウザで `http://localhost:8501` が自動的に開きます。

## 2. 初期設定（初回のみ）

### 方法A: .envファイルを使う（推奨）

`.env` ファイルを作成して以下を記入:

```env
ZOTERO_LIBRARY_ID=123456
ZOTERO_API_KEY=your_zotero_api_key
GEMINI_API_KEY=your_gemini_api_key
ZOTERO_STORAGE_PATH=C:\Users\YourName\Zotero\storage
```

### 方法B: UIで直接入力

サイドバーの入力欄に直接APIキーを入力できます。

## 3. 使い方

### Step 1: コレクションを取得
1. サイドバーで設定を確認
2. "🔄 Fetch Collections" ボタンをクリック
3. ドロップダウンからコレクションを選択

### Step 2: 論文を読み込み
1. "📄 Load Papers" ボタンをクリック
2. 表示された論文リストから要約したいものにチェック

### Step 3: 要約を実行
1. Output Mode（Summary + Slides / Summary Only / Slides Only）を選択
2. "🚀 Start Summarization" ボタンをクリック
3. 進捗バーで処理状況を確認

### Step 4: 結果を確認
- 各論文のExpanderを開いて要約とスライドを確認
- `./output/論文タイトル/` フォルダに保存されたファイルを開く

## 4. 生成されたスライドの表示

### VS Code（推奨）
1. Marp for VS Code拡張機能をインストール
2. `output/論文タイトル/slides.md` を開く
3. 右上の "Open Preview" アイコンをクリック

### PDF/HTMLに変換
```powershell
cd output/論文タイトル
npx @marp-team/marp-cli slides.md -o slides.pdf
```

## 📌 Tips

- **バッチ処理**: 複数の論文を一度に選択できます
- **進捗確認**: プログレスバーで現在の処理状況がわかります
- **エラー時**: 各論文ごとにエラーが表示されるので、一部が失敗しても他は処理されます
- **保存先**: `./output/` フォルダに論文タイトル名のサブフォルダが作成されます
- **PDF検索**: Zoteroのattachment（子アイテム）キーを使用してPDFを正確に特定します

## ⚠️ 注意事項

- Gemini APIの無料枠では1分あたりのリクエスト数に制限があります
- 大量の論文を処理する場合は時間がかかる可能性があります
- PDFがZoteroのstorageフォルダに存在することを確認してください
- コレクションの論文数が多い場合、読み込みに時間がかかります（子アイテムを取得するため）
