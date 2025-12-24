import time
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC

# --- GLOBAL CONTEXT ---
MTF_CONTEXT = { "h1": "UNKNOWN", "m15": "UNKNOWN", "m5": "UNKNOWN" }

# --- 1. MACD CALCULATION ---
def calculate_ema(prices, days, smoothing=2):
    if not prices: return []
    ema = [sum(prices[:days]) / days]
    multiplier = smoothing / (days + 1)
    for price in prices[days:]:
        ema.append((price - ema[-1]) * multiplier + ema[-1])
    return ema

def get_macd_data(candles):
    if not candles or len(candles) < 35: return {'macd': [], 'signal': [], 'hist': []}
    closes = [float(c['close']) for c in candles]
    
    ema12 = calculate_ema(closes, 12)
    ema26 = calculate_ema(closes, 26)
    
    min_len = min(len(ema12), len(ema26))
    macd_line = [e12 - e26 for e12, e26 in zip(ema12[-min_len:], ema26[-min_len:])]
    signal_line = calculate_ema(macd_line, 9)
    
    min_sig = min(len(macd_line), len(signal_line))
    histogram = [m - s for m, s in zip(macd_line[-min_sig:], signal_line[-min_sig:])]
    
    return { 'macd': macd_line[-50:], 'signal': signal_line[-50:], 'hist': histogram[-50:] }

# --- 2. PRECISE PRICE FINDER (Fixed for "4372.<span class='pips'>32</span>") ---
def get_real_price(driver):
    """
    Extracts price precisely from the .order-control panel.
    Target: <div class="order-control"> ... <button class="buy"><div class="price">4382.<span class="pips">63</span>
    """
    try:
        # 1. Target the Price DIV inside the BUY button within the Order Control
        # This is the most stable element in the HTML structure you provided.
        price_el = driver.find_element(By.CSS_SELECTOR, ".order-control .order-button.buy .price")
        
        # 2. Use JavaScript to get 'textContent'. 
        # This guarantees we get "4382.63" even if the <span> is styled weirdly or hidden.
        # Selenium's standard .text sometimes misses nested spans.
        raw_text = driver.execute_script("return arguments[0].textContent;", price_el)
        
        # 3. Clean it: Remove newlines, spaces, and ensure it's a number
        clean_price = raw_text.strip().replace("\n", "").replace(" ", "")
        
        # Validate that we actually got a number (e.g., "4382.63")
        if clean_price and clean_price.replace(".", "").isdigit():
            return clean_price

    except:
        pass

    # Fallback: Try the SELL button if BUY failed (User said "Any price from here")
    try:
        price_el = driver.find_element(By.CSS_SELECTOR, ".order-control .order-button.sell .price")
        raw_text = driver.execute_script("return arguments[0].textContent;", price_el)
        clean_price = raw_text.strip().replace("\n", "").replace(" ", "")
        if clean_price and clean_price.replace(".", "").isdigit():
            return clean_price
    except:
        pass

    return "0.00"

# --- 3. BALANCE FINDER ---
def get_account_metrics(driver):
    metrics = {"balance": 0.0, "equity": 0.0}
    try:
        # Use a very broad search for the Balance text
        # Look for any element that contains a $ sign and is near "Balance"
        script = """
        const els = document.querySelectorAll('span, div');
        let bal = 0;
        let eq = 0;
        for (let el of els) {
            if (el.innerText.includes('$') && el.innerText.length < 20) {
                 // Check parent or sibling for label "Balance"
                 const txt = el.innerText.replace(/[^0-9.]/g, '');
                 // Heuristic: If we haven't found balance, assume first dollar value is balance
                 if (bal === 0 && txt > 0) bal = parseFloat(txt); 
                 else if (eq === 0 && txt > 0) eq = parseFloat(txt);
            }
        }
        return {balance: bal, equity: eq};
        """
        # Note: The above JS is a fallback. Let's try your specific classes first.
        try:
            bal_el = driver.find_element(By.CSS_SELECTOR, ".summary-cell.balance .amount-label-text")
            metrics['balance'] = float(bal_el.text.replace('$','').replace(',','').strip())
        except: pass
        
        try:
            eq_el = driver.find_element(By.CSS_SELECTOR, ".summary-cell.equity .amount-label-text")
            metrics['equity'] = float(eq_el.text.replace('$','').replace(',','').strip())
        except: pass

    except: pass
    return metrics

def get_active_positions(driver):
    trades = []
    try:
        rows = driver.find_elements(By.CSS_SELECTOR, ".positions-table .data-table-row")
        for row in rows:
            try:
                cells = row.find_elements(By.TAG_NAME, "span")
                if len(cells) < 10: continue
                trades.append({
                    "ticket_id": f"#{int(time.time())}", 
                    "symbol": cells[2].text.strip(),
                    "direction": cells[3].text.strip().upper(),
                    "volume": cells[4].text.strip(),
                    "entry": cells[5].text.strip(),
                    "current_price": cells[6].text.strip(),
                    "pnl": cells[14].text.strip().replace('$', '').replace('−', '-')
                })
            except: continue
    except: pass
    return trades

def check_for_active_trades(driver):
    return len(get_active_positions(driver)) > 0

# --- 4. NAVIGATION ---
def switch_timeframe(driver, tf_name, log_func, account_id):
    try:
        wait = WebDriverWait(driver, 2)
        # Try to click the period button
        try:
            btn = driver.find_element(By.CSS_SELECTOR, "[data-testid*='periods'], [title='Period']")
            driver.execute_script("arguments[0].click();", btn)
        except: return False
        
        time.sleep(0.5)
        tf = wait.until(EC.element_to_be_clickable((By.XPATH, f"//span[text()='{tf_name}']")))
        driver.execute_script("arguments[0].click();", tf)
        time.sleep(2) 
        return True
    except: return False

def parse_candles(driver):
    # (SVG Parser code remains the same as it was working)
    candles = []
    try:
        container = driver.find_element(By.CSS_SELECTOR, "g.candlestick-plot")
        script = """
        const children = arguments[0].children;
        const data = [];
        for (let i = 0; i < children.length; i++) {
            const el = children[i];
            if (el.tagName === 'rect') {
                const rect = el;
                let line = rect.previousElementSibling;
                if (!line || line.tagName !== 'line') line = rect.nextElementSibling;
                if (line) {
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
                    if (fill === '#109a21') { open = bodyBottom; close = bodyTop; } 
                    else { open = bodyTop; close = bodyBottom; }
                    data.push({ high, low, open, close });
                }
            }
        }
        return data;
        """
        raw_data = driver.execute_script(script, container)
        if not raw_data: return []
        now_ms = int(time.time() * 1000)
        interval_ms = 5 * 60 * 1000
        for idx, c in enumerate(raw_data):
            time_offset = (len(raw_data) - 1 - idx) * interval_ms
            candles.append({'time': now_ms - time_offset, 'open': c['open'], 'high': c['high'], 'low': c['low'], 'close': c['close']})
    except: return []
    return candles