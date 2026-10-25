# Plan: the school blog («وبلاگ»)

Status: **waiting for approval.** Nothing is implemented. Implementation will go on
`feature/blog`, created from `main` after approval. Apart from this file, nothing will be
committed, pushed, merged or migrated unless you ask.

Skills: both were loaded with the Skill tool before planning.
- **`teachlog-workflow`**: this plan follows its read → plan → approve order. Only this
  file goes to `main`.
- **`frontend-design`**: it shaped §4.
  - I named the subject, the audience and the page's job.
  - I wrote a compact token system (colour, type, layout, principles).
  - I checked that system against the skill's list of generic defaults and revised every
    part that matched (§4.5).
  - The boldness is spent in one place, the masthead. Everything else stays disciplined so
    long texts read comfortably.
  - The authoring screens are **not** part of that freedom: they copy each panel's current
    design (`.claude/CLAUDE.md`).

Read before planning:
- `CLAUDE.md`, `.claude/CLAUDE.md`, ADR-001…025;
- docs: `docs/apps/` website, accounts, core, staff, supervisor; `docs/database.md`,
  `docs/database-mermaid.md`, `docs/changelog.md`;
- the About, Contact and Teachers plans and reports;
- all of `website/`: models, admin, views, selectors, services, signals, validators,
  `images.py`, migrations 0001–0013, templates, CSS, JS, tests;
- `accounts/models/user.py`, `accounts/utils.py` (`role_dashboard`), `accounts/views.py`;
- access and decorators: `core/services/access.py`, `core/context_processors/teacher_info.py`
  (`panel_base`), `staff/decorators.py`, `supervisor/permissions.py`;
- templates: `template/base.html`, `template/teacher/` (shell, sidebar, user menu),
  `template/partials/` (sidebar, topbar), the supervisor templates;
- static: `static/teacher/css/` tokens and components, `static/css/base.css`;
- config: `teachlog/urls.py`, settings, nginx config, `requirements.txt`.

---

## 1. Findings, risks and surprises

### 1.1 Roles and panels

1. **Counselors have no panel.**
   - `User.Roles.COUNSELOR` («مشاور») exists, but `accounts.utils.role_dashboard` has no
     entry for it.
   - After login a counselor lands in the Django admin if `is_staff`, otherwise on the
     public home page. The same holds for accountant, IT, services and «مدیر سامانه».
   - So "an authoring page inside their existing panel" doesn't exist for the people who
     will write «مشاوره». This drives D6.
2. **There are two panel designs, not one.**
   - The teacher panel has its own shell: `template/teacher/base.html` with the `ui-*`
     components and `static/teacher/css/tokens.css`.
   - The supervisor, director and student panels use `template/base.html`,
     `partials/sidebar.html` and their own classes (`dashboard-header`, `sv-filters`,
     `btn`).
   - Pages shared by several roles pick the shell through `panel_base`. Matching "that
     panel's design exactly" therefore means two sets of page templates for the authoring
     screens (§7.5).
3. **Panel decorators differ.**
   - `teacher_required` sends other roles to their own dashboard.
   - `require_supervisor` answers 403, and also needs `request.branch` to be the
     supervisor's branch.
   - The blog is not branch-scoped, so it gets its own decorator. The supervisor sidebar
     and topbar read `request.supervisor.grade`, so the authoring views set
     `request.supervisor` for supervisors themselves.
4. **Director (ADR-020).** The director panel is GET-only. If the director may write
   (D3), they write in the blog's authoring area, not in their panel, and the panel stays
   read-only. That is worth stating in ADR-026.
5. **Roles and `is_staff` are independent (ADR-020).**
   - Making authors staff, which Django-admin authoring needs, would give teachers and
     counselors admin access.
   - The admin was built for the system admin, not for them.

### 1.2 Query counts

6. **A sidebar link costs a query on every panel page.**
   - About 37 tests lock query counts, many on teacher and supervisor pages. A
     «نوشته‌های من» sidebar link that asks "is this user an author?" adds one query to all
     of them.
   - D9 proposes loading the author row together with the user, which costs zero queries.
7. **Public lists stay flat.**
   - A list needs posts with section, category and author (one query, `select_related`),
     tags (one prefetch) and the page count (one query).
   - The post page also needs related posts (one query) and previous/next (two queries).
     Nothing grows with the number of posts or tags.

### 1.3 Security and content

8. **Author HTML is the new attack surface.**
   - Until now every public string was auto-escaped. A rich-text body has to be rendered
     unescaped.
   - So it must be sanitized with an allow-list. Doing it in `Post.save()` covers every
     path: the authoring page, the admin, the shell and tests. It is sanitized again when
     rendered.
   - `bleach` is deprecated (2023). **`nh3`** (the Python binding of the Rust `ammonia`
     sanitizer, MIT) is the maintained choice; see D11.
9. **Images inside posts are user uploads served by nginx** from `/media/`.
   - The existing validators allow only jpg, png and webp, up to 2 MB.
   - Re-encoding (`website/images.py`) removes EXIF data, including GPS, and anything
     hidden in the file. That matters most here: photos of school events show children.
   - Files of drafts get random names but are still public if someone has the URL. That is
     acceptable because the names can't be guessed, and is noted in ADR-026.
10. **Children's privacy.**
    - «مشاوره» posts are about children and families. A well-meant "a student of ours…"
      story can identify a child.
    - The authoring form needs a clear reminder, submitting needs an acknowledgement, and
      publishing needs a reviewer checklist (D16).
    - ADR-025 already forbids reading school data on public pages. The blog follows it:
      the only data it reads from the school's records is a user's first and last name, as
      a fallback for an author's display name, and a teacher card the admin linked on
      purpose.
11. **ADR-025 and author photos.** You suggested falling back to the user or teacher
    profile. ADR-025 says a person's photo is published only when it was uploaded for that
    purpose, never the account avatar. A linked **teacher card's** photo was uploaded for
    the public site, so that fallback is fine. The **account avatar** is not (D5).

### 1.4 What the project doesn't have yet

12. **No sitemap, no robots.txt, no feeds**, and `django.contrib.sitemaps` isn't
    installed. Without `django.contrib.sites`, absolute URLs come from the request
    (`RequestSite`, used by both the sitemap and the syndication frameworks). Behind nginx
    with `SECURE_PROXY_SSL_HEADER` that gives the right scheme and host. No new setting is
    needed.
13. **No scheduler** (no Celery, no cron in `docker-compose.yml`).
    - Scheduled publishing therefore can't be a job that flips a status.
    - Instead, "public" means *published **and** `published_at` ≤ now*, checked in one
      queryset method. A scheduled post appears on time, with nothing to run or forget
      (D8).
14. **Search must work on PostgreSQL and SQLite**, since the suite runs on both, so there's
    no `SearchVector`.
    - Persian text also needs normalising: Arabic ي and ك against Persian ی and ک,
      Arabic-Indic digits, and ZWNJ.
    - On save, the post keeps a normalised plain-text copy, and the search query is
      normalised the same way (D13).
15. **The navbar** marks an item active only when `item.url == request.path`, so «وبلاگ»
    wouldn't be highlighted on `/blog/post/…/`. This needs a small change for prefixes
    (§7.4).
16. **Menu rows.**
    - The seed (`0002`) has nav rows «وبلاگ» and «مقاله», both still `#` unless edited.
    - Neither is in the footer.
    - Reversible migration in the same shape as `0005`, `0008` and `0012` (D20).
17. **Django 6.0** has built-in Content-Security-Policy support. A strict policy on the
    public blog pages is cheap extra protection around user-written HTML (D12).
18. **Docs and code disagree** (to fix on the branch):
    - `docs/apps/accounts.md` shows `User → ClassSubject` and doesn't list
      `national_code`, `must_change_password` or `director`;
    - `docs/database-mermaid.md` says the website tables are left out. The blog tables do
      link into the domain (`BlogAuthor.user`), so I'll add them to the diagram.

---

## 2. Decisions to confirm

**School policy** items are marked **[policy]**: those are yours to decide. The others are
technical, each with my recommendation.

### Structure

**D1. A new `blog` app.** Recommended: yes.
- The `website` app is already 13 migrations and 12 models of page singletons.
- The blog has its own users (authors), a workflow, permissions, an editor, feeds and an
  authoring area.
- It reuses `website`'s validators, `images.reencode`, the file-cleanup signal handlers and
  the public navbar and footer.
- It follows the layout conventions: a models package, `selectors.py`, `services.py`,
  `permissions.py` and thin views.

**D2. URLs.** Recommended (ASCII prefixes, Persian slugs):

| URL | Page |
|---|---|
| `/blog/` | blog home |
| `/blog/post/<slug>/` | post |
| `/blog/section/<section>/` | section |
| `/blog/section/<section>/<category>/` | category |
| `/blog/tag/<tag>/` | tag |
| `/blog/author/<slug>/` | author |
| `/blog/search/?q=` | search |
| `/blog/feed/`, `/blog/section/<section>/feed/` | Atom feeds |
| `/blog/write/…` | authoring area («نوشته‌های من») |
| `/sitemap.xml`, `/robots.txt` | site-wide (D19) |

- A post's URL doesn't depend on its section or category, so moving a post never breaks a
  link.
- There are no reserved words to police.
- The slug is generated from the title (`allow_unicode`, as on the teachers page).
  - It is editable while the post is a draft.
  - It is **frozen once published**; only the admin can change it then, with a warning in
    the help text.

### Authors

**D3. [policy] Which roles may be authors?** The admin grants author access to a person;
the role is only a safety net that a grant can't override. Recommended:

| Role | Eligible |
|---|---|
| teacher («معلم») | yes |
| counselor («مشاور») | yes |
| supervisor («پشتیبان») | yes |
| director («مدیر مدرسه») | yes (writes in the authoring area; the director panel stays read-only) |
| system admin («مدیر سامانه») | yes |
| accountant, IT, services | no (can be added later in settings) |
| student | **never** |

The list lives in `settings.BLOG_AUTHOR_ROLES` and is read only in `blog.permissions`.

If a user's role later moves to a role that isn't eligible, they lose author access at
once. Their posts are not changed.

**D4. The author model.** Recommended: **`BlogAuthor`**, one row per person, created by the
admin («نویسندگان وبلاگ»).
- `user`: one-to-one link, limited to eligible roles.
- Sections the author may write in, through `AuthorSection`, which also records who
  granted access and when (§5).
- Public profile:
  - `display_name`: blank → the user's first and last name, **never the username**;
  - `slug`, generated and then frozen;
  - `bio` (600 characters);
  - `photo`, re-encoded on upload;
  - `teacher_card`: optional link to `website.LandingTeacher`.
- `is_active`: the admin's master switch for writing.

How it fits `User.Roles`: no new role. Being an author is a grant that sits on top of a
role, as `BranchAccess` sits on top of teaching.

A person **can write** when **all** of these hold:
- their `BlogAuthor` is active;
- their `User` is active;
- their role is eligible;
- if they have a `Staff` row, it is active (someone who has left can't write);
- the section is granted to them and is active.

This check is one function, `blog.permissions.writable_sections(user)`, and every
authoring view and test goes through it.

**D5. Fallbacks for the public byline.** Recommended:
- **name:** `display_name`, else the user's first and last name;
- **photo:** `BlogAuthor.photo`, else the linked teacher card's `photo_override`, else the
  name's first letter. **Never the account avatar** (ADR-025).
- **bio:** `BlogAuthor.bio`, else the teacher card's `bio`;
- **the «صفحه معلم» link** (`/teachers/#<slug>`) is shown only while that card is public:
  active, `on_teachers_page`, and staff active or none. That's the same rule
  `website.selectors.public_teachers()` already uses.

**D6. Where authors write.** Recommended: **an authoring area in the blog app,
`/blog/write/` («نوشته‌های من»), rendered in the author's own panel shell.** The Django
admin is used only by editors.

| | Authoring area in the panel (recommended) | Django admin with scoped permissions |
|---|---|---|
| Who can use it | everyone eligible, including counselors with no panel | only `is_staff` users, so teachers and counselors would have to become staff (finding 5) |
| Least privilege | sees only `/blog/write/`, scoped in `permissions.py` | admin access; scoping depends on every `ModelAdmin` method being overridden correctly |
| Child-safety reminder and checklist | built into the form | help text only |
| Design | matches the teacher or supervisor panel | admin look; RTL editing in the admin is weaker |
| Cost | about 6 templates (2 shells × list, editor, profile), views, forms | less code |
| Tests | every role is tested against the views (§7.8) | the same, against admin views |

Shell per role:
- **teachers:** the teacher shell (`ui-*`);
- **everyone else:** the `base.html` shell with `partials/sidebar.html`, styled like the
  supervisor panel. A counselor's sidebar shows only the blog item. A director's shows
  their two items plus the blog item.

**D7. Login landing for authors without a panel.** Recommended: in
`accounts.utils.role_dashboard`, after the role dashboards and the staff check, an active
author goes to `/blog/write/` instead of the public home page. A counselor then logs in and
sees «نوشته‌های من». Roles that already have a panel keep it.

### Workflow

**D8. [policy] States, transitions and who does what.** Recommended:

```
            author: ارسال برای بررسی (privacy ack required)
  پیش‌نویس ─────────────────────────────▶ در انتظار بررسی
  (DRAFT)  ◀───────────────────────────── (SUBMITTED)
     │       author: پس گرفتن  /  editor: بازگرداندن با یادداشت
     │                                   │ editor: انتشار (checklist required;
     │ author: بایگانی                    │         now or a future date/time)
     ▼                                   ▼
  بایگانی  ◀─── editor: لغو انتشار ───── منتشرشده  (PUBLISHED; future published_at
  (ARCHIVED) ─── editor: انتشار دوباره ──▶          = «زمان‌بندی‌شده»)
     │
     └── author or editor: بازگرداندن به پیش‌نویس
```

Who does what:
- **Authors** edit only **drafts**, including drafts returned with an editor's note.
  - A submitted post is locked until they withdraw it.
  - They can archive their own draft. That is the soft "delete" (ADR-011): no hard delete
    for authors.
- **Editors** («ویراستار وبلاگ») are staff with `blog.publish_post`. They work in the
  Django admin, across all sections:
  - publish, now or scheduled;
  - unpublish (archive);
  - return to the author with a note;
  - feature a post;
  - edit any post.
- **Scheduled publishing:** status `PUBLISHED` with a future `published_at`.
  - The post becomes public at that moment (finding 13), and feeds and the sitemap follow.
  - Until then it shows as «زمان‌بندی‌شده» in the admin and the authoring area.
- **Each transition** is a function in `blog.services`, run under `select_for_update`:
  - it checks the current state, so a double click or two tabs can't publish twice;
  - it stamps `submitted_at`, `reviewed_by`, `reviewed_at` and `published_at`.
- A **database constraint** says a published post has a `published_at`.

**D9. [policy] Can authors edit after publishing?** Recommended: **no, in this task.**
- A published post is locked for its author.
- An editor can fix it in the admin, or return it to draft. Returning it takes it offline
  until it is published again.

Alternatives:
- (b) authors' edits go live immediately, skipping review. I don't recommend that for
  «مشاوره».
- (c) "suggested changes" stored as a pending revision, which the editor approves. That is
  a sizeable feature and can be added later without changing the model.

**D10. [policy] Per-section editors.** Recommended: **not in this task**. Editors are the
website admin's staff, for all sections. If, for example, the head counselor should approve
«مشاوره» posts:
- an optional Phase 4 adds a `can_review` flag on `AuthorSection`;
- it adds a «بررسی» tab in the authoring area for that section's submitted posts.

The model is shaped so that this is additive.

### Content

**D11. Rich text: a vendored WYSIWYG editor, Trix.** Recommended: **Trix 2.1.x** (MIT;
one JS and one CSS file, no build step, no dependencies), vendored under
`static/vendor/trix/` with its licence and a README (version, source, integrity), as
ADR-021 requires.

Why not Markdown:
- the authors are teachers and counselors, not technical users;
- Markdown markers (`**`, `#`, `-`) mix badly with right-to-left text when typed, and the
  result is hard to proofread.

Why not the alternatives:
- TinyMCE 7 and CKEditor 5 are GPL or commercial;
- Quill 2 writes bullet lists as `<ol data-list="bullet">`, which complicates sanitizing;
- Tiptap and Editor.js need a build step or JSON storage.

Configuration:
- paragraphs become `<p>`;
- Trix's "heading" becomes `<h2>`, and I add `<h3>`;
- toolbar: bold, italic, link, h2, h3, quote, bulleted and numbered lists, image, undo and
  redo. No colours, fonts or sizes.

**Phase 1 starts with a half-day spike**: RTL typing, Persian with ZWNJ, paste from Word,
lists in RTL, image upload. If Trix fails the spike, Quill 2 is the fallback, and I'll tell
you before going further.

Without JS:
- the body is a plain `<textarea>`;
- the server turns blank-line-separated paragraphs into `<p>` when the text has no tags,
  so an author can still write;
- inline images need JS, but the cover image doesn't.

Sanitizing (ADR-026), with **`nh3`**:
- it runs in `Post.save()` and again on render;
- the allow-list:
  - **tags:** `p h2 h3 strong em del a ul ol li blockquote br hr figure figcaption img
    pre`;
  - **link attributes:** `a[href]`, restricted to `http`, `https`, `mailto`, relative
    paths and `#`; `rel="noopener noreferrer"` is added;
  - **image attributes:** `img[src alt width height]`, and only when `src` is under
    `MEDIA_URL + "blog/"`: no hotlinked or `data:` images.
- everything else is removed with its content where it is dangerous (`script`, `style`,
  `iframe`, `object`): every `on*` attribute, `style`, `class`, `id`, and `javascript:` or
  `data:` URLs.
- after sanitizing, `h2` and `h3` get generated `id`s for the table of contents.
- new dependency: `nh3` in `requirements.txt` (pure wheel, no system packages).

**D12. A strict Content-Security-Policy on the public blog pages.** Recommended: yes, with
Django 6.0's built-in CSP, only on the blog's public views:
- `default-src 'self'`; `script-src 'self'`; `object-src 'none'`; `base-uri 'self'`;
- `img-src 'self'`; `form-action 'self'`; `frame-ancestors 'self'`.

A sanitizer bug would then still not run a script. `base.html` has no inline scripts, so
nothing breaks. The rest of the site is unchanged.

**D13. Post fields and the derived data computed on save.**
- **Required:** title (120), section, body.
- **Category:** required when the section has active categories.
- **Excerpt** (300): blank → the first ~200 characters of the text.
- **Cover image + `cover_alt`:** the alt is required when there is a cover; re-encoded,
  at most 1600 px.
- **Tags:** up to 5.
- **SEO:** `meta_title` and `meta_description`, falling back to the title and the excerpt.
- **Derived on save:**
  - `body_text`: normalised plain text, for search and reading time;
  - `reading_minutes`: words ÷ `BLOG_WORDS_PER_MINUTE` (180), at least 1, shown as
    «۴ دقیقه مطالعه»;
  - `toc`: the h2 and h3 headings.

**D14. [policy] Tags: who creates them?** Recommended:
- authors pick existing tags or type new ones, up to 5 per post;
- names are normalised (ی/ک, spaces, ZWNJ), so «کتاب‌خوانی» and «كتاب خوانی» don't become
  two tags;
- editors can rename, merge or deactivate tags in the admin;
- a tag page lists only public posts and is a 404 when there are none.

The alternative is admin-only tags, where authors only pick from the list. That is tidier
but slower to start with.

**D15. [policy] Seeding.**
- The two sections «پرورشی» (tomato paper) and «مشاوره» (sky paper) are created active,
  with a one-line description each:
  - «جشن‌ها، اردوها، هنر و فعالیت‌های بیرون از کلاس.»
  - «راهنمایی مشاور مدرسه برای خانواده‌ها: درس خواندن، احساسات و رشد بچه‌ها.»
- A `BlogPage` row holds the home page's texts and the safety texts.
- **No categories are seeded**: I don't know how the school wants them. Suggestions for the
  admin:
  - پرورشی: «جشن‌ها و مناسبت‌ها»، «اردو و گردش»، «هنر و خلاقیت»؛
  - مشاوره: «فرزندپروری»، «عادت‌های درس خواندن»، «احساسات کودک»، «خانه و مدرسه».
- No authors or posts are seeded.

### Safety and privacy

**D16. [policy] Child-safety texts, acknowledgement and checklist.** Recommended. The texts
are editable on «صفحه وبلاگ» and seeded as below.

Reminder at the top of the editor:

> «این نوشته در سایت عمومی مدرسه منتشر می‌شود. نام کامل، عکس چهره، کلاس یا هر نشانه‌ای
> که دانش‌آموزی را قابل شناسایی کند، بدون رضایت کتبی ولی او ننویسید و نگذارید. در
> نوشته‌های مشاوره، ماجراهای واقعی را طوری تغییر دهید که به هیچ دانش‌آموز یا خانواده‌ای
> نرسد.»

Acknowledgement checkbox before «ارسال برای بررسی» (required, stored as
`privacy_ack_at`):

> «این نوشته و عکس‌هایش هیچ دانش‌آموزی را بدون رضایت ولی‌اش قابل شناسایی نمی‌کند.»

Reviewer checklist, every line ticked before publishing (the publish form and the bulk
publish confirmation page):
1. «هیچ دانش‌آموزی بدون رضایت کتبی ولی قابل شناسایی نیست (نام، چهره، کلاس).»
2. «در نوشته‌های مشاوره، هیچ ماجرای واقعی به دانش‌آموز یا خانواده‌ای قابل ردیابی نیست.»
3. «هیچ اطلاعات داخلی مدرسه (نمره، غیبت، شماره تماس، نشانی) در متن یا عکس‌ها نیست.»
4. «همه عکس‌ها متن جایگزین دارند و اجازه انتشارشان گرفته شده است.»

The ticks aren't stored line by line. `reviewed_by` and `reviewed_at` record that someone
reviewed the post against the checklist of that day.

Not in this task: storing parents' consent forms. That is a records process, and it's
listed under open questions.

**D17. [policy] Comments.** Recommended: **not in this task**, as you lean.
- Moderated comments on «مشاوره» posts would invite parents to describe their own child's
  situation in public.
- The contact form already exists, so the post page ends with «پرسشی دارید؟ با دفتر مدرسه
  در تماس باشید» → `/contact/`.

Comments can come later on ADR-024's rules.

**D18. [policy] When an author leaves or loses access.** Recommended:
- they lose writing access at once (D4);
- their published posts stay public with their byline, since the writing belongs to the
  school;
- their author page stays while they have public posts;
- the «صفحه معلم» link disappears with the card (D5);
- the admin can unpublish posts, or untick «نمایش صفحه نویسنده» to remove the author page
  and the byline link. The name still shows on the post.

### Public site

**D19. SEO and discovery.** Recommended, all in this task:
- **per page:** a meta title and description, a canonical URL, and Open Graph tags
  (`og:type article`, the cover image or a default blog image, published and modified
  times);
- **structured data:** `Article` and `BreadcrumbList` JSON-LD on posts. It is a data
  block, not a script, so the CSP doesn't block it;
- **feeds:** Atom, `/blog/feed/` and one per section, 20 items, title + excerpt + link (not
  the full text), linked with `<link rel="alternate">`;
- **`/sitemap.xml`:** `django.contrib.sitemaps` added to `INSTALLED_APPS` (no migration).
  It lists the public site pages (home, about, contact, teachers) plus the blog home,
  sections, categories with posts, tags with posts, author pages and public posts;
- **`/robots.txt`:** a small view that points to the sitemap and disallows `/admin/`,
  `/auth/`, `/dashboard/`, `/blog/write/` and the other logged-in panels;
- **noindex:** previews and search results are `noindex`.

**D20. Menu.** As requested, a reversible migration (`website.0014_blog_menu`):
- the nav row «وبلاگ» still at `#` → `/blog/`;
- the nav row «مقاله» still at `#` → deactivated (not deleted);
- the reverse resets only a «وبلاگ» row still at `/blog/`, and re-activates only an
  inactive «مقاله» row still at `#`;
- rows an admin has renamed or linked are left alone.

**D21. The teachers page link.** Recommended: yes.
- The commented «نوشته‌های …» slot in a teacher's card (left there by the teachers page)
  becomes a link to the author page.
- It shows when an author linked to that card has public posts.
- Cost: one query for all cards (author slugs by card id), so the teachers page goes from
  5 to 6 queries, still flat, and its locked counts are updated.

**D22. Not in this task** (each would be its own small plan):
- the latest posts on the landing page;
- view counters: they would need writes on GET, and add little;
- video embeds such as Aparat: a third-party iframe;
- suggested-change revisions (D9c);
- comments (D17).

### Technical

**D23. The author check costs zero queries** (finding 6). Recommended:
- a small authentication backend, `accounts.backends.ModelBackend`, which subclasses
  Django's and overrides only `get_user()` to `select_related("blog_author")`;
- the sidebar asks `user.blog_author` without a query;
- the full `writable_sections()` check runs only in the blog's own views.

The alternative is to accept +1 query on every panel page and update about 37 locked
counts. That is transparent but noisy.

**D24. Settings** (`base.py`, each read in one place):

| Setting | Value | Note |
|---|---|---|
| `BLOG_AUTHOR_ROLES` | as D3 | **[policy]** |
| `BLOG_WORDS_PER_MINUTE` | 180 | Persian reading speed |
| `BLOG_PAGE_SIZE` | 9 | fills a 3-column grid |
| `BLOG_MAX_TAGS_PER_POST` | 5 | |
| `BLOG_FEED_ITEMS` | 20 | |
| `BLOG_TOC_MIN_HEADINGS` | 3 | the table of contents is shown from this many headings |

**D25. ADR.**
- A new **ADR-026: "Blog authorship is granted per section by the website admin; post HTML
  is sanitized with an allow-list"**. It covers D3, D4, D6, D8, D11 and D12, and records
  that the director writes outside the read-only panel.
- **ADR-025**'s consequences get one line: the blog follows the editorial rule, and the
  author photo is never the account avatar.

---

## 3. Phases

Each phase ends with tests green, docs updated for that phase, and a stop for your review.
You decide whether a phase is committed on `feature/blog` before the next one starts.

| Phase | Contents | Visible change |
|---|---|---|
| **1. Foundations** | Trix spike; `blog` app, models, migrations, seed; content pipeline (sanitizer, slugs, reading time, TOC, plain text); `permissions.py`; workflow `services.py`; admin (sections + categories, tags, authors, posts, «در انتظار بررسی», publish form with checklist, bulk actions with confirmation); settings; ADR-026 | admin only; nothing public |
| **2. Public blog** | design system; home, section, category, tag, author, post, search, pagination; preview; SEO, feeds, sitemap, robots; CSP; menu migration; navbar prefix highlight; teachers page link (D21); query-count locks; screenshots | the blog goes live after `migrate` |
| **3. Authoring area** | «نوشته‌های من» in both shells: list, editor, image upload, preview, submit and withdraw, own author profile; sidebar items; auth backend (D23); login landing (D7); full role matrix tests; screenshots | authors write in their panel |
| *4. Section editors (optional)* | only if D10 is changed to yes | |

Until Phase 3, editors can write posts in the admin themselves, so Phase 2 can be
reviewed with real content.

---

## 4. Design of the public blog

### 4.1 Subject, audience and job

- **Subject:** a primary school's own writing, in two voices. «پرورشی» covers celebrations,
  trips, art and projects. «مشاوره» is the counselor's guidance for families.
- **Audience:** parents, mostly on phones, often reading a long «مشاوره» article to the
  end; and children looking at «پرورشی» posts with their parents.
- **Job:** make visiting a pleasure, and make a 1,500-word article comfortable to read.

### 4.2 The direction: «روزنامه دیواری» (the class wall newspaper)

Every Iranian schoolchild knows the روزنامه دیواری:
- a board in the corridor;
- a big hand-made title, each word cut from a different colour of card;
- articles written on sheets of paper glued on, edged with pinking shears (قیچی زیگزاگ);
- corners held with strips of tape;
- photos stuck on with photo corners.

It is literally the school's place for writing that people stop to read. The blog is the
school's wall newspaper, online.

It also continues the site's stationery family: the About page's blue ballpoint, the
Contact page's notebook page, and the Teachers page's red pen. The blog adds **coloured
card, tape and scissors**: louder and more joyful than the rest, as you asked, but from
the same drawer.

**The one memorable thing: the masthead.**
- The blog's title, «وبلاگ نسل قلم», is set in Vazirmatn 900. Each **word** sits on its
  own cut-out of coloured card with a pinking-shear edge, tilted a few degrees, held by a
  strip of tape.
- Words, not letters: Persian letters join, and cutting them apart would break the script.
- The `h1` stays real text; the cut-outs are spans styled with CSS.
- **The one orchestrated motion:** on first load, the cut-outs drop onto the board one
  after another and "stick" (a 600 ms settle). It runs only once, and not at all with
  `prefers-reduced-motion`.

Everything else is quiet:
- posts are **white sheets** with dark ink;
- a single tape strip in the section's colour says which section a post belongs to,
  together with the written section name, never colour alone;
- the post page is a calm, wide sheet built for reading. There's no rotation and nothing
  moves.

### 4.3 Tokens (new, in `blog/static/blog/css/blog.css`)

Colour. Every pair was checked with a script; ratios are WCAG 2.x.

| Token | Value | Role | Contrast |
|---|---|---|---|
| `--bl-wall` | `#e7f0fb` | the painted wall behind the board (page background) | ink on it 12.3:1 |
| `--bl-sheet` | `#ffffff` | sheets: cards and the reading surface | — |
| `--bl-ink` | `#1e2a4a` | all body text and headings (a school-uniform navy) | 14.1:1 on sheet |
| `--bl-ink-soft` | `#4a5573` | dates, reading time, captions | 7.4:1 on sheet, 6.4:1 on the wall |

Coloured card: the palette sections and masthead words pick from. A section's colour is a
**choice** in the admin, so a new section can't pick an inaccessible colour.

| Paper | Card (`--bl-<name>`) | Ink on white (`--bl-<name>-ink`) | Navy on card | Card ink on white |
|---|---|---|---|---|
| گوجه‌ای (tomato) | `#ff7a59` | `#b33a1c` | 5.5:1 | 5.9:1 |
| آفتابگردانی (sunflower) | `#ffd23f` | `#7a5600` | 9.8:1 | 6.7:1 |
| چمنی (grass) | `#5cc98f` | `#1a7148` | 6.9:1 | 6.0:1 |
| آسمانی (sky) | `#5db2ff` | `#1a5ea8` | 6.3:1 | 6.5:1 |
| انگوری (grape) | `#a58bff` | `#5a3ccc` | 5.2:1 | 7.1:1 |
| آدامسی (bubblegum) | `#ff94c6` | `#a8306b` | 6.9:1 | 6.4:1 |

How they're used:
- **Text on card** (masthead words, section chips, tags) is always navy.
- **Coloured text on white** (links in the body, the section name) uses the `-ink` step.
  White text on the `-ink` steps passes too (5.9–7.1:1), for filled buttons.
- **Focus ring:** 3 px navy with a 2 px sunflower gap, visible on white, the wall and
  every card.

**Type: Vazirmatn only** (the vendored variable font, 100–900; ADR-021, and you asked for
the site's font). The play comes from weight, scale and the paper, not a second face.

| Role | Size | Weight | Line height |
|---|---|---|---|
| masthead `h1` | `clamp(2.4rem, 1.4rem + 4.6vw, 4.6rem)` | 900 | 1.25 |
| post title `h1` | `clamp(1.75rem, 1.2rem + 2.4vw, 2.9rem)` | 850 | 1.45 |
| card title `h2`/`h3` | `clamp(1.1rem, 1rem + 0.5vw, 1.3rem)` | 800 | 1.6 |
| lead (excerpt on the post) | 1.2rem | 500 | 1.95 |
| **body** | **1.125rem phone, 1.1875rem from 768 px** | 400, bold 700 | **2.05** |
| body `h2` / `h3` | 1.5rem / 1.25rem | 800 | 1.6 |
| meta (date, reading time) | 0.9375rem | 500 | 1.7 |

- The body measure is **at most 66ch**, which is about 60–70 Persian characters.
- Text is start-aligned (right), never justified: justified Persian on a phone opens
  rivers.
- Nothing is smaller than 0.875rem.

### 4.4 Layout and principles

- **The board:** the page background is the wall, and the content sits on it.
- **Home:**
  - the masthead, the intro sentence and search;
  - then the sections as **two big folders** of coloured card (title, one line, the
    number of posts written out);
  - then **featured**: one large sheet with its cover photo held by photo corners, and up
    to two smaller featured sheets beside it;
  - then «تازه‌ترین نوشته‌ها» as a grid of sheets (1 / 2 / 3 columns at < 576 / 576 /
    992 px);
  - pagination; then the tags as round stickers.
- **Sheets:** white, with a pinking-shear bottom edge (CSS `mask`) and a tape strip in the
  section colour at the top.
  - On desktop they lean ±0.6–1.2° in a fixed, repeating pattern (`nth-child`), so the
    grid looks hand-pinned. On phones and the post page they sit straight.
  - Hover and focus straighten a sheet and lift it 2 px. That is the only hover effect,
    and it shows what's clickable.
  - Each sheet is one `<article>` with one link on its title, stretched over the card with
    a pseudo-element, so screen readers announce one link per post.
- **Post:**
  - one big straight sheet, at most 760 px wide on desktop;
  - the TOC as a **yellow sticky note** beside it, sticky from 1200 px; on phones it's a
    `<details>` «فهرست این نوشته» under the byline;
  - share stickers;
  - previous/next as two paper tabs, then «نوشته‌های مرتبط» as three small sheets.
- **Section and category pages:** a smaller masthead made of the section's single card
  word, the category chips (a `<nav>`), then the grid.
- **Tag and author pages** are the same, headed by the tag sticker or the author's circle
  photo on card.

Principles:
1. **Colour is for joy around the text, never under it.** Long text is always navy on
   white.
2. **One loud thing per page:** the masthead on home, the section card on section pages,
   the cover photo on a post. Nothing else competes.
3. **Information is never colour alone:** the section name is always written.
4. **Semantics:**
   - one `h1` per page, `<main>`, and breadcrumbs as a `<nav aria-label>` with an `ol`;
   - posts as `<article>` with `<time datetime>` holding the ISO date and the Jalali date
     as text;
   - the TOC as a `<nav aria-labelledby>` with an `ol`;
   - pagination as a `<nav aria-label="صفحه‌ها">`, with `aria-current="page"` on the
     current page.
5. **RTL with logical properties only.** The tape, the photo corners and the pinking edge
   mirror correctly.
6. **No JS needed:** search is a GET form; pagination, filters and the TOC are links;
   share links are plain URLs. «کپی پیوند» is JS-only and hidden without JS; a `<noscript>`
   shows the URL in a read-only field.
7. **Print stylesheet for posts:** parents print counseling articles. It prints the sheet
   only, with the URL under the title, and no tape, stickers or navigation.

Share links, with no third-party scripts:
- Telegram: `https://t.me/share/url?url=…&text=…`;
- WhatsApp: `https://wa.me/?text=…`;
- copy link.

### 4.5 What I changed after checking against the generic defaults

- **First sketch:** a "kids' site" kit, with crayon doodles, a rainbow-gradient hero and
  rounded white cards with the same soft shadow. That's the default for any children's
  blog, plus the SaaS card kit. **Now** it's a specific Iranian school object, the wall
  newspaper:
  - pinking-shear sheets, tape and photo corners;
  - no gradients;
  - a hard, short "paper on a wall" shadow instead of the soft grey one.
- **First sketch:** a second, "playful" display face for headings. That means a large
  vendored font, and you asked for the site's font. **Now** the play comes from Vazirmatn
  at 900 on cut-out card.
- **First sketch:** every card tilted, wiggling on hover, and fading in as it scrolls.
  That's motion everywhere. **Now** there's one masthead moment, tilts only on desktop
  grids, and nothing on the reading page.
- **First sketch:** a cork-board texture. It's cliché and noisy behind text. **Now** the
  wall is a flat painted blue.
- **First sketch:** the meta line «مشاوره · ۵ دقیقه · ۱۲ آبان». That's the middle-dot
  tell. **Now** the section is a card chip, the reading time is a small paper tag, and the
  date is its own `<time>`.
- **First sketch:** sections in fixed green and blue. **Now** the colour is an admin
  choice from the palette, so a third section needs no code.
- No eyebrow labels, no `→` on links, no numbered markers (posts aren't a sequence; the
  TOC's `ol` is).

### 4.6 Wireframe: blog home, desktop (1280 px)

```
┌ public navbar (shared) ─────────── «وبلاگ» highlighted ───────────────────────┐
│░░░░░░░░░░░░░░░░░░░░░░░░░░ wall #e7f0fb ░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░│
│      ┌▔▔tape▔▔┐                                                              │
│   ╱‾‾‾‾‾‾‾‾‾‾‾╲   ╱‾‾‾‾‾‾‾╲  ╱‾‾‾‾‾‾‾╲     ← h1: each word on a card cut-out,  │
│   │  وبلاگ  │   │  نسل  │  │  قلم  │        tilted −3° / 2° / −1.5°,          │
│   ╲▁▁▁▁▁▁▁▁▁▁▁╱   ╲▁▁▁▁▁▁▁╱  ╲▁▁▁▁▁▁▁╱        tomato / sunflower / sky          │
│   نوشته‌هایی از معلمان و مشاور مدرسه، برای بچه‌ها و پدر و مادرها.              │
│   [ جستجو در نوشته‌ها…                                   ] [ جستجو ]         │
│                                                                               │
│   ┌ tomato card ─────────────────┐  ┌ sky card ────────────────────┐          │
│   │ پرورشی                        │  │ مشاوره                        │          │
│   │ جشن‌ها، اردوها، هنر و …        │  │ راهنمایی مشاور مدرسه برای …   │          │
│   │ ۲۴ نوشته                       │  │ ۱۱ نوشته                      │          │
│   └──────────────────────────────┘  └──────────────────────────────┘          │
│                                                                               │
│   نوشته‌های ویژه (h2)                                                          │
│   ┌▔tape▔─────────────────────────────────┐ ┌▔tape▔──────────────┐            │
│   │ ◸ cover photo, photo corners        ◹ │ │ [مشاوره] chip        │            │
│   │ ◺                                   ◿ │ │ title, 2 lines      │            │
│   │ [پرورشی] chip   [۴ دقیقه] tag         │ │ excerpt, 2 lines    │            │
│   │ جشن پاییز در حیاط مدرسه (h3)           │ └/\/\/\/\/\/\/\/\/\/\┘            │
│   │ excerpt, 3 lines                       │ ┌▔tape▔──────────────┐            │
│   │ (ن) نام نویسنده   ۱۲ آبان ۱۴۰۵          │ │ …                    │            │
│   └/\/\/\/\/\/\/\/\/\/\/\/\/\/\/\/\/\/\/\/┘ └/\/\/\/\/\/\/\/\/\/\┘            │
│                                                                               │
│   تازه‌ترین نوشته‌ها (h2)                                                       │
│   ┌▔▔┐──────────┐  ┌▔▔┐──────────┐  ┌▔▔┐──────────┐   sheets lean ±1°,        │
│   │ cover        │  │ (no cover:   │  │ cover        │   straighten on hover/   │
│   │ chip, title  │  │  title       │  │ chip, title  │   focus                  │
│   │ excerpt      │  │  larger)     │  │ excerpt      │                          │
│   │ author, date │  │ author, date │  │ author, date │                          │
│   └/\/\/\/\/\/\/┘  └/\/\/\/\/\/\/┘  └/\/\/\/\/\/\/┘                          │
│   … 9 per page                                                                │
│        ( قبلی )  ( ۱ ) [ ۲ ] ( ۳ )  ( بعدی )                                   │
│                                                                               │
│   برچسب‌ها:  (کتاب‌خوانی) (اردو) (والدگری) (ریاضی در خانه) …  ← round stickers │
├ footer (shared) ──────────────────────────────────────────────────────────────┤
```

### 4.7 Wireframe: blog home, phone (375 px)

```
┌ logo                    ☰ ┐
│░░░░░░░░ wall ░░░░░░░░░░░░░│
│ ╱‾‾‾‾‾‾‾╲ ╱‾‾‾‾‾╲          │  cut-outs wrap; tilts kept small
│ │ وبلاگ │ │ نسل │          │
│ ╲▁▁▁▁▁▁▁╱ ╲▁▁▁▁▁╱          │
│ ╱‾‾‾‾‾╲                     │
│ │ قلم │                     │
│ ╲▁▁▁▁▁╱                     │
│ one sentence               │
│ [جستجو در نوشته‌ها…    ][🔍]│  44 px; label visually hidden
│ ┌ tomato ────────────────┐ │
│ │ پرورشی       ۲۴ نوشته   │ │  folders become two wide strips
│ └────────────────────────┘ │
│ ┌ sky ───────────────────┐ │
│ │ مشاوره       ۱۱ نوشته   │ │
│ └────────────────────────┘ │
│ نوشته‌های ویژه              │
│ ┌▔▔┐────────────────────┐  │  straight, full width
│ │ cover                 │  │
│ │ chip  title  excerpt  │  │
│ └/\/\/\/\/\/\/\/\/\/\/\┘  │
│ تازه‌ترین نوشته‌ها          │
│ ┌▔▔┐ title ──────────────┐  │  one column; cover above
│ │ …                     │  │
│ └/\/\/\/\/\/\/\/\/\/\/\┘  │
│ ( قبلی )  صفحه ۲ از ۵  ( بعدی ) │
│ (کتاب‌خوانی) (اردو) …       │  stickers wrap
└ footer ────────────────────┘
```

### 4.8 Wireframe: post page, desktop (1280 px)

```
┌ public navbar ────────────────────────────────────────────────────────────────┐
│░░ wall ░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░│
│  وبلاگ › مشاوره › فرزندپروری                    (breadcrumb nav, ol)          │
│  ┌▔▔▔▔ sky tape ▔▔▔▔┐───────────────────────────────┐   ┌ sunflower note ──┐  │
│  │ [مشاوره] card chip      [۵ دقیقه مطالعه] paper tag │   │ فهرست این نوشته  │  │
│  │                                                  │   │ ۱. چرا…           │  │
│  │ چطور با کودک درباره ترس‌هایش حرف بزنیم؟  (h1)     │   │ ۲. وقتی بچه…      │  │
│  │ lead: the excerpt, larger, 2–3 lines              │   │ ۳. …              │  │
│  │ ( ن )  نام نویسنده        منتشرشده: ۱۲ آبان ۱۴۰۵  │   └──────────────────┘  │
│  │        مشاور مدرسه        به‌روزرسانی: ۲۰ آبان     │    sticky from 1200 px │
│  │ ◸ cover photo ◹  (photo corners; alt from cover_alt)│                        │
│  │ ◺             ◿                                   │   ( تلگرام )            │
│  │ body at 66ch, 1.1875rem / 2.05, navy on white      │   ( واتساپ )            │
│  │ ## h2 in navy, a short underline of sky card       │   ( کپی پیوند )         │
│  │ > blockquote on a strip of sky card               │                        │
│  │ images full sheet width, rounded, photo corners    │                        │
│  │ برچسب‌ها: (ترس) (گفت‌وگو با کودک)                    │                        │
│  │ ┌ author box ──────────────────────────────────┐ │                        │
│  │ │ ( ن ) نام نویسنده: bio, 2 lines                │ │                        │
│  │ │ همه نوشته‌های نام نویسنده   صفحه معلم            │ │                        │
│  │ └──────────────────────────────────────────────┘ │                        │
│  │ پرسشی دارید؟ با دفتر مدرسه در تماس باشید → /contact/ │                        │
│  └/\/\/\/\/\/\/\/\/\/\/\/\/\/\/\/\/\/\/\/\/\/\/\/\/\/┘                        │
│  ┌ ‹ نوشته بعدی ───────────┐            ┌ نوشته قبلی › ───────────┐          │
│  └─────────────────────────┘            └─────────────────────────┘          │
│  نوشته‌های مرتبط (h2):  three small sheets (same category, then shared tags)  │
├ footer ───────────────────────────────────────────────────────────────────────┤
```

### 4.9 Wireframe: post page, phone (375 px)

```
┌ logo                    ☰ ┐
│ وبلاگ › مشاوره              │  breadcrumb wraps
│ ┌▔ sky tape ▔┐────────────┐│  sheet: 16 px side gutters
│ │[مشاوره] [۵ دقیقه مطالعه] ││
│ │ title (h1), wraps        ││
│ │ lead                     ││
│ │ (ن) نام نویسنده           ││
│ │     ۱۲ آبان ۱۴۰۵          ││
│ │ ▸ فهرست این نوشته         ││  <details>, 44 px row
│ │ cover, full sheet width  ││
│ │ body 1.125rem / 2.05     ││
│ │ … tags, author box       ││
│ │ (تلگرام)(واتساپ)(کپی)     ││  share row wraps
│ └/\/\/\/\/\/\/\/\/\/\/\/\┘│
│ ‹ نوشته بعدی                │  stacked tabs
│ نوشته قبلی ›                │
│ نوشته‌های مرتبط: one column  │
└ footer ────────────────────┘
```

### 4.10 Wireframe: authoring screen, teacher panel (1280 px)

This copies the teacher panel's `ui-*` design: `ui-page-head`, `ui-card`, `ui-tabs`,
`ui-badge`, `ui-form`, `ui-field`, `ui-btn`. The only blog-specific CSS is the editor's
toolbar and content area, built from `--ui-*` tokens.

```
┌ teacher sidebar ┐┌ ui-topbar: نوشته‌های من ─────────────────────── user menu ┐
│ داشبورد          ││ ui-page-head                                             │
│ برنامه هفتگی     ││  نوشته‌های من                        [ + نوشته تازه ]      │
│ کلاس‌ها          ││  (a section picker when the author has more than one)    │
│ گزارش‌ها         ││ ui-tabs: همه (۷) | پیش‌نویس (۲) | در انتظار بررسی (۱) |    │
│ ▶ نوشته‌های من   ││          منتشرشده (۴) | بایگانی                          │
│                 ││ ┌ ui-card ─────────────────────────────────────────────┐ │
│                 ││ │ ⚠ بازگردانده شد: «لطفاً نام کلاس را حذف کنید.»        │ │
│                 ││ │ جشن پاییز در حیاط مدرسه   [پرورشی] [پیش‌نویس]          │ │
│                 ││ │ آخرین ویرایش: ۱۴ آبان           ویرایش   پیش‌نمایش    │ │
│                 ││ ├──────────────────────────────────────────────────────┤ │
│                 ││ │ کتاب‌خوانی در خانه   [پرورشی] [منتشرشده] ۱۰ آبان   دیدن │ │
│                 ││ └──────────────────────────────────────────────────────┘ │
└─────────────────┘└──────────────────────────────────────────────────────────┘

Editor (/blog/write/<id>/edit/):
┌ ui-page-head: ویرایش نوشته در «پرورشی»   [پیش‌نمایش] [ذخیره پیش‌نویس] ──────────┐
│ ┌ warning callout (ui-warning-soft) ───────────────────────────────────────┐ │
│ │ این نوشته در سایت عمومی مدرسه منتشر می‌شود. نام کامل، عکس چهره، …           │ │
│ └──────────────────────────────────────────────────────────────────────────┘ │
│ ┌ ui-card (main, 2/3) ──────────────────────┐ ┌ ui-card (side, 1/3) ───────┐ │
│ │ عنوان  [______________________________]   │ │ دسته  [ اردو و گردش ▾ ]     │ │
│ │ متن                                       │ │ برچسب‌ها [کتاب‌خوانی ×] [+]   │ │
│ │ [B][I][🔗][عنوان][زیرعنوان]["][•][1.][🖼][↶] │ │ تصویر شاخص [انتخاب فایل]    │ │
│ │ ┌───────────────────────────────────────┐ │ │ متن جایگزین تصویر [______] │ │
│ │ │ Trix area, RTL, min 24rem, auto-grows │ │ │ ▸ تنظیمات جستجو (details)   │ │
│ │ └───────────────────────────────────────┘ │ │   عنوان سئو، توضیح سئو      │ │
│ │ خلاصه  [textarea, 300, counter]           │ │ نامک [__________] (draft)  │ │
│ └───────────────────────────────────────────┘ └────────────────────────────┘ │
│ ┌ ui-card ─────────────────────────────────────────────────────────────────┐ │
│ │ ☐ این نوشته و عکس‌هایش هیچ دانش‌آموزی را بدون رضایت ولی‌اش قابل شناسایی … │ │
│ │                                   [ ذخیره پیش‌نویس ] [ ارسال برای بررسی ] │ │
│ └──────────────────────────────────────────────────────────────────────────┘ │
```

### 4.11 Wireframe: authoring screen, phone (375 px)

```
┌ ☰  نوشته‌های من        (ن) ┐
│ ویرایش نوشته در «پرورشی»   │
│ [پیش‌نمایش]                 │
│ ┌ ⚠ reminder ───────────┐ │
│ └───────────────────────┘ │
│ عنوان [_______________]   │
│ متن                        │
│ [B][I][🔗][ع][ز]["][•][1.]→│  toolbar scrolls inside itself
│ ┌───────────────────────┐ │  (no page scroll)
│ │ editor                │ │
│ └───────────────────────┘ │
│ خلاصه […]                 │
│ دسته [▾]  برچسب‌ها […]      │  side card stacks below
│ تصویر شاخص, متن جایگزین    │
│ ▸ تنظیمات جستجو            │
│ ☐ acknowledgement          │
│ [ ذخیره پیش‌نویس ]          │  full-width buttons
│ [ ارسال برای بررسی ]        │
└───────────────────────────┘
```

The `base.html` shell, for supervisors, counselors and the director, has the same content
in the supervisor panel's components: `dashboard-header`, the `sv-*` card and form styles,
`btn btn--primary`, `status-pill`.

---

## 5. Data model

```mermaid
erDiagram
    User ||--o| BlogAuthor : "may be"
    BlogAuthor }o--o| LandingTeacher : "optional public card"
    BlogAuthor ||--o{ AuthorSection : "may write in"
    Section ||--o{ AuthorSection : ""
    User ||--o{ AuthorSection : "granted by"
    Section ||--o{ Category : "has"
    Section ||--o{ Post : ""
    Category |o--o{ Post : ""
    BlogAuthor ||--o{ Post : "writes"
    Post }o--o{ Tag : "tagged"
    Post ||--o{ PostImage : "inline images"
    User |o--o{ Post : "reviewed by"

    BlogPage {
        str title "«وبلاگ نسل قلم»"
        text intro
        text author_reminder "D16"
        text author_ack "D16"
        text review_checklist "one line per item"
        image og_image "default share image"
        str meta_title
        str meta_description
    }
    Section {
        str title "پرورشی"
        slug slug "unicode, unique"
        str description
        str paper "choice: tomato sky ..."
        int order
        bool is_active
    }
    Category {
        fk section
        str title
        slug slug "unique per section"
        int order
        bool is_active
    }
    Tag {
        str name "normalised, unique"
        slug slug "unicode, unique"
        bool is_active
    }
    BlogAuthor {
        fk user "one-to-one"
        str display_name "blank: first + last name"
        slug slug "unique, frozen"
        text bio
        image photo "re-encoded"
        fk teacher_card "nullable, SET_NULL"
        bool show_profile "author page and byline link"
        bool is_active "may write"
    }
    AuthorSection {
        fk author
        fk section
        fk granted_by "nullable"
        jdatetime granted_at
    }
    Post {
        fk section "PROTECT"
        fk category "nullable, PROTECT, same section"
        fk author "PROTECT"
        str title
        slug slug "unicode, unique, frozen once published"
        str excerpt
        text body "sanitized HTML"
        text body_text "normalised plain text"
        json toc
        int reading_minutes
        image cover "re-encoded"
        str cover_alt
        str status "DRAFT SUBMITTED PUBLISHED ARCHIVED"
        bool is_featured
        jdatetime published_at "check: set when PUBLISHED"
        jdatetime submitted_at
        jdatetime privacy_ack_at
        fk reviewed_by "nullable"
        jdatetime reviewed_at
        text review_note "shown to the author"
        str meta_title
        str meta_description
        jdatetime content_updated_at
    }
    PostImage {
        fk post "CASCADE"
        image image "re-encoded"
        fk uploaded_by
    }
```

Rules:
- **`Post.clean()` and the service** check that `category.section == section`, and that a
  draft has an editable slug.
- **Indexes:** `(status, published_at)`, `(section, status, published_at)`,
  `(author, status)`.
- **Unique constraints:** `(section, slug)` on `Category`; `(author, section)` on
  `AuthorSection`.
- **One public rule**, `Post.objects.public()`:
  - `status=PUBLISHED`, `published_at <= now`, section active;
  - every public page, feed and the sitemap use it;
  - drafts, submitted, scheduled and archived posts are a **404** on public URLs for
    everyone, staff included. Staff and authors use the preview.
- **Inactive category or tag:** the post stays visible; the category or tag link isn't
  shown, and its page is a 404.
- **Inline images:**
  - a `PostImage` is created when an author uploads (validated, re-encoded);
  - on save, images whose URL no longer appears in the body are deleted, with their files
    removed after commit (the `website.signals` handlers are reused);
  - every image field is registered for file cleanup.
- **`content_updated_at`** is set when the title, body or excerpt change after
  publication. «به‌روزرسانی: …» is shown only when it is more than a day after
  `published_at`.

---

## 6. Permission matrix

Legend:
- ✓ allowed;
- **404** not found (existence not revealed);
- **403** forbidden;
- **→login** redirected to the login page;
- "author (S)" is an author granted section S.

| Action | Anonymous | Student | Logged in, not an author (teacher, supervisor, director…) | Author (S), own post | Author (S), another author's post or section T | Inactive author, or role no longer eligible, or staff inactive | Staff without blog permissions | Editor (staff + `blog.*` + `publish_post`) | Superuser |
|---|---|---|---|---|---|---|---|---|---|
| read public blog pages, feeds, sitemap | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ |
| open a draft, submitted, scheduled or archived post by public URL | 404 | 404 | 404 | 404 (use preview) | 404 | 404 | 404 | 404 (use preview) | 404 (use preview) |
| preview a non-public post | 404 | 404 | 404 | ✓ | 404 | 404 | 404 | ✓ | ✓ |
| open «نوشته‌های من» | →login | 403 | 403 | ✓ | ✓ (own posts only) | 403 | 403 | 403 unless also an author | 403 unless also an author |
| create a post in S | →login | 403 | 403 | ✓ | T: 403 | 403 | 403 | admin ✓ | admin ✓ |
| edit own draft (or returned) | →login | 403 | 403 | ✓ | others': 404 | 403 | 403 | admin ✓ (any) | admin ✓ |
| edit own submitted post | | | | ✗ (withdraw first) | 404 | 403 | | admin ✓ | admin ✓ |
| edit own published post | | | | ✗ (D9) | 404 | 403 | | admin ✓ | admin ✓ |
| submit, withdraw, archive own post | →login | 403 | 403 | ✓ | 404 | 403 | 403 | admin ✓ | admin ✓ |
| upload an image to a post | →login | 403 | 403 | ✓ (own draft) | 404 | 403 | 403 | admin ✓ | admin ✓ |
| publish, schedule, unpublish, return, feature | ✗ | ✗ | ✗ | ✗ | ✗ | ✗ | ✗ (admin hides the actions) | ✓ (checklist required) | ✓ |
| edit own author profile (bio, photo) | →login | 403 | 403 | ✓ (display name: admin only) | 404 | 403 | 403 | admin ✓ | admin ✓ |
| manage sections, categories, tags | ✗ | ✗ | ✗ | ✗ | ✗ | ✗ | per Django permission | ✓ | ✓ |
| grant author access (`BlogAuthor`, `AuthorSection`) | ✗ | ✗ | ✗ | ✗ | ✗ | ✗ | per Django permission | with `add/change_blogauthor` | ✓ |

Notes:
- **Wrong role or wrong section → 403.** Someone else's post, or a post id that doesn't
  exist → 404. Author views look posts up with `get_object_or_404` on the author's own
  queryset, the `SupervisorScope` pattern (ADR-014).
- **Logged in without author access → 403**, with a Persian page that says to ask the
  website admin. This follows `require_supervisor` rather than redirecting, so a link
  someone was sent doesn't silently bounce them to a dashboard.
- **Write views take POST only** for transitions, with CSRF.
- **The director panel stays GET-only.** Author access for a director is a separate,
  explicit grant (D3).
- Permissions are granted by hand in the admin; no migration creates groups or grants (as
  in ADR-024). The docs will give the steps for a «ویراستار وبلاگ» group.

---

## 7. Implementation outline

### 7.1 Models and migrations (`blog/models/`)

Files:
- `page.py`: `BlogPage(SingletonModel)`, reusing `website.models.base`;
- `section.py`: `Section`, `Category`;
- `tag.py`: `Tag`;
- `author.py`: `BlogAuthor`, `AuthorSection`;
- `post.py`: `Post` (`PostQuerySet.public()`, `.for_author()`), `PostImage`;
- `__init__.py`.

`Post.save()` runs `blog.content.prepare(post)`: sanitize, ids and TOC, `body_text`,
reading time, excerpt fallback. It also re-encodes a new cover and fills a draft's slug.

Migrations:

| Migration | Kind | Contents | Reverse |
|---|---|---|---|
| `blog.0001_initial` | schema | all tables, constraints, indexes, the `publish_post` permission | drops them |
| `blog.0002_seed` | data | `BlogPage` row with the D16 texts; sections «پرورشی» (tomato) and «مشاوره» (sky). Create only (`get_or_create`) | deletes only those rows, and only if no post uses them |
| `website.0014_blog_menu` | data | D20 | D20 |

Verification:
- `makemigrations --check`;
- forward → back to `website 0013` / `blog zero` → forward on a scratch SQLite copy;
- the test database on PostgreSQL;
- migration tests for `0014` in both directions, including rows an admin edited.

### 7.2 Content pipeline (`blog/content.py`, `blog/text.py`)

- **`text.py`:**
  - `normalize()`: ي→ی, ك→ک, Arabic and Persian digits → ASCII for search, collapsed
    spaces, ZWNJ kept in display text and dropped for search;
  - `unique_slug()`: shared by posts, tags and authors, in the same shape as
    `LandingTeacher._unique_slug`;
  - `reading_minutes()`;
  - `plain_text()`.
- **`content.py`:**
  - `sanitize(html)`: the nh3 allow-list of D11, with an attribute filter for `img src`
    and `rel` on links;
  - `plain_to_html()`: the no-JS fallback;
  - `add_heading_ids()`: h1 → h2, ids from `slugify(allow_unicode)`, de-duplicated;
  - `toc()`.

### 7.3 Permissions and services

- **`blog/permissions.py`:**
  - `author_for(user)`, `writable_sections(user)`, `can_write_in(user, section)`;
  - `author_posts(user)`: the queryset every authoring view starts from;
  - `can_preview(user, post)`, `can_publish(user)`;
  - decorators `author_required` (→login, 403) and `post_editable` (a post the author
    can't edit opens read-only, with the reason).
- **`blog/services.py`:**
  - `create_draft`, `save_draft`, `submit`, `withdraw`, `archive`, `reopen`;
  - `publish(post, by, at=None)`, `unpublish`, `return_to_author(note)`, `set_featured`;
  - `add_image(post, file, by)`;
  - `sync_tags(post, names)`.

  Each runs in `transaction.atomic()` with `select_for_update` on the post, checks the
  allowed source states, and raises `TransitionError` with a Persian message.
- **`blog/selectors.py`:**
  - `home_page()`: featured and latest, with section counts in one aggregate query;
  - `section_listing`, `category_listing`, `tag_listing`, `author_listing`;
  - `search(q)`;
  - `post_page(slug)`: the post, tags, related and previous/next;
  - `author_dashboard(user, status)`: the list and the tab counts in one aggregate query.

### 7.4 Views, URLs and site-wide bits

- **`blog/views/public.py`:** one thin function each, `require_safe`, with the CSP
  decorator (D12).
- **`blog/views/studio.py`:**
  - `write_list`, `write_new`, `write_edit`, `write_transition` (POST);
  - `write_preview`, `write_image_upload`: POST, returns `{url}` JSON for Trix. This is the
    one JSON response, needed by the editor; ADR-026 notes it;
  - `write_profile`.

  The template is chosen by `panel_base` (teacher shell or `base.html`). Supervisors get
  `request.supervisor` with its grade (one `select_related` query).
- **`blog/feeds.py`** (`Atom1Feed`), **`blog/sitemaps.py`** (plus `website` static pages),
  **`website.views.robots_txt`**.
- **Project-wide changes:**
  - `teachlog/urls.py`: `path("blog/", include("blog.urls"))`, `sitemap.xml`,
    `robots.txt`;
  - `INSTALLED_APPS`: `django.contrib.sitemaps`, `blog`;
  - `AUTHENTICATION_BACKENDS`: D23.
- **The navbar** (`public_navbar.html` + a `website_tags` filter): an item is active when
  the path equals its URL, or starts with it for URLs other than `/`. `aria-current="page"`
  is kept only for the exact match.
- **`accounts.utils.role_dashboard`:** D7.

### 7.5 Templates

- **Public:** `blog/templates/blog/base_public.html`, which extends `base.html`. It adds
  the public navbar, `blog.css`, and the `meta` block (canonical, OG, feed link,
  JSON-LD). Pages:
  - `home.html`, `listing.html` (section, category, tag, author and search share it with a
    different header);
  - `post.html`;
  - partials `_sheet.html`, `_pagination.html`, `_masthead.html`, `_share.html`,
    `_toc.html`, `_author_box.html`, `_byline.html`;
  - preview: `post.html` with a fixed «پیش‌نمایش؛ هنوز منتشر نشده» banner and
    `noindex`.
- **Authoring area:**
  - `blog/write/teacher/list.html`, `edit.html`, `profile.html`, extending
    `teacher/base.html` with `ui-*` components;
  - `blog/write/panel/list.html`, `edit.html`, `profile.html`, extending `base.html` with
    the sidebar and the supervisor components;
  - shared partials with no layout classes of their own: the editor field
    (`_editor.html`), the tag input, the reminder text, the read-only notice.
- **Sidebars:**
  - `template/teacher/partials/sidebar.html` gets «نوشته‌های من» (pen icon added to
    `icons.html`), shown when `user.blog_author` is active;
  - `template/partials/sidebar.html` gets the same item outside the role branches, so
    counselors and directors see it too.
- **Teachers page:** `website/teachers/_teacher.html` fills the commented slot (D21).

### 7.6 Static files

- **`blog/static/blog/css/blog.css`:** the public design. Tokens §4.3, mobile-first at
  576 / 768 / 992 / 1200 px, logical properties, `prefers-reduced-motion`, a print block.
  Pinking edges are a CSS `mask` with a repeating `conic-gradient`; tape and photo corners
  are pseudo-elements. No images.
- **`blog/static/blog/js/blog.js`:** enhancement only: «کپی پیوند», and the masthead's
  settle class (CSS animation, skipped with reduced motion).
- **`blog/static/blog/css/write.css` + `js/write.js`:**
  - the editor skin, with both shells' tokens through `var(--ui-…, var(--…))`
    fallbacks;
  - Trix configuration: `<p>`, h2/h3, toolbar, RTL;
  - attachment upload to `write_image_upload` with a CSRF header, refusing files over
    2 MB or of the wrong type before upload;
  - the tag input, the excerpt counter;
  - a warning before leaving with unsaved changes.
- **`static/vendor/trix/`:** `trix.umd.min.js`, `trix.css`, LICENSE, README (ADR-021).
- The admin loads Trix and `write.js` through `PostAdmin.Media`, so admin edits get the
  same editor.

### 7.7 Admin (`blog/admin.py`)

- **«صفحه وبلاگ»** (`BlogPage`): singleton, fieldsets for texts, safety texts and SEO.
- **«بخش‌ها»** (`Section`): `CategoryInline`; paper choice with a swatch; order and
  «فعال» in the list.
- **«برچسب‌ها»** (`Tag`):
  - search;
  - number of public posts (annotated);
  - a «ادغام در…» action: re-tag the posts, then deactivate the merged tag.
- **«نویسندگان وبلاگ»** (`BlogAuthor`):
  - `user` autocomplete limited to eligible roles;
  - sections as checkboxes (through `AuthorSection`, with `granted_by` set to
    `request.user`);
  - `teacher_card` autocomplete;
  - a read-only «وضعیت نویسندگی» that says whether the person can write now and, if not,
    why (inactive account, role not eligible, staff inactive, no active section).
- **«نوشته‌ها»** (`Post`):
  - **list:** title, section, category, author, status badge (with «زمان‌بندی‌شده»),
    Jalali `published_at`, featured, preview link;
  - **filters:** status, section, category (`RelatedOnlyFieldListFilter`), author,
    featured;
  - **search:** title, excerpt, author name;
  - **form:** Trix body; the review fields read-only.
  - **«بررسی و انتشار»:** a page per post with the checklist, «اکنون» or a date and time,
    and a note; plus «بازگرداندن به نویسنده» with a required note.
  - **Bulk actions:**
    - «انتشار»: an intermediate confirmation page listing the posts, with the checklist;
      only `SUBMITTED` or `ARCHIVED` posts;
    - «لغو انتشار»;
    - «ویژه / غیرویژه».
  - **Permissions:** the publish actions appear only with `publish_post`.
- **«در انتظار بررسی»**: a proxy model `PostAwaitingReview`, so it has its own admin entry.
  It lists only `SUBMITTED` posts, oldest first, with the preview and «بررسی و انتشار»
  links.

### 7.8 Tests

Files: `blog/tests/` with `test_models`, `test_content`, `test_permissions`,
`test_workflow`, `test_public`, `test_seo`, `test_write`, `test_admin`, `test_migrations`;
factories in `blog/testing.py` (`make_author`, `make_post`, …).

- **Models:**
  - the category must be in the post's section;
  - slugs: Persian kept, unique `-2`, frozen after publishing;
  - the published-needs-date constraint;
  - unique constraints;
  - the public queryset: draft, submitted, archived, future-scheduled, inactive section →
    excluded; past-scheduled → included. `timezone.now` is mocked, never the real date.
- **Sanitization:**
  - `<script>`, `onerror=`, `onclick=`, `javascript:` and `data:` links, `style`,
    `<iframe>`, `<svg onload>`, `<img src="https://evil">`, `<img src="data:…">` are all
    removed;
  - allowed markup is kept;
  - h1 → h2; heading ids are unique;
  - re-sanitized on render;
  - the admin path sanitizes too;
  - the no-JS plain-text fallback.
- **Images:** type and size validators; EXIF and GPS removed (the same test as the
  teachers page); orphan images deleted with their files after commit; another author
  uploading to my post → 404.
- **Permissions, every role from §6:** anonymous, student, teacher non-author, supervisor
  non-author, director non-author, author (S) on S, author (S) on T, author on another
  author's post (each view and transition), inactive author, deactivated user, role
  changed to student, staff inactive, staff without permissions in the admin, editor,
  superuser.
- **Workflow:**
  - every allowed transition, and every refused one (publish a draft as author, edit a
    submitted post, double submit);
  - the privacy acknowledgement is required;
  - the checklist is required to publish;
  - returning needs a note;
  - the stamps are set;
  - scheduled publishing becomes public exactly at `published_at` (mocked clock).
- **Public visibility:** a draft, submitted, scheduled or archived post is a 404 on its URL
  and missing from home, section, category, tag, author, search, feeds and the sitemap.
  The preview works only for the author and editors.
- **SEO:** title, description, canonical, `og:*`, JSON-LD present and escaped; the feed
  lists only public posts; the sitemap contains public URLs only; robots.txt;
  `noindex` on preview and search; the CSP header on blog pages only.
- **Search:** ی/ک and digit normalisation; ZWNJ variants match; an empty or one-character
  query.
- **Menu migration** forward and reverse, including edited rows.
- **Query counts** locked for home, section, category, tag, author, search, the post and
  the teachers page (6), each checked with 1 and with many posts and tags; the authoring
  list; and existing panel pages unchanged with the D23 backend.
- **Privacy markers:** fill a linked user's and staff member's private fields with marker
  values and assert none reaches any blog page (the teachers page test, reused).

The full suite runs on PostgreSQL against a baseline on `main`, plus the blog app on
SQLite.

### 7.9 Docs (on the branch)

- `docs/apps/blog.md` (new);
- updates to `docs/apps/website.md` (menu, navbar, robots, sitemap, teachers link),
  `docs/apps/accounts.md` (auth backend, login landing, finding 18), `docs/database.md`,
  `docs/database-mermaid.md`;
- ADR-026, ADR-025 consequence;
- `docs/changelog.md`;
- report `docs/plans/2026-10-blog.md`, written per the workflow, with screenshots at
  1280 and 375 px of the blog home, a post, a category page and the authoring screen
  (both shells).

---

## 8. What I will NOT touch

- **School data:** no app reads or writes it for the blog (`school`, `teaching`,
  `attendance`, `analytics`, `scheduling`, `academic_calendar`, `director`, `supervisor`
  logic). The only links are `BlogAuthor.user` and `BlogAuthor.teacher_card`.
- **Existing website pages:** only the navbar's active state, the teachers card slot
  (D21) and the menu migration change. No other page's markup or CSS.
- **No existing data rows** change except the two menu rows D20 names, and only when they
  are still at `#`.
- **The production database, the local Docker database (no `migrate` without asking),
  deploys,** and anything on `main` except this plan.
- **No CDN,** no third-party scripts or embeds, no analytics or trackers.

---

## 9. Open questions and manual steps (for the report)

- **At deploy:** `migrate` (`blog 0001–0002`, `website 0014`) and `collectstatic`;
  `pip install` (nh3).
- **Admin setup:**
  - create the categories;
  - create a «ویراستار وبلاگ» group with the blog permissions plus `publish_post`;
  - add the authors and their sections;
  - fill «صفحه وبلاگ».
- **Consent:** the school should decide how parents' photo consent is collected and kept.
  The blog only reminds and records the acknowledgement.
- **robots.txt and sitemap.xml** become reachable at the site root. Check that the CDN and
  nginx don't already serve a robots file.
