# Plan: public «تماس با ما» page

Status: **plan, waiting for approval.** No code written. Implementation goes on
`feature/contact-page`, created from `main` after approval.

Read before planning: `CLAUDE.md`, `.claude/CLAUDE.md`, `docs/apps/website.md`,
ADR-011/015/021, `docs/changelog.md`, `template/base.html`, all of `website/`
(models, admin, views, signals, validators, context processor, templates,
CSS/JS, both migrations, `tests.py`), `accounts/validators.py`,
`school/models/branch.py`, `core/templatetags/jalali_tags.py`, the Dockerfile
and the nginx config. I also took screenshots of the current landing page from
the local Docker stack (read-only GET).

---

## 1. Findings, risks and surprises

1. **The school has two branches, and `school.Branch` already stores `address`
   and `phone_number`** (local data: «شعبه مرکزی (عمار)», «شعبه 2 (منصور
   افشار)»). A contact page with one address would be wrong. The page needs
   one location block per branch, and it should not make the admin type the
   same address twice (D3).
2. **The brand orange fails contrast with white text.** `--lp-brand #ef7e41`
   on white is 2.72:1 and `--lp-brand-dark #d96a30` is 3.47:1. WCAG AA needs
   4.5:1 for normal text. The landing page's buttons use them today. For the
   contact page I add one darker action token, `--ct-action: #b4501c` (5.12:1
   on white, 4.54:1 on the cream panel), for filled buttons and orange text.
   It's the same hue, so it still reads as the site's orange. I won't touch
   the landing page in this task; I'll list it in the report as a follow-up.
3. **Rate limiting has no shared cache to sit on.** `CACHES` isn't
   configured, so Django uses a per-process LocMemCache. Gunicorn runs one
   gthread worker today, but that's an accident of the Dockerfile. A limit
   counted in the database (the stored submissions themselves) is correct
   whatever the worker count, and needs no new service (D6).
4. **The client IP sits behind nginx.** `REMOTE_ADDR` is the nginx container.
   nginx sets `X-Real-IP $remote_addr`, overwriting anything the client sent,
   and gunicorn is only `expose`d to the compose network. So `X-Real-IP` is
   trustworthy in production. The header name goes in a setting, with a
   fallback to `REMOTE_ADDR` (runserver, tests).
5. **Reusable pieces already exist:** `accounts.validators.normalize_mobile`
   / `validate_mobile`, with Persian/Arabic digits, `+98`/`0098` handling and
   a Persian message. Also the `fa_digits` filter in `core/templatetags/jalali_tags.py`,
   and `SingletonModel` / `OrderedItem` / `image_url` / `IMAGE_VALIDATORS` /
   the cleanup signals. I'll reuse all of them rather than write new ones.
6. **Messages render at the top of every page** (`template/base.html`, inside
   `.container`, before `{% block content %}`). After a redirect back to the
   form, a success message at the top of a long page is easy to miss. Fix:
   wrap that markup in `{% block messages %}` with the same default content.
   That changes nothing for other pages. The contact page then shows the
   message inside the form card (D9).
7. The navbar marks the active item with `item.url == request.path`, so a
   «تماس با ما» row pointing at `/contact/` will highlight on the new page
   with no template change.
8. Social links in the footer (`FooterLink`, `kind=social`) are all `#` in
   the seed. Social chips on the contact page will skip items still set to
   `#`, so the page never shows a dead link.
9. The local SQLite file isn't migrated, and `.env` points at the Docker
   Postgres. For screenshots I'll run `runserver` against a **scratch SQLite
   copy** through a throw-away settings module in the scratchpad. I won't
   migrate the local Docker database.

---

## 2. Decisions to confirm

**D1. Include a contact form?** Recommended: **yes**. Many parents will want
to leave a message outside office hours. Fields:

| Field | Required | Notes |
|---|---|---|
| نام و نام خانوادگی | yes | 2–100 chars |
| شماره موبایل | yes | `normalize_mobile` + `validate_mobile`, so «۰۹۱۲ ۳۴۵ ۶۷۸۹» and `+98…` are accepted; stored as `09xxxxxxxxx` |
| موضوع | yes, if topics exist | choices from admin-editable `ContactTopic` rows (seed: ثبت‌نام، امور آموزشی، شهریه و امور مالی، پیشنهاد یا انتقاد، سایر); hidden when none are active |
| شعبه | optional | shown only when more than one location is active; «فرقی نمی‌کند» as the empty choice |
| متن پیام | yes | 10–2000 chars |

No email field (parents here answer the phone, not email; one fewer field). No
student name or grade: the office can ask on the call.

**D2. Map approach.** Recommended: **option A**.
- **A. Static map image + "open in" links (recommended).** Per location, an
  optional map image uploaded in the admin (a screenshot of the area, with the
  usual image validators and cleanup), plus three optional link fields: Neshan,
  Balad, Google Maps. The admin pastes each app's own "share location" link,
  so I never guess a URL format, and `validate_link` checks them. A button
  shows only when its link is filled in. Without an image, the block shows the
  address and buttons only, never a placeholder map.
- B. Latitude/longitude fields that generate the three links. Less typing,
  but it depends on each app's URL format staying stable.
- C. An embedded iframe (Neshan/Google). Rejected by ADR-021: an external host
  loads on every visit and the page breaks when it's blocked.

**D3. Where contact data lives.** Recommended: a **new `ContactPage`
singleton** (page texts and switches) with three inlines: `ContactLocation`,
`ContactChannel` and `ContactTopic`. `SiteSettings` stays site chrome (logo,
nav, footer). `ContactLocation` may link to a `school.Branch` and falls back
to it, like `LandingTeacher` does with `TeacherProfile`:
- title → `branch.name`, address → `branch.address`;
- if no phone channel is attached, `branch.phone_number` is shown.

So the address is entered once (on the branch), and a location can still exist
without a branch (e.g. an admissions office).

**D4. Footer reuse.** Recommended: **don't change the footer now.** It stays
links-only and gets the new URL through D5. The contact page **reuses the
footer's social items** (`FooterLink`, `kind=social`) instead of storing
social links twice. A footer phone/address line can come later if you want
it.

**D5. New URL for the existing «تماس با ما» nav and footer rows.**
Recommended: **a reversible data migration** that updates only `NavMenuItem`
and `FooterLink` rows whose `title == «تماس با ما»` **and** `url == "#"`, to
`/contact/`. Rows an admin has already edited are left alone. Reverse sets back
to `#` only the rows with that title still at `/contact/`. This modifies
existing rows, so it needs your explicit yes. The alternative is to change the
two rows by hand in «تنظیمات سایت» after deploy.

**D6. Spam protection.** Recommended, all three:
- **Honeypot:** a visually hidden text field that real users never see
  (`tabindex=-1`, `autocomplete=off`, label «این فیلد را خالی بگذارید» for
  screen readers). If it's filled, the view redirects with the normal success
  message and saves nothing, so the bot learns nothing.
- **Time trap:** a signed timestamp (`django.core.signing`) rendered into the
  form. Rejected if it's younger than 3 s or older than 2 h. The older case
  shows «فرم منقضی شده است؛ دوباره ارسال کنید» and keeps what the user typed.
- **Rate limit in the database:** at most `CONTACT_RATE_LIMIT = (3, 600)` (3
  messages per 10 minutes) and `CONTACT_DAILY_LIMIT = 10` per client. Counted
  on `ContactMessage` by `ip_hash` + `created_at`, with an index on both.
  Over the limit, the form is re-rendered with HTTP 429 and «از این دستگاه
  پیام‌های زیادی ارسال شده است؛ کمی بعد دوباره تلاش کنید یا با دفتر مدرسه
  تماس بگیرید.» and the user's text is kept.

**D7. What is stored about the sender's device.** Recommended: **an HMAC of
the IP** (`ip_hash`, keyed with `SECRET_KEY`), not the raw IP. That's enough
for the rate limit and keeps one less piece of personal data about parents.
The alternative is to store the raw IP, which helps if you ever need to report
abuse.

**D8. Admin for submissions.** Recommended: «پیام‌های تماس با ما» is
**read-only** except one checkbox, **«پیگیری شد»** (`is_handled`), so the
office can see what's still open. The list shows name, mobile, topic, branch,
Jalali date and handled, with filters for handled, topic and branch, and a
search on name and mobile. Add is disabled, and delete is superuser-only (spam
cleanup). If you want it strictly read-only, I'll drop the checkbox.

**D9. Success flow (PRG).** Recommended: on success, save, then
`messages.success(...)` and redirect to `/contact/#contact-form`. The contact
page overrides the new `{% block messages %}` (finding 6), so the message
shows inside the form card, which the anchor scrolls to. It reads «پیامتان
ثبت شد. همکاران ما با شماره ‎۰۹…‎ تماس می‌گیرند.» The text is admin-editable,
with the mobile shown in Persian digits.

**D10. Email notification.** Recommended: **none in this task** (your brief).
`EMAIL_*` isn't configured anyway. New messages are only in the admin. This
can be a later task.

**D11. Seed data.** Recommended: a data migration that only **creates** rows,
never modifies them:
- the `ContactPage` row with default Persian texts;
- the five `ContactTopic` rows;
- one `ContactLocation` per active `Branch`, linked to it, so address and
  phone show right after deploy from data the school already entered.

No `ContactChannel` is seeded: I don't know the school's numbers.

**D12. Mobile action bar.** Recommended: **yes**. Below 768px, a bar fixed to
the bottom of the screen with two buttons, «تماس با دفتر» (the first
school-wide phone channel) and «مسیریابی» (the first location's first map
link). It shows only the buttons whose data exists, and is hidden entirely
when neither does. It doesn't follow you on desktop. It's the fastest path to
the brief's two main goals on a phone.

**D13. "Open now" indicator: not in this task.** A live «دفتر الان باز است»
badge needs structured hours and would be wrong on holidays and closures,
which are per-branch events in `academic_calendar`. Working hours are free
text per location («شنبه تا چهارشنبه، ۷:۳۰ تا ۱۴:۰۰»). Tell me if you want
the indicator as a follow-up.

**D14. URL.** `/contact/`, name `website:contact`.

**D15. ADR.** Recommended: **ADR-024, "Public form submissions are stored,
rate-limited in the database by a hashed client IP, and never emailed by
default"**, so the next public form (e.g. registration enquiry) follows the
same rule.

---

## 3. Design

### Aesthetic direction: «دفتر مدرسه»

The page is the school office, and «دفتر» is also the notebook every child
carries. The one memorable element is the **contact form drawn as a page of
a school notebook**:
- a cream paper card;
- a single vertical margin line in the action orange on the inline-start
  (right) side;
- the message field ruled with faint horizontal lines aligned to its
  line-height, so typing sits on the lines.

Everything else stays quiet and belongs to the landing page:
- the same Vazirmatn (already vendored), peach cream panels with the 40px
  bottom radius of `.hero`, and glass section boxes on the doodle background;
- the landing page's **blob shapes**, reused as the frame of each branch's
  map image.

There are no entrance animations. The only motion answers the user: the copy
button confirms «کپی شد», and the submit button changes to «در حال ثبت…».
Both are off under `prefers-reduced-motion`.

Why this direction: the audience is parents, the tone is warm and
trustworthy, and the notebook ties the form to the child and the school
without decoration that gets in the way of calling.

What I changed after reviewing it against the brief:
- My first sketch opened with a big-number hero: the phone number huge, with
  a small label. That is the generic "stat" hero.
- I replaced it with a plain sentence headline and the call button as the
  hero's primary action. The number is still large and tappable, but as a
  button, not as a statistic.
- I also dropped a three-step "what happens next" row: it was numbered
  decoration for a single sentence of content.

### Tokens (extend, don't compete)

`contact.css` uses the landing tokens (`--lp-*`) and adds only:

| Token | Value | Role |
|---|---|---|
| `--ct-action` | `#b4501c` | filled buttons and orange text (AA on white and cream) |
| `--ct-action-hover` | `#9a4416` | hover |
| `--ct-paper` | `#fffaf6` | notebook card |
| `--ct-rule` | `#f0dccd` | ruled lines |
| `--ct-margin` | `rgba(180, 80, 28, 0.55)` | notebook margin line |
| `--ct-error` | `#b42318` | error text and field border (5.9:1 on white) |

Type: Vazirmatn only, already used across the site. Scale on a 1.25 ratio:
h1 `clamp(1.6rem, 1.1rem + 2vw, 2.4rem)` at 800, section h2 1.5rem at 800,
location title 1.15rem at 700, body 1rem with 1.9 line-height, help and notes
0.875rem. Never smaller than 14px. Text is right-aligned (start) throughout,
except the centered hero on phones (as on the landing page). Lines are at most
about 70 characters (`max-width: 38rem` on prose).

### Wireframe: desktop (≥ 992px)

```
┌ public navbar (shared) ─────────────────────────────────────────────┐
├─────────────────────────────────────────────────────────────────────┤
│ HERO (cream panel, rounded bottom)                                   │
│   با دفتر مدرسه در تماس باشید                         ┌─────────┐    │
│   برای ثبت‌نام، پیگیری درس فرزندتان یا هر پرسشی…       │ optional │    │
│   [ ☎ تماس با دفتر  ۰۴۴‑۳۳۴۴‑۵۵۶۶ ]  [ پیام بگذارید ]   │  image   │    │
│   social chips: اینستاگرام · تلگرام (only real links)   └─(blob)──┘    │
├─────────────────────────────────────────────────────────────────────┤
│ راه‌های تماس (school-wide channels, glass box)                         │
│  ┌ دفتر مدرسه ─────┐ ┌ معاونت آموزشی ──┐ ┌ ایمیل ──────────┐          │
│  │ ۰۴۴‑۳۳۴۴‑۵۵۶۶ [کپی]│ │ ۰۹۱۴… [کپی]      │ │ info@… [کپی]     │          │
│  │ note             │ │ note             │ │                 │          │
│  └──────────────────┘ └──────────────────┘ └─────────────────┘          │
├─────────────────────────────────────────────────────────────────────┤
│ نشانی شعبه‌ها (one row per location, alternating sides)                 │
│  ┌───────────────────────────────────────┬───────────────────┐       │
│  │ شعبه مرکزی (عمار)                       │   map image in    │       │
│  │ 📍 address …                    [کپی]   │   blob frame      │       │
│  │ 🕘 hours (free text, multiline)          │                   │       │
│  │ ☎ phones of this branch                 │                   │       │
│  │ [نشان] [بلد] [گوگل مپ]                    │                   │       │
│  └───────────────────────────────────────┴───────────────────┘       │
├─────────────────────────────────────────────────────────────────────┤
│ برای ما بنویسید                                                        │
│  ┌ notebook card ───────────────────────────┐   side column:          │
│  ┃ نام و نام خانوادگی  [______________]       │   form intro text,      │
│  ┃ شماره موبایل        [______________]       │   FAQ teaser (if on)    │
│  ┃ موضوع [▾]           شعبه [▾]               │                         │
│  ┃ متن پیام  ───────────────────────          │                         │
│  ┃           ───────────────────────          │                         │
│  ┃ [ ثبت پیام ]                               │                         │
│  └───────────────────────────────────────────┘                         │
├ footer (shared) ─────────────────────────────────────────────────────┤
```

### Wireframe: phone (375px)

```
┌ logo            ☰ ┐
│ HERO (centered)   │
│ h1, p             │
│ [☎ تماس با دفتر]   │  full width
│ [پیام بگذارید]     │
│ social chips      │
├───────────────────┤
│ channel cards     │  1 column
├───────────────────┤
│ location card     │  map image first (blob), then text,
│                   │  map buttons wrap 2+1
├───────────────────┤
│ notebook form     │  1 column, selects stacked
├───────────────────┤
│ footer            │
│ (bottom padding)  │
└───────────────────┘
[ ☎ تماس با دفتر | 📍 مسیریابی ]   ← fixed action bar (D12)
```

Breakpoints are the site's 576 / 768 / 992 / 1200. I'll use logical
properties only and `minmax(0, 1fr)` grids, and check for no horizontal scroll
at 375px.

---

## 4. Implementation outline

### Models and migrations (`website/models/contact.py`)

- **`ContactPage(SingletonModel)`**
  - switches: `show_channels`, `show_locations`, `show_form`, `show_faq`
    (FAQ default **off** until an FAQ page exists);
  - hero: `hero_title`, `hero_text`, `hero_image` (optional, blob frame) +
    alt, `hero_call_text`;
  - section titles: `channels_title`, `locations_title`;
  - form: `form_title`, `form_intro`, `success_message`;
  - FAQ teaser: `faq_title`, `faq_text`, `faq_url` (`validate_link`);
  - `meta_description`.
- **`ContactLocation(OrderedItem)`**
  - `page` FK, `branch` FK `school.Branch` (null, `SET_NULL`);
  - `title_override`, `address_override` (fall back to the branch);
  - `hours` (text);
  - `map_image` + alt;
  - `neshan_url`, `balad_url`, `google_maps_url` (`validate_link`);
  - properties `display_title`, `display_address` and `map_links`;
  - `clean()` requires a branch or a title.
- **`ContactChannel(OrderedItem)`**
  - `page` FK, `location` FK (null = school-wide);
  - `kind` (phone / mobile / email), `label`, `value` (as typed, shown in
    Persian digits), `note`;
  - `clean()` validates the value by kind (phone/mobile: 4–15 digits after
    normalising, mobile through `validate_mobile`; email through
    `EmailValidator`);
  - property `href` (`tel:` with ASCII digits, or `mailto:`).
- **`ContactTopic(OrderedItem)`**: `page` FK, `title`.
- **`ContactMessage`**
  - `name`, `mobile`, `topic` (text snapshot), `location` (text snapshot, so
    deleting a topic or branch keeps the record readable), `message`;
  - `ip_hash`, `created_at` (`jDateTimeField`), `is_handled`;
  - index on `(ip_hash, created_at)`; ordering `-created_at`.
- **Migrations:**
  - `0003_contact` (schema);
  - `0004_seed_contact` (D11, creates only);
  - `0005_link_contact_menu` (D5, only if approved, reversible).
- Register `ContactPage` and `ContactLocation` in `website/signals.py`
  `MODELS_WITH_IMAGES`.

### Services and forms

- `website/forms.py`, `ContactForm`:
  - honeypot and signed timestamp;
  - topic and location choices from the already-fetched lists, so the form
    makes no queries (`ObjectChoiceField` pattern from `core/forms.py`);
  - Persian error messages on every field.
- `website/services.py`:
  - `client_ip_hash(request)`;
  - `rate_limited(ip_hash)`, which runs one aggregate query for both windows;
  - `submit_contact_message(form, ip_hash)`.
- Settings in `base.py`: `CONTACT_RATE_LIMIT`, `CONTACT_DAILY_LIMIT`,
  `CONTACT_MIN_FILL_SECONDS`, `CONTACT_CLIENT_IP_HEADER = "HTTP_X_REAL_IP"`.

### View, URL, templates

- `views.contact` (GET/POST, `require_http_methods`), thin:
  - loads `ContactPage`;
  - prefetches active locations (`select_related("branch")`), active
    channels and active topics in **one query each**;
  - groups channels by location in Python;
  - POST → service → PRG (D9).
- `website/urls.py`: `path("contact/", views.contact, name="contact")`.
- `website/templates/website/contact.html` extends `base.html` and includes
  the shared navbar. It uses partials: `contact/_channel.html`,
  `contact/_location.html`, `contact/_form.html`.
- The page has a `<main>`-level structure with one `<h1>`, `<section
  aria-labelledby>` per block and `<address>` for addresses.
- Form accessibility:
  - each `<label for>` is tied to its input;
  - errors go in `<p id="…-error">`, with `aria-describedby` and
    `aria-invalid` on the input;
  - an error summary at the top of the form with links to the fields, which
    gets focus after a failed submit.
- `{% block messages %}` added to `template/base.html` with identical default
  markup.

### Static files

- `website/static/website/css/contact.css`: mobile-first, the tokens above,
  focus rings in `--ct-action`, a `prefers-reduced-motion` block.
- `website/static/website/js/contact.js` (vanilla, enhancement only):
  - copy buttons, rendered `hidden` and shown by JS, using the Clipboard API
    and an `aria-live` «کپی شد»;
  - inline validation on blur, with the same rules and messages as the
    server, mobile normalised;
  - the submit button disabled with «در حال ثبت…» while submitting.
- Without JS, everything works: `tel:`/`mailto:` links, the form posts
  normally and server errors render.

### Admin

- `ContactPageAdmin(SingletonAdmin)`:
  - fieldsets mirror the page;
  - inlines: `ContactLocationInline` (stacked, map preview),
    `ContactChannelInline` (tabular, location dropdown limited to this page's
    locations), `ContactTopicInline` (tabular).
- `ContactMessageAdmin` as in D8.

### Tests (`website/test_contact.py`)

- View:
  - renders seeded content;
  - sections hidden by switches or with no items;
  - branch fallbacks for title, address and phone;
  - `tel:` hrefs use ASCII digits and are displayed in Persian digits;
  - social chips skip `#` links;
  - the FAQ teaser is off by default;
  - user text is escaped;
  - the nav item is `aria-current` on `/contact/` (after D5).
- Query count stays flat when locations, channels and topics are added.
- Form:
  - required fields;
  - mobile variants accepted and invalid ones refused, with the Persian
    message;
  - message length limits;
  - topic and location choices;
  - `aria-describedby` on errors.
- Spam:
  - honeypot → redirect with nothing saved;
  - too fast / expired timestamp;
  - the 4th message within 10 minutes → 429 with the text kept;
  - the daily cap;
  - a different IP isn't limited;
  - `X-Real-IP` is preferred over `REMOTE_ADDR`;
  - only the hash is stored.
- PRG: success → 302 to `#contact-form`, one row saved, message shown on the
  next GET; CSRF enforced (`Client(enforce_csrf_checks=True)`).
- Admin:
  - the singleton redirect;
  - the change page renders with its inlines;
  - message admin add is forbidden;
  - fields are read-only except `is_handled`;
  - delete is superuser-only.
- Models: channel and location `clean()`; the map image cleanup signal.
- Migrations: seed creates topics and branch locations; the D5 migration
  changes only rows still at `#`, leaves edited rows alone and reverses.
- Existing `website.tests` keep passing (the landing test still finds «تماس
  با ما»).

### Docs

- `docs/apps/website.md`: models, admin, view, front end, spam rules.
- `docs/database.md` and `docs/database-mermaid.md`: the five new models.
- `docs/architecture-decisions.md`: ADR-024 (D15).
- `docs/changelog.md`.
- Work report `docs/plans/2026-10-contact-page.md` on the feature branch.

---

## 5. Verification

- `makemigrations --check --dry-run` is clean.
- Migrations forward and back on a **scratch SQLite copy** (`migrate website
  0002` then forward again). The D5 reverse is checked by a test too.
- `website` tests, then the full suite in the background on the Postgres test
  database. Baseline on `main` first and compare. The only expected failure is
  the known `scheduling…test_invalid_color_in_database_never_reaches_style`.
- Headless Chrome screenshots at 1280px and 375px: page, form with errors and
  success state, with a check that `scrollWidth <= innerWidth` at 375px.
  Shared in the conversation.

## 6. Not touched

- The production database.
- Migrating the local Docker database.
- The landing page's styles, including the contrast follow-up from finding 2.
- `SiteSettings` fields, existing nav and footer rows (unless D5 is approved),
  and email settings.
- Nothing is committed, pushed or merged on the feature branch unless you ask.
