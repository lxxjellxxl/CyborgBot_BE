import re

import pandas as pd


class StudentExcelImporter:

    COLUMN_MAPPING = {
        'رقم الهوية': 'student_id',
        'الاسم كاملاً': 'full_name',
        'المدرسة': 'school_name',
        'الصف / المستوى': 'grade_name',
        'الفصل': 'class_name',
        'رقم الجوال': 'parent_phone'
    }

    @classmethod
    def clean_phone_number(cls, phone):
        if pd.isna(phone) or phone == '':
            return ''
        phone_str = str(phone).strip()
        phone_str = re.sub(r'[^\d+]', '', phone_str)
        return phone_str

    @classmethod
    def clean_class_name(cls, class_name):
        if pd.isna(class_name) or class_name == '':
            return '1'
        class_str = str(class_name).strip()
        return class_str

    @classmethod
    def process_row(cls, row_data, row_number, academic_year, user):
        from ...managment.models import Class, Grade, School, Student

        try:
            # Extract and clean data
            student_id = str(row_data['student_id']).strip()
            full_name = str(row_data['full_name']).strip()
            school_name = str(row_data['school_name']).strip()
            grade_name = str(row_data['grade_name']).strip()
            class_name = cls.clean_class_name(row_data['class_name'])
            parent_phone = cls.clean_phone_number(row_data.get('parent_phone', ''))

            # 1. Validation: Required Fields
            if not student_id or not full_name or not school_name or not grade_name:
                return False, f'Row {row_number}: ❌ Missing required fields', None

            # 2. Validation: Check for Duplicates (The Update)
            if Student.objects.filter(student_id=student_id).exists():
                # We return False (Error) and specify the field
                return False, f"Row {row_number}: ❌ Duplicate Data - Field 'student_id' ({student_id}) already exists.", None

            # 3. Get or create School
            school, _ = School.objects.get_or_create(
                name=school_name, defaults={
                    'is_active': True,
                    'created_by': user,
                    'last_modified_by': user
                }
            )

            # 4. Get or create Grade
            grade, _ = Grade.objects.get_or_create(
                school=school,
                name=grade_name,
                academic_year=academic_year,
                defaults={
                    'is_active': True,
                    'created_by': user,
                    'last_modified_by': user
                }
            )

            # 5. Get or create Class
            class_obj, _ = Class.objects.get_or_create(
                grade=grade,
                name=class_name,
                academic_year=academic_year,
                defaults={
                    'is_active': True,
                    'created_by': user,
                    'last_modified_by': user
                }
            )

            # 6. Create Student (Since we checked for duplicates, we use create() now)
            student = Student.objects.create(
                student_id=student_id,
                school=school,
                grade=grade,
                class_group=class_obj,
                full_name=full_name,
                parent_phone=parent_phone,
                is_active=True,
                created_by=user,
                last_modified_by=user
            )

            return True, f'Row {row_number}: ✅ {full_name}', student

        except Exception as e:
            return False, f'Row {row_number}: ❌ System Error - {str(e)}', None

    @classmethod
    def import_from_excel(cls, excel_file, academic_year, user):
        try:
            df = pd.read_excel(excel_file)
            df_renamed = df.rename(columns=cls.COLUMN_MAPPING)

            required_columns = ['student_id', 'full_name', 'school_name', 'grade_name']
            missing_columns = [col for col in required_columns if col not in df_renamed.columns]

            if missing_columns:
                return 0, 0, [{
                    'row': 0,
                    'success': False,
                    'message': f'❌ Invalid File: Missing columns: {", ".join(missing_columns)}'
                }]

            # Check for duplicates INSIDE the Excel file itself before processing
            if df_renamed['student_id'].duplicated().any():
                return 0, 0, [{
                    'row': 0,
                    'success': False,
                    'message': '❌ Invalid File: Duplicate student_id found in the Excel file.'
                }]

            success_count = 0
            error_count = 0
            results = []

            for index, row in df_renamed.iterrows():
                row_number = index + 2
                success, message, _ = cls.process_row(row.to_dict(), row_number, academic_year, user)

                results.append({
                    'row': row_number,
                    'success': success,
                    'message': message,
                })

                if success:
                    success_count += 1
                else:
                    error_count += 1

            return success_count, error_count, results

        except Exception as e:
            return 0, 0, [{'row': 0, 'success': False, 'message': f'❌ Critical Error: {str(e)}'}]
