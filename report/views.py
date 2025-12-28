from django.shortcuts import render, get_object_or_404
from django.views import View
from django.http import HttpResponse
from django.template.loader import get_template
from django.conf import settings
from django.db.models import Count, Min, Max
from django.utils import timezone
import os
from xhtml2pdf import pisa

from school.models import SchoolClass, ClassSubject, AcademicYear, Grade
from teaching.models import SchoolSession

class BaseReportView(View):
    """
    Base view to handle PDF generation logic and static file callback.
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
        response = HttpResponse(content_type='application/pdf')
        filename = f"report_{timezone.now().strftime('%Y%m%d%H%M')}.pdf"
        response['Content-Disposition'] = f'inline; filename="{filename}"'

        template = get_template(self.template_name)
        html = template.render(context)

        pisa_status = pisa.CreatePDF(
            html, dest=response, link_callback=self.link_callback
        )

        if pisa_status.err:
            return HttpResponse('We had some errors <pre>' + html + '</pre>')
        return response

    @staticmethod
    def link_callback(uri, rel):
        sUrl = settings.STATIC_URL
        sRoot = settings.STATIC_ROOT
        mUrl = settings.MEDIA_URL
        mRoot = settings.MEDIA_ROOT

        if uri.startswith(mUrl):
            path = os.path.join(mRoot, uri.replace(mUrl, ""))
        elif uri.startswith(sUrl):
            path = os.path.join(sRoot, uri.replace(sUrl, ""))
        else:
            return uri 

        if not os.path.isfile(path):
             # Dev environment fallback - Check local static folder
             local_static = os.path.join(settings.BASE_DIR, 'static')
             rel_path = uri.replace(sUrl, "")
             local_path = os.path.join(local_static, rel_path)
             
             if os.path.isfile(local_path):
                 return local_path

             # App specific fallbacks (legacy check, might not be needed if above works but keeping for safety)
             if 'report/css/' in uri:
                 if 'grade_report.css' in uri:
                     return os.path.join(settings.BASE_DIR, 'report/static/report/css/grade_report.css')
                 if 'report.css' in uri:
                     return os.path.join(settings.BASE_DIR, 'report/static/report/css/report.css')
                 if 'reports.css' in uri:
                     return os.path.join(settings.BASE_DIR, 'report/static/report/css/reports.css')

             print(f"Warning: PDF static file not found: {path} (and local fallback {local_path}) for uri: {uri}")

        return path


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
            'schoolsession_set__sessioncontent'
        ).order_by('subject__name')

        subjects_data = []
        global_first_date = None
        global_last_date = None
        total_sessions_count = 0

        for cs in class_subjects:
            sessions = cs.schoolsession_set.all().order_by('date', 'session_number')
            session_list = []
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
                if hasattr(session, 'sessioncontent'):
                    content_summary = session.sessioncontent.title + ": " + session.sessioncontent.content

                session_list.append({
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
            total_sessions_count += len(session_list)

        return {
            'class_name': school_class.section,
            'grade': school_class.grade.name,
            'academic_year': school_class.year.title,
            'report_date': timezone.now().strftime("%Y-%m-%d"),
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
            'report_date': timezone.now().strftime("%Y-%m-%d"),
            'grades_data': grades_data
        }
