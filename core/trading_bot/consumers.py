import json
import traceback
from channels.generic.websocket import AsyncWebsocketConsumer
from channels.db import database_sync_to_async
from .models import TradingAccount
from .serializers import TradingAccountDetailSerializer

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
                    'scores': initial_data['persona_scores']
                }))
            else:
                print("⚠️ [Backend] No initial account data found.")

        except Exception as e:
            print("\n🔥 [CRITICAL WS ERROR] 🔥")
            print(f"Error: {str(e)}")
            traceback.print_exc() # This prints the exact line number!
            print("--------------------------\n")
            await self.close(code=4000) # Close with custom error code

    async def disconnect(self, close_code):
        print(f"🔌 [Backend] WS Disconnected (Code: {close_code})")
        await self.channel_layer.group_discard("bot_updates", self.channel_name)

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
                # Fallback if no active account, get any account
                account = TradingAccount.objects.first()
            
            if not account:
                return None
            
            # This triggers the Serializer (and potential calculation errors)
            return TradingAccountDetailSerializer(account).data
        except Exception as e:
            print(f"❌ [Backend] DB/Serializer Error: {e}")
            traceback.print_exc()
            return None