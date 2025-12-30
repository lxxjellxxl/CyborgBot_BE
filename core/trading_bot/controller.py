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
CACHED_SCORES = {"WISE": 0, "RECKLESS": 0, "ANALYST": 0} 

def sanitize_candle(candle):
    return {k.lower(): v for k, v in candle.items()}

def update_persona_scores(account_id):
    """
    Recalculates scores from scratch based on the last 50 trades.
    Prevents the 'infinite counting' bug.
    """
    global CACHED_SCORES
    
    # 1. Start Fresh (Reset to 0)
    scores = {"WISE": 0, "RECKLESS": 0, "ANALYST": 0}

    # 2. Fetch actual history from DB (Last 50 closed trades)
    # This gives us the "Current Form" of the personas
    closed_trades = TradePosition.objects.filter(account_id=account_id, is_closed=True).order_by('-close_time')[:50]

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
                # Normalize names
                if v == "RACER": v = "RECKLESS"
                if v == "NORMAL": v = "ANALYST"
                
                if v in scores:
                    if profit > 0: 
                        scores[v] += 1
                    else: 
                        # Only penalize if it's a real loss (ignore break-even 0.00)
                        if profit < -0.05:
                            scores[v] -= 1
        except: pass
    
    # 3. Save purely based on this fresh calculation
    try:
        with open(SCORES_FILE, 'w') as f: json.dump(scores, f)
    except: pass
    
    CACHED_SCORES = scores
    return scores

def start_trading_loop(driver, account_id, stop_check_func, log_func):
    layout = Layout()
    layout.split_column(Layout(name="main", size=20), Layout(name="footer", size=10))
    local_logs = []
    channel_layer = get_channel_layer()
    
    last_history_sync = 0
    last_ui_update = 0
    last_trend_sync = 0
    last_verbose_log = 0 
    
    START_TIME = time.time()
    WARMUP_SECONDS = 60 
    has_synced_once = False 

    def smart_sleep(seconds):
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

    update_persona_scores(account_id) 
    dash_log(account_id, "🚀 Bot Engine Started. Syncing state...")

    with Live(layout, refresh_per_second=2, screen=True):
        while True:
            if stop_check_func(account_id): 
                dash_log(account_id, "🛑 STOP SIGNAL RECEIVED.")
                break
            
            try:
                # 1. UI UPDATES
                if time.time() - last_ui_update > 2:
                    metrics = get_account_metrics(driver)
                    async_to_sync(channel_layer.group_send)("bot_updates", {"type": "send_update", "data": {"type": "balance_update", "balance": metrics.get('balance', 0.0), "equity": metrics.get('equity', 0.0), "scores": CACHED_SCORES}})
                    if metrics.get('balance', 0) > 0 and not has_synced_once:
                        dash_log(account_id, f"✅ Connected. Balance: ${metrics['balance']}")
                        has_synced_once = True
                    last_ui_update = time.time()

                if not has_synced_once:
                    if smart_sleep(1): break 
                    continue
                
                # 2. TREND SYNC (FIXED: THROTTLED RETRY)
                # Logic: Sync if 15 mins passed OR (if Trend is Unknown AND 60 seconds have passed since last try)
                is_scheduled = (time.time() - last_trend_sync > 900)
                is_retry = (MTF_CONTEXT.get("h1") == "UNKNOWN" and time.time() - last_trend_sync > 60)
                
                if is_scheduled or is_retry:
                    last_trend_sync = time.time() # Reset timer immediately to prevent loop spam
                    
                    dash_log(account_id, "🔄 Syncing Trends (H1/M15)...")
                    try:
                        updated_charts = {}
                        for tf, label in [("1 hour", "h1"), ("15 minutes", "m15")]:
                            if switch_timeframe(driver, tf, dash_log, account_id):
                                smart_sleep(3)
                                # Sanitize and Parse
                                raw_candles = parse_candles(driver)
                                if raw_candles:
                                    candles = [sanitize_candle(c) for c in raw_candles]
                                    CHART_BUFFER[label] = candles
                                    
                                    # Determine Trend
                                    last_c = candles[-1]
                                    trend = "BULLISH" if last_c['close'] > last_c['open'] else "BEARISH"
                                    MTF_CONTEXT[label] = trend
                                    
                                    updated_charts[f"candles_{label}"] = candles
                                    dash_log(account_id, f"📈 {label.upper()} Trend: {trend}")
                        
                        # --- FORCE PUSH CHARTS NOW ---
                        if updated_charts:
                            async_to_sync(channel_layer.group_send)(
                                "bot_updates",
                                {"type": "send_update", "data": {
                                    "type": "chart_update", 
                                    **updated_charts
                                }}
                            )

                        # ALWAYS RETURN TO M5
                        switch_timeframe(driver, "5 minutes", dash_log, account_id)
                        smart_sleep(3)
                        
                    except Exception as e:
                        dash_log(account_id, f"⚠️ Trend Sync Failed: {e}")

                # 3. ANALYSIS
                raw_m5 = parse_candles(driver)
                if not raw_m5:
                    dash_log(account_id, "⚠️ No M5 Candles found! Retrying...")
                    smart_sleep(2)
                    continue 
                
                candles_m5 = [sanitize_candle(c) for c in raw_m5]
                CHART_BUFFER["m5"] = candles_m5
                ask_price = get_real_price(driver)
                
                # RESTART-PROOF CONTEXT
                active_trades_ui = get_active_positions(driver)
                trade_context = None
                
                if active_trades_ui:
                    t = active_trades_ui[0]
                    trade_context = {
                        "direction": t.get('direction', 'BUY').upper(), 
                        "entry_price": t.get('open_price') or t.get('entry') or "0.00",
                        "current_pnl": t.get('profit', '0.00')
                    }

                decision = get_market_decision(ask_price, MTF_CONTEXT, candles_m5, get_recent_history(account_id), active_trade=trade_context)

                # --- VERBOSE LOGGING ---
                if time.time() - last_verbose_log > 10:
                    snapshot = decision.get('snapshot', {})
                    rsi = snapshot.get('rsi', '--')
                    
                    # UPDATE THIS PART to show M15
                    h1_trend = MTF_CONTEXT.get('h1', 'UNK')
                    m15_trend = MTF_CONTEXT.get('m15', 'UNK')
                    trends_display = f"H1:{h1_trend[:4]} M15:{m15_trend[:4]}" # Shorten to 4 chars (BULL/BEAR)
                    
                    votes = decision.get('reason', '').replace('\n', ' ')
                    
                    if trade_context:
                         dash_log(account_id, f"👀 MONITOR: PnL {trade_context['current_pnl']} | {trends_display} | {votes}")
                    else:
                         dash_log(account_id, f"🧠 THINKING: Price {ask_price} | RSI {rsi} | {trends_display} | {votes}")
                    
                    last_verbose_log = time.time()

                # --- OPTIMIZED UPDATE: NO H1/M15 HERE ---
                async_to_sync(channel_layer.group_send)("bot_updates", {"type": "send_update", "data": {
                    "type": "analysis_update", 
                    "market_trend": MTF_CONTEXT.get('h1', 'UNKNOWN'), 
                    "decision_data": decision,
                    "candles_m5": CHART_BUFFER["m5"][-50:], 
                    "price": ask_price
                }})

                if (time.time() - START_TIME) < WARMUP_SECONDS:
                    layout["main"].update(Panel(f"WARMING UP: {int(WARMUP_SECONDS - (time.time() - START_TIME))}s left...", title="Status"))
                    smart_sleep(1)
                    continue

                # 5. EXECUTION
                is_open = len(active_trades_ui) > 0
                
                # A. EMERGENCY BREAK (TRAILING STOP)
                if is_open and ask_price != "0.00":
                    db_trades = TradePosition.objects.filter(account_id=account_id, is_closed=False)
                    for db_trade in db_trades:
                        mod_signal = apply_emergency_break(db_trade, ask_price)
                        if mod_signal:
                            if execute_trade_modification(driver, mod_signal, dash_log, account_id):
                                db_trade.sl = mod_signal['sl']
                                db_trade.save()
                                dash_log(account_id, f"🚨 SL Adjusted to {mod_signal['sl']}")

                # B. STRATEGIC BREAK & REVERSAL
                if is_open:
                    t = active_trades_ui[0]
                    curr_dir = t.get('direction', 'BUY').upper()
                    ai_signal = decision['action'].upper()
                    
                    try:
                        # --- ROBUST PNL PARSING ---
                        raw_pnl = t.get('profit', '0')
                        clean_pnl = raw_pnl.replace('$', '').replace(',', '') \
                                           .replace('\u2009', '').replace('\xa0', '') \
                                           .replace('−', '-').replace(' ', '').strip()
                        pnl = float(clean_pnl)
                        # ---------------------------

                        is_opposite = (curr_dir == "BUY" and ai_signal == "SELL") or (curr_dir == "SELL" and ai_signal == "BUY")
                        
                        # 1. HARD STOP LOSS (The Fix)
                        # If we lose more than $15 (or your limit), CLOSE IMMEDIATELY.
                        # We do NOT care what the Council says.
                        if pnl < -9.00: 
                            dash_log(account_id, f"🛑 HARD STOP: PnL is {pnl}. Closing early to save cash.")
                            if close_current_trade(driver, dash_log, account_id):
                                smart_sleep(2)
                                continue

                        # 2. Strategic Profit Take (Lock in Gains)
                        if pnl > 5.00 and is_opposite:
                            dash_log(account_id, f"🎯 STRATEGIC BREAK: Locking in ${pnl}. Council flipped to {ai_signal}.")
                            if close_current_trade(driver, dash_log, account_id):
                                smart_sleep(2)
                                continue
                        
                        # 3. Reversal (Only if Council flips)
                        if is_opposite and pnl < -2.00:
                            dash_log(account_id, f"🔄 REVERSAL: Council flipped to {ai_signal}. Closing current trade.")
                            if close_current_trade(driver, dash_log, account_id):
                                smart_sleep(2)
                                continue

                    except Exception as e:
                        dash_log(account_id, f"⚠️ PnL Parse Error: {e}")

                # D. OPEN NEW TRADE
                if not is_open and ask_price != "0.00":
                    if decision['action'] in ["BUY", "SELL"]:
                        
                        # --- 1. CONVERSION LOGIC (Price Gap -> Pips) ---
                        current_p = float(ask_price)
                        # SAFEGUARD: If AI sends 0 or fails, fallback to current price
                        sl_level = float(decision.get('sl') or current_p)
                        tp_level = float(decision.get('tp') or current_p)

                        # Calculate the Dollar Gap
                        raw_sl_gap = abs(current_p - sl_level)
                        raw_tp_gap = abs(current_p - tp_level)

                        # === SANITY CLAMP (THE FIX) ===
                        # If Gap is > $20 (crazy), clamp it to $5.00
                        if raw_sl_gap > 30.0 or raw_sl_gap == 0:
                            dash_log(account_id, f"⚠️ AI SL Missing/Crazy. Defaulting to $15.00 (150 Pips).")
                            raw_sl_gap = 15.0  # <--- CHANGE THIS (Was 5.0)

                        # TP Clamp (Keep this generous, e.g., $20)
                        if raw_tp_gap > 50.0 or raw_tp_gap == 0:
                            dash_log(account_id, f"⚠️ AI TP Missing/Crazy. Defaulting to $20.00 (200 Pips).")
                            raw_tp_gap = 20.0
                        # ==============================

                        # CONVERT TO PIPS
                        sl_pips = round(raw_sl_gap * 10, 1) 
                        tp_pips = round(raw_tp_gap * 10, 1)
                        # ---------------------------------------------

                        dash_log(account_id, f"⚡ ATTEMPTING {decision['action']} | Gap: ${round(raw_sl_gap, 2)} -> Sending {sl_pips} Pips")
                        
                        if navigate_order_panel_to_gold(driver, account_id, dash_log):
                            # Pass the calculated PIPS (e.g., 75) not the GAP (7.5)
                            if place_market_order(driver, decision['action'], sl_pips, tp_pips, dash_log, account_id):
                                
                                # --- 2. PREVENT SPAM (The Machine Gun Fix) ---
                                # Force the bot to wait 5 seconds for the table to update
                                dash_log(account_id, "✅ Trade Sent. Waiting for broker to update...")
                                time.sleep(5) 
                                
                                # Manually flag as open so we don't buy again in the next split second
                                active_trades_ui = [{"temp": "true"}] 
                                
                                # Save to DB
                                voters = decision.get('voters', [])
                                voters_str = ",".join(voters) if isinstance(voters, list) else str(voters)
                                save_trade_to_db(account_id, decision['action'], ask_price, decision['sl'], decision['tp'], decision['reason'], voters_str, MTF_CONTEXT)
                                last_history_sync = 0
                            else:
                                dash_log(account_id, "❌ Order Placement Failed")
                        else:
                            dash_log(account_id, "❌ Navigation Failed")

                # 6. HISTORY & SCORING
                if time.time() - last_history_sync > 30: 
                    sync_trade_history(driver, account_id, dash_log)
                    
                    # OLD LINE (DELETE THIS):
                    # recent_closed = TradePosition.objects.filter(...)...[:10]
                    # update_persona_scores(recent_closed)
                    
                    # NEW LINE (ADD THIS):
                    update_persona_scores(account_id)
                    
                    last_history_sync = time.time()

                layout["main"].update(Panel(f"Price: {ask_price} | Council: {decision.get('action')}", title="Live"))
                layout["footer"].update(Panel("\n".join(local_logs), title="Log"))
                smart_sleep(1)

            except Exception as e:
                dash_log(account_id, f"⚠️ Loop Error: {str(e)[:30]}")
                smart_sleep(2)