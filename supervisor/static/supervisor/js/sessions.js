/*
 * Training sessions page (supervisor/sessions.html).
 *
 *  - "جلسات" in a summary row expands the row: the class subject's
 *    timeline is fetched once (as an HTML fragment, see
 *    session_drawer.js) into the hidden row under it. Without JS the
 *    button is a link to the full timeline page.
 *  - Jalali date pickers on the date filters (typing still works).
 *  - Changing the academic year re-submits the filters right away: the
 *    teacher / subject / class options belong to the selected year.
 */
(function () {
  "use strict";

  // ------------------------------------------------------------------
  // Expandable rows
  // ------------------------------------------------------------------

  var table = document.getElementById("summaryTable");
  var partials = window.SupervisorPartials;

  if (table && partials) {
    table.addEventListener("click", function (event) {
      var toggle = event.target.closest("a[data-timeline-toggle]");
      if (!toggle || !partials.isPlainClick(event)) return;

      var detailRow = document.getElementById(toggle.getAttribute("aria-controls"));
      var host = detailRow && detailRow.querySelector("[data-timeline-host]");
      if (!host) return;

      event.preventDefault();

      var expand = toggle.getAttribute("aria-expanded") !== "true";
      toggle.setAttribute("aria-expanded", String(expand));
      toggle.closest("tr").classList.toggle("is-expanded", expand);
      detailRow.hidden = !expand;

      if (expand && host.dataset.loaded !== "true") {
        host.svOnLoad = function (ok) {
          if (ok) host.dataset.loaded = "true";
        };
        partials.load(host, toggle.href).then(host.svOnLoad);
      }
    });
  }

  // ------------------------------------------------------------------
  // Jalali date pickers (the project's persian-datepicker, as on the
  // teacher's session form)
  // ------------------------------------------------------------------

  var $ = window.jQuery;

  if ($ && $.fn.pDatepicker) {
    $("input[data-jalali-date]").each(function () {
      $(this).pDatepicker({
        // An empty filter must stay empty (not default to today), and a
        // rejected one must keep what was typed next to its error -- the
        // picker would "correct" 1405-13-40 into some other date.
        initialValue:
          /^\d{4}-\d{2}-\d{2}$/.test(this.value) &&
          this.getAttribute("aria-invalid") !== "true",
        initialValueType: "persian",
        format: "YYYY-MM-DD",
        autoClose: true,
        responsive: true,
        calendar: {
          persian: {
            locale: "fa"
          }
        },
        toolbox: {
          calendarSwitch: {
            enabled: false
          }
        }
      });
    });
  }

  // ------------------------------------------------------------------
  // Academic year: re-submit, without the previous year's choices
  // ------------------------------------------------------------------

  var form = document.getElementById("sessionFilters");
  var year = form && form.querySelector('select[name="academic_year"]');

  // The picker writes Persian digits; the server reads both, but ASCII
  // keeps the (shareable) URL readable.
  if (form) {
    form.addEventListener("submit", function () {
      Array.prototype.forEach.call(form.querySelectorAll("input[data-jalali-date]"), function (input) {
        input.value = input.value.replace(/[۰-۹]/g, function (digit) {
          return String("۰۱۲۳۴۵۶۷۸۹".indexOf(digit));
        });
      });
    });
  }

  if (year) {
    year.addEventListener("change", function () {
      ["teacher", "subject", "school_class"].forEach(function (name) {
        var select = form.querySelector('select[name="' + name + '"]');
        if (select) select.value = "";
      });
      form.submit();
    });
  }
})();
