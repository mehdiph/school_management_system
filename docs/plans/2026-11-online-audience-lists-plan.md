# Plan: audience summaries and student list pages in the online classes admin

Status: **plan only, waiting for approval.** Work will go on `feature/online-audience-lists`, branched from
`main` (f397098). `feature/online-classes` is already merged, so the work doesn't go there.

## The request

On the event page, the students without an access row are listed in full, so a few hundred students mean a lot
of scrolling. The fix:

1. A one-line summary: audience count, plus the with-access and without-row counts for personal-mode events.
2. Below it, a per-class breakdown, collapsed by default, ordered by grade then section.
3. Each count links to a separate admin list page with search, a class filter, a "without row only" filter and
   pagination, under the event page's permission and branch rules.
4. The same summary and breakdown (audience count only) on the announcement page.
5. The same pattern wherever else this app's admin renders one line per student on a form page.

The query count stays fixed whatever the audience size.

## 1. What reading found

- **Event page** (`OnlineEventAdmin.audience_report`): the total, then for personal events the `missing_access` list
  as one `<li>` per student. The announcement page shows no audience report at all, only the count in the message
  after saving.
- **Other one-line-per-student places in this app's admin:**
  - **Access inline** on the event page: one form row per access row, up to `ONLINE_ACCESS_INLINE_MAX` (100). Above
    that it shows none, because Django's field limit would break saving.
  - **Import preview** (`access_import.html`): one table row per file row, up to `ONLINE_ACCESS_IMPORT_MAX_ROWS`
    (1000).
  - **Student pickers** («دانش‌آموزان», «دانش‌آموزان مستثنا»): one select2 chip per *selected* student. These are
    the choices themselves, so a count can't replace them (D5).
  - The access row list is already a paginated changelist. Reveal and clear-confirm are one row or one event each.
- **Queries today:** `reached_enrollments` reads the five target lists (5 queries) and builds `IN (…)` filters;
  `.count()` adds one. `missing_access` and `obj.access_rows.count()` add more. That's constant, but the
  `missing` list renders every student.
- **Scoping risk (needs a decision, D1):** a branch-scoped admin with view permission can open a whole-school event,
  or one touching their branches but also others, read-only. Today its «بدون ردیف» list shows names from **all**
  branches. A list page with search would make that much easier to browse.

## 2. Decisions (please confirm)

- **D1, branch scope of counts and lists (policy):** for a non-superuser, the summary, the per-class breakdown and
  the list pages count and show **only students currently enrolled in their branches**. The summary then says so:
  «فقط دانش‌آموزان شعبه‌های شما». A superuser sees everyone. Opening the list page follows the event or announcement
  page: view permission on the model, and the item must be in the admin's queryset (it touches their branches),
  otherwise 404. This also closes the cross-branch names on today's event page. The alternative is whole counts but
  names only from their branches; mixed numbers would confuse more.
- **D2, the list page:** `…/onlineevent/<id>/students/` and `…/announcement/<id>/students/`, read-only admin pages
  in the admin's look (breadcrumbs, `results` table, Django's paginator, 100 per page). They work without JS (a GET
  form).
  - **Columns:** name, student code, class, and for personal events «ردیف دسترسی»: what's stored (لینک، نام کاربری،
    رمز، کد, never a value) with a link to that row's page, or «بدون ردیف».
  - **Search:** first and last name, student code and national code. The national code is searchable but **not
    shown**.
  - **Filters:** class (only the classes in this item's audience and the admin's scope) and, for personal events,
    «همه / با ردیف / بدون ردیف». That extends the requested "without row only" so the with-access count can link
    to the "with row" view.
  - **Links from the summary:** audience count → all; with-access → `?access=with`; without-row →
    `?access=without`; a class row's numbers → the same with `?class=<id>`.
- **D3, the access inline (applying point 5):** the inline no longer lists existing rows; it only offers blank rows
  for adding a few by hand. Existing rows are edited from their own page, linked from the list page (D2) and from
  the summary («ویرایش ردیف‌ها» → the access row list filtered by this event). `ONLINE_ACCESS_INLINE_MAX` and the
  formset's threshold go away. This changes behaviour for small events, where rows were editable in place; the
  alternative is keeping the inline up to a lower threshold (e.g. 30), which still means one line per student.
- **D4, the import preview (applying point 5):** the preview shows the totals (new, update, skipped, errors,
  warnings), then **only the rows with errors or warnings** in full, since those need fixing, then a per-class
  breakdown of the valid rows (new and update counts) in a collapsed block. Valid rows aren't listed one by one.
  The preview reads only the sealed rows, with no extra per-row query.
- **D5, student pickers stay as they are:** the selected students are the input itself. Replacing them would take
  away the way to choose and un-choose. Selecting hundreds by name isn't the intended use; that's what classes,
  grades and branches are for.

## 3. Implementation outline

- **audience.py** (the only code that reads targets):
  - `reached_enrollments(item)` becomes one queryset whose target sets are subqueries on the through tables, not
    Python id lists. Callers and results are unchanged, but it no longer reads the targets first.
  - New `audience_breakdown(item, branch_ids=None, event=None)`: one aggregate query,
    `values(class) → Count(enrolment), Count(filter=no access row)` with `~Exists` on `OnlineEventAccess`,
    ordered by grade level, section, then branch. It returns per-class rows plus totals summed in Python from those
    rows (no second query). `branch_ids=None` means unscoped (superuser).
  - New `audience_students(item, branch_ids=None, event=None)`: the list page's queryset, annotated with the access
    row (one `Subquery` for its id and which fields are stored), so a page costs a fixed number of queries.
- **services.py:** `missing_access` stays (the import's warning uses the audience; no change there).
- **admin.py:**
  - an `AudienceReportMixin` shared by both admins: `audience_report` (summary line plus `<details>` breakdown, no
    JS), `get_urls` adding `<id>/students/`, and `students_view` (permission, scope, filters, search, paginator);
  - the announcement page gets the «چه کسانی می‌بینند» fieldset (change page only), and the event page's report is
    replaced;
  - the inline per D3, and the import view per D4.
- **Templates:** `admin/online_classes/audience_students.html` (shared), `_audience_report.html` (summary and
  breakdown), and `access_import.html` changed per D4. RTL and the admin's own styles; checked at 1280 px and 375 px.
- **Settings:** remove `ONLINE_ACCESS_INLINE_MAX` (D3). The list page size is a constant in the admin.
- **Tests** (`online_classes/tests/test_audience_admin.py`):
  - counts: whole school, branch AND grade, classes, students, exclusions; with/without row; rows for students
    outside the audience aren't counted; a class change moves a student;
  - breakdown order (grade, section, branch); one row per class;
  - scoping: a branch admin sees only their branches' counts and students on the event page, the announcement page
    and the list pages; a list page of an item outside their queryset → 404; no view permission → 403; superuser
    sees all;
  - list page: search by name, student code and national code (not displayed); class filter limited to audience
    classes; access filter; pagination; works without JS; no secret values in the HTML;
  - **query count:** the event page, announcement page and list page each have an exact `assertNumQueries` that is
    the same for an audience of 3 and of 60 students;
  - inline per D3, and the import preview per D4 (valid rows not listed, error rows listed);
  - existing tests that check the old list (`test_page_shows_the_count_and_the_list_of_missing_students`, the
    inline threshold tests) are updated to the new behaviour, not deleted.
- **Docs:** `docs/apps/online_classes.md` (admin section, settings table, audience.py), ADR-027 amendment for D1
  (admin counts are branch-scoped), `docs/changelog.md`, and the report `docs/plans/2026-11-online-audience-lists.md`.

## 4. Verification and what I won't touch

- Baseline the app's tests on `main`, then the full suite on PostgreSQL (and SQLite), compared with 1302.
- No models change, so no migration (`makemigrations --check`).
- I won't touch the student panel, audience rules, any data, the local Docker database or production.
