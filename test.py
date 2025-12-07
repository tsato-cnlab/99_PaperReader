# test.py の修正版（簡単）
from dotenv import load_dotenv
import os
import google.generativeai as genai

load_dotenv()  # カレントディレクトリの .env を読み込む

api_key = os.getenv("GOOGLE_API_KEY") or os.getenv("GEMINI_API_KEY") or os.getenv("GEMINI_API_KEY_OLD")
if not api_key:
    raise SystemExit("環境変数が見つかりません。`.env` に GOOGLE_API_KEY または GEMINI_API_KEY を追加してください。")

genai.configure(api_key=api_key)

print("Available models:")
for m in genai.list_models():
    if 'generateContent' in m.supported_generation_methods:
        print(m.name)