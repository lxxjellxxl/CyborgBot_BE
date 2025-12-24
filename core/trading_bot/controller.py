import time
import json
import os
from rich.live import Live
from rich.panel import Panel
from rich.layout import Layout
from asgiref.sync import async_to_sync
from channels.layers import get_channel_layer
from django.conf import settings

# DB & IMPORTS
from core.trading_bot.models import TradePosition

from .scraper import (
    MTF_CONTEXT, switch_timeframe, parse_candles, 
    check_for_active_trades, get_account_metrics, 
    get_active_positions, get_real_price
)
from .navigator import close_current_trade, navigate_order_panel_to_gold, place_market_order, execute_trade_modification
from .brain import get_market_decision, apply_emergency_break 
from .database import save_trade_to_db, get_recent_history
from .history_manager import sync_trade_history

# CONSTANTS
CHART_BUFFER = { "h1": [], "m15": [], "m5": [] }
SCORES_FILE = os.path.join(settings.BASE_DIR, "persona_scores.json")
CACHED_SCORES = {"WISE": 0, "RECKLESS": 0, "ANALYST": 0} # RAM Cache

# --- HELPER: Prevent KeyErrors (Fixes 'CLOSE' crash) ---
def sanitize_candle(candle):
    """Ensures candle keys are always lowercase"""
    return {k.lower(): v for k, v in candle.items()}

# --- SCORING SYSTEM ---
def update_persona_scores(closed_trades):
    global CACHED_SCORES
    
    # 1. Load existing or start fresh
    if not os.path.exists(SCORES_FILE):
        scores = {"WISE": 0, "RECKLESS": 0, "ANALYST": 0}
    else:
        try:
            with open(SCORES_FILE, 'r') as f: scores = json.load(f)
        except: scores = {"WISE": 0, "RECKLESS": 0, "ANALYST": 0}

    # 2. Update logic
    for t in closed_trades:
        try:
            profit = float(t.profit)
            reason = t.ai_reasoning or ""
            voters = []
            
            # Extract voters safely
            if hasattr(t, 'voters') and t.voters:
                 voters = [v.strip().upper() for v in t.voters.split(',')]
            elif "Voted: " in reason:
                try:
                    part = reason.split("Voted: ")[1].split("\n")[0]
                    voters = [v.strip().upper() for v in part.split(",")]
                except: pass

            for v in voters:
                if v == "RACER": v = "RECKLESS"
                if v == "NORMAL": v = "ANALYST"
                if v in scores:
                    if profit > 0: scores[v] += 1
                    else: scores[v] -= 1
        except: pass
    
    # 3. Save to Disk & RAM
    with open(SCORES_FILE, 'w') as f: json.dump(scores, f)
    CACHED_SCORES = scores
    return scores

# --- MAIN ENGINE ---
def start_trading_loop(driver, account_id, stop_check_func, log_func):
    layout = Layout()
    layout.split_column(Layout(name="main", size=20), Layout(name="footer", size=10))
    local_logs = []
    channel_layer = get_channel_layer()
    
    last_history_sync = 0
    last_ui_update = 0
    last_trend_sync = 0
    
    START_TIME = time.time()
    WARMUP_SECONDS = 60 
    
    has_synced_once = False 

    # --- INSTANT KILL HELPER ---
    def smart_sleep(seconds):
        """Sleeps for 'seconds' but checks Stop Signal every 0.1s"""
        end_time = time.time() + seconds
        while time.time() < end_time:
            if stop_check_func(account_id): return True 
            time.sleep(0.1)
        return False

    def dash_log(acc_id, msg):
        log_func(acc_id, msg)
        local_logs.append(f"[{time.strftime('%H:%M:%S')}] {msg}")
        if len(local_logs) > 7: local_logs.pop(0)
        try:
            async_to_sync(channel_layer.group_send)(
                "bot_updates", {"type": "send_update", "data": {"type": "log", "message": msg}}
            )
        except: pass

    # Initialize Cache on Startup
    update_persona_scores([]) 

    dash_log(account_id, "🚀 Bot Engine Started. Warming up (60s)...")

    with Live(layout, refresh_per_second=2, screen=True):
        while True:
            # 1. Immediate Check
            if stop_check_func(account_id): 
                dash_log(account_id, "🛑 STOP SIGNAL RECEIVED.")
                break
            
            try:
                # ---------------------------------------------------------
                # 1. UI UPDATES (Optimized)
                # ---------------------------------------------------------
                if time.time() - last_ui_update > 2:
                    metrics = get_account_metrics(driver)
                    
                    # Send Cache directly (Don't read file)
                    async_to_sync(channel_layer.group_send)(
                        "bot_updates", 
                        {"type": "send_update", "data": {
                            "type": "balance_update", 
                            "balance": metrics.get('balance', 0.0), 
                            "equity": metrics.get('equity', 0.0),
                            "scores": CACHED_SCORES 
                        }}
                    )
                    
                    if metrics.get('balance', 0) > 0 and not has_synced_once:
                        dash_log(account_id, f"✅ Connected. Balance: ${metrics['balance']}")
                        has_synced_once = True
                    
                    last_ui_update = time.time()

                if not has_synced_once:
                    if smart_sleep(1): break 
                    continue
                
                # ---------------------------------------------------------
                # 2. TREND SYNC (Multi-Timeframe)
                # ---------------------------------------------------------
                is_time = (time.time() - last_trend_sync > 900)
                is_unknown = (MTF_CONTEXT.get("h1") == "UNKNOWN")
                
                if is_time or is_unknown:
                    try:
                        last_trend_sync = time.time() 
                        dash_log(account_id, "🔄 Syncing Trends...")
                        
                        # H1 Check
                        if switch_timeframe(driver, "1 hour", dash_log, account_id):
                            if smart_sleep(3): break
                            h1 = [sanitize_candle(c) for c in parse_candles(driver)] # Safe parsing
                            if h1 and len(h1) > 10: 
                                CHART_BUFFER["h1"] = h1
                                MTF_CONTEXT["h1"] = "BULLISH" if h1[-1]['close'] > h1[-1]['open'] else "BEARISH"
                        
                        # M15 Check
                        if switch_timeframe(driver, "15 minutes", dash_log, account_id):
                            if smart_sleep(3): break
                            m15 = [sanitize_candle(c) for c in parse_candles(driver)] # Safe parsing
                            if m15 and len(m15) > 10:
                                CHART_BUFFER["m15"] = m15
                                MTF_CONTEXT["m15"] = "BULLISH" if m15[-1]['close'] > m15[-1]['open'] else "BEARISH"
                        
                        # Reset to M5
                        switch_timeframe(driver, "5 minutes", dash_log, account_id)
                        if smart_sleep(3): break
                        
                    except Exception as e:
                        dash_log(account_id, f"⚠️ Trend Sync Failed: {str(e)[:20]}")
                        # Don't break loop, just skip trend update
                        switch_timeframe(driver, "5 minutes", dash_log, account_id)

                # ---------------------------------------------------------
                # 3. ANALYSIS & CONTEXT
                # ---------------------------------------------------------
                # Safe Parsing for M5
                raw_m5 = parse_candles(driver)
                if not raw_m5:
                    if smart_sleep(2): break
                    continue 
                
                candles_m5 = [sanitize_candle(c) for c in raw_m5] # Fixes 'CLOSE' error
                
                CHART_BUFFER["m5"] = candles_m5
                ask_price = get_real_price(driver)
                
                # Active Trade Context
                active_trades_ui = get_active_positions(driver)
                trade_context = None
                
                if len(active_trades_ui) > 0:
                    t = active_trades_ui[0]
                    entry = t.get('open_price') or t.get('entry') or t.get('price') or "0.00"
                    trade_context = {
                        "direction": t.get('direction', 'BUY'), 
                        "entry_price": entry,
                        "current_pnl": t.get('profit', '0.00')
                    }

                decision = get_market_decision(
                    ask_price, 
                    MTF_CONTEXT, 
                    candles_m5, 
                    get_recent_history(account_id),
                    active_trade=trade_context
                )

                # Push Analysis to UI
                async_to_sync(channel_layer.group_send)(
                    "bot_updates",
                    {"type": "send_update", "data": {
                        "type": "analysis_update", 
                        "market_trend": MTF_CONTEXT.get('h1', 'UNKNOWN'), 
                        "decision_data": decision,
                        "candles_m5": CHART_BUFFER["m5"][-50:],
                        "candles_h1": CHART_BUFFER["h1"][-30:],
                        "candles_m15": CHART_BUFFER["m15"][-30:],
                        "price": ask_price
                    }}
                )

                # ---------------------------------------------------------
                # 4. WARMUP & EXECUTION
                # ---------------------------------------------------------
                if (time.time() - START_TIME) < WARMUP_SECONDS:
                    layout["main"].update(Panel(f"WARMING UP: {int(WARMUP_SECONDS - (time.time() - START_TIME))}s left...", title="Status"))
                    if smart_sleep(1): break
                    continue

                is_open = len(active_trades_ui) > 0
                
                # A. TRAILING STOP
                if is_open and ask_price != "0.00":
                    db_trades = TradePosition.objects.filter(account_id=account_id, is_closed=False)
                    for db_trade in db_trades:
                        mod_signal = apply_emergency_break(db_trade, ask_price)
                        if mod_signal:
                            dash_log(account_id, f"🚨 TRAILING STOP: {db_trade.ticket_id}")
                            success = execute_trade_modification(driver, mod_signal, dash_log, account_id)
                            if success:
                                db_trade.sl = mod_signal['sl']
                                db_trade.save()
                                dash_log(account_id, f"✅ SL Updated to {mod_signal['sl']}")

                # B. SCALP LOGIC
                if is_open:
                    try:
                        t = active_trades_ui[0]
                        raw_pnl = t.get('profit', '0').replace('$', '').replace(',', '').strip()
                        pnl = float(raw_pnl)
                        if pnl > 1.00 and decision['action'] == "HOLD":
                             dash_log(account_id, f"💰 Scalping profit (${pnl}) on Neutral Council.")
                             if close_current_trade(driver, dash_log, account_id):
                                 if smart_sleep(2): break
                                 continue
                    except: pass

                # C. REVERSAL LOGIC
                if is_open:
                    t = active_trades_ui[0]
                    curr_dir = t.get('direction', 'BUY')
                    ai_signal = decision['action']
                    if (curr_dir == "BUY" and ai_signal == "SELL") or \
                       (curr_dir == "SELL" and ai_signal == "BUY"):
                        dash_log(account_id, f"🔄 REVERSAL: {curr_dir} -> {ai_signal}. Closing now.")
                        if close_current_trade(driver, dash_log, account_id):
                            dash_log(account_id, "✅ Position Closed.")
                            if smart_sleep(2): break
                            continue 
                
                # D. OPEN NEW TRADE
                if not is_open and ask_price != "0.00":
                    if decision['action'] in ["BUY", "SELL"]:
                        dash_log(account_id, f"⚡ Council Decision: {decision['action']}")
                        if navigate_order_panel_to_gold(driver, account_id, dash_log):
                            if place_market_order(driver, decision['action'], decision['sl'], decision['tp'], dash_log, account_id):
                                save_trade_to_db(
                                    account_id, 
                                    decision['action'], 
                                    ask_price, 
                                    decision['sl'], 
                                    decision['tp'], 
                                    decision['reason'], 
                                    decision.get('voters', ""), # Pass voters string here
                                    MTF_CONTEXT
                                )
                                dash_log(account_id, "✅ Trade Executed")
                                last_history_sync = 0

                # ---------------------------------------------------------
                # 6. HISTORY & SCORING
                # ---------------------------------------------------------
                if time.time() - last_history_sync > 30: 
                    sync_trade_history(driver, account_id, dash_log)
                    
                    # Update scores from DB, write to Disk + Cache
                    recent_closed = TradePosition.objects.filter(account_id=account_id, is_closed=True).order_by('-close_time')[:10]
                    update_persona_scores(recent_closed)
                    
                    last_history_sync = time.time()

                layout["main"].update(Panel(f"Price: {ask_price} | Council: {decision.get('action')}", title="Live"))
                layout["footer"].update(Panel("\n".join(local_logs), title="Log"))
                
                if smart_sleep(1): break

            except Exception as e:
                dash_log(account_id, f"⚠️ Loop Error: {str(e)[:30]}")
                # Wait safely and retry
                if smart_sleep(2): break