from django.contrib import admin

from .models import ReportExport, TestReport


@admin.register(TestReport)
class TestReportAdmin(admin.ModelAdmin):
    list_display = [
        'title', 'report_type', 'period', 'start_date', 'end_date', 'total_students', 'total_tests', 'average_score',
        'is_generated', 'generated_at'
    ]
    list_filter = ['report_type', 'period', 'is_generated', 'generated_at']
    search_fields = ['title', 'description']
    readonly_fields = [
        'generated_at', 'last_updated', 'total_students', 'total_tests', 'total_attempts', 'average_score',
        'highest_score', 'lowest_score', 'pass_rate', 'is_generated'
    ]
    fieldsets = (('Report Information', {
        'fields': ('title', 'description', 'report_type', 'period')
    }), ('Date Range', {
        'fields': ('start_date', 'end_date')
    }), ('Filters', {
        'fields': ('school', 'grade', 'class_group', 'subject'),
        'classes': ('collapse',)
    }), (
        'Statistics', {
            'fields': (
                'total_students', 'total_tests', 'total_attempts', 'average_score', 'highest_score', 'lowest_score',
                'pass_rate'
            ),
            'classes': ('collapse',)
        }
    ), ('Status', {
        'fields': ('is_generated', 'generated_at', 'last_updated')
    }))

    actions = ['generate_selected_reports']

    def generate_selected_reports(self, request, queryset):
        for report in queryset:
            report.generate_report_data()
        self.message_user(request, f'Generated {queryset.count()} reports successfully.')

    generate_selected_reports.short_description = 'Generate selected reports'


@admin.register(ReportExport)
class ReportExportAdmin(admin.ModelAdmin):
    list_display = ['report', 'export_format', 'exported_at', 'exported_by', 'download_count']
    list_filter = ['export_format', 'exported_at']
    readonly_fields = ['exported_at', 'download_count']
    search_fields = ['report__title', 'exported_by__username']

    def has_add_permission(self, request):
        return False  # Exports should only be created through the system
