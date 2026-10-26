# Blog App Documentation

The `blog` app is the school's blog («وبلاگ نسل قلم»): posts by teachers, the counselor
and other staff, in sections such as «پرورشی» and «مشاوره». Who may write is granted per
person and per section by the website admin; editors review and publish in the admin.
The rules are in ADR-026; the plan is `docs/plans/2026-10-blog-plan.md`.

**State (October 2026):** being built on `feature/blog` in three phases.

| Phase | Contents | State |
|---|---|---|
| 1. Foundations | models, migrations, seed; body pipeline and sanitizer; permissions; workflow services; admin (editor, review, bulk actions); Trix vendored | done, admin only; nothing public |
| 2. Public blog | public pages, SEO, feeds, sitemap, robots, CSP, menu | not yet |
| 3. Authoring area | «نوشته‌های من» in the panels, sidebar item, login landing | not yet |

Until Phase 3, editors write posts in the admin themselves.

---

## 1. Models (`blog/models/`)

| Model | Purpose |
|---|---|
| `BlogPage` | Singleton (`pk=1`, `website.models.base.SingletonModel`): the blog's name and intro, the three safety texts (D16) and SEO |
| `Section` | «پرورشی»، «مشاوره»: title, Unicode slug, one-line description, paper colour (a fixed choice, `Paper`), order, `is_active` |
| `Category` | Optional second level inside a section; slug unique per section |
| `Tag` | Free label; one row per spelling-independent `key` (`blog.text.search_key`) |
| `BlogAuthor` | One per person: the `user` (`PROTECT`), public byline (`display_name`, `slug`, `bio`, `photo`, optional `teacher_card`), `show_profile`, `is_active` («اجازه نوشتن») |
| `AuthorSection` | A section an author may write in, with `granted_by` and `granted_at`; unique per (author, section) |
| `Post` | The post; see below |
| `PostImage` | An image inside a post's body, uploaded from the editor (re-encoded, at most 1600 px, `width` / `height` stored) |
| `PostAwaitingReview` | Proxy of `Post`: the admin's «در انتظار بررسی» queue |

### Post

| Field | Notes |
|---|---|
| `section`, `category` | Both `PROTECT`. The category must be in the section, and is required when the section has active categories (`Post.clean`) |
| `author` | `BlogAuthor`, `PROTECT` |
| `title` (120), `slug` (unique, Unicode) | The slug is generated from the title on first save and does not follow later title changes. Once published it should not change; only the admin can edit it, with a warning |
| `excerpt` (300) | Blank → `summary`, the first ~200 characters of the text |
| `body` | Sanitized HTML (§2) |
| `cover`, `cover_alt` | Re-encoded, at most 1600 px; the alt text is required with a cover |
| `tags` | At most `BLOG_MAX_TAGS_PER_POST` |
| `status` | `draft` «پیش‌نویس», `submitted` «در انتظار بررسی», `published` «منتشرشده», `archived` «بایگانی». A published post with a future `published_at` shows as «زمان‌بندی‌شده» |
| `published_at` | Set when published; kept after unpublishing. Database constraint: a published post has one |
| `submitted_at`, `privacy_ack_at`, `reviewed_by`, `reviewed_at`, `review_note` | Stamped by the services |
| `body_text`, `search_text`, `toc`, `reading_minutes` | Derived on every save (§2) |
| `content_updated_at` | Set when the title, body or excerpt change after publication |
| `meta_title`, `meta_description` | Blank → title and summary |

Indexes: `(status, published_at)`, `(section, status, published_at)`, `(author, status)`.

**The public rule** is one queryset method, `Post.objects.public()`: status published,
`published_at <= now`, section active. There is no scheduler: a scheduled post becomes
public when its time comes. An inactive category or tag doesn't hide a post.

**Files:** every image field (`BlogPage.og_image`, `BlogAuthor.photo`, `Post.cover`,
`PostImage.image`) is removed from storage after commit when replaced or deleted
(`blog/signals.py`, reusing `website.signals`). `Post.save()` also deletes inline images no
longer in the body, once they are a day old (younger ones may still be in an editor that
hasn't saved yet).

## 2. The body: editor and sanitizer (`blog/content.py`, `blog/text.py`)

The editor is **Trix 2.1.19**, vendored in `static/vendor/trix/` (version, source and
SHA-256 of each file in its README, checked by `blog.tests.test_assets`).
`blog/js/editor.js` is loaded before Trix, configures it (Persian toolbar, «عنوان» = `h2`,
«زیرعنوان» = `h3`), and mounts it over the field's own textarea. Without JavaScript the
textarea is the editor: text without tags becomes paragraphs at blank lines.

`content.prepare(html)` runs in `Post.save()`, whatever path saves:

1. **Reshape** Trix's markup: its block `<div>`s become `<p>`, split at blank lines (two
   `<br>`); `h1` → `h2`, `h4`–`h6` → `h3`, `b`/`i`/`s` → `strong`/`em`/`del`; each image
   attachment becomes `<figure><img src alt width height><figcaption>`, with the caption
   also as `alt`; figures are lifted out of paragraphs; empty blocks are dropped.
2. **Sanitize** with `nh3` (`content.sanitize`), the allow-list of ADR-026:
   tags `p h2 h3 strong em del a ul ol li blockquote br hr figure figcaption img pre`;
   `a[href]` (http, https, mailto, relative, `#`; `rel="noopener noreferrer"` added);
   `img[src alt width height]` only for `src` under `MEDIA_URL` + `blog/`; `h2`/`h3` `id`.
   `script`, `style`, `iframe`, `object`, `svg`, `math`… are removed with their content.
   Links whose address is refused are left as text.
3. **Derive**: heading ids from the text (Unicode, de-duplicated) and the table of contents
   (`toc`: level, id, title); `body_text` (one line per block); `reading_minutes`
   (`BLOG_WORDS_PER_MINUTE`, at least 1); `search_text`.

`sanitize` is idempotent and is run again when a body is shown (Phase 2). `to_editor` turns
a stored body back into Trix's attachment markup, so captions survive editing.

**Persian text** (`blog/text.py`): `normalize` fixes ي/ى→ی, ك→ک, tatweel, repeated
spaces and stray ZWNJ, and keeps ZWNJ, ئ and digits as typed (titles, names, tags).
`search_key` folds spellings for matching: also ئ→ی, ۀ→ه, أ/إ/آ→ا, diacritics removed,
digits to ASCII, lower case, and **no ZWNJ and no spaces**, so «کتاب‌خوانی»،
«کتاب خوانی» and «کتابخوانی» are the same key. Tags are unique on that key.

**What Trix can't do** (found in the Phase 1 spike):
- Enter adds a line break inside the block, never a new block; the server makes the
  paragraphs (blank line = new paragraph).
- A numbered list pasted from Word arrives as lines starting «1.», «2.»; tables arrive as
  text; images pasted from Word (local files) are dropped.

## 3. Who can do what (`blog/permissions.py`)

| Function | Meaning |
|---|---|
| `author_for(user)` | The user's `BlogAuthor` (one query with the user and staff record, cached on the user) |
| `write_block_reason(author)` | Why they can't write now, in Persian, or "" (the admin's «وضعیت نویسندگی») |
| `can_write(user)` | Active author, active account, eligible role, active staff record (if any) |
| `writable_sections(user)` | Active sections granted to them; none when they can't write |
| `can_write_in(user, section)` | |
| `author_posts(user)` | Their own posts: where every authoring view starts (Phase 3) |
| `can_edit_as_author(user, post)` | Own draft in a section still granted |
| `is_editor(user)` / `can_publish(user)` | Active staff with `blog.publish_post` |
| `can_preview(user, post)` | The post's author (while they can write) and editors |

`BLOG_AUTHOR_ROLES` (setting) is read only here. The admin may only pick users of those
roles for a new author; an author whose role later changes can still be opened and
deactivated, but can't write.

## 4. Workflow (`blog/services.py`)

Every transition locks the post (`select_for_update`), checks the state it starts from and
who asks, and raises `TransitionError` (Persian message) or `PermissionDenied`.

| Service | From → to | Who | Needs |
|---|---|---|---|
| `create_draft` | → draft | author, in a granted section | |
| `submit` | draft → submitted | the author | privacy acknowledgement, title and text, valid category |
| `withdraw` | submitted → draft | the author | |
| `archive` | draft → archived | the author | (the soft delete; nothing is removed) |
| `reopen` | archived → draft | the author or an editor | |
| `publish` | draft / submitted / archived → published | editor | every checklist line ticked; `at` (default now, future = scheduled) |
| `unpublish` | published → archived | editor | (also unfeatures) |
| `return_to_author` | submitted / published / archived → draft | editor | a note |
| `set_featured` | | editor | only published posts are featured |
| `sync_tags`, `parse_tag_names` | | | existing tags reused in any spelling; at most 5 |
| `merge_tags` | | admin action | re-tags posts, deactivates the merged tags |
| `add_image` | | the author of a draft, or staff with `change_post` | jpg/png/webp, 2 MB; re-encoded |

Publishing a **draft** is possible only from the post's own review page, which warns that
the author never sent it: editors write in the admin until the authoring area exists. The
bulk action publishes only submitted and archived posts.

## 5. Admin (`blog/admin.py`)

| Entry | Contents |
|---|---|
| «صفحه وبلاگ» | Singleton: name and intro; the privacy reminder, acknowledgement and review checklist (one line per item); SEO and the default share image |
| «بخش‌ها» | Paper colour (swatch in the list), order, active, published posts count; categories inline |
| «برچسب‌ها» | Search in any spelling; published posts count; action «ادغام در برچسب دیگر…» (confirmation page) |
| «نویسندگان وبلاگ» | User (autocomplete, eligible roles), «اجازه نوشتن», sections as checkboxes (each grant records who and when, shown in «سابقه اجازه‌ها»), «وضعیت نویسندگی» with the reason when they can't write, public byline |
| «نوشته‌ها» | List with status badge («زمان‌بندی‌شده» too), filters (status, section, category, author, featured), search. Form with the Trix editor (images after the first save), tags autocomplete, cover. The status is read-only |
| «بررسی و انتشار» | `admin/blog/post/<id>/review/`, a link on the change form for editors: the checklist, «اکنون» or a Jalali date and time (`۱۴۰۵/۰۸/۱۲ ۱۰:۳۰`, Tehran time), «بازگرداندن به نویسنده» with a required note, «خارج کردن از انتشار» |
| Bulk actions | «انتشار…» (confirmation page with the checklist), «خارج کردن از انتشار», «ویژه کردن», «برداشتن از ویژه‌ها»; shown only to editors |
| «در انتظار بررسی» | Submitted posts, oldest first, with «ویرایش» and «بررسی و انتشار» links; needs `view_post` or `change_post` |
| Image upload | `admin/blog/post/<id>/upload-image/` (POST, JSON `{url, width, height}` or `{error}`): the editor's one JSON endpoint; needs `change_post` |

Posts are never deleted by editors (superusers only, for spam or test rows); archive instead.

### Setting up editors and authors

1. Create a group «ویراستار وبلاگ» with every `blog` permission, including «انتشار،
   زمان‌بندی، لغو انتشار و بازگرداندن نوشته‌ها» (`publish_post`), and add the editors
   (staff users).
2. Create the categories under «بخش‌ها» (suggestions in the plan, D15).
3. Add each author under «نویسندگان وبلاگ» and tick their sections.
4. Check the texts on «صفحه وبلاگ».

## 6. Settings (`teachlog/config/settings/base.py`)

| Setting | Value | Read in |
|---|---|---|
| `BLOG_AUTHOR_ROLES` | teacher, counselor, supervisor, director, admin | `blog.permissions` (policy, D3) |
| `BLOG_WORDS_PER_MINUTE` | 180 | `blog.text.reading_minutes` |
| `BLOG_PAGE_SIZE` | 9 | public lists (Phase 2) |
| `BLOG_MAX_TAGS_PER_POST` | 5 | `blog.services.sync_tags`, the admin form |
| `BLOG_FEED_ITEMS` | 20 | feeds (Phase 2) |
| `BLOG_TOC_MIN_HEADINGS` | 3 | the post page (Phase 2) |

## 7. Migrations

| Migration | Contents | Reverse |
|---|---|---|
| `blog.0001_initial` | All tables, constraints, indexes, the `publish_post` permission | drops them |
| `blog.0002_seed` | The «صفحه وبلاگ» row; sections «پرورشی» (tomato) and «مشاوره» (sky). Create only | removes the seeded sections no post uses |

## 8. Tests (`blog/tests/`)

`test_content` (sanitizer, Trix reshaping, round trip, Persian text), `test_models`,
`test_permissions` (every role), `test_workflow`, `test_admin`, `test_migrations`,
`test_assets` (no external script or stylesheet in any blog template or stylesheet;
vendored Trix matches its README). Factories in `blog/testing.py`.
