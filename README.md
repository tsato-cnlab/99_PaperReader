# 📚 Paper Summarizer - Zotero + Gemini

研究者のための論文要約GUIアプリケーション。Zoteroで管理している論文PDFを一括で要約し、プレゼンテーション用スライド（Marp形式）を自動生成します。

## ✨ Features

- 🔗 **Zotero統合**: Zoteroコレクションから論文を直接取得
- 📄 **PDF解析**: PyMuPDF4LLMでPDFをMarkdownに変換
- 🧹 **自動クリーニング**: 参考文献セクションを自動除去
- 🤖 **AI要約**: Gemini 1.5 Proによる詳細な論文要約
- 🎞️ **スライド生成**: Marp形式のプレゼンテーションスライドを自動作成
- 💾 **バッチ処理**: 複数の論文を一度に処理可能
- 📊 **リアルタイム進捗**: プログレスバーで処理状況を表示

## 🛠️ Tech Stack

- **Package Manager:** `uv`
- **GUI Framework:** Streamlit
- **Zotero API:** pyzotero
- **PDF Parsing:** pymupdf4llm
- **LLM API:** google-generativeai (Gemini 1.5 Pro)
- **Environment:** python-dotenv

## 📦 Installation

### 1. uvのインストール

uvがまだインストールされていない場合、PowerShellで以下を実行:

```powershell
powershell -ExecutionPolicy ByPass -c "irm https://astral.sh/uv/install.ps1 | iex"
```

インストール後、PowerShellを再起動してください。

### 2. プロジェクトのセットアップ

```powershell
# リポジトリをクローンまたはダウンロード
cd C:\Users\echiz\00_研究コード\99_PaperReader

# 依存関係のインストール（既に完了している場合はスキップ可）
uv add streamlit pyzotero pymupdf4llm google-generativeai python-dotenv
```

### 3. 環境変数の設定

`.env.example` をコピーして `.env` を作成:

```powershell
Copy-Item .env.example .env
```

`.env` ファイルを編集して、以下の情報を入力:

```env
ZOTERO_LIBRARY_ID=your_library_id_here
ZOTERO_API_KEY=your_zotero_api_key_here
GEMINI_API_KEY=your_gemini_api_key_here
ZOTERO_STORAGE_PATH=C:\Users\YourUsername\Zotero\storage
```

#### Zotero API Keyの取得方法

1. [Zotero Settings](https://www.zotero.org/settings/keys) にアクセス
2. "Create new private key" をクリック
3. Library IDとAPI Keyをコピー

#### Gemini API Keyの取得方法

1. [Google AI Studio](https://makersuite.google.com/app/apikey) にアクセス
2. "Create API Key" をクリック
3. API Keyをコピー

#### Zotero Storage Pathの確認方法

Zoteroアプリで:
1. `Edit` → `Preferences` → `Advanced` → `Files and Folders`
2. "Data Directory Location" を確認
3. `storage` フォルダのパスをコピー（例: `C:\Users\YourName\Zotero\storage`）

## 🚀 Usage

### アプリの起動

```powershell
uv run streamlit run app.py
```

ブラウザが自動的に開き、アプリが起動します（通常 `http://localhost:8501`）。

### 使用手順

1. **サイドバーで設定**
   - Zotero Library ID、API Key、Gemini API Keyを入力
   - Local Zotero Storage Pathを確認・修正
   - Output Mode（Summary + Slides / Summary Only / Slides Only）を選択

2. **コレクションを選択**
   - "Fetch Collections" ボタンをクリック
   - ドロップダウンからコレクションを選択

3. **論文を選択**
   - "Load Papers" ボタンをクリック
   - 要約したい論文にチェックを入れる

4. **要約を実行**
   - "Start Summarization" ボタンをクリック
   - 進捗バーで処理状況を確認

5. **結果を確認**
   - 生成された要約とスライドをExpanderで確認
   - `./output/{論文タイトル}/` に保存されたファイルを開く

## 📂 Output Structure

```
output/
├── Paper_Title_1/
│   ├── summary.md          # 詳細要約
│   └── slides.md           # Marpスライド
├── Paper_Title_2/
│   ├── summary.md
│   └── slides.md
└── ...
```

## 🎞️ Marp Slidesの表示方法

生成された `slides.md` をプレゼンテーションとして表示する方法:

### VS Code拡張機能を使う（推奨）

1. VS Codeで [Marp for VS Code](https://marketplace.visualstudio.com/items?itemName=marp-team.marp-vscode) をインストール
2. `slides.md` を開く
3. 右上の "Open Preview to the Side" アイコンをクリック
4. HTMLやPDFにエクスポート可能

### Marp CLIを使う

Node.jsがインストール済みの場合:

```powershell
npx @marp-team/marp-cli slides.md -o slides.pdf
npx @marp-team/marp-cli slides.md -o slides.html
```

## 🔧 Troubleshooting

### uvコマンドが見つからない

- PowerShellを再起動してください
- 手動でPATHに追加:
  ```powershell
  $env:PATH += ";$env:USERPROFILE\.local\bin"
  ```

### PDFが見つからない

- Zotero Storage Pathが正しいか確認
- Zoteroで該当論文にPDFが添付されているか確認

### API Key エラー

- `.env` ファイルが正しく設定されているか確認
- Streamlit UIで直接入力した場合、その値が優先されます

### Gemini APIレート制限

- 無料枠の場合、1分あたりのリクエスト数に制限があります
- エラーが出た場合は少し待ってから再試行してください

## 📝 Code Structure

```python
app.py
├── get_collections()           # Zoteroコレクション取得
├── get_items_in_collection()   # 論文メタデータ取得
├── find_pdf()                  # PDFファイル検索
├── pdf_to_markdown()           # PDF→Markdown変換
├── clean_text()                # 参考文献除去（正規表現）
├── summarize_paper()           # Geminiで要約生成
├── generate_slides()           # Marpスライド生成
├── save_outputs()              # ファイル保存
└── main()                      # Streamlit UI
```

## 🤝 Contributing

改善提案やバグ報告は Issue または Pull Request でお願いします。

## 📄 License

このプロジェクトはMITライセンスの下で公開されています。

## 🙏 Acknowledgments

- [Zotero](https://www.zotero.org/) - 文献管理
- [pyzotero](https://github.com/urschrei/pyzotero) - Zotero Python API
- [pymupdf4llm](https://github.com/pymupdf/pymupdf4llm) - PDF解析
- [Google Gemini](https://ai.google.dev/) - LLM API
- [Marp](https://marp.app/) - Markdownプレゼンテーション
- [Streamlit](https://streamlit.io/) - GUIフレームワーク
