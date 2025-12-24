from datetime import timedelta

from django.utils import timezone
from rest_framework import status
from rest_framework.decorators import action
from rest_framework.response import Response

from core.core.views import BaseModelViewSet

from .models import ReportExport, TestReport
from .serializers import (
    ReportExportSerializer,
    TestReportExportSerializer,
    TestReportGenerateSerializer,
    TestReportSerializer,
)


class TestReportViewSet(BaseModelViewSet):
    queryset = TestReport.objects.all().order_by('-generated_at')
    serializer_class = TestReportSerializer

    def get_queryset(self):
        queryset = super().get_queryset()

        # Filter by report type
        report_type = self.request.query_params.get('report_type')
        if report_type:
            queryset = queryset.filter(report_type=report_type)

        # Filter by period
        period = self.request.query_params.get('period')
        if period:
            queryset = queryset.filter(period=period)

        # Filter by date range
        start_date = self.request.query_params.get('start_date')
        end_date = self.request.query_params.get('end_date')
        if start_date and end_date:
            queryset = queryset.filter(start_date__gte=start_date, end_date__lte=end_date)

        # Filter by school
        school_id = self.request.query_params.get('school')
        if school_id:
            queryset = queryset.filter(school_id=school_id)

        return queryset

    @action(detail=True, methods=['post'])
    def generate(self, request, pk=None):
        """Generate/regenerate report data"""
        report = self.get_object()
        report.generate_report_data()

        serializer = self.get_serializer(report)
        return Response(serializer.data)

    @action(detail=False, methods=['post'])
    def generate_new(self, request):
        """Generate a new report with parameters"""
        serializer = TestReportGenerateSerializer(data=request.data)
        if serializer.is_valid():
            data = serializer.validated_data

            # Set default dates if not provided
            if not data.get('start_date') or not data.get('end_date'):
                end_date = timezone.now().date()
                if data['period'] == 'daily':
                    start_date = end_date - timedelta(days=1)
                elif data['period'] == 'weekly':
                    start_date = end_date - timedelta(weeks=1)
                elif data['period'] == 'monthly':
                    start_date = end_date - timedelta(days=30)
                else:
                    start_date = end_date - timedelta(days=365)

                data['start_date'] = start_date
                data['end_date'] = end_date

            # Create the report
            report = TestReport.objects.create(**data)
            report.generate_report_data()

            return Response(TestReportSerializer(report).data, status=status.HTTP_201_CREATED)

        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

    @action(detail=True, methods=['get'])
    def breakdown(self, request, pk=None):
        """Get detailed breakdown of report data"""
        report = self.get_object()
        breakdown_data = report.get_detailed_breakdown()
        return Response(breakdown_data)

    @action(detail=True, methods=['post'])
    def export(self, request, pk=None):
        """Export report to different formats"""
        report = self.get_object()
        serializer = TestReportExportSerializer(data=request.data)

        if serializer.is_valid():
            export_format = serializer.validated_data['export_format']

            # Create export record (in real implementation, this would generate the file)
            export = ReportExport.objects.create(
                report=report,
                export_format=export_format,
                exported_by=request.user,
                file_path=f'/exports/report_{report.id}_{export_format}.{export_format}'
            )

            # Increment download count
            export.download_count += 1
            export.save()

            return Response({
                'message': f'Report exported as {export_format}',
                'export_id': export.id,
                'download_url': export.file_path
            })

        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)


class ReportExportViewSet(BaseModelViewSet):
    queryset = ReportExport.objects.all().order_by('-exported_at')
    serializer_class = ReportExportSerializer

    def get_queryset(self):
        queryset = super().get_queryset()

        # Filter by report
        report_id = self.request.query_params.get('report')
        if report_id:
            queryset = queryset.filter(report_id=report_id)

        # Filter by format
        export_format = self.request.query_params.get('format')
        if export_format:
            queryset = queryset.filter(export_format=export_format)

        return queryset

    @action(detail=True, methods=['post'])
    def download(self, request, pk=None):
        """Increment download count and return download URL"""
        export = self.get_object()
        export.download_count += 1
        export.save()

        return Response({'download_url': export.file_path, 'download_count': export.download_count})
