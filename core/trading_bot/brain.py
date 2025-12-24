import pandas as pd
import pandas_ta as ta
# Import the dictionary of initialized personas from the council package
from .council import COUNCIL_MEMBERS 

# --- CONFIGURATION ---
MIN_PROFIT_FOR_BE = 1.00
COOLDOWN_MINUTES = 15

# --- 1. HELPER: DETECT PATTERNS ---
def detect_patterns(df):
    patterns = []
    try:
        c = df.iloc[-1]; p = df.iloc[-2]
        body = abs(c['close'] - c['open'])
        
        # Bullish Engulfing
        if (p['close'] < p['open']) and (c['close'] > c['open']) and \
           (c['close'] > p['open']) and (c['open'] < p['close']):
            patterns.append("BULLISH_ENGULFING")

        # Bearish Engulfing
        if (p['close'] > p['open']) and (c['close'] < c['open']) and \
           (c['open'] > p['close']) and (c['close'] < p['open']):
            patterns.append("BEARISH_ENGULFING")
            
        # Doji
        if (c['high'] - c['low']) > 0 and (body / (c['high'] - c['low'])) < 0.1:
            patterns.append("DOJI")
            
    except: pass
    return patterns

# --- 2. MAIN BRAIN ---
def get_market_decision(current_price, mtf_context, candles, history, active_trade=None):
    # A. PREPARE DATA
    df = pd.DataFrame(candles)
    df.columns = [c.lower() for c in df.columns] 

    # B. CALCULATE MATH
    df['rsi'] = ta.rsi(df['close'], length=14)
    df['atr'] = ta.atr(df['high'], df['low'], df['close'], length=14)
    bb = ta.bbands(df['close'], length=20, std=2)
    
    rsi_val = round(df['rsi'].iloc[-1], 2)
    # Safely get BB columns (names change based on pandas_ta version)
    bb_lower = bb.iloc[-1, 0] if bb is not None else 0
    bb_upper = bb.iloc[-1, 2] if bb is not None else 0
    
    # C. BUILD CONTEXT
    patterns = detect_patterns(df)
    
    context_str = (
        f"Price: {current_price}\n"
        f"H1 Trend: {mtf_context.get('h1', 'UNKNOWN')}\n"
        f"RSI (14): {rsi_val}\n"
        f"Patterns Detected: {', '.join(patterns) if patterns else 'None'}\n"
        f"Bollinger Status: Lower={round(bb_lower, 2)}, Upper={round(bb_upper, 2)}\n"
    )

    # D. MODULAR COUNCIL VOTING
    # This loop handles any number of personas added to the council folder
    votes = {"BUY": 0, "SELL": 0, "HOLD": 0}
    persona_decisions = {}
    raw_data = candles[-10:] # Give AI slightly more context
    
    for name, agent in COUNCIL_MEMBERS.items():
        try:
            decision = agent.analyze(context_str, raw_data)
            action = decision.get('action', 'HOLD').upper()
            votes[action] += 1
            persona_decisions[name] = action
        except Exception as e:
            print(f"⚠️ Error calling {name}: {e}")
            persona_decisions[name] = "ERROR"

    # E. TALLY VOTES
    winner = "HOLD"
    if votes["BUY"] >= 2: winner = "BUY"
    elif votes["SELL"] >= 2: winner = "SELL"
    
    # Dynamic Voters List for Frontend
    voters_list = [name for name, action in persona_decisions.items() if action == winner]
    
    # F. HARD RULES (Cooldown)
    if not active_trade and history and len(history) > 0:
        last = history[0]
        if float(last.profit) < 0 and last.trade_type == winner:
            return {
                "action": "HOLD",
                "sl": 0, "tp": 0,
                "reason": f"⚠️ COOLDOWN: Last loss in {winner} direction. Waiting...",
                "voters": voters_list,
                "patterns": {p: True for p in patterns}
            }

    # G. RISK MANAGEMENT
    atr = df['atr'].iloc[-1] if pd.notna(df['atr'].iloc[-1]) else 1.0
    sl_dist = max(atr * 1.5, 1.50) 
    
    entry = float(current_price)
    sl = entry - sl_dist if winner == "BUY" else entry + sl_dist
    tp = entry + (sl_dist * 2) if winner == "BUY" else entry - (sl_dist * 2)

    # H. REASONING STRING
    reason_parts = [f"{n}:{a}" for n, a in persona_decisions.items()]
    reason_str = f"Council: {winner} | " + " | ".join(reason_parts)

    return {
        "action": winner,
        "sl": round(sl, 2),
        "tp": round(tp, 2),
        "reason": reason_str,
        "voters": voters_list,
        "indicators": {"rsi": rsi_val, "atr": round(atr, 2)},
        "patterns": {p: True for p in patterns}
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