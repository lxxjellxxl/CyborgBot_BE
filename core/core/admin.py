from django.contrib import admin


class BaseModelAdmin(admin.ModelAdmin):
    def save_model(self, request, obj, form, change):
        if not change:  # If it's a new object
            obj.created_by = request.user
        obj.last_modified_by = request.user
        obj.save()
        super().save_model(request, obj, form, change)

    def save_formset(self, request, form, formset, change):
        instances = formset.save(commit=False)
        for instance in instances:
            if not instance.pk:  # If it's a new instance
                instance.created_by = request.user
            instance.last_modified_by = request.user
            instance.save()
        formset.save_m2m()
        super().save_formset(request, form, formset, change)
