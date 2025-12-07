"""
Paper Q&A Chain with PDF Integration
=====================================

This script demonstrates how to use the two-stage Q&A system with actual PDF files.
It combines pymupdf4llm for PDF parsing with the chain-of-models approach.

Usage:
    python paper_qa_pdf.py <pdf_path> <question>
    
Example:
    python paper_qa_pdf.py transformer_paper.pdf "Attention機構の数式を説明してください"
"""

import sys
import os
from pathlib import Path
import pymupdf4llm
from paper_qa_chain import analyze_paper_and_answer


def clean_markdown_text(text: str) -> str:
    """
    Clean extracted markdown text by removing references section.
    
    Args:
        text: Raw markdown text from PDF
        
    Returns:
        Cleaned text without references
    """
    import re
    
    # Patterns to match reference sections
    patterns = [
        r"\n#+\s*References?\s*\n",
        r"\n#+\s*Bibliography\s*\n",
        r"\n#+\s*参考文献\s*\n",
        r"\n#+\s*REFERENCES?\s*\n",
    ]
    
    for pattern in patterns:
        match = re.search(pattern, text, re.IGNORECASE)
        if match:
            text = text[:match.start()]
            break
    
    return text.strip()


def process_pdf_and_answer(pdf_path: str, question: str) -> dict:
    """
    Process a PDF file and answer a question about it.
    
    Pipeline:
    1. Convert PDF to Markdown using pymupdf4llm
    2. Clean the text (remove references)
    3. Run two-stage Q&A pipeline
    
    Args:
        pdf_path: Path to PDF file
        question: Question about the paper
        
    Returns:
        Dictionary with extracted_info and answer
    """
    print(f"Processing PDF: {pdf_path}")
    print("=" * 80)
    
    # Step 1: Convert PDF to Markdown
    print("[PDF Processing] Converting PDF to Markdown...")
    try:
        md_text = pymupdf4llm.to_markdown(pdf_path)
        print(f"[PDF Processing] Conversion complete. Length: {len(md_text)} characters")
    except Exception as e:
        raise RuntimeError(f"Failed to convert PDF: {e}")
    
    # Step 2: Clean text
    print("[PDF Processing] Cleaning text (removing references)...")
    cleaned_text = clean_markdown_text(md_text)
    print(f"[PDF Processing] Cleaned length: {len(cleaned_text)} characters")
    
    print("\n" + "-" * 80 + "\n")
    
    # Step 3: Run Q&A pipeline
    result = analyze_paper_and_answer(cleaned_text, question)
    
    return result


def interactive_mode(pdf_path: str):
    """
    Interactive Q&A mode for a single paper.
    
    Allows users to ask multiple questions about the same paper
    without re-processing the PDF each time.
    
    Args:
        pdf_path: Path to PDF file
    """
    print("\n" + "=" * 80)
    print("INTERACTIVE MODE")
    print("=" * 80)
    print("Processing PDF once, then you can ask multiple questions.")
    print("Type 'exit' or 'quit' to end the session.\n")
    
    # Convert and clean PDF once
    print("[Setup] Converting PDF to Markdown...")
    md_text = pymupdf4llm.to_markdown(pdf_path)
    cleaned_text = clean_markdown_text(md_text)
    
    print("[Setup] Extracting information (Stage 1)...")
    from paper_qa_chain import extract_high_resolution_info, answer_question_with_retry
    extracted_info = extract_high_resolution_info(cleaned_text)
    
    print("\n[Setup] Ready! You can now ask questions.\n")
    print("=" * 80 + "\n")
    
    # Q&A loop
    question_count = 0
    while True:
        question = input(f"\nQuestion {question_count + 1}: ").strip()
        
        if question.lower() in ["exit", "quit", "終了"]:
            print("\nExiting interactive mode.")
            break
        
        if not question:
            print("Please enter a question.")
            continue
        
        try:
            print("\n[Answering...]")
            answer = answer_question_with_retry(extracted_info, question)
            
            print("\n" + "-" * 80)
            print("ANSWER:")
            print("-" * 80)
            print(answer)
            print("-" * 80)
            
            question_count += 1
            
        except Exception as e:
            print(f"\n[ERROR] Failed to answer: {e}")


def main():
    """
    Main entry point for the script.
    
    Supports two modes:
    1. Single question mode: python paper_qa_pdf.py <pdf> <question>
    2. Interactive mode: python paper_qa_pdf.py <pdf>
    """
    if len(sys.argv) < 2:
        print("Usage:")
        print("  Single question: python paper_qa_pdf.py <pdf_path> <question>")
        print("  Interactive:     python paper_qa_pdf.py <pdf_path>")
        print("\nExample:")
        print('  python paper_qa_pdf.py paper.pdf "この論文の提案手法は?"')
        sys.exit(1)
    
    pdf_path = sys.argv[1]
    
    # Check if PDF exists
    if not Path(pdf_path).exists():
        print(f"Error: PDF file not found: {pdf_path}")
        sys.exit(1)
    
    # Check API key
    if not os.environ.get("GEMINI_API_KEY"):
        print("Error: GEMINI_API_KEY environment variable is required")
        print("\nSet it with:")
        print('  $env:GEMINI_API_KEY="your_key_here"  # PowerShell')
        print('  export GEMINI_API_KEY="your_key_here"  # Bash')
        sys.exit(1)
    
    # Decide mode based on arguments
    if len(sys.argv) >= 3:
        # Single question mode
        question = " ".join(sys.argv[2:])
        
        try:
            result = process_pdf_and_answer(pdf_path, question)
            
            print("\n" + "=" * 80)
            print("FINAL ANSWER")
            print("=" * 80)
            print(result["answer"])
            print("\n" + "=" * 80)
            
        except Exception as e:
            print(f"\n[ERROR] Processing failed: {e}")
            sys.exit(1)
    
    else:
        # Interactive mode
        try:
            interactive_mode(pdf_path)
        except KeyboardInterrupt:
            print("\n\nInterrupted by user.")
        except Exception as e:
            print(f"\n[ERROR] {e}")
            sys.exit(1)


if __name__ == "__main__":
    main()
