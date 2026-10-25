# Website App Documentation

The `website` app is the public site: the landing page (`/`) and the contact
page (`/contact/`). All of their text and images are editable from the Django
admin; nothing on the pages is hardcoded anymore.

---

## 1. Models (`website/models/`)

Two singletons (always `pk=1`, see `SingletonModel` in `models/base.py`) hold
single-value content; the repeatable blocks hang off them by foreign key so
they are edited as admin inlines.

| Model | Purpose | Children (inlines) |
|---|---|---|
| `SiteSettings` | site name, logo, login button, footer texts, meta title/description — used by `base.html` on every page | `NavMenuItem`, `FooterLink` |
| `LandingPage` | intro, "why us", active-learning and teachers section texts/images, plus one `show_*` switch per section | `HeroSlide`, `FeatureCard`, `LearningPoint`, `LandingTeacher` |
| `ContactPage` | contact page texts (hero, section titles, form, success message, FAQ teaser, meta title/description), plus one `show_*` switch per section | `ContactLocation`, `ContactChannel`, `ContactTopic` |

`ContactMessage` (not a singleton child) stores what the contact form sends;
see §5.

* `SingletonModel.load()` returns the row, creating it on first use; `delete()`
  is a no-op.
* Repeatable models extend `OrderedItem` (`order`, `is_active`, `created_at`,
  ordered by `order`).
* `LandingTeacher.teacher` optionally links a `staff.TeacherProfile`.
  `display_name`, `photo_url` and `display_specialty` prefer the
  `*_override` fields, then fall back to the user's name/avatar and the
  profile's `field_of_study`.
* Images: per-model `upload_to`, jpg/jpeg/png/webp only, max 2 MB
  (`website/validators.py`). Replaced or deleted files are removed from
  MEDIA_ROOT after the transaction commits (`website/signals.py`).
* Links are `CharField`s validated by `validate_link`: relative paths, `#…`,
  `http(s)://`, `mailto:` and `tel:` only (no `javascript:`).
* `static_fallback` (not editable) lets seeded rows show the original images
  from `website/static` until an image is uploaded.

* `ContactLocation.branch` optionally links a `school.Branch`:
  `display_title`, `display_address` and the branch phone fall back to the
  branch's `name`, `address` and `phone_number` (like `LandingTeacher`).
  Locations of inactive branches are not shown. `map_links` lists only the
  filled-in Neshan / Balad / Google Maps links.
* `ContactChannel` is a phone, mobile or email, school-wide (no location)
  or under one location. `value` is shown as typed (in Persian digits);
  `href` is `tel:` with ASCII digits or `mailto:`; `clean()` validates the
  value by kind (mobiles with `accounts.validators.validate_mobile`).

Migration `0002_seed_content` loads the original page content.
`0004_seed_contact` creates the contact page row, five topics and one
location per active branch (only creates rows). `0005_link_contact_menu`
points the «تماس با ما» menu and footer rows at `/contact/`, only where they
were still `#`; its reverse resets only rows still at `/contact/`.

## 2. Admin

* **مدیریت صفحه اصلی** (`LandingPage`), **صفحه تماس با ما** (`ContactPage`)
  and **تنظیمات سایت** (`SiteSettings`) open their single record directly;
  add/delete are disabled.
* On **صفحه تماس با ما**, a channel's «شعبه» dropdown lists saved locations
  only: save a new location before attaching phones to it.
* **پیام‌های تماس با ما** (`ContactMessage`): see §5.
* Every image has a thumbnail preview; `order` is editable inline;
  `LandingTeacher.teacher` uses autocomplete.

## 3. View and templates

* `views.website` loads `LandingPage` and prefetches only the enabled sections'
  active items (teachers with `select_related("teacher__staff__user")`), so the
  query count doesn't grow with the number of items.
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
  `index.css` and reusing its `--lp-*` tokens. Adds `--ct-action #b4501c`
  (the brand orange fails AA under white text; this darker step passes) and
  the notebook-paper tokens. The form is a notebook page (margin line,
  ruled message field). Below 768px a phone bar («تماس با دفتر»,
  «مسیریابی») is fixed to the bottom: under the header so the nav drawer
  and overlay cover it, padded by `env(safe-area-inset-bottom)`, with
  matching padding under the footer, and hidden while a form field has
  focus (CSS `:has()`, plus a class from JS). `contact.js` only enhances:
  copy buttons (hidden without JS), inline validation with the server's
  messages, a busy submit button. Everything works without JS.
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
