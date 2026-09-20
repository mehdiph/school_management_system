(function () {
  "use strict";

  // ------------------------------------------------------------------
  // Class picker / refresh -- pure UI feedback. The class select and
  // the refresh button both cause a real page reload (this is a Django
  // template page, not an SPA); the skeleton is just shown right
  // before that navigation so the switch doesn't look instantaneous
  // then blank. When stage 2 swaps this for a real fetch(), the same
  // showLoading() call is the hook to keep using.
  // ------------------------------------------------------------------

  var classForm = document.getElementById("classForm");
  var classSelect = document.getElementById("classSelect");
  var refreshBtn = document.getElementById("refreshBtn");
  var skeleton = document.getElementById("attendanceSkeleton");
  var content = document.getElementById("attendanceContent");

  function showLoading() {
    if (skeleton) skeleton.hidden = false;
    if (content) content.hidden = true;
  }

  if (classSelect && classForm) {
    classSelect.addEventListener("change", function () {
      showLoading();
      classForm.submit();
    });
  }

  if (refreshBtn) {
    refreshBtn.addEventListener("click", function () {
      showLoading();
      window.location.reload();
    });
  }

  // ------------------------------------------------------------------
  // Status filter + search -- purely client-side visibility toggling
  // over rows/cards already rendered by the server. No attendance data
  // is computed or re-derived here.
  // ------------------------------------------------------------------

  var searchInput = document.getElementById("studentSearch");
  var statusPills = document.querySelectorAll(".status-pill");
  var rows = document.querySelectorAll(".attendance-row");
  var cards = document.querySelectorAll(".attendance-card");
  var noResults = document.getElementById("noFilterResults");

  // The server already rendered the pill matching ?status= as active
  // (so a reload / shared link keeps its filter); start from that
  // instead of always defaulting to "all".
  var initiallyActivePill = document.querySelector(".status-pill.is-active");
  var activeStatus = initiallyActivePill
    ? initiallyActivePill.getAttribute("data-status-filter")
    : "all";

  function rowMatches(el, query) {
    var status = el.getAttribute("data-status");
    var name = el.getAttribute("data-name") || "";
    var statusOk = activeStatus === "all" || status === activeStatus;
    var searchOk = query === "" || name.indexOf(query) !== -1;
    return statusOk && searchOk;
  }

  function applyFilters() {
    var query = searchInput ? searchInput.value.trim() : "";
    var visibleCount = 0;

    for (var i = 0; i < rows.length; i++) {
      var visible = rowMatches(rows[i], query);
      rows[i].classList.toggle("is-filtered-out", !visible);
      if (visible) visibleCount++;
    }

    for (var j = 0; j < cards.length; j++) {
      cards[j].classList.toggle("is-filtered-out", !rowMatches(cards[j], query));
    }

    if (noResults) {
      noResults.hidden = visibleCount !== 0;
    }
  }

  if (searchInput) {
    searchInput.addEventListener("input", applyFilters);
  }

  // Server-rendered search value / active status pill (from ?search=
  // / ?status=) need one pass on load to actually hide/show rows.
  if (rows.length || cards.length) {
    applyFilters();
  }

  for (var p = 0; p < statusPills.length; p++) {
    statusPills[p].addEventListener("click", function (event) {
      for (var k = 0; k < statusPills.length; k++) {
        statusPills[k].classList.remove("is-active");
      }
      event.currentTarget.classList.add("is-active");
      activeStatus = event.currentTarget.getAttribute("data-status-filter");
      applyFilters();
    });
  }

  // ------------------------------------------------------------------
  // Follow-up modal -- UI only, no call/log action is actually
  // performed. Every field is filled from the triggering button's
  // data-* attributes, which the template already renders with the
  // same values as the row itself.
  // ------------------------------------------------------------------

  var overlay = document.getElementById("followupOverlay");
  var closeBtn = document.getElementById("followupClose");
  var closeFooterBtn = document.getElementById("followupCloseFooter");
  var callBtn = document.getElementById("followupCallBtn");

  var fields = {
    name: document.getElementById("followupName"),
    klass: document.getElementById("followupClass"),
    status: document.getElementById("followupStatus"),
    date: document.getElementById("followupDate"),
    time: document.getElementById("followupTime"),
    phone: document.getElementById("followupPhone")
  };

  function setField(field, value) {
    if (field) field.textContent = value || "—";
  }

  function openModal(trigger) {
    if (!overlay) return;

    setField(fields.name, trigger.getAttribute("data-name"));
    setField(fields.klass, trigger.getAttribute("data-class"));
    setField(fields.status, trigger.getAttribute("data-status"));
    setField(fields.date, trigger.getAttribute("data-date"));
    setField(fields.time, trigger.getAttribute("data-time"));

    var phone = trigger.getAttribute("data-phone") || "";
    setField(fields.phone, phone);

    if (callBtn) {
      callBtn.hidden = !phone;
      if (phone) callBtn.href = "tel:" + phone;
    }

    overlay.hidden = false;
    document.body.style.overflow = "hidden";
    closeBtn && closeBtn.focus();
  }

  function closeModal() {
    if (!overlay) return;
    overlay.hidden = true;
    document.body.style.overflow = "";
  }

  var triggers = document.querySelectorAll("[data-followup-trigger]");
  for (var t = 0; t < triggers.length; t++) {
    triggers[t].addEventListener("click", function (event) {
      openModal(event.currentTarget);
    });
  }

  if (closeBtn) closeBtn.addEventListener("click", closeModal);
  if (closeFooterBtn) closeFooterBtn.addEventListener("click", closeModal);

  if (overlay) {
    overlay.addEventListener("click", function (event) {
      if (event.target === overlay) closeModal();
    });
  }

  document.addEventListener("keydown", function (event) {
    if (event.key === "Escape" && overlay && !overlay.hidden) {
      closeModal();
    }
  });
})();
