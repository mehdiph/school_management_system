# Website App Documentation

The `website` app is the public site: the landing page (`/`), the contact
page (`/contact/`), the about page (`/about/`) and the teachers page
(`/teachers/`). All of their text and
images are editable from the Django admin; nothing on the pages is hardcoded
anymore. Public content is editorial: nothing is computed from school data
(ADR-025).

---

## 1. Models (`website/models/`)

Two singletons (always `pk=1`, see `SingletonModel` in `models/base.py`) hold
single-value content; the repeatable blocks hang off them by foreign key so
they are edited as admin inlines.

| Model | Purpose | Children (inlines) |
|---|---|---|
| `SiteSettings` | site name, logo, login button, footer texts, meta title/description — used by `base.html` on every page | `NavMenuItem`, `FooterLink` |
| `LandingPage` | intro, "why us", active-learning and teachers section texts/images, the link to the teachers page, plus one `show_*` switch per section | `HeroSlide`, `FeatureCard`, `LearningPoint` |
| `ContactPage` | contact page texts (hero, section titles, form, success message, FAQ teaser, meta title/description), plus one `show_*` switch per section | `ContactLocation`, `ContactChannel`, `ContactTopic` |
| `TeachersPage` | teachers page texts (intro, list labels, empty state, closing CTA, meta title/description), plus `show_intro`, `show_filter`, `show_cta` | `TeacherGroup` |
| `AboutPage` | about page texts (hero, story, director's words, mission/vision, section titles, branches text and link, closing CTA, meta title/description), the hero and quote photos, plus one `show_*` switch per section | `AboutMilestone`, `AboutValue` (`belief_values`), `AboutHighlight`, `AboutFact`, `AboutPerson`, `AboutPhoto` |

`ContactMessage` (not a singleton child) stores what the contact form sends;
see §5. `LandingTeacher` (not a singleton child either, since the teachers
page) is the list of teachers both the landing page and the teachers page
read; see below.

* `SingletonModel.load()` returns the row, creating it on first use; `delete()`
  is a no-op.
* Repeatable models extend `OrderedItem` (`order`, `is_active`, `created_at`,
  ordered by `order`).
* `LandingTeacher` is one teacher of the public site, shared by the landing
  page's row and the teachers page:
  * `on_teachers_page` («نمایش در صفحه معلمان») and `on_home` («نمایش در
    صفحه اصلی») say where it appears; both default to off, so nobody is
    published until ticked. Rows that existed before `0009` got `on_home`
    on, so the landing page didn't change. `is_active` is the master switch.
  * `teacher` optionally links a `staff.TeacherProfile`. `display_name` is
    `name_override`, else the user's first and last name, **never the
    username**; `display_specialty` is `specialty_override`, else the
    profile's `field_of_study`. `clean()` needs a name.
  * The photo is **only** `photo_override` (ADR-025): never the account
    avatar; without it, `initial` (the name's first letter) is shown on
    both pages.
  * `experience` (text as typed, «۱۲ سال»), `education`, `quote` (the
    red-pen note), `bio` (400 characters) are typed on the card; nothing
    is read from `teaching_experience`, `education` or any other staff
    field.
  * `group` optionally links a `TeacherGroup` (`SET_NULL`).
  * `slug` (unique, Persian kept) is generated from the name on first save
    (`-2`, `-3`… on a clash), never regenerated, editable; it is the card's
    `id`, so `/teachers/#<slug>` links to a teacher. It is the hook for the
    blog, whose plan decides how an author optionally links to a card; the
    card's expansion has a commented slot for a «نوشته‌های …» link.
  * Cards linked to an inactive `Staff` are hidden on both pages
    (`selectors.public_teachers()`).
* `TeacherGroup` (inline of `TeachersPage`): an editorial department
  («آموزگاران پایه», «زبان انگلیسی»…), not `school.Subject`. Teachers of an
  inactive group are hidden on the teachers page.
* Photos of people (`LandingTeacher.photo_override`,
  `AboutPerson.photo_override`) are re-encoded when uploaded
  (`website/images.py`, called from the models' `save()`): turned upright,
  scaled to fit 900 px, flattened onto white if transparent, saved as a
  fresh JPEG with a random name. No EXIF (GPS included) survives. Other
  website images are stored as uploaded (follow-up).
* Images: per-model `upload_to`, jpg/jpeg/png/webp only, max 2 MB
  (`website/validators.py`). Replaced or deleted files are removed from
  MEDIA_ROOT after the transaction commits (`website/signals.py`).
* Links are `CharField`s validated by `validate_link`: relative paths, `#…`,
  `http(s)://`, `mailto:` and `tel:` only (no `javascript:`).
* `static_fallback` (not editable) lets seeded rows show the original images
  from `website/static` until an image is uploaded.

* `ContactLocation.branch` optionally links a `school.Branch`:
  `display_title`, `display_address` and the branch phone fall back to the
  branch's `name`, `address` and `phone_number`.
  Locations of inactive branches are not shown. `map_links` lists only the
  filled-in Neshan / Balad / Google Maps links.
* `ContactChannel` is a phone, mobile or email, school-wide (no location)
  or under one location. `value` is shown as typed (in Persian digits);
  `href` is `tel:` with ASCII digits or `mailto:`; `clean()` validates the
  value by kind (mobiles with `accounts.validators.validate_mobile`).

* `AboutPerson.staff` optionally links a `staff.Staff`: `display_name`
  falls back to the user's first and last name (never the username). The
  photo **never** falls back to the account avatar: only `photo_override`,
  uploaded on purpose, is published; without it the template shows
  `initial` (the name's first letter). People whose `Staff` is inactive are
  hidden. `clean()` needs a name from the override or the account. The
  section is for leadership and office staff; teachers get their own page.
* `AboutFact.value` and `AboutMilestone.year` are text, shown as typed
  («۴۰۰+»، «۱۳۹۲»). `AboutPhoto.image` is required. `AboutHighlight` has a
  `static_fallback` like the landing page's cards; `AboutPage.hero_image`
  falls back to the bundled `happy_young_boy.png`.

Migration `0002_seed_content` loads the original page content.
`0004_seed_contact` creates the contact page row, five topics and one
location per active branch (only creates rows). `0005_link_contact_menu`
points the «تماس با ما» menu and footer rows at `/contact/`, only where they
were still `#`; its reverse resets only rows still at `/contact/`.
`0006_about` creates the about tables. `0007_seed_about` creates the page
row, four values and four highlights (active), and three milestones and
four facts as **inactive examples** (placeholder years and «—»), so no
invented fact is published; no people or photos, and the director's words
are off. Only creates rows; the reverse deletes the about rows.
`0008_about_menu` points the «درباره ما» menu and footer rows still at `#`
to `/about/`, and deactivates (doesn't delete) the «کلاس ها» menu item if
it is still at `#`. Its reverse resets only rows still at `/about/` and
re-activates only an inactive «کلاس ها» still at `#`; rows an admin has
renamed or linked are never touched. (If an admin had deactivated «کلاس
ها» by hand before 0008, a rollback turns it back on.)

Teachers page migrations:
* `0009_teachers`: the `TeachersPage` and `TeacherGroup` tables, the new
  `LandingTeacher` fields (`slug` still nullable), `LandingTeacher.page`
  made nullable, the landing page's link fields, help texts.
* `0010_seed_teachers`: creates the `TeachersPage` row and fills every
  card's `slug`. No teachers or groups are created. Its reverse points the
  cards back at the landing page's row and deletes the teachers page row.
* `0011_teacher_slug`: drops `LandingTeacher.page`, makes `slug` unique and
  required. Kept apart from 0010 so no PostgreSQL transaction both updates
  and alters the table.
* `0012_teachers_menu`: the «معلمان» menu row still at `#` → `/teachers/`;
  the reverse resets only a row still at `/teachers/`.
* `0013_hide_seed_teachers`: deactivates the four invented seed teachers
  of `0002` (علی رضایی، سعید محمدی، ماریا کریمی، ندا حسینی) only where
  they are untouched: exact seed name and specialty, no linked teacher, no
  photo. The reverse re-activates only inactive rows matching the same
  conditions (one an admin had deactivated by hand would come back on).

## 2. Admin

* **مدیریت صفحه اصلی** (`LandingPage`), **صفحه تماس با ما** (`ContactPage`),
  **صفحه درباره ما** (`AboutPage`) and **تنظیمات سایت** (`SiteSettings`)
  open their single record directly; add/delete are disabled.
* On **صفحه درباره ما**, the fieldsets follow the page's order; people are
  picked with autocomplete on «پرسنل»; every photo field says photos are
  public, and the people section's note says it is for leaders and office
  staff (teachers have their own page). To bring a seeded milestone or
  number onto the page, edit it and tick «فعال».
* On **صفحه تماس با ما**, a channel's «شعبه» dropdown lists saved locations
  only: save a new location before attaching phones to it.
* **پیام‌های تماس با ما** (`ContactMessage`): see §5.
* **معلمان سایت** (`LandingTeacher`), its own list: thumbnail, name,
  specialty, group, and the two ticks, «فعال» and order editable in the
  list; filters by tick and group; search by name. The change form has
  «معلم» (autocomplete on teacher profiles), «نمایش», «عکس», «معرفی»,
  «لینک». The help texts say a teacher is published only with their
  agreement, and that photo metadata is removed. **مدیریت صفحه اصلی** no
  longer has a teachers inline: its «سکشن اساتید» links to this list.
* **صفحه معلمان** (`TeachersPage`) opens its single record, with the groups
  as an inline and a link to «معلمان سایت».
* Every image has a thumbnail preview; `order` is editable inline.

## 3. View and templates

* `views.website` loads `LandingPage` and prefetches only the enabled sections'
  active items, and reads the teachers from
  `selectors.public_teachers().filter(on_home=True)` (one query), so the
  query count doesn't grow with the number of items. Below the teachers
  row, `teachers_link_text` links to `teachers_link_url` (`/teachers/`),
  shown only with both filled in.
* `website.context_processors.site_settings` exposes `site_settings`,
  `nav_items` and `footer_links` lazily to every template (the header logo and
  footer live in `template/base.html`).
* `templates/website/partials/public_navbar.html` is the public menu, shared by
  the landing, contact and login pages. A section with no active items, or
  switched off, is not rendered.
* `views.contact` (`website:contact`, GET and POST) loads `ContactPage` with
  its active locations (`select_related("branch")`), channels and topics in
  one query each and groups channels under their location in Python, so
  the query count doesn't grow with the number of items (tested). The hero
  and the phone bar call the first school-wide phone (else the first
  location's); «مسیریابی» opens the first location's first map link.
  Social chips are the footer's `FooterLink` social items whose link isn't
  `#`. Templates: `website/contact.html` and `website/contact/_*.html`.
* `views.about` (`website:about`, GET/HEAD only) loads `AboutPage` and
  prefetches only the enabled sections' active items (people with
  `select_related("staff__user")`, filtered to active staff), plus the
  public locations: the same `_public_locations()` queryset the contact
  page uses (active rows of active branches). 11 queries whatever the
  number of items (tested). Sections in order: hero (the only `h1`),
  story with the milestones, director's words, beliefs, «در نسل قلم،
  بچه‌ها…», numbers, «همکاران ما» (`#team`), gallery, branches (name and
  address, linking to the contact page for phones and maps), closing CTA.
  A section switched off, or with nothing active, isn't rendered.
  Templates: `website/about.html` and `website/about/_person.html`.
* `views.teachers` (`website:teachers`, GET/HEAD only) loads `TeachersPage`
  and `selectors.teachers_page_listing()`: the published teachers
  (`is_active`, `on_teachers_page`, linked staff null or active, group null
  or active) in **one** query with their groups, grouped in Python. With
  «همه», one section per group in use (group order), then the teachers
  without a group under `other_group_title`; with no group in use, one
  flat list under a visually hidden `list_title`. `?group=<id>` shows one
  group; an unknown, inactive, empty or non-numeric value shows everyone.
  The chips («همه» + groups in use) appear only with two or more groups and
  `show_filter`. With `?partial=1` only `website/teachers/_directory.html`
  (the filter and the list) is rendered, for `teachers.js` (ADR-015).
  5 queries for the page and 2 for the fragment, whatever the number of
  teachers and groups (tested). One `h1`, visually hidden when the intro is
  off; an empty state (`empty_text`) until a teacher is published.
  Templates: `website/teachers.html` and `website/teachers/_filter.html`,
  `_list.html`, `_teacher.html`, `_directory.html`. The template only uses
  a card's own fields and `display_*` properties, never `card.teacher`.
* `template/base.html` has a `messages` block (default markup unchanged) and
  a `viewport` block; the contact page shows its confirmation inside the
  form card and sets `viewport-fit=cover` for the phone bar.

## 4. Front end (`website/static/website/`)

* `css/index.css` — mobile-first landing styles (tokens in `:root`,
  breakpoints 576/768/992/1200px, logical properties for RTL).
* `css/nav.css` + `js/nav.js` — below 992px the menu becomes a drawer from the
  right with an overlay; closes on ✕, overlay, Esc, link click or resize to
  desktop; locks body scroll and traps focus while open.
* `css/contact.css` + `js/contact.js` — the contact page; loaded after
  `index.css` and reusing its `--lp-*` tokens. Its `--ct-action` is the
  shared `--lp-action` (the brand orange fails AA under white text; this
  darker step passes); it adds the notebook-paper tokens. The form is a notebook page (margin line,
  ruled message field). Below 768px a phone bar («تماس با دفتر»,
  «مسیریابی») is fixed to the bottom: under the header so the nav drawer
  and overlay cover it, padded by `env(safe-area-inset-bottom)`, with
  matching padding under the footer, and hidden while a form field has
  focus (CSS `:has()`, plus a class from JS). `contact.js` only enhances:
  copy buttons (hidden without JS), inline validation with the server's
  messages, a busy submit button. Everything works without JS.
* `css/about.css` — the about page; loaded after `index.css`. The shared
  action colour lives in `index.css` as `--lp-action` / `--lp-action-hover`
  (`#b4501c` / `#9a4416`, AA under white text); `contact.css`'s
  `--ct-action*` reference it, and the landing page's own buttons don't use
  it yet. The page adds only `--ab-ink #1f4f8f` (a blue ballpoint), used
  for the story's pen line, its dots and years and the quote mark. The
  line is a CSS mask tile (so it never stretches) beside the story; where
  `animation-timeline: view()` is supported and motion is allowed, it
  draws itself as the story scrolls by and each year's dot fills as it is
  reached. Everywhere else it is simply drawn. The hero photo sits in an
  arch. The gallery is a scroll-snap strip below 768px and a grid above.
  No JavaScript besides `nav.js`.
* `css/teachers.css` + `js/teachers.js` — the teachers page; loaded after
  `index.css`. It adds `--tc-redpen #b3202e` (6.4:1 on the paper), used only
  for each teacher's note and its hand-drawn tick, and repeats the contact
  page's paper and rule values (`--tc-paper`, `--tc-rule`) plus a red
  notebook margin. A teacher's `quote` is written in red ink on a strip of
  ruled notebook paper with the margin line at the start (right) edge.
  Portraits use the landing page's blob frame (peach / yellow / sand
  backgrounds), with no card boxes. Below 576px each teacher is a row (96px
  portrait beside the name); then 2 / 3 / 4 columns at 576 / 992 / 1200px.
  The bio and education are in a native `<details>` («درباره …»), the only
  motion (a height transition where `::details-content` is supported and
  motion is allowed). `teachers.js` only enhances: the chips fetch
  `?partial=1`, swap `[data-tc-swap]` blocks, `pushState` (back and forward
  work), announce «n معلم» in a polite live region and keep focus on the
  chip; any error falls back to a normal page load. It also opens the
  `<details>` of a teacher linked by `#slug`.
* `index.css` also styles the landing card's initial (`.instructor-initial`)
  and the link to the teachers page (`.instructors-more`, `--lp-action`).
* `js/slider.js` — hero carousel (autoplay, dots, arrows, touch swipe; pauses on
  hover/focus and honours `prefers-reduced-motion`) and the teachers row
  (native scroll-snap; arrows scroll one card; 1/2/3 cards per view).


## 5. Contact form and messages

* `forms.ContactForm`: name, mobile (`normalize_mobile` + `validate_mobile`:
  Persian digits, `+98`, `0098` accepted, stored as `09xxxxxxxxx`), topic
  (hidden when no topic is active), branch (only with two or more
  locations; «فرقی نمی‌کند»), message (10–2000 characters). Persian error
  messages; Django sets `aria-invalid` and `aria-describedby`
  (`<id>_helptext`, `<id>_error`), and an error summary with links to the
  fields is focused after a failed submit.
* Success: Post/Redirect/Get to `/contact/#contact-form` with
  `ContactPage.success_text` (`{mobile}` replaced in Persian digits).
* Spam (ADR-024), in `website/services.py`:
  * honeypot field `website`: filled → normal success message, nothing saved;
  * signed render time: faster than `CONTACT_MIN_FILL_SECONDS` (3) or older
    than `CONTACT_MAX_FORM_AGE_SECONDS` (2 h) → refused;
  * rate limit, counted on `ContactMessage` in one query:
    `CONTACT_RATE_LIMIT = (3, 600)` per mobile **and** per device (either one
    trips it), `CONTACT_DAILY_LIMIT = 50` per device over 24 hours → HTTP
    429, the text is kept.
* The device is `ip_hash`, an HMAC-SHA256 of the client IP keyed with
  `SECRET_KEY`. The raw IP is never stored.

### Client IP behind the CDN

`CLIENT_IP_HEADER` (settings, from the environment variable of the same
name) names the header that carries the visitor's IP. Write it as the HTTP
header name or the `request.META` key:

| In front of nginx | `.env` |
|---|---|
| Cloudflare | `CLIENT_IP_HEADER=CF-Connecting-IP` |
| ArvanCloud | `CLIENT_IP_HEADER=AR-Real-IP` |
| Another CDN / proxy | its client-IP header (check its docs) |
| Nothing (nginx only) | leave unset: `X-Real-IP` (nginx overwrites it) |

The first address of a comma-separated value is used; a missing or
malformed value falls back to `REMOTE_ADDR`. **Set it before deploying:**
with a CDN in front, nginx's `X-Real-IP` is the CDN edge's address, so
every visitor would share a few "devices" and hit the daily cap together.
The CDN header can be forged by anyone reaching the server directly, so
the origin should accept traffic from the CDN only (firewall or nginx
`allow` list); if it can't, only the per-mobile limit really holds.

### Admin access for office staff

**پیام‌های تماس با ما** is read-only except «پیگیری شد» (`is_handled`, also
editable from the list). Add is disabled; delete is superuser-only (spam
cleanup). The `ip_hash` is never shown. Search accepts Persian digits.

Office staff need a staff account (`is_staff`) and:

| Permission | Allows |
|---|---|
| `website.view_contactmessage` («Can view پیام تماس با ما») | reading messages |
| `website.change_contactmessage` («Can change پیام تماس با ما») | ticking «پیگیری شد»; every other field stays read-only |

To grant them (by hand; no migration creates groups or grants), in the
admin: **بررسی اصالت و اجازه‌ها → گروه‌ها → افزودن**, name it e.g.
«دفتر مدرسه», add the two permissions, save; then open each office user,
tick «وضعیت کارمندی» (`is_staff`) and add them to the group. Or give the
permissions to the user directly under «اجازه‌های کاربر».
