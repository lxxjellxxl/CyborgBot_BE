import os
import django
from django.core.asgi import get_asgi_application

# 1. Set the default Django settings module FIRST
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'core.project.settings')

# 2. Initialize Django (Critical: Load settings & apps)
django.setup()

# ------------------------------------------------------------------
# 3. NOW it is safe to import Channels, Consumers, and Models
# ------------------------------------------------------------------
from channels.routing import ProtocolTypeRouter, URLRouter
from channels.auth import AuthMiddlewareStack
from django.urls import path
from core.trading_bot.consumers import BotConsumer  # Import this AFTER django.setup()

# 4. Define the ASGI Application
application = ProtocolTypeRouter({
    # A. Handle standard HTTP requests (REST API)
    "http": get_asgi_application(),

    # B. Handle WebSocket requests
    "websocket": AuthMiddlewareStack(
        URLRouter([
            # This matches 'ws://localhost:8000/ws/bot/'
            path("ws/bot/", BotConsumer.as_asgi()),
        ])
    ),
})