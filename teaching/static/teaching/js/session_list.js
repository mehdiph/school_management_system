/*
 * Session list (teaching/session_list.html): "بیشتر" toggle on cards.
 *
 * Cards start fully expanded in the HTML (so nothing is lost without JS).
 * Here each card is collapsed -- long text clamped, activity/notes hidden
 * -- and the toggle is shown only when that actually hides something.
 */
(function () {
  "use strict";

  var cards = document.querySelectorAll(".sl-card[data-collapsible]");

  Array.prototype.forEach.call(cards, function (card) {
    var button = card.querySelector(".sl-more");
    var details = card.querySelector(".sl-details");
    if (!button || !details) return;

    card.classList.add("is-collapsed");

    var isCut = Array.prototype.some.call(details.querySelectorAll(".sl-clamp"), function (text) {
      return text.scrollHeight > text.clientHeight + 1;
    });
    var hasExtra = details.querySelector(".sl-extra") !== null;

    if (!isCut && !hasExtra) {
      card.classList.remove("is-collapsed");
      return;
    }

    var label = button.querySelector("span");
    button.hidden = false;

    button.addEventListener("click", function () {
      var expand = button.getAttribute("aria-expanded") !== "true";

      button.setAttribute("aria-expanded", String(expand));
      card.classList.toggle("is-collapsed", !expand);
      label.textContent = expand ? "بستن" : "بیشتر";
    });
  });
})();
