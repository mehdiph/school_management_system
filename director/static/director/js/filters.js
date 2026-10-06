/*
 * Director panel filter bar (director/partials/_filters.html).
 *
 * Progressive enhancement only: the form is a plain GET form and works
 * without this file.
 *  - Jalali date pickers on the date inputs (typing still works).
 *  - The picker writes Persian digits; they are turned into ASCII on
 *    submit so the shareable URL stays readable (the server reads both).
 */
(function () {
  "use strict";

  var $ = window.jQuery;
  var form = document.getElementById("directorFilters");
  if (!form) return;

  if ($ && $.fn.pDatepicker) {
    $(form).find("input[data-jalali-date]").each(function () {
      $(this).pDatepicker({
        // A rejected date keeps what was typed next to its error.
        initialValue:
          /^\d{4}-\d{2}-\d{2}$/.test(this.value) &&
          this.getAttribute("aria-invalid") !== "true",
        initialValueType: "persian",
        format: "YYYY-MM-DD",
        autoClose: true,
        responsive: true,
        calendar: { persian: { locale: "fa" } },
        toolbox: { calendarSwitch: { enabled: false } }
      });
    });
  }

  form.addEventListener("submit", function () {
    Array.prototype.forEach.call(form.querySelectorAll("input[data-jalali-date]"), function (input) {
      input.value = input.value.replace(/[۰-۹]/g, function (digit) {
        return String("۰۱۲۳۴۵۶۷۸۹".indexOf(digit));
      });
    });
  });
})();
