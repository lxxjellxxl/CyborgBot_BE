from django.contrib import admin
from django.contrib import messages
from django.utils.html import format_html
from django.urls import path, reverse
from django.shortcuts import redirect
from django.utils.http import urlencode
from .models import TradingAccount, TradePosition

# --- IMPORT CHECK ---
# We try to import from 'service' or 'services' depending on your file naming
try:
    from .service import run_bot_engine, stop_bot_engine, is_bot_running
except ImportError:
    try:
        from .services import run_bot_engine, stop_bot_engine, is_bot_running
    except ImportError:
        # Fallback to prevent crash if file is missing
        def run_bot_engine(id): return False, "Service file missing"
        def stop_bot_engine(id): return False, "Service file missing"
        def is_bot_running(id): return False

# ==============================================================================
# 1. TRADING ACCOUNT ADMIN
# ==============================================================================
@admin.register(TradingAccount)
class TradingAccountAdmin(admin.ModelAdmin):
    list_display = ('name', 'account_type', 'balance_display', 'bot_status_badge', 'bot_status_button')
    list_filter = ('account_type', 'broker', 'is_active')
    search_fields = ('name', 'login_id')
    
    # We removed the Inline History to keep this page clean
    inlines = [] 

    fieldsets = (
        ('Control Panel', {
            'fields': ('bot_status_button_large', 'view_history_link', 'last_sync_time')
        }),
        ('Live Metrics', {
            'fields': ('balance', 'equity')
        }),
        ('Account Details', {
            'fields': ('name', 'account_type', 'broker', 'is_active')
        }),
        ('Credentials', {
            'fields': ('login_id', 'password', 'server_name'),
            'classes': ('collapse',) 
        }),
    )
    readonly_fields = ('balance', 'equity', 'last_sync_time', 'bot_status_button_large', 'view_history_link')

    def balance_display(self, obj):
        return f"${obj.balance}"
    balance_display.short_description = "Balance"

    # --- CUSTOM BUTTONS ---
    
    def view_history_link(self, obj):
        """Link to the separate History Page filtered for this account"""
        if not obj.pk: return "-"
        # This URL points to the TradePosition change list
        url = reverse('admin:trading_bot_tradeposition_changelist')
        query = urlencode({'account__id__exact': obj.pk})
        return format_html('<a href="{}?{}" class="button" style="padding:8px 12px; background:#555; color:white; border-radius:4px; font-weight:bold;">📂 Open Trade History</a>', url, query)
    view_history_link.short_description = "Trade Log"

    def get_urls(self):
        urls = super().get_urls()
        custom_urls = [
            path('<int:account_id>/run/', self.admin_site.admin_view(self.run_bot_view), name='bot-run'),
            path('<int:account_id>/stop/', self.admin_site.admin_view(self.stop_bot_view), name='bot-stop'),
        ]
        return custom_urls + urls

    def run_bot_view(self, request, account_id):
        success, msg = run_bot_engine(account_id)
        level = messages.SUCCESS if success else messages.ERROR
        self.message_user(request, msg, level)
        return redirect(request.META.get('HTTP_REFERER', 'admin:index'))

    def stop_bot_view(self, request, account_id):
        success, msg = stop_bot_engine(account_id)
        level = messages.WARNING if success else messages.ERROR
        self.message_user(request, msg, level)
        return redirect(request.META.get('HTTP_REFERER', 'admin:index'))

    def bot_status_badge(self, obj):
        running = is_bot_running(obj.pk)
        color = "green" if running else "gray"
        state = "RUNNING" if running else "STOPPED"
        return format_html(
            '<span style="color: white; background-color: {}; padding: 3px 8px; border-radius: 10px; font-size: 10px;">{}</span>',
            color, state
        )
    bot_status_badge.short_description = "State"

    def bot_status_button(self, obj):
        return self._render_button(obj, size="small")
    bot_status_button.short_description = "Action"

    def bot_status_button_large(self, obj):
        return self._render_button(obj, size="large")
    bot_status_button_large.short_description = "Control"

    def _render_button(self, obj, size="small"):
        if not obj.pk: return "Save first"
        running = is_bot_running(obj.pk)
        url = reverse('admin:bot-stop' if running else 'admin:bot-run', args=[obj.pk])
        label = "⏹ STOP BOT" if running else "▶ START BOT"
        color = "#e74c3c" if running else "#2ecc71"
        padding = "12px 24px" if size == "large" else "6px 12px"
        
        return format_html(
            '<a href="{}" style="background-color: {}; color: white; padding: {}; border-radius: 4px; text-decoration: none; font-weight: bold;">{}</a>',
            url, color, padding, label
        )

# ==============================================================================
# 2. TRADE POSITION ADMIN (The Separate History Console)
# ==============================================================================
@admin.register(TradePosition)
class TradePositionAdmin(admin.ModelAdmin):
    list_display = ('ticket_id', 'symbol', 'trade_type_colored', 'volume', 'profit_colored', 'voters_display', 'close_time_display')
    list_filter = ('is_closed', 'trade_type', 'account', 'voters', ('open_time', admin.DateFieldListFilter))
    search_fields = ('ticket_id', 'ai_reasoning', 'voters')
    list_per_page = 20
    
    fieldsets = (
        ('Trade Info', {
            'fields': (('ticket_id', 'account'), ('symbol', 'trade_type', 'volume'), ('open_price', 'close_price'))
        }),
        ('Outcome', {
            'fields': ('profit', 'is_closed', ('open_time', 'close_time'))
        }),
        ('The Council (AI)', {
            'fields': ('voters', 'ai_reasoning_formatted', 'market_snapshot_pretty'),
            'classes': ('wide',)
        }),
    )
    
    readonly_fields = ('open_time', 'close_time', 'profit', 'voters', 'market_snapshot_pretty', 'ai_reasoning_formatted')

    def trade_type_colored(self, obj):
        color = "green" if obj.trade_type == "BUY" else "red"
        return format_html('<span style="color: {}; font-weight: bold;">{}</span>', color, obj.trade_type)
    trade_type_colored.short_description = "Type"

    def profit_colored(self, obj):
        val = float(obj.profit)
        color = "green" if val > 0 else "red" if val < 0 else "gray"
        return format_html('<span style="color: {}; font-weight: bold;">${}</span>', color, val)
    profit_colored.short_description = "PnL"

    def voters_display(self, obj):
        if not obj.voters: return "-"
        return format_html('<span style="background: #333; color: #fff; padding: 2px 6px; border-radius: 4px;">{}</span>', obj.voters)
    voters_display.short_description = "Council Voters"

    def close_time_display(self, obj):
        return obj.close_time.strftime("%H:%M:%S") if obj.close_time else "-"
    close_time_display.short_description = "Closed At"

    def ai_reasoning_formatted(self, obj):
        if not obj.ai_reasoning: return "-"
        return format_html('<pre style="white-space: pre-wrap; font-family: monospace; background: #f5f5f5; padding: 10px; border-radius:5px;">{}</pre>', obj.ai_reasoning)
    ai_reasoning_formatted.short_description = "Brain Logic"

    def market_snapshot_pretty(self, obj):
        import json
        if not obj.market_snapshot: return "-"
        try:
            # Handle both dict and string representation
            if isinstance(obj.market_snapshot, dict):
                data = obj.market_snapshot
            else:
                data = json.loads(obj.market_snapshot)
                
            pretty = json.dumps(data, indent=2)
            return format_html('<pre style="background: #222; color: #0f0; padding: 10px; border-radius:5px;">{}</pre>', pretty)
        except:
            return str(obj.market_snapshot)
    market_snapshot_pretty.short_description = "Market Snapshot (JSON)"