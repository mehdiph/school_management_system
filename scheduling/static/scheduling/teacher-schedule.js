/*
 * Teacher weekly schedule: day tabs (narrow screens), in-place messages
 * for slots that cannot be recorded, print.
 *
 * Everything works without JS: the week navigation and the slots are
 * plain links rendered with their state by the server, and every day is
 * listed. This only adds day tabs and toasts (why a registered, future
 * or holiday slot cannot be recorded).
 */
(function () {
    "use strict";

    var root = document.querySelector("[data-ts]");
    if (!root) return;

    root.classList.add("ts--js");
    var isRtl = getComputedStyle(root).direction === "rtl";

    // Arrow keys follow the reading direction: in RTL, ArrowLeft is "next".
    function step(event) {
        return { ArrowLeft: isRtl ? 1 : -1, ArrowRight: isRtl ? -1 : 1 }[event.key];
    }

    function tabList(tabs, select) {
        tabs.forEach(function (tab, index) {
            tab.addEventListener("click", function (event) {
                event.preventDefault();
                select(tab, false);
            });
            tab.addEventListener("keydown", function (event) {
                var next = step(event);
                var target = null;
                if (next) target = tabs[(index + next + tabs.length) % tabs.length];
                else if (event.key === "Home") target = tabs[0];
                else if (event.key === "End") target = tabs[tabs.length - 1];
                else if (event.key === " " && tab.tagName === "A") target = tab;
                if (target) {
                    event.preventDefault();
                    select(target, true);
                }
            });
        });
    }

    // ---------- Day tabs (narrow screens) ----------

    var dayTabs = Array.prototype.slice.call(root.querySelectorAll(".ts-day-tab"));

    function selectDay(tab, moveFocus) {
        var day = tab.dataset.day;
        dayTabs.forEach(function (other) {
            var selected = other.dataset.day === day;
            other.setAttribute("aria-selected", selected ? "true" : "false");
            other.tabIndex = selected ? 0 : -1;
        });
        root.querySelectorAll(".ts-day").forEach(function (panel) {
            panel.classList.toggle("is-selected", panel.dataset.day === day);
        });
        if (moveFocus) tab.focus();
        tab.scrollIntoView({ block: "nearest", inline: "center" });
    }

    tabList(dayTabs, selectDay);

    // ---------- Slots: say why a cell cannot be recorded, in place ----------
    // Without JS a registered slot is still a link: the session form then
    // redirects back with the same error (and a link to the session).

    function toastList() {
        var list = document.querySelector("[data-toasts]");
        if (!list) {
            list = document.createElement("ul");
            list.className = "ui-toasts";
            list.setAttribute("aria-live", "polite");
            list.setAttribute("data-toasts", "");
            document.body.appendChild(list);
        }
        return list;
    }

    function toast(message, level, link) {
        var item = document.createElement("li");
        item.className = "ui-toast ui-toast--" + level;
        item.setAttribute("role", level === "error" ? "alert" : "status");

        var text = document.createElement("span");
        text.className = "ui-toast__text";
        text.textContent = message;
        if (link) {
            var anchor = document.createElement("a");
            anchor.href = link.href;
            anchor.textContent = link.label;
            text.appendChild(document.createTextNode(" "));
            text.appendChild(anchor);
        }
        item.appendChild(text);

        // Same markup as the server-rendered toasts (teacher/base.html).
        var icon = level === "error" ? "i-alert" : "i-info";
        item.insertAdjacentHTML("afterbegin",
            '<svg class="ui-icon" aria-hidden="true"><use href="#' + icon + '"></use></svg>');

        var close = document.createElement("button");
        close.type = "button";
        close.className = "ui-icon-btn ui-toast__close";
        close.setAttribute("aria-label", "بستن پیام");
        close.innerHTML = '<svg class="ui-icon ui-icon--sm" aria-hidden="true"><use href="#i-x"></use></svg>';
        item.appendChild(close);

        function dismiss() {
            if (item.parentNode) item.parentNode.removeChild(item);
        }
        close.addEventListener("click", dismiss);
        var timer = window.setTimeout(dismiss, 6000);
        item.addEventListener("mouseenter", function () { window.clearTimeout(timer); });
        item.addEventListener("focusin", function () { window.clearTimeout(timer); });

        var list = toastList();
        // One message at a time: a new click replaces the previous one.
        Array.prototype.slice.call(list.querySelectorAll(".ui-toast[data-ts-toast]")).forEach(function (old) {
            old.parentNode.removeChild(old);
        });
        item.setAttribute("data-ts-toast", "");
        list.appendChild(item);
    }

    root.addEventListener("click", function (event) {
        var registered = event.target.closest("[data-ts-registered]");
        if (registered) {
            event.preventDefault();
            toast(registered.dataset.message, "error", {
                href: registered.dataset.sessionUrl,
                label: "مشاهده‌ی جلسه‌ی ثبت‌شده",
            });
            return;
        }
        var disabled = event.target.closest("[data-ts-disabled]");
        if (disabled) {
            // Touch screens have no hover tooltip: show the reason on tap.
            toast(disabled.dataset.message, "info");
        }
    });

    // ---------- Print ----------

    root.querySelectorAll("[data-ts-print]").forEach(function (button) {
        button.hidden = false;
        button.addEventListener("click", function () {
            window.print();
        });
    });
})();
