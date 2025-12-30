import pandas as pd
import pandas_ta as ta
import numpy as np

from core.trading_bot.personas.analyst import AnalystPersona
from core.trading_bot.personas.reckless import RecklessPersona
from core.trading_bot.personas.wise import WisePersona
from .council import COUNCIL_MEMBERS 

# --- CONFIGURATION ---
MIN_PROFIT_FOR_BE = 1.00 
STRATEGIC_BREAK_PNL = 5.00 

reckless = RecklessPersona()
analyst = AnalystPersona()
wise = WisePersona()

# --- 1. HELPER: MICRO PATTERNS (1-2 Candles) ---
def detect_micro_patterns(df):
    patterns = []
    try:
        c = df.iloc[-1]; p = df.iloc[-2]
        body = abs(c['close'] - c['open'])
        full_range = c['high'] - c['low']
        lower_wick = min(c['close'], c['open']) - c['low']
        upper_wick = c['high'] - max(c['close'], c['open'])

        if full_range == 0: return []

        # Engulfing
        if (p['close'] < p['open']) and (c['close'] > c['open']) and (c['close'] > p['open']) and (c['open'] < p['close']):
            patterns.append("BULLISH_ENGULFING")
        if (p['close'] > p['open']) and (c['close'] < c['open']) and (c['open'] > p['close']) and (c['close'] < p['open']):
            patterns.append("BEARISH_ENGULFING")
            
        # Pin Bars (Hammers/Shooting Stars) - CRITICAL FOR REVERSALS
        if (lower_wick > body * 2) and (upper_wick < body):
            patterns.append("HAMMER_BUY")
        if (upper_wick > body * 2) and (lower_wick < body):
            patterns.append("SHOOTING_STAR_SELL")

    except: pass
    return patterns

# --- 2. HELPER: MACRO PATTERNS (M, W, H&S) ---
def detect_macro_patterns(df):
    """
    Scans the last 50 candles to find M (Double Top), W (Double Bottom).
    """
    patterns = []
    try:
        if len(df) < 30: return []

        # Simple Peak Detection
        df['is_peak'] = df.iloc[2:-2]['high'].apply(
            lambda x: x == df['high'].rolling(window=5, center=True).max().loc[df.index[df['high'] == x][0]]
        )
        peaks = []   
        valleys = [] 
        
        subset = df.iloc[-40:].reset_index()
        for i in range(2, len(subset) - 2):
            curr = subset.iloc[i]
            prev = subset.iloc[i-1]; next_c = subset.iloc[i+1]
            
            if curr['high'] > prev['high'] and curr['high'] > next_c['high']:
                peaks.append((i, curr['high']))
            if curr['low'] < prev['low'] and curr['low'] < next_c['low']:
                valleys.append((i, curr['low']))

        # Double Top (M)
        if len(peaks) >= 2:
            p1 = peaks[-2]; p2 = peaks[-1]
            if abs(p1[1] - p2[1]) / p1[1] < 0.001:
                patterns.append("DOUBLE_TOP_M_SELL")

        # Double Bottom (W)
        if len(valleys) >= 2:
            v1 = valleys[-2]; v2 = valleys[-1]
            if abs(v1[1] - v2[1]) / v1[1] < 0.001:
                patterns.append("DOUBLE_BOTTOM_W_BUY")

    except: pass
    return patterns

# --- 3. MAIN BRAIN ---
def apply_emergency_break(db_trade, current_price):
    """
    Calculates if SL needs to move to Break Even or Trail.
    Includes 'Step Logic' to prevent spamming the broker.
    """
    try:
        entry = float(db_trade.open_price or 0)
        curr = float(current_price)
        sl = float(db_trade.sl or 0)
        direction = db_trade.trade_type 
        
        if entry == 0: return None
        
        # Profit per unit
        profit = (curr - entry) if direction == "BUY" else (entry - curr)
        
        # A. BREAK EVEN (at +$1.00 profit)
        if profit >= 1.00:
            # Move to Entry +/- 0.10 buffer
            be_level = entry + 0.10 if direction == "BUY" else entry - 0.10
            
            # Only update if new SL is better
            is_better = (be_level > sl) if direction == "BUY" else ((sl == 0) or (be_level < sl))
            if is_better:
                return {"sl": round(be_level, 2), "ticket": db_trade.ticket_id}
                
        # B. TRAILING STOP (at +$3.00 profit)
        if profit >= 3.00:
            # Trail $1.50 behind price
            trail_level = curr - 1.50 if direction == "BUY" else curr + 1.50
            
            # Anti-Spam: Only update if change is > $0.10
            step = 0.10
            is_significant = (trail_level > (sl + step)) if direction == "BUY" else ((sl == 0) or (trail_level < (sl - step)))
            
            if is_significant:
                return {"sl": round(trail_level, 2), "ticket": db_trade.ticket_id}
                
    except Exception as e: 
        print(f"Brain Error: {e}")
    return None

# --- 2. MATH HELPER (Calculates RSI/BB for Personas) ---
def get_technical_summary(candles):
    """
    Takes raw candles and returns a dictionary of indicators.
    This ensures Personas know the RSI and Bollinger values.
    """
    try:
        if not candles: return {}
        
        df = pd.DataFrame(candles)
        # Pandas TA requires lowercase columns
        df.columns = [c.lower() for c in df.columns] 

        # Calculate Indicators
        # 
        df['rsi'] = ta.rsi(df['close'], length=14)
        bb = ta.bbands(df['close'], length=20, std=2)
        
        # Extract last values
        rsi_val = round(df['rsi'].iloc[-1], 2)
        
        # BBands (0=Lower, 1=Mid, 2=Upper)
        bb_lower = bb.iloc[-1, 0] if bb is not None else 0
        bb_mid   = bb.iloc[-1, 1] if bb is not None else 0
        bb_upper = bb.iloc[-1, 2] if bb is not None else 0
        
        # Micro Patterns (Engulfing, Hammer)
        # 
        patterns = []
        c = df.iloc[-1]; p = df.iloc[-2]
        
        # Bullish Engulfing
        if (p['close'] < p['open']) and (c['close'] > c['open']) and (c['close'] > p['open']):
            patterns.append("BULLISH_ENGULFING")
            
        return {
            "rsi": rsi_val,
            "bb_lower": round(bb_lower, 2),
            "bb_upper": round(bb_upper, 2),
            "patterns": ", ".join(patterns)
        }
    except Exception as e:
        return {"rsi": 50, "bb_lower": 0, "bb_upper": 0, "patterns": "Error"}

# --- 3. VOTE SYNTHESIS (The Judge) ---
def synthesize_votes(votes, context):
    """
    Counts votes from Personas and applies H1 Trend Veto.
    """
    final_decision = {"action": "HOLD", "sl": 0, "tp": 0, "reason": "", "voters": []}
    
    buy_votes = 0; sell_votes = 0
    reasons = []; sl_values = []; tp_values = []
    
    for persona, vote in votes.items():
        action = vote.get('action', 'HOLD')
        reasons.append(f"{persona}: {action} ({vote.get('reason', '')})")
        
        if action == "BUY":
            buy_votes += 1
            if vote.get('sl'): sl_values.append(float(vote['sl']))
            if vote.get('tp'): tp_values.append(float(vote['tp']))
            final_decision['voters'].append(persona)
            
        elif action == "SELL":
            sell_votes += 1
            if vote.get('sl'): sl_values.append(float(vote['sl']))
            if vote.get('tp'): tp_values.append(float(vote['tp']))
            final_decision['voters'].append(persona)

    # CONTEXT CHECK: H1 Trend Veto
    h1_trend = context.get('h1', 'NEUTRAL')
    
    if h1_trend == "BEARISH" and buy_votes > 0: 
        buy_votes = 0; reasons.append("H1 Bearish Veto")
        
    if h1_trend == "BULLISH" and sell_votes > 0: 
        sell_votes = 0; reasons.append("H1 Bullish Veto")

    # DECIDE WINNER (Need 2 votes)
    if buy_votes >= 2:
        final_decision["action"] = "BUY"
        final_decision["sl"] = sum(sl_values)/len(sl_values) if sl_values else 0
        final_decision["tp"] = sum(tp_values)/len(tp_values) if tp_values else 0
        
    elif sell_votes >= 2:
        final_decision["action"] = "SELL"
        final_decision["sl"] = sum(sl_values)/len(sl_values) if sl_values else 0
        final_decision["tp"] = sum(tp_values)/len(tp_values) if tp_values else 0
        
    final_decision["reason"] = " | ".join(reasons)
    return final_decision

# Compatibility Wrapper
def get_market_decision(price, context, candles, history, active_trade=None):
    """
    Calculates Math -> Asks Personas -> Returns Decision.
    FIXED: Now includes MICRO and MACRO patterns in the snapshot.
    """
    # 1. Calculate Technicals (RSI, BB, PATTERNS)
    try:
        if not candles or len(candles) < 20:
            raise ValueError("Not enough candles")

        df = pd.DataFrame(candles)
        df.columns = [c.lower() for c in df.columns]
        
        # A. Indicators
        df['rsi'] = ta.rsi(df['close'], length=14)
        bb = ta.bbands(df['close'], length=20, std=2)
        
        rsi_val = float(round(df['rsi'].iloc[-1], 2))
        bb_lower = float(round(bb.iloc[-1, 0], 2)) if bb is not None else 0.0
        bb_upper = float(round(bb.iloc[-1, 2], 2)) if bb is not None else 0.0
        
        # === B. PATTERNS (THE FIX) ===
        # We must calculate them here so they get sent to the frontend
        micro_patterns = detect_micro_patterns(df) # e.g. ["BULLISH_ENGULFING"]
        macro_patterns = detect_macro_patterns(df) # e.g. ["DOUBLE_BOTTOM_W"]
        # =============================

        # C. Serialize History
        history_clean = []
        if history:
            for h in history:
                if isinstance(h, dict): history_clean.append(h)
                else:
                    history_clean.append({
                        "ticket": str(h.ticket_id),
                        "profit": float(h.profit),
                        "type": str(h.trade_type)
                    })

        # D. Prepare Snapshot Data
        tech_data = {
            "rsi": rsi_val,
            "bb_lower": bb_lower,
            "bb_upper": bb_upper,
            "price": float(price),
            # === SEND PATTERNS TO FRONTEND ===
            "patterns": micro_patterns,      # Logic: 1-2 candles
            "macro_patterns": macro_patterns, # Logic: Chart Shapes (M/W)
            # =================================
            "history": history_clean,
            "active_trade": active_trade
        }
    except Exception as e:
        tech_data = {
            "rsi": 50.0, "bb_lower": 0.0, "bb_upper": 0.0, "price": float(price),
            "patterns": [], "macro_patterns": [], "history": [], "error": str(e)
        }

    # 2. Merge Context
    full_context = {**context, **tech_data}
    chart_data = candles[-30:] if candles else []

    # 3. Gather Votes
    votes = {
        "RECKLESS": reckless.analyze(full_context, chart_data),
        "ANALYST": analyst.analyze(full_context, chart_data),
        "WISE": wise.analyze(full_context, chart_data)
    }

    # 4. Synthesize (The Judge)
    final = {"action": "HOLD", "sl": 0.0, "tp": 0.0, "reason": "", "voters": []}
    
    buy_votes = 0; sell_votes = 0
    sls = []; tps = []; reasons = []
    
    for p, v in votes.items():
        act = v.get('action', 'HOLD')
        reasons.append(f"{p}:{act}")
        
        raw_sl = float(v.get('sl', 0) or 0)
        raw_tp = float(v.get('tp', 0) or 0)

        if act == "BUY": 
            buy_votes += 1
            if raw_sl > 0: sls.append(raw_sl)
            if raw_tp > 0: tps.append(raw_tp)
        elif act == "SELL": 
            sell_votes += 1
            if raw_sl > 0: sls.append(raw_sl)
            if raw_tp > 0: tps.append(raw_tp)

    # VETO CHECK
    h1 = context.get('h1', 'NEUTRAL')
    if h1 == "BEARISH" and buy_votes > 0: 
        buy_votes = 0; reasons.append("VETO: H1 Bearish")
    if h1 == "BULLISH" and sell_votes > 0: 
        sell_votes = 0; reasons.append("VETO: H1 Bullish")

    # WINNER DECISION
    if buy_votes >= 2:
        final["action"] = "BUY"
        final["sl"] = sum(sls)/len(sls) if sls else 0.0
        final["tp"] = sum(tps)/len(tps) if tps else 0.0
        final["voters"] = ["COUNCIL_BUY"]
    elif sell_votes >= 2:
        final["action"] = "SELL"
        final["sl"] = sum(sls)/len(sls) if sls else 0.0
        final["tp"] = sum(tps)/len(tps) if tps else 0.0
        final["voters"] = ["COUNCIL_SELL"]
        
    final["reason"] = " | ".join(reasons)
    final["snapshot"] = tech_data # The Controller sends this entire object!
    
    return final