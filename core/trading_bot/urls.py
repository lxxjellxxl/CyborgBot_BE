from django.urls import path, include
from rest_framework.routers import DefaultRouter
from .views import BotControlViewSet, HistoryViewSet

router = DefaultRouter()
router.register(r'bot-control', BotControlViewSet, basename='bot-control')
router.register(r'history', HistoryViewSet, basename='history') # Maps to /history/

urlpatterns = [
    path('', include(router.urls)),
]