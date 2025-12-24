from django.db import models
from django.utils.translation import gettext_lazy as _
from django.utils import timezone

class TradingAccount(models.Model):
    class AccountType(models.TextChoices):
        DEMO = 'DEMO', _('Demo Account')
        LIVE = 'LIVE', _('Live Account')

    class Broker(models.TextChoices):
        FXPRO = 'FXPRO', _('FxPro Direct')
        FXPRO_CTRADER = 'CTRADER', _('FxPro cTrader')
        MT5 = 'MT5', _('MetaTrader 5')

    # --- Configuration ---
    name = models.CharField(max_length=100, help_text="e.g. 'My Gold Scalper'")
    account_type = models.CharField(max_length=10, choices=AccountType.choices, default=AccountType.DEMO)
    broker = models.CharField(max_length=20, choices=Broker.choices, default=Broker.FXPRO)
    
    # --- Credentials ---
    login_id = models.CharField(max_length=255, verbose_name="Login ID / Email")
    password = models.CharField(max_length=255)
    server_name = models.CharField(max_length=100, blank=True, null=True, help_text="e.g. 'FxPro-Real06'")

    # --- Real Data (Updated by Bot) ---
    balance = models.DecimalField(max_digits=12, decimal_places=2, default=0.00)
    equity = models.DecimalField(max_digits=12, decimal_places=2, default=0.00, help_text="Live value including open trades")
    last_sync_time = models.DateTimeField(null=True, blank=True)
    
    is_active = models.BooleanField(default=True)

    def __str__(self):
        return f"{self.name} [{self.account_type}]"

class TradePosition(models.Model):
    account = models.ForeignKey(TradingAccount, on_delete=models.CASCADE, related_name='positions')
    ticket_id = models.CharField(max_length=50, unique=True)
    symbol = models.CharField(max_length=20, default="GOLD")
    volume = models.DecimalField(max_digits=10, decimal_places=2, default=0.01)
    trade_type = models.CharField(max_length=10) # 'BUY' or 'SELL'
    
    open_price = models.DecimalField(max_digits=12, decimal_places=5)
    close_price = models.DecimalField(max_digits=12, decimal_places=5, null=True, blank=True)
    sl_pips = models.IntegerField(default=100)
    tp_pips = models.IntegerField(default=300)
    profit = models.DecimalField(max_digits=12, decimal_places=2, default=0.00)
    
    # --- Context & Memory Fields ---
    h1_trend = models.CharField(max_length=20, null=True, blank=True) # e.g., 'BULLISH'
    m15_bias = models.CharField(max_length=20, null=True, blank=True) # e.g., 'REVERSAL'
    
    ai_reasoning = models.TextField(null=True, blank=True) # Gemini's full logic
    candle_snapshot = models.TextField(null=True, blank=True) # The B0-B30 coordinate string
    
    # --- NEW FIELDS FOR COUNCIL MEMORY ---
    voters = models.CharField(max_length=255, null=True, blank=True, help_text="List of personas who voted for this trade (e.g. 'WISE, RACER')")
    market_snapshot = models.JSONField(null=True, blank=True, help_text="Exact indicators at entry time (RSI, ATR, BB)")

    open_time = models.DateTimeField(auto_now_add=True)
    close_time = models.DateTimeField(null=True, blank=True)
    is_closed = models.BooleanField(default=False)

    def __str__(self):
        status = "CLOSED" if self.is_closed else "OPEN"
        return f"{self.trade_type} {self.symbol} | {status} | Profit: {self.profit}"