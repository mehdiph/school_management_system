"""
The admin's student pickers (audience «دانش‌آموزان» / «دانش‌آموزان مستثنا»
and an access row's student): select2 autocomplete widgets that search on the
server, never one checkbox per student.

Results are students with a current enrolment, in the admin's branches for a
non-superuser, searchable by name, student code and national code, and labelled
with name, student code and class. The forms check the posted ids again
(``audience.targets_problems``, ``OnlineEventAccessForm.clean_student``), so a
forged id is refused whatever the widget showed.
"""

from django.contrib.admin.views.autocomplete import AutocompleteJsonView
from django.contrib.admin.widgets import AutocompleteSelect, AutocompleteSelectMultiple
from django.core.exceptions import PermissionDenied
from django.db.models import CharField, OuterRef, Subquery, Value
from django.db.models.functions import Concat

from core.services import access
from student.models.student_enrollment import StudentEnrollment
from student.models.student_profile import StudentProfile

URL_NAME = "online_classes_student_autocomplete"

#: The (model, field) pairs that may ask for students.
SOURCES = {
    ("onlineevent", "students"),
    ("onlineevent", "excluded_students"),
    ("announcement", "students"),
    ("announcement", "excluded_students"),
    ("onlineeventaccess", "student"),
}


def current_enrollments(request):
    """Current enrolments the admin may pick from: all for a superuser, else their branches."""

    enrollments = StudentEnrollment.objects.current()
    if request is None or request.user.is_superuser:
        return enrollments
    return enrollments.filter(school_class__branch__in=access.get_accessible_branch_ids(request.user, request=request))


def pickable_students(request):
    return StudentProfile.objects.filter(pk__in=current_enrollments(request).values("student_id"))


def _class_label():
    """The student's current class as one string, for the picker's label (a subquery, not a query per row)."""

    return Subquery(
        StudentEnrollment.objects.current()
        .filter(student=OuterRef("pk"))
        .annotate(label=Concat(
            "school_class__grade__name", Value(" "), "school_class__section", Value(" · "), "school_class__branch__name",
            output_field=CharField(),
        ))
        .values("label")[:1]
    )


class StudentAutocompleteView(AutocompleteJsonView):
    def process_request(self, request):
        if request.GET.get("app_label") != "online_classes" or (
            request.GET.get("model_name"), request.GET.get("field_name")
        ) not in SOURCES:
            raise PermissionDenied
        return super().process_request(request)

    def get_queryset(self):
        students = (
            pickable_students(self.request)
            .select_related("user")
            .annotate(class_label=_class_label())
            .order_by("user__last_name", "user__first_name", "pk")
        )
        students, distinct = self.model_admin.get_search_results(self.request, students, self.term)
        return students.distinct() if distinct else students

    def serialize_result(self, obj, to_field_name):
        parts = [obj.user.get_full_name() or obj.user.get_username(), obj.student_code, obj.class_label]
        return {"id": str(getattr(obj, to_field_name)), "text": " · ".join(part for part in parts if part)}


class _StudentPickerMixin:
    url_name = "%s:" + URL_NAME


class StudentPicker(_StudentPickerMixin, AutocompleteSelect):
    pass


class StudentsPicker(_StudentPickerMixin, AutocompleteSelectMultiple):
    pass
