from django.conf import settings
from django.conf.urls.static import static
from django.contrib import admin
from django.urls import include, path
from drf_yasg import openapi
from drf_yasg.views import get_schema_view
from rest_framework import permissions

# Documentation Configuration
schema_view = get_schema_view(
    openapi.Info(
        title='Nebras Al-Fadeelah API',
        default_version='v1',
        description='API for LMS Backend (Django + Quasar)',
        terms_of_service='https://www.google.com/policies/terms/',
        contact=openapi.Contact(email='admin@nebrasalfadeelah.com'),
        license=openapi.License(name='BSD License'),
    ),
    public=True,
    permission_classes=[permissions.AllowAny],
)

urlpatterns = [
    path('admin/', admin.site.urls),

    # --- DOCUMENTATION (Always Available) ---
    path('swagger<format>/', schema_view.without_ui(cache_timeout=0), name='schema-json'),
    path('swagger/', schema_view.with_ui('swagger', cache_timeout=0), name='schema-swagger-ui'),
    path('redoc/', schema_view.with_ui('redoc', cache_timeout=0), name='schema-redoc'),
    path('explorer/', include('explorer.urls')),

    # --- AUTHENTICATION ---
    path('api/auth/system/', include('core.users.urls')),
    path('api/auth/', include('djoser.urls')),
    path('api/auth/', include('djoser.urls.authtoken')),
    path('api/trading-bot/', include('core.trading_bot.urls')),
]

# --- STATIC FILES ---
urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
urlpatterns += static(settings.STATIC_URL, document_root=settings.STATIC_ROOT)

# --- DEBUG ONLY ---
if settings.DEBUG:
    import debug_toolbar
    urlpatterns += [
        path('__debug__/', include(debug_toolbar.urls)),
    ]