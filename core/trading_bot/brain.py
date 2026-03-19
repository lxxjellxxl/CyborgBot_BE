import json
import os
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

# Helper function to read DXY data
def get_dxy_from_file():
    """Read latest DXY data from the background service"""
    dxy_file = 'dxy_latest.json'
    default_data = {
        'price': 100.0,
        'change_percent': 0,
        'strength': False,
        'weakness': False,
        'timestamp': None
    }
    
    try:
        if os.path.exists(dxy_file):
            with open(dxy_file, 'r') as f:
                data = json.load(f)
                return data
    except Exception as e:
        print(f"Error reading DXY file: {e}")
    
    return default_data

# --- 1. VWAP CALCULATION ---
def calculate_vwap(df):
    """Calculate VWAP (Volume Weighted Average Price)"""
    try:
        if df is None or len(df) < 10:
            return None
            
        df['typical'] = (df['high'] + df['low'] + df['close']) / 3
        df['vp'] = df['typical'] * df['volume']
        
        df['cum_vp'] = df['vp'].cumsum()
        df['cum_vol'] = df['volume'].cumsum()
        
        vwap = df['cum_vp'] / df['cum_vol']
        latest_vwap = vwap.iloc[-1]
        
        if pd.isna(latest_vwap):
            return None
        return float(latest_vwap)
    except:
        return None



# --- 2. LIQUIDITY LEVELS (Recent Highs/Lows) ---
def detect_liquidity_levels(df, lookback=30):
    """Find liquidity levels (recent highs and lows)"""
    try:
        recent_high = df['high'].tail(lookback).max()
        recent_low = df['low'].tail(lookback).min()
        
        # Check if they're valid numbers
        if pd.isna(recent_high) or pd.isna(recent_low):
            return {
                'high': None, 'low': None, 
                'swept_high': False, 'swept_low': False,
                'is_premium': False, 'is_discount': False
            }
        
        current_close = float(df['close'].iloc[-1])
        prev_close = float(df['close'].iloc[-2])
        
        liquidity_swept_high = current_close > recent_high and prev_close <= recent_high
        liquidity_swept_low = current_close < recent_low and prev_close >= recent_low
        
        # Calculate VWAP safely
        vwap_val = calculate_vwap(df)
        is_premium = vwap_val is not None and current_close > vwap_val
        is_discount = vwap_val is not None and current_close < vwap_val
        
        return {
            'high': float(recent_high),
            'low': float(recent_low),
            'swept_high': liquidity_swept_high,
            'swept_low': liquidity_swept_low,
            'is_premium': is_premium,
            'is_discount': is_discount
        }
    except Exception as e:
        print(f"Liquidity error: {e}")
        return {
            'high': None, 'low': None, 
            'swept_high': False, 'swept_low': False,
            'is_premium': False, 'is_discount': False
        }

# --- 3. VOLUME PROFILE (POC, Value Area) ---
def calculate_volume_profile(df, bins=25):
    """Calculate Point of Control and Value Area"""
    try:
        if len(df) < 20:
            return {'poc': None, 'va_high': None, 'va_low': None}
        
        highest = df['high'].max()
        lowest = df['low'].min()
        
        # Check if highest/lowest are valid
        if pd.isna(highest) or pd.isna(lowest):
            return {'poc': None, 'va_high': None, 'va_low': None, 
                    'extreme_bullish': False, 'extreme_bearish': False, 'inside_va': False}
        
        price_range = highest - lowest
        if price_range <= 0:
            return {'poc': None, 'va_high': None, 'va_low': None, 
                    'extreme_bullish': False, 'extreme_bearish': False, 'inside_va': False}
        
        bin_size = price_range / bins
        
        # Initialize price levels and volume at price
        price_levels = []
        volume_at_price = []
        
        for i in range(bins):
            price_levels.append(lowest + (i * bin_size) + (bin_size / 2))
            volume_at_price.append(0.0)
        
        # Accumulate volume
        for i in range(len(df)):
            bar_low = df['low'].iloc[i]
            bar_high = df['high'].iloc[i]
            bar_volume = df['volume'].iloc[i]
            bar_close = df['close'].iloc[i]
            
            # Skip if any value is invalid
            if pd.isna(bar_low) or pd.isna(bar_high) or pd.isna(bar_volume) or pd.isna(bar_close):
                continue
                
            for j in range(bins):
                if price_levels[j] >= bar_low and price_levels[j] <= bar_high:
                    closeness = 1 - abs(price_levels[j] - bar_close) / price_range
                    volume_at_price[j] += bar_volume * closeness
        
        # Find POC (highest volume)
        max_volume = max(volume_at_price)
        if max_volume <= 0:
            return {'poc': None, 'va_high': None, 'va_low': None, 
                    'extreme_bullish': False, 'extreme_bearish': False, 'inside_va': False}
        
        poc_idx = volume_at_price.index(max_volume)
        poc = price_levels[poc_idx]
        
        # Find Value Area (70% of volume)
        total_volume = sum(volume_at_price)
        if total_volume <= 0:
            return {'poc': poc, 'va_high': poc, 'va_low': poc, 
                    'extreme_bullish': False, 'extreme_bearish': False, 'inside_va': True}
        
        target_volume = total_volume * 0.7
        
        # Sort by volume
        sorted_indices = sorted(range(bins), key=lambda i: volume_at_price[i], reverse=True)
        
        # Build value area
        va_volume = 0
        va_levels = []
        for idx in sorted_indices:
            if va_volume >= target_volume:
                break
            va_volume += volume_at_price[idx]
            va_levels.append(price_levels[idx])
        
        va_high = max(va_levels) if va_levels else poc
        va_low = min(va_levels) if va_levels else poc
        
        current_price = float(df['close'].iloc[-1])
        
        # SAFE COMPARISONS with null checks
        extreme_bullish = va_low is not None and current_price < va_low
        extreme_bearish = va_high is not None and current_price > va_high
        inside_va = (va_low is not None and va_high is not None and 
                     va_low <= current_price <= va_high)
        
        return {
            'poc': poc,
            'va_high': va_high,
            'va_low': va_low,
            'extreme_bullish': extreme_bullish,
            'extreme_bearish': extreme_bearish,
            'inside_va': inside_va
        }
    except Exception as e:
        print(f"Volume profile error: {e}")
        return {'poc': None, 'va_high': None, 'va_low': None, 
                'extreme_bullish': False, 'extreme_bearish': False, 'inside_va': False}


# --- 4. EMA TREND FILTER ---
def calculate_ema_trend(df, fast=9, slow=21):
    """Calculate EMA trend alignment"""
    try:
        df['ema_fast'] = ta.ema(df['close'], length=fast)
        df['ema_slow'] = ta.ema(df['close'], length=slow)
        
        # EMA alignment
        bullish_alignment = df['ema_fast'].iloc[-1] > df['ema_slow'].iloc[-1]
        bearish_alignment = df['ema_fast'].iloc[-1] < df['ema_slow'].iloc[-1]
        
        # Price position relative to EMAs
        current_price = df['close'].iloc[-1]
        price_above_ema = current_price > df['ema_fast'].iloc[-1] and current_price > df['ema_slow'].iloc[-1]
        price_below_ema = current_price < df['ema_fast'].iloc[-1] and current_price < df['ema_slow'].iloc[-1]
        
        return {
            'bullish': bullish_alignment,
            'bearish': bearish_alignment,
            'price_above': price_above_ema,
            'price_below': price_below_ema,
            'fast': df['ema_fast'].iloc[-1],
            'slow': df['ema_slow'].iloc[-1]
        }
    except:
        return {'bullish': False, 'bearish': False, 'price_above': False, 'price_below': False}

# --- 5. DELTA FLOW (Buying/Selling Pressure) ---
def calculate_delta_flow(df):
    """Calculate delta and momentum"""
    try:
        # Delta = ((close - open) / (high - low)) * volume
        df['delta'] = ((df['close'] - df['open']) / (df['high'] - df['low']).replace(0, 1)) * df['volume']
        df['delta_ma'] = ta.sma(df['delta'].abs(), length=20)
        
        # Delta status
        latest_delta = df['delta'].iloc[-1]
        latest_delta_ma = df['delta_ma'].iloc[-1]
        
        if latest_delta > latest_delta_ma:
            delta_status = "STRONG_BUYING"
        elif latest_delta < -latest_delta_ma:
            delta_status = "STRONG_SELLING"
        else:
            delta_status = "NEUTRAL"
        
        # Delta momentum
        if len(df) >= 5:
            delta_momentum = df['delta'].iloc[-1] - df['delta'].iloc[-5]
        else:
            delta_momentum = 0
        
        return {
            'delta': latest_delta,
            'delta_ma': latest_delta_ma,
            'status': delta_status,
            'momentum': delta_momentum,
            'is_big_buying': latest_delta > latest_delta_ma * 1.8,
            'is_big_selling': latest_delta < -latest_delta_ma * 1.8
        }
    except:
        return {'status': 'NEUTRAL', 'momentum': 0, 'is_big_buying': False, 'is_big_selling': False}

# --- 6. VOLUME SPIKE DETECTION ---
def detect_volume_spike(df):
    """Check if current volume is significantly above average"""
    try:
        df['volume_ma'] = ta.sma(df['volume'], length=20)
        latest_volume = df['volume'].iloc[-1]
        latest_ma = df['volume_ma'].iloc[-1]
        
        return {
            'is_big': latest_volume > latest_ma * 1.5,
            'is_huge': latest_volume > latest_ma * 2.5,
            'ratio': latest_volume / latest_ma if latest_ma > 0 else 1
        }
    except:
        return {'is_big': False, 'is_huge': False, 'ratio': 1}

# --- 7. MAIN DECISION ENGINE ---
def get_market_decision(price, context, candles, history, active_trade=None):
    try:
        if not candles or len(candles) < 30:
            return {'action': 'HOLD', 'sl': 0, 'tp': 0, 'reason': 'Insufficient data'}

        # Create DataFrame
        df = pd.DataFrame(candles)
        df.columns = [c.lower() for c in df.columns]
        
        # Get DXY data
        dxy = get_dxy_from_file()
        
        # --- CALCULATE ALL COMPONENTS WITH DEBUG ---
        try:
            vwap = calculate_vwap(df)
            print(f"DEBUG - VWAP: {vwap}")
        except Exception as e:
            print(f"DEBUG - VWAP ERROR: {e}")
            vwap = None
        
        try:
            liquidity = detect_liquidity_levels(df, lookback=30)
            print(f"DEBUG - LIQUIDITY: {liquidity}")
        except Exception as e:
            print(f"DEBUG - LIQUIDITY ERROR: {e}")
            liquidity = {'high': None, 'low': None, 'swept_high': False, 'swept_low': False, 'is_premium': False, 'is_discount': False}
        
        try:
            volume_profile = calculate_volume_profile(df)
            print(f"DEBUG - VOLUME PROFILE: {volume_profile}")
        except Exception as e:
            print(f"DEBUG - VOLUME PROFILE ERROR: {e}")
            volume_profile = {'poc': None, 'va_high': None, 'va_low': None, 'extreme_bullish': False, 'extreme_bearish': False, 'inside_va': False}
        
        try:
            ema_trend = calculate_ema_trend(df)
            print(f"DEBUG - EMA TREND: {ema_trend}")
        except Exception as e:
            print(f"DEBUG - EMA ERROR: {e}")
            ema_trend = {'bullish': False, 'bearish': False, 'price_above': False, 'price_below': False}
        
        try:
            delta = calculate_delta_flow(df)
            print(f"DEBUG - DELTA: {delta}")
        except Exception as e:
            print(f"DEBUG - DELTA ERROR: {e}")
            delta = {'status': 'NEUTRAL', 'momentum': 0, 'is_big_buying': False, 'is_big_selling': False}
        
        try:
            volume_spike = detect_volume_spike(df)
            print(f"DEBUG - VOLUME SPIKE: {volume_spike}")
        except Exception as e:
            print(f"DEBUG - VOLUME SPIKE ERROR: {e}")
            volume_spike = {'is_big': False, 'is_huge': False, 'ratio': 1}
        
        try:
            atr = ta.atr(df['high'], df['low'], df['close'], length=14).iloc[-1] if len(df) > 14 else 1.0
            print(f"DEBUG - ATR: {atr}")
        except Exception as e:
            print(f"DEBUG - ATR ERROR: {e}")
            atr = 1.0
        
        # --- DETERMINE SIGNAL TYPES ---
        price_f = float(price)
        
        # VWAP Bias with null check
        is_premium = vwap is not None and price_f > vwap
        is_discount = vwap is not None and price_f < vwap
        
        # DXY conditions
        dxy_weakness = dxy.get('weakness', False)
        dxy_strength = dxy.get('strength', False)
        
        # Volume conditions
        is_volume_big = volume_spike['is_big']
        is_big_order = volume_spike['is_huge']
        
        # Delta conditions
        delta_big_buying = delta['is_big_buying']
        delta_big_selling = delta['is_big_selling']
        
        # Signal detection
        perfect_sweep_buy = liquidity['swept_low'] and is_discount and dxy_weakness and is_volume_big
        perfect_sweep_sell = liquidity['swept_high'] and is_premium and dxy_strength and is_volume_big
        
        perfect_scalp_buy = is_discount and dxy_weakness and is_volume_big and not liquidity['swept_low']
        perfect_scalp_sell = is_premium and dxy_strength and is_volume_big and not liquidity['swept_high']
        
        # Volume profile boosted signals
        vp_boosted_buy = (perfect_sweep_buy or perfect_scalp_buy) and volume_profile['extreme_bullish']
        vp_boosted_sell = (perfect_sweep_sell or perfect_scalp_sell) and volume_profile['extreme_bearish']
        
        # Premium signals
        premium_buy = perfect_sweep_buy and volume_profile['extreme_bullish']
        premium_sell = perfect_sweep_sell and volume_profile['extreme_bearish']
        
        # --- SIGNAL HIERARCHY ---
        if premium_buy:
            action = "BUY"
            signal_type = "💎 PREMIUM BUY"
            confidence = 95
        elif premium_sell:
            action = "SELL"
            signal_type = "💎 PREMIUM SELL"
            confidence = 95
        elif vp_boosted_buy:
            action = "BUY"
            signal_type = "⚡ BOOSTED BUY"
            confidence = 85
        elif vp_boosted_sell:
            action = "SELL"
            signal_type = "⚡ BOOSTED SELL"
            confidence = 85
        elif perfect_sweep_buy:
            action = "BUY"
            signal_type = "🔥 SWEEP BUY"
            confidence = 80
        elif perfect_sweep_sell:
            action = "SELL"
            signal_type = "🔥 SWEEP SELL"
            confidence = 80
        elif perfect_scalp_buy:
            action = "BUY"
            signal_type = "✨ SCALP BUY"
            confidence = 75
        elif perfect_scalp_sell:
            action = "SELL"
            signal_type = "✨ SCALP SELL"
            confidence = 75
        else:
            action = "HOLD"
            signal_type = "WAIT"
            confidence = 0
        
        # --- DYNAMIC SL/TP ---
        if action != "HOLD":
            sl_distance = atr * (1.5 if confidence >= 90 else 2.0)
            tp_distance = atr * (3.0 if confidence >= 90 else 4.0)
            
            if action == "BUY":
                sl = round(price_f - sl_distance, 2)
                tp = round(price_f + tp_distance, 2)
            else:
                sl = round(price_f + sl_distance, 2)
                tp = round(price_f - tp_distance, 2)
        else:
            sl = 0.0
            tp = 0.0
        
        reason_parts = [
            f"DXY: {'+' if dxy_strength else '-' if dxy_weakness else '='}{dxy.get('change_percent', 0):.1f}%",
            f"VP: {'Below' if price_f < volume_profile.get('poc', price_f) else 'Above'}",
            f"Vol: {volume_spike['ratio']:.1f}x"
        ]
        
        final = {
            "action": action,
            "sl": sl,
            "tp": tp,
            "reason": f"{signal_type} | " + " | ".join(reason_parts),
            "voters": [],
            "confidence": confidence,
            "snapshot": {
                "vwap": vwap,
                "liquidity": liquidity,
                "volume_profile": volume_profile,
                "dxy": dxy,
                "delta": delta['status'],
                "ema_trend": "BULLISH" if ema_trend['bullish'] else "BEARISH" if ema_trend['bearish'] else "NEUTRAL"
            }
        }
        
        return final
        
    except Exception as e:
        import traceback
        error_details = traceback.format_exc()
        
        # Log to your dash_log system
        try:
            # You need to pass log_func to this function or make it available
            # For now, we'll return the error in the reason
            pass
        except:
            pass
        
        return {
            "action": "HOLD",
            "sl": 0.0,
            "tp": 0.0,
            "reason": f"ERROR: {str(e)[:50]}",
            "voters": [],
            "confidence": 0,
            "error": error_details  # Add this to see in controller
        }


# --- 8. EMERGENCY BREAK (Keep this) ---
def apply_emergency_break(trade, current_price):
    try:
        current_p = float(current_price)
        entry_p = float(trade.entry_price)
        sl_p = float(trade.sl) if trade.sl else 0.0
        
        if trade.trade_type == "BUY": profit = current_p - entry_p
        else: profit = entry_p - current_p
            
        new_sl = None

        # Break even after $1.00 profit
        if profit > 1.00:
            if trade.trade_type == "BUY":
                desired_sl = entry_p + 0.40
                if sl_p < desired_sl: new_sl = desired_sl
            else:
                desired_sl = entry_p - 0.40
                if sl_p == 0 or sl_p > desired_sl: new_sl = desired_sl

        # Trailing after $3.00 profit
        if profit > 3.00:
            if trade.trade_type == "BUY":
                trail_sl = current_p - 1.00
                if trail_sl > sl_p: new_sl = trail_sl
            else:
                trail_sl = current_p + 1.00
                if sl_p == 0 or trail_sl < sl_p: new_sl = trail_sl

        if new_sl:
            return {"ticket": trade.ticket_id, "sl": round(new_sl, 2), "tp": trade.tp}
        return None
    except: 
        return None