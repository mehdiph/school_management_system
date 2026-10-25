# Report: public «درباره ما» page, and «کلاس ها» removed from the menu

**State: implemented on `feature/about-page`, not committed, not pushed, not
deployed.** The plan (`docs/plans/2026-10-about-page-plan.md`) was approved on
2026-10-25 with three changes, and those changes are applied here. Nothing was
migrated outside the test databases and scratch SQLite copies.

## 1. Summary and reasoning

`/about/` is a public page for parents choosing a school. It builds trust,
then leads to «تماس با ما». It's built like the landing and contact pages:
- an `AboutPage` singleton holds every text, photo and section switch;
- six `OrderedItem` inlines hold the repeatable content;
- everything is edited in the admin and nothing is hard-coded.

Sections:
1. hero (the only `h1`);
2. story and milestones;
3. director's words;
4. mission, vision and values;
5. «در نسل قلم، بچه‌ها…»;
6. numbers;
7. «همکاران ما»;
8. gallery;
9. branches;
10. closing call to action.

**Design.** Both skills were used. The page belongs to the public site:
- the same navbar, footer, doodle background, cream and glass panels;
- Vazirmatn;
- the shared action orange.

It spends its boldness in one place: a **blue-ink pen line** (the school is
«نسل قلم», the generation of the pen). The line runs down the story, with a
dot on each year. Where `animation-timeline: view()` is supported and motion
is allowed, it draws itself as the parent scrolls through the story, and each
dot fills as the line reaches it. That's CSS only. Everywhere else, the line is
simply drawn. The hero photo sits in an arch, a doorway, the page's
invitation to visit.

**No invented facts (ADR-025).** Content that would read as a fact is not
published on deploy day:
- milestones and numbers are seeded as **inactive examples**;
- people and photos are left empty;
- the director's words are off.

The page is still complete without them: hero, story, beliefs, highlights,
branches and CTA.

Rejected alternatives:
- one generic "content block" model, which makes the admin harder for office
  staff;
- reading `school.Branch` directly for the branches, which would ignore the
  contact page's overrides and hiding;
- a stretched SVG for the line, where dashes and the wobble distort with the
  section height. A repeated CSS mask tile keeps the wobble true at any height.
- `about.js`, because nothing needs a script.

## 2. Files

### Code

| File | Change |
|---|---|
| `website/models/about.py` | new: `AboutPage`, `AboutMilestone`, `AboutValue`, `AboutHighlight`, `AboutFact`, `AboutPerson`, `AboutPhoto` |
| `website/models/__init__.py` | exports |
| `website/admin.py` | `AboutPageAdmin` (singleton, fieldsets in page order) and six inlines |
| `website/signals.py` | about models added to `MODELS_WITH_IMAGES` (file cleanup) |
| `website/views.py` | `about` view; `_public_locations()` shared with the contact view (same filter, no behaviour change) |
| `website/urls.py` | `about/` → `website:about` |
| `website/templates/website/about.html`, `about/_person.html` | new |
| `website/static/website/css/about.css` | new |
| `website/static/website/css/index.css` | `--lp-action`, `--lp-action-hover` (token definitions only) |
| `website/static/website/css/contact.css` | `--ct-action*` now reference `--lp-action*` |

### Migrations and tests

| File | Change |
|---|---|
| `website/migrations/0006_about.py` | tables |
| `website/migrations/0007_seed_about.py` | seed (creates only) |
| `website/migrations/0008_about_menu.py` | menu changes |
| `website/test_about.py` | 31 tests |

### Docs

| File | Change |
|---|---|
| `docs/apps/website.md` | about page: models, migrations, admin, view, front end; contact.css token note |
| `docs/database.md`, `docs/database-mermaid.md` | about tables, `AboutPerson.staff` → `Staff` |
| `docs/architecture-decisions.md` | ADR-025 |
| `docs/changelog.md` | entry |
| `docs/plans/2026-10-about-page-plan.md` | the approved plan (on `main`) |
| `docs/plans/2026-10-about-page.md` | this report |

## 3. Models and migrations

| Migration | Database effect | Reverse |
|---|---|---|
| `0006_about` | seven new tables `website_about*`; FK `website_aboutperson.staff_id` → `staff_staff` (nullable, `SET_NULL`) | drops them |
| `0007_seed_about` | creates the page row, 4 values and 4 highlights (active), 3 milestones and 4 facts (inactive examples). It only fills empty lists, so re-running never duplicates | deletes the about rows |
| `0008_about_menu` | `NavMenuItem` / `FooterLink` rows with `title == «درباره ما»` and `url == "#"` → `/about/`; the `NavMenuItem` titled «کلاس ها» with `url == "#"` and active → `is_active=False` | resets only rows still at `/about/`; re-activates only an inactive «کلاس ها» still at `#` |

No existing data is modified except those menu rows, and only under their
exact conditions. «معلمان», «وبلاگ», «مقاله» and «سوالات متداول» are
untouched.

**Verification:**
- `makemigrations --check --dry-run`: no changes.
- Scratch SQLite copy of the pre-about state:
  - forward to `0008`: «کلاس ها» inactive, «درباره ما» nav and footer at
    `/about/`, seven tables, 1/4/4/3/4 rows as expected;
  - back to `0005`: menu identical to before, about tables gone;
  - forward again: same as the first forward.
- Tests cover both data migrations' functions forward and back, including
  edited rows that must be left alone.

**Rollback:** `migrate website 0005`. Caveat (documented): if an admin had
deactivated «کلاس ها» by hand before `0008`, the reverse turns it back on.

## 4. URLs, views and permissions

- `/about/`, `website:about`, public, `require_safe` (GET/HEAD; POST → 405).
- Read-only. Nobody gets a 403; there is nothing to protect.
- 11 queries whatever the number of items (asserted exactly and as flat):
  - page row;
  - six section lists (only for enabled sections);
  - locations;
  - site settings, nav and footer.
- Admin: **صفحه درباره ما** for staff with the usual `website` change
  permissions. Add and delete are disabled (singleton).

## 5. Settings / configurable values

No new settings. Everything is in the admin (**صفحه درباره ما**):
- texts, photos and links;
- the ten section switches;
- the inline lists.

The branches section uses the contact page's locations. Their names and
addresses are edited under «صفحه تماس با ما», or on the branch itself.

## 6. Decisions taken

Approved as planned: D1, D2, D4, D6, D7, D8, D10, D11. D5 / D12: ADR-025.

Changes required at approval, all applied:
1. **D3, privacy.** `AboutPerson.photo_url` is **only** `photo_override`:
   - no fallback to the account avatar; without a photo, the name's initial;
   - the name may fall back to the account's first and last name (never the
     username);
   - every photo field's help text says photos here are public;
   - tested with a linked staff member who has an avatar. I also confirmed
     the test fails if an avatar fallback is added.
2. **«همکاران ما» is for leadership and office staff only.** This is stated
   in the inline's admin title and the fieldset note. «معلمان» is untouched.
3. **D9, one shared action colour.** `--lp-action` / `--lp-action-hover` are
   defined in `index.css`, used by `about.css`, and referenced by
   `contact.css`. No landing rule changed. Verified: every element's computed
   style on `/` and `/contact/`, at 1280px and 375px, is identical with
   `main`'s CSS and the branch's CSS (169 and 145 elements).

   Pixel diffs of full-page screenshots are identical on desktop. On phone
   they differ, but two runs with the *same* CSS differ in the same areas
   (the teachers carousel, the footer), so that's run-to-run noise.

Resolved during implementation:
- **Hero fallback image:** `happy_young_boy.png` (a child with a backpack in
  the doorway arch) rather than a classroom picture. All four classroom
  pictures are used by the highlights.
- **Hero title:** the default has no forced line break; `text-wrap: balance`
  splits it evenly. A `\n` default left a one-word last line at 1280px.
- **Story layout:** at ≥ 992px the story's heading sits beside the line, like
  a chapter title (sticky). Below that, it's above.
- **Highlights:** 4 columns from 992px (the plan said 1200px); 2 from 576px.
- **Quote mark:** «, which renders mirrored in RTL, exactly like the opening
  mark of Persian text typed in the admin. Checked in Chrome.
- `AboutValue` uses `related_name="belief_values"`, so it doesn't shadow
  `QuerySet.values`.
- The branches link («مسیریابی و تلفن», `/contact/`) is two editable fields,
  not a hard-coded URL.

## 7. Tests

`website/test_about.py`, 31 tests:
- **View:** URL name, seeded content, one `h1`, HEAD/POST.
- **Sections:** active items; every switch; story with only text or only
  milestones; empty sections not rendered; inactive items.
- **Content:** the quote, the CTA's second button (needs text **and** URL),
  escaping, `javascript:` refused on all four link fields.
- **Navigation:** «درباره ما» current and «کلاس ها» gone.
- **Query count:** exact and flat.
- **Branches:** the contact locations, overrides, inactive location or
  branch.
- **People:** name fallback (never the username), avatar never published,
  overrides win, inactive staff and rows hidden, `clean()`.
- **Admin:** singleton with all six inlines, autocomplete, the public-photo
  and teachers notes, add/delete 403.
- **Image files:** cleanup on replace and delete, bundled fallbacks.
- **Migrations:** seed once plus reverse, about links forward/reverse with an
  edited row untouched, «کلاس ها» deactivated (not deleted) and reversed,
  linked or renamed rows left alone.

| Run | Result |
|---|---|
| Baseline, `main` (worktree), full suite, PostgreSQL | Ran 750 tests, OK |
| Branch, `website`, SQLite | Ran 100 tests, OK |
| Branch, `website`, PostgreSQL | Ran 100 tests, OK |
| Branch, full suite, PostgreSQL | Ran 781 tests (+31), OK |

**Browser checks:** headless Chrome (Playwright in a scratch venv, the
system Chrome) against a scratch SQLite copy. Two states:
- **deploy day:** seed only;
- **filled:** milestones and numbers activated, the quote on, four people
  without photos, five gallery photos.

What was checked:
- 1280px and 375px full pages, both states.
- `scrollWidth == 375` for `html`, `body` and `.app-shell`. The only
  elements outside the viewport are the closed nav drawer's, as on the other
  public pages.
- One `h1`.
- The phone nav drawer: «درباره ما» is current, «کلاس ها» is gone.
- The pen line part-drawn at two scroll positions, at 1280px (window
  scroller) and 375px (`.app-shell` scroller).
- The fully drawn line under `prefers-reduced-motion: reduce`.

## 8. Discrepancies between docs and code

- None found in the parts this task touched. My first draft of ADR-025 said
  the public site never shows account avatars. That's not true:
  `LandingTeacher.photo_url` falls back to `user.avatar_url` on the landing
  page. ADR-025 now says so and leaves it for the teachers page task.

## 9. Open questions and manual steps at deploy

1. Back up, then by hand:
   `docker compose exec web python manage.py migrate` (website 0006–0008)
   and `collectstatic` (new `about.css`, changed `index.css`/`contact.css`).
2. In the admin, **صفحه درباره ما**:
   - write the real story;
   - edit the example milestones and numbers and tick «فعال» (or delete
     them);
   - add the leaders and office staff, with photos only where the person
     agreed;
   - upload real school photos, with parents' consent wherever children
     appear;
   - get the director's words approved, fill in the name, and switch
     «نمایش سخن مدیر» on;
   - replace the bundled hero picture with a real one.
3. **Follow-ups:**
   - the teachers page (and whether the landing page's teacher cards should
     stop falling back to account avatars, per ADR-025);
   - the landing page's own buttons still use the brand orange, which fails
     AA under white text; they can switch to `--lp-action`;
   - the CTA's second button is ready for registration («ثبت‌نام» + its URL)
     once that page exists.
