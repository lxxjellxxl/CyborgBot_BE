import time
import re
from datetime import datetime
from decimal import Decimal 
from selenium.webdriver.common.by import By
from core.trading_bot.models import TradePosition, TradingAccount
from asgiref.sync import async_to_sync
from channels.layers import get_channel_layer
# FIX 1: Import the Detail Serializer to calculate scores
from core.trading_bot.serializers import TradePositionSerializer, TradingAccountDetailSerializer

def sync_trade_history(driver, account_id, log_func):
    updated_trades_list = []
    try:
        # 1. Switch to History Tab
        try:
            history_tab = driver.find_element(By.XPATH, "//div[contains(@class, 'tab-label') and text()='History']")
            driver.execute_script("arguments[0].click();", history_tab)
            time.sleep(1) 
        except: pass

        account = TradingAccount.objects.get(id=account_id)
        today_str = datetime.now().strftime("%d/%m/%Y") 
        
        processed_tickets = set()
        keep_scrolling = True
        scroll_attempts = 0
        max_scrolls = 20
        
        try:
            table_container = driver.find_element(By.CSS_SELECTOR, ".history-container .data-table-content")
        except:
            return [] 

        while keep_scrolling and scroll_attempts < max_scrolls:
            rows = driver.find_elements(By.CSS_SELECTOR, ".history-container .data-table-content .data-table-row")
            if not rows: break
            
            found_older_date = False

            for row in rows:
                try:
                    cells = row.find_elements(By.TAG_NAME, "span")
                    if len(cells) < 12: continue

                    def get_text(idx):
                        return driver.execute_script("return arguments[0].textContent;", cells[idx]).strip()

                    # --- 1. DATE CHECK ---
                    full_date_str = get_text(0)
                    date_part = full_date_str.split(' ')[0]

                    if date_part != today_str:
                        found_older_date = True
                        keep_scrolling = False
                        continue 

                    # --- 2. EXTRACT DATA ---
                    raw_ticket = get_text(1)
                    if raw_ticket in processed_tickets: continue
                    processed_tickets.add(raw_ticket)

                    raw_symbol = get_text(2)
                    raw_type   = get_text(4).upper()
                    raw_vol    = get_text(5)
                    raw_comm   = get_text(8)
                    raw_pnl    = get_text(10)
                    raw_comment= get_text(11)

                    # --- 3. CLEAN & CONVERT ---
                    def clean_num(val):
                        if not val: return 0.0
                        val = str(val).replace('−', '-').replace('‐', '-')
                        val = re.sub(r'[^\d.-]', '', val)
                        try: return float(val)
                        except: return 0.0

                    pnl_val = clean_num(raw_pnl)
                    comm_val = clean_num(raw_comm)
                    
                    # FIX: Convert Volume to String then Decimal for perfect DB matching
                    vol_float = clean_num(raw_vol)
                    vol_decimal = Decimal(str(vol_float)) 
                    
                    net_profit = pnl_val + comm_val

                    # Skip empty rows
                    if net_profit == 0.0 and pnl_val == 0.0 and comm_val == 0.0: 
                        continue

                    # Reason Parsing
                    exit_reason = "MANUAL"
                    if "[sl" in raw_comment.lower(): exit_reason = "SL"
                    elif "[tp" in raw_comment.lower(): exit_reason = "TP"

                    # --- 4. PARSE TIME ---
                    dt_obj = datetime.now()
                    try: dt_obj = datetime.strptime(full_date_str, "%d/%m/%Y %H:%M:%S")
                    except: pass

                    # --- 5. MATCHING LOGIC ---
                    
                    # A. Check if this Real Ticket ID is already saved
                    existing_trade = TradePosition.objects.filter(ticket_id=raw_ticket).first()
                    
                    if existing_trade:
                        if float(existing_trade.profit) != net_profit:
                            existing_trade.profit = net_profit
                            existing_trade.save()
                            updated_trades_list.append(existing_trade)
                        continue

                    # B. Find the Matching "AUTO" Trade
                    matching_trade = TradePosition.objects.filter(
                        account=account,
                        symbol=raw_symbol,
                        trade_type=raw_type,
                        volume=vol_decimal,
                        is_closed=False
                    ).order_by('open_time').first()

                    if matching_trade:
                        # MATCH FOUND: Close the AUTO trade
                        matching_trade.ticket_id = raw_ticket 
                        matching_trade.profit = net_profit
                        matching_trade.close_time = dt_obj
                        matching_trade.is_closed = True
                        
                        if exit_reason != "MANUAL":
                             current_reason = matching_trade.ai_reasoning or ""
                             if "CLOSED BY" not in current_reason:
                                matching_trade.ai_reasoning = current_reason + f"\n[CLOSED BY {exit_reason}]"
                        
                        matching_trade.save()
                        updated_trades_list.append(matching_trade)
                    else:
                        # NO MATCH: Create new Manual Trade entry
                        trade = TradePosition.objects.create(
                            account=account,
                            ticket_id=raw_ticket,
                            symbol=raw_symbol,
                            volume=vol_decimal,
                            trade_type=raw_type,
                            open_price=0, 
                            profit=net_profit,
                            close_time=dt_obj,
                            is_closed=True,
                            ai_reasoning=f"Manual/External Trade [{exit_reason}]"
                        )
                        updated_trades_list.append(trade)

                except Exception: continue
            
            # --- 6. SCROLL ---
            if not found_older_date:
                driver.execute_script("arguments[0].scrollTop += 600;", table_container)
                time.sleep(0.7)
                scroll_attempts += 1
            else:
                keep_scrolling = False

        if updated_trades_list:
            log_func(account_id, f"✅ History Synced: {len(updated_trades_list)} trades.")
            
            channel_layer = get_channel_layer()
            serializer = TradePositionSerializer(updated_trades_list, many=True)
            
            # FIX 2: Calculate fresh stats using the Detail Serializer
            # accessing .data runs the get_persona_scores method on the updated account data
            account_stats = TradingAccountDetailSerializer(account).data
            
            async_to_sync(channel_layer.group_send)(
                "bot_updates", 
                {
                    "type": "send_update", 
                    "data": {
                        "type": "history_update", 
                        "trades": serializer.data,
                        # FIX 3: Send the fresh stats to the frontend
                        "daily_stats": account_stats['daily_stats'],
                        "persona_scores": account_stats['persona_scores']
                    }
                }
            )
            
            try:
                pos_tab = driver.find_element(By.XPATH, "//div[contains(@class, 'tab-label') and text()='Positions']")
                driver.execute_script("arguments[0].click();", pos_tab)
            except: pass
            
    except Exception as e:
        log_func(account_id, f"Sync Error: {str(e)[:20]}")

    return updated_trades_list