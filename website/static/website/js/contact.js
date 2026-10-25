// Contact page enhancements (website/contact.html). Everything works
// without this file: tel:/mailto: links, the form posts normally and the
// server renders errors. Here: copy buttons, inline validation with the
// server's rules and messages, a busy submit button, and hiding the phone
// action bar while a field has focus.
(function () {
    // ----- Copy buttons (rendered hidden: copying needs JS) -----
    const live = document.createElement('p');
    live.className = 'visually-hidden';
    live.setAttribute('aria-live', 'polite');
    const contact = document.querySelector('.contact');
    if (contact) contact.appendChild(live);

    if (navigator.clipboard && window.isSecureContext) {
        document.querySelectorAll('.ct-copy[data-copy]').forEach((button) => {
            button.hidden = false;
            const label = button.querySelector('.ct-copy__text');
            let timer;
            button.addEventListener('click', () => {
                navigator.clipboard.writeText(button.dataset.copy).then(() => {
                    label.textContent = 'کپی شد';
                    button.classList.add('is-done');
                    live.textContent = 'کپی شد';
                    clearTimeout(timer);
                    timer = setTimeout(() => {
                        label.textContent = 'کپی';
                        button.classList.remove('is-done');
                        live.textContent = '';
                    }, 2000);
                });
            });
        });
    }

    // ----- Form -----
    const form = document.querySelector('[data-contact-form]');
    if (!form) return;

    const summary = document.getElementById('ct-errors');
    if (summary) summary.focus();

    const toAscii = (value) => value.replace(/[۰-۹]/g, (d) => '۰۱۲۳۴۵۶۷۸۹'.indexOf(d))
        .replace(/[٠-٩]/g, (d) => '٠١٢٣٤٥٦٧٨٩'.indexOf(d));

    // Same steps as accounts.validators.normalize_mobile.
    function normalizeMobile(value) {
        let v = toAscii(value.trim()).replace(/[\s\-().‌‎‏]/g, '');
        if (v.startsWith('+98')) v = '0' + v.slice(3);
        else if (v.startsWith('0098')) v = '0' + v.slice(4);
        else if (v.startsWith('98') && v.length === 12) v = '0' + v.slice(2);
        else if (v.startsWith('9') && v.length === 10) v = '0' + v;
        return v;
    }

    const length = (value) => value.trim().length;

    // Messages match website/forms.py.
    const rules = {
        name(value) {
            if (!length(value)) return 'نام و نام خانوادگی را وارد کنید.';
            if (length(value) < 2) return 'نام باید دست‌کم ۲ حرف باشد.';
            return '';
        },
        mobile(value) {
            if (!length(value)) return 'شماره موبایل را وارد کنید.';
            if (!/^09\d{9}$/.test(normalizeMobile(value))) {
                return 'شماره موبایل باید ۱۱ رقم باشد و با ۰۹ شروع شود؛ مثل ۰۹۱۲۳۴۵۶۷۸۹.';
            }
            return '';
        },
        topic(value) {
            return value ? '' : 'موضوع پیام را انتخاب کنید.';
        },
        message(value) {
            if (!length(value)) return 'متن پیام را بنویسید.';
            if (length(value) < 10) return 'متن پیام باید دست‌کم ۱۰ حرف باشد.';
            return '';
        },
    };

    function showError(input, message) {
        const field = input.closest('.ct-field');
        const errorId = `${input.id}_error`;
        let error = document.getElementById(errorId);
        const ids = (input.getAttribute('aria-describedby') || '').split(' ').filter((id) => id && id !== errorId);

        if (message) {
            if (!error) {
                error = document.createElement('p');
                error.className = 'ct-field__error';
                error.id = errorId;
                field.appendChild(error);
            }
            error.textContent = message;
            ids.push(errorId);
            input.setAttribute('aria-invalid', 'true');
            field.classList.add('has-error');
        } else {
            if (error) error.remove();
            input.removeAttribute('aria-invalid');
            field.classList.remove('has-error');
        }
        if (ids.length) input.setAttribute('aria-describedby', ids.join(' '));
        else input.removeAttribute('aria-describedby');
    }

    function check(input) {
        const message = rules[input.name](input.value);
        showError(input, message);
        return !message;
    }

    const inputs = Object.keys(rules).map((name) => form.elements[name]).filter(Boolean);

    inputs.forEach((input) => {
        let touched = input.getAttribute('aria-invalid') === 'true';
        input.addEventListener('input', () => { touched = true; });
        input.addEventListener('change', () => { touched = true; });
        input.addEventListener('blur', () => { if (touched) check(input); });
    });

    const submit = form.querySelector('[type="submit"]');
    let sending = false;
    form.addEventListener('submit', (event) => {
        if (sending) {
            event.preventDefault();
            return;
        }
        const invalid = inputs.filter((input) => !check(input));
        if (invalid.length) {
            event.preventDefault();
            invalid[0].focus();
            return;
        }
        sending = true;
        submit.setAttribute('aria-disabled', 'true');
        submit.dataset.idleText = submit.textContent;
        submit.textContent = submit.dataset.busyText;
    });

    // Back button from the next page restores this one from the cache.
    window.addEventListener('pageshow', (event) => {
        if (!event.persisted || !sending) return;
        sending = false;
        submit.removeAttribute('aria-disabled');
        submit.textContent = submit.dataset.idleText;
    });

    // ----- Phone action bar: off while typing (CSS :has() does the same). -----
    form.addEventListener('focusin', () => document.body.classList.add('ct-typing'));
    form.addEventListener('focusout', () => document.body.classList.remove('ct-typing'));
})();
