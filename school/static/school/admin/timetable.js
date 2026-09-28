/*
 * «برنامه هفتگی» grid of one class
 * (school/templates/admin/school/schoolclass/timetable.html).
 *
 * The grid is rendered from `cells` (one entry per day x bell) and posts
 * the whole of it on save; scheduling/timetable.py diffs it against the
 * saved timetable and enforces every conflict rule. The "busy" marks are
 * only a hint fetched per teacher.
 *
 * Week types are the stored ClassSchedule.week_type values:
 * 1 = هفته اول, 2 = هفته دوم, 3 = هر هفته.
 */
(function () {
  "use strict";

  const $ = django.jQuery;
  const root = document.querySelector("[data-timetable]");
  if (!root) return;

  const EVERY = "3";
  const WEEK_LABELS = { 1: "هفته اول", 2: "هفته دوم", 3: "هر هفته" };
  const FA_DIGITS = "۰۱۲۳۴۵۶۷۸۹";
  const MAX_RECENT = 8;

  let data = JSON.parse(document.getElementById("tt-data").textContent);
  const canEdit = data.can_edit;
  const table = root.querySelector("[data-tt-grid]");
  const caption = table.querySelector("caption");
  const messages = root.querySelector("[data-tt-messages]");
  const csrf = root.querySelector("input[name=csrfmiddlewaretoken]").value;

  let cells = new Map();          // "day:bell" -> {alt, slots: {1|2|3: {subject, teacher}}}
  let subjects = new Map();       // id -> {id, name, color}
  let teachers = new Map();       // id -> {id, name}
  let subjectTemplate, teacherTemplate;
  let recent = [];                // [{subject, teacher}], most recent first
  let tool = null;                // null | "paint" | "erase"
  let dirty = false;
  let busy = { teacher: null, entries: [] };
  const busyCache = new Map();

  const toFa = (value) => String(value).replace(/\d/g, (d) => FA_DIGITS[d]);
  const cellKey = (day, bell) => day + ":" + bell;
  const emptyPair = () => ({ subject: "", teacher: "" });

  // ------------------------------------------------------------------
  // State
  // ------------------------------------------------------------------

  function loadState(grid) {
    subjects = new Map(grid.subjects.map((s) => [String(s.id), s]));
    teachers = new Map(grid.teachers.map((t) => [String(t.id), t]));
    subjectTemplate = optionsTemplate(grid.subjects);
    teacherTemplate = optionsTemplate(grid.teachers);

    cells = new Map();
    grid.days.forEach((day) => grid.bells.forEach((bell) => {
      cells.set(cellKey(day.value, bell.id), {
        alt: false,
        slots: { 1: emptyPair(), 2: emptyPair(), 3: emptyPair() },
      });
    }));
    grid.entries.forEach((e) => {
      const cell = cells.get(cellKey(e.day, e.bell));
      if (!cell) return;
      cell.slots[e.week_type] = { subject: String(e.subject), teacher: String(e.teacher) };
      if (String(e.week_type) !== EVERY) cell.alt = true;
    });

    recent = grid.recent_pairs
      .map((p) => ({ subject: String(p.subject), teacher: String(p.teacher) }))
      .slice(0, MAX_RECENT);
  }

  function optionsTemplate(items) {
    const select = document.createElement("select");
    select.appendChild(new Option("", ""));
    items.forEach((item) => select.appendChild(new Option(item.name, item.id)));
    return select;
  }

  function ensureSubject(select) {
    // A subject just added through the "+" popup.
    const id = select.value;
    if (!id || subjects.has(id)) return;
    const name = select.options[select.selectedIndex].text;
    subjects.set(id, { id: Number(id), name: name, color: "" });
    subjectTemplate.appendChild(new Option(name, id));
    document.querySelectorAll("[data-role=subject], [data-tt-brush=subject]").forEach((other) => {
      if (!other.querySelector('option[value="' + id + '"]')) other.appendChild(new Option(name, id));
    });
  }

  function markDirty() {
    dirty = true;
    const note = root.querySelector("[data-tt-dirty]");
    if (note) note.hidden = false;
  }

  function markClean() {
    dirty = false;
    const note = root.querySelector("[data-tt-dirty]");
    if (note) note.hidden = true;
  }

  window.addEventListener("beforeunload", (event) => {
    if (dirty) {
      event.preventDefault();
      event.returnValue = "";
    }
  });

  // ------------------------------------------------------------------
  // Rendering
  // ------------------------------------------------------------------

  function el(tag, className, text) {
    const node = document.createElement(tag);
    if (className) node.className = className;
    if (text !== undefined) node.textContent = text;
    return node;
  }

  function render() {
    $(table).find("select.select2-hidden-accessible").select2("destroy");
    table.replaceChildren(caption);

    const head = el("thead");
    const headRow = el("tr");
    headRow.appendChild(el("th", "tt-corner", "روز / زنگ")).scope = "col";
    data.bells.forEach((bell) => {
      const th = el("th", "tt-bell");
      th.scope = "col";
      th.appendChild(el("span", "tt-bell__title", bell.title));
      th.appendChild(el("span", "tt-bell__time", bell.time));
      headRow.appendChild(th);
    });
    head.appendChild(headRow);
    table.appendChild(head);

    const body = el("tbody");
    data.days.forEach((day) => {
      const row = el("tr");
      const th = el("th", "tt-day", day.label);
      th.scope = "row";
      row.appendChild(th);
      data.bells.forEach((bell) => row.appendChild(renderCell(day, bell)));
      body.appendChild(row);
    });
    table.appendChild(body);

    table.querySelectorAll(".tt-cell").forEach(enhanceCell);
    applyBusy();
  }

  function renderCell(day, bell) {
    const state = cells.get(cellKey(day.value, bell.id));
    const td = el("td", "tt-cell");
    td.dataset.day = day.value;
    td.dataset.bell = bell.id;
    td.classList.toggle("is-alt", state.alt);

    if (canEdit) {
      const toggle = el("button", "tt-mode", "هفته‌درمیان");
      toggle.type = "button";
      toggle.dataset.ttMode = "";
      toggle.setAttribute("aria-pressed", String(state.alt));
      toggle.title = state.alt ? "برگرداندن به «هر هفته»" : "تقسیم به «هفته اول» و «هفته دوم»";
      td.appendChild(toggle);
    }

    [EVERY, "1", "2"].forEach((week) => td.appendChild(renderSlot(day, bell, week, state.slots[week])));
    return td;
  }

  function renderSlot(day, bell, week, pair) {
    const slot = el("div", "tt-slot");
    slot.dataset.week = week;
    const where = day.label + "، " + bell.title + (week === EVERY ? "" : "، " + WEEK_LABELS[week]);
    if (week !== EVERY) slot.appendChild(el("span", "tt-slot__label", WEEK_LABELS[week]));

    const id = "id_tt_s_" + day.value + "_" + bell.id + "_" + week;
    const subjectRow = el("div", "tt-slot__subject");
    const subject = subjectTemplate.cloneNode(true);
    subject.id = id;
    subject.dataset.role = "subject";
    subject.dataset.context = "available-source";
    subject.setAttribute("aria-label", where + ": درس");
    subject.value = pair.subject;
    subject.disabled = !canEdit;
    subjectRow.appendChild(subject);

    if (canEdit && data.can_add_subject) {
      const add = el("a", "related-widget-wrapper-link add-related tt-add-subject", "+");
      add.id = "add_" + id;
      add.href = data.urls.add_subject + "?_popup=1";
      add.dataset.popup = "yes";
      add.title = "افزودن درس جدید";
      add.setAttribute("aria-label", "افزودن درس جدید برای " + where);
      subjectRow.appendChild(add);
    }
    slot.appendChild(subjectRow);

    const teacher = teacherTemplate.cloneNode(true);
    teacher.dataset.role = "teacher";
    teacher.setAttribute("aria-label", where + ": معلم");
    teacher.value = pair.teacher;
    teacher.disabled = !canEdit;
    slot.appendChild(teacher);

    slot.appendChild(el("p", "tt-slot__error"));
    slot.appendChild(el("p", "tt-slot__busy"));
    paintColor(slot, pair.subject);
    return slot;
  }

  function paintColor(slot, subjectId) {
    const subject = subjects.get(subjectId);
    if (subject && subject.color) slot.style.setProperty("--tt-color", subject.color);
    else slot.style.removeProperty("--tt-color");
    slot.classList.toggle("has-subject", Boolean(subjectId));
  }

  function select2(select, placeholder) {
    if (select.classList.contains("select2-hidden-accessible")) return;
    $(select).select2({
      width: "100%",
      dir: "rtl",
      language: "fa",
      placeholder: placeholder,
      allowClear: true,
    });
  }

  function enhanceCell(td) {
    // Select2 only on the slots that are shown; the others on demand.
    td.querySelectorAll(".tt-slot").forEach((slot) => {
      if (getComputedStyle(slot).display === "none") return;
      select2(slot.querySelector("[data-role=subject]"), "درس");
      select2(slot.querySelector("[data-role=teacher]"), "معلم");
    });
  }

  function rerenderCell(td) {
    $(td).find("select.select2-hidden-accessible").select2("destroy");
    const day = data.days.find((d) => String(d.value) === td.dataset.day);
    const bell = data.bells.find((b) => String(b.id) === td.dataset.bell);
    const fresh = renderCell(day, bell);
    td.replaceWith(fresh);
    enhanceCell(fresh);
    applyBusy();
    return fresh;
  }

  function slotOf(day, bell, week) {
    return table.querySelector(
      '.tt-cell[data-day="' + day + '"][data-bell="' + bell + '"] .tt-slot[data-week="' + week + '"]'
    );
  }

  function setSlot(slot, pair) {
    const td = slot.closest(".tt-cell");
    const state = cells.get(cellKey(td.dataset.day, td.dataset.bell));
    state.slots[slot.dataset.week] = { subject: pair.subject, teacher: pair.teacher };
    $(slot.querySelector("[data-role=subject]")).val(pair.subject).trigger("change.select2");
    $(slot.querySelector("[data-role=teacher]")).val(pair.teacher).trigger("change.select2");
    paintColor(slot, pair.subject);
    clearError(slot);
    markDirty();
    applyBusy();
  }

  // ------------------------------------------------------------------
  // Editing
  // ------------------------------------------------------------------

  $(table).on("change", "select", function () {
    const slot = this.closest(".tt-slot");
    const td = this.closest(".tt-cell");
    const state = cells.get(cellKey(td.dataset.day, td.dataset.bell));
    const pair = state.slots[slot.dataset.week];

    if (this.dataset.role === "subject") ensureSubject(this);
    pair[this.dataset.role] = this.value;

    paintColor(slot, pair.subject);
    clearError(slot);
    markDirty();
    if (pair.subject && pair.teacher) remember(pair);
    if (this.dataset.role === "teacher" && this.value) showBusy(this.value);
    else applyBusy();
  });

  table.addEventListener("click", (event) => {
    const toggle = event.target.closest("[data-tt-mode]");
    if (toggle) {
      toggleAlternating(toggle.closest(".tt-cell"));
      return;
    }

    const slot = tool && event.target.closest(".tt-slot");
    if (!slot) return;
    event.preventDefault();
    if (tool === "erase") {
      setSlot(slot, emptyPair());
      return;
    }
    const pair = brushPair();
    if (!pair.subject || !pair.teacher) {
      flash("error", "برای پر کردن سریع، ابتدا درس و معلم را در بالای جدول انتخاب کنید.");
      return;
    }
    setSlot(slot, pair);
    remember(pair);
  });

  function toggleAlternating(td) {
    const state = cells.get(cellKey(td.dataset.day, td.dataset.bell));
    const filled = (week) => Boolean(state.slots[week].subject || state.slots[week].teacher);

    if (!state.alt) {
      // Every week -> alternating: the current entry becomes week 1.
      state.slots[1] = { ...state.slots[EVERY] };
      state.slots[2] = emptyPair();
      state.slots[EVERY] = emptyPair();
      state.alt = true;
    } else {
      if (filled(1) && filled(2) &&
          !window.confirm("هر دو هفته پر است. با برگشت به «هر هفته» فقط «هفته اول» می‌ماند. ادامه می‌دهید؟")) {
        return;
      }
      state.slots[EVERY] = { ...state.slots[filled(1) ? 1 : 2] };
      state.slots[1] = emptyPair();
      state.slots[2] = emptyPair();
      state.alt = false;
    }
    markDirty();
    rerenderCell(td).querySelector("[data-tt-mode]").focus();
  }

  // ------------------------------------------------------------------
  // Quick fill: brush, eraser, most used pairs
  // ------------------------------------------------------------------

  const brushSubject = root.querySelector("[data-tt-brush=subject]");
  const brushTeacher = root.querySelector("[data-tt-brush=teacher]");
  const paintButton = root.querySelector("[data-tt-paint]");
  const eraseButton = root.querySelector("[data-tt-erase]");
  const recentBox = root.querySelector("[data-tt-recent]");
  const recentList = root.querySelector("[data-tt-recent-list]");

  function brushPair() {
    return { subject: brushSubject.value, teacher: brushTeacher.value };
  }

  function fillBrushOptions() {
    if (!brushSubject) return;
    [[brushSubject, subjectTemplate, "درس"], [brushTeacher, teacherTemplate, "معلم"]].forEach(([select, template, placeholder]) => {
      const value = select.value;
      if (select.classList.contains("select2-hidden-accessible")) $(select).select2("destroy");
      select.replaceChildren(...Array.from(template.options, (o) => o.cloneNode(true)));
      select.value = value;
      select2(select, placeholder);
    });
  }

  function setTool(next) {
    tool = tool === next ? null : next;
    if (paintButton) paintButton.setAttribute("aria-pressed", String(tool === "paint"));
    if (eraseButton) eraseButton.setAttribute("aria-pressed", String(tool === "erase"));
    root.classList.toggle("is-painting", tool === "paint");
    root.classList.toggle("is-erasing", tool === "erase");
  }

  function remember(pair) {
    recent = [{ subject: pair.subject, teacher: pair.teacher }]
      .concat(recent.filter((p) => p.subject !== pair.subject || p.teacher !== pair.teacher))
      .slice(0, MAX_RECENT);
    renderRecent();
  }

  function renderRecent() {
    if (!recentList) return;
    const chips = recent.filter((p) => subjects.has(p.subject) && teachers.has(p.teacher));
    recentBox.hidden = chips.length === 0;
    recentList.replaceChildren(...chips.map((pair) => {
      const chip = el("button", "tt-chip");
      chip.type = "button";
      const subject = subjects.get(pair.subject);
      if (subject.color) chip.style.setProperty("--tt-color", subject.color);
      chip.appendChild(el("span", "tt-chip__subject", subject.name));
      chip.appendChild(el("span", "tt-chip__teacher", teachers.get(pair.teacher).name));
      chip.addEventListener("click", () => {
        $(brushSubject).val(pair.subject).trigger("change.select2");
        $(brushTeacher).val(pair.teacher).trigger("change.select2");
        if (tool !== "paint") setTool("paint");
        showBusy(pair.teacher);
      });
      return chip;
    }));
  }

  if (canEdit) {
    paintButton.addEventListener("click", () => setTool("paint"));
    eraseButton.addEventListener("click", () => setTool("erase"));
    $(brushTeacher).on("change", function () {
      if (this.value) showBusy(this.value);
    });
    $(brushSubject).on("change", function () {
      ensureSubject(this);
    });
  }

  // ------------------------------------------------------------------
  // Teacher availability hint
  // ------------------------------------------------------------------

  const legend = root.querySelector("[data-tt-busy-legend]");

  async function showBusy(teacherId) {
    busy.teacher = teacherId;
    let entries = busyCache.get(teacherId);
    if (!entries) {
      try {
        const response = await fetch(
          data.urls.busy + "?teacher=" + encodeURIComponent(teacherId),
          { headers: { Accept: "application/json" }, credentials: "same-origin" }
        );
        if (!response.ok) return;
        entries = (await response.json()).busy;
      } catch (error) {
        return;  // only a hint
      }
      busyCache.set(teacherId, entries);
    }
    if (busy.teacher !== teacherId) return;  // another teacher was picked meanwhile
    busy.entries = entries;
    applyBusy();
  }

  function clearBusy() {
    busy = { teacher: null, entries: [] };
    applyBusy();
  }

  function applyBusy() {
    table.querySelectorAll(".tt-slot.is-busy").forEach((slot) => {
      slot.classList.remove("is-busy", "is-clash");
      slot.querySelector(".tt-slot__busy").textContent = "";
    });

    if (!busy.teacher) {
      legend.hidden = true;
      return;
    }

    busy.entries.forEach((entry) => {
      const weeks = String(entry.week_type) === EVERY ? [EVERY, "1", "2"] : [EVERY, String(entry.week_type)];
      weeks.forEach((week) => {
        const slot = slotOf(entry.day, entry.bell, week);
        if (!slot) return;
        slot.classList.add("is-busy");
        const note = slot.querySelector(".tt-slot__busy");
        note.textContent = note.textContent ? note.textContent + " " + entry.message : entry.message;
        if (slot.querySelector("[data-role=teacher]").value === busy.teacher) slot.classList.add("is-clash");
      });
    });

    const teacher = teachers.get(busy.teacher);
    const name = teacher ? teacher.name : "";
    legend.replaceChildren(
      el("span", "", busy.entries.length
        ? "زنگ‌هایی که «" + name + "» در کلاس دیگری درس دارد هاشور خورده‌اند."
        : "«" + name + "» در این سال تحصیلی در کلاس دیگری برنامه‌ای ندارد.")
    );
    const hide = el("button", "button tt-busy-legend__hide", "پنهان کردن");
    hide.type = "button";
    hide.addEventListener("click", clearBusy);
    legend.appendChild(hide);
    legend.hidden = false;
  }

  // ------------------------------------------------------------------
  // Saving
  // ------------------------------------------------------------------

  function flash(level, text) {
    const item = el("li", level, text);
    messages.replaceChildren(item);
    messages.scrollIntoView({ block: "nearest" });
  }

  function clearError(slot) {
    slot.classList.remove("has-error");
    slot.querySelector(".tt-slot__error").textContent = "";
    const td = slot.closest(".tt-cell");
    if (!td.querySelector(".tt-slot.has-error")) td.classList.remove("has-error");
  }

  function showErrors(errors) {
    table.querySelectorAll(".tt-slot.has-error").forEach(clearError);
    let first = null;
    errors.forEach((error) => {
      const slot = slotOf(error.day, error.bell, error.week_type);
      if (!slot) return;
      slot.classList.add("has-error");
      slot.closest(".tt-cell").classList.add("has-error");
      const note = slot.querySelector(".tt-slot__error");
      if (!note.textContent.includes(error.message)) {
        note.textContent = note.textContent ? note.textContent + " " + error.message : error.message;
      }
      first = first || slot;
    });
    if (first) first.scrollIntoView({ block: "center", inline: "center" });
  }

  function entries() {
    const result = [];
    cells.forEach((state, key) => {
      const [day, bell] = key.split(":").map(Number);
      (state.alt ? ["1", "2"] : [EVERY]).forEach((week) => {
        const pair = state.slots[week];
        if (pair.subject || pair.teacher) {
          result.push({
            day: day,
            bell: bell,
            week_type: Number(week),
            subject: pair.subject ? Number(pair.subject) : null,
            teacher: pair.teacher ? Number(pair.teacher) : null,
          });
        }
      });
    });
    return result;
  }

  async function save(button) {
    button.disabled = true;
    try {
      const response = await fetch(data.urls.save, {
        method: "POST",
        credentials: "same-origin",
        headers: { "Content-Type": "application/json", "X-CSRFToken": csrf, Accept: "application/json" },
        body: JSON.stringify({ entries: entries() }),
      });
      const body = await response.json().catch(() => null);

      if (response.ok && body && body.ok) {
        data = { ...data, ...body.grid };
        loadState(data);
        fillBrushOptions();
        render();
        renderRecent();
        markClean();
        const c = body.counts;
        flash("success", "برنامه ذخیره شد (" + toFa(c.created) + " مورد جدید، " +
          toFa(c.updated) + " ویرایش، " + toFa(c.deleted) + " حذف).");
        return;
      }

      if (response.status === 400 && body) {
        showErrors(body.errors || []);
        const general = (body.general || []).join(" ");
        flash("error", "برنامه ذخیره نشد؛ هیچ تغییری اعمال نشد. " +
          (general || "خطاهای مشخص‌شده در جدول را برطرف کنید و دوباره ذخیره کنید."));
        return;
      }
      if (response.status === 403) {
        flash("error", "شما اجازه‌ی ویرایش برنامه‌ی این کلاس را ندارید.");
        return;
      }
      flash("error", "ذخیره انجام نشد (خطای " + toFa(response.status) + "). دوباره تلاش کنید.");
    } catch (error) {
      flash("error", "ارتباط با سرور برقرار نشد. تغییرات شما حفظ شده است؛ دوباره تلاش کنید.");
    } finally {
      button.disabled = false;
    }
  }

  const saveButton = root.querySelector("[data-tt-save]");
  if (saveButton) saveButton.addEventListener("click", () => save(saveButton));

  // ------------------------------------------------------------------

  loadState(data);
  fillBrushOptions();
  render();
  renderRecent();
})();
