"""
Test script for update_notion_page function
"""
import os
from dotenv import load_dotenv
from notion_client import Client

load_dotenv()

NOTION_TOKEN = os.getenv("NOTION_TOKEN")
NOTION_DATABASE_ID = os.getenv("NOTION_DATABASE_ID")

def update_notion_page(title: str, ai_result: dict, notion_token: str, database_id: str, summary: str = "") -> bool:
    """
    Update Notion page with AI analysis results and summary content.
    Compatible with Notion API version 2022-06-28 and later.
    
    Args:
        title: Paper title
        ai_result: Dict with score, novelty, category
        notion_token: Notion API token
        database_id: Notion database ID
        summary: Optional markdown summary to append to page body
    """
    if not notion_token or not database_id:
        print("⚠️ Notion credentials not configured.")
        return False
    
    try:
        # Initialize Notion client
        notion = Client(auth=notion_token)
        
        # Step 1: Query database directly with title filter
        print(f"🔍 Searching Notion database for: {title}")
        
        # Query the database with a title filter
        query_results = notion.data_sources.query(
            data_source_id=database_id,
            filter={
                "property": "Title",  # Changed from "Name" to "Title"
                "title": {
                    "equals": title
                }
            }
        )
        
        results = query_results.get("results", [])
        print(f"📊 Database query returned {len(results)} results")
        
        if not results:
            print(f"⚠️ No exact match found. Trying partial search...")
            
            # Fallback: Search with partial title
            query_results = notion.data_sources.query(
                data_source_id=database_id,
                filter={
                    "property": "Title",
                    "title": {
                        "contains": title.split()[0]  # Search with first word
                    }
                }
            )
            results = query_results.get("results", [])
            print(f"📊 Partial search returned {len(results)} results")
        
        if not results:
            print(f"⚠️ No Notion page found in database for: {title}")
            return False
        
        # Use the first matching page
        page_id = results[0]["id"]
        
        # Extract title from properties
        page_title = "Unknown"
        title_prop = results[0].get("properties", {}).get("Title", {})
        if title_prop.get("type") == "title":
            title_array = title_prop.get("title", [])
            if title_array:
                page_title = title_array[0].get("plain_text", "Unknown")
        
        print(f"✅ Found Notion page: {page_title}")
        print(f"   Page ID: {page_id[:8]}...")
        
        # Step 2: Update page properties
        print("📝 Updating Notion page properties...")
        
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
        
        print(f"✅ Notion page properties updated successfully!")
        
        # Step 3: Append summary to page body if provided
        if summary:
            print("📝 Appending summary to page body...")
            
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
            
            # Add summary in a collapsible toggle block for cleaner appearance
            summary_blocks.append({
                "object": "block",
                "type": "toggle",
                "toggle": {
                    "rich_text": [{
                        "type": "text",
                        "text": {"content": "詳細要約を表示 ▶"}
                    }],
                    "children": [{
                        "object": "block",
                        "type": "code",
                        "code": {
                            "rich_text": [{
                                "type": "text",
                                "text": {"content": summary[:2000] if len(summary) <= 2000 else summary[:2000]}
                            }],
                            "language": "markdown"
                        }
                    }]
                }
            })
            
            # If summary is longer than 2000 chars, add continuation blocks
            if len(summary) > 2000:
                chunks = [summary[i:i+2000] for i in range(2000, len(summary), 2000)]
                for idx, chunk in enumerate(chunks, 2):
                    summary_blocks.append({
                        "object": "block",
                        "type": "toggle",
                        "toggle": {
                            "rich_text": [{
                                "type": "text",
                                "text": {"content": f"詳細要約 (続き {idx}) ▶"}
                            }],
                            "children": [{
                                "object": "block",
                                "type": "code",
                                "code": {
                                    "rich_text": [{
                                        "type": "text",
                                        "text": {"content": chunk}
                                    }],
                                    "language": "markdown"
                                }
                            }]
                        }
                    })
            
            # Append blocks to page
            notion.blocks.children.append(
                block_id=page_id,
                children=summary_blocks
            )
            
            print(f"✅ Summary appended to page body ({len(summary_blocks)} blocks)")
        
        print(f"✅ Notion page fully updated!")
        print(f"   - AI Score: {ai_result.get('score')}")
        print(f"   - Category: {ai_result.get('category')}")
        print(f"   - Novelty: {ai_result.get('novelty')[:50]}...")
        return True
        
    except Exception as e:
        print(f"❌ Notion update failed: {str(e)}")
        import traceback
        print("\n🔍 Full traceback:")
        traceback.print_exc()
        return False


# ==================== Test Cases ====================

if __name__ == "__main__":
    print("=" * 60)
    print("Notion Integration Test")
    print("=" * 60)
    print()
    
    # Check credentials
    if not NOTION_TOKEN:
        print("❌ NOTION_TOKEN not found in .env file")
        exit(1)
    
    if not NOTION_DATABASE_ID:
        print("❌ NOTION_DATABASE_ID not found in .env file")
        exit(1)
    
    print(f"✅ Notion Token: {NOTION_TOKEN[:10]}...")
    print(f"✅ Database ID: {NOTION_DATABASE_ID}")
    print()
    
    # Test data
    test_title = input("Enter paper title to search (or press Enter for default): ").strip()
    if not test_title:
        test_title = "A Planning Method for Charging Station Based on Long-Term Charging Load Forecasting of Electric Vehicles"
    
    test_ai_result = {
        "score": 75,
        "novelty": "テスト用の新規性説明です。この論文は充電ステーションの計画手法を提案しています。",
        "category": "Energy Systems, Electric Vehicles"
    }
    
    test_summary = """## 1. どんなもの？ (Overview)
* 一言でいうと：電気自動車の充電需要予測に基づく充電ステーション配置計画手法
* 解決したい課題：長期的な充電需要を考慮した効率的な充電インフラの配置

## 2. 先行研究と比べてどこがすごい？ (Novelty & Difference)
* 既存手法の限界：短期的な需要予測のみで長期計画が不十分
* この研究の独自の提案・アイディア：機械学習を用いた長期需要予測モデルの統合

## 3. 技術や手法のキモはどこ？ (Methodology)
* 使用したモデル/アルゴリズム：時系列予測モデル + 最適配置アルゴリズム
* データの種類と規模：実走行データ10万件以上
* 特筆すべき工夫点：地理的要因と需要パターンの統合分析
"""
    
    print(f"📄 Test Title: {test_title}")
    print(f"🎯 Test Data: {test_ai_result}")
    print()
    print("-" * 60)
    print()
    
    # Run test
    success = update_notion_page(
        title=test_title,
        ai_result=test_ai_result,
        notion_token=NOTION_TOKEN,
        database_id=NOTION_DATABASE_ID,
        summary=test_summary
    )
    
    print()
    print("-" * 60)
    if success:
        print("✅ Test PASSED")
    else:
        print("❌ Test FAILED")