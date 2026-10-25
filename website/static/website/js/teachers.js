// «معلمان» page: enhancements only; the page works fully without them.
// - The group chips are links (?group=<id>). Here a click fetches the same
//   URL with ?partial=1 (ADR-015), swaps the filter and the list, updates
//   the address and announces the number of teachers. Any failure falls
//   back to normal navigation.
// - A link to a teacher (/teachers/#<slug>) opens that teacher's «درباره …».
(function () {
    const status = document.querySelector('[data-tc-status]');
    let shown = location.search; // the filter the list on screen was rendered for

    function openLinkedTeacher() {
        if (!location.hash) return;
        let target;
        try {
            target = document.getElementById(decodeURIComponent(location.hash.slice(1)));
        } catch (error) {
            return;
        }
        const details = target && target.matches('.tc-teacher') && target.querySelector('details');
        if (details) details.open = true;
    }

    function swap(html) {
        const fresh = document.createElement('template');
        fresh.innerHTML = html;
        fresh.content.querySelectorAll('[data-tc-swap]').forEach((block) => {
            const current = document.querySelector(`[data-tc-swap="${block.dataset.tcSwap}"]`);
            if (current) current.replaceWith(block);
        });
    }

    async function load(url, { push }) {
        const partial = new URL(url, location.href);
        partial.searchParams.set('partial', '1');
        partial.hash = '';
        const response = await fetch(partial, { headers: { Accept: 'text/html' } });
        if (!response.ok) throw new Error(response.status);
        swap(await response.text());
        if (push) history.pushState({ teachers: true }, '', url);
        shown = new URL(url, location.href).search;

        const list = document.querySelector('[data-tc-swap="list"]');
        if (status && list) status.textContent = list.dataset.tcCount || '';
    }

    document.addEventListener('click', async (event) => {
        const chip = event.target.closest('.tc-chip');
        if (!chip || event.defaultPrevented || event.button !== 0
            || event.metaKey || event.ctrlKey || event.shiftKey || event.altKey) return;
        event.preventDefault();
        const href = chip.href;
        try {
            await load(href, { push: true });
            // Keep the keyboard where it was: on the chip just chosen.
            const same = [...document.querySelectorAll('.tc-chip')].find((el) => el.href === href);
            if (same) same.focus();
        } catch (error) {
            location.href = href;
        }
    });

    window.addEventListener('popstate', () => {
        // Following a teacher's #link fires popstate too: nothing to reload.
        if (location.search === shown) return;
        load(location.href, { push: false }).catch(() => location.reload());
    });

    window.addEventListener('hashchange', openLinkedTeacher);
    openLinkedTeacher();
})();
