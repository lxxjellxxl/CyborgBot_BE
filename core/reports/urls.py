from django.urls import include, path
from rest_framework.routers import DefaultRouter

from . import views

router = DefaultRouter()
router.register(r'test-reports', views.TestReportViewSet, basename='testreport')
router.register(r'report-exports', views.ReportExportViewSet, basename='reportexport')

urlpatterns = [
    path('', include(router.urls)),

    # Additional endpoints
    path(
        'reports/auto-generate/',
        views.TestReportViewSet.as_view({'post': 'generate_new'}),
        name='auto-generate-report'
    ),
]
