from django import forms
from django.contrib import admin

from .models import SupervisorClass, SupervisorProfile


class SupervisorProfileAdminForm(forms.ModelForm):
    class Meta:
        model = SupervisorProfile
        fields = "__all__"


class SupervisorClassAdminForm(forms.ModelForm):
    class Meta:
        model = SupervisorClass
        fields = "__all__"

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        supervisor = self.initial.get("supervisor")

        # The admin's "add" view populates ``initial`` straight from the
        # request's GET params (see ModelAdmin.get_changeform_initial_data),
        # so a ForeignKey value like this one arrives as a raw pk string,
        # not a SupervisorProfile instance -- resolve it before using it.
        if supervisor and not isinstance(supervisor, SupervisorProfile):
            supervisor = SupervisorProfile.objects.filter(pk=supervisor).first()

        if not supervisor and self.instance.pk and self.instance.supervisor_id:
            supervisor = self.instance.supervisor

        if supervisor:
            self.fields["school_class"].queryset = (
                self.fields["school_class"]
                .queryset
                .filter(
                    branch=supervisor.branch,
                    grade=supervisor.grade,
                )
            )


@admin.register(SupervisorProfile)
class SupervisorProfileAdmin(admin.ModelAdmin):

    form = SupervisorProfileAdminForm

    list_display = (
        "user",
        "branch",
        "grade",
        "assigned_classes_count",
    )

    list_filter = (
        "branch",
        "grade",
    )

    search_fields = (
        "user__first_name",
        "user__last_name",
        "user__username",
    )

    autocomplete_fields = (
        "user",
        "branch",
        "grade",
    )

    def assigned_classes_count(self, obj):
        return obj.class_assignments.count()

    assigned_classes_count.short_description = "تعداد کلاس‌ها"


@admin.register(SupervisorClass)
class SupervisorClassAdmin(admin.ModelAdmin):

    form = SupervisorClassAdminForm

    list_display = (
        "supervisor",
        "school_class",
        "branch",
        "grade",
        "academic_year",
    )

    list_filter = (
        "supervisor__branch",
        "supervisor__grade",
        "school_class__year",
    )

    search_fields = (
        "supervisor__user__first_name",
        "supervisor__user__last_name",
        "school_class__section",
    )

    autocomplete_fields = (
        "supervisor",
        "school_class",
    )

    list_select_related = (
        "supervisor",
        "supervisor__user",
        "supervisor__branch",
        "supervisor__grade",
        "school_class",
        "school_class__branch",
        "school_class__grade",
        "school_class__year",
    )

    def branch(self, obj):
        return obj.school_class.branch

    branch.short_description = "شعبه"

    def grade(self, obj):
        return obj.school_class.grade

    grade.short_description = "پایه"

    def academic_year(self, obj):
        return obj.school_class.year

    academic_year.short_description = "سال تحصیلی"