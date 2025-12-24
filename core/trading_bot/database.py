import time
import json
from django.utils import timezone
from .models import TradePosition, TradingAccount

def save_trade_to_db(account_id, action, price, sl, tp, reason, candle_data, mtf_context):
    """
    Saves a NEW trade execution to the database with full AI context.
    Argument 'reason' might be a dictionary if coming from new brain, or string if old.
    """
    try:
        account = TradingAccount.objects.get(id=account_id)
        
        # Create a unique fake ID initially
        ticket_id = f"AUTO-{int(time.time())}"
        
        # --- Handle New Brain Data Structure ---
        # The 'reason' argument might now contain the full data packet or just text
        # But based on bot_engine.py, we are passing decision['reason'] which is text string
        
        # We need to extract voters/snapshot if they are passed.
        # Since the signature of this function is being called from bot_engine with specific args,
        # we can parse the "reason" string if it contains the voters, OR update bot_engine to pass them.
        
        # BETTER APPROACH: Let's extract them if they exist in the reason string
        # format: "COUNCIL: BUY... Voted: WISE, RACER"
        
        voters_str = ""
        snapshot_data = {}
        
        if isinstance(reason, str) and "Voted: " in reason:
            try:
                # Extract "WISE, RACER"
                voters_str = reason.split("Voted: ")[1].split("\n")[0].strip()
            except: pass
            
        # Note: If you want to save the full JSON market_snapshot, you should 
        # ideally update the function signature to accept it. 
        # For now, we default to empty dict unless passed explicitly.
        
        TradePosition.objects.create(
            account=account,
            ticket_id=ticket_id,
            symbol="GOLD",
            volume=0.01,
            trade_type=action, 
            open_price=price,
            sl_pips=sl,
            tp_pips=tp,
            
            # --- CONTEXT FIELDS ---
            h1_trend=mtf_context.get('h1', 'UNKNOWN'),
            m15_bias=mtf_context.get('m15', 'UNKNOWN'),
            
            ai_reasoning=reason,
            candle_snapshot=str(candle_data)[:500] if candle_data else "",
            
            # --- NEW FIELDS ---
            voters=voters_str,
            market_snapshot=snapshot_data, # Saved as empty for now until passed
            
            is_closed=False
        )
        print(f"✅ Database: Saved {action} trade {ticket_id} [Voters: {voters_str}]")
    except Exception as e:
        print(f"❌ Database Error: {e}")

def get_recent_history(account_id):
    """
    Retrieves the last 5 trades to give context to the AI for the next decision.
    """
    return TradePosition.objects.filter(account_id=account_id).order_by('-open_time')[:5]