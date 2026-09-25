from django import forms

REPORT_TYPE_CLASS = "class"
REPORT_TYPE_GRADE = "grade"


def class_label(school_class):
    return f"{school_class.grade.name} - {school_class.section}"


class ClassChoiceField(forms.ModelChoiceField):
    def label_from_instance(self, obj):
        return class_label(obj)


class ReportFilterForm(forms.Form):
    """
    Report filters. Every queryset comes from a ``ReportScope``, so an id
    outside the user's scope -- e.g. another teacher's class typed into
    the URL -- fails ``ModelChoiceField`` validation on the server.
    """

    report_type = forms.ChoiceField(
        label="نوع گزارش",
        choices=[
            (REPORT_TYPE_CLASS, "بر اساس کلاس"),
            (REPORT_TYPE_GRADE, "بر اساس پایه"),
        ],
        initial=REPORT_TYPE_CLASS,
        widget=forms.RadioSelect,
    )
    year = forms.ModelChoiceField(
        label="سال تحصیلی",
        queryset=None,
        empty_label=None,
        widget=forms.Select(attrs={"class": "form-control"}),
    )
    grade = forms.ModelChoiceField(
        label="پایه تحصیلی (اختیاری)",
        queryset=None,
        required=False,
        empty_label="همه پایه‌ها",
        widget=forms.Select(attrs={"class": "form-control"}),
    )
    class_id = ClassChoiceField(
        label="کلاس",
        queryset=None,
        required=False,
        empty_label="انتخاب کنید...",
    )

    def __init__(self, *args, scope, years, **kwargs):
        """
        ``years`` is ``scope.years()`` already evaluated by the view; it
        is reused for the year dropdown and to pick which year's grades
        and classes are offered, so neither needs another query.
        """

        super().__init__(*args, **kwargs)
        self.scope = scope

        self.fields["year"].queryset = scope.years()
        self.fields["year"].choices = [(year.pk, year.title) for year in years]

        self.selected_year = self._selected_year(years)
        if not self.is_bound and self.selected_year is not None:
            self.initial.setdefault("year", self.selected_year.pk)

        self.fields["grade"].queryset = (
            scope.grades(self.selected_year).order_by("level")
        )
        self.fields["class_id"].queryset = (
            scope.classes(self.selected_year)
            .filter(is_active=True)
            .select_related("grade", "year")
            .order_by("grade__level", "section")
        )

    def _selected_year(self, years):
        """The submitted year if it is in scope, otherwise the default one."""

        submitted = self.data.get(self.add_prefix("year"))

        for year in years:
            if str(year.pk) == submitted:
                return year

        return self.scope.default_year(years)

    def clean(self):
        cleaned_data = super().clean()

        if cleaned_data.get("report_type") != REPORT_TYPE_CLASS:
            return cleaned_data

        grade = cleaned_data.get("grade")
        school_class = cleaned_data.get("class_id")

        if school_class is None:
            if "class_id" not in self.errors:
                self.add_error("class_id", "برای گزارش کلاسی، یک کلاس انتخاب کنید.")
        elif grade is not None and school_class.grade_id != grade.pk:
            self.add_error("class_id", "کلاس انتخاب‌شده متعلق به پایه انتخاب‌شده نیست.")

        return cleaned_data

    def class_options(self):
        """``(class, selected)`` pairs, so the template can add ``data-grade``."""

        selected = str(self["class_id"].value() or "")

        return [
            (school_class, str(school_class.pk) == selected)
            for school_class in self.fields["class_id"].queryset
        ]
