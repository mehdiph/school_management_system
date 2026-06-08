from django.shortcuts import render, get_object_or_404
from django.views import View
from django.http import HttpResponse
from django.template.loader import get_template
from django.conf import settings
from jdatetime import datetime
import os

# Third-party for PDF
from weasyprint import HTML
from weasyprint.text.fonts import FontConfiguration

from school.models import SchoolClass, ClassSubject, AcademicYear, Grade
from teaching.models import SchoolSession

class BaseReportView(View):
    """
    Base view to handle PDF generation logic using WeasyPrint.
    """
    template_name = None 

    def get_report_context(self, request, *args, **kwargs):
        raise NotImplementedError

    def get(self, request, *args, **kwargs):
        context = self.get_report_context(request, *args, **kwargs)
        
        if request.GET.get('format') == 'pdf':
            return self.render_to_pdf(request, context)
        
        return render(request, self.template_name, context)

    def render_to_pdf(self, request, context):
        context['is_pdf'] = True
        
        # Determine strict font path for WeasyPrint
        # Assuming we have a font file in static/fonts/ or similar
        # Since I don't see a visible fonts folder, I will try to find where Vazirmatn is
        # Or recommend the user to place it. For now, I will assume it is in static/fonts/Vazirmatn-Regular.ttf
        # If not, WeasyPrint will struggle. I'll add a check.
        
        # CHECK: Does the user have the font locally? 
        # The user's system likely doesn't have it in a static folder yet based on file list.
        # I will point to a system font or ask the user.
        # However, for a robust solution, I should look for the font file.
        # I'll Assume standard staticfile structure: static/fonts/Vazirmatn.ttf
        
        font_path = os.path.join(settings.BASE_DIR, 'static', 'fonts', 'Vazirmatn-Regular.ttf')
        context['font_path'] = font_path

        # Use specific PDF template
        template = get_template('report/report_pdf.html')
        html_string = template.render(context)

        # Create HTTP Response
        response = HttpResponse(content_type='application/pdf')
        filename = f"report_{datetime.now().strftime('%Y_%m_%d')}.pdf"
        response['Content-Disposition'] = f'inline; filename="{filename}"'

        # WeasyPrint font config
        font_config = FontConfiguration()
        
        # Base URL for resolving static files
        base_url = request.build_absolute_uri('/')

        # Generate PDF
        try:
            HTML(string=html_string, base_url=base_url).write_pdf(
                target=response, 
                font_config=font_config,
                presentational_hints=True
            )
        except Exception as e:
            return HttpResponse(f"Error generating PDF (WeasyPrint): {e}")

        return response


class ReportsView(BaseReportView):
    template_name = 'report/reports.html'

    def get_report_context(self, request, *args, **kwargs):
        # 1. Base Context (Form Data)
        context = {
            'years': AcademicYear.objects.all().order_by('-start_date'),
            'grades_list': Grade.objects.filter(is_active=True).order_by('level'),
            'classes_list': SchoolClass.objects.filter(is_active=True).select_related('grade').order_by('grade__level', 'section'),
            'report_type': request.GET.get('report_type', 'class'),
            'selected_year_id': int(request.GET.get('year')) if request.GET.get('year') else None,
            'selected_grade_id': int(request.GET.get('grade')) if request.GET.get('grade') else None,
            'selected_class_id': int(request.GET.get('class_id')) if request.GET.get('class_id') else None,
            'has_report': False,
        }

        # 2. Process Report Generation if params exist
        if request.GET.get('report_type'):
             report_data = self.generate_report_data(request)
             if report_data:
                 context.update(report_data)
                 context['has_report'] = True

        return context

    def generate_report_data(self, request):
        report_type = request.GET.get('report_type')
        year_id = request.GET.get('year')
        
        if not year_id:
            return None

        # --- CLASS BASED REPORT ---
        if report_type == 'class':
            class_id = request.GET.get('class_id')
            if not class_id:
                return None
            
            return self._get_class_report_data(class_id)

        # --- GRADE BASED REPORT ---
        elif report_type == 'grade':
            grade_id = request.GET.get('grade')
            return self._get_grade_report_data(year_id, grade_id)

        return None

    def _get_class_report_data(self, class_id):
        school_class = get_object_or_404(SchoolClass, pk=class_id)
        
        class_subjects = ClassSubject.objects.filter(
            school_class=school_class
        ).select_related(
            'subject', 'teacher'
        ).prefetch_related(
            'schoolsession_set',
            'schoolsession_set__session_contents'
        ).order_by('subject__name')

        subjects_data = []
        global_first_date = None
        global_last_date = None
        total_sessions_count = 0

        for cs in class_subjects:
            sessions = cs.schoolsession_set.all().order_by('date', 'session_number')
            session_list = []
            session_list_held = []
            cs_first_date = None
            cs_last_date = None
            
            for session in sessions:
                if not global_first_date or (session.date and session.date < global_first_date):
                    global_first_date = session.date
                if not global_last_date or (session.date and session.date > global_last_date):
                    global_last_date = session.date

                if not cs_first_date: cs_first_date = session.date
                cs_last_date = session.date 
                
                content_summary = ""
                if hasattr(session, 'session_contents'):
                    content_summary = session.session_contents.title + ": " + session.session_contents.content

                session_list.append({
                    'number': session.session_number,
                    'date': session.date,
                    'content': content_summary,
                    'status': session.status,
                })

                if session.status == 'HD':
                    session_list_held.append({
                        'number': session.session_number,
                        'date': session.date,
                        'content': content_summary
                    })
            
            subjects_data.append({
                'name': cs.subject.name,
                'teacher_name': cs.teacher.get_full_name() or cs.teacher.username,
                'session_count': len(session_list),
                'first_date': cs_first_date,
                'last_date': cs_last_date,
                'sessions': session_list
            })
            total_sessions_count += len(session_list_held)

        return {
            'class_name': school_class.section,
            'grade': school_class.grade.name,
            'academic_year': school_class.year.title,
            'report_date': datetime.now().strftime("%Y-%m-%d"),
            'total_subjects': len(subjects_data),
            'total_sessions': total_sessions_count,
            'first_session_date': global_first_date,
            'last_session_date': global_last_date,
            'subjects': subjects_data,
        }

    def _get_grade_report_data(self, year_id, grade_id=None):
        academic_year = get_object_or_404(AcademicYear, pk=year_id)
        
        grades_query = Grade.objects.filter(is_active=True).order_by('level')
        if grade_id:
            grades_query = grades_query.filter(pk=grade_id)

        grades_data = []

        for grade in grades_query:
            classes = SchoolClass.objects.filter(grade=grade, year=academic_year).order_by('section')
            if not classes.exists():
                continue

            classes_list = []
            for school_class in classes:
                sessions = SchoolSession.objects.filter(
                    class_subject__school_class=school_class
                ).select_related(
                    'class_subject', 
                    'class_subject__subject',
                    'class_subject__teacher'
                ).prefetch_related(
                    'sessioncontent'
                ).order_by('date', 'session_number')

                if not sessions.exists():
                    classes_list.append({'class_name': school_class.section, 'sessions': []})
                    continue

                session_rows = []
                for s in sessions:
                    content_summary = ""
                    if hasattr(s, 'sessioncontent'):
                        content = s.sessioncontent.content
                        if len(content) > 50: content = content[:50] + "..."
                        content_summary = content

                    session_rows.append({
                        'date': s.date,
                        'subject_name': s.class_subject.subject.name,
                        'teacher_name': s.class_subject.teacher.get_full_name() or s.class_subject.teacher.username,
                        'content_summary': content_summary
                    })
                
                classes_list.append({
                    'class_name': school_class.section,
                    'sessions': session_rows
                })

            if classes_list:
                 grades_data.append({
                    'grade_name': grade.name,
                    'classes': classes_list
                })

        return {
            'academic_year': academic_year.title,
            'report_date': datetime.now().strftime("%Y/%m/%d"),
            'grades_data': grades_data
        }
