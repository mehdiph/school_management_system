document.addEventListener('DOMContentLoaded', function () {
    const reportTypeRadios = document.querySelectorAll('input[name="report_type"]');
    const classContainer = document.getElementById('class-filter-container');
    const gradeContainer = document.getElementById('grade-filter-container');

    function toggleFilters() {
        // Find checked radio
        let selectedType = 'class'; // default
        for (const radio of reportTypeRadios) {
            if (radio.checked) {
                selectedType = radio.value;
                break;
            }
        }

        if (selectedType === 'class') {
            classContainer.style.display = 'flex';
        } else {
            classContainer.style.display = 'none';
        }
    }

    // Attach listeners
    reportTypeRadios.forEach(radio => {
        radio.addEventListener('change', toggleFilters);
    });

    // Initial run
    toggleFilters();
});
