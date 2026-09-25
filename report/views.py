from django.contrib.auth.mixins import LoginRequiredMixin
from django.shortcuts import render
from django.urls import reverse_lazy
from django.views import View
from django.http import HttpResponse, JsonResponse
from django.template.loader import get_template
from django.conf import settings
from jdatetime import datetime
import os

# Third-party for PDF
from weasyprint import HTML
from weasyprint.text.fonts import FontConfiguration

from .forms import REPORT_TYPE_CLASS, ReportFilterForm, class_label
from .selectors import (
    NO_ASSIGNMENT_MESSAGE,
    NO_CURRENT_YEAR_NOTICE,
    ReportScope,
    build_class_report,
    build_grade_report,
)

class BaseReportView(View):
    """
    Base view to handle PDF generation logic using WeasyPrint.
    """
    template_name = None 

    def get_report_context(self, request, *args, **kwargs):
        raise NotImplementedError

    def get(self, request, *args, **kwargs):
        context = self.get_report_context(request, *args, **kwargs)
        
        if request.GET.get('format') == 'pdf' and context.get('has_report'):
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


class ReportsView(LoginRequiredMixin, BaseReportView):
    template_name = 'report/reports.html'
    login_url = reverse_lazy('accounts:login')

    def get_report_context(self, request, *args, **kwargs):
        scope = ReportScope(request.user)
        context = {'has_report': False, 'form': None, 'scope_message': None}

        if scope.error_message:
            context['scope_message'] = scope.error_message
            return context

        years = list(scope.years())

        if not years:
            context['scope_message'] = NO_ASSIGNMENT_MESSAGE
            return context

        if scope.is_restricted and not any(year.is_current for year in years):
            context['scope_notice'] = NO_CURRENT_YEAR_NOTICE

        is_submitted = 'report_type' in request.GET
        form = ReportFilterForm(
            request.GET if is_submitted else None, scope=scope, years=years
        )
        context['form'] = form
        context['report_type'] = form['report_type'].value()

        if is_submitted and form.is_valid():
            data = form.cleaned_data

            if data['report_type'] == REPORT_TYPE_CLASS:
                report = build_class_report(scope, data['class_id'])
            else:
                report = build_grade_report(scope, data['year'], data['grade'])

            context.update(report)
            context['has_report'] = True

        return context


class ReportOptionsView(LoginRequiredMixin, View):
    """
    Grades and classes of one academic year for the report filter, as
    JSON. Uses the same form (and therefore the same ``ReportScope``
    querysets) as the page, so the dropdowns can never offer more than
    the server would accept.
    """

    login_url = reverse_lazy('accounts:login')

    def get(self, request):
        scope = ReportScope(request.user)
        years = [] if scope.error_message else list(scope.years())
        year_id = request.GET.get('year')

        if not any(str(year.pk) == year_id for year in years):
            return JsonResponse({'grades': [], 'classes': []}, status=404)

        form = ReportFilterForm({'year': year_id}, scope=scope, years=years)

        return JsonResponse({
            'grades': [
                {'id': grade.pk, 'name': grade.name}
                for grade in form.fields['grade'].queryset
            ],
            'classes': [
                {
                    'id': school_class.pk,
                    'label': class_label(school_class),
                    'grade_id': school_class.grade_id,
                }
                for school_class in form.fields['class_id'].queryset
            ],
        })
