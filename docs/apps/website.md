# Website App Documentation

The `website` app is the public landing page (`/`). All of its text and images
are editable from the Django admin; nothing on the page is hardcoded anymore.

---

## 1. Models (`website/models/`)

Two singletons (always `pk=1`, see `SingletonModel` in `models/base.py`) hold
single-value content; the repeatable blocks hang off them by foreign key so
they are edited as admin inlines.

| Model | Purpose | Children (inlines) |
|---|---|---|
| `SiteSettings` | site name, logo, login button, footer texts, meta title/description — used by `base.html` on every page | `NavMenuItem`, `FooterLink` |
| `LandingPage` | intro, "why us", active-learning and teachers section texts/images, plus one `show_*` switch per section | `HeroSlide`, `FeatureCard`, `LearningPoint`, `LandingTeacher` |

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

Migration `0002_seed_content` loads the original page content.

## 2. Admin

* **مدیریت صفحه اصلی** (`LandingPage`) and **تنظیمات سایت** (`SiteSettings`)
  open their single record directly; add/delete are disabled.
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
  the landing and login pages. A section with no active items, or switched
  off, is not rendered.

## 4. Front end (`website/static/website/`)

* `css/index.css` — mobile-first landing styles (tokens in `:root`,
  breakpoints 576/768/992/1200px, logical properties for RTL).
* `css/nav.css` + `js/nav.js` — below 992px the menu becomes a drawer from the
  right with an overlay; closes on ✕, overlay, Esc, link click or resize to
  desktop; locks body scroll and traps focus while open.
* `js/slider.js` — hero carousel (autoplay, dots, arrows, touch swipe; pauses on
  hover/focus and honours `prefers-reduced-motion`) and the teachers row
  (native scroll-snap; arrows scroll one card; 1/2/3 cards per view).
