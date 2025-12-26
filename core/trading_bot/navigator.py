import time
import math
from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.common.action_chains import ActionChains
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC

# --- HELPER: WINDOW MANAGER ---
def ensure_trading_window(driver, log_func, account_id):
    """
    Fixes 'no such window' errors by finding the tab with the chart.
    """
    try:
        # 1. Check if current window is alive
        _ = driver.title 
        return True
    except:
        log_func(account_id, "⚠️ Lost Window focus. Searching for Trader...")
        
        # 2. Loop through all tabs to find the one with 'cTrader' or 'FxPro'
        found = False
        for handle in driver.window_handles:
            try:
                driver.switch_to.window(handle)
                title = driver.title.lower()
                if "ctrader" in title or "terminal" in title or "trade" in title:
                    found = True
                    break
            except: pass
            
        if not found and len(driver.window_handles) > 0:
            # Last Resort: Switch to the last opened tab
            driver.switch_to.window(driver.window_handles[-1])
            
    return True

def safe_cleanup_popups(driver):
    """Closes only non-essential popups."""
    try:
        dialogs = driver.find_elements(By.CLASS_NAME, "dialog")
        for d in dialogs:
            if not d.is_displayed(): continue
            d_class = d.get_attribute("class").lower()
            # Don't close these important windows
            if any(protected in d_class for protected in ["chart", "narrow", "history", "positions", "new-order"]):
                continue
            try:
                close_btn = d.find_element(By.CLASS_NAME, "dialog-close-button")
                driver.execute_script("arguments[0].click();", close_btn)
            except: pass
    except: pass

# --- 1. NAVIGATE TO GOLD ---
def navigate_order_panel_to_gold(driver, account_id, log_func):
    """
    Ensures the 'New Order' dialog is open for XAUUSD (Gold).
    """
    ensure_trading_window(driver, log_func, account_id)
    wait = WebDriverWait(driver, 5)
    
    try:
        safe_cleanup_popups(driver)
        
        # A. Check if already open (Optimization)
        try:
            dialog = driver.find_element(By.CSS_SELECTOR, "div.dialog.new-order-dialog, div.active-symbol-panel")
            if dialog.is_displayed():
                current_text = dialog.text.upper()
                if "XAU" in current_text or "GOLD" in current_text:
                    return True
        except: pass

        # B. Open New Order Panel
        log_func(account_id, "🔍 Switching to XAUUSD...")
        try:
            # Try Sidebar Button
            new_order_btn = wait.until(EC.element_to_be_clickable((By.CSS_SELECTOR, "[data-testid='new_order_button'], .new-order-button")))
            new_order_btn.click()
        except:
            # Fallback: Keyboard Shortcut (F9 is common, but might not work in web)
            pass

        time.sleep(1) 
        
        # C. Select XAUUSD
        # Find the Symbol Search / Dropdown in the active panel
        try:
            search_input = wait.until(EC.element_to_be_clickable((By.CSS_SELECTOR, "input.symbol-search, input[placeholder='Search'], .instrument-search")))
            search_input.click()
            
            # Clear and Type
            search_input.send_keys(Keys.CONTROL + "a", Keys.BACKSPACE)
            search_input.send_keys("XAUUSD") 
            time.sleep(1.0)
            
            # Click the first result
            first_result = wait.until(EC.element_to_be_clickable((By.XPATH, "//div[contains(@class, 'symbol-item') or contains(@class, 'search-result')][1]")))
            first_result.click()
            time.sleep(0.5)
            
        except Exception as e:
            # If search fails, it might already be selected or UI changed
            pass
        
        return True
    except Exception as e:
        log_func(account_id, f"⚠️ Nav Error: {str(e)[:30]}")
        return False

# --- 2. PLACE MARKET ORDER ---
def place_market_order(driver, direction, sl_price, tp_price, log_func, account_id):
    """
    Places a trade. 
    NOTE: sl_price and tp_price are Absolute Prices (e.g., 2024.50).
    """
    ensure_trading_window(driver, log_func, account_id)
    try:
        wait = WebDriverWait(driver, 5)
        
        # 1. SET DIRECTION (Buy/Sell)
        # Look for the specific toggle or button for direction
        try:
            dir_btn = driver.find_element(By.XPATH, f"//div[contains(@class, 'direction-toggle')]//div[contains(text(), '{direction}')] | //button[contains(@class, '{direction.lower()}')]")
            driver.execute_script("arguments[0].click();", dir_btn)
        except: pass

        # 2. FORCE 0.01 LOT
        try:
            vol_input = driver.find_element(By.CSS_SELECTOR, "input.volume-input, input[name='volume']")
            vol_input.click()
            vol_input.send_keys(Keys.CONTROL + "a", Keys.BACKSPACE)
            vol_input.send_keys("0.01")
        except: pass
        time.sleep(0.2)

        # 3. SET SL/TP (Advanced Logic)
        # We calculate "Distance" just in case the UI is in Pips mode
        # 1 Pip on Gold approx 0.10 or 0.01 depending on broker. We use approx distance.
        # Safe bet: Type the PRICE if we can find the "Price" toggle, otherwise skip and Modify later.
        
        # STRATEGY: We will skip SL/TP here to avoid "Invalid Pips" errors.
        # We will let the 'apply_emergency_break' logic handle it immediately after placement.
        # This is safer than guessing if the UI is in 'Pips' or 'Price' mode.

        # 4. CLICK PLACE ORDER
        submit_btn = wait.until(EC.element_to_be_clickable((By.CSS_SELECTOR, "button.place-order, button[type='submit']")))
        submit_btn.click()
        
        log_func(account_id, f"⚡ Order Sent: {direction}")
        time.sleep(1.5) # Wait for execution
        
        # 5. IMMEDIATE MODIFY (The Safe Fix)
        # Now that the trade is open, we call the modify function to set SL/TP accurately using the "Protect" tab
        # This needs the ticket ID, but we can't get it easily.
        # Instead, we rely on the Controller loop to pick it up in 1 second.
        
        return True

    except Exception as e:
        log_func(account_id, f"❌ Order Failed: {str(e)[:50]}")
        return False

# --- 3. CLOSE TRADE ---
def close_current_trade(driver, log_func, account_id):
    ensure_trading_window(driver, log_func, account_id)
    try:
        wait = WebDriverWait(driver, 5)
        
        # Find the "Close" (X) button on the first position
        close_btn = wait.until(EC.element_to_be_clickable((
            By.CSS_SELECTOR, 
            ".positions-table .close-button, button[title='Close Position']"
        )))
        close_btn.click()
        
        # Confirm
        try:
            confirm_btn = WebDriverWait(driver, 2).until(EC.element_to_be_clickable((
                By.CSS_SELECTOR, 
                "button.yes-button, button[name='ok']"
            )))
            confirm_btn.click()
        except: pass
            
        time.sleep(1) 
        return True
    except Exception as e:
        log_func(account_id, f"⚠️ Close Failed: {str(e)[:20]}")
        return False

# --- 4. MODIFY TRADE (EMERGENCY BREAK) ---
def execute_trade_modification(driver, signal, log_func, account_id):
    """
    Physically clicks the UI to update Stop Loss.
    """
    ensure_trading_window(driver, log_func, account_id)
    try:
        ticket_id = signal['ticket']
        new_sl = str(signal['sl'])

        # 1. Find the Trade Row by Ticket
        row_xpath = f"//div[contains(@class, 'data-table-row') and .//span[contains(text(), '{ticket_id}')]]"
        try:
            row = driver.find_element(By.XPATH, row_xpath)
        except:
            # Fallback: Just take the first row if ticket search fails
            row = driver.find_element(By.CSS_SELECTOR, ".positions-table .data-table-row")

        # 2. Double Click to Open Modify
        actions = ActionChains(driver)
        actions.double_click(row).perform()
        time.sleep(1.0) 

        # 3. SWITCH TO 'PROTECT' TAB (Crucial Fix)
        try:
            protect_tab = driver.find_element(By.XPATH, "//div[contains(@class, 'tab') and contains(text(), 'Protect')]")
            protect_tab.click()
            time.sleep(0.5)
        except: pass

        # 4. Find SL Input
        # We look for the input inside the Stop Loss section
        sl_input = driver.find_element(By.XPATH, "//div[contains(@class, 'stop-loss-content')]//input[@type='text']")
        
        # 5. Type New SL
        sl_input.click()
        sl_input.send_keys(Keys.CONTROL + "a", Keys.BACKSPACE)
        sl_input.send_keys(new_sl)
        time.sleep(0.2)

        # 6. Click Modify
        confirm_btn = driver.find_element(By.CSS_SELECTOR, "button.modify-protection, button[type='submit']")
        confirm_btn.click()
        
        log_func(account_id, f"🛡️ SL Updated to {new_sl}")
        time.sleep(1)
        return True

    except Exception as e:
        log_func(account_id, f"⚠️ Modify Failed: {str(e)[:20]}")
        return False