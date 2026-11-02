/*
 * Enhancements only (ADR-015): every page works without this. Countdowns tick
 * from seconds sent by the server, not the phone's clock, which is often wrong;
 * when a card changes state the fragment is fetched again with ?partial=1.
 */
(function () {
  "use strict";

  var DIGITS = "۰۱۲۳۴۵۶۷۸۹";

  function fa(text) {
    return String(text).replace(/\d/g, function (d) { return DIGITS[d]; });
  }

  // Same wording as online_classes.selectors.countdown_text.
  function countdownText(seconds) {
    seconds = Math.max(Math.floor(seconds), 0);
    var days = Math.floor(seconds / 86400);
    var hours = Math.floor((seconds % 86400) / 3600);
    var minutes = Math.floor((seconds % 3600) / 60);
    var secs = seconds % 60;
    var parts;
    if (days) {
      parts = [days + " روز"].concat(hours ? [hours + " ساعت"] : []);
    } else if (hours) {
      parts = [hours + " ساعت"].concat(minutes ? [minutes + " دقیقه"] : []);
    } else if (minutes) {
      parts = [minutes + " دقیقه"].concat(secs ? [secs + " ثانیه"] : []);
    } else {
      parts = [secs + " ثانیه"];
    }
    return fa(parts.join(" و ") + " دیگر");
  }

  function setupCountdowns(root) {
    root.querySelectorAll("[data-countdown]").forEach(function (element) {
      element.onlineEnd = performance.now() + Number(element.dataset.countdown) * 1000;
    });
  }

  function tick() {
    document.querySelectorAll("[data-countdown]").forEach(function (element) {
      if (element.onlineEnd === undefined) { return; }
      var left = (element.onlineEnd - performance.now()) / 1000;
      element.textContent = left > 0 ? countdownText(left) : "شروع شد";
    });
  }

  function setupCopy(root) {
    if (!navigator.clipboard) { return; }
    root.querySelectorAll("[data-copy]").forEach(function (button) {
      button.hidden = false;
      button.addEventListener("click", function () {
        navigator.clipboard.writeText(button.dataset.copy).then(function () {
          button.textContent = "کپی شد";
          setTimeout(function () { button.textContent = "کپی"; }, 2000);
        });
      });
    });
  }

  function partialUrl(holder) {
    var url = new URL(location.href);
    url.searchParams.set("partial", "1");
    return url.toString();
  }

  function scheduleRefresh(holder) {
    clearTimeout(holder.onlineTimer);
    var marked = holder.querySelector("[data-refresh-seconds]");
    var seconds = marked ? Number(marked.dataset.refreshSeconds) : 0;
    // setTimeout overflows above about 24 days; a page isn't open that long.
    if (!seconds || seconds > 86400 * 7) { return; }
    holder.onlineTimer = setTimeout(function () {
      fetch(partialUrl(holder), { credentials: "same-origin" })
        .then(function (response) {
          if (!response.ok) { throw new Error(response.status); }
          return response.text();
        })
        .then(function (html) {
          holder.innerHTML = html;
          setupCountdowns(holder);
          setupCopy(holder);
          scheduleRefresh(holder);
        })
        .catch(function () { /* the visible refresh of the page still works */ });
    }, seconds * 1000);
  }

  function setupDismiss() {
    document.querySelectorAll("form[data-dismiss]").forEach(function (form) {
      form.addEventListener("submit", function (event) {
        event.preventDefault();
        fetch(form.action + "?partial=1", {
          method: "POST",
          credentials: "same-origin",
          body: new FormData(form)
        }).then(function (response) {
          if (!response.ok) { throw new Error(response.status); }
          var banner = form.closest("[data-banner]");
          if (banner) { banner.remove(); }
        }).catch(function () {
          form.submit();
        });
      });
    });
  }

  setupCountdowns(document);
  setupCopy(document);
  setupDismiss();
  document.querySelectorAll("[data-online-refresh]").forEach(scheduleRefresh);
  setInterval(tick, 1000);
})();
