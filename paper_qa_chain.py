"""
Two-Stage Paper Q&A System with Gemini API
===========================================

Architecture:
1. Stage 1 (Flash Model): High-resolution information extraction from full paper text
2. Stage 2 (Pro Model): Reasoning and question answering with retry logic for rate limits

Usage:
    python paper_qa_chain.py
"""

import os
from typing import Dict, Optional
import google.generativeai as genai
from tenacity import (
    retry,
    stop_after_attempt,
    wait_fixed,
    retry_if_exception_type
)


# ==================== Configuration ====================

# API Key from environment
GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY")
if not GEMINI_API_KEY:
    raise ValueError("GEMINI_API_KEY environment variable is required")

genai.configure(api_key=GEMINI_API_KEY)

# Model names
FLASH_MODEL = "gemini-2.0-flash-exp"  # For information extraction
PRO_MODEL = "gemini-2.0-pro-exp"      # For reasoning and answering

# Retry configuration for Pro model (handles 429 rate limit errors)
MAX_RETRIES = 5
RETRY_WAIT_SECONDS = 40


# ==================== Stage 1: Information Extraction (Flash) ====================

EXTRACTION_PROMPT = """あなたは上位モデルへ情報を渡すための「高解像度情報抽出器」です。

入力された論文テキストから、一切の情報を省略せず、以下の要素を構造化して抽出してください。

## 抽出する情報

1. **研究の核心的な目的と新規性**
   - 論文が解決しようとする問題は何か
   - 既存手法との違いは何か
   - どのような新規性・貢献があるか

2. **提案手法の技術的詳細**
   - 数式の定義（すべての変数の意味を含む）
   - アルゴリズムのステップ（疑似コードレベルの詳細）
   - アーキテクチャの全構成要素（レイヤー、モジュール、接続関係）
   - ハイパーパラメータと設定値

3. **実験設定の詳細**
   - データセット名とその特性（サイズ、クラス数、分割方法）
   - 前処理とデータ拡張の手法
   - 評価メトリクスの定義
   - 比較対象となるベースラインモデル
   - 実験環境（ハードウェア、ソフトウェア）

4. **実験結果の具体的な数値**
   - すべてのメトリクスの値（平均、標準偏差を含む）
   - SOTA（State-of-the-Art）との比較
   - アブレーションスタディの結果
   - 統計的有意性の検定結果

5. **議論と限界点**
   - 結果の解釈と考察
   - 手法の限界や失敗ケース
   - 今後の改善方向

## 重要な指示

- **要約して短くする必要はありません**
- Proモデルが「原文を読んだ」のと同じレベルで推論できるよう、事実は詳細に記述してください
- 数式や表の内容は可能な限り正確に転記してください
- 曖昧な表現は避け、具体的な数値や定義を優先してください

---

## 論文テキスト

{paper_text}

---

上記の論文から、指示に従って高解像度の情報を抽出してください。
"""


def extract_high_resolution_info(paper_text: str) -> str:
    """
    Stage 1: Extract high-resolution information from paper text using Flash model.
    
    This function uses the fast Flash model to comprehensively extract all relevant
    information from the paper without summarization. The output is designed to be
    consumed by the Pro model for reasoning.
    
    Args:
        paper_text: Full text of the research paper
        
    Returns:
        Structured, detailed information extracted from the paper
        
    Raises:
        Exception: If API call fails
    """
    print(f"[Stage 1] Extracting information using {FLASH_MODEL}...")
    
    # Initialize Flash model
    flash_model = genai.GenerativeModel(FLASH_MODEL)
    
    # Prepare prompt
    prompt = EXTRACTION_PROMPT.format(paper_text=paper_text)
    
    # Generate extraction
    try:
        response = flash_model.generate_content(prompt)
        extracted_info = response.text
        
        print(f"[Stage 1] Extraction complete. Length: {len(extracted_info)} characters")
        return extracted_info
        
    except Exception as e:
        print(f"[Stage 1] Error during extraction: {e}")
        raise


# ==================== Stage 2: Reasoning & Q&A (Pro with Retry) ====================

QA_PROMPT = """あなたは研究論文の内容について深く推論し、質問に答える専門家AIです。

以下に、論文から抽出された詳細な情報コンテキストが与えられます。
このコンテキストを基に、ユーザーの質問に対して正確かつ詳細に回答してください。

## 重要な指示

- 回答には必ず根拠となる情報（数値、数式、実験結果など）を含めてください
- 推測が必要な場合は、その旨を明示してください
- 情報が不足している場合は「情報が不足しています」と明記してください
- 技術的な質問には、数式や定義を用いて厳密に説明してください

---

## 論文の詳細コンテキスト

{extracted_info}

---

## ユーザーの質問

{question}

---

上記の質問に対して、コンテキストに基づいて詳細に回答してください。
"""


@retry(
    retry=retry_if_exception_type(Exception),
    stop=stop_after_attempt(MAX_RETRIES),
    wait=wait_fixed(RETRY_WAIT_SECONDS),
    reraise=True
)
def answer_question_with_retry(extracted_info: str, question: str) -> str:
    """
    Stage 2: Answer question using Pro model with automatic retry on rate limit errors.
    
    This function uses the Pro model for advanced reasoning. It includes retry logic
    with 40-second wait intervals to handle rate limit (429) errors from the API.
    
    Args:
        extracted_info: Detailed information extracted in Stage 1
        question: User's question about the paper
        
    Returns:
        Detailed answer to the question
        
    Raises:
        Exception: If all retry attempts fail
    """
    print(f"[Stage 2] Answering question using {PRO_MODEL}...")
    
    try:
        # Initialize Pro model
        pro_model = genai.GenerativeModel(PRO_MODEL)
        
        # Prepare prompt
        prompt = QA_PROMPT.format(
            extracted_info=extracted_info,
            question=question
        )
        
        # Generate answer
        response = pro_model.generate_content(prompt)
        answer = response.text
        
        print(f"[Stage 2] Answer generated. Length: {len(answer)} characters")
        return answer
        
    except Exception as e:
        error_msg = str(e)
        
        # Check if it's a rate limit error
        if "429" in error_msg or "RESOURCE_EXHAUSTED" in error_msg:
            print(f"[Stage 2] Rate limit error detected. Waiting {RETRY_WAIT_SECONDS}s before retry...")
            raise  # Let tenacity handle the retry
        else:
            print(f"[Stage 2] Error: {error_msg}")
            raise


# ==================== Main Pipeline ====================

def analyze_paper_and_answer(paper_text: str, question: str) -> Dict[str, str]:
    """
    Complete two-stage pipeline for paper analysis and question answering.
    
    Pipeline:
    1. Extract high-resolution information using Flash model (fast, no rate limits)
    2. Answer question using Pro model with extracted context (with retry logic)
    
    Args:
        paper_text: Full text of the research paper
        question: User's question about the paper
        
    Returns:
        Dictionary containing:
        - extracted_info: Detailed extracted information
        - answer: Answer to the question
        
    Raises:
        Exception: If pipeline fails after all retries
    """
    print("=" * 80)
    print("Starting Two-Stage Paper Q&A Pipeline")
    print("=" * 80)
    
    # Stage 1: Information Extraction
    extracted_info = extract_high_resolution_info(paper_text)
    
    print("\n" + "-" * 80 + "\n")
    
    # Stage 2: Question Answering with Retry
    answer = answer_question_with_retry(extracted_info, question)
    
    print("\n" + "=" * 80)
    print("Pipeline Complete")
    print("=" * 80 + "\n")
    
    return {
        "extracted_info": extracted_info,
        "answer": answer
    }


# ==================== Example Usage ====================

def main():
    """
    Example usage of the two-stage paper Q&A system.
    
    This example demonstrates:
    1. Loading a sample paper text
    2. Asking a question about the paper
    3. Receiving a detailed answer
    """
    
    # Example paper text (replace with actual paper content)
    sample_paper_text = """
    [Title] Attention Is All You Need
    
    [Abstract]
    The dominant sequence transduction models are based on complex recurrent or 
    convolutional neural networks that include an encoder and a decoder. The best 
    performing models also connect the encoder and decoder through an attention 
    mechanism. We propose a new simple network architecture, the Transformer, 
    based solely on attention mechanisms, dispensing with recurrence and convolutions 
    entirely.
    
    [Introduction]
    Recurrent neural networks (RNNs), long short-term memory (LSTM), and gated 
    recurrent units (GRUs) have been firmly established as state of the art approaches 
    in sequence modeling and transduction problems such as language modeling and 
    machine translation. Numerous efforts have since continued to push the boundaries 
    of recurrent language models and encoder-decoder architectures.
    
    [Model Architecture]
    The Transformer follows this overall architecture using stacked self-attention 
    and point-wise, fully connected layers for both the encoder and decoder.
    
    Encoder: The encoder is composed of a stack of N = 6 identical layers. Each 
    layer has two sub-layers. The first is a multi-head self-attention mechanism, 
    and the second is a simple, position-wise fully connected feed-forward network.
    
    Decoder: The decoder is also composed of a stack of N = 6 identical layers. 
    In addition to the two sub-layers in each encoder layer, the decoder inserts 
    a third sub-layer, which performs multi-head attention over the output of the 
    encoder stack.
    
    Attention mechanism: An attention function can be described as mapping a query 
    and a set of key-value pairs to an output. We compute the attention as:
    
    Attention(Q, K, V) = softmax(QK^T / sqrt(d_k))V
    
    [Experiments]
    We trained on the standard WMT 2014 English-German dataset consisting of about 
    4.5 million sentence pairs. We used byte-pair encoding with a shared source-target 
    vocabulary of about 37000 tokens. On the WMT 2014 English-to-German translation 
    task, our model achieves 28.4 BLEU, improving over the existing best results by 
    over 2 BLEU points.
    
    [Conclusion]
    In this work, we presented the Transformer, the first sequence transduction model 
    based entirely on attention, replacing the recurrent layers most commonly used in 
    encoder-decoder architectures with multi-headed self-attention.
    """
    
    # Example question
    sample_question = "このTransformerモデルのアーキテクチャについて、EncoderとDecoderの構成を詳しく説明してください。また、Attention機構の数式も含めて教えてください。"
    
    print("Sample Paper Analysis")
    print("=" * 80)
    print(f"Question: {sample_question}\n")
    
    try:
        # Run the pipeline
        result = analyze_paper_and_answer(sample_paper_text, sample_question)
        
        # Display results
        print("\n" + "=" * 80)
        print("RESULTS")
        print("=" * 80)
        
        print("\n[Extracted Information (Stage 1)]")
        print("-" * 80)
        print(result["extracted_info"][:500] + "...\n")  # Show first 500 chars
        
        print("[Answer (Stage 2)]")
        print("-" * 80)
        print(result["answer"])
        
    except Exception as e:
        print(f"\n[ERROR] Pipeline failed: {e}")
        raise


if __name__ == "__main__":
    main()
