"""
Paper Summarizer with Zotero Integration
=========================================
A Streamlit app to summarize papers from Zotero collections using Gemini LLM.
"""

import os
import re
import time
import json
from pathlib import Path
from typing import List, Dict, Optional, Tuple
import streamlit as st
from pyzotero import zotero
import pymupdf4llm
import google.generativeai as genai
from dotenv import load_dotenv
from notion_client import Client

# Load environment variables
load_dotenv()

# ==================== Configuration ====================

DEFAULT_ZOTERO_STORAGE = os.getenv(
    "ZOTERO_STORAGE_PATH",
    r"C:\Users\echiz\Zotero\storage"
)

OUTPUT_DIR = Path("./output")
OUTPUT_DIR.mkdir(exist_ok=True)

# Model configuration (simplified to single-stage)
GEMINI_MODEL = "gemini-flash-lite-latest"  # Cost-efficient model
# GEMINI_MODEL = "gemini-2.5-flash-tts"  # Cost-efficient model
RATE_LIMIT_DELAY = 4  # seconds between API calls

# Notion configuration
NOTION_TOKEN = os.getenv("NOTION_TOKEN", "")
NOTION_DATABASE_ID = os.getenv("NOTION_DATABASE_ID", "")


# ==================== Helper Functions ====================

def get_collections(library_id: str, api_key: str, library_type: str = "user") -> List[Dict]:
    """
    Fetch collections from Zotero.
    
    Args:
        library_id: Zotero library ID
        api_key: Zotero API key
        library_type: 'user' or 'group'
    
    Returns:
        List of collection dictionaries with 'key' and 'name'
    """
    try:
        zot = zotero.Zotero(library_id, library_type, api_key)
        collections = zot.collections()
        return [
            {"key": col["key"], "name": col["data"]["name"]}
            for col in collections
        ]
    except Exception as e:
        st.error(f"Failed to fetch collections: {e}")
        return []


def get_items_in_collection(
    library_id: str, 
    api_key: str, 
    collection_key: str,
    library_type: str = "user"
) -> List[Dict]:
    """
    Get all items in a specific Zotero collection.
    
    IMPORTANT: This function fetches child attachments for each item to find the PDF key.
    Zotero stores PDFs under the attachment (child) key, not the parent item key.
    
    Returns:
        List of items with metadata (key, title, creators, year, pdf_key)
        - key: Parent item key
        - pdf_key: Child attachment key (used to locate PDF in storage folder)
    """
    try:
        zot = zotero.Zotero(library_id, library_type, api_key)
        items = zot.collection_items(collection_key)
        
        papers = []
        for item in items:
            data = item.get("data", {})
            if data.get("itemType") not in ["journalArticle", "conferencePaper", "preprint"]:
                continue
            
            # Extract authors
            creators = data.get("creators", [])
            authors = ", ".join([
                f"{c.get('lastName', '')} {c.get('firstName', '')}".strip()
                for c in creators if c.get("creatorType") == "author"
            ])
            
            # Find PDF attachment key from children
            pdf_key = None
            try:
                children = zot.children(item["key"])
                for child in children:
                    child_data = child.get("data", {})
                    if (child_data.get("itemType") == "attachment" and 
                        child_data.get("contentType") == "application/pdf"):
                        pdf_key = child["key"]
                        break
            except Exception:
                pass  # If children fetch fails, pdf_key remains None
            
            papers.append({
                "key": item["key"],
                "pdf_key": pdf_key,  # Child attachment key
                "title": data.get("title", "Untitled"),
                "authors": authors or "Unknown",
                "year": data.get("date", "")[:4] if data.get("date") else "N/A"
            })
        
        return papers
    except Exception as e:
        st.error(f"Failed to fetch items: {e}")
        return []


def find_pdf(storage_path: str, pdf_key: Optional[str]) -> Optional[Path]:
    """
    Find the PDF file using the attachment key.
    
    IMPORTANT: Use the child attachment key (not parent item key) to locate PDF.
    Zotero stores PDFs in: storage/{attachment_key}/*.pdf
    
    Args:
        storage_path: Base Zotero storage directory
        pdf_key: Zotero attachment (child) key
    
    Returns:
        Path to PDF file if found, None otherwise
    """
    if not pdf_key:
        return None
    
    item_dir = Path(storage_path) / pdf_key
    if not item_dir.exists():
        return None
    
    # Look for .pdf files
    pdf_files = list(item_dir.glob("*.pdf"))
    if pdf_files:
        return pdf_files[0]
    
    return None


def pdf_to_markdown(pdf_path: Path) -> str:
    """
    Convert PDF to Markdown using pymupdf4llm.
    
    Args:
        pdf_path: Path to PDF file
    
    Returns:
        Markdown text
    """
    try:
        md_text = pymupdf4llm.to_markdown(str(pdf_path))
        return md_text
    except Exception as e:
        raise RuntimeError(f"Failed to convert PDF to Markdown: {e}")


def clean_text(text: str) -> str:
    """
    Remove references/bibliography section from text.
    
    Args:
        text: Raw markdown text
    
    Returns:
        Cleaned text without references
    """
    # Pattern to match common reference section headers
    patterns = [
        r"\n#+\s*References?\s*\n",
        r"\n#+\s*Bibliography\s*\n",
        r"\n#+\s*参考文献\s*\n",
        r"\n#+\s*REFERENCES?\s*\n",
        r"\n##\s*References?\s*\n",
    ]
    
    for pattern in patterns:
        match = re.search(pattern, text, re.IGNORECASE)
        if match:
            # Cut everything from this point onward
            text = text[:match.start()]
            break
    
    return text.strip()


def analyze_paper_with_gemini(text: str, api_key: str, title: str) -> Dict:
    """
    Analyze paper and generate structured JSON output for Notion.
    
    Args:
        text: Paper content in markdown
        api_key: Gemini API key
        title: Paper title for context
    
    Returns:
        Dictionary with 'score', 'novelty', and 'category' keys
    """
    genai.configure(api_key=api_key)
    model = genai.GenerativeModel(GEMINI_MODEL)
    
    prompt = f"""
あなたは研究論文を評価する専門家AIです。

以下の論文を分析し、JSON形式で結果を出力してください。

## 論文タイトル
{title}

## 論文内容
{text[:80000]}

---

## 出力形式（必ずこのJSON形式で出力してください）

{{
  "score": <0-100の整数スコア>,
  "novelty": "<新規性の要約を200文字程度で記述>",
  "category": "<論文のカテゴリ（例: 機械学習、コンピュータビジョン、自然言語処理など）>"
}}

## 評価基準

- **score**: 論文の重要性・影響力を0-100で評価
  - 90-100: 画期的な成果
  - 70-89: 非常に優れた研究
  - 50-69: 良好な研究
  - 30-49: 平均的な研究
  - 0-29: 限定的な貢献

- **novelty**: 新規性の要点を簡潔に要約

- **category**: 論文の主要な研究分野。例：（Generative Models, Scenario Generation, Resilience Analysis）

JSONのみを出力してください（説明文は不要）。
"""
    
    try:
        response = model.generate_content(prompt)
        result_text = response.text.strip()
        
        # Extract JSON from response (handle markdown code blocks)
        if "```json" in result_text:
            result_text = result_text.split("```json")[1].split("```")[0].strip()
        elif "```" in result_text:
            result_text = result_text.split("```")[1].split("```")[0].strip()
        
        # Parse JSON
        result = json.loads(result_text)
        
        # Validate required keys
        required_keys = ["score", "novelty", "category"]
        if not all(key in result for key in required_keys):
            raise ValueError(f"Missing required keys. Expected: {required_keys}")
        
        return result
        
    except json.JSONDecodeError as e:
        raise RuntimeError(f"Failed to parse JSON from Gemini response: {e}\nResponse: {result_text}")
    except Exception as e:
        raise RuntimeError(f"Gemini API error: {e}")


def summarize_paper(text: str, api_key: str, title: str) -> str:
    """
    Generate detailed summary in markdown format.
    
    Args:
        text: Paper content in markdown
        api_key: Gemini API key
        title: Paper title
    
    Returns:
        Markdown summary
    """
    genai.configure(api_key=api_key)
    model = genai.GenerativeModel(GEMINI_MODEL)
    
    prompt = f"""
# Role
あなたは論文の査読経験が豊富なシニアリサーチャーです。

# Goal
提供された論文テキストを読み込み、以下のフォーマットに従って重要事項を構造化して出力してください。
私がこの論文を詳細に読むべきか、自分の研究に取り入れるべきかを判断するための材料とします。

# Title
{title}

# Input Text
{text[:80000]}

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
"""
    
    try:
        response = model.generate_content(prompt)
        return response.text
    except Exception as e:
        raise RuntimeError(f"Gemini API error: {e}")


def generate_slides(text: str, api_key: str, title: str, authors: str) -> str:
    """
    Generate Marp-compatible slide deck.
    
    Args:
        text: Paper content in markdown
        api_key: Gemini API key
        title: Paper title
        authors: Paper authors
    
    Returns:
        Marp markdown slides
    """
    genai.configure(api_key=api_key)
    model = genai.GenerativeModel(GEMINI_MODEL)
    
    prompt = f"""
あなたは学術プレゼンテーションスライドの専門家です。

以下の論文からMarp形式のスライド（5-8枚）を作成してください。

## 論文タイトル
{title}

## 著者
{authors}

## 論文内容
{text[:80000]}

---

## スライド構成
1. タイトルスライド
2. 背景と課題
3. 提案手法
4. 実験結果
5. 結論

## ルール
- `---` でスライドを区切る
- ヘッダーに `marp: true` を含める
- 箇条書きを使用
- 簡潔に

Marpスライドを生成してください。
"""
    
    try:
        response = model.generate_content(prompt)
        slide_text = response.text
        if "marp:" not in slide_text[:100]:
            slide_text = "---\nmarp: true\ntheme: default\n---\n\n" + slide_text
        return slide_text
    except Exception as e:
        raise RuntimeError(f"Gemini API error: {e}")


def markdown_to_notion_blocks(markdown_text: str) -> list:
    """
    Convert Markdown text to Notion block objects with nested list support.
    
    Supports:
    - ## headings -> heading_2
    - ### headings -> heading_3
    - * or - bullet points -> bulleted_list_item (with nesting via indentation)
    - **bold** text -> annotations with bold
    - Regular paragraphs -> paragraph
    
    Args:
        markdown_text: Markdown formatted text
    
    Returns:
        List of Notion block objects
    """
    blocks = []
    lines = markdown_text.split('\n')
    
    def parse_inline_formatting(text: str) -> list:
        """Parse **bold** formatting and return rich_text array."""
        rich_text = []
        parts = re.split(r'(\*\*[^*]+\*\*)', text)
        
        for part in parts:
            if not part:
                continue
            
            if part.startswith('**') and part.endswith('**'):
                # Bold text
                content = part[2:-2]
                if content:
                    rich_text.append({
                        "type": "text",
                        "text": {"content": content},
                        "annotations": {"bold": True}
                    })
            else:
                # Regular text
                if part:
                    rich_text.append({
                        "type": "text",
                        "text": {"content": part}
                    })
        
        return rich_text if rich_text else [{"type": "text", "text": {"content": text}}]
    
    def get_indent_level(line: str) -> int:
        """Calculate indentation level (number of leading spaces divided by 4)."""
        return (len(line) - len(line.lstrip())) // 4
    
    # Stack to track parent list items by indent level
    # Format: {indent_level: block_reference}
    parent_stack = {}
    
    for line in lines:
        if not line.strip():
            continue  # Skip empty lines
        
        # Heading 3 (###)
        if line.startswith('### '):
            heading_text = line[4:].strip()
            rich_text = parse_inline_formatting(heading_text)
            blocks.append({
                "object": "block",
                "type": "heading_3",
                "heading_3": {"rich_text": rich_text}
            })
            parent_stack.clear()  # Reset stack on non-list items
        
        # Heading 2 (##)
        elif line.startswith('## '):
            heading_text = line[3:].strip()
            rich_text = parse_inline_formatting(heading_text)
            blocks.append({
                "object": "block",
                "type": "heading_2",
                "heading_2": {"rich_text": rich_text}
            })
            parent_stack.clear()  # Reset stack on non-list items
        
        # Heading 1 (#)
        elif line.startswith('# ') and not line.startswith('##'):
            heading_text = line[2:].strip()
            rich_text = parse_inline_formatting(heading_text)
            blocks.append({
                "object": "block",
                "type": "heading_1",
                "heading_1": {"rich_text": rich_text}
            })
            parent_stack.clear()  # Reset stack on non-list items
        
        # Bulleted list (* or -)
        elif line.strip().startswith('* ') or line.strip().startswith('- '):
            indent_level = get_indent_level(line)
            bullet_text = line.strip()[2:].strip()
            rich_text = parse_inline_formatting(bullet_text)
            
            new_block = {
                "object": "block",
                "type": "bulleted_list_item",
                "bulleted_list_item": {"rich_text": rich_text}
            }
            
            # Determine where to add this block
            if indent_level == 0:
                # Top-level item
                blocks.append(new_block)
                parent_stack = {0: new_block}  # Reset stack to this item
            else:
                # Nested item - find parent
                parent_level = indent_level - 1
                
                # Find the closest parent at a lower indent level
                while parent_level >= 0 and parent_level not in parent_stack:
                    parent_level -= 1
                
                if parent_level >= 0 and parent_level in parent_stack:
                    # Add as child of parent
                    parent_block = parent_stack[parent_level]
                    
                    # Ensure parent has children array
                    if "children" not in parent_block["bulleted_list_item"]:
                        parent_block["bulleted_list_item"]["children"] = []
                    
                    parent_block["bulleted_list_item"]["children"].append(new_block)
                else:
                    # No valid parent found, add to top level
                    blocks.append(new_block)
                
                # Update stack with current item
                parent_stack[indent_level] = new_block
                
                # Remove deeper levels from stack
                keys_to_remove = [k for k in parent_stack.keys() if k > indent_level]
                for k in keys_to_remove:
                    del parent_stack[k]
        
        # Regular paragraph
        else:
            rich_text = parse_inline_formatting(line.strip())
            blocks.append({
                "object": "block",
                "type": "paragraph",
                "paragraph": {"rich_text": rich_text}
            })
            parent_stack.clear()  # Reset stack on non-list items
    
    return blocks


def update_notion_page(title: str, ai_result: Dict, notion_token: str, database_id: str, summary: str = "") -> bool:
    """
    Update Notion page with AI analysis results and summary content.
    
    Args:
        title: Paper title to search for
        ai_result: Dictionary with 'score', 'novelty', 'category' keys
        notion_token: Notion API token
        database_id: Notion database ID
        summary: Optional markdown summary to append to page body
    
    Returns:
        True if successful, False otherwise
    """
    if not notion_token or not database_id:
        st.warning("⚠️ Notion credentials not configured. Skipping Notion update.")
        return False
    
    try:
        notion = Client(auth=notion_token)
        
        # Step 1: Search for page by title
        st.info(f"🔍 Searching Notion for: {title}")
        
        search_results = notion.data_sources.query(
            data_source_id=database_id,
            filter={
                "property": "Title",
                "title": {
                    "equals": title
                }
            }
        )
        
        if not search_results["results"]:
            st.warning(f"⚠️ No Notion page found for: {title}")
            return False
        
        page_id = search_results["results"][0]["id"]
        st.success(f"✅ Found Notion page: {page_id[:8]}...")
        
        # Step 2: Update page properties
        st.info("📝 Updating Notion page...")
        
        notion.pages.update(
            page_id=page_id,
            properties={
                "AI Score": {
                    "number": int(ai_result.get("score", 0))
                },
                "Novelty": {
                    "rich_text": [
                        {
                            "type": "text",
                            "text": {
                                "content": str(ai_result.get("novelty", ""))[:2000]
                            }
                        }
                    ]
                },
                "Category": {
                    "rich_text": [
                        {
                            "type": "text",
                            "text": {
                                "content": str(ai_result.get("category", ""))[:2000]
                            }
                        }
                    ]
                }
            }
        )
        
        st.success(f"✅ Notion page properties updated!")
        
        # Step 3: Append summary to page body if provided
        if summary:
            st.info("📝 Appending summary to page body...")
            
            # Convert markdown summary to Notion blocks
            summary_blocks = []
            
            # Add a divider
            summary_blocks.append({
                "object": "block",
                "type": "divider",
                "divider": {}
            })
            
            # Add heading
            summary_blocks.append({
                "object": "block",
                "type": "heading_2",
                "heading_2": {
                    "rich_text": [{
                        "type": "text",
                        "text": {"content": "🤖 AI Generated Summary"}
                    }]
                }
            })
            
            # Add summary as paragraph blocks (preserves markdown as plain text)
            # Split by character limit (2000 chars per block)
            # Convert markdown to properly formatted Notion blocks
            converted_blocks = markdown_to_notion_blocks(summary)
            summary_blocks.extend(converted_blocks)
            
            # Notion API has a limit of 100 blocks per append call
            # Split into chunks if necessary
            chunk_size = 100
            for i in range(0, len(summary_blocks), chunk_size):
                chunk = summary_blocks[i:i+chunk_size]
                notion.blocks.children.append(
                    block_id=page_id,
                    children=chunk
                )
            
            st.success(f"✅ Summary appended to page ({len(converted_blocks)} blocks)")
        
        st.success(f"✅ Notion page fully updated!")
        return True
        
    except Exception as e:
        st.error(f"❌ Notion update failed: {e}")
        import traceback
        st.code(traceback.format_exc(), language="python")
        return False


def safe_filename(name: str) -> str:
    """Create a safe filename from paper title."""
    # Remove or replace invalid characters
    name = re.sub(r'[<>:"/\\|?*]', '', name)
    name = name.replace(' ', '_')
    return name[:100]  # Limit length


def save_outputs(title: str, summary: str, slides: str) -> Tuple[Path, Path]:
    """
    Save summary and slides to output directory.
    
    Returns:
        Tuple of (summary_path, slides_path)
    """
    safe_title = safe_filename(title)
    output_folder = OUTPUT_DIR / safe_title
    output_folder.mkdir(exist_ok=True)
    
    summary_path = output_folder / "summary.md"
    slides_path = output_folder / "slides.md"
    
    summary_path.write_text(summary, encoding="utf-8")
    slides_path.write_text(slides, encoding="utf-8")
    
    return summary_path, slides_path


# ==================== Streamlit UI ====================

def main():
    st.set_page_config(
        page_title="Paper Summarizer - Zotero + Gemini",
        page_icon="📚",
        layout="wide"
    )
    
    st.title("📚 Paper Summarizer with Zotero + Notion")
    st.markdown("""
    Select papers from your Zotero collections and generate AI-powered summaries and slides.
    
    **🚀 Features:**
    - **AI Analysis:** Gemini 1.5 Flash for cost-efficient analysis
    - **Notion Integration:** Auto-update Notion database with AI scores
    - **Rate Limit Protection:** 4-second delay between API calls
    """)
    
    # ========== Sidebar: Configuration ==========
    with st.sidebar:
        st.header("⚙️ Configuration")
        
        library_id = st.text_input(
            "Zotero Library ID",
            value=os.getenv("ZOTERO_LIBRARY_ID", ""),
            type="default"
        )
        
        api_key_zotero = st.text_input(
            "Zotero API Key",
            value=os.getenv("ZOTERO_API_KEY", ""),
            type="password"
        )
        
        gemini_api_key = st.text_input(
            "Gemini API Key",
            value=os.getenv("GEMINI_API_KEY", ""),
            type="password"
        )
        
        st.divider()
        
        st.subheader("🔗 Notion Integration")
        
        notion_token = st.text_input(
            "Notion Token",
            value=NOTION_TOKEN,
            type="password",
            help="Notion API token (optional)"
        )
        
        notion_database_id = st.text_input(
            "Notion Database ID",
            value=NOTION_DATABASE_ID,
            help="Notion database ID (optional)"
        )
        
        st.divider()
        
        storage_path = st.text_input(
            "Local Zotero Storage Path",
            value=DEFAULT_ZOTERO_STORAGE,
            help="Path to your Zotero storage folder (e.g., C:\\Users\\...\\Zotero\\storage)"
        )
        
        library_type = st.selectbox(
            "Library Type",
            options=["user", "group"],
            index=0
        )
        
        st.divider()
        
        # Model information
        st.subheader("🤖 AI Model")
        st.caption(f"**Model:** {GEMINI_MODEL}")
        st.caption(f"**Rate Limit:** {RATE_LIMIT_DELAY}s delay between calls")
        st.info("💡 Cost-efficient single-stage processing")
        
        st.divider()
        
        # Output mode
        output_mode = st.radio(
            "Output Mode",
            options=["Both (Summary + Slides)", "Summary Only", "Slides Only"],
            index=0
        )
    
    # ========== Main Area ==========
    
    # Validation
    if not all([library_id, api_key_zotero, gemini_api_key]):
        st.warning("⚠️ Please fill in all API credentials in the sidebar.")
        return
    
    # Step 1: Select Collection
    st.header("1️⃣ Select Collection")
    
    if st.button("🔄 Fetch Collections", use_container_width=True):
        with st.spinner("Fetching collections..."):
            collections = get_collections(library_id, api_key_zotero, library_type)
            if collections:
                st.session_state["collections"] = collections
                st.success(f"Found {len(collections)} collections.")
            else:
                st.error("No collections found or failed to fetch.")
    
    if "collections" not in st.session_state:
        st.info("👆 Click 'Fetch Collections' to start.")
        return
    
    collections = st.session_state["collections"]
    collection_names = [c["name"] for c in collections]
    
    selected_collection_name = st.selectbox(
        "Choose a collection:",
        options=collection_names
    )
    
    selected_collection = next(
        (c for c in collections if c["name"] == selected_collection_name),
        None
    )
    
    if not selected_collection:
        return
    
    # Step 2: Display Papers
    st.header("2️⃣ Select Papers")
    
    if st.button("📄 Load Papers", use_container_width=True):
        with st.spinner("Loading papers..."):
            papers = get_items_in_collection(
                library_id, api_key_zotero, selected_collection["key"], library_type
            )
            if papers:
                st.session_state["papers"] = papers
                st.success(f"Loaded {len(papers)} papers.")
            else:
                st.warning("No papers found in this collection.")
    
    if "papers" not in st.session_state:
        return
    
    papers = st.session_state["papers"]
    
    # Display papers with checkboxes
    st.subheader("Available Papers")
    
    selected_papers = []
    for idx, paper in enumerate(papers):
        col1, col2 = st.columns([0.1, 0.9])
        with col1:
            if st.checkbox("", key=f"paper_{idx}"):
                selected_papers.append(paper)
        with col2:
            st.markdown(f"**{paper['title']}**")
            st.caption(f"_{paper['authors']}_ ({paper['year']})")
    
    st.divider()
    
    # Step 3: Execute Summarization
    st.header("3️⃣ Generate Summaries")
    
    if not selected_papers:
        st.info("✅ Select one or more papers above to proceed.")
        return
    
    st.write(f"**Selected:** {len(selected_papers)} paper(s)")
    
    if st.button("🚀 Start Summarization", type="primary", use_container_width=True):
        progress_bar = st.progress(0)
        status_text = st.empty()
        
        results = []
        
        for idx, paper in enumerate(selected_papers):
            status_text.text(f"Processing: {paper['title']} ({idx+1}/{len(selected_papers)})")
            
            # Find PDF using attachment key
            pdf_path = find_pdf(storage_path, paper.get("pdf_key"))
            if not pdf_path:
                st.error(f"❌ PDF not found for: {paper['title']}")
                results.append({
                    "paper": paper,
                    "status": "failed",
                    "reason": "PDF not found"
                })
                continue
            
            try:
                # Convert to markdown
                with st.spinner(f"📄 Converting PDF to Markdown..."):
                    md_text = pdf_to_markdown(pdf_path)
                
                # Clean text
                cleaned_text = clean_text(md_text)
                
                # AI Analysis for Notion
                with st.spinner(f"🤖 Analyzing paper with {GEMINI_MODEL}..."):
                    ai_result = analyze_paper_with_gemini(cleaned_text, gemini_api_key, paper["title"])
                
                st.success(f"✅ AI Analysis complete: Score={ai_result.get('score')}, Category={ai_result.get('category')}")
                
                # Generate outputs based on mode
                summary = None
                slides = None
                
                if output_mode in ["Both (Summary + Slides)", "Summary Only"]:
                    with st.spinner(f"📝 Generating summary..."):
                        summary = summarize_paper(cleaned_text, gemini_api_key, paper["title"])
                
                # Update Notion if credentials provided (after generating summary)
                if notion_token and notion_database_id:
                    update_notion_page(
                        paper["title"], 
                        ai_result, 
                        notion_token, 
                        notion_database_id,
                        summary=summary or ""  # Pass summary to write to page body
                    )
                
                if output_mode in ["Both (Summary + Slides)", "Slides Only"]:
                    with st.spinner(f"🎞️ Generating slides..."):
                        slides = generate_slides(
                            cleaned_text, 
                            gemini_api_key, 
                            paper["title"],
                            paper["authors"]
                        )
                
                # Save outputs
                if summary or slides:
                    summary_path, slides_path = save_outputs(
                        paper["title"],
                        summary or "",
                        slides or ""
                    )
                    
                    results.append({
                        "paper": paper,
                        "status": "success",
                        "ai_result": ai_result,
                        "summary": summary,
                        "slides": slides,
                        "summary_path": summary_path if summary else None,
                        "slides_path": slides_path if slides else None
                    })
                    
                    st.success(f"✅ Completed: {paper['title']}")
                
            except Exception as e:
                st.error(f"❌ Error processing {paper['title']}: {e}")
                results.append({
                    "paper": paper,
                    "status": "failed",
                    "reason": str(e)
                })
            
            progress_bar.progress((idx + 1) / len(selected_papers))
            
            # Rate limit protection: wait before next iteration
            if idx < len(selected_papers) - 1:  # Don't wait after last paper
                st.info(f"⏳ Waiting {RATE_LIMIT_DELAY}s to avoid rate limits...")
                time.sleep(RATE_LIMIT_DELAY)
        
        status_text.text("✅ All papers processed!")
        st.session_state["results"] = results
    
    # Step 4: Display Results
    if "results" in st.session_state:
        st.header("4️⃣ Results")
        
        for result in st.session_state["results"]:
            paper = result["paper"]
            
            if result["status"] == "success":
                with st.expander(f"✅ {paper['title']}", expanded=False):
                    
                    # AI Analysis Results
                    if result.get("ai_result"):
                        st.subheader("🤖 AI Analysis")
                        ai_res = result["ai_result"]
                        col1, col2 = st.columns(2)
                        with col1:
                            st.metric("AI Score", ai_res.get("score", "N/A"))
                        with col2:
                            st.metric("Category", ai_res.get("category", "N/A"))
                        st.write("**Novelty:**")
                        st.write(ai_res.get("novelty", "N/A"))
                    
                    st.divider()
                    
                    # Summary preview
                    if result.get("summary"):
                        st.subheader("📝 Summary")
                        st.markdown(result["summary"])
                        st.caption(f"Saved to: `{result['summary_path']}`")
                    
                    st.divider()
                    
                    # Slides preview
                    if result.get("slides"):
                        st.subheader("🎞️ Slides (Marp)")
                        st.code(result["slides"][:1000] + "\n...", language="markdown")
                        st.caption(f"Saved to: `{result['slides_path']}`")
                        st.info("💡 Use Marp CLI or VS Code extension to render slides as PDF.")
            
            else:
                with st.expander(f"❌ {paper['title']} - Failed"):
                    st.error(f"Reason: {result.get('reason', 'Unknown error')}")


if __name__ == "__main__":
    main()
