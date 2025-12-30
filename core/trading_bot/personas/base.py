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
        # This will be overwritten by Analyst/Wise/Reckless
        return "You are a trader."

    def analyze(self, market_context, chart_data):
        role = self.get_role_prompt()
        
        # === GENERIC ENGINE LOGIC ===
        
        full_prompt = f"""
        {role}
        
        MARKET CONTEXT:
        {market_context}
        
        RECENT CANDLES (Oldest to Newest):
        {chart_data}
        
        TASK:
        Decide IMMEDIATE action.
        CRITICAL: RESPONSE MUST BE VALID JSON ONLY. NO MARKDOWN. NO TEXT.
        FORMAT: {{"action": "BUY" | "SELL" | "HOLD", "sl": 1234.56, "tp": 1234.56, "reason": "Max 5 words"}}
        
        * IMPORTANT: You MUST provide 'sl' (Stop Loss) and 'tp' (Take Profit) prices if you vote BUY or SELL.
        * If HOLD, set sl and tp to 0.
        """
        
        try:
            response = client.models.generate_content(
                model='gemini-2.0-flash', 
                contents=full_prompt,
                config=types.GenerateContentConfig(
                    temperature=0.5,
                    response_mime_type="application/json"
                ) 
            )
            text = response.text.strip()
            
            # --- ROBUST PARSING ---
            try:
                return json.loads(text)
            except:
                if "```" in text:
                    text = text.split("```json")[-1].split("```")[0].strip()
                
                match = re.search(r'\{.*\}', text, re.DOTALL)
                if match:
                    return json.loads(match.group())
                
                # FALLBACK: If JSON fails, HOLD (Do not guess)
                print(f"[{self.name}] ⚠️ JSON Parse Failed. Raw: {text[:20]}...")
                return {"action": "HOLD", "reason": "JSON Error", "sl": 0, "tp": 0}

        except Exception as e:
            print(f"[{self.name}] Analysis Error: {e}")
            return {"action": "HOLD", "reason": "API Error", "sl": 0, "tp": 0}