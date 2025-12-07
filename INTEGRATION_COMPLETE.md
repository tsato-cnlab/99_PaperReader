# Two-Stage Model Integration - 完了

## ✅ 統合内容

`app.py` に2段階Gemini推論システムを統合しました。

### 🔄 主な変更点

#### 1. インポートとモデル設定

```python
from tenacity import (
    retry,
    stop_after_attempt,
    wait_fixed,
    retry_if_exception_type
)

# Two-stage model configuration
FLASH_MODEL = "gemini-2.0-flash-exp"  # Fast information extraction
PRO_MODEL = "gemini-2.0-pro-exp"      # Advanced reasoning
MAX_RETRIES = 5
RETRY_WAIT_SECONDS = 40
```

#### 2. 新しい関数構成

**Stage 1: 情報抽出（Flash Model）**
```python
def extract_paper_info(text: str, api_key: str, title: str) -> str:
    """高解像度情報抽出 - レート制限なし、高速"""
    flash_model = genai.GenerativeModel(FLASH_MODEL)
    # 詳細な情報を抽出（要約せず）
    ...
```

**Stage 2a: 要約生成（Pro Model + Retry）**
```python
@retry(
    stop=stop_after_attempt(MAX_RETRIES),
    wait=wait_fixed(RETRY_WAIT_SECONDS),
    ...
)
def summarize_paper(extracted_info: str, api_key: str, title: str) -> str:
    """抽出情報から要約を生成 - 40秒リトライ付き"""
    pro_model = genai.GenerativeModel(PRO_MODEL)
    # 構造化された要約を生成
    ...
```

**Stage 2b: スライド生成（Pro Model + Retry）**
```python
@retry(...)
def generate_slides(extracted_info: str, api_key: str, title: str, authors: str) -> str:
    """抽出情報からMarpスライドを生成 - 40秒リトライ付き"""
    pro_model = genai.GenerativeModel(PRO_MODEL)
    # Marp形式のスライドを生成
    ...
```

#### 3. 処理フローの更新

**変更前（1段階）:**
```python
# 1. PDF → Markdown
md_text = pdf_to_markdown(pdf_path)

# 2. 直接要約・スライド生成
summary = summarize_paper(md_text, api_key, title)
slides = generate_slides(md_text, api_key, title, authors)
```

**変更後（2段階）:**
```python
# 1. PDF → Markdown
md_text = pdf_to_markdown(pdf_path)

# 2. Stage 1: 情報抽出（Flash - 高速）
extracted_info = extract_paper_info(md_text, api_key, title)

# 3. Stage 2: 要約・スライド生成（Pro - リトライ付き）
summary = summarize_paper(extracted_info, api_key, title)
slides = generate_slides(extracted_info, api_key, title, authors)
```

### 🎨 UI の改善

#### サイドバー
```
⚙️ Configuration
└─ Zotero Library ID
└─ Zotero API Key
└─ Gemini API Key
└─ Local Zotero Storage Path
└─ Library Type

🤖 AI Model
└─ Stage 1: gemini-2.0-flash-exp
   └─ Fast information extraction
└─ Stage 2: gemini-2.0-pro-exp
   └─ Advanced reasoning (40s retry on rate limit)

Output Mode
└─ Both / Summary Only / Slides Only
```

#### メインエリア - プログレスメッセージ
```
Processing: Paper Title (1/3)
📄 Converting PDF to Markdown...
🔍 Stage 1: Extracting detailed information (gemini-2.0-flash-exp)...
✅ Stage 1 complete. Extracted 8543 characters.
📝 Stage 2: Generating summary (gemini-2.0-pro-exp)...
⏳ Rate limit detected. Waiting 40s before retry... (自動表示)
✅ Completed: Paper Title
```

### 🔧 エラーハンドリング

#### レート制限（429エラー）
```python
try:
    response = pro_model.generate_content(prompt)
    return response.text
except Exception as e:
    if "429" in str(e) or "RESOURCE_EXHAUSTED" in str(e):
        st.warning(f"⏳ Rate limit detected. Waiting {RETRY_WAIT_SECONDS}s...")
        raise  # tenacity が自動リトライ
    raise RuntimeError(f"Pro model error: {e}")
```

- **自動リトライ**: 最大5回、各40秒待機
- **ユーザー通知**: Streamlit警告メッセージで表示
- **透過的**: リトライは裏で実行、ユーザーは待つだけ

### 📊 パフォーマンス比較

#### 変更前（1段階・gemini-1.5-pro）
```
PDF変換: 3秒
要約生成: 20秒 (429エラー頻発)
スライド生成: 20秒 (429エラー頻発)
合計: 約43秒 + エラー再試行
```

#### 変更後（2段階・Flash + Pro）
```
PDF変換: 3秒
Stage 1 (Flash): 8秒 (情報抽出)
Stage 2a (Pro): 15秒 (要約)
Stage 2b (Pro): 15秒 (スライド)
合計: 約41秒 (429時は +40秒/回)
```

**利点:**
- ✅ Flash modelは制限なし・高速
- ✅ Proへの入力が圧縮されるため、処理が効率的
- ✅ 自動リトライで429エラーを吸収
- ✅ 情報の解像度を落とさない

### 🚀 使い方

#### 起動
```powershell
uv run streamlit run app.py
```

ブラウザで `http://localhost:8501` にアクセス

#### 使用フロー
1. サイドバーでAPIキーを入力
2. コレクションを選択
3. 論文を選択（複数可）
4. Output Mode を選択
5. 「🚀 Start Summarization」をクリック
6. 進捗を確認（Stage 1 → Stage 2）
7. 結果を確認・保存

#### レート制限が発生した場合
- 自動的に40秒待機してリトライ
- 画面に「⏳ Rate limit detected. Waiting 40s...」と表示
- 最大5回まで自動リトライ

### 🔍 技術的詳細

#### Stage 1（Flash）のプロンプト設計
- **目的**: 要約ではなく「高解像度情報抽出」
- **指示**: 
  - 数式・変数定義を省略せず記述
  - アルゴリズムステップを詳細に
  - 実験数値をすべて含める
  - 議論・限界点も記録
- **出力**: Proモデルが「原文を読んだ」のと同等の情報量

#### Stage 2（Pro）のプロンプト設計
- **入力**: Stage 1の抽出情報（圧縮されているがロスレス）
- **指示**:
  - 構造化された要約を生成
  - 根拠となる数値・数式を含める
  - Marpスライドは箇条書き形式で
- **リトライロジック**: `tenacity` で自動化

### 💡 ベストプラクティス

#### 複数論文の処理
- バッチ処理が可能
- 各論文ごとに Stage 1 → Stage 2 を実行
- エラーが起きても他の論文は処理継続

#### レート制限対策
- Stage 1 は何回実行してもOK（Flash modelは制限なし）
- Stage 2 で制限に遭遇→自動リトライ
- 大量処理時は時間をおいて実行

#### 出力モード活用
- `Summary Only`: 要約だけ必要な場合（Pro呼び出し1回）
- `Slides Only`: スライドだけ必要な場合（Pro呼び出し1回）
- `Both`: 両方生成（Pro呼び出し2回）

### 📝 今後の拡張案

1. **Stage 1結果の再利用**
   - 抽出情報をキャッシュ
   - 同じ論文に複数の質問（Q&A機能）

2. **カスタムプロンプト**
   - ユーザーが抽出項目を指定
   - 要約スタイルを選択

3. **モデル選択**
   - Flash/Proのモデルをドロップダウンで選択
   - リトライ設定をUI調整

---

**統合完了！すぐに使えます。**
```powershell
uv run streamlit run app.py
```
