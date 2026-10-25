# Plan: public «معلمان» page

Status: **approved 2026-10-25** with the changes below. Implementation goes on
`feature/teachers-page`, created from `main` after this update.

## Approval (2026-10-25)

Approved as recommended:
- D1, D2, D5, D6, D8, D9, D10, D11, D12;
- D3, keeping the model name `LandingTeacher`;
- D4: the photo is `photo_override` only, with no avatar fallback, on both
  pages, and the name never falls back to the username;
- D7: yes;
- D13: amend ADR-025, no new ADR.

Changes to the plan (they supersede the text below where they differ):

1. **Blog hook.** The blog's author model is **not** decided here. Blog
   authors will include counselors and supervisors who aren't public
   teachers. This task keeps only:
   - the stable slug, used as the card's anchor;
   - the commented «نوشته‌های …» slot in the card's expansion.

   The blog plan will decide how an author optionally links to a
   `LandingTeacher` card. The statement in D8 that `blog.Post.author` would
   be an FK to `LandingTeacher` is withdrawn.
2. **The four invented seed teachers** from `0002` contradict ADR-025.
   - A reversible data migration, `0013_hide_seed_teachers`, sets
     `is_active=False` **only on untouched seed rows**. A row counts as
     untouched when it has the exact seed `name_override` **and**
     `specialty_override`, no linked teacher and no `photo_override`. Rows an
     admin has edited are left alone.
   - The reverse re-activates only those same rows.
   - Both directions are tested.
   - A test confirms that the landing teachers section is simply not
     rendered when no row is both active and `on_home`.
3. **D7, one shared helper.** The re-encoding lives in one helper,
   `website/images.py`, and is applied now to both `LandingTeacher` and
   `AboutPerson.photo_override` (same GPS and metadata risk). The same EXIF
   test runs for `AboutPerson`. The About gallery and the other website
   images stay a follow-up.

Skills: both were loaded with the Skill tool before planning.
- **`teachlog-workflow`**: this plan follows its read → plan → approve order.
  Only this file is published to `main`.
- **`frontend-design`**: it shaped §3. I wrote a compact token system
  (colour, type, layout, principles), then checked it against the skill's
  list of generic defaults and revised what matched (§3.4). The boldness is
  spent in one place: the teacher's own words, written in red pen in a
  notebook margin. Everything else reuses the About and Contact pages'
  vocabulary.

Read before planning:
- `CLAUDE.md`, `.claude/CLAUDE.md`;
- `docs/apps/website.md`, `docs/apps/staff.md`, `docs/database.md`,
  `docs/database-mermaid.md`, `docs/changelog.md`;
- ADR-015 (partial fragments), ADR-021 (no CDN), ADR-024, ADR-025;
- all of `website/`: models, admin, views, urls, signals, validators,
  context processor, template tags, templates, CSS, JS, migrations
  0001–0008, `tests.py`, `test_contact.py`, `test_about.py`;
- the About and Contact plans and reports in `docs/plans/`;
- `staff/models/` (`Staff`, `TeacherProfile`, `TeacherAssignment`),
  `staff/admin.py`, `accounts/avatars.py`, `accounts.User.avatar_url`,
  `school/models/subject.py`, `supervisor/views.py` (`?partial=1`).

---

## 1. Findings, risks and surprises

### 1.1 How `LandingTeacher` works today

- It's a `TabularInline` on «مدیریت صفحه اصلی», with an FK `page` to the
  `LandingPage` singleton (`related_name="teachers"`).
- `teacher` is an optional FK to `staff.TeacherProfile` (`SET_NULL`). The
  overrides win when filled in:
  - `display_name`: `name_override`, else the user's first and last name,
    **else the username**;
  - `photo_url`: `photo_override`, else **the account avatar**
    (`user.avatar_url`);
  - `display_specialty`: `specialty_override`, else
    `TeacherProfile.field_of_study`.
- Cards linked to a teacher whose `Staff` is inactive (someone who left) are
  **still shown**.
- The landing view loads them in one query
  (`select_related("teacher__staff__user")`), and a test locks that.

### 1.2 Privacy

1. **The avatar fallback contradicts ADR-025.** ADR-025 says a person's
   photo is published only when uploaded for that purpose, and it names
   `LandingTeacher` as the exception "to be revisited with the teachers
   page". Your brief says "keep the fallback to `TeacherProfile` for
   name/photo/specialty". These disagree on the photo, so it's **D4** for
   you to decide. I recommend dropping the avatar fallback. An account
   avatar is uploaded for the internal panels (the teacher's own choice, a
   256 px square) and was never meant to be public.
2. **The username fallback** publishes an internal login (`t-12`,
   `ahmadi.s`). The About page already refuses it (`AboutPerson`). I'll do
   the same here.
3. **What sits one join away from a card**, and must never be rendered:
   - `User`: username, national code, mobile, email, avatar;
   - `Staff`: personnel code, birth and hire dates, address, emergency
     phone;
   - `TeacherProfile`: `education` and `teaching_experience` (HR fields);
   - `TeacherAssignment`: branch and year;
   - classes and timetable.

   The template gets only the card's `display_*` properties and its own
   editorial fields. It never touches `card.teacher`. A test fills every one
   of those fields with a marker value and asserts that none of them
   appears on `/teachers/` or `/`.
4. **Uploaded photos keep their metadata.** Website images are only checked
   for extension and size (`IMAGE_VALIDATORS`). Unlike account avatars
   (`accounts/avatars.py`), they're stored byte for byte. A teacher's photo
   taken with a phone at home can carry the **GPS position in its EXIF**.
   **D7** proposes re-encoding teacher photos on upload. The About page's
   photos have the same issue; that's a follow-up (§7).
5. **Leavers.** A card linked to an inactive `Staff` is hidden on both pages
   (D5), as `AboutPerson` already is.
6. **The seeded landing teachers are invented**: «علی رضایی»، «سعید
   محمدی»، «ماریا کریمی»، «ندا حسینی», each «استاد …», from
   `0002_seed_content`. They are live on the landing page unless an admin
   has replaced them. I don't touch existing rows. Because publishing on the
   new page is an explicit tick that defaults to off (D2), they won't appear
   on `/teachers/`. The report will recommend replacing them.
7. **Search engines.** Published teachers become findable by name. That's
   the school's choice, made when it publishes each teacher. The admin help
   text says to publish a teacher (and especially a photo) only with their
   agreement.

### 1.3 Other findings

8. **`field_of_study` is the degree subject, not what someone teaches.**
   For example, «مهندسی کامپیوتر» for the robotics teacher, or «علوم
   تربیتی» for a homeroom teacher. The fallback stays, as the brief asks,
   but the help text recommends filling in «عنوان تخصص»
   (`specialty_override`).
9. **The tabular inline won't scale.** With a bio, a quote, education and a
   photo per teacher, 20–40 teachers in one inline on «مدیریت صفحه اصلی»
   would make a very long form with one file input per row. **D3** moves the
   list to its own admin page.
10. **The navbar** highlights an item when `item.url == request.path`.
    `/teachers/?group=3` still has the path `/teachers/`, so «معلمان» stays
    highlighted while filtering.
11. **«معلمان» is a nav row only.** It has the exact title `معلمان` and is
    still `#` in the seed. There is no footer row with that title, so the
    footer is unaffected.
12. **Deploy day.** No teacher is published on the new page until an admin
    ticks one, so the page needs a real empty state (D9). The nav and the
    landing link will point at it from the moment of `migrate`.
13. **Postgres "pending trigger events".** Filling the new `slug` column and
    then altering the same table in one transaction fails on PostgreSQL.
    The schema change, the data fill and the constraint go in **separate
    migrations** (§4.1).
14. **Docs vs code** (to fix in the docs on the branch, §4.7):
    - `docs/apps/staff.md` lists `national_code` on `Staff` (it moved to
      `User` in `staff` 0004–0005), and lists `is_homeroom_teacher` on
      `TeacherProfile` (that field doesn't exist);
    - `docs/database.md` §TeacherProfile lists `is_homeroom_teacher` too,
      and §Staff lists `national_code`.

---

## 2. Decisions to confirm

**D1. One list or two? Recommended: extend `LandingTeacher`, one list.**
The landing row and the teachers page show the **same rows**. A teacher is
entered once, with one photo and one name, and two ticks say where they
appear.

The alternative was a separate `TeacherProfilePage` model. Then a teacher on
both pages would be two rows that drift apart (a photo updated in one place
only), and the future blog author would have two identities to choose
between.

**D2. Who is published where.** Recommended: `LandingTeacher` gets two
placement ticks, and `is_active` stays the master switch, as on every other
website row:

| Field | Admin label | Existing rows | New rows |
|---|---|---|---|
| `on_teachers_page` | «نمایش در صفحه معلمان» | **off** | **off** |
| `on_home` | «نمایش در صفحه اصلی» | **on** (landing unchanged) | off |
| `is_active` (existing) | «فعال» (off = hidden everywhere, ticks kept) | unchanged | on |

So nobody appears on `/teachers/` until an admin ticks them, and the
landing page looks the same on deploy day. A new teacher is ticked onto the
home page on purpose too, which keeps the home carousel short. The admin
list shows both ticks as editable columns.

**D3. Admin.** Recommended:
- a new **«معلمان سایت»** page, a regular `ModelAdmin` for `LandingTeacher`:
  - list columns: photo thumbnail, name, specialty, group, the two ticks,
    «فعال», order; the ticks and order are editable in the list;
  - filters: group, the ticks, «فعال»;
  - search by name;
  - one change form per teacher, with fieldsets «معلم», «نمایش», «عکس»,
    «معرفی».
- `LandingTeacherInline` is removed from «مدیریت صفحه اصلی». Its «سکشن
  اساتید» fieldset gets a note linking to «معلمان سایت» and the new link
  fields (D10).
- the `page` FK becomes meaningless, since every row points at
  `LandingPage` pk 1, and is dropped reversibly (§4.1).
- **The model keeps its name `LandingTeacher`.** Only its verbose names
  change («معلم سایت» / «معلمان سایت»). Renaming the class (pinned
  `db_table`, `RenameModel`, permission codename migration) buys only a
  nicer name, and it churns the tests, signals and permissions. Say if you'd
  rather rename it now, for example to `PublicTeacher`, before the blog
  points at it.

**D4. Fallbacks.** Recommended, given the conflict in finding 1:
- **name:** `name_override`, else the user's first and last name. **Never
  the username.** `clean()` requires a name from one of the two.
- **specialty:** `specialty_override`, else `field_of_study`, as today.
- **photo:** **`photo_override` only.** Without one, the card shows the
  name's first letter in the portrait frame. This applies to **both pages**:
  the landing carousel shows the initial too (a small template change).
  Consequence: a landing card that relies on an account avatar today loses
  it on deploy, until a photo is uploaded on the card. ADR-025's
  parenthetical is updated to say the exception is gone.

  The alternative, if you prefer the brief's wording: keep the avatar
  fallback on both pages. I'd then still re-encode it (D7 doesn't cover
  avatars; they're already re-encoded).
- **experience and education: no fallback** to `TeacherProfile` (the brief
  limits fallbacks to name, photo and specialty, and ADR-025 lets only named
  fields follow a school record). Both are typed on the card.

**D5. Leavers.** Recommended: a card linked to an inactive `Staff` is hidden
on both pages. This changes the landing page slightly (today it still shows
them) and matches `AboutPerson`.

**D6. Content per teacher.** All fields optional except the name; text is
shown as typed (ADR-025):

| Field | Type | Shown |
|---|---|---|
| photo (`photo_override`) | image, 600×800 portrait suggested | in the portrait frame; else the initial |
| name, specialty | existing fields | always |
| `group` | FK `TeacherGroup`, `SET_NULL` | as the section the card sits in, and the filter |
| `experience` | text, 30 chars, e.g. «۱۲ سال» | «سابقه تدریس: ۱۲ سال» |
| `education` | text, 120 chars | in the expansion |
| `bio` | text, 400 chars | in the expansion |
| `quote` | text, 200 chars, «سخن یا باور آموزشی» | on the card, as the red-pen note (§3) |
| `slug` | unique, filled automatically, editable | the card's `id`, for links (D8) |

Experience is free text rather than an integer, like `AboutFact.value`, so
«بیش از ۲۰ سال» works. It's never computed from `hire_date` or
`teaching_experience`.

**D7. Photos are re-encoded on upload.** Recommended: when a new
`photo_override` is saved, it is decoded with Pillow, turned upright (EXIF
orientation), scaled down to fit 900 px on the long side (never up),
flattened onto white if it has transparency, and re-encoded as a fresh
JPEG. That drops every bit of metadata, GPS included, and anything hidden
in the file.

This happens in `LandingTeacher.save()`, only for an uncommitted (just
uploaded) file, so every path is covered (admin, shell, tests). It reuses
`accounts/avatars.py`'s approach, but with no square crop: teacher portraits
are 3:4. The help text says so. The About page's photos are left for a
follow-up (§7), unless you want them in this task.

**D8. Detail page or in-page expansion? Recommended: an in-page expansion,
no detail pages now.**
- Each card shows the face, name, specialty, experience and the red-pen
  note. A native `<details>` («درباره سارا احمدی») holds the bio and
  education. It's keyboard and screen-reader accessible with no JS, and the
  browser's find-in-page searches it.
- With a 400-character bio and a one-line quote, a page per teacher would be
  thin. It would make each teacher an indexable page of its own, and add a
  second template and URL to maintain.
- Each card has a stable `id` from its `slug`, for example
  `/teachers/#سارا-احمدی`, so a card can be linked to today. A small script
  opens the `<details>` of a linked card.

**Blog hook (not built; see Approval, change 1):**
- each card has a stable anchor (`/teachers/#<slug>`) that a byline can link
  to;
- the card's expansion has a commented slot for a «نوشته‌های …» link;
- how a blog author optionally links to a card is for the blog plan to
  decide. Nothing here fixes the author model.

The slug is generated from the display name (`slugify(..., allow_unicode=True)`,
Persian kept, ZWNJ dropped). On a clash, `-2`, `-3`… are added. The admin
can edit it; it's never regenerated once set.

**D9. Groups and filtering.** Recommended: a small editorial
**`TeacherGroup`** model: a title (e.g. «آموزگاران پایه», «زبان انگلیسی»,
«هنر», «ورزش», «رباتیک و رایانه»), order and «فعال», edited as an inline
on «صفحه معلمان». It's not `school.Subject`: a homeroom teacher teaches many
subjects, and subject names are internal data (ADR-025).

- **«همه»** (no filter): one section per group, in group order, each with
  its `h2`. Teachers with no group come last under «سایر معلمان» (editable).
  With no groups in use, it's one flat list under a visually hidden `h2`.
- **Filter chips** «همه» + each group that has at least one published
  teacher. They're shown only when two or more groups are in use, and each
  one is a plain link to `?group=<id>#teachers`. Without JS, the page
  reloads on the list. An unknown, inactive or empty group shows everyone
  (status 200, no chip current).
- **JS enhancement** (`teachers.js`, ADR-015): a click fetches the same URL
  with `&partial=1`, swaps only the list region, updates the address
  (`pushState`, back and forward work), and announces «۸ معلم» in a polite
  live region. Focus stays on the chip.
- The **empty state** (no published teacher yet), editable: «فهرست معلمان
  به‌زودی در این صفحه منتشر می‌شود.» The intro and the CTA still render.

The alternative was in-page anchors instead of a filter. It's simpler, but
the brief asks for a query-string filter.

**D10. Page texts, switches and links (`TeachersPage` singleton, admin
«صفحه معلمان»).**
- **switches:** `show_intro`, `show_filter`, `show_cta`. With the intro off,
  the `h1` stays, visually hidden.
- **intro:** title «معلمان نسل قلم» (the `h1`); text «با معلمانی آشنا شوید
  که هر روز در کلاس‌ها کنار فرزندان شما هستند.» It's general on purpose and
  claims no number or programme.
- **list:** `filter_label` (visually hidden nav name, «گروه‌های آموزشی»),
  `all_text` («همه»), `other_group_title` («سایر معلمان»), `empty_text`.
- **CTA:** «از نزدیک با مدرسه آشنا شوید» / «برای بازدید از مدرسه و گفت‌وگو
  درباره ثبت‌نام، با دفتر مدرسه هماهنگ کنید.» / «تماس با مدرسه» →
  `/contact/`, and an optional second button (empty; shown only with both
  text and link).
- **SEO:** `meta_title` («معلمان»), `meta_description`.
- **The landing page:** `LandingPage.teachers_link_text` («آشنایی با همه
  معلمان») and `teachers_link_url` (`/teachers/`) under the carousel, shown
  only with both filled in. The link uses `--lp-action` (AA), not the brand
  orange.

The intro, the CTA and the `TeachersPage` row come from a **create-only
seed migration**, with texts held as model defaults like the About page.
No groups are seeded: I don't know the school's departments. The admin adds
them, and until then the list is flat with no chips.

**D11. Menu.** As requested: a reversible data migration (`0012`) points
`NavMenuItem` rows titled «معلمان» **and** still at `#` to `/teachers/`. The
reverse resets only rows still at `/teachers/`. It's the same shape as
`0005` and `0008`.

**D12. URL and view.** `/teachers/`, `website:teachers`, `require_safe`
(GET/HEAD). Queries:
1. `TeachersPage`;
2. the published teachers with `select_related("teacher__staff__user",
   "group")`, filtered in SQL to active rows, `on_teachers_page`, linked
   staff null or active, and group null or active.

Groups for the chips and sections are derived from those rows in Python, so
there's no query per teacher or group. The navbar and footer add their
usual 3. That's **5 queries whatever the number of teachers and groups**,
locked with `assertNumQueries`. The landing view switches to
`LandingTeacher.objects.filter(is_active=True, on_home=True, …)` and keeps
its flat count.

**D13. ADR.** No new ADR. I'll **amend ADR-025**:
- the `LandingTeacher` avatar exception is gone (if D4 is approved);
- publishing a person on the public site is an explicit, per-person choice
  (D2);
- uploaded photos of people are re-encoded without metadata (D7).

Say if you'd rather have that as ADR-026.

---

## 3. Design

### 3.1 The subject and the direction: «خودکار قرمز معلم»

Who reads it: parents choosing a primary school, mostly on phones. Its job:
put faces and names to the school, and give each teacher one sentence of
their own.

The site already speaks in a schoolchild's stationery. The About page tells
the school's story in **a pupil's blue ballpoint**. The Contact page's form
is **a notebook page** with a margin line. The teachers page completes the
set with **the teacher's red pen**, the pen that writes «آفرین» in the
margin of every Iranian child's notebook.

**The memorable thing:** each teacher's own sentence (their quote or
teaching belief) is written **in red ink on a strip of notebook paper**: the
Contact page's paper, rules and margin line. The words sit right of the
margin, like a teacher's note beside the homework, and a small hand-drawn
red tick closes the note. That's the one element that performs, and it's
the one thing on the page that is red.

Everything else is quiet and borrowed from the family:
- the doodle background and the glass and cream panels;
- the landing page's **blob portrait frame** (the shape of
  `.instructor-img-wrapper`), so a face looks the same on the home page and
  here;
- Vazirmatn;
- `--lp-action` for buttons, links and specialties;
- the About page's paper CTA panel.

There's **no motion** that the visitor didn't cause. The only movement is
the `<details>` opening, with a short height transition where the browser
supports `::details-content` and motion is allowed. The filter swap is
instant.

### 3.2 Tokens

New, in `teachers.css` only:

| Token | Value | Role | Contrast |
|---|---|---|---|
| `--tc-redpen` | `#b3202e` | the note's ink and its tick, nothing else | 6.4:1 on paper, 6.0:1 on cream |
| `--tc-paper` | `var(--ct-paper)` → `#fffaf6` | the note strip | — |
| `--tc-rule` | `#f0dccd` (= `--ct-rule`) | the note's ruled lines | decorative |
| `--tc-margin` | `rgba(179, 32, 46, 0.45)` | the note's margin line (red, like a real notebook) | decorative |

`contact.css` isn't loaded (17 KB of form rules), so the two paper values
are repeated with a comment pointing to `--ct-*`. Hoisting them into
`index.css`, as was done with `--lp-action`, is an option if you'd rather
have that.

Existing tokens, used as they are:
- `--lp-cream` (intro panel), `--lp-glass` (list panel);
- `--lp-peach`, `--lp-yellow`, `--lp-sand`: portrait backgrounds, cycled,
  never under text;
- `--lp-heading` (`h2`s, the initial: 8.2:1 on peach), `--lp-ink` (names);
- `--lp-action` and `--lp-action-hover`: specialty, links, the current chip,
  buttons;
- radii, shadows, `--lp-touch`.

**Type: Vazirmatn only** (the one vendored family; ADR-021). The note's
"hand" comes from the ink, the paper and the weight, not from a second
font: there's no OFL Persian handwriting face worth vendoring for one
sentence per teacher.

| Role | Size | Weight | Line height |
|---|---|---|---|
| `h1` | `clamp(1.55rem, 1.1rem + 1.9vw, 2.45rem)` (the About hero's) | 800 | 1.55 |
| `h2` (group) | `clamp(1.25rem, 1.1rem + 0.6vw, 1.5rem)` | 800 | 1.5 |
| teacher name `h3` | 1.1rem | 800 | 1.6 |
| specialty | 0.95rem, `--lp-action` | 700 | 1.6 |
| red-pen note | 1.05rem | **400** (a voice, not a heading) | 2 (one rule per line) |
| experience, bio, education | 0.95rem, `#555` (7.2:1 on paper) | 400–500 | 1.9 |

Nothing is smaller than 0.875rem. Text is start-aligned (right) throughout;
the only centred blocks are the CTA and, on phones, the intro, as on the
About page.

### 3.3 Layout and principles

- **Intro:** a short cream panel; the `h1`, one paragraph, and the chips
  directly under it, so filtering is in reach before the first face.
- **The list:** one glass panel per group. Inside, a grid of teachers with
  **no card boxes**: a portrait in the blob frame, then the name, specialty
  and experience, then the note strip, then «درباره …».
  - Columns: 1 on phones; 2 from 576px; 3 from 992px; 4 from 1200px.
  - `align-items: start`, so opening one teacher's expansion doesn't stretch
    the others in the row.
- **On phones**, a teacher is a row: a 96 px portrait at the start (right),
  with the name, specialty and experience beside it. The note and the
  expansion run full width below. The list reads like a class register
  without the chrome of one.
- **CTA:** the About page's paper panel, centred.

Principles:
1. The red pen is the only decoration that performs. If a teacher has no
   quote, there's no note: no empty paper.
2. Nothing invented: no seeded teachers, groups, numbers or claims. Empty
   means hidden, or the written empty state.
3. Semantics:
   - one `h1`;
   - `<main>`, and a `<section aria-labelledby>` per group;
   - teachers in a `<ul>`, each an `<article>` with an `h3`;
   - the quote is a `<blockquote>` inside a `<figure>`, with a visually
     hidden `<figcaption>` naming the teacher;
   - experience and education in a `<dl>`;
   - the chips are a `<nav>` of links, the current one `aria-current="true"`.
4. Logical properties only, so the note's margin line sits on the
   inline-start side and mirrors correctly.
5. The portrait `alt` is empty (the name is the heading right below);
   initials are `aria-hidden`.

### 3.4 What I changed after checking against the generic defaults

- **First sketch:** white rounded cards with the same soft shadow, one per
  teacher: the "SaaS card kit", and also the default "team page". **Now**
  there are no card boxes. Faces sit on the group's glass panel, and the
  only paper on the page is the red-pen note, so the note stands out
  instead of competing with 30 boxes.
- **First sketch:** a hero with three overlapping teacher photos and a
  stat («۳۵ معلم»). That's a computed number (ADR-025) and the default
  stat hero. **Now** the intro is text and chips, and the faces right below
  are the hero.
- **First sketch:** «ریاضی · ۱۲ سال · کارشناسی ارشد» as one meta line.
  That's the middle-dot tell, and it mixes three kinds of fact. **Now** the
  specialty is its own line, and experience and education are a labelled
  `<dl>`.
- **First sketch:** a hover lift on every portrait and fade-in rows. **Now**
  nothing moves on its own; only the expansion moves, because the visitor
  opened it.
- **First sketch:** the note in a second, "handwritten" font. That would
  mean a CDN or a large vendored file for one sentence. **Now** it's the
  ink, the paper and the weight.
- No eyebrow labels, no `→` on links, no numbered markers: teachers aren't
  a sequence.

### 3.5 Wireframe: desktop (1280px)

```
┌ public navbar (shared) ── «معلمان» highlighted ──────────────────────────┐
├──────────────────────────────────────────────────────────────────────────┤
│ INTRO (cream panel)                                                       │
│   معلمان نسل قلم                                         (h1)            │
│   با معلمانی آشنا شوید که هر روز در کلاس‌ها کنار فرزندان شما هستند.        │
│   ( همه )  ( آموزگاران پایه )  ( زبان انگلیسی )  ( هنر )  ( ورزش )        │
│     ▲ current: filled --lp-action                                         │
├──────────────────────────────────────────────────────────────────────────┤
│ آموزگاران پایه                                    (h2, glass panel)       │
│                                                                           │
│   ╭──────╮          ╭──────╮          ╭──────╮          ╭──────╮          │
│   │ blob │          │ blob │          │  س   │ (initial)│ blob │          │
│   ╰──────╯          ╰──────╯          ╰──────╯          ╰──────╯          │
│   سارا احمدی         مریم نوری          سمیه کاظمی        …                 │
│   آموزگار پایه دوم   آموزگار پایه اول   آموزگار پایه سوم                   │
│   سابقه تدریس: ۱۲ سال                                                     │
│  ┌─────────────────┐ ┌─────────────────┐                                  │
│  │┆ «هر بچه راه    │ │┆ «کلاس ما جای   │   ← red ink on ruled paper,        │
│  │┆  خودش را دارد؛ │ │┆  پرسیدن است.» ✓│     red margin line at the right   │
│  │┆  ما همراهیم.» ✓│ └─────────────────┘                                  │
│  └─────────────────┘                                                      │
│   ▸ درباره سارا احمدی  ▸ درباره مریم نوری                                  │
│     (open:) bio, two to four lines                                        │
│             تحصیلات: کارشناسی ارشد آموزش ابتدایی                           │
│             [slot: «نوشته‌های سارا احمدی» when the blog exists]           │
├──────────────────────────────────────────────────────────────────────────┤
│ زبان انگلیسی                                       (h2, glass panel)       │
│   …                                                                       │
├──────────────────────────────────────────────────────────────────────────┤
│ سایر معلمان  (only if some have no group)                                 │
├──────────────────────────────────────────────────────────────────────────┤
│ CTA (paper panel, centred)                                                │
│   از نزدیک با مدرسه آشنا شوید                                            │
│   one sentence                                                            │
│   [ تماس با مدرسه ]                                                       │
├ footer (shared) ─────────────────────────────────────────────────────────┤
```

### 3.6 Wireframe: phone (375px)

```
┌ logo                ☰ ┐
│ INTRO (centred)        │
│  معلمان نسل قلم        │  h1
│  one paragraph         │
│ (همه) (آموزگاران پایه) │  chips wrap onto lines;
│ (زبان) (هنر) (ورزش)    │  no sideways scroll, 44px tall
├────────────────────────┤
│ آموزگاران پایه     h2  │
│ ╭────╮ سارا احمدی      │  96px portrait at the start (right),
│ │blob│ آموزگار پایه دوم │  text beside it
│ ╰────╯ سابقه: ۱۲ سال    │
│ ┌────────────────────┐ │
│ │┆ «هر بچه راه خودش   │ │  note, full width
│ │┆  را دارد.» ✓       │ │
│ └────────────────────┘ │
│ ▸ درباره سارا احمدی    │  44px summary row
│ ────────────────────── │
│ ╭────╮ مریم نوری       │
│ …                      │
├────────────────────────┤
│ CTA, full-width button │
└ footer ────────────────┘
```

Breakpoints are the site's (576 / 768 / 992 / 1200px), mobile-first. Grid
children get `min-width: 0` and names get `overflow-wrap: anywhere`.
Overflow is checked with `scrollWidth` on `html`, `body` and `.app-shell`.

---

## 4. Implementation outline

### 4.1 Models and migrations

`website/models/teachers.py` (new):
- `TeachersPage(SingletonModel)`: the fields in D10.
- `TeacherGroup(OrderedItem)`: `page` FK → `TeachersPage`
  (`related_name="groups"`) and `title` (80).

`website/models/landing.py`, `LandingTeacher`:
- **new fields:** `group` (FK `TeacherGroup`, null, `SET_NULL`,
  `related_name="teachers"`), `slug`, `experience`, `education`, `bio`,
  `quote`, `on_home`, `on_teachers_page`;
- **removed:** `page`;
- **verbose names:** «معلم سایت» / «معلمان سایت»; help texts on photo
  consent, metadata removal and the specialty fallback;
- **`display_name`:** never the username;
- **`photo_url`:** override only (D4);
- **new properties:** `initial`, `has_details`;
- **`clean()`:** requires a name;
- **`save()`:** fills the slug (D8) and re-encodes a new photo (D7).
- The "who is published" filters live in `website/selectors.py` (new), so
  the views stay thin (§4.3).

`LandingPage`: `teachers_link_text`, `teachers_link_url`.

Migrations. They're split so that no PostgreSQL transaction both updates
rows and alters the same table (finding 13):

| Migration | Kind | Contents | Reverse |
|---|---|---|---|
| `0009_teachers` | schema | create `TeachersPage`, `TeacherGroup`; add the new `LandingTeacher` fields (`slug` nullable, not unique yet; `on_home` added with default True, then its default set to False; `on_teachers_page` False); make `page` nullable; add the landing link fields | drops them |
| `0010_seed_teachers` | data | create the `TeachersPage` row (`get_or_create`); fill `slug` for rows without one | resets `page` to the `LandingPage` row on rows where it's null (creating that row if missing), and deletes the `TeachersPage` row and its groups |
| `0011_teacher_slug` | schema | remove `page`; make `slug` unique and not null | re-adds `page` nullable; `slug` nullable |
| `0012_teachers_menu` | data | «معلمان» rows still at `#` → `/teachers/` (D11) | only rows still at `/teachers/` → `#` |

No existing row's content is changed. `0009` adds columns, `0010` fills the
new `slug` column and creates one new row, and `0012` changes only the
`#` link the brief names. `page` is dropped, but its value was always the
singleton's pk and the reverse restores it.

### 4.2 Admin (`website/admin.py`)

- **`TeachersPageAdmin(SingletonAdmin)`**, «صفحه معلمان»:
  - `TeacherGroupInline` (tabular: title, order, «فعال»);
  - fieldsets: «نمایش سکشن‌ها», «بالای صفحه», «فهرست», «دعوت پایانی»,
    «سئو»;
  - a link to «معلمان سایت» in the description.
- **`LandingTeacherAdmin`**, «معلمان سایت», as in D3:
  - `autocomplete_fields=("teacher",)`;
  - `list_select_related=("teacher__staff__user", "group")`;
  - the group dropdown lists active groups.
- **`LandingPageAdmin`**: the inline is removed; «سکشن اساتید» gets the two
  link fields and a note linking to «معلمان سایت».
- `LandingTeacher` stays in `signals.MODELS_WITH_IMAGES`. A replaced or
  re-encoded photo's old file is removed after commit, as today.

### 4.3 Selectors, views, URLs

- **`website/selectors.py` (new):**
  - `public_teachers()`: the base queryset: active, linked staff null or
    active, `select_related("teacher__staff__user", "group")`;
  - `teachers_page_list(group_id)`: the published teachers, plus the groups
    in use, built in Python from the same rows.
- **`views.teachers`** (`require_safe`) renders `website/teachers.html`, or
  `website/teachers/_list.html` for `?partial=1` (the house `_is_partial`
  check).
- **`views.website`**: the teachers section reads `public_teachers()
  .filter(on_home=True)` instead of the `page.teachers` prefetch.
- **`website/urls.py`**: `path("teachers/", views.teachers,
  name="teachers")`.

### 4.4 Templates

- `website/teachers.html` extends `base.html`:
  - the public navbar;
  - `body_class` `public-page landing teachers-page`;
  - the title (`meta_title | site_name`) and the meta description.
- `website/teachers/_list.html` is the region the filter swaps: the
  sections, or the empty state. It has an `id="teachers"` landmark target
  and the live-region count.
- `website/teachers/_teacher.html` is one teacher: the portrait or initial,
  the name, specialty, `<dl>`, note and `<details>`, plus the commented
  blog slot.
- `website/index.html`:
  - the initial in the blob when there's no photo;
  - the «آشنایی با همه معلمان» link under the carousel.
- Everything is auto-escaped, multi-line text uses `linebreaksbr`, and links
  come only from `validate_link`ed fields.

### 4.5 Static files

- `website/static/website/css/teachers.css`, loaded after `nav.css` and
  `index.css`:
  - the tokens in §3.2;
  - its own small button block (`.tc-btn`, the same rules as `.ab-btn`);
  - chips, groups, the portrait, the note (the ruled paper is a
    `linear-gradient` on the line height, as in `contact.css`; the margin
    line is a border; the tick is an inline SVG);
  - `<details>` styling;
  - `:focus-visible` rings and a `prefers-reduced-motion` guard.
- `website/static/website/js/teachers.js`, enhancement only:
  - the filter swap (fetch `?partial=1`, `pushState` and `popstate`, the
    live-region count, falling back to normal navigation on any error);
  - opening the `<details>` of a card named in the URL hash.
- Two lines in `index.css` for the landing initial and the link (no other
  landing rule changes).
- Nothing from a CDN (ADR-021).

### 4.6 Tests (`website/test_teachers.py`, plus updates to `tests.py`)

- **View:**
  - `website:teachers`, 200;
  - one `<h1>`;
  - HEAD is OK, POST returns 405;
  - with the intro off, the `h1` is still there, visually hidden;
  - the empty state with no published teacher;
  - each switch hides its block;
  - the CTA's second button only with both text and link.
- **Publish flags:**
  - only `is_active` + `on_teachers_page` rows appear on `/teachers/`, and
    only `is_active` + `on_home` rows on `/`;
  - the seeded landing teachers aren't on `/teachers/`;
  - after the migration, existing rows keep showing on `/`.
- **Fallbacks:**
  - the name falls back to first and last name, never the username;
  - the specialty falls back to `field_of_study`, and the override wins;
  - **the photo is the override only**: a linked teacher with an avatar and
    no override shows the initial on both pages;
  - an inactive linked staff member is hidden on both pages;
  - `clean()` requires a name.
- **Privacy:** a linked teacher whose username, national code, mobile,
  email, personnel code, birth date, address, emergency phone,
  `TeacherProfile.education` and `teaching_experience`, branch assignment
  and avatar all hold unique marker values. None of them appears in
  `/teachers/`, its partial, or `/`.
- **Photos:** an uploaded JPEG with EXIF (GPS) is stored without EXIF,
  upright, at most 900 px, as JPEG. A PNG with transparency is flattened.
  The file name is new and the old file is removed after commit.
- **Slug:**
  - generated from the name (Persian kept);
  - clashes get `-2`;
  - an edited slug is kept;
  - not regenerated when the name changes;
  - the card's `id` matches it.
- **Filtering:**
  - `?group=<id>` shows only that group, with its chip `aria-current`;
  - an unknown, inactive, empty or non-numeric group shows everyone;
  - chips are hidden with fewer than two groups in use;
  - ungrouped teachers come last under «سایر معلمان»;
  - `?partial=1` returns only the list fragment (no navbar, no `<html>`).
- **Escaping:** `<script>` in a name, quote and bio is rendered escaped.
  `javascript:` is refused on the CTA and the landing link.
- **Admin:**
  - «صفحه معلمان» opens its one record, and add and delete are forbidden;
  - the group inline renders;
  - «معلمان سایت» changelist, search, filters, the editable ticks, and the
    add form with a photo upload;
  - «مدیریت صفحه اصلی» no longer has the teacher inline and renders;
  - a staff user without the permission gets 403.
- **Migrations:**
  - the seed creates the page row once, and the reverse removes it and
    restores `page`;
  - slugs are filled for existing rows;
  - the menu: a `#` «معلمان» → `/teachers/`; an edited row and the other
    `#` rows («وبلاگ», «مقاله») are untouched; the reverse resets only
    `/teachers/`.
- **Query count:** `/teachers/` takes exactly 5 queries with 0 teachers,
  and with 12 teachers in 4 groups, linked to staff (flat, and locked). It's
  the same with a filter and for the partial (2). The landing count stays
  flat (the existing test is updated).
- **Navbar:** «معلمان» is `aria-current="page"` on `/teachers/` and on
  `/teachers/?group=…`.
- **Existing tests:** `LandingTeacherPropertyTests.test_falls_back_to_linked_user`
  asserts the avatar fallback. It is legitimately changed (if D4 is
  approved) to assert the initial instead. `clear_content()` and any test
  that creates `LandingTeacher(page=…)` are updated for the dropped FK. No
  test is deleted.

### 4.7 Verification and docs

- `makemigrations --check --dry-run`.
- Migrations forward, back to `0008` and forward again on a **scratch SQLite
  copy** (with landing teachers linked to staff), checking `page`, `slug`
  and the menu row at each step.
- `website` tests on PostgreSQL and SQLite.
- Full suite on PostgreSQL, serially in the background, against a
  **baseline full run on `main`** taken before any change.
- Headless Chrome (Playwright in a scratch venv, the system Chrome) against
  the scratch copy, in two states:
  - **deploy day:** nothing published (the empty state);
  - **filled:** 10 teachers in 3 groups plus one ungrouped, some without a
    photo or quote, one expansion open.

  Checks:
  - 1280px and 375px full pages;
  - a filtered page;
  - the nav drawer;
  - `scrollWidth == 375` on `html`, `body` and `.app-shell`;
  - the landing page before and after (only the initial and the link may
    differ);
  - one shot with `prefers-reduced-motion: reduce`.

  I'll share the screenshots.
- **Docs on the branch:**
  - `docs/apps/website.md`: models, admin, view, front end, migrations;
  - `docs/database.md` and `docs/database-mermaid.md`: the new tables,
    `LandingTeacher` changes, `group` FK, `page` dropped;
  - the staff doc fixes from finding 14;
  - `docs/changelog.md`;
  - ADR-025 amended (D13);
  - report `docs/plans/2026-10-teachers-page.md`.

---

## 5. What I will NOT touch

- `staff`, `accounts`, `school` and every other app: their models, admin and
  data are only read. There are no migrations outside `website`.
- **Existing website rows**: the seeded landing teachers, slides, texts,
  footer links and the «وبلاگ», «مقاله» and «سوالات متداول» rows. The only
  changes are the new columns and the `#` «معلمان» link (D11).
- The About and Contact pages, their CSS and JS, and `base.html`.
- `slider.js` and the landing page's other sections and button colours
  (the AA follow-up stays separate).
- The blog: no model, URL or link, only the slot and the documented plan
  (D8).
- The local Docker database and production: no `migrate`, no
  `collectstatic`.
- No commits, pushes or merges beyond this plan file, unless you ask.

## 6. Manual steps at deploy (for the report)

1. Back up, then `migrate` (website 0009–0012) and `collectstatic` by hand.
   The contact and about migrations (0003–0008) are still pending too.
2. In the admin:
   - **«صفحه معلمان»**: add the groups, and adjust the texts;
   - **«معلمان سایت»**: for each teacher who has agreed, upload a photo, write
     the specialty, experience, bio and quote, and tick «نمایش در صفحه
     معلمان»;
   - replace or untick the four seeded landing teachers;
   - check which landing cards relied on an account avatar (they show an
     initial after deploy, if D4 is approved) and upload photos for them.

## 7. Open questions and follow-ups

1. **D4** is the one real conflict between your brief and ADR-025. I need
   your call.
2. Should the About page's people and gallery photos also be re-encoded
   (D7)? I'd make that a separate small task.
3. «سوالات متداول», «وبلاگ» and «مقاله» stay `#` until their pages exist.
