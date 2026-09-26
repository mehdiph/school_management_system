/*
 * Weekly schedule: week tabs + day chips.
 *
 * Both weeks are already in the page (server-rendered from the same
 * data), so switching is only showing/hiding. Without JS the week tabs
 * are plain ?week=N links and every day is listed.
 */
(function () {
  "use strict";

  var root = document.querySelector("[data-ws]");
  if (!root) return;

  var tabs = Array.prototype.slice.call(root.querySelectorAll('[role="tab"]'));
  var isRtl = getComputedStyle(root).direction === "rtl";

  root.classList.add("ws--js");

  // ---------- Week tabs (WAI-ARIA tabs pattern, manual roving tabindex) ----------

  function selectWeek(tab, moveFocus) {
    tabs.forEach(function (other) {
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

    revealSelectedChip();
  }

  tabs.forEach(function (tab, index) {
    tab.addEventListener("click", function (event) {
      event.preventDefault();
      selectWeek(tab, false);
    });

    tab.addEventListener("keydown", function (event) {
      var next = { ArrowLeft: isRtl ? 1 : -1, ArrowRight: isRtl ? -1 : 1 }[event.key];
      var target = null;

      if (next) target = tabs[(index + next + tabs.length) % tabs.length];
      else if (event.key === "Home") target = tabs[0];
      else if (event.key === "End") target = tabs[tabs.length - 1];
      else if (event.key === " ") target = tab;  // links only activate on Enter by default

      if (target) {
        event.preventDefault();
        selectWeek(target, true);
      }
    });
  });

  // ---------- Day chips (narrow layout) ----------
  // The selected day is shared by both weeks, so switching weeks keeps it.

  function selectDay(day) {
    root.querySelectorAll(".ws-chip").forEach(function (chip) {
      chip.setAttribute("aria-pressed", chip.dataset.day === day ? "true" : "false");
    });
    root.querySelectorAll(".ws-day").forEach(function (section) {
      section.classList.toggle("is-selected", section.dataset.day === day);
    });
    revealSelectedChip();
  }

  function revealSelectedChip() {
    var panel = root.querySelector('[role="tabpanel"]:not([hidden])');
    var chip = panel && panel.querySelector('.ws-chip[aria-pressed="true"]');
    if (chip) chip.scrollIntoView({ block: "nearest", inline: "center" });
  }

  root.querySelectorAll(".ws-chip").forEach(function (chip) {
    chip.addEventListener("click", function () {
      selectDay(chip.dataset.day);
    });
  });

  revealSelectedChip();
})();
