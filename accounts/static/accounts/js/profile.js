/*
 * Teacher profile: tabs, avatar preview, password show/hide, checklist and
 * strength meter. Every check here is a hint only; the server validates.
 */
(function () {
    "use strict";

    var root = document.querySelector("[data-pf]");
    if (!root) return;

    // ---------- Tabs (links to ?tab=..., switched in place) ----------

    var tabs = Array.prototype.slice.call(root.querySelectorAll('.pf-tabs [role="tab"]'));
    var isRtl = getComputedStyle(root).direction === "rtl";

    function selectTab(tab, moveFocus) {
        tabs.forEach(function (other) {
            var selected = other === tab;
            other.setAttribute("aria-selected", selected ? "true" : "false");
            other.tabIndex = selected ? 0 : -1;
            document.getElementById(other.getAttribute("aria-controls")).hidden = !selected;
        });
        if (moveFocus) tab.focus();
        var url = new URL(window.location.href);
        url.searchParams.set("tab", tab.dataset.tab);
        window.history.replaceState(null, "", url);
    }

    tabs.forEach(function (tab, index) {
        tab.addEventListener("click", function (event) {
            event.preventDefault();
            selectTab(tab, false);
        });
        tab.addEventListener("keydown", function (event) {
            var step = { ArrowLeft: isRtl ? 1 : -1, ArrowRight: isRtl ? -1 : 1 }[event.key];
            var target = null;
            if (step) target = tabs[(index + step + tabs.length) % tabs.length];
            else if (event.key === "Home") target = tabs[0];
            else if (event.key === "End") target = tabs[tabs.length - 1];
            else if (event.key === " ") target = tab;
            if (target) {
                event.preventDefault();
                selectTab(target, true);
            }
        });
    });

    // ---------- Avatar ----------

    var avatar = root.querySelector("[data-avatar]");
    if (avatar) {
        var input = avatar.querySelector("[data-avatar-input]");
        var remove = avatar.querySelector("[data-avatar-remove]");
        var preview = avatar.querySelector("[data-avatar-preview]");
        var newImage = avatar.querySelector("[data-avatar-new]");
        var status = avatar.querySelector("[data-avatar-status]");
        var clientError = avatar.querySelector("[data-avatar-error]");
        var maxBytes = parseInt(input.dataset.maxBytes, 10);
        var allowed = ["image/jpeg", "image/png", "image/webp"];
        var objectUrl = null;

        function showError(message) {
            clientError.textContent = message;
            clientError.hidden = !message;
        }

        function resetPreview() {
            if (objectUrl) URL.revokeObjectURL(objectUrl);
            objectUrl = null;
            newImage.hidden = true;
            newImage.removeAttribute("src");
        }

        input.addEventListener("change", function () {
            var file = input.files && input.files[0];
            showError("");
            resetPreview();
            status.textContent = "";
            if (!file) return;

            if (allowed.indexOf(file.type) === -1) {
                showError("فقط تصویر JPG، PNG یا WebP پذیرفته می‌شود.");
                input.value = "";
                return;
            }
            if (file.size > maxBytes) {
                showError("حجم تصویر نباید بیشتر از ۲ مگابایت باشد.");
                input.value = "";
                return;
            }

            objectUrl = URL.createObjectURL(file);
            newImage.src = objectUrl;
            newImage.hidden = false;
            if (remove) remove.checked = false;
            preview.classList.remove("is-removing");
            status.textContent = "پیش‌نمایش تصویر جدید. برای ثبت، «ذخیره تغییرات» را بزنید.";
        });

        if (remove) {
            remove.addEventListener("change", function () {
                if (remove.checked) {
                    input.value = "";
                    resetPreview();
                    preview.classList.add("is-removing");
                    status.textContent = "تصویر با «ذخیره تغییرات» حذف می‌شود.";
                } else {
                    preview.classList.remove("is-removing");
                    status.textContent = "";
                }
            });
        }
    }

    // ---------- Password show / hide ----------

    root.querySelectorAll("[data-toggle-password]").forEach(function (button) {
        var field = document.getElementById(button.dataset.togglePassword);
        if (!field) return;
        var icon = button.querySelector("use");
        button.hidden = false;
        button.addEventListener("click", function () {
            var show = field.type === "password";
            field.type = show ? "text" : "password";
            button.setAttribute("aria-pressed", show ? "true" : "false");
            button.setAttribute("aria-label", show ? "پنهان کردن رمز عبور" : "نمایش رمز عبور");
            icon.setAttribute("href", show ? "#i-eye-off" : "#i-eye");
        });
    });

    // ---------- Checklist + strength ----------

    var form = root.querySelector("[data-password-form]");
    if (!form) return;

    var password = form.querySelector('[name="new_password1"]');
    var meter = form.querySelector("[data-strength]");
    var bar = form.querySelector("[data-strength-bar]");
    var label = form.querySelector("[data-strength-label]");
    var words = (form.dataset.userWords || "")
        .toLowerCase()
        .split(/[\s@._-]+/)
        .filter(function (word) { return word.length >= 3; });

    var checks = {
        length: function (value, rule) { return value.length >= parseInt(rule.dataset.value, 10); },
        "not-numeric": function (value) { return value.length > 0 && !/^\d+$/.test(value); },
        "not-similar": function (value) {
            var lower = value.toLowerCase();
            return value.length > 0 && !words.some(function (word) {
                return lower.indexOf(word) !== -1 || word.indexOf(lower) !== -1;
            });
        }
    };

    var LEVELS = ["", "ضعیف", "متوسط", "خوب", "قوی"];

    function score(value) {
        if (!value) return 0;
        var points = 0;
        if (value.length >= 8) points++;
        if (value.length >= 12) points++;
        if (/[a-z]/i.test(value) && /\d/.test(value)) points++;
        if (/[^a-z0-9]/i.test(value) || (/[a-z]/.test(value) && /[A-Z]/.test(value))) points++;
        if (/^\d+$/.test(value)) points = Math.min(points, 1);
        return Math.max(1, Math.min(points, 4));
    }

    function update() {
        var value = password.value;
        form.querySelectorAll("[data-rule]").forEach(function (rule) {
            var met = checks[rule.dataset.rule] ? checks[rule.dataset.rule](value, rule) : false;
            rule.classList.toggle("is-met", met);
            rule.querySelector("[data-rule-state]").textContent = met ? "(رعایت شده)" : "";
        });

        var level = score(value);
        meter.hidden = !value;
        meter.dataset.level = level;
        bar.style.setProperty("inline-size", (level * 25) + "%");
        label.textContent = LEVELS[level];
    }

    password.addEventListener("input", update);
    update();
})();
