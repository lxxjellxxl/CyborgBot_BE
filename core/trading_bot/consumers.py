import json
import traceback
from channels.generic.websocket import AsyncWebsocketConsumer
from channels.db import database_sync_to_async
from .models import TradingAccount
from .serializers import TradingAccountDetailSerializer
from core.trading_bot.scraper import MTF_CONTEXT # <--- IMPORTED GLOBAL CONTEXT

class BotConsumer(AsyncWebsocketConsumer):
    async def connect(self):
        print("🔌 [Backend] WS Connection Request...")
        try:
            # 1. Accept Connection
            await self.accept()
            
            # 2. Join Group
            await self.channel_layer.group_add("bot_updates", self.channel_name)
            print("✅ [Backend] WS Connected & Joined Group")

            # 3. Send Initial Data (Wrapped in Try/Catch to see errors)
            initial_data = await self.get_initial_data()
            
            if initial_data:
                await self.send(text_data=json.dumps({
                    'type': 'balance_update',
                    'balance': str(initial_data['balance']),
                    'equity': str(initial_data['equity']),
                    'daily_stats': initial_data['daily_stats'],
                    'scores': initial_data['persona_scores'],
                    # Send current strategy so UI knows state
                    'current_strategy': MTF_CONTEXT.get('strategy', 'NORMAL') 
                }))
            else:
                print("⚠️ [Backend] No initial account data found.")

        except Exception as e:
            print("\n🔥 [CRITICAL WS ERROR] 🔥")
            print(f"Error: {str(e)}")
            traceback.print_exc() 
            print("--------------------------\n")
            await self.close(code=4000) 

    async def disconnect(self, close_code):
        print(f"🔌 [Backend] WS Disconnected (Code: {close_code})")
        await self.channel_layer.group_discard("bot_updates", self.channel_name)

    # --- NEW: HANDLE MESSAGES FROM FRONTEND ---
    async def receive(self, text_data):
        try:
            data = json.loads(text_data)
            
            # 1. Strategy Update Signal
            if data.get('type') == 'update_strategy':
                new_mode = data.get('strategy', 'NORMAL')
                
                # Update Global Context immediately
                MTF_CONTEXT['strategy'] = new_mode
                
                print(f"🔄 [Backend] Strategy Switched to: {new_mode}")
                
                # Confirm back to UI (Log)
                await self.send(text_data=json.dumps({
                    "type": "log", 
                    "message": f"🔄 Strategy Switched to: {new_mode}"
                }))

        except Exception as e:
            print(f"❌ [Backend] Receive Error: {e}")

    async def send_update(self, event):
        """ Forward internal messages to WebSocket """
        try:
            await self.send(text_data=json.dumps(event['data']))
        except Exception as e:
            print(f"❌ [Backend] Send Failed: {e}")

    @database_sync_to_async
    def get_initial_data(self):
        """ Safe DB Access Wrapper """
        try:
            account = TradingAccount.objects.filter(is_active=True).first()
            if not account:
                account = TradingAccount.objects.first()
            
            if not account:
                return None
            
            return TradingAccountDetailSerializer(account).data
        except Exception as e:
            print(f"❌ [Backend] DB/Serializer Error: {e}")
            traceback.print_exc()
            return None