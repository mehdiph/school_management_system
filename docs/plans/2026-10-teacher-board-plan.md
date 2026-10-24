# Teacher board («تخته‌ی هوشمند») and classroom panel login: plan

**Status:** plan only, waiting for approval. Branch `feature/teacher-board` is created; nothing is written, committed, pushed or deployed. Date: 24 October 2026 (2 Aban 1405).

The work report will be `docs/plans/2026-10-teacher-board.md`.

---

## 1. What I read

- **Docs:**
  - `architecture-decisions.md` (ADR-001…023)
  - `changelog.md`, `database.md`, `database-mermaid.md`
  - `apps/accounts.md`, `core.md`, `school.md`, `scheduling.md`, `teaching.md`, `academic_calendar.md`, `staff.md`, `supervisor.md`
  - the previous report, `plans/2026-10-director-daily-attendance.md`
  - `project-overview.md` is **empty** (§9).
- **Code:**
  - accounts: `User`, `LoginActivity`, `sessions.py` (login history, "sign out of other devices"), `ForcePasswordChangeMiddleware`, `login_form`, `role_dashboard`, the profile page, `avatars.py` (the upload-validation pattern)
  - `staff.decorators.teacher_required`, `TeacherAssignment`, `BranchAccess`
  - `core.services.access`, `BranchService`, `BranchMiddleware`, `core.admin.mixins.BranchScopedAdminMixin`
  - `Bell` (global, not per branch), `Branch`, `SchoolClass`, `ClassSubject`
  - `academic_calendar.services` (`get_slots`, `Closures`, `closing_event`) and the branch-scoped `CalendarEventAdmin`
  - `scheduling.services.build_teacher_week`, `scheduling.utils`, `teaching.services.slot_errors`
  - the teacher shell: `template/teacher/base.html`, sidebar, `static/teacher/css/tokens.css`, `shell.css`, `components.css`, `shell.js`
  - settings (`base.py`, `production.py`), `teachlog/urls.py`
  - deployment: `docker-compose.yml`, `docker-compose.local.yml`, `nginx/conf.d` and `nginx/local`, `Dockerfile`
  - `core/testing.py`, `requirements.txt`

---

## 2. Risks and surprises found while reading

1. **Every file under `MEDIA_ROOT` is public.**
   - Production nginx serves `/media/` straight from the volume with `Cache-Control: public` and no check.
   - So board PDFs must not live under `MEDIA_ROOT` at all; a new path inside `media/` is not enough.
   - This decides D8.
2. **nginx caps request bodies at 10 MB** (`client_max_body_size 10M`, both configs), so a textbook PDF will often be refused before it reaches Django. The upload location needs its own limit, matched to the setting.
3. **URLs are logged in full.**
   - gunicorn runs with `--access-logfile -` in the default format, which logs the request line with its query string.
   - nginx logs `$request` too.
   - A QR token in a path or in `?t=` would therefore be logged. This decides D11.
4. **The `Secure` cookie flag depends on an environment variable.**
   - `SESSION_COOKIE_SECURE = SECURE_SSL_REDIRECT`, which comes from the env.
   - The repo's `.env` has it `False` (laptop). I can't see the production value.
   - The device cookie must be `Secure` in production (D22).
5. **There is no shared cache.**
   - No `CACHES` is configured, so it is per-process LocMem, and there are 3 gunicorn workers.
   - Cache-based rate limits would be wrong by a factor of 3.
   - Plan: count rows in the new audit and challenge tables instead, which is exact across workers.
6. **The timetable editor deletes `ClassSubject` rows** that lose their last slot and have no sessions (`scheduling/timetable.py`).
   - A `PROTECT` foreign key from the board would break the admin timetable editor.
   - So the board's links use `SET_NULL` (document) or `CASCADE` (slot plan), never `PROTECT`.
7. **A classroom login is an ordinary Django login.**
   - `user_logged_in` records a `LoginActivity` (shown in the teacher's «ورودهای اخیر»).
   - «خروج از سایر دستگاه‌ها» and a password change end the panel session too. I think that is desirable and will document it.
   - The teacher's phone session is untouched, because the panel is a different browser.
8. **`ForcePasswordChangeMiddleware`** would send a panel session to the password page, which the panel scope blocks. Users with `must_change_password` are therefore refused on a panel with a clear message. On the phone they are already forced to change their password before they can open the approval page.
9. **Bells are global wall-clock times** (Asia/Tehran), the same in both branches. The panel's own clock may be wrong, so every timing decision is made on the server. Client timers only count down seconds the server gave them.
10. **ADR-015 says "no JSON API, every page works without JS".** A drawing board cannot meet that. Library, settings and pairing pages stay server-rendered and work without JS. The board editor and its ink API are a declared exception (D21, recorded in the new ADR).
11. **Panel browser unknown.**
    - pdf.js ≥ 4 ships only ES-module builds (module workers).
    - pdf.js 3.x has the CVE-2024-4367 class of font-eval issue, which is mitigated by `isEvalSupported: false`.
    - Without a build step, our own JS must also be written for the oldest panel browser.
    - I need the panel model and its browser version (D6).
12. **Malicious PDFs.**
    - A teacher may open a PDF from anywhere, so PDF parsing is attack surface on both sides: pdf.js in the browser, and the page-count check on the server.
    - Mitigations: size limits before parsing, refusing encrypted PDFs, `isEvalSupported: false`, a strict CSP on board pages, and serving files as `application/pdf` with `Content-Disposition: inline` and `nosniff`.
13. **Polling load.** If every panel showed a QR and polled every 1–2 s all day, 30 panels would make about 20 requests/s, about 1.7 M nginx log lines a day, and a challenge row every 90 s per panel. Hence D12.
14. **Backups:** the new private-files volume has to be added to whatever backs up `media_data` today.

---

## 3. Decisions to confirm

Items marked **(policy)** are school decisions rather than technical ones.

| # | Decision | Proposal and reason |
| --- | --- | --- |
| **D1** | Apps | **Two new apps.**<br>• `board`: documents, pages, ink, slot plans, the private file view.<br>• `classroom`: devices, pairing, challenges, PIN, audit, the classroom-session middleware.<br>Panel login is useful beyond the board (recording later, perhaps attendance on the panel), and keeping it out of `accounts` keeps that app lightweight, as its doc asks.<br>The PIN lives in `classroom` (`PanelPin`) because it is valid *only* on panels.<br>Alternatives: everything in `board`, or the PIN on `User`. |
| **D2** | Device bound to `SchoolClass` or a room model | **`SchoolClass`, nullable, plus a required `branch`.**<br>• Pros: no new concept. The lock screen gets the timetable directly. Classes have no room today, and a room model would need a room on every class every year (the same yearly work as re-binding about N devices).<br>• Cons: at each new academic year the system admin re-binds each device to its new class. An admin action «انتقال به کلاس سال جدید» suggests the class with the same branch, grade and section in the current year.<br>• An unbound or inactive class shows «این پنل به کلاس فعالی متصل نیست»; QR login still works, with no slot.<br>• If you expect classes to change rooms often, or labs shared by classes, choose a `Room` model instead (rooms are stable; `SchoolClass.room` is optional). |
| **D3** | Who else may view a teacher's documents **(policy)** | **Nobody in phase 1.**<br>• The owner only. Others get 404, so a document's existence does not leak.<br>• Superusers get the metadata only (title, size, owner) in a read-only admin, not the content.<br>• Students get nothing.<br>• Supporter or director viewing can be added later through a `board.permissions.can_view` that already exists. |
| **D4** | Board ↔ `SchoolSession` | **No foreign key.**<br>• A slot plan stores `(class_subject, date, bell)`, the same identity a session has (ADR-016), so "the board of this session" is a join on those three fields.<br>• It survives session renumbering (ADR-018) and deletion, and needs no migration on `teaching`.<br>• **One document per slot** (unique), because a document can already hold PDF pages and blank pages. |
| **D5** | Session form reachable from a classroom session **(policy)** | **Yes, but only the form for the current slot.**<br>• That is the current slot's class subject, today and its bell, with GET and POST. After saving it returns to the board.<br>• The session list, edit, attendance archive and reports stay blocked.<br>• The form shows nothing about students. The teacher records the lesson while still in front of the panel.<br>• The alternative is to keep the panel board-only in phase 1. |
| **D6** | pdf.js build and version | **Depends on the panel's browser. Please send the panel model and its user agent or `chrome://version`, and say whether teachers will use the panel's built-in browser or an installed Chrome.**<br>• If the panel's Chromium supports module workers: pdf.js **4.10.38 legacy** build, the last 4.x.<br>• Otherwise: **3.11.174 legacy** (UMD) with `isEvalSupported: false`.<br>• Vendored under `static/vendor/pdfjs/` with LICENSE (Apache-2.0) and a README (version, source tarball, npm integrity).<br>• Before vendoring, I'll check the chosen build's real minimum Chromium against the panel. |
| **D7** | Plain canvas or a drawing library | **Plain JS, Pointer Events and canvas, no build step.**<br>• Excalidraw: React plus a build, a large bundle, its own data model, and no PDF pages.<br>• tldraw: React plus a build, and its SDK licence needs a key for production use.<br>• Fabric.js: MIT, about 300 KB, no build, but its object model fights normalised per-page vector ink and replay.<br>• What we need (freehand, highlighter, shapes, text, whole-stroke eraser, normalised coordinates) is a few hundred lines we fully control. |
| **D8** | Serving private files | **A new `PRIVATE_MEDIA_ROOT`** (`/app/private_media`, a new volume `private_media_data`) **outside `MEDIA_ROOT`.**<br>• The view checks permission, then answers with `X-Accel-Redirect: /_private/board/…`.<br>• nginx gets `location /_private/ { internal; alias /app/private_media/; }`, with the volume mounted read-only. nginx then handles `Range`, which pdf.js uses for large files, and `If-None-Match`.<br>• Without nginx (dev, tests, `SERVE_MEDIA`), it falls back to `FileResponse` via `PRIVATE_MEDIA_X_ACCEL = False`.<br>• Upload location: `client_max_body_size` raised to the PDF limit for `/board/upload/` only.<br>• This changes `docker-compose.yml` and both nginx configs (repo files only; applying them is a manual deploy step). |
| **D9** | Superusers and system admins on a panel | **Superusers: QR only (no PIN), in the same restricted classroom session, with their own library, flagged in the audit log.**<br>• The «مدیر سامانه» role without superuser, staff, director, supporter and student cannot log in on a panel. |
| **D10** | Username/password login on a paired device | **Accepted, but it becomes a classroom session** with the same restrictions, as a third path for a teacher without a phone or PIN.<br>• A normal (non-classroom) session that already exists on a paired browser, for example the admin who did the pairing, is logged out when the lock screen loads.<br>• The alternative is to refuse password login on panels. |
| **D11** | QR token never logged | **The token goes in the URL fragment**: `https://…/classroom/approve/#<token>`.<br>• Browsers never send fragments, so the token never appears in nginx, gunicorn or Django logs, or in a Referer.<br>• The approval page's small script POSTs it, and the server keeps it in the phone's session.<br>• If the teacher is not logged in, they are sent to login and come back via `next`. Django's `login()` keeps session data, so the token survives.<br>• **No-JS / failed-scan fallback:** the lock screen also shows a 6-digit «کد ورود», bound to the same challenge and expiring with it. The teacher can type it on «ورود به پنل کلاس» on their phone.<br>• The alternative is the token in `?t=` plus log formats that drop query strings (gunicorn `--access-logformat`, nginx `log_format` with `$uri`). |
| **D12** | Lock screen polling | **The lock screen sleeps after `CLASSROOM_LOCK_SLEEP_SECONDS` (120 s) without a touch:**<br>• the QR is hidden, polling stops and no challenges are created;<br>• it shows «برای ورود صفحه را لمس کنید»;<br>• one tap creates a fresh challenge.<br>The expected teacher, the clock and the bell stay visible while asleep. Set the setting to `0` for a QR that is always on. One extra tap removes almost all of the all-day load (risk 13). |
| **D13** | Who may log in on a panel **(policy)** | **Teacher role with a `TeacherProfile` and access to the device's branch,** through `core.services.access`, so in practice an active assignment there this year. Superusers too (D9).<br>• Refused: `must_change_password`, inactive users.<br>• Substitutes from the other branch are refused unless they have `BranchAccess` there. |
| **D14** | When a classroom session ends | **Computed on the server at login from the device's class and the bells:**<br>• during a bell, its end;<br>• between bells, the end of the next bell today;<br>• extended over consecutive bells of the **same class subject** (a double period);<br>• plus `CLASSROOM_SLOT_GRACE_MINUTES`;<br>• with no bell left today, or on Thursday, Friday or a holiday, login time + `CLASSROOM_SESSION_MAX_MINUTES`.<br>The Django session's own expiry is set to the same moment, so a powered-off panel's session dies on time even with no further requests. |
| **D15** | PIN rules **(policy)** | **Length:** 4–6 digits as asked. I recommend `CLASSROOM_PIN_MIN_LENGTH = 6`: a 4-digit PIN under 5 tries per 15 min can be guessed within days by someone with daily access to a panel.<br>**Weak PINs refused:** all-same, ascending or descending runs, and the teacher's birth year and national-code tail.<br>**Setting or changing it:** requires the account password, in profile › امنیت.<br>**Storage:** hashed with Django's password hashers (`make_password`).<br>**Lockout:** after `MAX_ATTEMPTS` failures per teacher, and per device, in `LOCKOUT_MINUTES`, with the message «به‌دلیل چند تلاش نادرست، ورود با رمز تا X دقیقه‌ی دیگر ممکن نیست».<br>**After 3 lockouts in 24 h** the PIN is disabled until the teacher sets a new one. They see «رمز پنل شما به‌دلیل تلاش‌های نادرست غیرفعال شد» on their profile, with the failed attempts (device, time). |
| **D16** | New Python dependencies | **`pypdf`** (BSD-3, pure Python) checks the page count, encryption and page sizes server-side. A page count from the browser can't be trusted.<br>**`segno`** (BSD-3, pure Python, no dependencies) draws the QR as inline SVG on the server, so the lock screen QR works without JS and no external API or JS library is involved.<br>Both go into `requirements.txt`. The alternative for the QR is vendoring `qrcode-generator` (MIT) in JS. |
| **D17** | Saves and conflicts | **One version counter per page. The client sends operations, not the whole page:** `{base_version, add: [strokes], remove: [ids], clear: bool}`.<br>• A stale `base_version` gets **409** with the page's current strokes and version. The client rebases its unsaved operations (re-adds its strokes, re-removes its ids) and retries.<br>• Two devices drawing on one page therefore never overwrite each other, and an erase on one device is never undone by the other.<br>• Page-list changes (insert or delete a blank page) use a separate `pages_version` on the document, also returning 409.<br>• Payloads stay small: one stroke, not a 300 KB page. |
| **D18** | Storage quota **(policy, server disk)** | **`BOARD_STORAGE_QUOTA_MB = 1024` per teacher** (active documents' PDFs). Please tell me the server's free disk. Textbook PDFs are often 10–50 MB.<br>• A deactivated document keeps its file (ADR-011) and does not count.<br>• A purge of documents deactivated over N days ago is a later management command, not phase 1. |
| **D19** | Setting defaults | See §4.8. |
| **D20** | Where the board lives in the teacher panel | **A sidebar item «تخته‌ی هوشمند» → the library** (teacher shell). The board editor is full-screen without the shell. In a classroom session there is a minimal kiosk shell (no sidebar, a large «خروج»). |
| **D21** | ADR-015 exception | **The board editor needs JS and a small JSON ink API.** Without JS the board page says «برای استفاده از تخته، جاوااسکریپت مرورگر را فعال کنید» and offers the PDF.<br>Library, upload, settings, pairing, lock screen (except polling), approval and PIN pages are server-rendered and work without JS, with `?partial=1` fragments where JS enhances them. |
| **D22** | HTTPS and cookies | **The device cookie is `HttpOnly`, `SameSite=Strict`, with `Secure` from `CLASSROOM_DEVICE_COOKIE_SECURE`.**<br>• That setting defaults to `SESSION_COOKIE_SECURE`; `production.py` forces it to `True`.<br>• It lasts 365 days, sliding, renewed when the lock screen loads.<br>• Please confirm production runs with `SECURE_SSL_REDIRECT=True`. The nginx config already forces HTTPS. |
| **D23** | Nothing left behind after logout | **On the server:** board pages in a classroom session are `Cache-Control: no-store` (which also keeps them out of the back/forward cache). PDF responses are always `private, no-cache` with an ETag: the browser must re-check with the server, so a cached copy is only reused by someone allowed to see it, and an unchanged textbook costs a 304, not 30 MB.<br>**On logout,** the response carries `Clear-Site-Data: "cache", "storage"`. Cookies are not cleared, so the device cookie survives.<br>**On the client:** before logging out it flushes unsaved strokes (up to 5 s). Strokes that still fail to save are discarded, and a manual logout first warns «n تغییر ذخیره نشد؛ خروج؟». The IndexedDB queue is keyed by user and wiped on logout and at the lock screen. |
| **D24** | Blank page size | **A standalone board's pages are 16:9 landscape,** the panel's shape. A blank page inserted into a PDF takes the aspect of the page before it. Each page stores its aspect, so normalised coordinates stay undistorted. |

**Questions for you, besides the D-items:**
1. The panel model and browser (D6).
2. How many panels, in which branches.
3. The production `SECURE_SSL_REDIRECT` (D22).
4. The server's free disk (D18).

---

## 4. Design

### 4.1 Apps, URLs and layers

**`board`** (namespace `board`, `/board/`):

- `/board/` is the library. It is filtered by class subject and kind, and shows the slot plans of the coming days.
- `/board/upload/` (POST) and `/board/new/` (a whiteboard).
- `/board/<id>/` is the editor; `/board/<id>/settings/` covers title, class subject, slot plan and deactivation.
- `/board/<id>/file/` serves the PDF through the permission check.
- The ink API, all JSON:
  - `/board/api/<id>/pages/` (GET the list)
  - `/board/api/pages/<page_id>/` (GET the ink)
  - `/board/api/pages/<page_id>/ops/` (POST operations)
  - `/board/api/<id>/pages/insert/` and `…/delete/` (blank pages)

Layers follow the project:

- `models/` (a package)
- `services.py`: upload validation, page building, applying operations under `select_for_update`, slot plans
- `selectors.py`: library, page list, upcoming slots through `get_slots` and `Closures`
- `permissions.py`: `board_user_required` (teacher with a profile, or superuser; others go to their own dashboard and APIs get 403) and `owned_document_or_404`
- `validators.py`: the stroke schema
- `conf.py`: reads settings, the one place

**`classroom`** (namespace `classroom`, `/classroom/`):

- On the panel:
  - `/classroom/` is the lock screen (`?partial=1` for the status fragment).
  - `/classroom/pair/` (public, rate-limited).
  - `/classroom/challenge/` (POST, new QR), `/classroom/challenge/<id>/status/` (GET, polled), `/classroom/challenge/<id>/claim/` (POST, which logs the user in on the panel).
  - `/classroom/pin/` (pick or search a teacher, then PIN) and `/classroom/session/` (GET: remaining and idle seconds).
  - `/classroom/session/keepalive/` («ادامه») and `/classroom/logout/`.
- On the phone: `/classroom/approve/` (GET/POST: confirm, or type the 6-digit code).
- The PIN card goes in the profile's «امنیت» tab, with its POST handled by `classroom.services`.

Layers: `models/`, `services.py` (pairing, challenges, approve and claim, PIN, session window, audit), `selectors.py` (the expected-teacher state, the teacher search), `permissions.py`, `middleware.py`, `conf.py`, `admin.py`.

### 4.2 Board data model (`board/models/`)

**`BoardDocument`**

| Field | Notes |
| --- | --- |
| `owner` | FK `User`, `PROTECT` |
| `title` | |
| `kind` | `pdf` or `whiteboard` |
| `source_file` | `FileField` on a private `FileSystemStorage(PRIVATE_MEDIA_ROOT)`, `upload_to` `board/<owner_id>/<uuid>.pdf`; null for whiteboards |
| `file_size`, `file_sha256` | the hash is the ETag |
| `pdf_page_count` | |
| `class_subject` | FK, null, `SET_NULL` (risk 6) |
| `pages_version` | |
| `created_at`, `updated_at`, `last_opened_at` | |
| `is_active` | |

- Index on `(owner, is_active, -updated_at)`.

**`BoardPage`**

| Field | Notes |
| --- | --- |
| `document` | FK, `CASCADE` |
| `position` | renumbered 1..N under a document row lock, like ADR-018 |
| `kind` | `pdf` or `blank` |
| `pdf_page` | 1-based, null for blank |
| `background` | `none` / `plain` / `grid` / `lined` |
| `aspect` | width ÷ height, from pypdf, with `/Rotate` applied |
| `strokes` | `JSONField`, the current state |
| `stroke_count` | |
| `version` | |
| `updated_at` | |

- Unique `(document, position)`. Check constraint: `pdf_page` is set if and only if `kind = pdf`.
- Annotations are keyed by the page's **id**, never by its position, so inserting a blank page shifts nothing.
- List reads `defer("strokes")`.

**`BoardSlotPlan`**

| Field | Notes |
| --- | --- |
| `document` | FK, `CASCADE` |
| `class_subject` | FK, `CASCADE` (the slot is gone if the class subject is) |
| `date` | `jDateField` |
| `bell` | FK `Bell`, `PROTECT` (bells are soft-deactivated) |
| `created_at` | |

- Unique `(class_subject, date, bell)`.
- Validation:
  - the owner must be the class subject's teacher (`teacher_assignment.teacher.staff.user`);
  - the slot must exist in `get_slots`;
  - a closed slot is allowed but flagged.
- The settings form offers the next 14 days' slots of the chosen class subject (`get_slots` and `Closures`, holidays marked), never a free date.

### 4.3 Stroke format v1 (in the ADR)

```json
{"v":1,"id":"<client UUID>","tool":"pen|highlighter|line|arrow|rect|ellipse|text",
 "color":"#1f2937","w":0.0025,"t":1761300000000,
 "pts":[0.1234,0.5678, …],"p":[0.52, …],"dt":[0,16, …],
 "text":"…","size":0.03}
```

- `pts`: flat `x,y` pairs normalised to the page (0…1, x relative to width and y to height), 4 decimals. Shapes have 2 points; text has 1.
- `w` and `size`: normalised to the page width.
- `p` (pressure, 0…1) and `dt` (ms offsets from `t`, one per point): optional, but the same length as the points when present.
- `t`: creation time in epoch milliseconds.

**Server validation** (`board/validators.py`):

- Known tool, and a colour from the palette (8 colours).
- Widths only from the 3 presets per tool.
- Lengths: `MAX_POINTS_PER_STROKE`, `MAX_TEXT_LENGTH`. Coordinates are finite, within −0.05…1.05, rounded.
- Unknown keys are refused.
- Request size: at most `MAX_OPS_BYTES` per request, `MAX_STROKES_PER_PAGE` and `MAX_PAGE_INK_BYTES` per page.
- Malformed JSON gets 400 with a Persian message.

**Recording later:** a recording will add an append-only `BoardEvent` log (stroke added or erased, page cleared, page shown, with timestamps) next to an audio file, keyed to stroke ids and page ids. Strokes already carry ids, timestamps and per-point offsets, so recording needs **no migration of stroke data**. Erase history before recording exists is not kept (state only), which the ADR states.

### 4.4 Classroom data model (`classroom/models/`)

**`ClassroomDevice`**

| Field | Notes |
| --- | --- |
| `name` | e.g. «پنل ۱۱-ب» |
| `branch` | FK, `PROTECT` |
| `school_class` | FK, null, `SET_NULL`; validated to the same branch |
| `secret_hash` | SHA-256 of a 256-bit random secret; unique, null until paired |
| `pairing_code_hash`, `pairing_expires_at` | |
| `paired_at`, `last_seen_at` | `last_seen_at` is written at most once a minute |
| `is_active` | |
| `registered_by` | FK `User`, `SET_NULL` |
| `created_at`, `updated_at` | |

- A salted slow hash is not needed for a 256-bit random secret, and SHA-256 allows an indexed lookup.
- The pairing code is 8 characters from an unambiguous alphabet, single use, valid `PAIRING_MINUTES`.

**`LoginChallenge`**

| Field | Notes |
| --- | --- |
| `device` | FK, `CASCADE` |
| `token_hash` | unique |
| `short_code` | 6 digits, unique among unexpired challenges |
| `created_at`, `expires_at` | |
| `approved_by`, `approved_at`, `approved_ip` | |
| `claimed_at` | |

- Expired, unclaimed rows of a device are pruned when it creates a new challenge.

**`PanelPin`**

| Field | Notes |
| --- | --- |
| `user` | one-to-one |
| `pin_hash` | |
| `created_at`, `updated_at` | |
| `disabled_at` | set after the third lockout in 24 hours (D15) |

**`DeviceLog`** (the audit; append-only, read-only admin):

| Field | Notes |
| --- | --- |
| `device` | null for a failed pairing |
| `user` | null when unknown |
| `event` | `paired`, `pair_failed`, `challenge_created`, `qr_approved`, `qr_refused`, `pin_ok`, `pin_failed`, `pin_locked`, `password_login`, `logout_manual`, `logout_idle`, `logout_slot_end`, `logout_revoked` |
| `created_at`, `ip` | |
| `detail` | `JSONField`: slot, substitute or not, reason |

- Rate limits and lockouts count rows here.
- **Never stores a token, PIN or code.**

### 4.5 Flows

- **Pairing:**
  1. The admin adds a device, or uses «صدور کد اتصال جدید». The code is shown once in the admin message.
  2. On the panel: `/classroom/pair/`, enter the code.
  3. The device gets a new secret; any previous secret dies; any session on that browser is logged out.
  4. The device cookie is set.
  5. Deactivation in the admin revokes immediately: the middleware checks the device on every request.
- **Lock screen:**
  - Shows the class, the Jalali date, a server-synced clock, and the current or next bell from `Bell` times.
  - Shows the expected teacher (name and avatar) from `get_slots(today, today, class_subject__school_class=device.school_class)`, with closures from `Closures.between(...).event_for(...)`.
  - States:
    - in a bell with a slot;
    - in a bell, closed by an event (with its title);
    - in a bell with no lesson;
    - between bells (the next lesson);
    - after school;
    - Thursday, Friday or a holiday (with the reason);
    - device not bound.
  - It re-renders its status fragment at the next bell boundary (the server sends the seconds left).
  - No weekday or time is hard-coded.
- **QR:** challenge (device-bound, single use, `CHALLENGE_SECONDS`) → QR (`segno` SVG) of `…/classroom/approve/#token`, plus the 6-digit code → phone confirmation «ورود به پنل کلاس ۱۱-ب؟» (device name, class, branch) → approve under `select_for_update`: not expired, not approved, approver allowed by D13, rate limited → the panel polls `status` every `POLL_SECONDS` → `claim` (POST, `select_for_update`, approved and not claimed, device equals the cookie's device) → `login()` on the panel request → classroom session.
- **PIN:**
  1. Tap the expected teacher, or «معلم دیگری هستم», which searches by name among teachers of the device's branch (D13).
  2. Enter the PIN on a large on-screen keypad.
  3. Accepted only with a valid device cookie, never on `/auth/login/`.
  4. Lockouts follow D15. A teacher without a PIN sees «رمز پنل تنظیم نشده است؛ با QR وارد شوید».
- **Classroom session** (stored in the Django session):
  - `classroom = {device_id, started_at, ends_at, last_activity, slot: {class_subject_id, date, bell_ids}, substitute}`, with `set_expiry(ends_at)`.
  - `classroom.middleware.ClassroomMiddleware` runs right after `AuthenticationMiddleware`. On every request of a classroom session it:
    - checks the device cookie (same device, active), `ends_at` and the idle limit, and on failure logs out with an audit event and sends the browser to the lock screen;
    - allows only an allow-list of URL names: board pages, board APIs, the board file view, `classroom:*` session endpoints, the D5 session form, static files and media;
    - otherwise HTML GETs redirect to the board library with «این بخش در پنل کلاس در دسترس نیست»; everything else gets 403 (JSON for API calls).
  - Board saves and «ادامه» count as activity; polling `/classroom/session/` does not.
  - Client: a countdown near «خروج», an idle warning «تا ۶۰ ثانیه‌ی دیگر خارج می‌شوید» with «ادامه», and a flush before the bell-end logout.
- **After login:**
  - if the teacher planned a document for the current slot (`BoardSlotPlan` matching the session's slot), open it;
  - otherwise open the library filtered to the class subjects this teacher teaches in the device's class, falling back to everything.

### 4.6 Private files and validation

**Upload checks**, in this order:

1. `.pdf` extension.
2. Declared MIME `application/pdf`.
3. Size ≤ `BOARD_PDF_MAX_BYTES`, checked before reading.
4. `%PDF-` magic in the first 1024 bytes.
5. pypdf opens it: not encrypted, page count ≤ `BOARD_PDF_MAX_PAGES`, and each page's size and rotation read for its aspect.
6. Quota (D18).

Each check has its own Persian message.

**Storage:** the file is stored under a random name; the original name is kept only as the default title.

**Serving:** D8 and D23, with `Content-Disposition: inline; filename="document.pdf"`.

### 4.7 Front end

- **Shells:**
  - the library in the teacher shell, matching the existing pages (`ui-` components, tokens);
  - the editor and the classroom screens in a new minimal `classroom/base.html` and `board/editor.html` built on the same `tokens.css` and `components.css`, with no new visual direction.
- **Editor structure:** `static/board/js/` as plain scripts (no build). The ES syntax level follows D6.
  - `pdf-layer`: pdf.js renders lazily, keeps an LRU cache of about 6 rendered pages, and caps `devicePixelRatio` at `min(dpr, 2)` and the canvas at about 4096 px.
  - `ink-layer`: a second canvas per page, redrawn from normalised strokes, with the live stroke on its own overlay.
  - `tools`: pen, highlighter, whole-stroke eraser (hit test on segments), line, arrow, rectangle, ellipse, text box, 8 colours, 3 widths, undo/redo per page from the operation log, clear page.
  - `gestures`: one pointer draws; two pointers pan and pinch-zoom; once `pointerType === "pen"` has been seen, touch no longer draws (palm rejection) but still pans and zooms; `touch-action: none` on the canvas.
  - `pages`: a thumbnail strip (lazy), go-to-page, insert a blank page (plain, grid, lined), delete a blank page.
  - `sync`:
    - debounced autosave (`BOARD_AUTOSAVE_DELAY_MS`) with the status «در حال ذخیره… / ذخیره شد / ذخیره نشد – تلاش دوباره»;
    - pending operations kept in memory and mirrored to IndexedDB, keyed by user, document and page;
    - retry with backoff, rebase on 409, flush on `pagehide` and before logout.
- **Layout:** big toolbar buttons (at least 56 px on the panel), RTL around the canvas. At 375 px the toolbar collapses into a scrollable row with a «ابزارها» sheet. On small screens the scroller stays `.app-shell` / `.ui-shell__main`, as in the project.
- **Security headers:** a strict CSP on board and classroom pages (`script-src 'self'`, `worker-src 'self' blob:`, `object-src 'none'`), with no inline scripts on those pages.
- **QR:** server-side SVG, no image request.

### 4.8 Settings (in `base.py`, read only through each app's `conf.py`)

| Setting | Default | Why |
| --- | --- | --- |
| `BOARD_PDF_MAX_BYTES` | 40 MB | Textbook PDFs run 10–50 MB; nginx's upload limit is matched to it |
| `BOARD_PDF_MAX_PAGES` | 300 | A full textbook |
| `BOARD_MAX_BLANK_PAGES` | 100 per document | |
| `BOARD_STORAGE_QUOTA_MB` | 1024 per teacher | D18 |
| `BOARD_MAX_STROKES_PER_PAGE` | 5000 | |
| `BOARD_MAX_POINTS_PER_STROKE` | 4000 | |
| `BOARD_MAX_OPS_BYTES` | 256 KB per save | |
| `BOARD_MAX_PAGE_INK_BYTES` | 4 MB | |
| `BOARD_AUTOSAVE_DELAY_MS` | 1500 | |
| `CLASSROOM_PAIRING_MINUTES` | 10 | |
| `CLASSROOM_DEVICE_COOKIE_DAYS` | 365, sliding | |
| `CLASSROOM_DEVICE_COOKIE_SECURE` | `SESSION_COOKIE_SECURE`; `True` in production | D22 |
| `CLASSROOM_CHALLENGE_SECONDS` | 90 | |
| `CLASSROOM_POLL_SECONDS` | 2 | |
| `CLASSROOM_LOCK_SLEEP_SECONDS` | 120 (0 = never) | D12 |
| `CLASSROOM_CHALLENGES_PER_MINUTE` | 6 per device | |
| `CLASSROOM_APPROVALS_PER_MINUTE` | 5 per user | |
| `CLASSROOM_PAIRING_ATTEMPTS` | 10 per IP per 10 min | |
| `CLASSROOM_PIN_MIN_LENGTH` / `_MAX_LENGTH` | 6 / 6 (or 4 / 6) | D15 |
| `CLASSROOM_PIN_MAX_ATTEMPTS` | 5 | Per teacher; 10 per device |
| `CLASSROOM_PIN_LOCKOUT_MINUTES` | 15 | |
| `CLASSROOM_IDLE_MINUTES` | 15 | Warning 60 s before |
| `CLASSROOM_SLOT_GRACE_MINUTES` | 5 | Bells here have 15-minute breaks |
| `CLASSROOM_SESSION_MAX_MINUTES` | 60 | Login with no bell left |
| `PRIVATE_MEDIA_ROOT` | `BASE_DIR / 'private_media'` | |
| `PRIVATE_MEDIA_X_ACCEL` | `False`; production `True` | D8 |

---

## 5. Implementation outline

1. **Settings and wiring:**
   - `INSTALLED_APPS` gets `board` and `classroom`; the middleware is added after `AuthenticationMiddleware`; URLs.
   - The settings in §4.8; `production.py` overrides.
   - `requirements.txt` gets `pypdf` and `segno`.
   - `.gitignore` and `.dockerignore` get `private_media/`.
2. **`classroom` models, migrations and admin:**
   - The device admin is `BranchScopedAdminMixin` with `related_branch_lookups` (`branch`, `school_class__branch`). Change and delete follow the calendar admin pattern (only devices of your branches; no delete, deactivate instead).
   - Actions: «صدور کد اتصال جدید», «غیرفعال‌کردن», «انتقال به کلاس سال جدید».
   - `DeviceLog` is a read-only, branch-scoped admin.
3. **`classroom` services and selectors:**
   - pairing, cookie, challenges, approve and claim, PIN (set, verify, lockout), the session window (D14), the expected-teacher state, audit, DB-based rate limits.
4. **`classroom` middleware and views:**
   - lock screen, pair, challenge, status, claim, approve (phone), PIN, session status, keepalive, logout;
   - the PIN card in profile › امنیت (`accounts/views.py` delegates to `classroom.services`);
   - D10 in `accounts.views.login_form`: a paired browser makes a classroom session.
5. **`board` models, migrations and services:**
   - upload validation, page building, operations under `select_for_update` with versions, blank page insert and delete, slot plans, the private file view with X-Accel.
6. **`board` front end:**
   - vendor pdf.js (D6) with a README;
   - library, settings, editor;
   - `static/board/css`, `js`.
7. **Integration:**
   - the teacher sidebar item;
   - classroom login opens the planned document or the filtered library;
   - the D5 session form allowed and returning to the board.
8. **Deployment files** (repo only):
   - `docker-compose.yml` gets the volume `private_media_data`, rw in `web` and ro in `nginx`;
   - both nginx configs get `location /_private/ { internal; … }` and the upload location's `client_max_body_size`.
9. **Tests** (§6), **browser checks**, **docs** (§7), then the work report.

---

## 6. Tests

**Permissions:**
- Every new URL × {owner teacher, other teacher, supporter, director, student, logged out, staff without permission, staff with permission in another branch, superuser}.
- Others' documents are 404; non-teacher panels redirect to their own dashboard; APIs are 403.

**Device:**
- Pairing-code expiry and single use; re-pairing kills the old secret.
- A revoked device and a cookie from a deactivated device: the lock screen refuses, and a live classroom session ends on its next request.
- A forged cookie; the cookie flags (`HttpOnly`, `SameSite=Strict`, `Secure` per setting).
- Branch-scoped admin: list, change, other branch refused.

**Challenge:**
- Expiry (mocked `timezone.now`); reuse; claim from another device.
- Approval by a non-teacher, a teacher without branch access, or a user with `must_change_password`.
- Rate limits on creation, approval and pairing.
- The token is absent from the audit and from logs: assert on captured log output.
- The phone session survives the panel login.

**PIN:**
- Hashed (never plain); weak PINs refused; the password is needed to set it.
- Lockout and unlock at M minutes ± 1 s, per teacher and per device; disabled after 3 lockouts.
- Refused without a paired device and on `/auth/login/`.

**Classroom session:**
- An allow-listed URL passes; every other URL (reports, other panels, admin, profile, PIN settings, attendance, session list) is 403 or redirected.
- Auto-logout at bell end + grace −1 s / +1 s, and at idle −1 s / +1 s.
- `set_expiry` matches; `Clear-Site-Data` on logout; `no-store` on board pages.

**Expected teacher** (lock screen state):
- Rotation weeks 1 and 2; two bells of one subject (a double period extends the session).
- A slot closed by an event (whole day and bell-scoped); Thursday and Friday.
- Between bells, after school, a substitute (QR or PIN) flagged in the audit, a device without a class.
- Reuses `analytics.tests.Fixture` where it fits.

**Board:**
- PDF validation: wrong extension, MIME, magic, encrypted, too large, too many pages, quota.
- Private file access and the X-Accel header versus `FileResponse`.
- Operations: add, remove and clear; a stale version gets 409 with the state; the rebase scenario; malformed JSON, unknown tools, out-of-range coordinates, oversize payloads and too many strokes are refused.
- Blank page insert and delete with `pages_version`.
- Slot plan validation (not the owner's class subject, not a timetable slot, uniqueness).
- Timetable editor deletion of a class subject → `SET_NULL` / `CASCADE` behave.

**Locked query counts:** lock screen, board editor page, library, page list API.

**Migrations:** `makemigrations --check`; `migrate board zero` and `migrate classroom zero` on a scratch SQLite copy.

**Full suite:** a baseline on `main`, then the branch (Postgres, no `--parallel`). Expected error: only the known colour test.

**Browser** (headless Chrome via `puppeteer-core` from my scratchpad, using `/usr/bin/google-chrome`, nothing added to the repo):
- library, editor and lock screen at 1280 px and 375 px (no horizontal overflow of `.app-shell`);
- 1920×1080 with touch emulation for the panel: draw, pinch, palm rejection with a synthetic pen pointer, autosave states with the network offline then online.

---

## 7. Documentation

- **New:** `docs/apps/board.md` and `docs/apps/classroom.md`, the latter with the Persian admin guide: pairing a panel, revoking it, moving it to a new year's class, and how a teacher sets a PIN.
- **Updated:**
  - `docs/apps/accounts.md` (panel logins, the PIN card, D10)
  - `core.md` (sidebar)
  - `teaching.md` (D5)
  - `school.md` and `staff.md` (only where §9 discrepancies touch what I change)
  - `database.md`, `database-mermaid.md`, `changelog.md`
- **New ADRs:**
  - **ADR-024** for the board data model: vector ink per page, normalised strokes v1, operation saves with versions, owner-only private files, readiness for recording.
  - **ADR-025** for classroom devices and panel login: paired devices, QR challenge, PIN, the restricted classroom session, auto-logout, and the ADR-015 exception.
- **Report:** `docs/plans/2026-10-teacher-board.md`.

---

## 8. Migrations, verification, and what I will not touch

**Migrations:** only new tables in the two new apps. No migration on an existing app, and no existing row is changed. They are verified with `makemigrations --check`, the test database (Postgres), and a scratch SQLite copy forward and back to zero. Rollback is `migrate board zero` and `migrate classroom zero`, then deleting the volume.

**I will not touch:**
- the production database or server;
- the local Docker database (no `migrate` there without asking);
- `analytics`, `attendance`, `supervisor`, `director`, `student`, `teaching` (except the D5 allow-list and redirect), scheduling and calendar logic (only called).

**I will not:** commit, push or deploy until you ask.

---

## 9. Discrepancies between docs and code (code wins)

1. `docs/project-overview.md` is empty (0 bytes).
2. `school.md` and `accounts.md` say `ClassSubject.teacher` is a FK to `User` with `limit_choices_to role=teacher`. In the code the field is `teacher_assignment`, a FK to `TeacherAssignment` (→ `TeacherProfile` → `Staff` → `User`).
3. `scheduling.md`'s field table lists `class_room`, `start_time`, `end_time`. The code has `class_subject` and `bell` (times live on the global `Bell`).
4. `core.md` gives the URL `/core/dashboard/`. The real URL is `/dashboard/dashboard/`. The doc also says nothing about the app's services, middleware, querysets and admin mixins.
5. `accounts.md` lists only login and logout. It misses `password/change/` and `profile/`, `LoginActivity`, `ForcePasswordChangeMiddleware` and `sessions.py`, and lists "login activity tracking" as a future feature although it exists.
6. `staff.md` documents `TeacherProfile.is_homeroom_teacher`, which the code does not have, and omits `TeacherAssignment` and `BranchAccess`.
7. ADR-015 says there is no JSON API, but the student timeline already uses one (`/student/api/sessions/<slug>`).
8. The request mentions per-branch bells: `Bell` is global (same times in both branches).
