from django.db import models

from core.managment.models import Class, GovernmentTestAttempt, Grade, NormalTestAttempt, School, Student, Subject


class TestReport(models.Model):
    """Comprehensive test reporting model that aggregates data from both government and normal tests"""

    REPORT_TYPES = (
        ('government', 'Government Test Report'),
        ('normal', 'Normal Test Report'),
        ('comparative', 'Comparative Report'),
        ('summary', 'Summary Report'),
    )

    REPORT_PERIODS = (
        ('daily', 'Daily'),
        ('weekly', 'Weekly'),
        ('monthly', 'Monthly'),
        ('quarterly', 'Quarterly'),
        ('semester', 'Semester'),
        ('annual', 'Annual'),
    )

    # Report metadata
    report_type = models.CharField(max_length=20, choices=REPORT_TYPES)
    period = models.CharField(max_length=20, choices=REPORT_PERIODS)
    start_date = models.DateField()
    end_date = models.DateField()
    generated_at = models.DateTimeField(auto_now_add=True)
    title = models.CharField(max_length=255)
    description = models.TextField(blank=True)

    # Filters for the report
    school = models.ForeignKey(School, on_delete=models.SET_NULL, null=True, blank=True)
    grade = models.ForeignKey(Grade, on_delete=models.SET_NULL, null=True, blank=True)
    class_group = models.ForeignKey(Class, on_delete=models.SET_NULL, null=True, blank=True)
    subject = models.ForeignKey(Subject, on_delete=models.SET_NULL, null=True, blank=True)

    # Aggregated data (could be calculated on the fly or stored)
    total_students = models.IntegerField(default=0)
    total_tests = models.IntegerField(default=0)
    total_attempts = models.IntegerField(default=0)
    average_score = models.DecimalField(max_digits=5, decimal_places=2, default=0)
    highest_score = models.DecimalField(max_digits=5, decimal_places=2, default=0)
    lowest_score = models.DecimalField(max_digits=5, decimal_places=2, default=0)
    pass_rate = models.DecimalField(max_digits=5, decimal_places=2, default=0)  # Percentage

    # Report status
    is_generated = models.BooleanField(default=False)
    last_updated = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = 'Test Report'
        verbose_name_plural = 'Test Reports'
        ordering = ['-generated_at', 'title']
        indexes = [
            models.Index(fields=['report_type', 'period']),
            models.Index(fields=['start_date', 'end_date']),
            models.Index(fields=['school', 'grade']),
        ]

    def __str__(self):
        return f'{self.title} - {self.get_report_type_display()} ({self.start_date} to {self.end_date})'

    def generate_report_data(self):
        """Generate and populate the report data based on filters"""
        from django.db.models import Q

        # Build filters based on report criteria
        filters = Q()

        # Date range filter
        date_filter = Q(governmenttestattempt__attempt_date__range=[self.start_date, self.end_date]
                        ) | Q(normaltestattempt__attempt_date__range=[self.start_date, self.end_date])

        filters &= date_filter

        # Additional filters
        if self.school:
            filters &= Q(school=self.school)
        if self.grade:
            filters &= Q(grade=self.grade)
        if self.class_group:
            filters &= Q(class_group=self.class_group)

        # Get students based on filters
        students = Student.objects.filter(filters).distinct()
        self.total_students = students.count()

        # Calculate statistics for government tests
        gov_attempts = GovernmentTestAttempt.objects.filter(
            attempt_date__range=[self.start_date, self.end_date], student__in=students
        )

        # Calculate statistics for normal tests
        normal_attempts = NormalTestAttempt.objects.filter(
            attempt_date__range=[self.start_date, self.end_date], student__in=students
        )

        # Combine and calculate overall statistics
        all_attempts = list(gov_attempts) + list(normal_attempts)
        self.total_attempts = len(all_attempts)

        if all_attempts:
            scores = [attempt.score for attempt in all_attempts]
            self.average_score = sum(scores) / len(scores)
            self.highest_score = max(scores)
            self.lowest_score = min(scores)
            self.pass_rate = (sum(1 for score in scores if score >= 50) / len(scores)) * 100

        # Count unique tests
        gov_tests = gov_attempts.values('government_test').distinct().count()
        normal_tests = normal_attempts.values('normal_test').distinct().count()
        self.total_tests = gov_tests + normal_tests

        self.is_generated = True
        self.save()

    def get_detailed_breakdown(self):
        """Return detailed breakdown of the report data"""
        from collections import defaultdict

        breakdown = {
            'by_test_type': {
                'government': {
                    'total_attempts': 0,
                    'average_score': 0,
                    'highest_score': 0,
                    'lowest_score': 0,
                },
                'normal': {
                    'total_attempts': 0,
                    'average_score': 0,
                    'highest_score': 0,
                    'lowest_score': 0,
                }
            },
            'by_subject':
                defaultdict(lambda: {
                    'total_attempts': 0,
                    'average_score': 0,
                    'highest_score': 0,
                    'lowest_score': 0,
                }),
            'by_grade':
                defaultdict(lambda: {
                    'total_attempts': 0,
                    'average_score': 0,
                    'highest_score': 0,
                    'lowest_score': 0,
                })
        }

        # This would be populated with actual data calculation logic
        return breakdown

    @property
    def report_period_display(self):
        return f'{self.start_date} to {self.end_date}'

    @classmethod
    def generate_auto_reports(cls, report_type, period):
        """Class method to generate automatic reports based on type and period"""
        from datetime import timedelta

        from django.utils import timezone

        now = timezone.now()

        if period == 'daily':
            start_date = now - timedelta(days=1)
            end_date = now
        elif period == 'weekly':
            start_date = now - timedelta(weeks=1)
            end_date = now
        elif period == 'monthly':
            start_date = now - timedelta(days=30)
            end_date = now
        else:
            start_date = now - timedelta(days=365)
            end_date = now

        report = cls.objects.create(
            report_type=report_type,
            period=period,
            start_date=start_date,
            end_date=end_date,
            title=f'Auto-generated {report_type} Report - {period}',
            description=f'Automatically generated {period} report for {report_type} tests'
        )

        report.generate_report_data()
        return report


class ReportExport(models.Model):
    """Model to track report exports and downloads"""

    EXPORT_FORMATS = (
        ('pdf', 'PDF'),
        ('excel', 'Excel'),
        ('csv', 'CSV'),
        ('json', 'JSON'),
    )

    report = models.ForeignKey(TestReport, on_delete=models.CASCADE, related_name='exports')
    export_format = models.CharField(max_length=10, choices=EXPORT_FORMATS)
    exported_at = models.DateTimeField(auto_now_add=True)
    exported_by = models.ForeignKey('users.User', on_delete=models.SET_NULL, null=True)
    file_path = models.CharField(max_length=500, blank=True)
    download_count = models.IntegerField(default=0)

    class Meta:
        verbose_name = 'Report Export'
        verbose_name_plural = 'Report Exports'
        ordering = ['-exported_at']

    def __str__(self):
        return f'{self.report.title} - {self.export_format}'
