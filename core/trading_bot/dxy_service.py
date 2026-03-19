# dxy_service.py - runs in background
import requests
import time
import json
from datetime import datetime
import threading

class DXYService:
    def __init__(self, token, update_interval=12):  # 12 seconds = 5 calls/minute
        self.token = token
        self.interval = update_interval
        self.latest_data = None
        self.running = False
        
    def fetch_dxy(self):
        url = "https://api-free.itick.org/indices/quote"
        params = {"code": "DXY", "region": "GB"}
        headers = {"accept": "application/json", "token": self.token}
        
        try:
            response = requests.get(url, headers=headers, params=params)
            if response.status_code == 200:
                data = response.json()
                if data.get("code") == 0:
                    return data.get("data")
        except Exception as e:
            print(f"DXY fetch error: {e}")
        return None
    
    def update_loop(self):
        while self.running:
            data = self.fetch_dxy()
            if data:
                self.latest_data = {
                    'price': data.get('p'),
                    'change': data.get('ch'),
                    'change_percent': data.get('chp'),
                    'high': data.get('h'),
                    'low': data.get('l'),
                    'timestamp': datetime.now().isoformat(),
                    'strength': data.get('chp', 0) > 0,  # Positive change = DXY strong
                    'weakness': data.get('chp', 0) < 0   # Negative change = DXY weak
                }
                # Save to file for main bot to read
                with open('dxy_latest.json', 'w') as f:
                    json.dump(self.latest_data, f)
            
            time.sleep(self.interval)
    
    def start(self):
        self.running = True
        thread = threading.Thread(target=self.update_loop)
        thread.daemon = True
        thread.start()
        return thread

# In your main bot, simply read the file:
def get_dxy():
    try:
        with open('dxy_latest.json', 'r') as f:
            return json.load(f)
    except:
        return {'price': 100.0, 'strength': False, 'weakness': False}