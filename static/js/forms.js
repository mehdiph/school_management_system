document.addEventListener('DOMContentLoaded', function () {
    // Auto-focus first input
    const firstSelect = document.querySelector('select.form-control, input.form-control');
    if (firstSelect) {
        firstSelect.focus();
    }

    // Enhance select dropdowns with visual feedback
    const selectElements = document.querySelectorAll('select.form-control');
    selectElements.forEach(select => {
        select.addEventListener('change', function () {
            if (this.value) {
                this.style.borderColor = 'var(--success)';
                setTimeout(() => {
                    this.style.borderColor = '';
                }, 300);
            }
        });
    });

    // Form submit loading state
    const forms = document.querySelectorAll('form');
    forms.forEach(form => {
        form.addEventListener('submit', function () {
            const submitBtn = this.querySelector('button[type="submit"]');
            if (submitBtn && !submitBtn.classList.contains('no-loading')) {
                submitBtn.classList.add('loading');
                submitBtn.disabled = true;

                // Backup for if text replacement is desired
                if (submitBtn.dataset.loadingText) {
                    const icon = submitBtn.querySelector('i');
                    submitBtn.innerHTML = (icon ? icon.outerHTML + ' ' : '') + submitBtn.dataset.loadingText;
                }
            }
        });
    });
});
