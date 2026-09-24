// Mobile drawer for the public navbar (partials/public_navbar.html).
(function () {
    const toggle = document.querySelector('.nav-toggle');
    const panel = document.getElementById('public-nav-panel');
    const overlay = document.querySelector('[data-nav-overlay]');
    if (!toggle || !panel || !overlay) return;

    const desktop = window.matchMedia('(min-width: 992px)');
    const isOpen = () => toggle.getAttribute('aria-expanded') === 'true';
    const focusables = () => [...panel.querySelectorAll('a[href]'), toggle]
        .filter((el) => el.offsetParent !== null);

    function open() {
        toggle.setAttribute('aria-expanded', 'true');
        toggle.setAttribute('aria-label', toggle.dataset.labelClose);
        panel.classList.add('is-open');
        overlay.hidden = false;
        requestAnimationFrame(() => overlay.classList.add('is-visible'));
        document.documentElement.classList.add('nav-locked');
        const first = panel.querySelector('a[href]');
        if (first) first.focus();
    }

    function close(returnFocus) {
        if (!isOpen()) return;
        toggle.setAttribute('aria-expanded', 'false');
        toggle.setAttribute('aria-label', toggle.dataset.labelOpen);
        panel.classList.remove('is-open');
        overlay.classList.remove('is-visible');
        overlay.hidden = true;
        document.documentElement.classList.remove('nav-locked');
        if (returnFocus) toggle.focus();
    }

    toggle.addEventListener('click', () => (isOpen() ? close(false) : open()));
    overlay.addEventListener('click', () => close(true));
    panel.addEventListener('click', (e) => {
        if (e.target.closest('a')) close(false);
    });
    desktop.addEventListener('change', (e) => {
        if (e.matches) close(false);
    });

    document.addEventListener('keydown', (e) => {
        if (!isOpen()) return;
        if (e.key === 'Escape') {
            close(true);
        } else if (e.key === 'Tab') {
            // Keep focus inside the drawer (+ the close button).
            const items = focusables();
            const first = items[0];
            const last = items[items.length - 1];
            if (e.shiftKey && document.activeElement === first) {
                e.preventDefault();
                last.focus();
            } else if (!e.shiftKey && document.activeElement === last) {
                e.preventDefault();
                first.focus();
            }
        }
    });
})();
