import time
import re
from google import genai
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.common.keys import Keys

# Dashboard Imports
from rich.live import Live
from rich.table import Table
from rich.panel import Panel
# --- CONFIG ---
from rich.layout import Layout
from rich.console import Console

GEMINI_API_KEY = "AIzaSyB5Hqj_Z2GhdZmP0oD4wNr19UeQ4kcAM0k"
client = genai.Client(api_key=GEMINI_API_KEY)
console = Console()

def make_dashboard_layout():
    layout = Layout()
    layout.split_column(
        Layout(name="header", size=3),
        Layout(name="main", size=12),
        Layout(name="footer", size=10)
    )
    return layout

def parse_candles(driver, account_id, log_func):
    """Expanded Scraper: Captures 30 bars to provide deeper trend context."""
    try:
        candle_path = "//*[local-name()='svg']/*[local-name()='g'][2]/*[local-name()='g'][5]"
        wait = WebDriverWait(driver, 10)
        container = wait.until(EC.presence_of_element_located((By.XPATH, candle_path)))
        rects = container.find_elements(By.XPATH, ".//*[local-name()='rect']")
        
        # Increased to 30 bars for better AI perspective
        recent_rects = rects[-30:]
        history_summary = []
        for i, r in enumerate(recent_rects):
            color = r.get_attribute("fill")
            height = r.get_attribute("height")
            y_pos = r.get_attribute("y")
            sentiment = "GREEN_UP" if color == "#109a21" else "RED_DOWN"
            # Explicit coordinate mapping
            history_summary.append(f"Bar_{i}: {sentiment}, BodySize:{height}, Y_Position:{y_pos}")
        
        return "\n".join(history_summary)
    except Exception as e:
        log_func(account_id, f"Scrape Error: {str(e)[:20]}")
        return "ERROR_SCANNING_CHART"
    
def check_for_active_trades(driver):
    """Position Guard: Returns True if any GOLD trade is currently open."""
    try:
        # Check for rows in the data table
        rows = driver.find_elements(By.CLASS_NAME, "data-table-row")
        return len(rows) > 0
    except:
        return False

def manage_open_positions(driver, account_id, log_func, target_profit=10.00):
    try:
        rows = driver.find_elements(By.CLASS_NAME, "data-table-row")
        for row in rows:
            try:
                profit_elem = row.find_element(By.CLASS_NAME, "profit-loss")
                if "up" in profit_elem.get_attribute("class"):
                    profit_info = profit_elem.get_attribute("title")
                    match = re.search(r"(\d+\.\d+)", profit_info.replace("$", ""))
                    if match and float(match.group(1)) >= target_profit:
                        val = float(match.group(1))
                        close_btn = row.find_element(By.CLASS_NAME, "close-button")
                        driver.execute_script("arguments[0].click();", close_btn)
                        log_func(account_id, f"Target Hit: ${val}. Position Closed.")
                        return f"WINNER: ${val}"
            except: continue
    except: pass
    return "Monitoring..."

def get_market_decision(sell_p, buy_p, candle_data):
    """Advanced AI prompt for Dynamic Risk Management."""
    prompt = f"""
    ROLE: Senior Gold Strategist.
    CHART: 5-Minute Timeframe.
    QUOTE: Bid {sell_p} / Ask {buy_p}
    DATA (30-Bar History): {candle_data}
    
    ANALYSIS REQUIREMENTS:
    1. TREND: Analyze Y_Position. Decreasing Y = Price climbing.
    2. VOLATILITY: Use 'BodySize' to gauge risk. Large bodies = High Volatility.
    
    DYNAMIC RISK RULES:
    - SL_PIPS: Base is 100. If market is volatile (Large BodySize), increase up to 150.
    - TP_PIPS: Maintain a 1:3 ratio. If SL is 100, TP must be 300.
    - If no clear setup, output ACTION: HOLD.
    
    OUTPUT FORMAT (Mandatory):
    ACTION: [BUY/SELL/HOLD]
    SL: [Calculated Number]
    TP: [Calculated Number]
    REASON: [Short analysis]
    """
    try:
        response = client.models.generate_content(model='gemini-2.0-flash', contents=prompt)
        return response.text.strip()
    except:
        return "ACTION: HOLD\nSL: 100\nTP: 300"

def navigate_order_panel_to_gold(driver, account_id, log_func):
    wait = WebDriverWait(driver, 10)
    try:
        sidebar_btn = wait.until(EC.element_to_be_clickable((By.XPATH, "//i[@data-testid='new_order']")))
        driver.execute_script("arguments[0].click();", sidebar_btn)
        time.sleep(2) 
        dialog = wait.until(EC.presence_of_element_located((By.CSS_SELECTOR, "div.dialog.narrow")))
        dropdown_trigger = dialog.find_element(By.XPATH, ".//div[@class='instrument-dropdown']//div[@class='value']")
        driver.execute_script("arguments[0].click();", dropdown_trigger)
        time.sleep(1) 
        search_input = wait.until(EC.presence_of_element_located((By.CSS_SELECTOR, "input.instrument-search")))
        search_input.send_keys("GOLD")
        time.sleep(1.5) 
        gold_result = wait.until(EC.element_to_be_clickable((By.XPATH, "//div[contains(@class, 'instrument-search-result')]//div[@class='name' and text()='GOLD']")))
        driver.execute_script("arguments[0].click();", gold_result)
        return True
    except Exception as e:
        log_func(account_id, f"Nav Error: {str(e)[:30]}")
        return False

def place_market_order(driver, action, sl_pips, tp_pips, log_func, account_id):
    wait = WebDriverWait(driver, 10)
    try:
        bid_xpath = "/html/body/main/div/div/div/div[2]/div[2]/div/div/div/div[2]/div/div/div/div/section[3]/div[1]"
        ask_xpath = "/html/body/main/div/div/div/div[2]/div[2]/div/div/div/div[2]/div/div/div/div/section[3]/div[2]"
        side_btn = wait.until(EC.presence_of_element_located((By.XPATH, bid_xpath if action.upper() == "SELL" else ask_xpath)))
        driver.execute_script("arguments[0].click();", side_btn)

        vol_input = driver.find_element(By.CSS_SELECTOR, ".volume-select input")
        vol_input.send_keys(Keys.CONTROL + "a")
        vol_input.send_keys("0.01")

        checkboxes = driver.find_elements(By.CSS_SELECTOR, ".protection .checkbox")
        for cb in checkboxes: driver.execute_script("arguments[0].click();", cb)
        
        time.sleep(1)
        sl_field = driver.find_element(By.CSS_SELECTOR, ".stop-loss .numeric-input-field")
        tp_field = driver.find_element(By.CSS_SELECTOR, ".take-profit .numeric-input-field")
        
        for field, val in [(sl_field, sl_pips), (tp_field, tp_pips)]:
            field.send_keys(Keys.CONTROL + "a")
            field.send_keys(Keys.BACKSPACE)
            field.send_keys(str(val))

        btn_xpath = "/html/body/main/div/div/div/div[2]/div[2]/div/div/div/div[2]/div/div/div/div/section[7]/button"
        final_btn = wait.until(EC.presence_of_element_located((By.XPATH, btn_xpath)))
        driver.execute_script("arguments[0].click();", final_btn)
        log_func(account_id, f"🚀 {action} PLACED | SL: {sl_pips} | TP: {tp_pips}")
        return True
    except Exception as e:
        log_func(account_id, f"Trade Error: {str(e)[:30]}")
        return False

def start_trading_loop(driver, account_id, stop_check_func, log_func):
    layout = make_dashboard_layout()
    logs = []
    
    with Live(layout, refresh_per_second=2):
        while True:
            if stop_check_func(account_id): break
            try:
                is_trade_open = check_for_active_trades(driver)
                pos_status = manage_open_positions(driver, account_id, log_func, target_profit=10.00)

                bid_elem = driver.find_element(By.XPATH, "//button[contains(@class, 'sell')]")
                ask_elem = driver.find_element(By.XPATH, "//button[contains(@class, 'buy')]")
                bid, ask = bid_elem.text.replace("\n", " "), ask_elem.text.replace("\n", " ")
                candles = parse_candles(driver, account_id, log_func)

                decision = get_market_decision(bid, ask, candles)
                
                # Regex to extract dynamic SL/TP from Gemini's response
                sl_match = re.search(r"SL:\s*(\d+)", decision)
                tp_match = re.search(r"TP:\s*(\d+)", decision)
                sl_val = sl_match.group(1) if sl_match else "100"
                tp_val = tp_match.group(1) if tp_match else "300"

                layout["header"].update(Panel(f"GOLD SNIPER | Status: {'ACTIVE_TRADE' if is_trade_open else 'READY'}", style="bold yellow" if is_trade_open else "bold green"))
                
                table = Table(title="Volatility-Adjusted Strategy", expand=True)
                table.add_column("Indicator", style="cyan")
                table.add_column("Value", style="magenta")
                table.add_row("Price", ask)
                table.add_row("AI Signal", decision.splitlines()[0])
                table.add_row("Dynamic Risk", f"SL: {sl_val} Pips / TP: {tp_val} Pips")
                table.add_row("Position Status", pos_status)
                layout["main"].update(table)

                if not is_trade_open:
                    if "BUY" in decision.upper() or "SELL" in decision.upper():
                        if navigate_order_panel_to_gold(driver, account_id, log_func):
                            place_market_order(driver, "BUY" if "BUY" in decision.upper() else "SELL", sl_val, tp_val, log_func, account_id)
                            logs.append(f"[{time.strftime('%H:%M:%S')}] {decision.splitlines()[0]} PLACED")

                if len(logs) > 6: logs.pop(0)
                layout["footer"].update(Panel("\n".join(logs), title="Execution Logs"))
                
                time.sleep(10)
            except Exception as e:
                time.sleep(5)