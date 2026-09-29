/*
 * Teacher panel shell (template/teacher/base.html):
 *   - sidebar: collapse to icons on desktop (remembered), drawer below 1024px
 *   - user menu: WAI-ARIA menu button (Enter/Space/arrows/Escape, click outside)
 *   - toasts: close button, auto-dismiss for non-errors
 *   - forms with [data-busy-form]: disable the submit button + spinner while submitting
 */
(function () {
    "use strict";

    var root = document.documentElement;
    var body = document.body;

    // ------------------------------------------------------------------
    // Sidebar
    // ------------------------------------------------------------------

    var sidebar = document.getElementById("teacherSidebar");
    var toggle = document.getElementById("sidebarToggle");
    var overlay = document.getElementById("sidebarOverlay");
    var desktop = window.matchMedia("(min-width: 1024px)");
    var STORAGE_KEY = "teacher.sidebar";

    function remember(value) {
        try {
            localStorage.setItem(STORAGE_KEY, value);
        } catch (e) {}
    }

    function setInert(element, value) {
        if (!element) return;
        if ("inert" in element) element.inert = value;
        if (value) element.setAttribute("aria-hidden", "true");
        else element.removeAttribute("aria-hidden");
    }

    function syncToggle() {
        if (!toggle) return;
        var label;
        if (desktop.matches) {
            var collapsed = root.classList.contains("ui-sidebar-collapsed");
            toggle.setAttribute("aria-expanded", collapsed ? "false" : "true");
            label = collapsed ? toggle.dataset.labelExpand : toggle.dataset.labelCollapse;
        } else {
            var open = root.classList.contains("ui-sidebar-open");
            toggle.setAttribute("aria-expanded", open ? "true" : "false");
            label = open ? toggle.dataset.labelClose : toggle.dataset.labelOpen;
        }
        toggle.setAttribute("aria-label", label);
    }

    function openDrawer() {
        root.classList.add("ui-sidebar-open");
        setInert(sidebar, false);
        overlay.hidden = false;
        requestAnimationFrame(function () {
            overlay.classList.add("is-visible");
        });
        body.classList.add("is-scroll-locked");
        syncToggle();
        var first = sidebar.querySelector("a, button");
        if (first) first.focus();
    }

    function closeDrawer(restoreFocus) {
        if (!root.classList.contains("ui-sidebar-open")) return;
        root.classList.remove("ui-sidebar-open");
        overlay.classList.remove("is-visible");
        body.classList.remove("is-scroll-locked");
        setInert(sidebar, true);
        syncToggle();
        window.setTimeout(function () {
            if (!root.classList.contains("ui-sidebar-open")) overlay.hidden = true;
        }, 200);
        if (restoreFocus !== false && toggle) toggle.focus();
    }

    function applyBreakpoint() {
        if (desktop.matches) {
            root.classList.remove("ui-sidebar-open");
            body.classList.remove("is-scroll-locked");
            overlay.classList.remove("is-visible");
            overlay.hidden = true;
            setInert(sidebar, false);
        } else {
            setInert(sidebar, !root.classList.contains("ui-sidebar-open"));
        }
        syncToggle();
    }

    if (sidebar && toggle && overlay) {
        toggle.addEventListener("click", function () {
            if (desktop.matches) {
                var collapsed = root.classList.toggle("ui-sidebar-collapsed");
                remember(collapsed ? "collapsed" : "expanded");
                syncToggle();
            } else if (root.classList.contains("ui-sidebar-open")) {
                closeDrawer();
            } else {
                openDrawer();
            }
        });

        overlay.addEventListener("click", function () {
            closeDrawer();
        });

        sidebar.querySelectorAll("[data-sidebar-close]").forEach(function (button) {
            button.addEventListener("click", function () {
                closeDrawer();
            });
        });

        // Keep Tab inside the open drawer (it is a modal on small screens).
        sidebar.addEventListener("keydown", function (event) {
            if (event.key !== "Tab" || desktop.matches) return;
            var focusable = sidebar.querySelectorAll("a[href], button:not([disabled])");
            if (!focusable.length) return;
            var first = focusable[0];
            var last = focusable[focusable.length - 1];
            if (event.shiftKey && document.activeElement === first) {
                event.preventDefault();
                last.focus();
            } else if (!event.shiftKey && document.activeElement === last) {
                event.preventDefault();
                first.focus();
            }
        });

        if (desktop.addEventListener) desktop.addEventListener("change", applyBreakpoint);
        else if (desktop.addListener) desktop.addListener(applyBreakpoint);
        applyBreakpoint();
    }

    // ------------------------------------------------------------------
    // User menu
    // ------------------------------------------------------------------

    document.querySelectorAll("[data-usermenu]").forEach(function (menuRoot) {
        var trigger = menuRoot.querySelector('[aria-haspopup="menu"]');
        var panel = document.getElementById(trigger.getAttribute("aria-controls"));
        var items = Array.prototype.slice.call(panel.querySelectorAll('[role="menuitem"]'));

        function isOpen() {
            return !panel.hidden;
        }

        function open(focusIndex) {
            panel.hidden = false;
            trigger.setAttribute("aria-expanded", "true");
            if (typeof focusIndex === "number" && items.length) {
                items[(focusIndex + items.length) % items.length].focus();
            }
        }

        function close(restoreFocus) {
            if (!isOpen()) return;
            panel.hidden = true;
            trigger.setAttribute("aria-expanded", "false");
            if (restoreFocus) trigger.focus();
        }

        trigger.addEventListener("click", function () {
            if (isOpen()) close(false);
            else open(0);
        });

        trigger.addEventListener("keydown", function (event) {
            if (event.key === "ArrowDown") {
                event.preventDefault();
                open(0);
            } else if (event.key === "ArrowUp") {
                event.preventDefault();
                open(-1);
            }
        });

        panel.addEventListener("keydown", function (event) {
            var index = items.indexOf(document.activeElement);
            if (event.key === "ArrowDown") {
                event.preventDefault();
                items[(index + 1) % items.length].focus();
            } else if (event.key === "ArrowUp") {
                event.preventDefault();
                items[(index - 1 + items.length) % items.length].focus();
            } else if (event.key === "Home") {
                event.preventDefault();
                items[0].focus();
            } else if (event.key === "End") {
                event.preventDefault();
                items[items.length - 1].focus();
            } else if (event.key === "Escape") {
                event.preventDefault();
                close(true);
            } else if (event.key === "Tab") {
                close(false);
            } else if (event.key === " " && index > -1) {
                // Links only activate on Enter by default.
                event.preventDefault();
                items[index].click();
            }
        });

        document.addEventListener("click", function (event) {
            if (!menuRoot.contains(event.target)) close(false);
        });
    });

    // Escape closes the drawer (the menu handles its own Escape above).
    document.addEventListener("keydown", function (event) {
        if (event.key === "Escape" && root.classList.contains("ui-sidebar-open")) {
            closeDrawer();
        }
    });

    // ------------------------------------------------------------------
    // Toasts
    // ------------------------------------------------------------------

    function dismiss(toast) {
        if (!toast || toast.classList.contains("is-leaving")) return;
        toast.classList.add("is-leaving");
        window.setTimeout(function () {
            if (toast.parentNode) toast.parentNode.removeChild(toast);
        }, 200);
    }

    document.querySelectorAll("[data-toasts] .ui-toast").forEach(function (toast) {
        var close = toast.querySelector("[data-toast-close]");
        if (close) {
            close.addEventListener("click", function () {
                dismiss(toast);
            });
        }
        // Errors stay until closed; everything else fades after a while.
        if (!toast.classList.contains("ui-toast--error")) {
            var timer = window.setTimeout(function () {
                dismiss(toast);
            }, 6000);
            toast.addEventListener("mouseenter", function () {
                window.clearTimeout(timer);
            });
            toast.addEventListener("focusin", function () {
                window.clearTimeout(timer);
            });
        }
    });

    // ------------------------------------------------------------------
    // Busy submit buttons
    // ------------------------------------------------------------------

    document.querySelectorAll("form[data-busy-form]").forEach(function (form) {
        form.addEventListener("submit", function (event) {
            if (event.defaultPrevented) return;
            var button = event.submitter || form.querySelector('[type="submit"]');
            if (!button) return;
            // A double click must not send the form twice, but the button's
            // own name/value still has to be posted: disable on the next tick.
            button.classList.add("is-busy");
            button.setAttribute("aria-busy", "true");
            window.setTimeout(function () {
                button.disabled = true;
            }, 0);
        });
    });

    // Back/forward cache: never come back to a spinning, disabled button.
    window.addEventListener("pageshow", function (event) {
        if (!event.persisted) return;
        document.querySelectorAll(".ui-btn.is-busy").forEach(function (button) {
            button.classList.remove("is-busy");
            button.removeAttribute("aria-busy");
            button.disabled = false;
        });
    });
})();
