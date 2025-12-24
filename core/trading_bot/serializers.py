from rest_framework import serializers
from .models import TradingAccount, TradePosition
from django.utils import timezone
from django.db.models import Sum
import pytz

class TradePositionSerializer(serializers.ModelSerializer):
    class Meta:
        model = TradePosition
        fields = '__all__'

class TradingAccountSerializer(serializers.ModelSerializer):
    daily_stats = serializers.SerializerMethodField()
    class Meta:
        model = TradingAccount
        fields = ['id', 'name', 'login_id', 'account_type', 'broker', 'is_active', 'balance', 'equity', 'daily_stats']

    def get_daily_stats(self, obj):
        try:
            # 1. Safety Check: If no timezone support, return 0
            try:
                cairo_tz = pytz.timezone('Africa/Cairo')
                now_cairo = timezone.now().astimezone(cairo_tz)
                today_start = now_cairo.replace(hour=0, minute=0, second=0, microsecond=0)
            except Exception:
                # Fallback to UTC if timezone fails
                today_start = timezone.now().replace(hour=0, minute=0, second=0, microsecond=0)

            # 2. Filter Trades
            todays_trades = TradePosition.objects.filter(account=obj, is_closed=True, close_time__gte=today_start)

            # 3. Safe Aggregation
            profit_sum = todays_trades.filter(profit__gt=0).aggregate(total=Sum('profit'))['total'] or 0.0
            loss_sum = todays_trades.filter(profit__lt=0).aggregate(total=Sum('profit'))['total'] or 0.0

            return {"profit": round(float(profit_sum), 2), "loss": abs(round(float(loss_sum), 2))}
        
        except Exception as e:
            print(f"⚠️ [Serializer] Daily Stats Error: {e}")
            return {"profit": 0, "loss": 0}

class TradingAccountDetailSerializer(serializers.ModelSerializer):
    open_positions = serializers.SerializerMethodField()
    recent_history = serializers.SerializerMethodField()
    daily_stats = serializers.SerializerMethodField()
    persona_scores = serializers.SerializerMethodField()

    class Meta:
        model = TradingAccount
        fields = [
            'id', 'name', 'login_id', 'server_name', 'account_type', 
            'broker', 'balance', 'equity', 'is_active', 'last_sync_time',
            'open_positions', 'recent_history', 'daily_stats', 'persona_scores'
        ]

    def get_open_positions(self, obj):
        qs = obj.positions.filter(is_closed=False).order_by('-open_time')
        return TradePositionSerializer(qs, many=True).data

    def get_recent_history(self, obj):
        qs = obj.positions.filter(is_closed=True).order_by('-close_time')[:50]
        return TradePositionSerializer(qs, many=True).data
    
    def get_daily_stats(self, obj):
        # --- SAFE VERSION ---
        try:
            cairo_tz = pytz.timezone('Africa/Cairo')
            now_cairo = timezone.now().astimezone(cairo_tz)
            today_start = now_cairo.replace(hour=0, minute=0, second=0, microsecond=0)
            
            todays_trades = TradePosition.objects.filter(account=obj, is_closed=True, close_time__gte=today_start)
            
            profit_sum = todays_trades.filter(profit__gt=0).aggregate(total=Sum('profit'))['total'] or 0.0
            loss_sum = todays_trades.filter(profit__lt=0).aggregate(total=Sum('profit'))['total'] or 0.0
            
            return {"profit": round(float(profit_sum), 2), "loss": abs(round(float(loss_sum), 2))}
        except Exception as e:
            print(f"⚠️ [Serializer] Daily Stats Calculation Failed: {e}")
            return {"profit": 0, "loss": 0}

    def get_persona_scores(self, obj):
        scores = {"WISE": 0, "RECKLESS": 0, "ANALYST": 0}
        try:
            trades = obj.positions.exclude(voters__isnull=True).exclude(voters__exact='')
            
            for trade in trades:
                if not trade.voters or trade.voters.strip() == "":
                    continue

                raw_voters = trade.voters.replace(" ", "").upper().split(',')
                
                try:
                    profit_val = float(trade.profit)
                except:
                    profit_val = 0.0
                    
                is_win = profit_val > 0
                
                for persona in raw_voters:
                    if persona == "RACER": persona = "RECKLESS"
                    
                    if persona in scores:
                        if is_win:
                            scores[persona] += 1
                        else:
                            scores[persona] -= 1
            return scores
        except Exception as e:
             print(f"⚠️ [Serializer] Score Calc Failed: {e}")
             return scores