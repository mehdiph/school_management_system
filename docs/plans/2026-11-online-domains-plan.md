# Plan: allowed domains for online platforms (bug fix)

Status: **plan only, waiting for approval.** Nothing implemented yet. Work will go on `fix/online-domains`,
branched from `main` (6d6321b, which has online classes Phase 1 merged).

## The report

Adding an event with `https://skyroom.online/ch/nasle_ghalam/sheshom1-1` on a platform whose «دامنه‌های مجاز»
shows `skyroom.online` is refused with «دامنه‌ی این لینک جزو دامنه‌های مجاز این پلتفرم نیست».

## 1. Cause

**With exactly those two strings, the validator accepts the link.** I reproduced it with
`validate_https_url(link, "skyroom.online")`, so either the link or the stored text holds more than what's
visible. I couldn't read the row where the error happened: the running Docker container still runs an image
without `online_classes`, and no local or scratch database has a platform row. So this section is a reproduction,
not a reading of that row (see Q1).

How the code compares (`online_classes/validators.py`):

- Allowed domains: `split_domains` splits on whitespace and `, ، ; ؛` and lower-cases. `validate_domains`
  refuses (on save) anything that isn't a plain ASCII domain, including a scheme, a path, a trailing dot, a trailing
  slash and zero-width/bidi characters. Upper case and surrounding spaces are already harmless. **`www.` is kept:**
  `www.skyroom.online` saves fine and then accepts only `www.skyroom.online` and its subdomains, *not*
  `skyroom.online`.
- The link: the "space or invalid character" check only looks for ASCII whitespace/control characters and `\`.
  Django's `URLValidator` accepts any character from U+00A1 to U+FFFF in a host, so invisible Unicode marks
  get through. `urlsplit(...).hostname` then keeps them, and the host no longer equals `skyroom.online`.

Each of these produces the reported message exactly:

| Where | Value | Result today |
|---|---|---|
| link | `https://skyroom.online‏/ch/…` (U+200F RLM after the host) | «دامنه‌ی این لینک جزو …» |
| link | `https://‏skyroom.online/…`, `https://skyroom‌.online/…` (RLM/ZWNJ inside the host) | same |
| link | `https://skyroom.online./…` (trailing dot) | same |
| stored | `www.skyroom.online` (saves without error) | same, for the link without `www` |

The variants with invisible characters in the *stored* text can't be the cause, because saving them is already
refused. **Most likely cause:** an invisible direction mark (U+200E/U+200F) was copied along with the link,
which is common when it comes from a Persian chat or document. The mark sat right after `skyroom.online`, so it
became part of the host. The message blames the domain, so there's no way to see the real problem. The second
candidate is a stored `www.skyroom.online`.

Also found: invisible marks in the link's *path* (e.g. a trailing RLM) are accepted and stored today.

## 2. Decisions (please confirm)

- **D1, `www` (policy):** a stored domain covers itself and all its subdomains (as now), and a leading `www.` is
  removed when normalising. Entering `www.example.com` or `example.com` stores `example.com`, which accepts
  `example.com`, `www.example.com` and `class.example.com`. This is slightly wider than "only www" (it also allows
  other subdomains of the same domain), and I think that's right because the same owner controls them. The
  alternative is to keep `www.` stored and also accept the bare domain; it's narrower but adds a second matching rule.
- **D2, normalising each allowed-domain line on save:** trim surrounding whitespace and invisible characters
  (ZWNJ/ZWJ/ZWSP, LRM/RLM, bidi embeddings and isolates, BOM); remove the scheme (`https://`), any `user@`, the path,
  query and fragment, the port, a trailing dot, a leading `*.` and a leading `www.`; turn Persian/Arabic digits into
  Latin digits and `۔ ٫ 。 ．` into `.`; lower-case; drop duplicates and empty lines; store one domain per line.
  A line that still isn't a valid ASCII hostname (Persian letters, a bare word like `skyroom`, an IP address) is
  refused. All bad lines are named in one error:
  - Persian/Arabic letters: «‎«اسکای‌روم»‎: نام دامنه باید با حروف انگلیسی باشد، مثل skyroom.online»
  - anything else: «‎«skyroom»‎ دامنه‌ی معتبری نیست؛ فقط نام دامنه را بنویسید، مثل skyroom.online»
  Commas and Persian/Latin semicolons still work as separators.
- **D3, where normalising happens:** in the model (`OnlinePlatform.clean()` writes the normalised text, and the
  field validator accepts anything that normalises), so the admin form and any `full_clean()` path agree. The
  admin shows the stored, normalised list after saving. **No data migration.** Matching also normalises when
  reading (same function, ignoring unusable lines), so an existing `www.skyroom.online` row already accepts
  `skyroom.online` before anyone re-saves it.
- **D4, the link side (rule change):** the link itself isn't rewritten beyond trimming whitespace and invisible
  characters at both ends. Inside the link:
  - Bidi controls and zero-width characters (U+200B, U+200E/F, U+202A–E, U+2066–9, U+FEFF) are refused with
    «لینک نویسه‌ی نامرئی دارد (معمولاً از کپی کردن متن فارسی می‌آید)؛ لینک را دوباره کپی یا تایپ کنید.»
    ZWNJ (U+200C) is still allowed in the path because Persian slugs use it.
  - A host with anything but ASCII letters, digits, `-` and `.` is refused, with
    «دامنه‌ی لینک باید با حروف انگلیسی باشد.» This means IDN (Persian-script) domains are no longer accepted
    for links. They also can't match any allowed domain, and they're a look-alike risk. **Policy: confirm.**
  - A trailing dot in the host (`skyroom.online.`) counts as the same host. The port is ignored (as now).
  These rules apply wherever links are validated: event `join_url`, personal access `url` (form and Excel import),
  platform `support_url` and announcement buttons. The render-time `safe_*` checks get them too.
- **D5, the event error lists the allowed domains and the host read from the link:**
  «دامنه‌ی این لینک (example.com) جزو دامنه‌های مجاز این پلتفرم نیست. دامنه‌های مجاز: skyroom.online، monta.ir
  (و زیردامنه‌هایشان).» The same message appears in the personal-access form and the Excel import rows. The host
  isn't secret; the importer already shows only the host.

## 3. Implementation outline

- **validators.py:** `normalise_domain(line)` and `normalise_domains(text)` → `(domains, errors)`;
  `validate_domains` raises the collected errors; `split_domains` returns the normalised usable domains;
  `validate_https_url` trims the ends, refuses invisible marks and non-ASCII hosts, drops a trailing host dot and
  builds the D5 message. One set of invisible-character constants.
- **models/platform.py:** `clean()` stores the normalised text; help text mentions one domain per line and that
  `www` and subdomains are included. A help-text change makes a no-op `AlterField` migration
  (`online_classes.0002`, no database effect).
- **event model / access form / importer:** no logic change; they already call `validate_https_url` with the
  platform's text. The access form and the event model strip the link's ends via the validator's helper.
- **admin:** `domains_summary` shows the normalised list (already uses `domains`).
- **Tests** (`online_classes/tests/test_validators.py`, plus admin tests for saving a platform):
  - each normalisation case: scheme, path, port, `user@`, whitespace, ZWNJ/RLM/BOM, trailing dot and slash, `*.`,
    `www.`, upper case, Persian digits and full stops, duplicates, separators;
  - refusals with the right Persian message for Persian letters, a bare word, an IP, and several bad lines at once;
  - platform admin save stores the normalised text;
  - `www` in either place accepts both;
  - the reported link with RLM after or inside the host, and a trailing host dot;
  - a non-ASCII host is refused, and ZWNJ in the path is still accepted;
  - the error lists the allowed domains in the event admin, the access form and the import preview;
  - existing tests (`user@host`, look-alike domains like `skyroom.online.evil.com`, `evilskyroom.online`) still
    pass.
- **Docs:** `docs/apps/online_classes.md` §5, ADR-027 (validator paragraph: `www`, invisible marks, ASCII hosts),
  `docs/changelog.md`, and the report `docs/plans/2026-11-online-domains.md`.

## 4. Verification and what I won't touch

- Baseline the online_classes tests on `main`, then the full suite on PostgreSQL in the background, compared
  with the last run (1264 OK).
- `makemigrations --check`; `0002` applies and reverses on the test database.
- I won't touch the local Docker database (it isn't migrated for online classes yet anyway), production, or any
  stored platform/event row.

## 5. Questions

- **Q1:** Where did you see the error (which server or database)? If you can run this there, it confirms which
  of the two causes it was:
  `python manage.py shell -c "from online_classes.models import OnlinePlatform as P; [print(p.pk, ascii(p.allowed_domains)) for p in P.objects.all()]"`
  and paste the link into the event form again after typing it by hand. If it works when typed by hand, the
  pasted text carried an invisible mark.
