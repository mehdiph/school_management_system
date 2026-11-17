# Report: audience summaries and student lists in the online classes admin

**Status:** committed on `feature/online-audience-lists` (from `main` at 6a2f9b9) in two commits: the student-picker
fix (46456f1) and the rest. **Merged into `main` and pushed on 2026-11-17, not deployed.** The full test suite was
not re-run before merging, at the user's request; only `online_classes` + `student` (310 OK, SQLite) were run on the
final commit (see §7). Plan:
`docs/plans/2026-11-online-audience-lists-plan.md` (approved 2026-11-17 with D3 extended and D5 replaced).

## 1. Summary and reasoning

A few hundred students made the event page long. There were two causes:

1. **The student pickers.** «دانش‌آموزان» and «دانش‌آموزان مستثنا» rendered **every student profile as a checkbox,
   twice**: all years and all branches, including other branches' students for a branch admin. This was most of the
   scroll.
2. **The «بدون ردیف» list.** It had one `<li>` per student, and the inline listed up to 100 access rows.

Both are now counts and links:

- **Pickers:** server-side autocomplete, scoped to current students in the admin's branches. Committed on its own.
- **Event and announcement pages:** a one-line summary and a collapsed per-class table.
- **List page:** a paginated, searchable page per item.
- **Inline:** only adds new rows.
- **Access rows:** a row can be added from the list page and the admin returns to the same filtered page.
- **Import preview:** lists only the rows that need attention.

Counting moved into the database (`audience.breakdown`, one aggregate), so each page's query count is fixed. For a
non-superuser everything is limited to their branches (D1). That also closes a gap: a branch admin viewing a
whole-school event used to see «بدون ردیف» names from every branch.

**Why the existing tests didn't catch the checkboxes.**
- The picker tests called Django's `admin:autocomplete` JSON view directly. The view worked and was branch-scoped,
  but the form never used it: `formfield_overrides = {ManyToManyField: CheckboxSelectMultiple}` puts a widget into the
  kwargs, and `formfield_for_manytomany` only applies autocomplete when there's no widget.
- No test rendered the change page and looked at what the student fields became.
- No test measured the page against the number of students: the fixtures have three students, where a checkbox list
  looks fine.
- The branch tests checked `form.fields["branches"]` and `["classes"]` querysets, but not `["students"]`.

The new tests render the pages and check the HTML. They compare query count and size with 3 and 48 students, and
post forged ids.

**Rejected alternatives.**
- Whole-school counts with names only from the admin's branches: mixed numbers confuse more.
- Keeping the inline up to a lower threshold: it would still be one line per student.
- Patching `StudentProfileAdmin` further for labels: this app's own autocomplete view keeps the scoping and labels
  in one place, and only answers this app's student fields.

## 2. Files changed / added

| Area | File | Change |
|---|---|---|
| Pickers (commit 46456f1) | `online_classes/pickers.py` (new) | `StudentAutocompleteView` (current enrolment, branch scope, labels, only this app's student fields), `StudentPicker` / `StudentsPicker` widgets |
| | `online_classes/admin.py` | checkboxes for branches/grades/classes only; student fields use `StudentsPicker`; access row student uses `StudentPicker`; URL `onlineevent/student-autocomplete/` |
| | `online_classes/forms.py` | students / excluded querysets = pickable ∪ already selected |
| | `online_classes/tests/test_pickers.py` (new), `test_admin.py` | page HTML, size and queries; scoping; forged ids; old endpoint tests moved to the new view |
| Audience | `online_classes/audience.py` | `reached_enrollments` as one query; `breakdown`, `students`, `ClassCount`, `Breakdown` |
| Admin | `online_classes/admin.py` | summary via `render_change_form`; `students_view` + URL on both admins; inline adds only; access row add flow (`?event=&student=&next=`) and safe return; `_stored` helper |
| | `online_classes/forms.py` | `require_audience` on the add page: audience and duplicate checks; event set on the instance |
| Import | `online_classes/importer.py` | class read with the branch (same query); `ImportPlan.flagged`, `ImportPlan.by_class` |
| Templates | `_audience_report.html`, `audience_students.html`, `announcement/change_form.html` (new); `onlineevent/change_form.html`, `onlineevent/access_import.html` | |
| Static | `online_classes/admin/audience.css` (new), `online_classes/admin/import.css` | |
| Settings | `teachlog/config/settings/base.py` | `ONLINE_ACCESS_INLINE_MAX` removed |
| Tests | `online_classes/tests/test_audience_admin.py` (new); `test_admin.py`, `test_importer.py` updated | see §7 |
| Docs | `docs/apps/online_classes.md` (§2, §7, §8, §9), ADR-027 amendment, `docs/changelog.md`, this report | |

## 3. Models and migrations

None. `makemigrations --check`: no changes. No data is touched.

## 4. URLs, views and permissions

| URL | Who | Refused |
|---|---|---|
| `admin/online_classes/onlineevent/<id>/students/`, `…/announcement/<id>/students/` | view or change permission on the model, and the item in the admin's queryset (touches their branches) | no permission → 403; item outside → 404; not logged in → login |
| `admin/online_classes/onlineevent/student-autocomplete/` | staff with view (or change) on `StudentProfile`, for this app's student fields only | other app/model/field → 403; no permission → 403 |
| `admin/online_classes/onlineeventaccess/add/?event=&student=&next=` | `add_onlineeventaccess`, and change permission on that personal event (wholly inside the admin's branches) | no `?event=` → 403; bad, unknown or shared event → 404; event visible but not theirs → 403 |

On the add page, the student must be in the event's audience and the admin's branches and have no row, whatever is
posted. `next` is followed only if it's a path (no scheme or host) equal to that event's list page and passes
`url_has_allowed_host_and_scheme`; otherwise Django's default applies. «ذخیره و افزودن» is hidden on that page,
because it would lose `?event=`.

## 5. Settings

`ONLINE_ACCESS_INLINE_MAX` is removed (D3). The list page size (`STUDENTS_PER_PAGE = 100`) is a constant in
`online_classes/admin.py`.

## 6. Decisions

- D1: non-superusers see counts and names of their branches only, with «فقط دانش‌آموزان شعبه‌های شما».
- D2: list page as planned. The access filter has three options (all / with / without), so the with-row count has a
  target.
- D3: the inline only adds; existing rows are edited on their own page.
  - **Extended:** «افزودن ردیف» on the list page, and the return to the filtered list.
- D4: the import preview lists only flagged rows; valid rows are counted per class.
- D5 (replaced): server-side autocomplete pickers, scoped and validated.

Resolved during implementation:
- **The summary is rendered by the change form templates** (`after_field_sets`), not as a read-only field. A
  read-only field has no request, and the counts need it for D1. It now sits after «ثبت», before the inline.
- **The access row's student picker uses the same scoped view.** Its results are current students in the admin's
  branches, now for superusers too.
- **Existing selections stay valid.** The audience form's student queryset includes students already selected on the
  item, so someone who has since left doesn't make the item unsaveable.
- **Row links follow the change permission.** Links to a row's page appear only for admins who may change the event,
  since only those can open the row. A branch admin viewing a whole-school event sees what's stored but no links.
- **A blank «بدون کلاس جاری» group.** In the import breakdown, a student without a current enrolment is counted there
  (such a row has an error anyway).
- **Other admin forms in this app checked for the override problem.** Only `AudienceAdminMixin` set
  `formfield_overrides`. The other relations are foreign keys (platform, subject, class subject, event, row student),
  which the override never affected.
  `academic_calendar`'s admin has the same blanket override, but only on branches, grades and bells (small sets, no
  students), so it was left alone.

## 7. Tests

- **`test_pickers.py`** (14, in commit 46456f1):
  - no `type="checkbox" name="students|excluded_students"` on four pages, while branches, grades and classes stay
    checkboxes;
  - selected students are rendered as options;
  - query count equal and size within 100 bytes with 45 more students;
  - autocomplete: superuser current-only, branch admin scoped for all five fields, search by name, code and national
    code, label, other fields refused, permission, fixed query count;
  - forged ids refused on events and announcements; a non-current student refused; an old selection stays valid.
- **`test_audience_admin.py`** (33):
  - breakdown for every audience rule (matching `reached_enrollments`), with and without a row, rows outside the
    audience not counted, a class change, one row per class in grade/section/branch order, branch scope;
  - the summary on both pages, closed `<details>`, links, no names, nobody selected, no summary on add pages, branch
    scope with the note;
  - **locked query counts:** event page 25 and announcement page 19, the same with 3 and 60 students;
  - list page: all/with/without, search (national code not displayed), class filter limited to the audience,
    pagination keeping filters, a plain GET form, no secrets, the announcement variant, branch scope and 404s,
    permissions, **a locked query count of 18** for 3 and 63 students;
  - adding a row:
    - prefilled link and form, and saving on the event with a return to the filtered list;
    - swapping in a student outside the audience or the branches is refused, and so is a duplicate;
    - add reachable only for a changeable personal event, and no add button on the rows list;
    - the link shows only for who may add;
    - seven forged `next` values give the default redirect, no `next` gives the default, the row change returns to
      the list, and «ذخیره و ادامه» stays;
  - the inline lists no row;
  - the import preview lists flagged rows only and counts per class, and its query count doesn't grow with rows.
- **Existing tests changed** because the approved behaviour changed, none deleted:
  - `test_admin`:
    - masking is now checked on the event page and the list page;
    - the blank-keeps-secret test edits on the row page;
    - the old missing-list test checks counts on the page and names on the list page;
    - the threshold test becomes "never lists rows";
    - the two old autocomplete tests point at the new view.
  - `test_importer`: the masking check uses a flagged (warning) row, because valid rows aren't listed.

| Run | Result |
|---|---|
| Baseline on `main` (6a2f9b9), `online_classes` + `student`, SQLite | 263 OK |
| Branch, `online_classes` + `student`, SQLite | 310 OK |
| Branch, full suite, PostgreSQL | **Not completed.** Stopped partway by Claude Code because the machine ran critically low on memory; no result. To be re-run. |
| Branch, full suite, SQLite | **Not completed.** Stopped for the same reason; to be re-run. |
| Branch (96c7847), `online_classes` + `student`, SQLite, before merging | 310 OK. Full suite skipped at the user's request. |

**Browser check:** scratch SQLite database (300 students in 12 classes, a whole-school personal event with 200 rows,
an announcement), headless Chromium at 1280 px and a true 375 px. Pages: event change page, announcement change page,
student list page (`?access=without`) and the prefilled add page.
- **Overflow:** none on any page at either width (`scrollWidth` equal to the window width).
- **Event page:** the pickers are single autocomplete boxes, and the summary reads «۳۰۰ دانش‌آموز مخاطب · ۲۰۰ با ردیف
  دسترسی · ۱۰۰ بدون ردیف» with the 12-class table closed. The inline offers one blank row.
- **List page:** filters stack at 375 px.
- **Add page:** shows the prefilled student and no «ذخیره و افزودن».
- **Not checked in a browser:** the import preview, which needs a POSTed file. Its markup change (flagged rows only,
  a `<details>` block, a scrolling wrapper) is covered by tests.

## 8. Discrepancies between docs and code

- The app doc said the student picker was autocomplete ("`StudentProfileAdmin.search_fields`; results are
  branch-scoped"), but the page rendered checkboxes (see §1). The doc is now accurate.
- My own plan's first D5 repeated that mistake; it was corrected at approval.

## 9. Open questions and deploy notes

- **Deploy:** no migration. Run `collectstatic` (new `online_classes/admin/audience.css`, changed `import.css`).
  Remove `ONLINE_ACCESS_INLINE_MAX` from any environment override if one was set; it's no longer read.
- **Brief the admins:**
  - students are picked by typing a name or code;
  - the event page shows counts, and «N دانش‌آموز مخاطب» opens the list;
  - missing rows can be added from the list one at a time, or by Excel as before;
  - existing rows are edited from the list or «دسترسی‌های شخصی».
