// Landing page sliders: the hero carousel and the teachers row.
(function () {
    const reducedMotion = window.matchMedia('(prefers-reduced-motion: reduce)');
    const SWIPE_MIN = 40;

    // Page is RTL: the "next" content sits to the left, so a finger moving
    // right (positive dx) means "next", like dragging the row along.
    function onSwipe(el, handler) {
        let x0 = null;
        let y0 = null;
        el.addEventListener('touchstart', (e) => {
            x0 = e.touches[0].clientX;
            y0 = e.touches[0].clientY;
        }, { passive: true });
        el.addEventListener('touchend', (e) => {
            if (x0 === null) return;
            const dx = e.changedTouches[0].clientX - x0;
            const dy = e.changedTouches[0].clientY - y0;
            x0 = null;
            if (Math.abs(dx) > SWIPE_MIN && Math.abs(dx) > Math.abs(dy)) handler(dx > 0 ? 1 : -1);
        }, { passive: true });
    }

    function initHero(root) {
        const slides = [...root.querySelectorAll('.main-slide')];
        const dots = [...root.querySelectorAll('[data-hero-dot]')];
        if (slides.length < 2) return;

        let index = 0;
        let timer = null;

        function show(i) {
            index = (i + slides.length) % slides.length;
            slides.forEach((slide, n) => {
                slide.classList.toggle('active', n === index);
                slide.inert = n !== index;
            });
            dots.forEach((dot, n) => {
                dot.classList.toggle('active', n === index);
                dot.toggleAttribute('aria-current', n === index);
            });
        }

        const stop = () => clearInterval(timer);
        function start() {
            stop();
            if (!reducedMotion.matches) timer = setInterval(() => show(index + 1), 6000);
        }
        function go(step) {
            show(index + step);
            start();
        }

        root.querySelector('[data-hero-next]').addEventListener('click', () => go(1));
        root.querySelector('[data-hero-prev]').addEventListener('click', () => go(-1));
        dots.forEach((dot) => dot.addEventListener('click', () => {
            show(Number(dot.dataset.heroDot));
            start();
        }));
        onSwipe(root, go);

        root.addEventListener('mouseenter', stop);
        root.addEventListener('mouseleave', start);
        root.addEventListener('focusin', stop);
        root.addEventListener('focusout', start);
        document.addEventListener('visibilitychange', () => (document.hidden ? stop() : start()));
        start();
    }

    // The track scrolls natively (scroll-snap), so touch swipe and
    // keyboard scrolling work without JS; the arrows just scroll one card.
    function initTeachers(root) {
        const track = root.querySelector('[data-teacher-track]');
        const prev = root.querySelector('[data-teacher-prev]');
        const next = root.querySelector('[data-teacher-next]');
        if (!track || !track.firstElementChild) return;

        // In RTL scrollLeft starts at 0 and goes negative towards the end.
        const dir = getComputedStyle(track).direction === 'rtl' ? -1 : 1;

        function stepWidth() {
            const gap = parseFloat(getComputedStyle(track).columnGap) || 0;
            return track.firstElementChild.getBoundingClientRect().width + gap;
        }

        function scrollByCards(count) {
            track.scrollBy({
                left: dir * count * stepWidth(),
                behavior: reducedMotion.matches ? 'auto' : 'smooth',
            });
        }

        function update() {
            const max = track.scrollWidth - track.clientWidth;
            const pos = Math.abs(track.scrollLeft);
            prev.disabled = pos <= 1;
            next.disabled = pos >= max - 1;
        }

        let frame = null;
        const scheduleUpdate = () => {
            cancelAnimationFrame(frame);
            frame = requestAnimationFrame(update);
        };

        next.addEventListener('click', () => scrollByCards(1));
        prev.addEventListener('click', () => scrollByCards(-1));
        track.addEventListener('scroll', scheduleUpdate, { passive: true });
        window.addEventListener('resize', scheduleUpdate);
        update();
    }

    document.querySelectorAll('[data-hero-slider]').forEach(initHero);
    document.querySelectorAll('[data-teacher-slider]').forEach(initTeachers);
})();
