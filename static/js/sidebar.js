(function () {
  "use strict";

  var sidebar = document.getElementById("appSidebar");
  var overlay = document.getElementById("sidebarOverlay");
  var mobileOpenBtn = document.getElementById("openSidebarBtn");
  var closeBtn = document.getElementById("closeSidebarBtn");
  var desktopOpenBtn = document.getElementById("desktopOpenSidebarBtn");

  if (!sidebar || !overlay || !mobileOpenBtn || !closeBtn || !desktopOpenBtn) return;

  // Desktop and mobile behave differently on purpose (see sidebar.css):
  // desktop collapses the sidebar out of the flex layout, mobile slides
  // it on/off canvas over an overlay. 768px matches the breakpoint
  // sidebar.css already uses everywhere else.
  var desktopQuery = window.matchMedia("(min-width: 769px)");

  function setSidebarInert(isHidden) {
    sidebar.setAttribute("aria-hidden", isHidden ? "true" : "false");
    // Progressive enhancement: keeps a visually-collapsed/off-canvas
    // sidebar out of the tab order and the accessibility tree in
    // browsers that support it; harmless no-op otherwise.
    if ("inert" in sidebar) {
      sidebar.inert = isHidden;
    }
  }

  // ------------------------------------------------------------------
  // Mobile: off-canvas drawer + overlay
  // ------------------------------------------------------------------

  function openMobile() {
    sidebar.classList.add("is-open");
    overlay.hidden = false;
    // allow the browser to paint hidden=false before animating opacity
    requestAnimationFrame(function () {
      overlay.classList.add("is-visible");
    });
    mobileOpenBtn.setAttribute("aria-expanded", "true");
    document.body.style.overflow = "hidden";
    setSidebarInert(false);
    closeBtn.focus();
  }

  function closeMobile() {
    sidebar.classList.remove("is-open");
    overlay.classList.remove("is-visible");
    mobileOpenBtn.setAttribute("aria-expanded", "false");
    document.body.style.overflow = "";
    setSidebarInert(true);
    mobileOpenBtn.focus();
    // wait for the closing transition before hiding the overlay
    window.setTimeout(function () {
      if (!sidebar.classList.contains("is-open")) {
        overlay.hidden = true;
      }
    }, 250);
  }

  // ------------------------------------------------------------------
  // Desktop: collapse in/out of the layout (no overlay, no scroll lock
  // -- main content is never covered, just resized)
  // ------------------------------------------------------------------

  function collapseDesktop() {
    sidebar.classList.add("is-collapsed");
    desktopOpenBtn.setAttribute("aria-expanded", "false");
    setSidebarInert(true);
    desktopOpenBtn.focus();
  }

  function expandDesktop() {
    sidebar.classList.remove("is-collapsed");
    desktopOpenBtn.setAttribute("aria-expanded", "true");
    setSidebarInert(false);
    closeBtn.focus();
  }

  // ------------------------------------------------------------------
  // Shared entry points -- the same close/open buttons/keys route to
  // whichever behavior matches the current breakpoint.
  // ------------------------------------------------------------------

  function openSidebar() {
    if (desktopQuery.matches) {
      expandDesktop();
    } else {
      openMobile();
    }
  }

  function closeSidebar() {
    if (desktopQuery.matches) {
      collapseDesktop();
    } else {
      closeMobile();
    }
  }

  mobileOpenBtn.addEventListener("click", openSidebar);
  desktopOpenBtn.addEventListener("click", openSidebar);
  closeBtn.addEventListener("click", closeSidebar);
  overlay.addEventListener("click", closeMobile);

  document.addEventListener("keydown", function (event) {
    if (event.key !== "Escape") return;
    // Escape only closes the mobile off-canvas drawer (a transient
    // overlay); the desktop collapsed state is a persistent layout
    // choice, not something Escape is expected to undo.
    if (!desktopQuery.matches && sidebar.classList.contains("is-open")) {
      closeMobile();
    }
  });

  // Crossing the breakpoint while open/collapsed shouldn't leave the
  // sidebar in a state that only makes sense on the breakpoint the
  // user left -- e.g. a drawer left open on mobile must not linger as
  // "open" (covering nothing, overlay gone) once the layout becomes
  // desktop, and vice versa.
  function handleViewportChange(mediaQueryList) {
    if (mediaQueryList.matches) {
      sidebar.classList.remove("is-open");
      overlay.classList.remove("is-visible");
      overlay.hidden = true;
      document.body.style.overflow = "";
      mobileOpenBtn.setAttribute("aria-expanded", "false");
    } else {
      sidebar.classList.remove("is-collapsed");
      desktopOpenBtn.setAttribute("aria-expanded", "true");
    }
    setSidebarInert(false);
  }

  if (desktopQuery.addEventListener) {
    desktopQuery.addEventListener("change", handleViewportChange);
  } else if (desktopQuery.addListener) {
    // Safari < 14 fallback
    desktopQuery.addListener(handleViewportChange);
  }

  // Initial ARIA state matches whatever's actually visible on load
  // (sidebar starts expanded on desktop, closed on mobile).
  setSidebarInert(!desktopQuery.matches);
})();
