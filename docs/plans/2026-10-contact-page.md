# Work report: public «تماس با ما» page

**Status: committed on `feature/contact-page` and merged into `main` locally
on 2026-10-25. Not pushed, not deployed.** No migration was run on the local Docker database
or on production. The plan (`docs/plans/2026-10-contact-page-plan.md`) was
approved on 2026-10-25 and is on `main` (`deba498`, updated in `b3652ce`).

---

## 1. Summary and reasoning

`/contact/` (`website:contact`) is a new page of the public site, built for
parents: call the school, find a branch, or leave a message.

**Page structure:**
- a hero with a call button (the first school-wide phone) and «پیام بگذارید»;
- the footer's social links;
- school-wide phones, mobiles and email, with copy buttons;
- one address block per branch: address, hours, phones, a map picture and
  Neshan / Balad / Google Maps links;
- the contact form;
- below 768px, a phone bar with «تماس با دفتر» and «مسیریابی».

**Design («دفتر مدرسه»).** The page reuses the landing page's tokens, font,
cream panels, glass sections and blob shapes. The one distinctive element is
the form, drawn as a page of a school notebook: an orange margin line and a
ruled message field. The landing page's orange fails AA contrast under white
text (2.72:1), so the page adds one darker step of the same hue,
`--ct-action #b4501c` (5.12:1). There are no entrance animations; the only
motion responds to the user («کپی شد», «در حال ثبت…»).

**Content.** All content is edited in the admin: a `ContactPage` singleton
with `ContactLocation`, `ContactChannel` and `ContactTopic` inlines. A
location linked to a `school.Branch` shows the branch's name, address and
phone, so they are typed once.

**Messages.** Form messages are stored (`ContactMessage`), never emailed.
Spam is held off by a honeypot, a signed render time and a database-counted
rate limit. The limit applies per mobile and per device, because of CGNAT.
Only an HMAC of the IP is kept (ADR-024).

**Rejected alternatives:**
- an embedded map iframe (ADR-021);
- generating map links from coordinates (fragile URL formats);
- a cache-based rate limit (no shared cache, and the worker count comes from
  `WEB_CONCURRENCY`);
- a live «دفتر الان باز است» badge (wrong on holidays and closures; D13);
- a big-number hero (generic);
- email notification (not approved, and email isn't configured).

## 2. Files changed / added

### Models, migrations, settings

| File | Change |
|---|---|
| `website/models/contact.py` | new: `ContactPage`, `ContactLocation`, `ContactChannel`, `ContactTopic`, `ContactMessage` |
| `website/models/__init__.py` | exports |
| `website/migrations/0003_contact.py` | tables and indexes |
| `website/migrations/0004_seed_contact.py` | page row, 5 topics, 1 location per active branch; depends on `school.0006_assign_subject_colors` (latest) |
| `website/migrations/0005_link_contact_menu.py` | «تماس با ما» nav and footer rows from `#` to `/contact/`, reversible |
| `website/signals.py` | `ContactPage`, `ContactLocation` images cleaned up like the others |
| `teachlog/config/settings/base.py` | `CONTACT_*` limits, `CLIENT_IP_HEADER` |

### Forms, services, view

| File | Change |
|---|---|
| `website/forms.py` | new: `ContactForm`, `form_token` (time trap) |
| `website/services.py` | new: `client_ip`, `client_ip_hash`, `rate_limited`, `submit_contact_message` |
| `website/views.py` | `contact` view (landing view unchanged) |
| `website/urls.py` | `contact/` |
| `website/admin.py` | `ContactPageAdmin` (+3 inlines), `ContactMessageAdmin` |
| `website/templatetags/website_tags.py` | new: `social_only` filter |

### Templates and static files

| File | Change |
|---|---|
| `website/templates/website/contact.html`, `website/templates/website/contact/_channel.html`, `_location.html`, `_form.html`, `_field.html` | new |
| `template/base.html` | `viewport` and `messages` blocks (default output unchanged) |
| `website/static/website/css/contact.css` | new, mobile-first |
| `website/static/website/js/contact.js` | new, vanilla, enhancement only |

### Tests and docs

| File | Change |
|---|---|
| `website/test_contact.py` | new, 50 tests |
| `docs/apps/website.md` | contact page, §5 form/spam/client IP/permissions |
| `docs/database.md`, `docs/database-mermaid.md` | contact tables |
| `docs/architecture-decisions.md` | ADR-024 |
| `docs/changelog.md` | entry |
| `docs/plans/2026-10-contact-page.md` | this report |

## 3. Models and migrations

**`0003_contact`** creates five tables:
- `website_contactpage`;
- `website_contactlocation` (FK `school_branch`, `SET_NULL`);
- `website_contactchannel` (FK location, `CASCADE`);
- `website_contacttopic`;
- `website_contactmessage`, with indexes `website_contact_ip_idx (ip_hash,
  created_at)` and `website_contact_mobile_idx (mobile, created_at)`.

No existing table changes.

**`0004_seed_contact`** only creates rows:
- the page row (`get_or_create`);
- 5 topics, if there are none;
- one location per active branch, if there are none.

On production this creates locations for the two active branches, linked to
them. Re-running never duplicates rows.

**`0005_link_contact_menu`** updates `NavMenuItem` / `FooterLink` rows with
title «تماس با ما» **and** url `#` to `/contact/` (approved in D5). Rows an
admin has edited are untouched. The reverse resets only rows still at
`/contact/`.

**Verified:**
- `makemigrations --check --dry-run`: no changes.
- On a scratch SQLite copy with sample branches and data:
  - `migrate website 0002` unapplied 0005, 0004 and 0003 cleanly, and the
    links went back to `#`;
  - `migrate website` re-applied all three, seeding 5 topics and 2
    locations, with the links at `/contact/`.
- The seed and link functions are also tested directly: no duplicates, edited
  rows untouched, and the reverse.

**Rollback:** `migrate website 0002` (drops the five tables, including stored
messages, so export them first if any matter), then deploy the previous
code.

## 4. URLs, views and permissions

| URL | Who | Notes |
|---|---|---|
| `GET /contact/` | everyone | 405 for other methods except POST |
| `POST /contact/` | everyone, with CSRF | Outcomes: success → 302 to `/contact/#contact-form`; honeypot → the same 302 with nothing saved; invalid → 200 with errors; rate-limited → 429. Ignored (200) when the form is switched off. |
| admin «صفحه تماس با ما» | staff with `website.change_contactpage` | singleton: add/delete disabled |
| admin «پیام‌های تماس با ما» | staff with `website.view_contactmessage` (read), `change_contactmessage` (only «پیگیری شد») | add disabled for everyone; delete superuser only; `ip_hash` never shown |

How to grant the office permissions is in `docs/apps/website.md` §5. No group
or permission is created by a migration.

## 5. Settings and configurable values

| Setting | Default | Meaning |
|---|---|---|
| `CONTACT_RATE_LIMIT` | `(3, 600)` | per mobile **and** per device: 3 messages per 10 minutes |
| `CONTACT_DAILY_LIMIT` | `50` | per device, over the last 24 hours |
| `CONTACT_MIN_FILL_SECONDS` | `3` | faster submissions are refused |
| `CONTACT_MAX_FORM_AGE_SECONDS` | `7200` | older forms must be resubmitted |
| `CLIENT_IP_HEADER` | env var, default `X-Real-IP` | the header with the visitor's IP; see below |

**Client IP and the CDN (change 2).** The site sits behind a CDN or reverse
proxy in front of nginx, so nginx's `X-Real-IP` is the CDN edge's address.
`CLIENT_IP_HEADER` must be set in the production `.env` to the CDN's
client-IP header:
- `CF-Connecting-IP` for Cloudflare;
- `AR-Real-IP` for ArvanCloud.

It's written as the header name or the `request.META` key. The first address
of a comma-separated value is used, and a missing or malformed value falls
back to `REMOTE_ADDR`.

Left at the default behind a CDN, all visitors would share a few "devices"
and reach the daily cap together. The header can be forged by anyone who
reaches the origin directly, so the origin should accept traffic only from
the CDN. Without that, only the per-mobile limit really holds. Documented in
`docs/apps/website.md` §5 and ADR-024.

## 6. Decisions

**Approved:**
- D1: form fields as proposed.
- D2: option A (map picture + pasted share links).
- D3: `ContactPage` singleton + inlines, with branch fallback.
- D4: footer unchanged; social links reused.
- D5: reversible link migration.
- D6: honeypot, time trap, DB rate limit.
- D7: HMAC of the IP only.
- D8: read-only except «پیگیری شد».
- D9: PRG, with the confirmation in the form card.
- D10: no email.
- D11: seed one location per active branch.
- D12: phone bar.
- D13: no "open now" badge.
- D14: `/contact/`.
- D15: ADR-024.

**Changes 1–5 from the approval:**
1. **Rate limit:** the short window applies per mobile and per IP hash; the
   daily cap per IP is 50. Tests cover a shared IP with different mobiles.
2. **Client IP:** read from `CLIENT_IP_HEADER`.
3. **Office permissions:** documented; nothing granted in migrations.
4. **Phone bar:** z-index 50, under the header's 100, so the drawer and
   overlay cover it. It uses `env(safe-area-inset-bottom)` (with
   `viewport-fit=cover` on this page only), and there's matching padding
   under the footer. It hides on field focus via CSS `:has()` plus a JS
   class.
5. **Seed migration** depends on `school.0006`.

**Resolved during implementation:**
- **Rolling windows.** The daily cap is a rolling 24 hours, not the calendar
  day.
- **Branch status.** Locations whose branch is inactive are hidden, as are
  inactive locations.
- **Branch phone fallback.** A location shows the branch's `phone_number`
  only when it has no phone channel of its own.
- **Call target.** The hero and the bar call the first school-wide
  phone/mobile, else the first location's phone. «مسیریابی» uses the first
  location's first map link.
- **Hero image.** Without an upload it falls back to the bundled
  `website/images/teacher.jpg` (the landing page's «معلمان مجرب» picture), as
  `alt=""`.
- **Spam message.** The honeypot shows the normal success message, with the
  typed mobile.
- **No-JS validation.** The form has `novalidate`, so errors always come from
  the server in Persian when JS is off. JS validation mirrors the server's
  messages.
- **`ContactPage.meta_title`.** Added (default «تماس با ما»; the browser tab
  shows «… | site name»).
- **`ContactChannel.location` is `CASCADE`.** Deleting a location removes its
  phones rather than silently moving them to the school-wide list.
- **Interface labels in the template.** «کپی», «مسیریابی با», «ساعت کاری» and
  the error summary title live in the template, like the landing page's
  aria labels. Content texts are all in the admin.
- **Persian digits.** Phone numbers are converted by a small helper in the
  model, not `core`'s `fa_digits`, which would turn «۰۴۴-۳۳۴۴» into a range
  with an en dash.

## 7. Tests

`website/test_contact.py` has 50 tests:

- **View:**
  - content and branch fallbacks;
  - `tel:` with ASCII digits shown in Persian;
  - the branch phone fallback;
  - the call and directions targets, and no bar without them;
  - section switches; inactive locations and branches;
  - FAQ off by default;
  - social links skip `#`;
  - escaping;
  - the nav item is `is-active` with `aria-current`;
  - 405;
  - **query count stays flat** with 4 more locations, channels and topics.
- **Form:**
  - success + PRG + confirmation;
  - mobile variants accepted and refused;
  - required fields and length limits;
  - `aria-invalid` / `aria-describedby` / help ids;
  - unknown topic or location refused;
  - branch field only with 2+ locations; topic field only with topics;
  - POST ignored when the form is off;
  - CSRF enforced.
- **Spam:**
  - honeypot;
  - time trap (too fast, expired, forged);
  - the 4th message from one IP within 10 minutes → 429 with the text kept;
  - one mobile limited across IPs;
  - **shared IP with different mobiles** passes after the window;
  - daily cap and its 24-hour roll-off;
  - other IP and mobile not limited;
  - only the hash is stored.
- **Client IP:**
  - configured header wins (Cloudflare form, META form, IPv6);
  - default `X-Real-IP`;
  - first entry of a list;
  - malformed or missing header → `REMOTE_ADDR`;
  - empty setting.
- **Models:**
  - channel validation per kind, mapped to the field;
  - `href`;
  - location `clean()`;
  - `map_links`; unsafe link refused;
  - success text;
  - map image cleanup.
- **Admin:**
  - singleton with inlines;
  - Persian-digit search;
  - view-only staff can't change;
  - change staff can only tick «پیگیری شد»;
  - add forbidden; delete superuser only;
  - `ip_hash` hidden.
- **Migrations:** seed (order, inactive branch skipped, idempotent) and link
  (only `#` rows, edited rows untouched, reverse).

**Results (PostgreSQL):**

| Run | Result |
|---|---|
| Baseline, `main` (worktree) | Ran 700 tests, FAILED (errors=1): the known `scheduling…test_invalid_color_in_database_never_reaches_style` |
| Branch, full suite | Ran 750 tests (+50), FAILED (errors=1): the same known error only |
| Branch, `website` after the final `ContactChannel.clean` change (made while the full run was going) | Ran 69 tests, OK |
| Branch, full suite on the committed work (`41ed4bb`), 2026-10-25 | Ran 750 tests, FAILED (errors=1): the same known error only |
| Branch, `scheduling` after fixing that test (`Fit the invalid-colour test value…`) | Ran 140 tests, OK |

The known error is gone: the test wrote a 21-character value into
`Subject.color varchar(7)`, which PostgreSQL refuses. It now uses a
7-character invalid value and passes on both databases.

**Browser checks.** Headless Chrome (Playwright, scratch venv) against a
scratch SQLite copy with sample branches, phones, social links and generated
map pictures:
- **Layout:** 1280px full page, and 375px top with the bar, full page,
  footer end and the drawer open.
- **Phone bar:** the bar is hidden with a field focused, and back after blur.
- **Overflow:** at 375px, `scrollWidth == clientWidth == 375` for `html`,
  `body` and `.app-shell`, and no element extends past the viewport.
- **Form states:**
  - server errors with JS off;
  - the success state after a real submit;
  - the 429 state, hit naturally by repeated runs from 127.0.0.1.

## 8. Discrepancies between docs and code

- **Plan finding 6 was wrong.** Messages in `base.html` are fixed-position
  toasts that auto-dismiss (`static/js/base.js`), not inline at the top. The
  in-form confirmation (D9) is still better, because it stays put.
- **`database.md` doesn't document the `website` app's tables** (only
  `docs/apps/website.md` does). The contact tables were added to both,
  because `ContactMessage` holds visitor data and `ContactLocation` links to
  `Branch`.
- **Gunicorn's worker count isn't fixed.** The Dockerfile command doesn't
  set `--workers`, but `.env` has `WEB_CONCURRENCY`, which gunicorn reads. A
  per-process cache limit would not have been reliable.

## 9. Open questions and manual actions at deploy

1. **Set `CLIENT_IP_HEADER` in the production `.env`** to the CDN's
   client-IP header, before or with the deploy. Which CDN is in front isn't
   recorded anywhere in the repo, so I couldn't set it.
2. **Make sure the origin accepts traffic from the CDN only** (firewall or
   nginx `allow` list); otherwise the IP limit can be bypassed.
3. Back up the database, then `docker compose exec web python manage.py
   migrate` (website 0003–0005) and `collectstatic` (new `contact.css` /
   `contact.js`).
4. In the admin, **صفحه تماس با ما**:
   - add the school's phones, mobiles and email (none are seeded);
   - check the two seeded branch locations: address and phone come from
     **شعبه‌ها**, so fill those or the overrides;
   - add working hours;
   - upload a map picture per branch and paste the Neshan / Balad / Google
     Maps share links.
5. In **تنظیمات سایت**, set the social footer links (they're still `#` and
   won't show on the page until set).
6. Create the office group and accounts as described in
   `docs/apps/website.md` §5. Brief the office: messages appear only in the
   admin; tick «پیگیری شد» after calling back.
7. Follow-up, not done: the landing page's buttons also use the brand orange
   under white text (2.72:1, fails AA). `--ct-action` could be reused there.
8. Optional later: email or Telegram notification of new messages, a
   retention period for old messages, and the «دفتر الان باز است» badge.
