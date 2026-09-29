/*
 * Teacher weekly schedule: week tabs, day tabs (narrow screens), print.
 *
 * Both weeks and every day are already in the page, so switching is only
 * showing/hiding. Without JS the week tabs are plain ?week=N links and
 * every day is listed.
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

    // ---------- Day tabs: the chosen day is shared by both weeks ----------

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

    // Each week has its own tab row; keyboard moves stay within one row.
    root.querySelectorAll(".ts-days").forEach(function (row) {
        tabList(Array.prototype.slice.call(row.querySelectorAll(".ts-day-tab")), selectDay);
    });

    // ---------- Week tabs ----------

    var weekTabs = Array.prototype.slice.call(root.querySelectorAll('.ui-tabs [role="tab"]'));

    function selectWeek(tab, moveFocus) {
        weekTabs.forEach(function (other) {
            var selected = other === tab;
            other.setAttribute("aria-selected", selected ? "true" : "false");
            other.tabIndex = selected ? 0 : -1;
            document.getElementById(other.getAttribute("aria-controls")).hidden = !selected;
        });
        if (moveFocus) tab.focus();

        // Keep the URL shareable, and the choice across a reload.
        var url = new URL(window.location.href);
        url.searchParams.set("week", tab.dataset.week);
        window.history.replaceState(null, "", url);
    }

    tabList(weekTabs, selectWeek);

    // ---------- Print ----------

    root.querySelectorAll("[data-ts-print]").forEach(function (button) {
        button.hidden = false;
        button.addEventListener("click", function () {
            window.print();
        });
    });
})();
