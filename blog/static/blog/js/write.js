// «نوشته‌های من» (blog/templates/blog/write/): small helps on top of pages
// that work without JavaScript. A character counter under each text box
// with [data-bl-counter], a confirmation before archiving, and a warning
// before leaving a form with unsaved changes. The editor itself is
// blog/js/editor.js.
(function () {
    const digits = (n) => String(n).replace(/\d/g, (d) => '۰۱۲۳۴۵۶۷۸۹'[d]);

    function counter(field) {
        const max = Number(field.getAttribute('maxlength'));
        if (!max) return;
        const note = document.createElement('p');
        note.className = 'bw-counter';
        note.setAttribute('aria-live', 'polite');
        const update = () => {
            note.textContent = `${digits(field.value.length)} از ${digits(max)} نویسه`;
        };
        field.after(note);
        field.addEventListener('input', update);
        update();
    }

    function guard(form) {
        let dirty = false;
        let sending = false;
        const mark = () => { dirty = true; };
        form.addEventListener('input', mark);
        form.addEventListener('change', mark);
        // Trix writes into its hidden input without an input event on the form.
        form.addEventListener('trix-change', mark);
        form.addEventListener('submit', (event) => {
            const message = event.submitter && event.submitter.dataset.bwConfirm;
            if (message && !window.confirm(message)) {
                event.preventDefault();
                return;
            }
            sending = true;
        });
        window.addEventListener('beforeunload', (event) => {
            if (dirty && !sending) {
                event.preventDefault();
                event.returnValue = '';
            }
        });
    }

    function start() {
        document.querySelectorAll('[data-bl-counter]').forEach(counter);
        document.querySelectorAll('[data-bw-form]').forEach(guard);
    }

    if (document.readyState === 'loading') {
        document.addEventListener('DOMContentLoaded', start);
    } else {
        start();
    }
})();
