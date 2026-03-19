import time
import re
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.common.action_chains import ActionChains
from selenium.common.exceptions import StaleElementReferenceException

def safe_cleanup_popups(driver):
    """Closes only non-essential popups."""
    try:
        dialogs = driver.find_elements(By.CLASS_NAME, "dialog")
        for d in dialogs:
            try:
                d_class = d.get_attribute("class").lower()
                # STRICT PROTECTION: Don't close trade/position windows
                if any(protected in d_class for protected in ["chart", "narrow", "history", "positions", "position-window"]):
                    continue
                
                # Close others (like generic alerts)
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
        
        target_label = "Ask" if direction == "BUY" else "Bid"
        try:
            side_btn = driver.find_element(By.XPATH, f"//div[contains(@class, 'side-button')]//label[text()='{target_label}']/..")
            driver.execute_script("arguments[0].click();", side_btn)
            time.sleep(0.5)
        except: pass

        try:
            vol_input = driver.find_element(By.CSS_SELECTOR, ".volume-select input")
            vol_input.click()
            vol_input.send_keys(Keys.CONTROL + "a")
            vol_input.send_keys("0.01")
            driver.execute_script("arguments[0].dispatchEvent(new Event('change', { bubbles: true }));", vol_input)
        except: pass
        time.sleep(0.5)

        if sl_pips > 0:
            try:
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

        if tp_pips > 0:
            try:
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

def execute_trade_modification(driver, mod_signal, log_func, account_id):
    """
    Robust modification with StaleElement protection and Safe Closing.
    """
    try:
        ticket = mod_signal['ticket']
        target_sl_price = float(mod_signal['sl'])
        wait = WebDriverWait(driver, 5)

        def safe_close_dialog(specific_element=None):
            """
            Safely closes the dialog.
            If specific_element is provided (the dialog), tries to find close button inside it.
            Otherwise falls back to generic close button search.
            """
            try:
                # 1. Try finding close button relative to the dialog element if provided
                if specific_element:
                    try:
                        # Looking for the 'X' icon inside the specific dialog header
                        close_btn = specific_element.find_element(By.XPATH, ".//i[contains(@class, 'dialog-close-button') or @data-testid='win_close']")
                        driver.execute_script("arguments[0].click();", close_btn)
                        time.sleep(0.5)
                        return
                    except: pass

                # 2. Generic fallback (Careful! Might close main chart if specific fail)
                # Only use if we are desperate (e.g. aborting due to error)
                close_icons = driver.find_elements(By.CSS_SELECTOR, "[data-testid='win_close'], .dialog-close-button")
                # Filter visible ones, try to pick the one with highest z-index or last in DOM usually overlays
                visible_icons = [icon for icon in close_icons if icon.is_displayed()]
                if visible_icons:
                    # The last one is usually the top-most dialog
                    driver.execute_script("arguments[0].click();", visible_icons[-1])
                    time.sleep(0.5)
            except: pass

        # A. OPEN DIALOG
        dialog_already_open = False
        try:
            driver.find_element(By.CSS_SELECTOR, ".trade-dialog-content, .position-window")
            dialog_already_open = True
        except:
            dialog_already_open = False

        if not dialog_already_open:
            try:
                edit_btn = wait.until(EC.element_to_be_clickable((
                    By.CSS_SELECTOR, "[data-testid='edit_balance'], .icon_edit_balance"
                )))
                driver.execute_script("arguments[0].scrollIntoView({block: 'center'});", edit_btn)
                time.sleep(0.5)
                edit_btn.click()
            except:
                log_func(account_id, "⚠️ Cannot find Edit button.")
                return False

        # B. GET DATA & PRE-CHECK
        try:
            # Attempt to find the specific dialog container
            dialog = wait.until(EC.visibility_of_element_located((By.CSS_SELECTOR, ".dialog:has(.trade-dialog-content)")))
        except:
            try:
                # Fallback: Find content then go up to parent dialog
                content = wait.until(EC.visibility_of_element_located((By.CSS_SELECTOR, ".trade-dialog-content")))
                dialog = content.find_element(By.XPATH, "./ancestor::div[contains(@class, 'dialog')]")
            except:
                return False

        time.sleep(1.0)

        # Scrape Description
        try:
            desc_text = dialog.find_element(By.CSS_SELECTOR, "section.description").text.lower()
        except StaleElementReferenceException:
            time.sleep(0.5)
            desc_text = dialog.find_element(By.CSS_SELECTOR, "section.description").text.lower()

        is_buy = "buy" in desc_text
        match = re.search(r"at\s+([\d\.]+)", desc_text)
        if not match:
            log_func(account_id, "⚠️ Could not read Open Price.")
            safe_close_dialog(dialog)
            return False
        open_price = float(match.group(1))

        # --- ROBUST PRE-CHECK ---
        # Checks if SL is already set to the target value
        for _ in range(3):
            try:
                est_price_input = dialog.find_element(By.XPATH, 
                    ".//div[contains(@class, 'stop-loss')]//label[contains(text(), 'Estimated Price')]/following-sibling::div//input")
                
                current_val_str = est_price_input.get_attribute("value")
                if current_val_str:
                    current_sl_val = float(current_val_str)
                    if abs(current_sl_val - target_sl_price) < 0.05:
                        log_func(account_id, f"✅ SL is already {current_sl_val}. Closing.")
                        safe_close_dialog(dialog)
                        return True
                break
            except StaleElementReferenceException:
                time.sleep(0.2)
                continue
            except:
                break

        log_func(account_id, f"🛠️ Modifying Trade {ticket} ({'BUY' if is_buy else 'SELL'}) -> Target: {target_sl_price}")

        # C. CALCULATE PIPS
        if "." in str(open_price):
            decimals = len(str(open_price).split(".")[1])
            multiplier = 100 if decimals <= 2 else 10000
        else:
            multiplier = 100
        
        if is_buy:
            diff = open_price - target_sl_price
        else:
            diff = target_sl_price - open_price
        
        pips_to_enter = int(round(diff * multiplier))
        log_func(account_id, f"ℹ️ Calc: Open {open_price} | Pips: {pips_to_enter}")

        # D. INPUT PIPS
        try:
            sl_pips_input = dialog.find_element(By.CSS_SELECTOR, ".stop-loss input.numeric-input-field")
            driver.execute_script("arguments[0].click();", sl_pips_input)
            sl_pips_input.send_keys(Keys.CONTROL + "a", Keys.DELETE)
            time.sleep(0.1)
            
            text_to_type = str(pips_to_enter)
            sl_pips_input.send_keys(text_to_type)
            time.sleep(0.2)
            
            if sl_pips_input.get_attribute("value") != text_to_type:
                 driver.execute_script("arguments[0].value = arguments[1]; arguments[0].dispatchEvent(new Event('input'));", sl_pips_input, text_to_type)
        except StaleElementReferenceException:
            log_func(account_id, "⚠️ Stale Input. Retrying...")
            return False 

        time.sleep(0.5)
        
        # E. SUBMIT WITH RETRY (No explicit close after success)
        for _ in range(3):
            try:
                modify_btn = dialog.find_element(By.XPATH, ".//button[contains(text(), 'Modify') or contains(text(), 'Protect')]")
                
                if "disabled" in modify_btn.get_attribute("class"):
                    log_func(account_id, "⚠️ Modify button disabled (No change?).")
                    safe_close_dialog(dialog)
                    return True 
                    
                modify_btn.click()
                time.sleep(1)
                
                # We assume success and return True. 
                # Platform should auto-close.
                return True
            except StaleElementReferenceException:
                time.sleep(0.5)
                continue
        
        # If we failed to click modify after retries, try to clean up
        safe_close_dialog(dialog)
        return False

    except Exception as e:
        log_func(account_id, f"⚠️ Logic Failed: {e}")
        # Last resort cleanup
        try: 
            ActionChains(driver).send_keys(Keys.ESCAPE).perform()
        except: pass
        return False

    except Exception as e:
        log_func(account_id, f"⚠️ Modify Error: {str(e)[:50]}")
        return False