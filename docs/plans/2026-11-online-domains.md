# Report: allowed domains for online platforms (bug fix)

**Status:** committed on `fix/online-domains` (from `main` at 827518c), merged into `main` and pushed on
2026-11-17. **Not deployed.** Plan: `docs/plans/2026-11-online-domains-plan.md` (approved 2026-11-17 with D4 changed).

## 1. Summary and reasoning

**The report.** `https://skyroom.online/ch/nasle_ghalam/sheshom1-1` was refused with «دامنه‌ی این لینک جزو
دامنه‌های مجاز این پلتفرم نیست» on a platform whose «دامنه‌های مجاز» showed `skyroom.online`.

**Cause.** With exactly those two strings, the old validator accepted the link. The text that was submitted held
more than what was visible. I couldn't read the row where it happened: the running Docker image predates
`online_classes`, and the environment wasn't stated. So the cause comes from reproducing it:

- **Most likely:** an invisible direction mark (RLM/LRM) was copied along with the link from a Persian messenger.
  The "invalid character" check only looked at ASCII whitespace and control characters, and Django's
  `URLValidator` accepts any character from U+00A1 to U+FFFF in a host. So `skyroom.online‏` became the host, didn't
  equal `skyroom.online`, and the error blamed the domain.
- **Also possible:** a stored `www.skyroom.online`, which saved without error and then refused the bare domain.
- **Ruled out:** invisible characters, a scheme or a path in the stored text, because saving those was already
  refused.

Both possible causes are fixed.

**Fix.**
- `clean_url` removes bidi and zero-width marks (ZWNJ only from the scheme and host) before every check, and the
  cleaned link is stored and rendered.
- Allowed domains are normalised on save and when read, and `www.` is dropped, so `www` and the bare domain are
  equivalent.
- The domain error names the host and lists the allowed domains.

**Rejected alternatives.**
- Refusing links with invisible marks: rejected at approval, because retyping long exam links causes more mistakes.
- Keeping `www.` stored and adding a second matching rule: one rule (a domain covers its subdomains) is simpler and
  equally safe.
- A data migration to normalise existing rows: unnecessary, since matching normalises when it reads.

## 2. Files changed / added

| Area | File | Change |
|---|---|---|
| Validators | `online_classes/validators.py` | `clean_url`; ASCII-host rule; trailing host dot; D5 message; `normalise_domains`, `tidy_domains`; `split_domains`/`validate_domains` built on them; `safe_*` return the cleaned link |
| Models | `online_classes/models/platform.py` | `clean_fields` tidies `allowed_domains` and cleans `support_url`; `safe_support_url`; help text |
| | `online_classes/models/event.py` | `clean_fields` cleans `join_url` |
| | `online_classes/models/announcement.py` | `clean_fields` cleans `button_url`; `button_is_external` reads the safe (cleaned) link |
| Forms / import | `online_classes/forms.py` | access row `clean_url` stores the cleaned link |
| | `online_classes/importer.py` | the link cell is cleaned when the row is built (preview and confirm both re-validate from the cells) |
| Template | `online_classes/templates/online_classes/_event_card.html` | support link via `safe_support_url` |
| Migration | `online_classes/migrations/0002_allowed_domains_help.py` | help text only |
| Tests | `online_classes/tests/test_links.py` (new), `online_classes/tests/test_validators.py`, `online_classes/tests/test_importer.py` (flaky assertion) | see §7 |
| Docs | `docs/apps/online_classes.md` §5, `docs/architecture-decisions.md` (ADR-027 amendment), `docs/changelog.md`, this report | |

## 3. Models and migrations

`online_classes.0002_allowed_domains_help`: `AlterField` on `OnlinePlatform.allowed_domains`, help text only.
`sqlmigrate` prints `(no-op)`. It was applied, reversed to `0001` and re-applied on a scratch SQLite database, and
applied by the PostgreSQL test run. `makemigrations --check` reports no changes. No stored row is changed: existing
`www.` domains and links with marks are normalised when read or rendered, and are stored cleaned the next time
someone saves them. Rollback: revert the branch; `0002` reverses with no database effect.

## 4. URLs, views and permissions

No changes. The same admin pages and the student page; who can and who gets 403 is unchanged.

## 5. Settings

None. The character sets (`INVISIBLE`, ZWNJ handling) are constants in `online_classes/validators.py`, read only
there.

## 6. Decisions

- D1: a leading `www.` is dropped; a domain covers itself and all subdomains.
- D2: each allowed-domain line is normalised; unusable lines are named in a Persian error, and if any are refused the
  text is kept as typed.
- D3: normalising happens in the model (`clean_fields`), with no data migration; reading normalises too.
- D4 (changed at approval): invisible marks are removed, not refused; the cleaned link is stored and rendered; a
  non-ASCII host is refused (no IDN).
- D5: the error names the host and lists the allowed domains, in the event admin, the access rows and the import.

Resolved during implementation:
- **U+061C (Arabic letter mark) is removed too.** It's a bidi control that Persian/Arabic text carries, though it
  wasn't in the approved list.
- **ZWJ (U+200D) stays in links** (it isn't in the approved list) but is removed from domains along with ZWNJ.
- **Punycode hosts (`xn--…`) pass.** They are plain ASCII, as the rule says.
- **Surrounding whitespace is trimmed** in the validator itself. `"https://example.com/\n"` was refused before and
  is now trimmed and accepted; a newline or a non-breaking space inside a link is still refused.
- **Cleaning happens in `clean_fields`**, not `clean`, so the field validators check the same value that is stored.
- **The support link was rendered without the render-time check.** It now goes through `safe_support_url`, as §5
  of the app doc already promised.
- **An Excel cell of only marks counts as empty.** A row with nothing else is skipped, as before.

## 7. Tests

38 new tests: 37 in `online_classes/tests/test_links.py` and 1 in `test_validators.py`.

`test_links.py`:

- `clean_url`: each mark, everywhere; ZWNJ removed from the scheme and host and kept in the path, query and
  fragment; trimming; empty values; internal paths.
- Validation:
  - the reported link with an RLM after the host, inside it, or around the whole link;
  - a trailing dot and a port;
  - non-ASCII hosts refused, including a Cyrillic look-alike;
  - marks can't hide `user@host`;
  - spaces inside a link still refused;
  - the D5 message;
  - look-alike domains still refused;
  - button links.
- Domain normalisation: every case from D2, separators and duplicates, each refusal with its message, text kept as
  typed on error, `www` either way, and old rows read normalised.
- Each path stores the cleaned link and shows the D5 error:
  - platform admin (domains and `support_url`) and `full_clean`;
  - event admin, including a `www.` platform with a bare link;
  - access inline row;
  - announcement button;
  - Excel import (validate, save, and the import page end to end).
- Student page: an old shared link, personal link and support link with marks render cleaned, and no RLM reaches
  the HTML.

`test_validators.py`, changed where the approved rules legitimately change behaviour: the `\n` case moved from
"refused" to "trimmed" (the new test), a newline inside a link is still refused, and `test_domain_list` now expects a pasted link, a path and `*.` to be normalised, with
`skyroom`, a Persian domain and an IP still refused.

Results:

| Run | Result |
|---|---|
| Baseline on `main`, `online_classes` + `student`, SQLite | 225 OK |
| Branch, `online_classes` + `student`, SQLite | 263 OK |
| Last full PostgreSQL run before this fix (c250e64) | 1264 OK |
| Branch, full suite, PostgreSQL | 1302 OK (1264 + 38 new), 1582 s |
| Branch, full suite, SQLite | 1301 OK, 1 skipped (the `select_for_update` test, PostgreSQL only), 1 failure in a flaky test (below), 1527 s |
| `online_classes.tests.test_importer` after fixing the flaky test, SQLite, 3 runs | 37 OK each |

**Flaky test found and fixed.** `test_importer.SaveTests.test_creates_encrypted_rows_with_who_did_it` (from
Phase 1, not touched by this fix) asserted that `"pw"` doesn't appear in a random Fernet token. A roughly
100-character base64 token contains `pw` by chance about 2% of the time, and it did on the SQLite run. The test now
uses `pw-secret`, like the other secret checks. It's the same assertion and isn't weakened. The other "not in the
ciphertext" checks use Persian text or long strings, so they can't hit this.

## 8. Discrepancies between docs and code

- `docs/apps/online_classes.md` §5 said templates check every link again when rendering, but the platform's
  `support_url` was rendered directly. It's fixed, so the doc is now true.

## 9. Open questions and deploy notes

- **Which environment showed the error** wasn't stated. To confirm the cause there:
  `python manage.py shell -c "from online_classes.models import OnlinePlatform as P; [print(p.pk, ascii(p.allowed_domains)) for p in P.objects.all()]"`
  (`‏` or `www.` in the output identifies it).
- **Deploy:** together with online classes Phase 1 (see `docs/plans/2026-11-online-classes.md` §9), migrate
  `online_classes` up to `0002`. No collectstatic change and no data to set up.
- **Brief the admins:**
  - pasting a link straight from a messenger now works;
  - allowed domains can be typed in any form (a whole link, `www.`), and only the domain is kept;
  - a domain covers all its subdomains.
