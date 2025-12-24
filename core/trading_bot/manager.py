import re
import time
from selenium.webdriver.common.by import By
from .models import TradePosition
from django.utils import timezone

def manage_open_positions(driver, account_id, dash_log, target_profit=30.00):
    """
    Scans the live positions table. 
    Closes trades at target profit and updates the Django DB.
    """
    try:
        # 1. Find all rows in the positions table
        rows = driver.find_elements(By.CLASS_NAME, "data-table-row")
        
        # 2. If no rows exist, ensure our DB knows trades are closed
        if not rows:
            open_in_db = TradePosition.objects.filter(account_id=account_id, is_closed=False)
            for trade in open_in_db:
                trade.is_closed = True
                trade.close_time = timezone.now()
                trade.save()
            return "No Active Trades"

        for row in rows:
            try:
                # Extract profit value
                profit_elem = row.find_element(By.CLASS_NAME, "profit-loss")
                profit_text = profit_elem.get_attribute("title") # Usually contains "$10.50"
                
                # Parse the number
                match = re.search(r"(-?\d+\.\d+)", profit_text.replace("$", "").replace(",", ""))
                if not match: continue
                
                current_profit = float(match.group(1))

                # 3. Check against target
                if current_profit >= target_profit:
                    dash_log(f"Target Reached: ${current_profit}. Closing...")
                    close_btn = row.find_element(By.CLASS_NAME, "close-button")
                    driver.execute_script("arguments[0].click();", close_btn)
                    
                    # Update DB
                    # Note: We match by ticket if available, or just the latest open trade
                    trade = TradePosition.objects.filter(account_id=account_id, is_closed=False).last()
                    if trade:
                        trade.profit = current_profit
                        trade.is_closed = True
                        trade.close_time = timezone.now()
                        trade.save()
                    
                    return f"CLOSED WINNER: ${current_profit}"

            except Exception:
                continue
                
        return f"Monitoring {len(rows)} position(s)"
    except Exception as e:
        return f"Manager Error: {str(e)[:20]}"