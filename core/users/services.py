import time
import random
import traceback
import os
from datetime import datetime
from django.conf import settings
from django.utils import timezone
from selenium import webdriver
from selenium.webdriver.chrome.service import Service as ChromeService
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.common.action_chains import ActionChains
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from webdriver_manager.chrome import ChromeDriverManager
from .models import TradingAccount
from .bot_logic import start_trading_loop 

ACTIVE_DRIVERS = {}
STOP_FLAGS = {} 

def log_step(account_id, message):
    timestamp = datetime.now().strftime("%H:%M:%S")
    log_entry = f"[{timestamp}] {message}\n"
    print(f"[ACC {account_id}] {message}")
    filename = f"bot_log_{account_id}.txt"
    filepath = os.path.join(settings.BASE_DIR, filename)
    try:
        with open(filepath, "a", encoding="utf-8") as f:
            f.write(log_entry)
    except Exception:
        pass

def should_abort(account_id):
    if STOP_FLAGS.get(account_id, False):
        log_step(account_id, "⚠ STOP SIGNAL RECEIVED.")
        return True
    return False

def simulate_mouse_click(driver, element):
    try:
        driver.execute_script("arguments[0].scrollIntoView({block: 'center'});", element)
        time.sleep(0.3)
        actions = ActionChains(driver)
        actions.move_to_element(element)
        actions.pause(random.uniform(0.2, 0.5))
        actions.click()
        actions.perform()
    except Exception:
        driver.execute_script("arguments[0].click();", element)

def human_type(driver, element, text):
    simulate_mouse_click(driver, element)
    element.send_keys(Keys.CONTROL + "a")
    time.sleep(0.1)
    element.send_keys(Keys.DELETE)
    time.sleep(0.2)
    for char in text:
        element.send_keys(char)
        time.sleep(random.uniform(0.05, 0.15)) 

def run_bot_engine(account_id):
    global ACTIVE_DRIVERS, STOP_FLAGS
    
    if account_id in ACTIVE_DRIVERS: return False, "Bot is already running!"
    STOP_FLAGS[account_id] = False
    open(f"bot_log_{account_id}.txt", "w").close() 
    log_step(account_id, "--- ENGINE STARTED ---")

    driver = None
    max_retries = 3

    for attempt in range(1, max_retries + 1):
        if should_abort(account_id): break

        try:
            account = TradingAccount.objects.get(id=account_id)
            log_step(account_id, f"Attempt {attempt}/{max_retries} Starting...")

            if driver:
                try: driver.quit()
                except: pass
                driver = None

            chrome_options = Options()
            chrome_options.add_argument("--incognito")
            chrome_options.add_argument("--start-maximized")
            chrome_options.add_experimental_option("detach", True) 

            driver = webdriver.Chrome(
                service=ChromeService(ChromeDriverManager().install()),
                options=chrome_options
            )
            ACTIVE_DRIVERS[account_id] = driver
            
            # --- 1-7. LOGIN & NAVIGATION SEQUENCE ---
            # (Summarized standard login steps to save space - identical to before)
            log_step(account_id, "Login Sequence Initiated...")
            driver.get("https://direct.fxpro.com/login")
            time.sleep(5)
            wait = WebDriverWait(driver, 25)

            try: driver.switch_to.frame(wait.until(EC.presence_of_element_located((By.TAG_NAME, "iframe"))))
            except: pass

            try: human_type(driver, wait.until(EC.visibility_of_element_located((By.XPATH, "//input[@data-testid='email-input']"))), account.login_id)
            except: human_type(driver, wait.until(EC.visibility_of_element_located((By.XPATH, "/html/body/div[3]/div/div/div[1]/div[1]/div/input"))), account.login_id)
            
            human_type(driver, wait.until(EC.visibility_of_element_located((By.XPATH, "/html/body/div[3]/div/div/div[1]/div[2]/div/input"))), account.password)
            simulate_mouse_click(driver, wait.until(EC.element_to_be_clickable((By.XPATH, "/html/body/div[3]/div/div/div[3]/button"))))
            
            driver.switch_to.default_content()
            try: wait.until(EC.url_contains("wallet"))
            except: raise Exception("URL verification failed.")
            time.sleep(4)

            if account.account_type == 'LIVE': xp = "/html/body/div[1]/div[5]/div[3]/main/div[3]/div/div[2]/div[1]/div[1]"
            else: xp = "/html/body/div[1]/div[5]/div[3]/main/div[3]/div/div[2]/div[1]/div[2]/div[1]/span"
            try: simulate_mouse_click(driver, wait.until(EC.element_to_be_clickable((By.XPATH, xp))))
            except: pass

            time.sleep(2)
            simulate_mouse_click(driver, wait.until(EC.element_to_be_clickable((By.XPATH, "/html/body/div[1]/div[5]/div[3]/main/div[3]/div/div[2]/div[2]/div/div[1]/div[5]/div[2]"))))
            time.sleep(2)
            simulate_mouse_click(driver, wait.until(EC.element_to_be_clickable((By.XPATH, "/html/body/div[1]/div[3]/div/div[3]/div[2]/div/div[3]/div[1]/span/span"))))

            time.sleep(5)
            driver.switch_to.window(driver.window_handles[-1])
            
            # Select Account in List
            target_server = account.server_name
            wait.until(EC.presence_of_element_located((By.XPATH, "/html/body/main/div/div/div/div[2]/div/div/div/div[2]/div[1]/div/div[1]")))
            rows = driver.find_elements(By.CLASS_NAME, "account-menu-item")
            found = False
            for row in rows:
                if target_server in row.text:
                    simulate_mouse_click(driver, row)
                    found = True
                    break
            if not found: raise Exception("Server Name not found.")
            
            log_step(account_id, "✔ Connected to WebTerminal.")
            time.sleep(5)

            # --- 8. CLEANUP UI (Close Extra Window) ---
            log_step(account_id, "Checking for popups...")
            try:
                short_wait = WebDriverWait(driver, 5)
                close_btn = short_wait.until(EC.element_to_be_clickable((By.XPATH, "/html/body/main/div/div/div/div[2]/div[1]/div/div[1]/div[1]/div[1]/div[3]/div[5]")))
                simulate_mouse_click(driver, close_btn)
                log_step(account_id, "✔ Closed extra window.")
            except:
                pass

            # --- 9. SELECT INSTRUMENT (GOLD) ---
            log_step(account_id, "Selecting GOLD Instrument...")
            
            # A. Click Dropdown
            dropdown_xpath = "/html/body/main/div/div/div/div[2]/div[1]/div/div[1]/div[1]/div[1]/div/div"
            dropdown = wait.until(EC.element_to_be_clickable((By.XPATH, dropdown_xpath)))
            simulate_mouse_click(driver, dropdown)
            
            # B. Search for GOLD
            search_input_xpath = "/html/body/main/div/div/div/div[2]/div[3]/div/input"
            search_input = wait.until(EC.visibility_of_element_located((By.XPATH, search_input_xpath)))
            
            # Use human_type but add a small pause for the UI to catch up
            human_type(driver, search_input, "GOLD")
            time.sleep(2) # Vital for the dynamic list to filter
            
            # C. Click THE FIRST Result
            # Using (//div[@class='instrument-search-result'])[1] ensures we grab ONLY the top one.
            try:
                # We search for a div with class 'name' that has the exact text 'GOLD'
                # This is more precise than just clicking the first result.
                exact_gold_xpath = "//div[contains(@class, 'instrument-search-result')]//div[@class='name' and text()='GOLD']"
                
                gold_result = wait.until(EC.element_to_be_clickable((By.XPATH, exact_gold_xpath)))
                
                log_step(account_id, f"Targeting exact instrument: {gold_result.text}")
                simulate_mouse_click(driver, gold_result)
                log_step(account_id, "✔ GOLD selected accurately.")
                
            except Exception as e:
                log_step(account_id, f"Exact GOLD selection failed, trying first result fallback: {e}")
                # Fallback to the first item if exact match fails
                fallback_xpath = "(//div[contains(@class, 'instrument-search-result')])[1]"
                simulate_mouse_click(driver, driver.find_element(By.XPATH, fallback_xpath))
                log_step(account_id, "✔ GOLD selected via fallback.")

            time.sleep(3) # Let chart load

            # --- 10. SELECT TIMEFRAME (5 MIN) ---
            log_step(account_id, "Setting timeframe to 5 minutes...")
            try:
                # Look for the button by its title attribute 'Period'
                period_btn = wait.until(EC.element_to_be_clickable((By.XPATH, "//i[@title='Period']")))
                simulate_mouse_click(driver, period_btn)
                
                # Click the 5 Minutes Option specifically by text
                m5_option = wait.until(EC.element_to_be_clickable((By.XPATH, "//span[text()='5 minutes']")))
                simulate_mouse_click(driver, m5_option)
                
                log_step(account_id, "✔ Timeframe set to 5M.")
                time.sleep(5)  # Give the SVG 5 seconds to draw the new candles
            except Exception as e:
                log_step(account_id, f"Timeframe selection failed: {e}")
            
            # --- 11. HANDOVER TO BOT ---
            start_trading_loop(driver, account_id, should_abort, log_step)
            
            return True, "Bot Stopped."

        except Exception as e:
            log_step(account_id, f"CRASH: {e}")
            traceback.print_exc()
            if attempt == max_retries:
                if account_id in ACTIVE_DRIVERS: del ACTIVE_DRIVERS[account_id]
                return False, str(e)
            time.sleep(5)
            continue
    
    return False, "Process ended."

def stop_bot_engine(account_id):
    global STOP_FLAGS, ACTIVE_DRIVERS
    STOP_FLAGS[account_id] = True
    if account_id in ACTIVE_DRIVERS: del ACTIVE_DRIVERS[account_id]
    try:
        acc = TradingAccount.objects.get(id=account_id)
        acc.last_run_status = "Stopping..."
        acc.save()
    except: pass
    return True, "Stopping..."

def is_bot_running(account_id):
    return account_id in ACTIVE_DRIVERS