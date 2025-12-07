import os
import time
from pyzotero import zotero
import pymupdf4llm
import google.generativeai as genai
from dotenv import load_dotenv

# 環境変数の読み込み (.envに APIキーなどを記述)
load_dotenv()
ZOTERO_API_KEY = os.getenv("fM2LEuw8tOBlzManMhkYZC0r")
ZOTERO_LIBRARY_ID = os.getenv("14538317")
GEMINI_API_KEY = os.getenv("AIzaSyD2fwH80k-exeBShaLogCh4ZHe36v4s4HA")

# Zoteroクライアントの設定
zot = zotero.Zotero(ZOTERO_LIBRARY_ID, 'user', ZOTERO_API_KEY)
# Geminiの設定
genai.configure(api_key=GEMINI_API_KEY)
model = genai.GenerativeModel("gemini-3") # コンテキストが長いのでPro推奨

def get_pdf_path(item):
    """Zoteroのアイテム情報からローカルのPDFパスを特定する"""
    # 注: Zoteroの添付ファイルは通常 'storage/KEY/filename.pdf' にある
    # 実際の実装では、Zoteroのデータディレクトリを検索するか、
    # リンクモードの場合はそのパスを参照する処理が必要
    # ここでは簡易的に「データディレクトリ」を指定する想定
    zotero_storage_dir = "C:\\Users\\echiz\\Zotero\\storage" # ★自分の環境に合わせる
    
    if 'key' not in item:
        return None
        
    item_key = item['key']
    item_dir = os.path.join(zotero_storage_dir, item_key)
    
    if not os.path.exists(item_dir):
        return None

    # ディレクトリ内のPDFを探す
    for file in os.listdir(item_dir):
        if file.endswith(".pdf"):
            return os.path.join(item_dir, file)
    return None

def summarize_paper(pdf_text):
    """LLMで要約を作成する"""
    prompt = f"""
            # Role
            あなたは[ご自身の専門分野]の専門家であり、論文の査読経験が豊富なシニアリサーチャーです。

            # Goal
            提供された論文テキストを読み込み、以下のフォーマットに従って重要事項を構造化して出力してください。
            私がこの論文を詳細に読むべきか、自分の研究に取り入れるべきかを判断するための材料とします。

            # Input Text
            [ここに論文のテキストを貼り付け]

            # Constraints
            * 出力は日本語で行ってください。
            * 抽象的な表現は避け、具体的な数値や手法名を用いてください。
            * 著者の主張を鵜呑みにせず、客観的な視点を維持してください。

            # Output Format (Markdown)

            ## 1. どんなもの？ (Overview)
            * 一言でいうと：
            * 解決したい課題：

            ## 2. 先行研究と比べてどこがすごい？ (Novelty & Difference)
            * 既存手法の限界：
            * この研究の独自の提案・アイディア：

            ## 3. 技術や手法のキモはどこ？ (Methodology)
            * 使用したモデル/アルゴリズム：
            * データの種類と規模：
            * 特筆すべき工夫点：

            ## 4. どうやって有効性を検証した？ (Evaluation)
            * 比較対象（Baseline）：
            * 評価指標（Metrics）：
            * 結果（数値で）：

            ## 5. 議論・課題はある？ (Discussion & Limitations)
            * この手法がうまくいかないケース：
            * 著者が挙げている課題（Future Work）：
            * （あなたの視点での）懸念点：
            
    {pdf_text[:50000]} # トークン節約のため適宜カットしても良いが1.5 Proなら全部いける
    """
    
    try:
        response = model.generate_content(prompt)
        return response.text
    except Exception as e:
        return f"Error: {e}"

def main(collection_id):
    # コレクション内のアイテムを取得 (limitで数を指定)
    items = zot.collection_items(collection_id, limit=50, itemType='journalArticle')
    
    for item in items:
        title = item['data'].get('title', 'No Title')
        print(f"Processing: {title}...")
        
        # 親アイテムのキーを使って添付ファイル（子供）を探す必要がある場合もあるが
        # pyzoteroのメソッドで添付ファイルを取得するロジックを組む
        # ※ ここでは簡略化のため、item自体がPDFを持っているか、
        #    あるいはitem['key']フォルダにPDFがある前提で進めます
        
        pdf_path = get_pdf_path(item) # ※ここのロジックはZoteroの管理方法(リンク/保存)による
        
        if pdf_path:
            # PDFをMarkdownテキストに変換 (非常に軽量かつ高精度)
            md_text = pymupdf4llm.to_markdown(pdf_path)
            
            # 要約生成
            summary = summarize_paper(md_text)
            
            # ファイル保存
            safe_title = title.replace("/", "_").replace(":", "-")
            with open(f"summaries/{safe_title}.md", "w", encoding="utf-8") as f:
                f.write(f"# {title}\n\n{summary}")
            
            print(f"Done: {safe_title}.md")
            time.sleep(2) # APIレート制限への配慮
        else:
            print("  Skipped: PDF not found.")

if __name__ == "__main__":
    # 対象のコレクションIDを指定して実行
    TARGET_COLLECTION_ID = "XXXXXXXX" 
    main(TARGET_COLLECTION_ID)