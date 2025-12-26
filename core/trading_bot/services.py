import time
import random
import os
import threading
from datetime import datetime
from django.conf import settings
from selenium import webdriver
from selenium.webdriver.chrome.service import Service as ChromeService
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.common.action_chains import ActionChains
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from webdriver_manager.chrome import ChromeDriverManager
import undetected_chromedriver as uc

# IMPORT MODELS & CONTROLLER
from .models import TradingAccount
from .controller import start_trading_loop 

# GLOBAL STATE
ACTIVE_DRIVERS = {}   # { account_id: SeleniumDriver }
RUNNING_THREADS = {}  # { account_id: Thread }
STOP_FLAGS = {}       # { account_id: Boolean }

def log_step(account_id, message):
    timestamp = datetime.now().strftime("%H:%M:%S")
    log_entry = f"[{timestamp}] {message}\n"
    print(f"[ACC {account_id}] {message}")
    # Optional: Write to file
    filepath = os.path.join(settings.BASE_DIR, f"bot_log_{account_id}.txt")
    try:
        with open(filepath, "a", encoding="utf-8") as f: f.write(log_entry)
    except: pass

def should_abort(account_id):
    return STOP_FLAGS.get(account_id, False)

# --- BROWSER INTERACTION HELPERS ---
def simulate_mouse_click(driver, element):
    try:
        driver.execute_script("arguments[0].scrollIntoView({block: 'center'});", element)
        time.sleep(0.3)
        ActionChains(driver).move_to_element(element).pause(random.uniform(0.2, 0.4)).click().perform()
    except:
        try: driver.execute_script("arguments[0].click();", element)
        except: pass

def human_type(driver, element, text):
    try:
        simulate_mouse_click(driver, element)
        element.send_keys(Keys.CONTROL + "a", Keys.DELETE)
        time.sleep(0.2)
        for char in text:
            element.send_keys(char)
            time.sleep(random.uniform(0.05, 0.12))
    except:
        driver.execute_script("arguments[0].value = arguments[1];", element, text)

# --- 1. DRIVER MANAGER (The Reusable Browser) ---
def get_or_login_driver(account_id):
    """
    Checks if a driver exists and is alive.
    If yes: Returns it (skips login).
    If no: Launches new Chrome, performs Login, returns it.
    """
    global ACTIVE_DRIVERS
    
    # A. REUSE CHECK
    if account_id in ACTIVE_DRIVERS:
        try:
            driver = ACTIVE_DRIVERS[account_id]
            _ = driver.title # Check if alive
            log_step(account_id, "♻️ Reusing existing Chrome Session...")
            return driver
        except:
            log_step(account_id, "⚠️ Existing driver died. Restarting...")
            del ACTIVE_DRIVERS[account_id]

    # B. LAUNCH NEW
    log_step(account_id, "🚀 Launching New Chrome...")
    try:
        account = TradingAccount.objects.get(id=account_id)
        
        # Use undetected-chromedriver with FIXED VERSION
        options = uc.ChromeOptions()
        options.add_argument("--start-maximized")
        # options.add_argument("--headless") 
        
        # Fixed version 142 to prevent crash
        driver = uc.Chrome(options=options, version_main=142)
        ACTIVE_DRIVERS[account_id] = driver
        wait = WebDriverWait(driver, 25)

        # ---------------------------------------------------------
        # 1. LOGIN SEQUENCE (RESTORED EXACT XPATHS)
        # ---------------------------------------------------------
        driver.get("https://direct.fxpro.com/login")
        time.sleep(5)
        
        # Handle iFrame if present
        if driver.find_elements(By.TAG_NAME, "iframe"):
            driver.switch_to.frame(driver.find_element(By.TAG_NAME, "iframe"))

        # Email (Restored)
        try: email_el = wait.until(EC.visibility_of_element_located((By.XPATH, "//input[@data-testid='email-input']")))
        except: email_el = wait.until(EC.visibility_of_element_located((By.XPATH, "/html/body/div[3]/div/div/div[1]/div[1]/div/input")))
        human_type(driver, email_el, account.login_id)

        # Password (Restored EXACT XPath)
        pass_el = wait.until(EC.visibility_of_element_located((By.XPATH, "/html/body/div[3]/div/div/div[1]/div[2]/div/input")))
        time.sleep(1)
        human_type(driver, pass_el, account.password)
        
        # Submit (Restored EXACT XPath)
        submit_btn = wait.until(EC.element_to_be_clickable((By.XPATH, "/html/body/div[3]/div/div/div[3]/button")))
        simulate_mouse_click(driver, submit_btn)
        
        driver.switch_to.default_content()
        wait.until(EC.url_contains("wallet"))
        log_step(account_id, "✔ Login Successful.")

        # ---------------------------------------------------------
        # 2. TERMINAL NAVIGATION (RESTORED EXACT XPATHS)
        # ---------------------------------------------------------
        time.sleep(4)
        
        # Click "Accounts" or similar button
        xp = "/html/body/div[1]/div[5]/div[3]/main/div[2]/div/div[2]/div[2]/div/div[1]/div[5]/div[2]/span" if account.account_type == 'LIVE' else "/html/body/div[1]/div[5]/div[3]/main/div[3]/div/div[2]/div[1]/div[2]/div[1]/span"
        simulate_mouse_click(driver, wait.until(EC.element_to_be_clickable((By.XPATH, xp))))
        
        time.sleep(2)
        
        # Click "Launch" or "Tenant" button
        tenent = "/html/body/div[1]/div[3]/div/div[3]/div[2]/div/div[3]/div[1]" if account.account_type == 'LIVE' else "/html/body/div[1]/div[5]/div[3]/main/div[3]/div/div[2]/div[2]/div/div[1]/div[5]/div[2]"
        simulate_mouse_click(driver, wait.until(EC.element_to_be_clickable((By.XPATH, tenent))))

        time.sleep(5)
        # Switch to new tab
        driver.switch_to.window(driver.window_handles[-1])

        # ---------------------------------------------------------
        # 3. SELECT ACCOUNT (RESTORED LOGIC)
        # ---------------------------------------------------------
        log_step(account_id, "🔍 Selecting Trading Account...")
        wait.until(EC.presence_of_element_located((By.CLASS_NAME, "account-menu-item")))
        time.sleep(3)

        if account.account_type == 'LIVE':
            # --- LIVE MODE: CLICK THE NAME IN THE FIRST ROW ---
            try:
                rows = driver.find_elements(By.CLASS_NAME, "account-menu-item")
                if rows:
                    first_row = rows[0]
                    # Specific LIVE selector from old file
                    name_element = first_row.find_element(By.CLASS_NAME, "account-name")
                    log_step(account_id, f"✔ LIVE Mode: Clicking account name '{name_element.text}'")
                    simulate_mouse_click(driver, name_element)
                else:
                    raise Exception("Account table is empty.")
            except Exception as e:
                # Fallback to just clicking the row if name fails
                if rows: simulate_mouse_click(driver, rows[0])
                else: raise e
        else:
            # --- DEMO MODE: SEARCH BY NAME ---
            target_server = account.server_name
            rows = driver.find_elements(By.CLASS_NAME, "account-menu-item")
            found = False
            for row in rows:
                if target_server in row.text:
                    simulate_mouse_click(driver, row)
                    found = True
                    break
            
            if not found: 
                log_step(account_id, f"⚠️ Server '{target_server}' not found, selecting first available.")
                if rows: simulate_mouse_click(driver, rows[0])

        return driver

    except Exception as e:
        log_step(account_id, f"❌ Driver Init Failed: {e}")
        if account_id in ACTIVE_DRIVERS: del ACTIVE_DRIVERS[account_id]
        if driver: driver.quit()
        raise e


# --- 2. THREAD MANAGER (The Bot Logic) ---
def run_bot_engine(account_id):
    """
    Starts the bot loop in a background thread.
    """
    global RUNNING_THREADS, STOP_FLAGS
    
    if account_id in RUNNING_THREADS and RUNNING_THREADS[account_id].is_alive():
        return False, "Bot is already running."

    # Reset Stop Flag
    STOP_FLAGS[account_id] = False

    def _worker():
        try:
            # A. Get Driver (Reused or New)
            driver = get_or_login_driver(account_id)
            
            # B. Handover to Controller
            log_step(account_id, "✔ Handover to Mother Controller.")
            start_trading_loop(driver, account_id, should_abort, log_step)
            
        except Exception as e:
            log_step(account_id, f"❌ Thread Crash: {e}")
        finally:
            log_step(account_id, "🛑 Bot Logic Stopped (Driver kept open).")

    # Start Thread
    t = threading.Thread(target=_worker, daemon=True)
    RUNNING_THREADS[account_id] = t
    t.start()
    
    return True, "Bot starting..."

def stop_bot_engine(account_id):
    """
    Sets the stop flag. The Controller's 'smart_sleep' will detect this instantly.
    Does NOT close the browser.
    """
    if account_id in RUNNING_THREADS:
        STOP_FLAGS[account_id] = True
        return True, "Stop signal sent."
    return False, "Bot not running."

def is_bot_running(account_id):
    return account_id in RUNNING_THREADS and RUNNING_THREADS[account_id].is_alive()