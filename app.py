"""
Paper Summarizer with Zotero Integration
=========================================
A Streamlit app to summarize papers from Zotero collections using Gemini LLM.
"""

import os
import re
from pathlib import Path
from typing import List, Dict, Optional, Tuple
import streamlit as st
from pyzotero import zotero
import pymupdf4llm
import google.generativeai as genai
from dotenv import load_dotenv
from tenacity import (
    retry,
    stop_after_attempt,
    wait_fixed,
    retry_if_exception_type
)

# Load environment variables
load_dotenv()

# ==================== Configuration ====================

DEFAULT_ZOTERO_STORAGE = os.getenv(
    "ZOTERO_STORAGE_PATH",
    r"C:\Users\echiz\Zotero\storage"
)

OUTPUT_DIR = Path("./output")
OUTPUT_DIR.mkdir(exist_ok=True)

# Two-stage model configuration
FLASH_MODEL = "gemini-2.0-flash-exp"  # Fast information extraction
PRO_MODEL = "gemini-2.0-pro-exp"      # Advanced reasoning
MAX_RETRIES = 5
RETRY_WAIT_SECONDS = 50  # Increased from 40 to handle quota delays


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


@retry(
    retry=retry_if_exception_type(Exception),
    stop=stop_after_attempt(MAX_RETRIES),
    wait=wait_fixed(RETRY_WAIT_SECONDS),
    reraise=True
)
def extract_paper_info(text: str, api_key: str, title: str) -> str:
    """
    Stage 1: Extract high-resolution information using Flash model with retry logic.
    
    Args:
        text: Paper content in markdown
        api_key: Gemini API key
        title: Paper title for context
    
    Returns:
        Detailed extracted information
    """
    genai.configure(api_key=api_key)
    flash_model = genai.GenerativeModel(FLASH_MODEL)
    
    extraction_prompt = f"""
あなたは上位モデルへ情報を渡すための「高解像度情報抽出器」です。

論文タイトル: {title}

以下の論文テキストから、一切の情報を省略せず、以下の要素を構造化して抽出してください:

1. **研究の核心的な目的と新規性**
2. **提案手法の技術的詳細**（数式、アルゴリズム、アーキテクチャ）
3. **実験設定の詳細**（データセット、評価メトリクス、ベースライン）
4. **実験結果の具体的な数値**（SOTA比較、アブレーション）
5. **議論と限界点**

重要: 要約せず、Proモデルが原文を読んだのと同じレベルで推論できるよう詳細に記述してください。

---

{text[:100000]}

---

上記の論文から高解像度の情報を抽出してください。
"""
    
    try:
        response = flash_model.generate_content(extraction_prompt)
        return response.text
    except Exception as e:
        error_msg = str(e)
        if "429" in error_msg or "RESOURCE_EXHAUSTED" in error_msg or "quota" in error_msg.lower():
            # Extract retry delay from error message if available
            import re
            retry_match = re.search(r'retry in (\d+\.?\d*)', error_msg)
            suggested_wait = int(float(retry_match.group(1))) if retry_match else RETRY_WAIT_SECONDS
            
            st.warning(f"⏳ Flash model rate limit: Will retry in {max(suggested_wait, RETRY_WAIT_SECONDS)}s...")
            raise  # Let tenacity handle retry
        raise RuntimeError(f"Flash model error: {e}")


@retry(
    retry=retry_if_exception_type(Exception),
    stop=stop_after_attempt(MAX_RETRIES),
    wait=wait_fixed(RETRY_WAIT_SECONDS),
    reraise=True
)
def summarize_paper(extracted_info: str, api_key: str, title: str) -> str:
    """
    Stage 2: Generate detailed summary using Pro model with retry logic.
    
    Args:
        extracted_info: Information extracted in Stage 1
        api_key: Gemini API key
        title: Paper title for context
    
    Returns:
        Summary text in markdown
    """
    genai.configure(api_key=api_key)
    pro_model = genai.GenerativeModel(PRO_MODEL)
    
    prompt = f"""
あなたは研究論文の専門家AIです。

以下に論文から抽出された詳細情報があります。
これを基に、構造化された要約を作成してください。

## 要約の構成

1. **背景と動機**: この論文が解決する問題は?
2. **主要な貢献**: 重要な革新や発見は?
3. **手法**: アプローチの詳細（数式・アルゴリズム含む）
4. **実験結果**: 主要な実験結果と数値
5. **結論と今後の課題**: 要点と次のステップ

---

## 論文タイトル
{title}

## 抽出された詳細情報

{extracted_info}

---

Markdown形式で詳細な要約を作成してください。
"""
    
    try:
        response = pro_model.generate_content(prompt)
        return response.text
    except Exception as e:
        error_msg = str(e)
        if "429" in error_msg or "RESOURCE_EXHAUSTED" in error_msg or "quota" in error_msg.lower():
            import re
            retry_match = re.search(r'retry in (\d+\.?\d*)', error_msg)
            suggested_wait = int(float(retry_match.group(1))) if retry_match else RETRY_WAIT_SECONDS
            st.warning(f"⏳ Pro model rate limit: Will retry in {max(suggested_wait, RETRY_WAIT_SECONDS)}s...")
            raise  # Let tenacity handle retry
        raise RuntimeError(f"Pro model error: {e}")


@retry(
    retry=retry_if_exception_type(Exception),
    stop=stop_after_attempt(MAX_RETRIES),
    wait=wait_fixed(RETRY_WAIT_SECONDS),
    reraise=True
)
def generate_slides(extracted_info: str, api_key: str, title: str, authors: str) -> str:
    """
    Stage 2: Generate Marp-compatible slide deck using Pro model with retry logic.
    
    Args:
        extracted_info: Information extracted in Stage 1
        api_key: Gemini API key
        title: Paper title
        authors: Paper authors
    
    Returns:
        Marp markdown slides
    """
    genai.configure(api_key=api_key)
    pro_model = genai.GenerativeModel(PRO_MODEL)
    
    prompt = f"""
あなたは学術プレゼンテーションスライドの専門家です。

以下の論文情報から、Marp形式のスライド（5-8枚）を作成してください。

## スライド構成
1. タイトルスライド（タイトル、著者）
2. 背景と課題
3. 提案手法
4. 実験結果
5. 結論

## ルール
- `---` でスライドを区切る
- ヘッダーに `marp: true` を含める
- 箇条書きを使用（段落は避ける）
- テキストは簡潔に
- 数式や重要な数値を含める

---

## 論文タイトル
{title}

## 著者
{authors}

## 抽出された詳細情報

{extracted_info}

---

Marpスライドを生成してください。
"""
    
    try:
        response = pro_model.generate_content(prompt)
        slide_text = response.text
        # Ensure marp header is present
        if "marp:" not in slide_text[:100]:
            slide_text = "---\nmarp: true\ntheme: default\n---\n\n" + slide_text
        return slide_text
    except Exception as e:
        error_msg = str(e)
        if "429" in error_msg or "RESOURCE_EXHAUSTED" in error_msg or "quota" in error_msg.lower():
            import re
            retry_match = re.search(r'retry in (\d+\.?\d*)', error_msg)
            suggested_wait = int(float(retry_match.group(1))) if retry_match else RETRY_WAIT_SECONDS
            st.warning(f"⏳ Pro model rate limit: Will retry in {max(suggested_wait, RETRY_WAIT_SECONDS)}s...")
            raise  # Let tenacity handle retry
        raise RuntimeError(f"Pro model error: {e}")


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
    
    st.title("📚 Paper Summarizer with Zotero")
    st.markdown("""
    Select papers from your Zotero collections and generate AI-powered summaries and slides.
    
    **🚀 Two-Stage AI Processing:**
    - **Stage 1 (Flash):** High-speed detailed information extraction
    - **Stage 2 (Pro):** Advanced reasoning with automatic retry for rate limits
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
        st.caption(f"**Stage 1:** {FLASH_MODEL}")
        st.caption("Fast information extraction (50s retry)")
        st.caption(f"**Stage 2:** {PRO_MODEL}")
        st.caption(f"Advanced reasoning (50s retry)")
        st.info("⚠️ Both models have rate limits. Auto-retry with 50s wait on quota errors.")
        
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
                
                # Stage 1: Extract high-resolution information (Flash model)
                with st.spinner(f"🔍 Stage 1: Extracting detailed information ({FLASH_MODEL})..."):
                    extracted_info = extract_paper_info(cleaned_text, gemini_api_key, paper["title"])
                
                st.info(f"✅ Stage 1 complete. Extracted {len(extracted_info)} characters.")
                
                # Stage 2: Generate outputs based on mode (Pro model with retry)
                summary = None
                slides = None
                
                if output_mode in ["Both (Summary + Slides)", "Summary Only"]:
                    with st.spinner(f"📝 Stage 2: Generating summary ({PRO_MODEL})..."):
                        summary = summarize_paper(extracted_info, gemini_api_key, paper["title"])
                
                if output_mode in ["Both (Summary + Slides)", "Slides Only"]:
                    with st.spinner(f"🎞️ Stage 2: Generating slides ({PRO_MODEL})..."):
                        slides = generate_slides(
                            extracted_info, 
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
        
        status_text.text("✅ All papers processed!")
        st.session_state["results"] = results
    
    # Step 4: Display Results
    if "results" in st.session_state:
        st.header("4️⃣ Results")
        
        for result in st.session_state["results"]:
            paper = result["paper"]
            
            if result["status"] == "success":
                with st.expander(f"✅ {paper['title']}", expanded=False):
                    
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
