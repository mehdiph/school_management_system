// The blog's body editor (ADR-026): Trix over the field's own textarea.
// Loaded before Trix (static/vendor/trix): it configures Trix as it starts,
// then turns each [data-bl-editor] into an editor. Without JavaScript the
// textarea is the editor; whatever is sent is cleaned again on the server
// (blog/content.py), so nothing here is a security boundary.
(function () {
    const MAX_BYTES = 2 * 1024 * 1024;
    const TYPES = ['image/jpeg', 'image/png', 'image/webp'];

    document.addEventListener('trix-before-initialize', () => {
        const config = window.Trix.config;
        if (config.blockAttributes.heading2) return;
        // «عنوان» is the article's h2 and «زیرعنوان» its h3: the page's h1 is the title.
        config.blockAttributes.heading1.tagName = 'h2';
        config.blockAttributes.heading2 = { tagName: 'h3', terminal: true, breakOnReturn: true, group: false };
        Object.assign(config.lang, {
            captionPlaceholder: 'زیرنویس تصویر (متن جایگزین هم همین است)…',
            remove: 'حذف',
            url: 'نشانی',
            bytes: 'بایت',
            KB: 'کیلوبایت',
            MB: 'مگابایت',
            GB: 'گیگابایت',
            TB: 'ترابایت',
            PB: 'پتابایت',
        });
    });

    function say(box, message) {
        const status = box.querySelector('[data-bl-editor-status]');
        if (!status) return;
        status.textContent = message;
        status.hidden = !message;
    }

    function csrfToken(form) {
        const input = form && form.querySelector('input[name="csrfmiddlewaretoken"]');
        return input ? input.value : '';
    }

    function upload(box, attachment) {
        const form = box.closest('form');
        const data = new FormData();
        data.append('image', attachment.file);
        const request = new XMLHttpRequest();
        request.open('POST', box.dataset.uploadUrl);
        request.setRequestHeader('X-CSRFToken', csrfToken(form));
        request.responseType = 'json';
        request.upload.addEventListener('progress', (event) => {
            if (event.lengthComputable) attachment.setUploadProgress((event.loaded / event.total) * 100);
        });
        request.addEventListener('load', () => {
            const body = request.response || {};
            if (request.status === 200 && body.url) {
                attachment.setAttributes({ url: body.url, href: body.url, width: body.width, height: body.height });
                say(box, '');
            } else {
                attachment.remove();
                say(box, body.error || 'بارگذاری تصویر انجام نشد. دوباره تلاش کنید.');
            }
        });
        request.addEventListener('error', () => {
            attachment.remove();
            say(box, 'بارگذاری تصویر انجام نشد؛ اتصال اینترنت را بررسی کنید.');
        });
        request.send(data);
    }

    function mount(box) {
        const textarea = box.querySelector('textarea');
        const template = box.querySelector('template[data-bl-editor-toolbar]');
        if (!textarea || !template || !window.customElements) return;
        if (!textarea.id) textarea.id = `bl-editor-${Math.random().toString(36).slice(2)}`;

        const toolbar = document.createElement('trix-toolbar');
        toolbar.id = `${textarea.id}-toolbar`;
        toolbar.appendChild(template.content.cloneNode(true));

        const editor = document.createElement('trix-editor');
        editor.setAttribute('input', textarea.id);
        editor.setAttribute('toolbar', toolbar.id);
        editor.setAttribute('dir', 'rtl');
        editor.classList.add('bl-editor__area', 'trix-content');
        const label = textarea.labels && textarea.labels[0];
        if (label) {
            if (!label.id) label.id = `${textarea.id}-label`;
            editor.setAttribute('aria-labelledby', label.id);
            label.addEventListener('click', () => editor.focus());
        }

        textarea.hidden = true;
        textarea.after(toolbar, editor);
        box.classList.add('bl-editor--ready');

        if (!box.dataset.uploadUrl) {
            toolbar.querySelector('[data-trix-button-group="file-tools"]')?.remove();
        }

        editor.addEventListener('trix-file-accept', (event) => {
            const file = event.file;
            if (!box.dataset.uploadUrl) {
                event.preventDefault();
                say(box, 'برای افزودن تصویر، نخست نوشته را ذخیره کنید.');
            } else if (!TYPES.includes(file.type)) {
                event.preventDefault();
                say(box, 'فقط تصویر jpg، png یا webp می‌توانید بگذارید.');
            } else if (file.size > MAX_BYTES) {
                event.preventDefault();
                say(box, 'حجم تصویر نباید بیشتر از ۲ مگابایت باشد.');
            }
        });
        editor.addEventListener('trix-attachment-add', (event) => {
            if (event.attachment.file) upload(box, event.attachment);
        });
    }

    function start() {
        document.querySelectorAll('[data-bl-editor]').forEach(mount);
    }

    if (document.readyState === 'loading') {
        document.addEventListener('DOMContentLoaded', start);
    } else {
        start();
    }
})();
