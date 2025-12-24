import threading
from rest_framework import viewsets, status, generics
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated
from rest_framework.pagination import PageNumberPagination

from .models import TradingAccount, TradePosition
from .serializers import (
    TradingAccountSerializer, 
    TradingAccountDetailSerializer, 
    TradePositionSerializer
)
# Import the checker function
from .services import run_bot_engine, is_bot_running 

# --- 1. PAGINATION CONFIGURATION ---
class StandardResultsSetPagination(PageNumberPagination):
    page_size = 50
    page_size_query_param = 'page_size'
    max_page_size = 100

# --- 2. BOT CONTROL VIEWSET ---
class BotControlViewSet(viewsets.ModelViewSet):
    """
    Main ViewSet for Dashboard & Bot Management.
    Handles retrieving account stats and Start/Stop actions.
    """
    queryset = TradingAccount.objects.all()
    permission_classes = [IsAuthenticated]

    def get_serializer_class(self):
        # Use detailed serializer (with stats/history) only for single account view
        if self.action == 'retrieve':
            return TradingAccountDetailSerializer
        return TradingAccountSerializer

    def retrieve(self, request, *args, **kwargs):
        """
        Custom Retrieve: Checks if bot is ACTUALLY running in memory
        and updates the DB flag before returning data.
        """
        instance = self.get_object()
        
        # Check if the driver exists in memory (Real Truth)
        actual_status = is_bot_running(instance.id)
        
        # If DB says active but memory says inactive (e.g. server restart), fix DB
        if instance.is_active != actual_status:
            instance.is_active = actual_status
            instance.save(update_fields=['is_active'])
        
        serializer = self.get_serializer(instance)
        return Response(serializer.data)

    @action(detail=True, methods=['post'])
    def start_bot(self, request, pk=None):
        account = self.get_object()
        
        # Double check to prevent duplicate threads
        if is_bot_running(account.id):
            return Response({'status': 'Bot is already running', 'is_active': True})

        # Set Flag to True
        account.is_active = True
        account.save()

        # Launch Engine in Background Thread
        thread = threading.Thread(target=run_bot_engine, args=(account.id,))
        thread.daemon = True
        thread.start()

        return Response({
            'status': 'Bot started', 
            'account_id': account.id,
            'is_active': True
        })

    @action(detail=True, methods=['post'])
    def stop_bot(self, request, pk=None):
        account = self.get_object()
        # Setting this to False triggers the loop inside run_bot_engine to break
        account.is_active = False
        account.save()
        
        return Response({'status': 'Stop signal sent', 'is_active': False})


# --- 3. HISTORY VIEWSET (PAGINATED) ---
class HistoryViewSet(viewsets.ReadOnlyModelViewSet):
    """
    Returns paginated CLOSED trade history.
    Filterable by account ID: /api/trading-bot/history/?account=1
    """
    serializer_class = TradePositionSerializer
    permission_classes = [IsAuthenticated]
    pagination_class = StandardResultsSetPagination

    def get_queryset(self):
        # Base: Only Closed Trades, Newest First
        queryset = TradePosition.objects.filter(is_closed=True).order_by('-close_time')
        
        # Filter by Account (Required for correct dashboard data)
        account_id = self.request.query_params.get('account')
        if account_id:
            queryset = queryset.filter(account_id=account_id)
            
        return queryset