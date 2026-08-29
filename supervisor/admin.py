from django.contrib import admin
from .models.supervisor_class import SupervisorClass
from .models.supervisor_profile import SupervisorProfile


@admin.register(SupervisorProfile)
class SupervisorProfileAdmin(admin.ModelAdmin):
    list_display = (
        "user",
        "grade",
        "assigned_classes_count",
    )

    list_filter = (
        "grade",
    )

    search_fields = (
        "user__first_name",
        "user__last_name",
        "user__username",
    )

    autocomplete_fields = (
        "user",
        "grade",
    )

    def assigned_classes_count(self, obj):
        return obj.class_assignments.count()

    assigned_classes_count.short_description = "تعداد کلاس‌ها"


@admin.register(SupervisorClass)
class SupervisorClassAdmin(admin.ModelAdmin):
    list_display = (
        "supervisor",
        "school_class",
    )

    list_filter = (
        "supervisor__grade",
        "supervisor",
    )

    search_fields = (
        "supervisor__user__first_name",
        "supervisor__user__last_name",
        "school_class__name",
    )

    autocomplete_fields = (
        "supervisor",
        "school_class",
    )

    def get_queryset(self, request):
        return (
            super()
            .get_queryset(request)
            .select_related(
                "supervisor__user",
                "supervisor__grade",
                "school_class",
            )
        )