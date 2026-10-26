/* The public blog: enhancement only, every page works without it (ADR-015).
   - «کپی پیوند»: shown only here, since copying needs JS.
   - The masthead's cut-outs drop onto the board once per visit (CSS does
     the motion, and nothing with prefers-reduced-motion). */
(function () {
    "use strict";

    function setUpCopy() {
        var button = document.querySelector("[data-bl-copy]");
        var status = document.querySelector("[data-bl-copy-status]");
        if (!button || !navigator.clipboard) {
            return;
        }
        button.hidden = false;
        button.addEventListener("click", function () {
            navigator.clipboard.writeText(button.getAttribute("data-bl-copy")).then(function () {
                var done = button.getAttribute("data-bl-copied");
                if (status) {
                    status.textContent = done;
                }
                button.classList.add("is-done");
                button.textContent = done;
            });
        });
    }

    function settleMasthead() {
        var masthead = document.querySelector("[data-bl-masthead]");
        if (!masthead) {
            return;
        }
        var key = "blMastheadSettled";
        try {
            if (window.sessionStorage.getItem(key)) {
                return;
            }
            window.sessionStorage.setItem(key, "1");
        } catch (error) {
            return; // no storage: no motion, rather than motion on every page
        }
        masthead.classList.add("bl-masthead--settle");
    }

    setUpCopy();
    settleMasthead();
})();
