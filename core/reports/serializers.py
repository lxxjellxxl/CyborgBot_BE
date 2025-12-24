from rest_framework import serializers

from core.core.serializers import BaseModelSerializer
from core.managment.models import Class, Grade, School, Subject
from core.managment.serializers import ClassSerializer, GradeSerializer, SchoolSerializer, SubjectSerializer

from .models import ReportExport, TestReport


class ReportExportSerializer(BaseModelSerializer):
    exported_by_name = serializers.CharField(source='exported_by.get_full_name', read_only=True)

    class Meta:
        model = ReportExport
        fields = [
            'id', 'export_format', 'exported_at', 'exported_by', 'exported_by_name', 'file_path', 'download_count'
        ]
        read_only_fields = ['exported_at', 'download_count']


class TestReportSerializer(BaseModelSerializer):
    school_details = SchoolSerializer(source='school', read_only=True)
    grade_details = GradeSerializer(source='grade', read_only=True)
    class_details = ClassSerializer(source='class_group', read_only=True)
    subject_details = SubjectSerializer(source='subject', read_only=True)
    report_period_display = serializers.CharField(read_only=True)
    exports = ReportExportSerializer(many=True, read_only=True)

    class Meta:
        model = TestReport
        fields = [
            'id', 'report_type', 'period', 'start_date', 'end_date', 'generated_at', 'title', 'description', 'school',
            'grade', 'class_group', 'subject', 'total_students', 'total_tests', 'total_attempts', 'average_score',
            'highest_score', 'lowest_score', 'pass_rate', 'is_generated', 'last_updated', 'school_details',
            'grade_details', 'class_details', 'subject_details', 'report_period_display', 'exports'
        ]
        read_only_fields = [
            'generated_at', 'last_updated', 'total_students', 'total_tests', 'total_attempts', 'average_score',
            'highest_score', 'lowest_score', 'pass_rate', 'is_generated'
        ]


class TestReportGenerateSerializer(serializers.Serializer):
    """Serializer for generating reports with parameters"""
    report_type = serializers.ChoiceField(choices=TestReport.REPORT_TYPES)
    period = serializers.ChoiceField(choices=TestReport.REPORT_PERIODS)
    start_date = serializers.DateField(required=False)
    end_date = serializers.DateField(required=False)
    title = serializers.CharField(max_length=255, required=False)
    description = serializers.CharField(required=False)
    school = serializers.PrimaryKeyRelatedField(queryset=School.objects.all(), required=False, allow_null=True)
    grade = serializers.PrimaryKeyRelatedField(queryset=Grade.objects.all(), required=False, allow_null=True)
    class_group = serializers.PrimaryKeyRelatedField(queryset=Class.objects.all(), required=False, allow_null=True)
    subject = serializers.PrimaryKeyRelatedField(queryset=Subject.objects.all(), required=False, allow_null=True)


class TestReportExportSerializer(serializers.Serializer):
    """Serializer for exporting reports"""
    export_format = serializers.ChoiceField(choices=ReportExport.EXPORT_FORMATS)
    report_id = serializers.IntegerField()
