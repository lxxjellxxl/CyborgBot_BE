import os
import json
import re
from google import genai
from google.genai import types
from dotenv import load_dotenv

# Load variables from .env file
load_dotenv()
# Securely fetch the key
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")

if not GEMINI_API_KEY:
    raise ValueError("GEMINI_API_KEY environment variable is not set.")

client = genai.Client(api_key=GEMINI_API_KEY)

class BasePersona:
    def __init__(self, name):
        self.name = name

    def get_role_prompt(self):
        return "You are a trader."

    def analyze(self, market_context, chart_data):
        role = self.get_role_prompt()
        
        full_prompt = f"""
        {role}
        
        MARKET CONTEXT:
        {market_context}
        
        RECENT CANDLES:
        {chart_data[-5:]}
        
        TASK:
        Decide IMMEDIATE action.
        CRITICAL: RESPONSE MUST BE VALID JSON ONLY. NO MARKDOWN. NO TEXT.
        FORMAT: {{"action": "BUY" | "SELL" | "HOLD", "reason": "Max 5 words"}}
        """
        
        try:
            response = client.models.generate_content(
                model='gemini-2.0-flash', 
                contents=full_prompt,
                config=types.GenerateContentConfig(
                    temperature=0.5,
                    response_mime_type="application/json"  # FORCE JSON MODE
                ) 
            )
            text = response.text.strip()
            
            # --- ROBUST PARSING (THE FIX) ---
            try:
                # 1. Try direct parse
                return json.loads(text)
            except:
                # 2. Try cleaning code blocks
                if "```" in text:
                    text = text.split("```json")[-1].split("```")[0].strip()
                
                # 3. Regex Search for JSON object {...}
                match = re.search(r'\{.*\}', text, re.DOTALL)
                if match:
                    return json.loads(match.group())
                
                # 4. Fallback: Keyword search if JSON fails
                text_upper = text.upper()
                if "BUY" in text_upper: return {"action": "BUY", "reason": "Fallback Parse"}
                if "SELL" in text_upper: return {"action": "SELL", "reason": "Fallback Parse"}
                
                return {"action": "HOLD", "reason": "Parse Error"}

        except Exception as e:
            print(f"[{self.name}] Analysis Error: {e}")
            return {"action": "HOLD", "reason": "API Error"}