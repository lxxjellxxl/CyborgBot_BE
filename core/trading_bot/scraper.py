import time
from datetime import datetime
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC

# --- GLOBAL CONTEXT & CACHE ---
MTF_CONTEXT = { "h1": "UNKNOWN", "m15": "UNKNOWN", "m5": "UNKNOWN" }
CANDLE_CACHE = [] 

# --- 1. MACD & MATH CALCULATION (YOUR CODE) ---
def calculate_ema(prices, days, smoothing=2):
    if not prices: return []
    ema = [sum(prices[:days]) / days]
    multiplier = smoothing / (days + 1)
    for price in prices[days:]:
        ema.append((price - ema[-1]) * multiplier + ema[-1])
    return ema

def get_macd_data(candles):
    if not candles or len(candles) < 35: return {'macd': [], 'signal': [], 'hist': []}
    try:
        closes = [float(c['close']) for c in candles]
        ema12 = calculate_ema(closes, 12)
        ema26 = calculate_ema(closes, 26)
        min_len = min(len(ema12), len(ema26))
        macd_line = [e12 - e26 for e12, e26 in zip(ema12[-min_len:], ema26[-min_len:])]
        signal_line = calculate_ema(macd_line, 9)
        min_sig = min(len(macd_line), len(signal_line))
        histogram = [m - s for m, s in zip(macd_line[-min_sig:], signal_line[-min_sig:])]
        return { 'macd': macd_line[-50:], 'signal': signal_line[-50:], 'hist': histogram[-50:] }
    except:
        return {'macd': [], 'signal': [], 'hist': []}

# --- 2. PRECISE PRICE FINDER (YOUR CODE) ---
def get_real_price(driver):
    try:
        price_el = driver.find_element(By.CSS_SELECTOR, ".order-control .order-button.buy .price")
        raw_text = driver.execute_script("return arguments[0].textContent;", price_el)
        clean_price = raw_text.strip().replace("\n", "").replace(" ", "")
        if clean_price and clean_price.replace(".", "").isdigit():
            return float(clean_price)
    except:
        try:
            price_el = driver.find_element(By.CSS_SELECTOR, ".order-control .order-button.sell .price")
            raw_text = driver.execute_script("return arguments[0].textContent;", price_el)
            clean_price = raw_text.strip().replace("\n", "").replace(" ", "")
            if clean_price and clean_price.replace(".", "").isdigit():
                return float(clean_price)
        except: pass
    return "0.00"

# --- 3. BALANCE & METRICS (YOUR CODE) ---
def get_account_metrics(driver):
    metrics = {"balance": 0.0, "equity": 0.0}
    try:
        try:
            bal_el = driver.find_element(By.CSS_SELECTOR, ".summary-cell.balance .amount-label-text")
            metrics['balance'] = float(bal_el.text.replace('$','').replace(',','').strip())
        except: pass
        
        try:
            eq_el = driver.find_element(By.CSS_SELECTOR, ".summary-cell.equity .amount-label-text")
            metrics['equity'] = float(eq_el.text.replace('$','').replace(',','').strip())
        except: pass

        if metrics['balance'] == 0:
            script = """
            const els = document.querySelectorAll('span, div');
            let bal = 0; let eq = 0;
            for (let el of els) {
                let txt = el.innerText;
                if (txt.includes('$') && txt.length < 20) {
                     let val = parseFloat(txt.replace(/[^0-9.]/g, ''));
                     if (val > 0) {
                         if (bal === 0) bal = val; 
                         else if (eq === 0) eq = val;
                     }
                }
            }
            return {balance: bal, equity: eq};
            """
            res = driver.execute_script(script)
            if res['balance'] > 0: metrics['balance'] = res['balance']
            if res['equity'] > 0: metrics['equity'] = res['equity']
    except: pass
    return metrics

# --- 4. POSITION SCRAPER (YOUR CODE) ---
def get_active_positions(driver):
    trades = []
    try:
        rows = driver.find_elements(By.CSS_SELECTOR, ".positions-table .data-table-row")
        for row in rows:
            try:
                cells = row.find_elements(By.TAG_NAME, "span")
                if len(cells) < 14: continue 
                
                pnl_text = "0.00"
                for cell in cells:
                    txt = cell.text
                    if "$" in txt and ("+" in txt or "−" in txt or "-" in txt):
                        pnl_text = txt.replace('$', '').replace('−', '-').replace(' ', '')
                        break
                
                if pnl_text == "0.00" and len(cells) > 14:
                     pnl_text = cells[14].text.replace('$', '').replace('−', '-').replace(' ', '')

                trades.append({
                    "ticket_id": cells[0].text.strip() or f"#{int(time.time())}", 
                    "symbol": cells[2].text.strip(),
                    "direction": cells[3].text.strip().upper(),
                    "volume": cells[4].text.strip(),
                    "open_price": cells[5].text.strip(),
                    "current_price": cells[6].text.strip(),
                    "profit": pnl_text,
                    "entry": cells[5].text.strip()
                })
            except: continue
    except: pass
    return trades

def check_for_active_trades(driver):
    return len(get_active_positions(driver)) > 0

# --- 5. TIMEFRAME SWITCHING (ROBUST FIX) ---
def switch_timeframe(driver, tf_name, log_func=None, account_id=None):
    wait = WebDriverWait(driver, 3)
    
    # 1. Normalize Targets (What text to look for)
    targets = [tf_name]
    if "hour" in tf_name.lower(): targets.extend(["1h", "H1", "1 Hour"])
    if "15 minutes" in tf_name.lower(): targets.extend(["15m", "M15", "15 Min"])
    if "5 minutes" in tf_name.lower(): targets.extend(["5m", "M5", "5 Min"])

    def try_click_text(text_list):
        for t in text_list:
            try:
                # Look for ANY element with this exact text
                xpath = f"//*[normalize-space(text())='{t}']"
                el = wait.until(EC.element_to_be_clickable((By.XPATH, xpath)))
                driver.execute_script("arguments[0].click();", el)
                time.sleep(4)
                return True
            except: continue
        return False

    try:
        # STRATEGY A: The Dropdown (Best for H1/M15)
        # We try this FIRST because you said it was working for H1
        try:
            # Find and click the period dropdown
            btn = driver.find_element(By.CSS_SELECTOR, "[data-testid*='periods'], [title='Period'], .period-button")
            driver.execute_script("arguments[0].click();", btn)
            time.sleep(0.5) # Wait for menu
            
            # Now click the item
            if try_click_text(targets): return True
            
            # Close dropdown if failed
            driver.find_element(By.TAG_NAME, 'body').click()
        except: pass

        # STRATEGY B: The Toolbar (Best for M5)
        # If it wasn't in the dropdown, maybe it's pinned on the top bar?
        if try_click_text(targets): return True

        # STRATEGY C: Keyboard Shortcut (Last Resort)
        # Typing '1' often sets 1-minute (or hour), '5' sets 5-minute
        if "5" in tf_name:
            driver.find_element(By.TAG_NAME, 'body').send_keys("5")
            time.sleep(4)
            return True

    except Exception as e:
        pass

    if log_func: log_func(account_id, f"❌ Could not switch to {tf_name}")
    return False
# --- 6. CANDLE PARSER (YOUR CODE PRESERVED) ---
def parse_candles(driver, use_cache=True):
    global CANDLE_CACHE
    candles = []
    
    # RETRY LOOP: Try 3 times to find candles (Wait up to 3 seconds)
    for attempt in range(3):
        try:
            # 1. Find the container
            container = driver.find_element(By.CSS_SELECTOR, "g.candlestick-plot, .highcharts-series-group")
            
            # 2. Run the Parsing Script
            script = """
            const children = arguments[0].children;
            const data = [];
            // If children is empty, return null to trigger python retry
            if (children.length === 0) return null; 

            const startIdx = Math.max(0, children.length - 200);
            for (let i = startIdx; i < children.length; i++) {
                const el = children[i];
                if (el.tagName === 'rect') {
                    const rect = el;
                    let line = rect.previousElementSibling;
                    if (!line || line.tagName !== 'line') line = rect.nextElementSibling;
                    if (line && line.tagName === 'line') {
                        const y1 = parseFloat(line.getAttribute('y1'));
                        const y2 = parseFloat(line.getAttribute('y2'));
                        const rectY = parseFloat(rect.getAttribute('y'));
                        const rectH = parseFloat(rect.getAttribute('height'));
                        const fill = rect.getAttribute('fill');
                        const offset = 10000; 
                        const high = offset - Math.min(y1, y2);
                        const low = offset - Math.max(y1, y2);
                        const bodyTop = offset - rectY;
                        const bodyBottom = offset - (rectY + rectH);
                        let open, close;
                        if (fill === '#109a21' || fill.includes('green')) { 
                            open = bodyBottom; close = bodyTop; 
                        } else { 
                            open = bodyTop; close = bodyBottom; 
                        }
                        data.push({ high, low, open, close });
                    }
                }
            }
            return data;
            """
            raw_data = driver.execute_script(script, container)
            
            # 3. Validation: If we got data, break the loop!
            if raw_data and len(raw_data) > 0:
                # Process the data (Same as before)
                now_ms = int(time.time() * 1000)
                interval_ms = 5 * 60 * 1000 
                raw_data = raw_data[-120:]
                
                temp_candles = []
                for idx, c in enumerate(raw_data):
                    time_offset = (len(raw_data) - 1 - idx) * interval_ms
                    temp_candles.append({
                        'time': now_ms - time_offset, 
                        'open': c['open'], 
                        'high': c['high'], 
                        'low': c['low'], 
                        'close': c['close']
                    })
                
                # Save to cache and return
                candles = temp_candles
                CANDLE_CACHE = candles
                return candles

        except Exception:
            pass
        
        # If we failed, wait 1s and try again (The chart might be loading)
        time.sleep(1)

    # Fallback to cache if all 3 attempts failed
    if use_cache: return CANDLE_CACHE
    return []

# --- 7. CONTROLLER ALIASES ---
def get_chart_data(driver):
    return parse_candles(driver, use_cache=True)

def get_open_trades_from_ui(driver):
    return get_active_positions(driver)

# --- 8. THE TREND SYNC LOGIC (FIXED: INCLUDES 5M) ---
def get_technical_trends(driver, log_func=None, account_id=None):
    """
    Switches to H1 -> M15 -> M5.
    Captures ALL charts so the frontend doesn't blank out.
    """
    trends = {"h1": "UNKNOWN", "m15": "UNKNOWN"}
    charts = {} 

    # 1. Check H1
    if switch_timeframe(driver, "1 hour", log_func, account_id):
        candles = parse_candles(driver, use_cache=False)
        if candles:
            charts["candles_h1"] = candles
            last = candles[-1]
            trends["h1"] = "BULLISH" if last['close'] > last['open'] else "BEARISH"

    # 2. Check M15
    if switch_timeframe(driver, "15 minutes", log_func, account_id):
        candles = parse_candles(driver, use_cache=False)
        if candles:
            charts["candles_m15"] = candles
            last = candles[-1]
            trends["m15"] = "BULLISH" if last['close'] > last['open'] else "BEARISH"

    # 3. Return to M5 AND SCRAPE IT
    if switch_timeframe(driver, "5 minutes", log_func, account_id):
        
        # Parse (Now with internal Retry)
        candles_m5 = parse_candles(driver, use_cache=False)
        
        if candles_m5:
            charts["candles_m5"] = candles_m5
            global CANDLE_CACHE
            CANDLE_CACHE = candles_m5
        else:
            # Debug Log if it fails
            if log_func: log_func(account_id, "⚠️ CRITICAL: M5 Chart is blank after retry!")
    
    return trends, charts