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
    """
    global CACHED_SCORES
    scores = {"WISE": 0, "RECKLESS": 0, "ANALYST": 0}

    closed_trades = TradePosition.objects.filter(account_id=account_id, is_closed=True).order_by('-close_time')[:50]

    for t in closed_trades:
        try:
            profit = float(t.profit)
            reason = t.ai_reasoning or ""
            voters = []
            
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
                    else: 
                        if profit < -0.05: scores[v] -= 1
        except: pass
    
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

    # update_persona_scores(account_id) 
    dash_log(account_id, "🚀 Bot Engine Started. Syncing state...")

    with Live(layout, refresh_per_second=2, screen=True):
        while True:
            if stop_check_func(account_id): 
                dash_log(account_id, "🛑 STOP SIGNAL RECEIVED.")
                break
            
            try:
                # --- 1. UI UPDATES ---
                if time.time() - last_ui_update > 2:
                    metrics = get_account_metrics(driver)
                    async_to_sync(channel_layer.group_send)("bot_updates", {"type": "send_update", "data": {
                        "type": "balance_update", 
                        "balance": metrics.get('balance', 0.0), 
                        "equity": metrics.get('equity', 0.0), 
                        "scores": CACHED_SCORES
                    }})
                    if metrics.get('balance', 0) > 0 and not has_synced_once:
                        dash_log(account_id, f"✅ Connected. Balance: ${metrics['balance']}")
                        has_synced_once = True
                    last_ui_update = time.time()

                if not has_synced_once:
                    if smart_sleep(1): break 
                    continue
                
                # --- 2. TREND SYNC ---
                is_scheduled = (time.time() - last_trend_sync > 900)
                is_retry = (MTF_CONTEXT.get("h1") == "UNKNOWN" and time.time() - last_trend_sync > 60)
                
                if is_scheduled or is_retry:
                    last_trend_sync = time.time()
                    dash_log(account_id, "🔄 Syncing Trends (H1/M15)...")
                    try:
                        updated_charts = {}
                        for tf, label in [("1 hour", "h1"), ("15 minutes", "m15")]:
                            if switch_timeframe(driver, tf, dash_log, account_id):
                                smart_sleep(3)
                                raw_candles = parse_candles(driver)
                                if raw_candles:
                                    candles = [sanitize_candle(c) for c in raw_candles]
                                    CHART_BUFFER[label] = candles
                                    last_c = candles[-1]
                                    trend = "BULLISH" if last_c['close'] > last_c['open'] else "BEARISH"
                                    MTF_CONTEXT[label] = trend
                                    updated_charts[f"candles_{label}"] = candles
                                    dash_log(account_id, f"📈 {label.upper()} Trend: {trend}")
                        
                        if updated_charts:
                            async_to_sync(channel_layer.group_send)("bot_updates", {"type": "send_update", "data": {"type": "chart_update", **updated_charts}})

                        switch_timeframe(driver, "5 minutes", dash_log, account_id)
                        smart_sleep(3)
                    except Exception as e:
                        dash_log(account_id, f"⚠️ Trend Sync Failed: {e}")

                # --- 3. ANALYSIS & DATA PREP ---
                raw_m5 = parse_candles(driver)
                if not raw_m5:
                    dash_log(account_id, "⚠️ No M5 Candles found! Retrying...")
                    smart_sleep(2); continue 

                candles_m5 = [sanitize_candle(c) for c in raw_m5]
                CHART_BUFFER["m5"] = candles_m5
                ask_price = get_real_price(driver)

                try:
                    vol_val = sum([c['high'] - c['low'] for c in candles_m5[-5:]]) / 5
                    vol_str = f"{vol_val:.2f}"
                except: 
                    vol_str = "0.00"

                active_trades_ui = get_active_positions(driver)
                trade_context = None
                if active_trades_ui:
                    t = active_trades_ui[0]
                    trade_context = {
                        "direction": t.get('direction', 'BUY').upper(), 
                        "entry_price": t.get('open_price') or t.get('entry') or "0.00",
                        "current_pnl": t.get('profit', '0.00')
                    }

                # Get decision with error handling
                decision = get_market_decision(ask_price, MTF_CONTEXT, candles_m5, get_recent_history(account_id), active_trade=trade_context)

                # Check if decision contains error
                if 'error' in decision:
                    dash_log(account_id, f"⚠️ BRAIN ERROR: {decision.get('reason')}")
                    # You can print full error to console for debugging
                    print(f"FULL ERROR: {decision.get('error', 'No details')}")

                # --- 4. LOGGING ---
                if time.time() - last_verbose_log > 10:
                    trends_display = f"H1:{MTF_CONTEXT.get('h1', 'UNK')[:4]} M15:{MTF_CONTEXT.get('m15', 'UNK')[:4]}"
                    votes = decision.get('reason', '').replace('\n', ' ')
                    if trade_context:
                        dash_log(account_id, f"👀 MONITOR: PnL {trade_context['current_pnl']} | {trends_display} | {votes}")
                    else:
                        dash_log(account_id, f"🧠 THINKING: Price {ask_price} | Vol {vol_str} | {votes}")
                    last_verbose_log = time.time()

                # Fixed UI update - removed scores
                async_to_sync(channel_layer.group_send)("bot_updates", {"type": "send_update", "data": {
                    "type": "analysis_update", 
                    "market_trend": MTF_CONTEXT.get('h1', 'UNKNOWN'), 
                    "volatility": vol_str, 
                    "decision_data": decision,
                    "candles_m5": CHART_BUFFER["m5"][-50:], 
                    "price": ask_price
                }})

                if (time.time() - START_TIME) < WARMUP_SECONDS:
                    smart_sleep(1); continue

                # --- 5. EXECUTION ---
                is_open = len(active_trades_ui) > 0
                
                # A. EMERGENCY BREAK (FIXED FOR LOOPING)
                if is_open:
                    t = active_trades_ui[0]
                    curr_dir = t.get('direction', 'BUY').upper()
                    
                    try:
                        raw_pnl = t.get('profit', '0').replace('$', '').replace(',', '').strip()
                        raw_pnl = raw_pnl.replace('\u2009', '').replace('\xa0', '').replace(' ', '').replace('−', '-').replace('+', '')
                        pnl = float(raw_pnl)
                        
                        # HARD STOP LOSS (keep this)
                        if pnl < -9.00: 
                            dash_log(account_id, f"🛑 HARD STOP: PnL is {pnl}. Closing.")
                            close_current_trade(driver, dash_log, account_id)
                            smart_sleep(2); continue
                        
                        # NEW: Check if we should close based on signal reversal
                        # If we have a trade open and get opposite signal, close
                        if decision['action'] in ["BUY", "SELL"]:
                            is_opposite = (curr_dir == "BUY" and decision['action'] == "SELL") or \
                                        (curr_dir == "SELL" and decision['action'] == "BUY")
                            
                            if is_opposite:
                                dash_log(account_id, f"🔄 REVERSAL: Signal flipped to {decision['action']}. Closing.")
                                close_current_trade(driver, dash_log, account_id)
                                smart_sleep(2); continue
                                
                    except Exception as e:
                        dash_log(account_id, f"⚠️ PnL Error: {e}")


                # D. OPEN NEW TRADE
                if not is_open and ask_price != "0.00" and decision['action'] in ["BUY", "SELL"]:
                    current_p = float(ask_price)
                    sl_level = float(decision.get('sl') or 0)
                    tp_level = float(decision.get('tp') or 0)
                    
                    if sl_level == 0:
                        dash_log(account_id, "🛑 BLOCKED: Failed to calculate SL.")
                        smart_sleep(2); continue
                    
                    raw_sl_gap = abs(current_p - sl_level)
                    raw_tp_gap = abs(current_p - tp_level)
                    
                    MIN_SL_GAP = 30.00 
                    if raw_sl_gap < MIN_SL_GAP: raw_sl_gap = MIN_SL_GAP
                    if raw_sl_gap > 40.0: raw_sl_gap = 40.0
                    
                    sl_pips = round(raw_sl_gap * 10, 1) 
                    tp_pips = round(raw_tp_gap * 10, 1)
                    
                    # NEW: Show signal type and confidence
                    signal_type = decision.get('reason', '').split('|')[0].strip()
                    confidence = decision.get('confidence', 0)
                    dash_log(account_id, f"⚡ {signal_type} (Confidence: {confidence}%) | Gap: ${raw_sl_gap:.2f} | Pips: {sl_pips}")
                    
                    if navigate_order_panel_to_gold(driver, account_id, dash_log):
                        if place_market_order(driver, decision['action'], sl_pips, tp_pips, dash_log, account_id):
                            dash_log(account_id, "✅ Trade Sent.")
                            time.sleep(5) 
                            active_trades_ui = [{"temp": "true"}] 
                            
                            # Save to DB (no voters needed)
                            save_trade_to_db(
                                account_id, 
                                decision['action'], 
                                ask_price, 
                                decision['sl'], 
                                decision['tp'], 
                                decision['reason'],
                                "",  # Empty voters string
                                MTF_CONTEXT
                            )
                            last_history_sync = 0
                        else: 
                            dash_log(account_id, "❌ Order Failed")
                    else: 
                        dash_log(account_id, "❌ Nav Failed")

                # 6. HISTORY
                if time.time() - last_history_sync > 30: 
                    sync_trade_history(driver, account_id, dash_log)
                    # update_persona_scores(account_id)
                    last_history_sync = time.time()

                layout["main"].update(Panel(
                    f"Price: {ask_price} | Signal: {decision.get('action')} ({decision.get('confidence', 0)}%)", 
                    title="Live"
                ))

                layout["footer"].update(Panel("\n".join(local_logs), title="Log"))
                smart_sleep(1)

            except Exception as e:
                dash_log(account_id, f"⚠️ Loop Error: {str(e)[:30]}")
                smart_sleep(2)