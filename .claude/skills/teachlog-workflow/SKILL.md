---
name: teachlog-workflow
description: Use for any feature, change or bug fix in the teachlog Django school system (models, views, templates, reports, dashboards). Defines the plan-approve-implement-document workflow, project conventions, safety rules and the work report in docs/plans.
---

# Teachlog development workflow

Teachlog is a Django school management system (PostgreSQL in production) used in Persian.
Roles include teacher, supervisor/supporter («پشتیبان», one per grade), director and admin.
Follow this workflow for every change unless the user explicitly says otherwise.

## 1. Read before you plan

1. Read the relevant docs in `docs/` first: `docs/apps/<app>.md` for every app you touch,
   `docs/database.md`, `docs/database-mermaid.md`, `docs/architecture-decisions.md` (ADRs)
   and `docs/changelog.md`. Use the names, URL namespaces and conventions you find there;
   never invent new conventions.
2. Then read the actual code of the areas involved. **If docs and code disagree, trust the
   code** and list the discrepancy in the report.
3. Look for everything that depends on what you are changing (selectors, the analytics
   engine, director/supervisor dashboards, alerts, admin, templates, tests), not only the
   files named in the request.

## 2. Plan and wait for approval

Before writing any code, present a plan and **stop until the user approves it**:

- Risks and surprises found while reading (dependencies, data issues, timing).
- Decisions that need confirmation, numbered **D1, D2, …**, each with your proposed choice
  and the reason. Flag anything that is a school/business policy rather than a technical
  choice (e.g. how a status counts in a rate) so the user decides it.
- Implementation outline grouped by area: models & migrations, services, each role's side,
  reports, tests, docs.
- How you will verify migrations and what you will NOT touch.

### Publishing the plan on `main`

The user reads plans from a copy of `main` synced elsewhere, so the plan file must reach
`origin/main` without any manual merge. Do this **before** creating the feature branch:

1. Start from a clean `main`: `git switch main` and `git pull --ff-only origin main`.
   If the working tree has changes you didn't make, or the pull is not a fast-forward,
   stop and tell the user instead of resolving it yourself.
2. Write the plan to `docs/plans/YYYY-MM-<slug>-plan.md`.
3. Stage **only that file** (`git add docs/plans/YYYY-MM-<slug>-plan.md`) and commit it
   with the subject `Add plan for <short feature name>`.
4. `git push origin main`. Never force-push. If the push is rejected, pull with
   `--ff-only` and retry once; if it still fails, stop and report.
5. Show the plan in the conversation, say it was pushed to `main` (with the commit hash),
   and stop for approval.

When the user asks for changes to the plan, edit the same file on `main` and repeat
steps 3–5 (subject `Update plan for <short feature name>`). Only after approval, create
the feature branch from the updated `main`.

This is the only thing ever committed or pushed to `main` directly. Code, migrations,
tests, other docs and the final work report stay on the feature branch.

If something is ambiguous during implementation and not covered by the approved plan,
choose the option most consistent with existing code and record it in the report.

## 3. Safety rules (never break these)

- Work on a new git branch (`feature/<slug>` or `fix/<slug>`). **Do not commit, push or
  deploy** unless the user asks. The one exception is the plan file, which is committed
  and pushed to `main` as described in "Publishing the plan on `main`" above.
- **Never touch the production database.** Do not migrate the local Docker database without
  asking first. Run migrations on the test database and on scratch SQLite copies only.
- **Never modify or delete existing data rows** (attendance, sessions, enrollments, …)
  without explicit approval. Prefer archiving (rename, keep the table) over converting.
- For model renames, pin `db_table` and use `RenameModel` so tables and rows stay intact;
  add a migration that renames `auth_permission` codenames so existing grants survive.
- Always run `makemigrations --check` and verify a migration reverses cleanly.
- Do not change values with policy meaning (cutoff dates, statuses, permissions) silently;
  put such values in settings (`teachlog/config/settings/base.py`) and read them in one place.

## 4. Code conventions

- **Layers:** business logic in `<app>/services.py`, read queries in `<app>/selectors.py`,
  access checks in `<app>/permissions.py`, reusable querysets/managers in
  `core/querysets/` and `core/managers/`. Views stay thin.
- **One definition per metric:** attendance rates, counts and alerts come from the shared
  `analytics` engine (ADR-019). Change the engine, never re-compute a metric in a page.
- **Dates:** use `jDateField` (Jalali) like the rest of the project; Jalali in the UI.
  Timetable-based rules come from `ClassSchedule`, closures from `academic_calendar`; never
  hard-code weekdays.
- **Access:** follow the existing patterns: `SupervisorScope` for supervisors,
  `require_supervisor`, superuser, or staff with the specific permission **and** branch
  access. Return 403 for forbidden access; teachers and the director's read-only panel get
  no write access unless the plan says so.
- **Concurrency:** use `get_or_create` plus row locks (`select_for_update`) where two saves
  could race, and rely on database unique constraints.
- **UI:** Persian, RTL, styled like the existing pages of the same panel (reuse the app's
  `static/<app>/css` and `js`). Must work at 375 px phone width with no horizontal scroll.
  Check new or changed pages in a headless browser at desktop (1280 px) and phone (375 px).

## 5. Tests

- Write tests for every new rule: constraints, permissions (each role that must be refused),
  service logic, boundaries (e.g. dates around a cutoff), redirects, and query counts on
  pages that have locked counts.
- Update existing tests that the change legitimately affects; never delete a test just to
  make the suite pass.
- Full run: `POSTGRES_HOST=localhost .venv/bin/python manage.py test --noinput`.
  Run a baseline on `main` first and compare. The suite has no known failures; report
  any failure.

## 6. Documentation (required, part of the task)

Update every doc affected by the change:
- `docs/apps/<app>.md` for each app touched (create it if missing),
- `docs/database.md` and the Mermaid diagram `docs/database-mermaid.md` for model changes,
- a new ADR in `docs/architecture-decisions.md` for architectural decisions (next number),
- `docs/changelog.md`,
- any doc whose statement is no longer true (e.g. "this panel is read-only").

## 7. Work report

Write `docs/plans/YYYY-MM-<slug>.md` with these sections:

1. Summary and reasoning (including rejected alternatives)
2. Files changed / added, grouped by area (tables)
3. Models and migrations, with their database effect and how they were verified; rollback notes
4. URLs, views and permission rules (who can, who gets 403)
5. Settings / configurable values and how to change them
6. Decisions taken: approved D-items plus ambiguities resolved during implementation
7. Tests: what is covered, baseline vs branch results
8. Discrepancies found between docs and code
9. Open questions and manual actions before / at deploy (backup, migrations, data to set up
   in the admin, who to brief)

State clearly at the top whether the work is committed, pushed or deployed.

The plan itself lives in `docs/plans/YYYY-MM-<slug>-plan.md` on `main` (see section 2);
the work report above is written on the feature branch.