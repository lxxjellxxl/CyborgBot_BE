import time
import json
from django.utils import timezone
from .models import TradePosition, TradingAccount

def save_trade_to_db(account_id, action, price, sl, tp, reason, voters_str, mtf_context):
    """
    Saves a trade execution.
    Arguments matched to Controller: 
    (account_id, action, price, sl, tp, reason, voters_str, mtf_context)
    """
    try:
        account = TradingAccount.objects.get(id=account_id)
        ticket_id = f"AUTO-{int(time.time())}"
        
        # Ensure voters string is clean
        if isinstance(voters_str, list):
            voters_str = ",".join(voters_str)
        
        TradePosition.objects.create(
            account=account,
            ticket_id=ticket_id,
            symbol="GOLD",
            volume=0.01,
            trade_type=action, 
            open_price=price,
            sl_pips=sl,
            tp_pips=tp,
            
            # Context
            h1_trend=mtf_context.get('h1', 'UNKNOWN'),
            m15_bias=mtf_context.get('m15', 'UNKNOWN'),
            
            ai_reasoning=reason,
            voters=voters_str,
            
            is_closed=False
        )
        print(f"✅ Database: Saved {action} trade {ticket_id} [Voters: {voters_str}]")
    except Exception as e:
        print(f"❌ Database Error: {e}")

def get_recent_history(account_id):
    """
    Retrieves the last 5 trades.
    """
    return TradePosition.objects.filter(account_id=account_id).order_by('-open_time')[:5]