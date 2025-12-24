from google import genai
from google.genai import types
import json

GEMINI_API_KEY = "AIzaSyB5Hqj_Z2GhdZmP0oD4wNr19UeQ4kcAM0k"
client = genai.Client(api_key=GEMINI_API_KEY)

class BasePersona:
    def __init__(self, name):
        self.name = name

    def get_role_prompt(self):
        """Override this in child classes"""
        return "You are a trader."

    def analyze(self, market_context, chart_data):
        role = self.get_role_prompt()
        
        full_prompt = f"""
        {role}
        
        MARKET CONTEXT:
        {market_context}
        
        RECENT CANDLES (Open/High/Low/Close):
        {chart_data[-5:]}
        
        TASK:
        Analyze the data based on your specific ROLE.
        Output ONLY valid JSON.
        
        FORMAT:
        {{
            "action": "BUY" or "SELL" or "HOLD",
            "reason": "Short explanation (max 10 words)"
        }}
        """
        
        try:
            response = client.models.generate_content(
                model='gemini-2.0-flash', 
                contents=full_prompt,
                config=types.GenerateContentConfig(temperature=0.1)
            )
            text = response.text.replace("```json", "").replace("```", "").strip()
            return json.loads(text)
        except:
            return {"action": "HOLD", "reason": "Error"}