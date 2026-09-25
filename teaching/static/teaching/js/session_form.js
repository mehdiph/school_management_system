/*
 * Session form (teaching/session_form.html)
 *
 *  - textareas grow with their content
 *  - after a failed submit: scroll to and focus the first invalid field
 *  - the read-only session number follows the class-subject dropdown
 *  - Persian date picker, touch friendly
 *  - Enter in a one-line field moves on instead of submitting
 *  - no double submission ("در حال ثبت...")
 */
(function () {
  "use strict";

  var form = document.getElementById("sessionForm");
  if (!form) return;

  var reduceMotion = window.matchMedia("(prefers-reduced-motion: reduce)").matches;

  function toPersianDigits(value) {
    return String(value).replace(/\d/g, function (digit) {
      return "۰۱۲۳۴۵۶۷۸۹"[digit];
    });
  }

  function scrollToField(element) {
    element.scrollIntoView({ block: "center", behavior: reduceMotion ? "auto" : "smooth" });
  }

  // ------------------------------------------------------------------
  // Auto-growing textareas
  // ------------------------------------------------------------------

  function autogrow(textarea) {
    // collapsing to "auto" for a moment can make the page jump; keep
    // the scroll position where it was
    var scrollY = window.scrollY;
    var borders = textarea.offsetHeight - textarea.clientHeight;

    textarea.style.height = "auto";
    textarea.style.height = textarea.scrollHeight + borders + "px";

    if (window.scrollY !== scrollY) window.scrollTo(0, scrollY);
  }

  var textareas = Array.prototype.slice.call(form.querySelectorAll("textarea"));

  textareas.forEach(function (textarea) {
    textarea.classList.add("is-autogrow");
    autogrow(textarea);
    textarea.addEventListener("input", function () {
      autogrow(textarea);
    });
  });

  // line wrapping (and so the needed height) changes with the width
  var resizeFrame = null;
  window.addEventListener("resize", function () {
    if (resizeFrame) return;
    resizeFrame = window.requestAnimationFrame(function () {
      resizeFrame = null;
      textareas.forEach(autogrow);
    });
  });

  // ------------------------------------------------------------------
  // Errors. Runs before the date picker is attached: the picker opens on
  // focus, and focusing the date field on page load should not pop it.
  // ------------------------------------------------------------------

  var summary = document.getElementById("errorSummary");
  var firstInvalid = form.querySelector('[aria-invalid="true"]');
  var errorTarget = firstInvalid || summary;

  if (errorTarget) {
    errorTarget.focus({ preventScroll: true });
    scrollToField(errorTarget);
  }

  // links in the summary: focus the field itself, not just jump to it
  if (summary) {
    summary.addEventListener("click", function (event) {
      var link = event.target.closest("a[href^='#']");
      if (!link) return;

      var field = document.getElementById(link.getAttribute("href").slice(1));
      if (!field) return;

      event.preventDefault();
      field.focus({ preventScroll: true });
      scrollToField(field);
    });
  }

  // ------------------------------------------------------------------
  // Session number preview (new sessions only; the server sends
  // {class_subject_id: next number})
  // ------------------------------------------------------------------

  var numbersScript = document.getElementById("nextSessionNumbers");
  var classSubject = form.querySelector('select[name="class_subject"]');
  var sessionNumber = document.getElementById("sessionNumber");

  if (numbersScript && classSubject && sessionNumber) {
    var nextNumbers = JSON.parse(numbersScript.textContent);

    classSubject.addEventListener("change", function () {
      var number = nextNumbers[classSubject.value];
      sessionNumber.textContent = number ? "جلسه شماره " + toPersianDigits(number) : "—";
    });
  }

  // ------------------------------------------------------------------
  // Persian date picker
  // ------------------------------------------------------------------

  var $ = window.jQuery;
  var $date = $ ? $('input[name="date"]', form) : null;

  if ($date && $date.length && $.fn.pDatepicker) {
    // On touch screens the calendar is the input method: no on-screen
    // keyboard on top of it. (Without JS the field stays typeable.)
    if (window.matchMedia("(pointer: coarse)").matches) {
      $date.attr({ readonly: "readonly", inputmode: "none" });
    }

    $date.pDatepicker({
      initialValue: true,
      // the field holds a Jalali date ("1405-07-03"); the default,
      // 'gregorian', misread it and rewrote the value on the edit page
      // and after a failed submit
      initialValueType: "persian",
      format: "YYYY-MM-DD",
      autoClose: true,
      // full-screen picker with large touch targets on phones
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
  }

  // ------------------------------------------------------------------
  // Enter in a one-line field: go to the next field. (A phone keyboard's
  // "next" key would otherwise submit a half-filled form.)
  // ------------------------------------------------------------------

  form.addEventListener("keydown", function (event) {
    if (event.key !== "Enter" || event.isComposing) return;
    if (event.target.tagName !== "INPUT") return;

    event.preventDefault();

    var fields = Array.prototype.filter.call(form.elements, function (element) {
      return element.type !== "hidden" && !element.disabled && element.tagName !== "FIELDSET";
    });
    var next = fields[fields.indexOf(event.target) + 1];

    if (next) next.focus();
  });

  // ------------------------------------------------------------------
  // Double submission
  // ------------------------------------------------------------------

  var submit = form.querySelector(".sf-submit");

  if (submit) {
    var idleHTML = submit.innerHTML;

    form.addEventListener("submit", function (event) {
      if (form.dataset.submitting === "true") {
        event.preventDefault();
        return;
      }

      form.dataset.submitting = "true";
      submit.disabled = true;
      submit.setAttribute("aria-busy", "true");
      submit.innerHTML =
        '<span class="sf-spinner" aria-hidden="true"></span>' +
        '<span class="sf-submit__label"></span>';
      submit.querySelector(".sf-submit__label").textContent =
        submit.dataset.loadingText || "در حال ثبت...";
    });

    // back/forward cache: the page comes back exactly as it was left,
    // i.e. with the button still disabled
    window.addEventListener("pageshow", function (event) {
      if (!event.persisted) return;

      form.dataset.submitting = "false";
      submit.disabled = false;
      submit.removeAttribute("aria-busy");
      submit.innerHTML = idleHTML;
    });
  }
})();
