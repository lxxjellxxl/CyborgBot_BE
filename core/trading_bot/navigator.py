import time
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.common.action_chains import ActionChains

def safe_cleanup_popups(driver):
    """Closes only non-essential popups."""
    try:
        dialogs = driver.find_elements(By.CLASS_NAME, "dialog")
        for d in dialogs:
            d_class = d.get_attribute("class").lower()
            if any(protected in d_class for protected in ["chart", "narrow", "history", "positions"]):
                continue
            try:
                close_btn = d.find_element(By.CLASS_NAME, "dialog-close-button")
                driver.execute_script("arguments[0].click();", close_btn)
            except: pass
    except: pass

def navigate_order_panel_to_gold(driver, account_id, log_func):
    """
    Ensures the 'New Order' dialog is open for GOLD.
    """
    wait = WebDriverWait(driver, 10)
    try:
        safe_cleanup_popups(driver)
        
        # Check if already open (optimization)
        try:
            dialog = driver.find_element(By.CSS_SELECTOR, "div.dialog.narrow")
            if dialog.is_displayed():
                # Check if instrument is already GOLD
                current_instr = dialog.find_element(By.CSS_SELECTOR, ".instrument-dropdown .value").text
                if "GOLD" in current_instr: return True
        except: pass

        sidebar_btn = wait.until(EC.element_to_be_clickable((By.XPATH, "//i[@data-testid='new_order']")))
        driver.execute_script("arguments[0].click();", sidebar_btn)
        time.sleep(1) 

        dialog = wait.until(EC.presence_of_element_located((By.CSS_SELECTOR, "div.dialog.narrow")))
        
        # Select Gold if not selected
        try:
            current_instr = dialog.find_element(By.CSS_SELECTOR, ".instrument-dropdown .value").text
            if "GOLD" not in current_instr:
                dropdown_trigger = dialog.find_element(By.XPATH, ".//div[@class='instrument-dropdown']//div[@class='value']")
                driver.execute_script("arguments[0].click();", dropdown_trigger)
                time.sleep(0.5) 

                search_input = wait.until(EC.presence_of_element_located((By.CSS_SELECTOR, "input.instrument-search")))
                search_input.send_keys(Keys.CONTROL + "a", Keys.BACKSPACE)
                search_input.send_keys("GOLD")
                time.sleep(1) 

                gold_result = wait.until(EC.element_to_be_clickable((By.XPATH, "//div[contains(@class, 'instrument-search-result')]//div[@class='name' and text()='GOLD']")))
                driver.execute_script("arguments[0].click();", gold_result)
        except: pass
        
        return True
    except Exception as e:
        log_func(account_id, f"Nav Error: {str(e)[:20]}")
        return False

def place_market_order(driver, direction, sl_pips, tp_pips, log_func, account_id):
    try:
        wait = WebDriverWait(driver, 5)
        
        # 1. SWITCH DIRECTION
        target_label = "Ask" if direction == "BUY" else "Bid"
        try:
            side_btn = driver.find_element(By.XPATH, f"//div[contains(@class, 'side-button')]//label[text()='{target_label}']/..")
            driver.execute_script("arguments[0].click();", side_btn)
            time.sleep(0.5)
        except: pass

        # 2. FORCE 0.01 LOT
        try:
            vol_input = driver.find_element(By.CSS_SELECTOR, ".volume-select input")
            vol_input.click()
            vol_input.send_keys(Keys.CONTROL + "a")
            vol_input.send_keys("0.01")
            driver.execute_script("arguments[0].dispatchEvent(new Event('change', { bubbles: true }));", vol_input)
        except: pass
        time.sleep(0.5)

        # 3. SET STOP LOSS
        if sl_pips > 0:
            try:
                # Open checkbox if closed
                try:
                    driver.find_element(By.CSS_SELECTOR, ".protection .stop-loss input")
                except: 
                    sl_container = driver.find_element(By.XPATH, "//div[contains(@class, 'checkbox')][.//span[contains(text(), 'Stop Loss')]]")
                    driver.execute_script("arguments[0].click();", sl_container)
                    time.sleep(0.5)

                sl_input = driver.find_element(By.XPATH, "//div[contains(@class, 'stop-loss')]//input")
                sl_input.click()
                sl_input.send_keys(Keys.CONTROL + "a")
                time.sleep(0.1)
                sl_input.send_keys(str(sl_pips))
            except Exception as e:
                log_func(account_id, f"❌ SL Failed: {str(e)[:20]}")

        time.sleep(0.5) 

        # 4. SET TAKE PROFIT
        if tp_pips > 0:
            try:
                # Open checkbox if closed
                try:
                    driver.find_element(By.CSS_SELECTOR, ".protection .take-profit input")
                except: 
                    tp_container = driver.find_element(By.XPATH, "//div[contains(@class, 'checkbox')][.//span[contains(text(), 'Take Profit')]]")
                    driver.execute_script("arguments[0].click();", tp_container)
                    time.sleep(0.5)

                tp_input = driver.find_element(By.XPATH, "//div[contains(@class, 'take-profit')]//input")
                tp_input.click()
                tp_input.send_keys(Keys.CONTROL + "a")
                time.sleep(0.1)
                tp_input.send_keys(str(tp_pips))
            except Exception as e:
                log_func(account_id, f"❌ TP Failed: {str(e)[:20]}")

        # 5. SUBMIT
        try:
            submit_btn = driver.find_element(By.CSS_SELECTOR, "section.actions button")
            driver.execute_script("arguments[0].click();", submit_btn)
            time.sleep(2)
            return True
        except:
            return False

    except Exception as e:
        log_func(account_id, f"❌ Exec Error: {str(e)[:20]}")
        return False

def close_current_trade(driver, log_func, account_id):
    try:
        wait = WebDriverWait(driver, 3)
        try:
            close_btn = wait.until(EC.element_to_be_clickable((
                By.CSS_SELECTOR, 
                ".positions-table .data-table-row .data-table-action-cell .close-button"
            )))
            driver.execute_script("arguments[0].click();", close_btn)
            log_func(account_id, "🛑 Closing Position...")
        except:
            log_func(account_id, "⚠️ Close button not found (Trade might be gone)")
            return False

        try:
            confirm_btn = wait.until(EC.element_to_be_clickable((
                By.XPATH, 
                "//button[contains(@class, 'submit') or contains(text(), 'Close')]"
            )))
            if confirm_btn.is_displayed():
                driver.execute_script("arguments[0].click();", confirm_btn)
        except: pass
            
        time.sleep(2) 
        return True
    except Exception as e:
        log_func(account_id, f"❌ Close Error: {str(e)[:20]}")
        return False

def execute_trade_modification(driver, signal, log_func, account_id):
    """
    Physically clicks the UI to update Stop Loss.
    """
    try:
        ticket_id = signal['ticket']
        new_sl = str(signal['sl'])

        log_func(account_id, f"🛡️ Applying Emergency Break: Moving SL to {new_sl}")

        # 1. Find the Trade Row
        try:
            row_ticket = driver.find_element(By.XPATH, f"//span[contains(text(), '{ticket_id}')]")
        except:
            log_func(account_id, f"❌ Could not find trade {ticket_id} on screen.")
            return False

        # 2. Double Click to Open Modify Popup
        actions = ActionChains(driver)
        actions.double_click(row_ticket).perform()
        time.sleep(1.5) 

        # 3. Find SL Input
        try:
            sl_input = driver.find_element(By.XPATH, "//input[contains(@id, 'stop') or contains(@name, 'sl')]")
        except:
            actions.send_keys(Keys.TAB * 3).perform() 
            sl_input = driver.switch_to.active_element

        # 4. Type New SL
        if sl_input:
            sl_input.click()
            sl_input.send_keys(Keys.CONTROL + "a")
            sl_input.send_keys(Keys.DELETE)
            time.sleep(0.2)
            sl_input.send_keys(new_sl)
            time.sleep(0.5)

        # 5. Click Modify Button
        try:
            confirm_btn = driver.find_element(By.XPATH, "//button[contains(text(), 'Modify') or contains(text(), 'Update') or contains(text(), 'Protect')]")
            confirm_btn.click()
            time.sleep(1)
            return True
        except:
            log_func(account_id, "❌ Modify button not found")
            return False

    except Exception as e:
        log_func(account_id, f"⚠️ Modify Failed: {str(e)[:20]}")
        return False