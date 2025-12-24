from django import forms


class ExcelImportForm(forms.Form):
    excel_file = forms.FileField(label='Excel File', help_text='Upload Excel file (.xls, .xlsx) with student data')
    academic_year = forms.CharField(
        max_length=20, initial='1445-1446', help_text='Academic year for the imported data'
    )
