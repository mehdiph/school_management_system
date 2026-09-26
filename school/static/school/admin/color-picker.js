/*
 * Admin colour picker (school.widgets.ColorPickerWidget): keeps the
 * colour input, hex field, presets and preview in sync. The text colour
 * of the preview uses the same WCAG rule as school.colors.readable_text_color.
 */
(function () {
  "use strict";

  var HEX = /^#[0-9a-f]{6}$/i;
  var DARK = "#1f2937";
  var LIGHT = "#ffffff";

  function luminance(hex) {
    return [1, 3, 5].map(function (i) {
      var c = parseInt(hex.substr(i, 2), 16) / 255;
      return c <= 0.04045 ? c / 12.92 : Math.pow((c + 0.055) / 1.055, 2.4);
    }).reduce(function (sum, c, i) { return sum + c * [0.2126, 0.7152, 0.0722][i]; }, 0);
  }

  function contrast(a, b) {
    var la = luminance(a), lb = luminance(b);
    return (Math.max(la, lb) + 0.05) / (Math.min(la, lb) + 0.05);
  }

  function readable(hex) {
    return contrast(hex, DARK) >= contrast(hex, LIGHT) ? DARK : LIGHT;
  }

  function init(picker) {
    var color = picker.querySelector('input[type="color"]');
    var hex = picker.querySelector(".color-picker__hex");
    var preview = picker.querySelector(".color-picker__preview");
    var presets = picker.querySelectorAll(".color-picker__preset");

    function apply(value) {
      value = value.toLowerCase();
      color.value = value;
      if (document.activeElement !== hex) hex.value = value;
      preview.style.setProperty("--subject-color", value);
      preview.style.setProperty("--subject-on", readable(value));
      presets.forEach(function (preset) {
        preset.setAttribute("aria-pressed", preset.dataset.color === value ? "true" : "false");
      });
    }

    color.addEventListener("input", function () { apply(color.value); });
    hex.addEventListener("input", function () {
      if (HEX.test(hex.value)) apply(hex.value);
    });
    hex.addEventListener("blur", function () { hex.value = color.value; });
    presets.forEach(function (preset) {
      preset.addEventListener("click", function () { apply(preset.dataset.color); });
    });

    apply(color.value);
  }

  document.addEventListener("DOMContentLoaded", function () {
    document.querySelectorAll("[data-color-picker]").forEach(init);
  });
})();
