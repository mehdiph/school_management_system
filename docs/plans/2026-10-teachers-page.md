# Report: public «معلمان» page

**State: committed on `feature/teachers-page`, merged into `main` with
`--no-ff` and pushed on 2026-10-26. Not deployed.** No migration has been
run outside the test databases and scratch SQLite copies. The plan is `docs/plans/2026-10-teachers-page-plan.md`
on `main` (approved 2026-10-25, with three changes).

## 1. Summary and reasoning

`/teachers/` lists the teachers the website admin has chosen to publish:
- grouped by department, with filter chips;
- each with a portrait (or initial), name, specialty and experience;
- the teacher's own sentence written in red pen on a strip of notebook
  paper;
- an expansion with the bio and education.

An intro and a closing call to action, both editable and switchable, frame
the list.

Main choices:

- **One list** (D1). The landing page's teachers row and the new page read
  the same `LandingTeacher` rows, so a teacher is entered once.
  - Two ticks, «نمایش در صفحه معلمان» and «نمایش در صفحه اصلی», say where
    a teacher appears. Both default to off. Existing rows were set on the
    home page so the landing page didn't change.
  - The list moved from an inline on «مدیریت صفحه اصلی» to its own admin
    page, «معلمان سایت».
  - The model keeps its name (D3).
  - *Rejected:* a separate model. A teacher on both pages would become two
    rows that drift apart.
- **Privacy first** (D4, D5, D7, ADR-025 amended):
  - the photo is only the one uploaded on the card, never the account
    avatar, on both pages;
  - the name never falls back to the username;
  - leavers are hidden;
  - only the name and `field_of_study` are read from school records;
  - new photos of people are re-encoded without metadata. That covers
    teacher cards and, as approved, the About page's «همکاران ما».
- **In-page expansion, no detail pages** (D8). The content per teacher is
  short. A native `<details>` works with no JS, and each card has a stable
  `#slug` anchor. The blog's author model is deliberately **not** decided
  here (approval change 1). The card only has the anchor and a commented
  «نوشته‌های …» slot.
- **Editorial groups** (D9). `TeacherGroup` is typed in the admin, not
  `school.Subject`. The filter uses query-string links (`?group=<id>`), and
  JS only swaps a `?partial=1` fragment (ADR-015).
- **The invented seed teachers** (approval change 2). The four made-up
  people from `0002` are deactivated where untouched, and edited rows are
  left alone. Reversible.

Design (the `frontend-design` skill): the About page writes in a pupil's
blue ballpoint, and the Contact page is a notebook page. This page adds
**the teacher's red pen**:
- the one red element is each teacher's note on ruled notebook paper, with
  a red margin line and a hand-drawn tick;
- portraits reuse the landing page's blob frame;
- there are no card boxes and no motion besides the expansion the visitor
  opens.

## 2. Files

### Models and migrations

| File | Change |
|---|---|
| `website/models/teachers.py` | new: `TeachersPage`, `TeacherGroup` |
| `website/models/landing.py` | `LandingTeacher`: new fields, `page` removed, fallbacks (no avatar, no username), `initial`, `has_details`, slug and photo re-encoding in `save()`; `LandingPage.teachers_link_text` / `_url` |
| `website/models/about.py` | `AboutPerson.save()` re-encodes a new photo; `PUBLIC_PHOTO_HELP` moved to `website/images.py` |
| `website/models/__init__.py` | exports |
| `website/images.py` | new: `reencode()`, `reencode_new_photo()`, the shared photo help texts |
| `website/migrations/0009_teachers.py` … `0013_hide_seed_teachers.py` | new (§3) |

### Read side, views, admin

| File | Change |
|---|---|
| `website/selectors.py` | new: `public_teachers()`, `teachers_page_listing()` |
| `website/views.py` | `teachers` view; the landing view reads `public_teachers().filter(on_home=True)` |
| `website/urls.py` | `teachers/` |
| `website/admin.py` | `LandingTeacherAdmin` («معلمان سایت»), `TeachersPageAdmin` + `TeacherGroupInline`; the teacher inline removed from `LandingPageAdmin`, which links to the list |

### Templates and static files

| File | Change |
|---|---|
| `website/templates/website/teachers.html` | new page |
| `website/templates/website/teachers/_directory.html`, `_filter.html`, `_list.html`, `_teacher.html` | new partials |
| `website/templates/website/index.html` | the initial in the teacher blob, the link under the row |
| `website/static/website/css/teachers.css` | new |
| `website/static/website/js/teachers.js` | new |
| `website/static/website/css/index.css` | `.instructor-initial`, `.instructors-more` (additions only) |

### Tests

| File | Change |
|---|---|
| `website/test_teachers.py` | new, 42 tests |
| `website/tests.py` | shared `phone_photo()` / `assert_reencoded()`; landing tests updated for the dropped FK, the avatar rule and the hidden seed teachers |
| `website/test_about.py` | `AboutPerson` EXIF test; the menu test resets «معلمان» too (0012 links it) |

### Docs

| File | Change |
|---|---|
| `docs/apps/website.md` | models, migrations, admin, view, front end |
| `docs/database.md`, `docs/database-mermaid.md` | teachers page section, `LandingTeacher`; stale `national_code` / `is_homeroom_teacher` rows removed |
| `docs/apps/staff.md` | the same stale fields removed; national code and public-website notes |
| `docs/architecture-decisions.md` | ADR-025 amended |
| `docs/changelog.md` | entry |
| this report | — |

## 3. Models and migrations

| Migration | Database effect | Reverse |
|---|---|---|
| `0009_teachers` (schema) | creates `website_teacherspage`, `website_teachergroup`; adds `group_id`, `slug` (nullable), `experience`, `education`, `quote`, `bio`, `on_home` (existing rows **true**, default false from then on), `on_teachers_page` (false) to `website_landingteacher`; makes `page_id` nullable; adds the two link columns to `website_landingpage`; help-text changes | drops them |
| `0010_seed_teachers` (data) | creates the `TeachersPage` row; fills `slug` for every card from its name | sets `page_id` back to the landing page row (creating it if missing); deletes the teachers page row and its groups |
| `0011_teacher_slug` (schema) | drops `page_id`; `slug` unique and not null | re-adds `page_id` (nullable), `slug` nullable |
| `0012_teachers_menu` (data) | the «معلمان» `NavMenuItem` still at `#` → `/teachers/` | only a row still at `/teachers/` → `#` |
| `0013_hide_seed_teachers` (data) | `is_active=False` on the four seed teachers **only if untouched**: exact seed name **and** specialty, no linked teacher, no photo | re-activates only inactive rows matching the same conditions |

The schema change, the data fill and the constraint are separate migrations
so that no PostgreSQL transaction updates rows and then alters the same
table ("pending trigger events").

Verified on a scratch SQLite copy. The copy was migrated to `0008`, with:
- the four seed teachers, one of them («علی رضایی») with an edited
  specialty;
- one card linked to a teacher profile.

Then forward to `0013`, back to `0008` and forward again. At each step:
- **forward:** three seed rows inactive, the edited one still active; every
  row has a slug (`سارا-احمدی` from the linked account); `on_home` true on
  existing rows; the menu at `/teachers/`; one teachers page row;
- **back:** `page_id` = 1 on every row; all four seed rows active; the menu
  at `#`; the new tables gone.

`makemigrations --check --dry-run`: no changes.

**Rollback:** `migrate website 0008` restores the previous schema and links.
Values typed into the new fields are lost, as with any dropped column, so
back up first.

## 4. URLs, views and permissions

| URL | View | Methods | Who |
|---|---|---|---|
| `/teachers/` (`website:teachers`) | `views.teachers` | GET, HEAD (POST → 405) | public |
| `/teachers/?group=<id>` | same | | public; an unknown, inactive, empty or non-numeric id shows everyone |
| `/teachers/?partial=1` | same, renders `_directory.html` | | public (the fragment `teachers.js` swaps) |

Queries:
- **5 for the page:** the page row, the teachers with their groups, and
  site settings, nav and footer;
- **2 for the fragment.**

Both are the same with 0 or 13 teachers in 4 groups (tested).

Admin:
- «معلمان سایت» needs the usual `website.*_landingteacher` permissions;
- «صفحه معلمان» needs `website.*_teacherspage`;
- staff without them get 403 (tested);
- add and delete of the singleton are disabled.

## 5. Settings / configurable values

There are no new settings. Everything is in the admin:
- **«صفحه معلمان»:**
  - switches for the intro, filter chips and closing call to action;
  - the title, intro, list labels, empty-state text, buttons and meta;
  - the groups.
- **«معلمان سایت»:** per teacher, the two ticks, «فعال», group, order and
  content.
- **«مدیریت صفحه اصلی» → «سکشن اساتید»:** the link text and URL
  (`/teachers/`); blank either to hide the link.
- **Fixed in code:** the photo's maximum size (900 px) is `MAX_SIDE` in
  `website/images.py`.

## 6. Decisions

Approved:
- D1, D2, D3 (name kept), D5, D6, D8, D9, D10, D11, D12 as recommended;
- D4: the photo is only `photo_override` on both pages, and the name never
  falls back to the username;
- D7: yes;
- D13: ADR-025 amended.

Approval changes:
1. **Blog hook:** only the slug anchor and the commented slot. The author
   model is left to the blog plan.
2. **`0013_hide_seed_teachers`**, tested in both directions. A test also
   checks that the landing section is not rendered without an active
   `on_home` teacher.
3. **One helper (`website/images.py`)**, applied to `LandingTeacher` and
   `AboutPerson`, with the same EXIF test for both.

Resolved during implementation:
- **Inactive groups:** teachers of an inactive group are hidden on the
  teachers page (the plan's SQL filter). The admin help text on «گروه
  آموزشی» says so. Teachers with no group are always shown.
- **Group dropdown:** it lists all groups, and inactive ones are labelled
  «(غیرفعال)». Editing a teacher of a deactivated group then doesn't fail
  validation.
- **Name without letters:** a name that yields no slug characters gets
  `teacher` (then `teacher-2`…).
- **Chip placement:** the chips sit inside the intro panel. With the intro
  off, they stand alone above the list.
- **Swapping:** the fragment holds both the chips and the list. JS swaps
  each `[data-tc-swap]` block and moves focus back to the chosen chip.
- **Landing initial:** it uses `--lp-ink`, which is at least 4.2:1 on the
  landing page's teal, blue and pink blobs (white fails on pink, 2.6:1).
- **Button styles:** `teachers.css` repeats the About page's button rules
  (`.tc-btn`) and the Contact page's paper colours rather than loading
  those pages' CSS.
- **Chevron underline:** the summary's underline is on its text only.
  Rotated with the chevron, it showed as a stray bar (seen in a
  screenshot).

## 7. Tests

New in `website/test_teachers.py`:
- **view:** URL, methods, one `h1`, intro off, empty state, switches, CTA,
  escaping, unsafe links, navbar;
- **publish ticks and leavers:** on both pages, including the landing
  section being hidden when nothing is ticked;
- **fallbacks:** name and specialty fall back, the photo doesn't (initial
  shown), overrides win;
- **slug:** generation, clash, kept on rename, editable, anchor;
- **privacy:** username, national code, mobile, email, personnel code,
  birth date, address, emergency phone, profile education and experience,
  branch and avatar all hold markers. None appears on `/teachers/`, the
  fragment or `/`.
- **photos:** EXIF and GPS stripped, upright, ≤ 900 px, JPEG; transparency
  flattened; the old file removed after commit; an unchanged save keeps
  the file. The same test runs for `AboutPerson` in `test_about.py`.
- **filtering:** sections, group order, one group, unusable values, an
  inactive group, the chip threshold and switch, the flat list, the
  fragment;
- **admin:** the singleton with groups, list, search, filter, editable
  ticks, adding a teacher with a photo through the admin, name required,
  the landing admin without the inline, 403 without permission;
- **migrations:** 0010 seed and slugs, 0012 forward, reverse and an edited
  row, 0013 forward, reverse and edited rows;
- **query count:** locked at 5 (page) and 2 (fragment).

Updated tests:
- the landing tests: the seed teachers are no longer shown; the avatar
  fallback test is replaced by "never the avatar" and "never the
  username";
- the query count test uses `on_home`;
- the about menu test resets «معلمان».

No test was deleted.

| Run | Result |
|---|---|
| Baseline, `main` (worktree), full suite, PostgreSQL | Ran 781 tests, OK |
| Branch, `website`, SQLite | Ran 144 tests, OK |
| Branch, `website`, PostgreSQL | Ran 144 tests, OK |
| Branch, full suite, PostgreSQL | Ran 825 tests (+44), OK |

**Browser checks:** headless Chrome (Playwright, the system Chrome) against
scratch SQLite copies. The states:
- **deploy day:** migrations only;
- **filled:** 9 teachers in 3 groups plus one ungrouped, some without a
  photo or quote, one expansion open;
- **before:** `main`'s code on the pre-migration copy.

What was checked:
- 1280px and 375px full pages of `/teachers/`, `/teachers/?group=2` and
  `/`;
- `scrollWidth` equal to the viewport on `html`, `body` and `.app-shell`
  at both widths;
- one `h1` on every page.
- **JS:**
  - a chip fetches only `?partial=1`, swaps the list, sets the address to
    `?group=2#tc-list`, announces «۲ معلم» and keeps focus on the chip
    (`aria-current="true"`);
  - Back restores all four sections;
  - `/teachers/#سمیه-کاظمی` opens that teacher's expansion.
- **Without JS:** a chip navigates to `?group=3#tc-list` with one section.
- **Phone menu:** «معلمان» is current.
- **Reduced motion:** the expansion opens with no transition.
- **Landing before and after:** the hero differs only by the autoplaying
  carousel. In the teachers row, the three untouched seed teachers are gone,
  the edited «علی رضایی» stays, the linked teacher shows an initial, and
  the new link appears.

## 8. Discrepancies between docs and code

- `docs/apps/staff.md` and `docs/database.md` listed `national_code` on
  `Staff` (it moved to `User` in `staff` 0004–0005) and an
  `is_homeroom_teacher` field on `TeacherProfile` (it doesn't exist). Both
  are fixed.
- `docs/apps/website.md` said `ContactLocation` falls back "like
  `LandingTeacher`". That comparison is gone, since `LandingTeacher` no
  longer falls back to the avatar.

## 9. Open questions and manual steps at deploy

1. Back up, then by hand:
   - `docker compose exec web python manage.py migrate` (website 0009–0013;
     the contact and about migrations 0003–0008 are still pending too);
   - `collectstatic` (new `teachers.css` and `teachers.js`, changed
     `index.css`).
2. Expect on the landing page right after `migrate`:
   - the three invented seed teachers disappear (if untouched);
   - cards that relied on an account avatar show an initial until a photo
     is uploaded on the card.

   If no active home teacher is left, the section is hidden.
3. In the admin:
   - **«صفحه معلمان»:** add the groups; adjust the texts.
   - **«معلمان سایت»:** for each teacher who agreed:
     - upload a photo;
     - fill in the specialty, experience, a sentence and a short bio;
     - tick «نمایش در صفحه معلمان», and «نمایش در صفحه اصلی» for the few
       on the home page.

   Until then, `/teachers/` shows its empty state.
4. Office staff who edit teachers need the `landingteacher` (and
   `teacherspage`) permissions, granted by hand.
5. **Follow-ups:**
   - re-encode the About gallery and the other website images (ADR-025
     consequences);
   - the blog plan decides how an author optionally links to a teacher card
     (anchor and slot are ready);
   - the landing page's own buttons still use the brand orange (AA).
