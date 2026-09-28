import json

from django import forms
from django.contrib import admin
from django.contrib.admin.utils import quote, unquote
from django.core.exceptions import PermissionDenied
from django.http import Http404, HttpResponseNotAllowed, JsonResponse
from django.shortcuts import render
from django.urls import path, reverse
from django.utils.html import format_html
from django_jalali.admin.filters import JDateFieldListFilter
import django_jalali.admin as jadmin

from core.admin import BranchScopedAdminMixin
from staff.models import TeacherAssignment

from .colors import readable_text_color, safe_hex
from .models import AcademicYear, Grade, Subject, SchoolClass, ClassSubject, Branch
from .widgets import ColorPickerWidget


@admin.register(AcademicYear)
class AcademicYearAdmin(admin.ModelAdmin):
    list_display = ('title', 'start_date', 'end_date', 'is_current', 'is_active')
    list_filter = ('is_current', 'is_active')
    search_fields = ('title',)
    list_editable = ('is_current', 'is_active')
    ordering = ('-start_date',)
    
    fieldsets = (
        ('اطلاعات اصلی', {
            'fields': ('title', ('start_date', 'end_date'))
        }),
        ('وضعیت', {
            'fields': ('is_current', 'is_active')
        }),
    )

@admin.register(Branch)
class BranchAdmin(BranchScopedAdminMixin, admin.ModelAdmin):
    # A Branch *is* the branch, so the scoping lookup is the row itself.
    branch_lookup = "id"

    list_display = ['name', 'address', 'phone_number', 'is_active']
    search_fields = ['name', 'code']

@admin.register(Grade)
class GradeAdmin(admin.ModelAdmin):
    list_display = ('name', 'level', 'is_active', 'created_at')
    list_filter = ('is_active',)
    search_fields = ('name',)
    list_editable = ('is_active',)
    ordering = ('level',)
    
    fieldsets = (
        ('اطلاعات اصلی', {
            'fields': ('name', 'level')
        }),
        ('وضعیت', {
            'fields': ('is_active',)
        }),
    )


class SubjectAdminForm(forms.ModelForm):
    class Meta:
        model = Subject
        fields = '__all__'
        widgets = {'color': ColorPickerWidget()}


@admin.register(Subject)
class SubjectAdmin(admin.ModelAdmin):
    form = SubjectAdminForm
    list_display = ('name', 'color_swatch', 'slug', 'is_active', 'created_at')
    list_filter = ('is_active',)
    search_fields = ('name', 'slug')
    prepopulated_fields = {'slug': ('name',)}
    list_editable = ('is_active',)
    ordering = ('name',)

    @admin.display(description='رنگ', ordering='color')
    def color_swatch(self, obj):
        color = safe_hex(obj.color)
        return format_html(
            '<span style="display:inline-block;padding:2px 10px;border-radius:6px;'
            'background:{};color:{};font-family:monospace" dir="ltr">{}</span>',
            color, readable_text_color(color), color,
        )


@admin.register(SchoolClass)
class SchoolClassAdmin(BranchScopedAdminMixin, admin.ModelAdmin):
    branch_lookup = "branch"

    related_branch_lookups = {
        "branch": "",
    }

    search_fields = ('section', 'grade__name', 'year__title')

    list_display = ('get_class_name', 'year', 'grade', 'section', 'branch', 'created_at', 'timetable_link')
    list_filter = ('year', 'grade', 'is_active', 'branch')
    search_fields = ('section', 'grade__name', 'year__title')
    ordering = ('-created_at',)
    
    fieldsets = (
        ('اطلاعات اصلی', {
            'fields': ('year', 'grade', 'branch', 'section')
        }),
        ('وضعیت', {
            'fields': ('is_active',)
        }),
    )
    
    def get_class_name(self, obj):
        return f"{obj.grade.name} - {obj.section}"
    get_class_name.short_description = 'کلاس'

    # ------------------------------------------------------------------
    # «برنامه هفتگی» -- the timetable grid (scheduling/timetable.py)
    # ------------------------------------------------------------------

    #: Everything the three old screens (ClassSchedule, ClassSubject)
    #: needed; the grid writes both models.
    TIMETABLE_EDIT_PERMISSIONS = (
        'scheduling.add_classschedule',
        'scheduling.change_classschedule',
        'scheduling.delete_classschedule',
        'school.add_classsubject',
        'school.change_classsubject',
    )

    def get_urls(self):
        return [
            path(
                '<path:object_id>/timetable/',
                self.admin_site.admin_view(self.timetable_view),
                name='school_schoolclass_timetable',
            ),
            path(
                '<path:object_id>/timetable/teacher-busy/',
                self.admin_site.admin_view(self.timetable_busy_view),
                name='school_schoolclass_timetable_busy',
            ),
        ] + super().get_urls()

    def can_view_timetable(self, request):
        return request.user.has_perm('scheduling.view_classschedule') or self.can_edit_timetable(request)

    def can_edit_timetable(self, request):
        return request.user.has_perms(self.TIMETABLE_EDIT_PERMISSIONS)

    def _timetable_class(self, request, object_id):
        if not self.can_view_timetable(request):
            raise PermissionDenied
        # get_object() goes through get_queryset(), i.e. branch scoping.
        school_class = self.get_object(request, unquote(object_id))
        if school_class is None:
            raise Http404
        return school_class

    @admin.display(description='برنامه هفتگی')
    def timetable_link(self, obj):
        return format_html(
            '<a href="{}">برنامه هفتگی</a>',
            reverse('admin:school_schoolclass_timetable', args=[quote(obj.pk)]),
        )

    def get_list_display(self, request):
        list_display = super().get_list_display(request)
        if not self.can_view_timetable(request):
            list_display = [f for f in list_display if f != 'timetable_link']
        return list_display

    def change_view(self, request, object_id, form_url='', extra_context=None):
        extra_context = {**(extra_context or {}), 'can_view_timetable': self.can_view_timetable(request)}
        return super().change_view(request, object_id, form_url, extra_context=extra_context)

    def timetable_view(self, request, object_id):
        # Imported here: scheduling's modules import school's models.
        from scheduling import timetable

        school_class = self._timetable_class(request, object_id)
        can_edit = self.can_edit_timetable(request)

        if request.method == 'POST':
            if not can_edit:
                raise PermissionDenied
            try:
                payload = json.loads(request.body or b'{}')
                entries = payload['entries']
            except (ValueError, KeyError, TypeError):
                return JsonResponse({'ok': False, 'errors': [], 'general': ['داده‌ی فرستاده‌شده معتبر نیست.']}, status=400)

            result = timetable.save_grid(
                school_class,
                entries,
                can_delete_class_subjects=request.user.has_perm('school.delete_classsubject'),
            )
            if not result.ok:
                return JsonResponse({
                    'ok': False,
                    'errors': [e for e in result.errors if e['day'] is not None],
                    'general': [e['message'] for e in result.errors if e['day'] is None],
                }, status=400)
            return JsonResponse({
                'ok': True,
                'grid': timetable.load_grid(school_class),
                'counts': {'created': result.created, 'updated': result.updated, 'deleted': result.deleted},
            })

        if request.method != 'GET':
            return HttpResponseNotAllowed(['GET', 'POST'])

        grid = timetable.load_grid(school_class)
        context = {
            **self.admin_site.each_context(request),
            'opts': self.opts,
            'original': school_class,
            'title': f'برنامه هفتگی کلاس {grid["class_label"]}',
            'subtitle': str(school_class),
            'grid': {
                **grid,
                'can_edit': can_edit,
                'can_add_subject': request.user.has_perm('school.add_subject'),
                'urls': {
                    'save': request.path,
                    'busy': reverse('admin:school_schoolclass_timetable_busy', args=[quote(school_class.pk)]),
                    'add_subject': reverse('admin:school_subject_add'),
                },
            },
        }
        return render(request, 'admin/school/schoolclass/timetable.html', context)

    def timetable_busy_view(self, request, object_id):
        from scheduling import timetable

        if request.method != 'GET':
            return HttpResponseNotAllowed(['GET'])

        school_class = self._timetable_class(request, object_id)
        try:
            assignment_id = int(request.GET.get('teacher', ''))
        except ValueError:
            raise Http404
        # Only assignments the grid itself offers for this class.
        assignment = next(
            (a for a in timetable.teacher_choices(school_class, [assignment_id]) if a.pk == assignment_id),
            None,
        )
        if assignment is None:
            raise Http404
        return JsonResponse({'busy': timetable.teacher_busy(school_class, assignment)})


@admin.register(ClassSubject)
class ClassSubjectAdmin(BranchScopedAdminMixin, admin.ModelAdmin):
    branch_lookup = "school_class__branch"

    related_branch_lookups = {
        "school_class": "branch",
        "teacher_assignment": "branch",
    }

    list_display = ('get_class_subject_name', 'school_class', 'subject', 'get_teacher', 'start_date', 'end_date', 'is_active')
    list_filter = ('subject', 'is_active', 'school_class__grade', 'school_class__branch')
    search_fields = ('school_class__section', 'subject__name')

    list_select_related = (
        'school_class',
        'school_class__grade',
        'school_class__branch',
        'subject',
        'teacher_assignment',
        'teacher_assignment__teacher',
        'teacher_assignment__teacher__staff',
        'teacher_assignment__teacher__staff__user',
    )
    list_editable = ('is_active',)
    ordering = ('-created_at',)
    
    fieldsets = (
        ('اطلاعات اصلی', {
            'fields': ('school_class', 'subject', 'teacher_assignment')
        }),
        ('دوره تدریس', {
            'fields': (('start_date', 'end_date'),)
        }),
        ('وضعیت', {
            'fields': ('is_active',)
        }),
    )
    def get_form(self, request, obj=None, **kwargs):
        # formfield_for_foreignkey() gets no obj, but the teacher
        # dropdown has to know which class is being edited -- stash it
        # on the request (per-request, never global) for the callback
        # below to pick up.
        request._class_subject_obj = obj

        return super().get_form(request, obj=obj, **kwargs)

    def formfield_for_foreignkey(self, db_field, request, **kwargs):
        """
        Narrows the teacher-assignment dropdown so a mismatching
        assignment can't be picked in the first place (``ClassSubject.
        clean()`` is still what guarantees it -- this only keeps the
        admin from offering choices that would be rejected).

        On the change form the class is known, so the list is exactly
        the assignments of that class's branch *and* academic year. On
        the add form there is no class yet, so it falls back to the
        current year within the branches the user may see.
        """

        if db_field.name == "teacher_assignment":
            queryset = kwargs.get("queryset")

            if queryset is None:
                queryset = TeacherAssignment.objects.all()

            obj = getattr(request, "_class_subject_obj", None)

            if obj is not None and obj.school_class_id:
                queryset = queryset.filter(
                    branch_id=obj.school_class.branch_id,
                    academic_year_id=obj.school_class.year_id,
                )
            else:
                queryset = queryset.filter(academic_year__is_current=True)

            kwargs["queryset"] = queryset.select_related(
                "teacher__staff__user", "branch", "academic_year"
            )

        return super().formfield_for_foreignkey(db_field, request, **kwargs)

    def get_teacher(self, obj):
        if obj:
            return obj.teacher_assignment.teacher.staff.user.get_full_name()

        return "-"


    get_teacher.short_description = "معلم"
    def get_class_subject_name(self, obj):
        return f"{obj.school_class.grade.name} {obj.school_class.section} - {obj.subject.name}"
    get_class_subject_name.short_description = 'کلاس و درس'


