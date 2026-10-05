/*
 * Supervised teachers page (supervisor/teachers.html).
 *
 * The filters are a plain GET form with a submit button; this only
 * submits it for the user: shortly after typing stops in the search box,
 * and when a select changes. After such a reload the caret is put back
 * at the end of the search box, so typing can go on.
 */
(function () {
  "use strict";

  var form = document.getElementById("teacherFilters");
  if (!form) return;

  var SEARCH_DELAY = 500;
  var FOCUS_KEY = "svTeacherSearchFocus";

  var search = form.querySelector("[data-debounced-search]");
  var timer = null;

  function submit(fromSearch) {
    try {
      if (fromSearch) window.sessionStorage.setItem(FOCUS_KEY, "1");
    } catch (error) {
      // storage unavailable: only the caret position is lost
    }
    form.submit();
  }

  if (search) {
    var submitted = search.value.trim();

    search.addEventListener("input", function () {
      window.clearTimeout(timer);
      timer = window.setTimeout(function () {
        if (search.value.trim() !== submitted) submit(true);
      }, SEARCH_DELAY);
    });

    var refocus = false;
    try {
      refocus = window.sessionStorage.getItem(FOCUS_KEY) === "1";
      window.sessionStorage.removeItem(FOCUS_KEY);
    } catch (error) {
      refocus = false;
    }

    if (refocus) {
      search.focus();
      var end = search.value.length;
      try {
        search.setSelectionRange(end, end);
      } catch (error) {
        // type=search may not support selection ranges in old browsers
      }
    }
  }

  Array.prototype.forEach.call(form.querySelectorAll("select"), function (select) {
    select.addEventListener("change", function () {
      window.clearTimeout(timer);
      // subjects are per academic year
      var subject = form.querySelector('select[name="subject"]');
      if (select.name === "academic_year" && subject) subject.value = "";
      submit(false);
    });
  });
})();
