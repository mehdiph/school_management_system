# Plan: blog follow-ups (PostgreSQL verification and three small fixes)

Status: **approved 2026-10-26 as recommended** (D1–D3). Work goes on
`fix/blog-followups`, created from `main` after this update. Nothing is committed on the
branch until the user asks.

## What was found while reading

- **PostgreSQL answers again.** From the host, `POSTGRES_HOST=localhost`
  reaches PostgreSQL 16.15; this was a read-only `select version()`. No
  migration was run and no data was touched.
- **`login.js` always throws, not only sometimes.** `accounts/login.html`
  has neither `.form-container` nor `.username-input`, so line 4 throws on
  every load of the login page. The `fullscreenchange` listener never ran.
  With the guards the script does nothing on this page. It keeps its current
  behaviour on any page that does have both elements.
- **`student_info` breaks the error page meant for this case.**
  `student.decorators.student_required` already handles a student with no
  `StudentProfile`: it raises `PermissionDenied` with
  «پروفایل دانش‌آموزی برای این حساب ثبت نشده است.». But the 403 page runs the
  context processors, and `student_info` reads `request.user.student_profile`
  directly. So that user gets a 500 instead of the 403. The same thing
  happens on any other page, such as the public website, the blog and the
  login redirect.
- `tinyhtml5==2.0.0` is on line 24 of `requirements.txt`, right above
  `weasyprint==67.0`. `blog/content.py` imports it directly.

## Decisions

- **D1. What to fix if PostgreSQL fails.** Proposed:
  - Failures caused by the blog code: fix them on the branch, explain the
    cause in the report, and re-run the affected apps on both databases.
  - Failures that are older than the blog, or that would need a policy or
    data change: report them and ask before fixing.

  To tell the two apart, a failing test is re-run on `f86b6b8`, the commit
  before the merge.
- **D2. Student with no profile.** Proposed: `student_info` returns `{}`,
  the same as for a non-student. The topbar then shows «دانش‌آموز» without a
  class, and the 403 from `student_required` renders as a 403. No new message
  and no redirect.
- **D3. Report rows.** The three PostgreSQL rows say "deferred" or "skipped"
  (§1.8, §2.8 and §3.7 of `docs/plans/2026-10-blog.md`). Proposed: each
  becomes the result of this run on `main` 271e40b, with the date and the
  test count. The rows keep a note that the run happened after the merge, not
  before it. The state line at the top and the "Still to do" item are
  updated to match. The three items in §3.8 are marked as fixed on
  `fix/blog-followups`.

## Implementation outline

1. **Verification.** On `main` (271e40b), run the full suite on PostgreSQL
   in the background, serially, and grep the log. Then run
   `blog website` on SQLite (`POSTGRES_DB=`). The two runs don't overlap.
2. **`accounts/static/accounts/js/login.js`.** Add the listener and the
   `focus()` only when both elements exist.
3. **`student/context_processors.py`.** Return `{}` when the user has no
   `student_profile`, by catching `RelatedObjectDoesNotExist`; the rest stays
   as it is.
4. **Tests, in `student/tests.py`.**
   - The context processor returns `{}` for a student with no profile.
   - A `student_required` page gives that user a 403, not a 500.
   - A student with a profile still gets `student` and `school_class`.
5. **`requirements.txt`.** Add a comment above `tinyhtml5==2.0.0` saying
   that `blog/content.py` imports it directly, so it stays pinned even if
   WeasyPrint stops depending on it or changes its version.
6. **Docs.**
   - `docs/changelog.md`: one fixes entry.
   - `docs/apps/student.md`: the context processor's no-profile case.
   - `docs/plans/2026-10-blog.md`: as in D3.

## Verification

- `makemigrations --check --dry-run`; no migration is expected.
- `student`, `accounts`, `blog` and `website` on both databases after the
  fixes.
- The login page in a headless browser shows no console error.

## Not touched

- The production database and the local Docker database: no migrate, and no
  data rows changed.
- The student views. The decorator already covers them.
- The login page's markup and behaviour.
- Docker and the VPN.
