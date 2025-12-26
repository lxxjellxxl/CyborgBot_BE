import time
from datetime import datetime
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC

# --- GLOBAL CONTEXT & CACHE ---
# We store the last valid candle data here to prevent "Blank Screen" glitches
MTF_CONTEXT = { "h1": "UNKNOWN", "m15": "UNKNOWN", "m5": "UNKNOWN" }
CANDLE_CACHE = [] 

# --- 1. MACD & MATH CALCULATION ---
def calculate_ema(prices, days, smoothing=2):
    if not prices: return []
    ema = [sum(prices[:days]) / days]
    multiplier = smoothing / (days + 1)
    for price in prices[days:]:
        ema.append((price - ema[-1]) * multiplier + ema[-1])
    return ema

def get_macd_data(candles):
    """
    Calculates MACD (12, 26, 9) for the dashboard visualization.
    """
    if not candles or len(candles) < 35: return {'macd': [], 'signal': [], 'hist': []}
    
    try:
        closes = [float(c['close']) for c in candles]
        
        ema12 = calculate_ema(closes, 12)
        ema26 = calculate_ema(closes, 26)
        
        # Sync lengths
        min_len = min(len(ema12), len(ema26))
        macd_line = [e12 - e26 for e12, e26 in zip(ema12[-min_len:], ema26[-min_len:])]
        
        signal_line = calculate_ema(macd_line, 9)
        
        # Sync lengths again
        min_sig = min(len(macd_line), len(signal_line))
        histogram = [m - s for m, s in zip(macd_line[-min_sig:], signal_line[-min_sig:])]
        
        return { 'macd': macd_line[-50:], 'signal': signal_line[-50:], 'hist': histogram[-50:] }
    except:
        return {'macd': [], 'signal': [], 'hist': []}

# --- 2. PRECISE PRICE FINDER ---
def get_real_price(driver):
    """
    Extracts precise price from the order control panel.
    Robust against <span> tags inside the price div.
    """
    try:
        # 1. Target the Price DIV inside the BUY button
        # This is the "Truth" price for entering a Long position
        price_el = driver.find_element(By.CSS_SELECTOR, ".order-control .order-button.buy .price")
        
        # 2. Use JS 'textContent' to strip HTML tags (spans/classes) safely
        raw_text = driver.execute_script("return arguments[0].textContent;", price_el)
        clean_price = raw_text.strip().replace("\n", "").replace(" ", "")
        
        if clean_price and clean_price.replace(".", "").isdigit():
            return float(clean_price)

    except:
        # Fallback: Try the SELL button if Buy is hidden/loading
        try:
            price_el = driver.find_element(By.CSS_SELECTOR, ".order-control .order-button.sell .price")
            raw_text = driver.execute_script("return arguments[0].textContent;", price_el)
            clean_price = raw_text.strip().replace("\n", "").replace(" ", "")
            if clean_price and clean_price.replace(".", "").isdigit():
                return float(clean_price)
        except:
            pass

    return 0.00

# --- 3. BALANCE & METRICS ---
def get_account_metrics(driver):
    metrics = {"balance": 0.0, "equity": 0.0}
    try:
        # 1. Try Specific Selectors First (Faster)
        try:
            bal_el = driver.find_element(By.CSS_SELECTOR, ".summary-cell.balance .amount-label-text")
            metrics['balance'] = float(bal_el.text.replace('$','').replace(',','').strip())
        except: pass
        
        try:
            eq_el = driver.find_element(By.CSS_SELECTOR, ".summary-cell.equity .amount-label-text")
            metrics['equity'] = float(eq_el.text.replace('$','').replace(',','').strip())
        except: pass

        # 2. Heuristic Fallback (If selectors fail, scan dollars)
        if metrics['balance'] == 0:
            script = """
            const els = document.querySelectorAll('span, div');
            let bal = 0; let eq = 0;
            for (let el of els) {
                let txt = el.innerText;
                if (txt.includes('$') && txt.length < 20) {
                     let val = parseFloat(txt.replace(/[^0-9.]/g, ''));
                     if (val > 0) {
                         // Simple Assumption: First big number is balance, second is equity
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

def get_active_positions(driver):
    trades = []
    try:
        rows = driver.find_elements(By.CSS_SELECTOR, ".positions-table .data-table-row")
        for row in rows:
            try:
                # Robust Cell Extraction
                cells = row.find_elements(By.TAG_NAME, "span")
                
                # Check for minimum length to avoid IndexErrors
                if len(cells) < 14: continue 
                
                # Dynamic Parsing based on your observed indices
                # Assuming index 14 is PnL based on your previous code
                pnl_text = cells[14].text.strip().replace('$', '').replace('−', '-').replace(' ', '')
                
                trades.append({
                    "ticket_id": cells[0].text.strip() or f"#{int(time.time())}", 
                    "symbol": cells[2].text.strip(),
                    "direction": cells[3].text.strip().upper(),
                    "volume": cells[4].text.strip(),
                    "open_price": cells[5].text.strip(),     # Renamed entry -> open_price for consistency
                    "current_price": cells[6].text.strip(),
                    "profit": pnl_text
                })
            except: continue
    except: pass
    return trades

def check_for_active_trades(driver):
    return len(get_active_positions(driver)) > 0

# --- 4. NAVIGATION & TIMEFRAMES ---
def switch_timeframe(driver, tf_name, log_func, account_id):
    try:
        wait = WebDriverWait(driver, 2)
        
        # Open Timeframe Dropdown
        try:
            # Look for Period Button
            btn = driver.find_element(By.CSS_SELECTOR, "[data-testid*='periods'], [title='Period'], .period-button")
            driver.execute_script("arguments[0].click();", btn)
        except: return False
        
        time.sleep(0.5)
        
        # Click Specific Timeframe
        # Robust XPath: Text exact match
        tf = wait.until(EC.element_to_be_clickable((By.XPATH, f"//span[text()='{tf_name}'] | //div[text()='{tf_name}']")))
        driver.execute_script("arguments[0].click();", tf)
        
        time.sleep(2.5) # Allow chart to re-render
        return True
    except: return False

# --- 5. CANDLE PARSER (THE CORE) ---
def parse_candles(driver):
    """
    Extracts candle data from SVG charts.
    Includes CACHING to handle blips and LIMITS to optimize speed.
    """
    global CANDLE_CACHE
    candles = []
    
    try:
        # Find the SVG container
        container = driver.find_element(By.CSS_SELECTOR, "g.candlestick-plot, .highcharts-series-group")
        
        # JS Script to extract SVG geometry -> Price Data
        # Preserved your logic as it works for cTrader's SVG structure
        script = """
        const children = arguments[0].children;
        const data = [];
        
        // LIMIT: Scan max 200 elements from end to keep it fast
        const startIdx = Math.max(0, children.length - 200);
        
        for (let i = startIdx; i < children.length; i++) {
            const el = children[i];
            if (el.tagName === 'rect') {
                const rect = el;
                // Find associated wick line (prev or next sibling)
                let line = rect.previousElementSibling;
                if (!line || line.tagName !== 'line') line = rect.nextElementSibling;
                
                if (line && line.tagName === 'line') {
                    const y1 = parseFloat(line.getAttribute('y1'));
                    const y2 = parseFloat(line.getAttribute('y2'));
                    const rectY = parseFloat(rect.getAttribute('y'));
                    const rectH = parseFloat(rect.getAttribute('height'));
                    const fill = rect.getAttribute('fill');
                    
                    // SVG Coordinate conversion (Inverted Y-axis)
                    // We normalize relative to an offset to get trend shape
                    // Note: Absolute prices might need 'conversionRatio' in frontend
                    const offset = 10000; 
                    const high = offset - Math.min(y1, y2);
                    const low = offset - Math.max(y1, y2);
                    const bodyTop = offset - rectY;
                    const bodyBottom = offset - (rectY + rectH);
                    
                    let open, close;
                    // Detect Green (Bullish) vs Red (Bearish) based on Fill Color
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
        
        if not raw_data: 
            # If scrape fails, return cache instead of empty
            return CANDLE_CACHE
            
        # Add timestamps (Back-calculated from 'now')
        now_ms = int(time.time() * 1000)
        interval_ms = 5 * 60 * 1000 # M5 assumption
        
        # Process ONLY the last 120 candles (10 Hours) for logic
        raw_data = raw_data[-120:]
        
        for idx, c in enumerate(raw_data):
            # Calculate time moving backwards from the last candle
            time_offset = (len(raw_data) - 1 - idx) * interval_ms
            candles.append({
                'time': now_ms - time_offset, 
                'open': c['open'], 
                'high': c['high'], 
                'low': c['low'], 
                'close': c['close']
            })
            
        if len(candles) > 10:
            CANDLE_CACHE = candles # Update Global Cache
            return candles

    except Exception as e:
        pass
        
    # Final Safety: Return cache if everything failed
    return CANDLE_CACHE