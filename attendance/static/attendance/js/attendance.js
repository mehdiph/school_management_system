/*
 * Attendance (attendance/attendance_management.html)
 *
 *  - live counters: present / absent / late / not recorded, in Persian
 *    digits, recomputed from the radios themselves (so they are right on
 *    first load, in edit mode, and after the browser restores the form)
 *  - «همه حاضر» (mark everyone present)
 *  - client-side search by name: only hides rows, the counts stay the same
 *  - per-student description: folded away while empty, opened by itself
 *    when a student is marked absent or late
 *  - no double submission ("در حال ثبت...")
 *  - warns before leaving the page with unsaved changes
 *
 * The form still posts plain radios / textareas; nothing here changes
 * what the server receives.
 */
(function () {
  "use strict";

  var form = document.getElementById("attendanceForm");
  var list = document.getElementById("attendanceList");
  if (!form || !list) return;

  var rows = Array.prototype.slice.call(list.querySelectorAll("[data-student]"));
  if (!rows.length) return;

  // statuses that usually need a word of explanation
  var NOTE_STATUSES = ["absent", "late"];
  var UNSET = "unset";

  var summary = document.getElementById("attendanceSummary");
  var progress = document.getElementById("presentRatio");
  var markAll = document.getElementById("markAllPresent");
  var search = document.getElementById("studentSearch");
  var noResults = document.getElementById("noResults");
  var submit = form.querySelector(".at-submit");

  function toPersianNumber(value) {
    return Number(value).toLocaleString("fa-IR");
  }

  function statusOf(row) {
    var checked = row.querySelector(".at-seg__input:checked");
    return checked ? checked.value : UNSET;
  }

  // ------------------------------------------------------------------
  // Counters
  // ------------------------------------------------------------------

  var countOutputs = summary ? Array.prototype.slice.call(summary.querySelectorAll("[data-count]")) : [];

  function recount() {
    var counts = {};

    rows.forEach(function (row) {
      var status = statusOf(row);
      counts[status] = (counts[status] || 0) + 1;
    });
    counts.total = rows.length;

    countOutputs.forEach(function (output) {
      var text = toPersianNumber(counts[output.dataset.count] || 0);
      // unchanged text is not rewritten, so the live region only speaks
      // when a number really changed
      if (output.textContent !== text) output.textContent = text;
    });

    // "not recorded" is only worth space on the bar when there are some
    var unsetWrap = summary && summary.querySelector('[data-count-wrap="' + UNSET + '"]');
    if (unsetWrap) unsetWrap.hidden = !counts[UNSET];

    if (progress) {
      progress.style.width = ((counts.present || 0) / rows.length) * 100 + "%";
    }
  }

  // ------------------------------------------------------------------
  // Per-student description
  // ------------------------------------------------------------------

  function noteOf(row) {
    var button = row.querySelector(".at-note-btn");
    var note = button && document.getElementById(button.getAttribute("aria-controls"));
    var input = note && note.querySelector("textarea");

    return input ? { button: button, note: note, input: input } : null;
  }

  function setNoteOpen(parts, open) {
    parts.note.hidden = !open;
    parts.button.setAttribute("aria-expanded", open ? "true" : "false");
  }

  function markHasNote(parts) {
    parts.button.classList.toggle("has-note", parts.input.value.trim() !== "");
  }

  // after a status change: open the note for absent / late, fold an
  // empty one away again when the student is back to present
  function followStatus(row) {
    var status = statusOf(row);
    var parts = noteOf(row);

    row.dataset.status = status;
    if (!parts) return;

    if (NOTE_STATUSES.indexOf(status) !== -1) {
      setNoteOpen(parts, true);
    } else if (parts.input.value.trim() === "" && document.activeElement !== parts.input) {
      setNoteOpen(parts, false);
    }
  }

  // ------------------------------------------------------------------
  // Unsaved changes
  // ------------------------------------------------------------------

  function snapshot() {
    var parts = [];

    Array.prototype.forEach.call(form.elements, function (element) {
      if (!element.name || element.name === "csrfmiddlewaretoken") return;

      if (element.type === "radio") {
        if (element.checked) parts.push(element.name + "=" + element.value);
      } else if (element.tagName === "TEXTAREA") {
        parts.push(element.name + "=" + element.value);
      }
    });

    return parts.join("&");
  }

  var savedState = snapshot();
  var isDirty = false;
  var isSubmitting = false;

  function updateDirty() {
    isDirty = snapshot() !== savedState;
  }

  window.addEventListener("beforeunload", function (event) {
    if (!isDirty || isSubmitting) return;

    event.preventDefault();
    event.returnValue = ""; // older browsers need a value to show the prompt
  });

  // ------------------------------------------------------------------
  // Events: one delegated listener per event type on the list
  // ------------------------------------------------------------------

  list.addEventListener("change", function (event) {
    var input = event.target;
    if (!input.classList || !input.classList.contains("at-seg__input")) return;

    followStatus(input.closest("[data-student]"));
    recount();
    updateDirty();
  });

  list.addEventListener("input", function (event) {
    if (event.target.tagName !== "TEXTAREA") return;

    var parts = noteOf(event.target.closest("[data-student]"));
    if (parts) markHasNote(parts);
    updateDirty();
  });

  list.addEventListener("click", function (event) {
    var button = event.target.closest(".at-note-btn");
    if (!button) return;

    var parts = noteOf(button.closest("[data-student]"));
    if (!parts) return;

    var open = parts.note.hidden;
    setNoteOpen(parts, open);
    if (open) parts.input.focus();
  });

  // ------------------------------------------------------------------
  // «همه حاضر»
  // ------------------------------------------------------------------

  if (markAll) {
    markAll.hidden = false;

    markAll.addEventListener("click", function () {
      var changing = rows.filter(function (row) {
        return statusOf(row) !== "present";
      });
      if (!changing.length) return;

      // absent / late marks the teacher already made are not wiped silently
      var marked = changing.filter(function (row) {
        return statusOf(row) !== UNSET;
      }).length;

      if (
        marked &&
        !window.confirm(
          "وضعیت " + toPersianNumber(marked) +
          " دانش‌آموز غایب یا دارای تاخیر به «حاضر» تغییر می‌کند. ادامه می‌دهید؟"
        )
      ) {
        return;
      }

      changing.forEach(function (row) {
        var present = row.querySelector('.at-seg__input[value="present"]');
        if (!present) return;

        present.checked = true; // setting .checked fires no change event
        followStatus(row);
      });

      recount();
      updateDirty();
    });
  }

  // ------------------------------------------------------------------
  // Search by name
  // ------------------------------------------------------------------

  // Arabic / Persian variants of the same letters, and ZWNJ, should not
  // make a name "not found"
  function normalize(text) {
    return String(text || "")
      .replace(/[‌‎‏]/g, "")
      .replace(/[يى]/g, "ی")
      .replace(/ك/g, "ک")
      .replace(/\s+/g, " ")
      .trim()
      .toLowerCase();
  }

  if (search) {
    var names = rows.map(function (row) {
      return normalize(row.dataset.name);
    });

    search.addEventListener("input", function () {
      var words = normalize(search.value).split(" ").filter(Boolean);
      var visible = 0;

      rows.forEach(function (row, index) {
        var match = words.every(function (word) {
          return names[index].indexOf(word) !== -1;
        });

        row.hidden = !match;
        if (match) visible += 1;
      });

      if (noResults) noResults.hidden = visible > 0;
    });

    // Enter in the search box must not submit the attendance
    search.addEventListener("keydown", function (event) {
      if (event.key === "Enter") event.preventDefault();
    });
  }

  // ------------------------------------------------------------------
  // Double submission
  // ------------------------------------------------------------------

  var idleHTML = submit ? submit.innerHTML : "";

  form.addEventListener("submit", function (event) {
    if (isSubmitting) {
      event.preventDefault();
      return;
    }

    isSubmitting = true;
    if (!submit) return;

    submit.disabled = true;
    submit.setAttribute("aria-busy", "true");
    submit.innerHTML =
      '<span class="at-spinner" aria-hidden="true"></span>' +
      '<span class="at-submit__label"></span>';
    submit.querySelector(".at-submit__label").textContent =
      submit.dataset.loadingText || "در حال ثبت...";
  });

  // back/forward cache: the page comes back exactly as it was left, i.e.
  // with the button still disabled and the state not saved
  window.addEventListener("pageshow", function (event) {
    if (!event.persisted) return;

    isSubmitting = false;
    if (submit) {
      submit.disabled = false;
      submit.removeAttribute("aria-busy");
      submit.innerHTML = idleHTML;
    }
    recount();
    updateDirty();
  });

  // ------------------------------------------------------------------
  // Initial state
  // ------------------------------------------------------------------

  rows.forEach(function (row) {
    var parts = noteOf(row);

    row.dataset.status = statusOf(row);
    if (!parts) return;

    // without JS every description stays visible; with it, only the ones
    // with text or for absent / late students
    parts.button.hidden = false;
    setNoteOpen(
      parts,
      parts.input.value.trim() !== "" || NOTE_STATUSES.indexOf(statusOf(row)) !== -1
    );
    markHasNote(parts);
  });

  recount();

  // shown only now, so the first fill is not read out as a change
  if (summary) summary.hidden = false;
  if (progress) progress.parentNode.hidden = false;
})();
