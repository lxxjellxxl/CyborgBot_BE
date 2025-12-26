import pandas as pd
import pandas_ta as ta
import numpy as np
from .council import COUNCIL_MEMBERS 

# --- CONFIGURATION ---
MIN_PROFIT_FOR_BE = 1.00 
STRATEGIC_BREAK_PNL = 5.00 

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
def get_market_decision(current_price, mtf_context, candles, history, active_trade=None):
    df = pd.DataFrame(candles)
    df.columns = [c.lower() for c in df.columns] 

    # Math
    df['rsi'] = ta.rsi(df['close'], length=14)
    df['atr'] = ta.atr(df['high'], df['low'], df['close'], length=14)
    bb = ta.bbands(df['close'], length=20, std=2)
    
    rsi_val = round(df['rsi'].iloc[-1], 2)
    
    # --- FIX: EXTRACT ALL 3 BOLLINGER BANDS ---
    # Index 0 = Lower, Index 1 = Middle (Basis), Index 2 = Upper
    bb_lower = bb.iloc[-1, 0] if bb is not None else 0
    bb_mid   = bb.iloc[-1, 1] if bb is not None else 0 # <--- THE MISSING PIECE
    bb_upper = bb.iloc[-1, 2] if bb is not None else 0
    
    # --- COMBINE PATTERNS ---
    micro_pats = detect_micro_patterns(df)
    macro_pats = detect_macro_patterns(df)
    all_patterns = micro_pats + macro_pats
    
    # --- CONTEXT STRING (Now includes Middle Band) ---
    context_str = (
        f"Price: {current_price}\n"
        f"H1 Trend: {mtf_context.get('h1', 'UNKNOWN')}\n"
        f"RSI (14): {rsi_val}\n"
        f"Patterns: {', '.join(all_patterns) if all_patterns else 'None'}\n"
        f"Bollinger: Lower={round(bb_lower, 2)}, Middle={round(bb_mid, 2)}, Upper={round(bb_upper, 2)}\n"
    )

    if active_trade:
        context_str += (
            f"\n🚨 ACTIVE TRADE: {active_trade['direction']} | "
            f"Entry: {active_trade['entry_price']} | "
            f"PnL: {active_trade['current_pnl']}\n"
        )

    # Voting
    votes = {"BUY": 0, "SELL": 0, "HOLD": 0}
    persona_decisions = {}
    raw_data = candles[-10:] 
    
    for name, agent in COUNCIL_MEMBERS.items():
        try:
            decision = agent.analyze(context_str, raw_data)
            action = decision.get('action', 'HOLD').upper()
            votes[action] += 1
            persona_decisions[name] = action
        except: persona_decisions[name] = "ERROR"

    winner = "HOLD"
    if votes["BUY"] >= 2: winner = "BUY"
    elif votes["SELL"] >= 2: winner = "SELL"
    
    voters_list = [name for name, action in persona_decisions.items() if action == winner]

    # Risk Management (ATR Clamped)
    raw_atr = df['atr'].iloc[-1] if pd.notna(df['atr'].iloc[-1]) else 1.0
    atr = min(raw_atr, 5.00) 
    if atr < 0.50: atr = 0.50
    
    sl_dist = max(atr * 1.5, 1.50) 
    entry = float(current_price)
    sl = entry - sl_dist if winner == "BUY" else entry + sl_dist
    tp = entry + (sl_dist * 2) if winner == "BUY" else entry - (sl_dist * 2)

    reason_parts = [f"{n}:{a}" for n, a in persona_decisions.items()]
    reason_str = f"Council: {winner} | " + " | ".join(reason_parts)

    return {
        "action": winner,
        "sl": round(sl, 2),
        "tp": round(tp, 2),
        "reason": reason_str,
        "voters": voters_list,
        "indicators": {"rsi": rsi_val, "atr": round(atr, 2)},
        "patterns": {p: True for p in all_patterns} 
    }

def apply_emergency_break(db_trade, current_price):
    try:
        entry = float(db_trade.open_price or 0); curr = float(current_price); sl = float(db_trade.sl or 0)
        direction = db_trade.trade_type 
        if entry == 0: return None
        profit = (curr - entry) if direction == "BUY" else (entry - curr)
        
        if profit >= MIN_PROFIT_FOR_BE:
            new_sl = entry + 0.20 if direction == "BUY" else entry - 0.20
            if (direction == "BUY" and sl < new_sl) or (direction == "SELL" and (sl == 0 or sl > new_sl)):
                return {"sl": round(new_sl, 2), "ticket": db_trade.ticket_id}
                
        if profit >= 3.00:
            trail = curr - 1.50 if direction == "BUY" else curr + 1.50
            if (direction == "BUY" and trail > sl) or (direction == "SELL" and (sl == 0 or trail < sl)):
                return {"sl": round(trail, 2), "ticket": db_trade.ticket_id}
    except: pass
    return None