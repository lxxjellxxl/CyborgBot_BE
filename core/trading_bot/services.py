import time
import random
import os
import threading
import requests
import threading
import shutil
import subprocess
import re
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
    filepath = os.path.join(settings.BASE_DIR, f"bot_log_{account_id}.txt")
    try:
        with open(filepath, "a", encoding="utf-8") as f: f.write(log_entry)
    except: pass

def should_abort(account_id):
    return STOP_FLAGS.get(account_id, False)

def get_chrome_version():
    """Get installed Chrome major version"""
    try:
        result = subprocess.run(['google-chrome', '--version'], 
                               capture_output=True, text=True)
        version_str = result.stdout.strip()
        match = re.search(r'(\d+)\.', version_str)
        if match:
            return int(match.group(1))
    except:
        pass
    return None

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
            _ = driver.title
            log_step(account_id, "♻️ Reusing existing Chrome Session...")
            return driver
        except:
            log_step(account_id, "⚠️ Existing driver died. Restarting...")
            try:
                ACTIVE_DRIVERS[account_id].quit()
            except:
                pass
            del ACTIVE_DRIVERS[account_id]

    # B. LAUNCH NEW
    log_step(account_id, "🚀 Launching New Chrome...")
    driver = None
    
    try:
        account = TradingAccount.objects.get(id=account_id)
        
        # Clear ChromeDriver cache to force fresh download
        chrome_driver_dir = os.path.expanduser("~/.local/share/undetected_chromedriver")
        if os.path.exists(chrome_driver_dir):
            log_step(account_id, "🧹 Clearing ChromeDriver cache...")
            shutil.rmtree(chrome_driver_dir, ignore_errors=True)
        
        # Get Chrome version and use matching ChromeDriver
        chrome_version = get_chrome_version()
        log_step(account_id, f"📊 Detected Chrome version: {chrome_version}")
        
        options = uc.ChromeOptions()
        options.add_argument("--start-maximized")
        
        # Force the correct ChromeDriver version
        if chrome_version:
            driver = uc.Chrome(options=options, version_main=chrome_version)
        else:
            driver = uc.Chrome(options=options)
            
        ACTIVE_DRIVERS[account_id] = driver
        wait = WebDriverWait(driver, 25)

        # ---------------------------------------------------------
        # 1. LOGIN SEQUENCE
        # ---------------------------------------------------------
        driver.get("https://direct.fxpro.com/login")
        time.sleep(5)
        
        if driver.find_elements(By.TAG_NAME, "iframe"):
            driver.switch_to.frame(driver.find_element(By.TAG_NAME, "iframe"))

        try: 
            email_el = wait.until(EC.visibility_of_element_located((By.XPATH, "//input[@data-testid='email-input']")))
        except: 
            email_el = wait.until(EC.visibility_of_element_located((By.XPATH, "/html/body/div[3]/div/div/div[1]/div[1]/div/input")))
        human_type(driver, email_el, account.login_id)

        pass_el = wait.until(EC.visibility_of_element_located((By.XPATH, "/html/body/div[3]/div/div/div[1]/div[2]/div/input")))
        time.sleep(1)
        human_type(driver, pass_el, account.password)
        
        submit_btn = wait.until(EC.element_to_be_clickable((By.XPATH, "/html/body/div[3]/div/div/div[3]/button")))
        simulate_mouse_click(driver, submit_btn)
        
        driver.switch_to.default_content()
        wait.until(EC.url_contains("wallet"))
        log_step(account_id, "✔ Login Successful.")

        # ---------------------------------------------------------
        # 2. TERMINAL NAVIGATION
        # ---------------------------------------------------------
        time.sleep(4)
        
        try:
            accounts_tab_xp = "//div[contains(text(), 'Accounts') or contains(@class, 'account')]" 
        except:
            pass 

        time.sleep(2)

        if account.account_type == 'LIVE':
            log_step(account_id, "🔍 Using LIVE Navigation XPaths...")
            if account.name == 'Ahmed Abdo Live':
                log_step(account_id, "🔍 Using Ahmed abdo XPaths...")
                trade_btn_xpath = "/html/body/div[1]/div[5]/div[3]/main/div[2]/div/div[2]/div[2]/div/div[1]/div[5]/div[2]"
            else:
                trade_btn_xpath = "/html/body/div[1]/div[5]/div[3]/main/div[2]/div/div[2]/div[2]/div/div[2]/div[5]/div[2]"
            
            try:
                trade_btn = wait.until(EC.element_to_be_clickable((By.XPATH, trade_btn_xpath)))
                simulate_mouse_click(driver, trade_btn)
                log_step(account_id, "✅ Clicked Trade button (Live)")
            except Exception as e:
                log_step(account_id, "❌ Live Trade button XPath failed.")
                raise e

            time.sleep(5)

            launch_btn_xpath = "/html/body/div[1]/div[3]/div/div[3]/div[2]/div/div[3]/div[1]"
            try:
                launch_btn = wait.until(EC.element_to_be_clickable((By.XPATH, launch_btn_xpath)))
                simulate_mouse_click(driver, launch_btn)
                log_step(account_id, "✅ Clicked Launch/Tenant button (Live)")
            except Exception as e:
                log_step(account_id, "❌ Live Launch button XPath failed.")
                raise e

        else:
            log_step(account_id, f"🔍 Using DEMO Navigation Logic...")
            
            try:
                demo_tab = wait.until(EC.element_to_be_clickable((By.XPATH, "//div[@data-testid='tab-demo-account']")))
                simulate_mouse_click(driver, demo_tab)
                log_step(account_id, "✅ Clicked 'Demo accounts' tab")
                time.sleep(3) 
            except:
                try: 
                    demo_tab = driver.find_element(By.XPATH, "/html/body/div[1]/div[5]/div[3]/main/div[3]/div/div[2]/div[1]/div[2]")
                    simulate_mouse_click(driver, demo_tab)
                    log_step(account_id, "✅ Clicked 'Demo accounts' tab (Fallback)")
                    time.sleep(3)
                except Exception as e:
                    log_step(account_id, f"⚠️ Demo Tab interaction failed: {e}")

            trade_btn_xpath = "/html/body/div[1]/div[5]/div[3]/main/div[3]/div/div[2]/div[2]/div/div[1]/div[5]/div[2]"
            try:
                trade_btn = wait.until(EC.element_to_be_clickable((By.XPATH, trade_btn_xpath)))
                simulate_mouse_click(driver, trade_btn)
                log_step(account_id, f"✅ Clicked Trade button (Demo)")
            except Exception as e:
                log_step(account_id, f"❌ Demo Trade button failed.")
                raise e

            time.sleep(5)

            try:
                launch_xpath = "//div[contains(@class, 'ui-button')]//span[contains(text(), 'Launch') or contains(text(), 'Web')]/ancestor::div[contains(@class, 'ui-button')]"
                launch_btn = wait.until(EC.element_to_be_clickable((By.XPATH, launch_xpath)))
                simulate_mouse_click(driver, launch_btn)
                log_step(account_id, "✅ Clicked Launch button (Demo)")
            except Exception as e:
                log_step(account_id, "⚠️ Demo Launch button not found by text. Trying fallback...")
                try:
                    launch_btn_xpath = "/html/body/div[1]/div[3]/div/div[3]/div[2]/div/div[3]/div[1]"
                    launch_btn = driver.find_element(By.XPATH, launch_btn_xpath)
                    simulate_mouse_click(driver, launch_btn)
                except:
                    log_step(account_id, "❌ All Launch attempts failed.")
                    raise e
        
        time.sleep(5)
        if len(driver.window_handles) > 1:
            driver.switch_to.window(driver.window_handles[-1])
            log_step(account_id, "✅ Switched to Trading Tab")
        else:
            log_step(account_id, "⚠️ No new tab detected. Checking if it opened in same window...")

        log_step(account_id, "🔍 Checking for Account Selection Dialog...")
        try:
            wait.until(EC.presence_of_element_located((By.CLASS_NAME, "account-select-dialog")))
            
            target_number = str(account.account_number).strip()
            items = driver.find_elements(By.CLASS_NAME, "account-menu-item")
            
            found = False
            for item in items:
                try:
                    name_el = item.find_element(By.CLASS_NAME, "account-name")
                    if target_number in name_el.text:
                        log_step(account_id, f"✔ Found matching account in dialog: {name_el.text}")
                        simulate_mouse_click(driver, item)
                        found = True
                        break
                except:
                    continue
            
            if not found:
                 log_step(account_id, f"⚠️ Account number '{target_number}' not found. Clicking first available.")
                 if items:
                     simulate_mouse_click(driver, items[0])

        except Exception as e:
            log_step(account_id, "ℹ️ No Account Selection Dialog found. Assuming ready.")
            pass
            
        time.sleep(3)
        return driver

    except Exception as e:
        log_step(account_id, f"❌ Driver Init Failed: {e}")
        if account_id in ACTIVE_DRIVERS: 
            del ACTIVE_DRIVERS[account_id]
        if driver:
            try:
                driver.quit()
            except:
                pass
        raise e

# --- 2. THREAD MANAGER ---
def run_bot_engine(account_id):
    global RUNNING_THREADS, STOP_FLAGS
    
    if account_id in RUNNING_THREADS and RUNNING_THREADS[account_id].is_alive():
        return False, "Bot is already running."

    STOP_FLAGS[account_id] = False

    def _worker():
        try:
            driver = get_or_login_driver(account_id)
            log_step(account_id, "✔ Handover to Mother Controller.")
            start_trading_loop(driver, account_id, should_abort, log_step)
        except Exception as e:
            log_step(account_id, f"❌ Thread Crash: {e}")
        finally:
            log_step(account_id, "🛑 Bot Logic Stopped (Driver kept open).")

    t = threading.Thread(target=_worker, daemon=True)
    RUNNING_THREADS[account_id] = t
    t.start()
    return True, "Bot starting..."

def stop_bot_engine(account_id):
    if account_id in RUNNING_THREADS:
        STOP_FLAGS[account_id] = True
        return True, "Stop signal sent."
    return False, "Bot not running."

def is_bot_running(account_id):
    return account_id in RUNNING_THREADS and RUNNING_THREADS[account_id].is_alive()