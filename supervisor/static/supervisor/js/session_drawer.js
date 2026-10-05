/*
 * Supervisor panel: loading server-rendered fragments, and the session
 * detail drawer (supervisor/partials/_session_drawer.html).
 *
 * Everything here is progressive enhancement. Each enhanced link is a
 * normal link to a full page; with JS, the same URL is fetched with
 * ?partial=1 (the view then renders only the fragment) and shown in place.
 *
 *  - SupervisorPartials.load(container, url): loading indicator, then the
 *    fragment, or an error message with a retry button.
 *  - a[data-session-detail] opens the session in the drawer (from the
 *    left in RTL). Esc / the backdrop / the close button close it, focus
 *    stays inside while it is open and returns to the link afterwards.
 */
(function () {
  "use strict";

  if (!window.fetch) return;

  function fromTemplate(id) {
    var template = document.getElementById(id);
    return template ? template.content.cloneNode(true) : document.createTextNode("");
  }

  function partialUrl(href) {
    var url = new URL(href, window.location.href);
    url.searchParams.set("partial", "1");
    return url.toString();
  }

  function isPlainClick(event) {
    return event.button === 0 && !event.metaKey && !event.ctrlKey && !event.shiftKey && !event.altKey;
  }

  /*
   * Resolves to true once the fragment is in, false on failure. A newer
   * load() into the same container wins over an older, slower one.
   */
  function load(container, url) {
    var token = {};
    container.svToken = token;
    container.setAttribute("aria-busy", "true");
    container.replaceChildren(fromTemplate("svLoadingTemplate"));

    return fetch(partialUrl(url), {
      credentials: "same-origin",
      headers: { Accept: "text/html" }
    })
      .then(function (response) {
        if (response.redirected) {
          // Logged out meanwhile: the login page answered instead. Go
          // to the full page, which sends the user through login.
          window.location.href = url;
          throw new Error("redirected");
        }
        if (!response.ok) throw new Error("HTTP " + response.status);
        return response.text();
      })
      .then(function (html) {
        if (container.svToken !== token) return false;
        container.innerHTML = html;
        container.removeAttribute("aria-busy");
        return true;
      })
      .catch(function () {
        if (container.svToken !== token) return false;
        var error = fromTemplate("svErrorTemplate");
        var retry = error.querySelector("[data-retry]");
        container.replaceChildren(error);
        container.removeAttribute("aria-busy");
        if (retry) {
          retry.addEventListener("click", function () {
            load(container, url).then(function (ok) {
              if (container.svOnLoad) container.svOnLoad(ok);
            });
          });
        }
        return false;
      });
  }

  window.SupervisorPartials = { load: load, isPlainClick: isPlainClick };

  // ------------------------------------------------------------------
  // Drawer
  // ------------------------------------------------------------------

  var drawer = document.getElementById("sessionDrawer");
  if (!drawer) return;

  var panel = drawer.querySelector(".sv-drawer__panel");
  var body = drawer.querySelector("[data-drawer-body]");
  var fullPageLink = drawer.querySelector("[data-drawer-full-page]");
  var trigger = null;

  var FOCUSABLE = 'a[href], button:not([disabled]), input:not([disabled]), select, textarea, [tabindex]:not([tabindex="-1"])';

  function openDrawer(link) {
    trigger = link;
    fullPageLink.href = link.href;
    drawer.hidden = false;
    document.body.classList.add("sv-drawer-open");
    panel.focus();
    load(body, link.href);
  }

  function closeDrawer() {
    drawer.hidden = true;
    body.svToken = null;
    body.replaceChildren();
    document.body.classList.remove("sv-drawer-open");
    if (trigger && document.body.contains(trigger)) trigger.focus();
    trigger = null;
  }

  function trapFocus(event) {
    var items = Array.prototype.filter.call(panel.querySelectorAll(FOCUSABLE), function (element) {
      return element.offsetParent !== null;
    });
    if (!items.length) {
      event.preventDefault();
      panel.focus();
      return;
    }

    var first = items[0];
    var last = items[items.length - 1];
    var active = document.activeElement;

    if (event.shiftKey && (active === first || active === panel)) {
      event.preventDefault();
      last.focus();
    } else if (!event.shiftKey && active === last) {
      event.preventDefault();
      first.focus();
    }
  }

  document.addEventListener("click", function (event) {
    var link = event.target.closest("a[data-session-detail]");
    if (!link || event.defaultPrevented || !isPlainClick(event)) return;
    event.preventDefault();
    openDrawer(link);
  });

  drawer.addEventListener("click", function (event) {
    if (event.target.closest("[data-drawer-close]")) closeDrawer();
  });

  document.addEventListener("keydown", function (event) {
    if (drawer.hidden) return;
    if (event.key === "Escape") {
      event.preventDefault();
      closeDrawer();
    } else if (event.key === "Tab") {
      trapFocus(event);
    }
  });
})();
