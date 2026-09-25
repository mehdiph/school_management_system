document.addEventListener('DOMContentLoaded', function () {
    const section = document.querySelector('[data-filter]');
    if (!section) return;

    const form = section.querySelector('form');
    const reportTypeRadios = form.querySelectorAll('input[name="report_type"]');
    const classContainer = document.getElementById('class-filter-container');
    const yearSelect = form.querySelector('select[name="year"]');
    const gradeSelect = form.querySelector('select[name="grade"]');
    const classSelect = form.querySelector('select[name="class_id"]');

    // ------------------------------------------------------------------
    // Collapsible filter (phones only -- CSS decides when it applies)
    // ------------------------------------------------------------------

    const toggle = section.querySelector('[data-filter-toggle]');
    const hasErrors = form.querySelector('.field-error') !== null;
    const startCollapsed = section.dataset.startCollapsed === 'true' && !hasErrors;

    section.classList.add('is-collapsible');
    toggle.setAttribute('aria-expanded', startCollapsed ? 'false' : 'true');
    toggle.addEventListener('click', function () {
        const expanded = toggle.getAttribute('aria-expanded') === 'true';
        toggle.setAttribute('aria-expanded', expanded ? 'false' : 'true');
    });

    // ------------------------------------------------------------------
    // Class field only for the class report
    // ------------------------------------------------------------------

    function toggleFilters() {
        const checked = form.querySelector('input[name="report_type"]:checked');
        classContainer.hidden = checked ? checked.value !== 'class' : false;
    }

    reportTypeRadios.forEach(function (radio) {
        radio.addEventListener('change', toggleFilters);
    });
    toggleFilters();

    // ------------------------------------------------------------------
    // Dependent dropdowns: year -> grades/classes, grade -> classes.
    // Options are rebuilt rather than hidden, because iOS Safari ignores
    // `hidden` on <option>. The server validates every id regardless.
    // ------------------------------------------------------------------

    const classPlaceholder = classSelect.options[0].textContent;
    let allClasses = Array.from(classSelect.options).slice(1).map(function (option) {
        return { id: option.value, label: option.textContent, gradeId: option.dataset.grade };
    });

    function renderClasses() {
        const gradeId = gradeSelect.value;
        const selected = classSelect.value;
        const visible = allClasses.filter(function (item) {
            return !gradeId || item.gradeId === gradeId;
        });

        classSelect.replaceChildren(new Option(classPlaceholder, ''));
        visible.forEach(function (item) {
            const option = new Option(item.label, item.id, false, item.id === selected);
            option.dataset.grade = item.gradeId;
            classSelect.add(option);
        });
    }

    function renderGrades(grades) {
        const selected = gradeSelect.value;
        const placeholder = gradeSelect.options[0].textContent;

        gradeSelect.replaceChildren(new Option(placeholder, ''));
        grades.forEach(function (grade) {
            const id = String(grade.id);
            gradeSelect.add(new Option(grade.name, id, false, id === selected));
        });
    }

    gradeSelect.addEventListener('change', renderClasses);

    yearSelect.addEventListener('change', function () {
        const url = new URL(form.dataset.optionsUrl, window.location.href);
        url.searchParams.set('year', yearSelect.value);

        gradeSelect.disabled = true;
        classSelect.disabled = true;

        fetch(url, { headers: { Accept: 'application/json' }, credentials: 'same-origin' })
            .then(function (response) {
                if (!response.ok) throw new Error(response.status);
                return response.json();
            })
            .then(function (data) {
                renderGrades(data.grades);
                allClasses = data.classes.map(function (item) {
                    return { id: String(item.id), label: item.label, gradeId: String(item.grade_id) };
                });
                renderClasses();
            })
            .catch(function () {
                // Keep the current options; the server rejects any mismatch.
            })
            .finally(function () {
                gradeSelect.disabled = false;
                classSelect.disabled = false;
            });
    });

    renderClasses();
});
