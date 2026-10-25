# Plan: public «درباره ما» page, and removing «کلاس ها» from the menu

Status: **approved 2026-10-25** with the changes below. Implementation goes on
`feature/about-page`, created from `main` after this update.

## Approval (2026-10-25)

Approved:
- D1, D2, D4, D6, D7, D8, D10 and D11, as recommended.
- D5: yes, recorded as **ADR-025** (D12).

Changes to the plan (they supersede the text below where they differ):

1. **D3, privacy.** A staff member's internal avatar is never published
   automatically:
   - a person's photo comes **only** from `photo_override`, which the admin
     uploads on purpose;
   - without it, the card shows the initial;
   - the name may still fall back to the linked user.

   The admin help text says photos here are public. Tests: a linked staff
   member with an avatar but no override shows the initial.
2. **«همکاران ما» is for leadership and office staff only, not teachers.**
   The dedicated teachers page is the next task, and the section's admin
   help text says so. Open question 1 is dropped: «معلمان» does **not**
   point to `/about/#team`, and its row is left untouched.
3. **D9, one shared action colour instead of a third copy:**
   - `index.css` gets `--lp-action` and `--lp-action-hover`, as token
     definitions only; no existing landing rule changes;
   - `about.css` uses them;
   - `contact.css`'s `--ct-action` and `--ct-action-hover` reference them.

   Screenshots before and after verify that the landing and contact pages
   look unchanged. Fixing the landing page's button contrast stays a
   separate follow-up.

Skills: both were loaded with the Skill tool before planning.
- **`teachlog-workflow`**: this plan follows its read → plan → approve order.
  Only this file is published to `main`.
- **`frontend-design`**: it shaped §3. I wrote a token system (colour, type,
  layout, principles) and checked it against the skill's list of "generic
  defaults". I revised the parts that matched, and I spend the boldness in one
  place, the pen line. Those revisions are listed in §3.3.

Read before planning: `CLAUDE.md`, `.claude/CLAUDE.md`, `docs/apps/website.md`,
ADR-011, ADR-015, ADR-021 and ADR-024 (the newest; there is no ADR-025 yet),
`docs/changelog.md`, `template/base.html`, and all of `website/`:
- models, admin, views, signals, validators, context processor, template tags;
- templates, CSS and JS;
- migrations 0001–0005;
- `tests.py` and `test_contact.py`.

Also the contact-page plan and report, `school/models/branch.py`,
`staff/models/staff.py`, `accounts.User.avatar_url` and `core/testing.py`.

I took screenshots of the current landing and contact pages at 1280px and
375px. They ran against a **scratch SQLite copy**, through a throw-away
settings module in the session scratchpad, with two sample branches. The
local Docker database was not touched.

---

## 1. Findings, risks and surprises

1. **The patterns to reuse already exist and fit:**
   - `SingletonModel` + `OrderedItem`;
   - `_image_field` / `_alt_field` / `_link_field` / `_static_fallback_field`;
   - `image_url()` with a static fallback;
   - `IMAGE_VALIDATORS`, `validate_link`;
   - the `MODELS_WITH_IMAGES` cleanup signals;
   - `PreviewInlineMixin`, `SingletonAdmin`;
   - the `Prefetch(..., to_attr="active_…")` loading of only the enabled
     sections (`views.website`).

   The «درباره ما» page reuses all of them. It adds no new base classes.
2. **Branches are already public through `ContactLocation`.** Each one is
   linked to a `school.Branch`, falls back to the branch's name and address,
   and inactive branches are hidden. The about page reads the **same rows,
   with the same filter**, so an address is never stored twice. An admin who
   hides a branch on the contact page hides it here too (D6).
3. **Content I don't know must not be invented on a public page.** Examples:
   - founding year, milestones, student/teacher counts;
   - the director's name and words;
   - photos of real children.

   A parent reads all of these as facts. Seeding plausible numbers would
   publish fiction on deploy day. So the seed creates such rows as
   **inactive examples**, or leaves them empty, and their sections stay
   hidden until the school fills them in (D4). The texts that are seeded
   active are general statements of intent, written so that they claim no
   specific fact.
4. **Contrast:**
   - The brand orange still fails AA under white text (`--lp-brand` 2.7:1).
     The page uses the contact page's darker action step `#b4501c`: 5.1:1 on
     white, 4.5:1 on the cream panel.
   - `--lp-text #666` on peach (`#f5dac8`) is 4.3:1, below AA. The page never
     puts body text on peach.
   - The new ink blue `#1f4f8f` is 7.3:1 on the cream panel and 6.1:1 on
     peach.
5. **`--ct-action` lives in `contact.css`.** The about page won't load
   `contact.css`: it's 17 KB of form and phone-bar rules. Options:
   - copy the value into `about.css`;
   - hoist the token into `index.css`, which touches the landing page's file.

   Recommendation and alternative in D9.
6. **The navbar highlights the current item with `item.url == request.path`.**
   A «درباره ما» row pointing at `/about/` highlights on the new page with no
   template change. The footer rows are plain links, so they need no change
   either.
7. **The seed's «کلاس ها» row is titled with a plain space** (`"کلاس ها"`,
   not a ZWNJ). The migration matches that exact title and `url == "#"`, so
   a row an admin has renamed or linked is left alone. «معلمان» is also still
   `#`; it's out of scope here (§7, open question 1).
8. **Scroll-driven CSS animations** (`animation-timeline: view()`) are
   supported in Chrome/Edge and Safari 26, but not yet in Firefox. The one
   motion on the page (the pen line drawing itself, §3) is therefore wrapped
   in `@supports` **and** `prefers-reduced-motion: no-preference`. Without
   either, the line is simply drawn. No JS is needed, so there's no
   `about.js` (D10). On phones the scroller is `.app-shell`, and `view()`
   follows the nearest scroller, so the animation works there too.
9. **Gallery uploads are heavy.** Each image is ≤ 2 MB (validator), and
   several of them load on one page. Every image below the hero gets
   `loading="lazy"`, `decoding="async"` and explicit width/height (no
   layout shift). Only the hero image loads eagerly.
10. **No discrepancies found** between `docs/apps/website.md` and the code
    for the parts this task touches.

---

## 2. Decisions to confirm

**D1. Page structure.** Recommended: these ten blocks, in this order. Each
one has its own on/off switch in the admin, and a section with no active
items is not rendered (the landing/contact rule).

| # | Section | Content (all admin-edited) | Why here |
|---|---|---|---|
| 1 | **Hero** (always on) | one-sentence story as the **h1**; short paragraph; a photo in an arch frame; one button «هماهنگی بازدید از مدرسه» → `/contact/` | who we are, in one breath; the main action is offered at once |
| 2 | **داستان ما** | story text (multi-paragraph) + **milestones timeline** (year, title, text) drawn as a pen line | history builds trust |
| 3 | **سخن مدیر** | quote, name, role, optional photo | a human voice right after the history |
| 4 | **باورهای ما** | mission and vision (title + text each), then a list of **values** (optional emoji, title, one line) | what the school stands for |
| 5 | **در نسل قلم، بچه‌ها…** («what makes us different») | intro + **highlights** (image, title, text): teaching approach, robotics, art, sport | concrete, visual proof |
| 6 | **نسل قلم در چند عدد** | **facts**: value as typed («۱۲»، «۴۰۰+») and label | short, admin-entered, never computed (D5) |
| 7 | **همکاران ما** | **people**: optional link to a `Staff` row, name, role, photo, one-line bio | faces of the people parents will meet |
| 8 | **گوشه‌ای از مدرسه** | **photos**: image, alt, caption | real photos, once uploaded |
| 9 | **شعبه‌ها** | title + short text, then each public branch's name and address, linking to `/contact/` for phones and maps | where; no duplicated addresses (D6) |
| 10 | **دعوت پایانی** (closing CTA) | title, text, primary button → `/contact/`, optional second button (empty now; registration later) | the page's goal |

Alternatives considered and dropped:
- a separate «چرا ما» section: the landing page already has one, and
  section 5 covers it with the about page's own content;
- an FAQ: the contact page has the teaser, and FAQ is its own future page.

**D2. Data model.** Recommended: a new `AboutPage` singleton with six
`OrderedItem` inlines, mirroring `LandingPage` / `ContactPage`. Full fields
are in §4.1. The inlines are:
- `AboutMilestone`
- `AboutValue`
- `AboutHighlight`
- `AboutFact`
- `AboutPerson`
- `AboutPhoto`

The alternative, one generic "content block" model with a type field, makes
the admin harder to read for office staff, and the template would branch on
types.

**D3. People («همکاران ما»).** Recommended: `AboutPerson.staff` is an
optional FK to **`staff.Staff`** (any employee: director, deputies, office,
teachers; `on_delete=SET_NULL`, admin autocomplete). The name and photo fall
back to the linked user's full name and `avatar_url`, exactly like
`LandingTeacher`. `name_override` and `photo_override` win when filled in.
**`role` is always typed by the admin** (e.g. «مدیر مدرسه»), because nothing in
the data says who leads what. A person needs a staff link or a name (`clean()`).

Only people the admin adds appear; nothing is listed automatically. A person
whose linked `Staff` is inactive is hidden, as locations of inactive branches
are on the contact page.

Without a photo, the card shows the person's initial in a circle: the same
initial logic as `User.initials`, or the first letter of the name override.
There's no stock silhouette.

**D4. Seed data (create-only data migration `0007_seed_about`).**
Recommended:
- the `AboutPage` row: model defaults hold all section titles and texts;
- **4 values**, active. They are general statements of intent, not facts.
- **4 highlights**, active. Their texts restate what the landing page already
  publishes (robotics and coding, art, sports halls, smart classes). Their
  images are the bundled ones, via `static_fallback`, until real photos are
  uploaded.
- **3 milestones and 4 facts as inactive examples.** Their placeholder years
  and numbers are obviously placeholders («۱۳۰۰»، «—»), so the admin can see
  the format, edit the row and tick «فعال».
- **No people and no photos.** Those sections stay hidden until real ones are
  added.
- `show_quote` defaults to **off**, and the quote text is an example, until
  the director approves real words.

Rows are only ever created (`get_or_create`, and only into empty lists), so
re-running never duplicates. The reverse deletes the about rows only. The
migration depends on the latest `staff` migration, for the FK.

The alternative is to seed everything active with invented content. I
recommend against it: that's what finding 3 warns about.

**D5. Headline numbers.** Recommended: the value is a free **text** field, not
an integer. That way «۴۰۰+»، «۱۲ سال»، «۲» all work, and the digits are shown
as typed. **Never computed** from enrolments, staff or classes. This is your
brief, and it also keeps internal data off the public site. I suggest
recording that as a short **ADR-025, "Public website content is editorial,
never computed from school data"**, so the blog and registration pages
follow it too. Say no if you'd rather keep it to `docs/apps/website.md`.

**D6. Branches section.** Recommended: read **`ContactLocation`**, with the
contact page's filter (active rows; branch null or active), `select_related(
"branch")`, ordered by `order`. Show `display_title` and `display_address`
(line breaks kept), plus «مسیریابی و تلفن» linking to `/contact/`. Maps,
phones and hours stay on the contact page. That's one query, and it's the
single place addresses are edited.

The alternative is to read `school.Branch` directly. It's simpler, but it
ignores the contact page's overrides and hiding, so the two pages could
disagree.

**D7. «درباره ما» menu and footer rows → `/about/`.** As requested: a
reversible data migration (`0008_about_menu`) that updates
`NavMenuItem` and `FooterLink` rows with `title == «درباره ما»` **and**
`url == "#"`. The reverse resets only rows with that title still at
`/about/`. This is the same shape as `0005_link_contact_menu`.

**D8. «کلاس ها» nav item.** Recommended: **deactivate** (`is_active=False`)
rather than delete, as you lean. Only the `NavMenuItem` with `title == «کلاس
ها»`, `url == "#"` and `is_active=True` changes. It stays in «تنظیمات سایت →
آیتم‌های منو», where one tick brings it back. The reverse re-activates only
a row with that title still at `#` and inactive. Caveat: if an admin had
deactivated it by hand before this migration, a rollback would turn it back
on. That's harmless (a `#` link), and I'll document it. Same migration
file as D7, as a second `RunPython` operation, so both reverse together.
There is no «کلاس ها» footer row (checked against the seed), so the footer
is unaffected.

**D9. Shared action colour.** Recommended: `about.css` defines `--ab-action:
#b4501c` (and its hover), with a comment pointing at `--ct-action`. This
doesn't touch `index.css` or `contact.css`. Follow-up for the report:
hoist one `--lp-action` into `index.css` when the landing page's buttons
are fixed for AA, and drop both copies. The alternative is to hoist it now,
touching two existing pages' CSS in this task.

**D10. JavaScript.** Recommended: **no `about.js`.** The only motion is
CSS, a scroll-driven draw that's progressive and off under reduced motion.
The gallery is a native scroll-snap strip on phones and a grid on desktop.
Nothing needs a script. Every section is complete without JS by
construction.

**D11. URL and view.** `/about/`, name `website:about`, `require_safe`
(GET/HEAD; there is nothing to POST). The view stays thin. A helper
`_load_about_page()` prefetches only the enabled sections' active items
into `active_*` attributes (one query each), plus one query for
locations. The query count is the same whether a section has 0 or 50
items, and it's locked by a test.

**D12. ADR.** Only ADR-025 from D5, if you agree. Nothing else here changes
a rule.

---

## 3. Design

### 3.1 Aesthetic direction: «نسل قلم», the pen line

The school is called *the generation of the pen*. Every child here learns
to write with a blue ballpoint. That's where the page's one memorable
element comes from:

**The story is told along a single hand-drawn line of blue ink.** It
starts as a small loop, like a pen touching paper, beside the «داستان ما»
heading. It runs down the inline-start (right) edge of the story, with a
slight wobble, through each milestone. It ends in a full dot under the
last one. Each milestone's year sits on the line as an ink dot, with the
year in heavy ink-blue numerals.

On browsers that support it, and only without reduced motion, the line
**draws itself as the parent scrolls through the story**, and each dot
fills when the line reaches it. That's one orchestrated moment, tied to
reading the history. Without support, the line is already drawn.

Everything else stays in the site's existing language and is deliberately
quiet:
- the doodle background;
- cream and glass panels with the landing page's radii and shadows;
- Vazirmatn;
- the dark action orange on buttons.

The second shape choice is the hero photo, framed in an **arch**, the
rounded top of a doorway. The arch says "come in", which is the page's
invitation to visit. It's used only once.

### 3.2 Tokens (extend `--lp-*`, don't compete)

New tokens in `about.css` only:

| Token | Value | Role |
|---|---|---|
| `--ab-ink` | `#1f4f8f` | the pen line, milestone dots and years, the quote's «» mark: nothing else is blue |
| `--ab-ink-track` | `rgba(31, 79, 143, 0.14)` | the undrawn line under the animated stroke |
| `--ab-action` | `#b4501c` | buttons and orange links (= `--ct-action`, D9) |
| `--ab-action-hover` | `#9a4416` | hover |
| `--ab-paper` | `#fffaf6` | the quote and the closing CTA panel (= contact's notebook paper) |

Existing tokens used as they are:
- `--lp-cream`, `--lp-glass` for panels;
- `--lp-peach` for image backgrounds, never under text;
- `--lp-heading` for h2s, `--lp-ink`;
- `--lp-yellow` for the value emoji disc, the same as the landing page's
  learning items;
- the radii, shadows and `--lp-touch`.

**Type: Vazirmatn only** (vendored variable font, weights 100–900). The
contrast comes from weight and size, not from a second family:

| Role | Size | Weight | Line height |
|---|---|---|---|
| h1 (hero sentence) | `clamp(1.75rem, 1.1rem + 2.8vw, 3rem)` | 800 | 1.5 |
| h2 sections | `clamp(1.35rem, 1.15rem + 0.8vw, 1.7rem)` | 800 | 1.5 |
| milestone year | 1.25rem | 900, ink blue | — |
| director's quote | `clamp(1.2rem, 1rem + 0.9vw, 1.55rem)` | **400** (a calm voice among heavy headings) | 2.0 |
| fact value | `clamp(1.8rem, 1.4rem + 1.5vw, 2.4rem)` | 900, `--lp-heading` | — |
| body | 1rem | 400–500 | 1.95 |
| captions, roles | 0.875rem | — | — never smaller |

Prose has `max-width: 38rem`, about 70 characters. Text is start-aligned
(right) throughout. The only centred things are the hero on phones (as on
the landing and contact pages) and the closing CTA.

**Principles**
1. The ink line is the only decoration that "performs"; everything else is
   content.
2. No hard-coded copy, no invented facts; empty means hidden.
3. One h1, landmarks (`<main>` is the page's content block, each section is
   `<section aria-labelledby>`), real lists, `<blockquote>` + `<figcaption>`
   for the quote, `<ol>` for the timeline (a true sequence), `<dl>` for
   facts.
4. Logical properties only (`inline-start`, `margin-block`, …); the ink
   line sits on the inline-start side, so it mirrors correctly.

### 3.3 What I changed after checking against the generic defaults

- **First sketch:** a band of four huge numbers right under the hero, with
  small labels. That's the default "stat hero". **Now** the numbers are
  section 6, set modestly in a `<dl>` row inside a glass panel. They are
  hidden until the school enters real ones.
- **First sketch:** values as three identical rounded icon cards with
  shadows (the "SaaS card kit"). **Now** values are a plain two-column list
  with the landing page's small yellow disc for an optional emoji. There
  are no card boxes.
- **First sketch:** a fade-and-slide-up on every section. **Now** there's
  one scroll-tied moment (the line drawing) and nothing else moves by
  itself.
- **First sketch:** the hero image in the landing page's blob, a third copy
  of the same hero after landing and contact. **Now** it's an arch, so the
  page belongs to the family without repeating it.
- No eyebrow labels above headings, no `·`-joined meta strings, no `→`
  glued to button text. Numbered markers appear only where the content is a
  sequence: the timeline's years.

### 3.4 Wireframe: desktop (1280px)

```
┌ public navbar (shared) ── «درباره ما» highlighted ───────────────────────┐
├──────────────────────────────────────────────────────────────────────────┤
│ HERO  (cream panel, landing radius)                                       │
│                                                         ╭───────────╮     │
│  مدرسه‌ای که بچه‌ها در آن با شوق یاد می‌گیرند،            │           │     │
│  و خانواده‌ها با خیال آسوده همراهشان هستند.  (h1, 2 lines) │  photo in  │     │
│  short paragraph (≤ 38rem)                               │  the arch  │     │
│  [ هماهنگی بازدید از مدرسه ]                              │           │     │
│                                                         └───────────┘     │
├──────────────────────────────────────────────────────────────────────────┤
│ داستان ما  ୧ ← ink loop starts here                     (glass panel)    │
│   story paragraphs (≤ 38rem) ┆                                            │
│                              ┆                                            │
│                       ● ۱۳۹۲  تأسیس مدرسه                                │
│                       ┆       one or two lines of text                    │
│                       ● ۱۳۹۷  افتتاح شعبه دوم                             │
│                       ┆                                                   │
│                       ● ۱۴۰۲  کارگاه رباتیک                               │
│                       ●  (end dot)                                        │
├──────────────────────────────────────────────────────────────────────────┤
│ سخن مدیر   (paper panel)                                                  │
│   «  quote text, calm weight, up to ~4 lines                  ( photo )   │
│      — name, role                                                         │
├──────────────────────────────────────────────────────────────────────────┤
│ باورهای ما                                                                │
│   مأموریت ما                       چشم‌انداز                              │
│   paragraph                        paragraph                              │
│   (●) امنیت و آرامش — one line     (●) یادگیری با تجربه — one line          │
│   (●) احترام به هر کودک — …         (●) همراهی با خانواده — …              │
├──────────────────────────────────────────────────────────────────────────┤
│ در نسل قلم، بچه‌ها…    intro line                                        │
│   ┌ image ┐  ┌ image ┐  ┌ image ┐  ┌ image ┐   (4 columns ≥ 1200,        │
│   title      title      title      title         2 at 768–1199)           │
│   text       text       text       text                                   │
├──────────────────────────────────────────────────────────────────────────┤
│ نسل قلم در چند عدد                                                        │
│     ۱۲              ۴۰۰+             ۳۵               ۲                     │
│   سال تجربه         دانش‌آموز          معلم             شعبه                  │
├──────────────────────────────────────────────────────────────────────────┤
│ همکاران ما                                                                │
│   (photo)  (photo)  (photo)  (photo)    name / role / one line            │
├──────────────────────────────────────────────────────────────────────────┤
│ گوشه‌ای از مدرسه                                                          │
│   ┌────────────┐┌─────┐┌─────┐                                            │
│   │  first 2×2 │└─────┘└─────┘   caption under each (figcaption)           │
│   │            │┌─────┐┌─────┐                                            │
│   └────────────┘└─────┘└─────┘                                            │
├──────────────────────────────────────────────────────────────────────────┤
│ شعبه‌ها   short text                                                      │
│   شعبه مرکزی (عمار)            شعبه ۲ (منصور افشار)                          │
│   address                      address                                    │
│   [مسیریابی و تلفن]             [مسیریابی و تلفن]   → /contact/            │
├──────────────────────────────────────────────────────────────────────────┤
│ CLOSING CTA (paper panel, centred)                                       │
│   از نزدیک با مدرسه آشنا شوید                                            │
│   one sentence                                                            │
│   [ تماس با مدرسه ]  ( [ ثبت‌نام ] later, when its URL is set )            │
├ footer (shared; «درباره ما» → /about/) ──────────────────────────────────┤
```

### 3.5 Wireframe: phone (375px)

```
┌ logo               ☰ ┐
│ HERO (centred)        │
│    ╭─────────╮        │  arch, max 220px wide
│    │  photo  │        │
│    └─────────┘        │
│  h1 (3–4 lines)       │
│  paragraph            │
│ [هماهنگی بازدید…]     │  full width
├───────────────────────┤
│ داستان ما           ୧ │
│ story text          ┆ │  ink line on the right edge,
│ ۱۳۹۲ تأسیس…         ● │  milestones hang off it
│ text                ┆ │
│ ۱۳۹۷ …              ● │
├───────────────────────┤
│ «  quote              │
│ — name, role (photo)  │
├───────────────────────┤
│ mission / vision      │  stacked
│ values (one column)   │
├───────────────────────┤
│ highlights, 1 column  │  image above text
├───────────────────────┤
│  ۱۲      ۴۰۰+         │  facts 2 × 2
│  ۳۵      ۲            │
├───────────────────────┤
│ people, 2 per row     │
├───────────────────────┤
│ gallery: ◀ swipe ▶    │  scroll-snap strip inside its own box
│ (no page overflow)    │  (overflow-x on the strip only)
├───────────────────────┤
│ branches, stacked     │
├───────────────────────┤
│ CTA, full-width btn   │
└ footer ───────────────┘
```

Breakpoints are the site's (576 / 768 / 992 / 1200px), mobile-first. Every
grid child has `min-width: 0`, and long words get `overflow-wrap: anywhere`.
Overflow is checked with `scrollWidth` on `html`, `body` and `.app-shell`.

---

## 4. Implementation outline

### 4.1 Models (`website/models/about.py`, exported from `models/__init__.py`)

`AboutPage(SingletonModel)`:
- **switches:** `show_story`, `show_timeline`, `show_quote` (default
  **False**), `show_values`, `show_highlights`, `show_facts`, `show_team`,
  `show_gallery`, `show_branches`, `show_cta`.
- **hero:** `hero_title` (TextField ≤ 200, Enter for a line break, as
  `intro_title`), `hero_text`, `hero_image` + `hero_image_alt` (fallback
  bundled image), `hero_button_text`, `hero_button_url` (default
  `/contact/`).
- **story:** `story_title`, `story_text`, `timeline_title` (visually hidden
  heading for the `<ol>`).
- **quote:** `quote_text`, `quote_name`, `quote_role`, `quote_photo` +
  `quote_photo_alt`.
- **beliefs:** `values_title`, `mission_title`, `mission_text`,
  `vision_title`, `vision_text`.
- **different:** `highlights_title`, `highlights_text`.
- **facts / team / gallery:** `facts_title`, `team_title`, `team_text`,
  `gallery_title`.
- **branches:** `branches_title`, `branches_text`, `branches_link_text`
  («مسیریابی و تلفن»).
- **CTA:** `cta_title`, `cta_text`, `cta_primary_text`, `cta_primary_url`
  (`/contact/`), `cta_secondary_text` (blank), `cta_secondary_url` (blank).
- **SEO:** `meta_title` («درباره ما»), `meta_description`.

Inlines (all `OrderedItem`, FK `page` → `AboutPage`, `related_name` as
below):

| Model | `related_name` | Fields |
|---|---|---|
| `AboutMilestone` | `milestones` | `year` (CharField 20, as typed), `title` (100), `text` (blank) |
| `AboutValue` | `belief_values` | `emoji` (10, blank), `title` (80), `text` (200, blank) |
| `AboutHighlight` | `highlights` | `image` + `image_alt` + `static_fallback`, `title` (80), `text` (blank) |
| `AboutFact` | `facts` | `value` (20), `label` (80) |
| `AboutPerson` | `people` | `staff` (FK `staff.Staff`, null, SET_NULL), `name_override`, `role` (80), `photo_override`, `bio` (150, blank); `display_name`, `photo_url`, `initial` properties; `clean()` |
| `AboutPhoto` | `photos` | `image` (**required**), `image_alt`, `caption` (150, blank) |

`AboutValue` uses `belief_values`, not `values`, which would shadow
`QuerySet.values` on the related manager.

Images use the existing `_image_field`, with size hints in the help text and
upload dirs under `website/about/…`. Every model with an image is added to
`signals.MODELS_WITH_IMAGES`.

**Migrations:**
- `0006_about`: schema; depends on `staff`'s latest migration.
- `0007_seed_about`: D4; create-only, reversible.
- `0008_about_menu`: D7 + D8; reversible.

### 4.2 Admin

- `AboutPageAdmin(SingletonAdmin)`:
  - `COMPACT_TEXTAREA`;
  - fieldsets in the page's order, starting with «نمایش سکشن‌ها» and the
    same "a section without active items is hidden" note;
  - image previews.
- Inlines, in page order:
  - `AboutMilestoneInline` (tabular);
  - `AboutValueInline` (tabular);
  - `AboutHighlightInline` (stacked, preview);
  - `AboutFactInline` (tabular);
  - `AboutPersonInline` (tabular, preview, `autocomplete_fields=("staff",)`,
    `select_related("staff__user")`);
  - `AboutPhotoInline` (tabular, preview).
- Admin menu name: **«صفحه درباره ما»**.
- Add and delete are disabled through `SingletonAdmin`.

### 4.3 View, URL, templates

- `website/urls.py`: `path("about/", views.about, name="about")`.
- `views.about` (`require_safe`): `_load_about_page()`, then
  `render("website/about.html", context)`. The context holds `page`, one
  list per section (empty when its switch is off) and `locations`.
- Templates:
  - `website/about.html` extends `base.html` and reuses the public navbar;
    `body_class` is `public-page landing about-page`.
  - It has the title block (`meta_title | site_name`) and the meta
    description.
  - It has one `<h1>`.
  - Partials go in `website/about/` only where a block is repeated:
    `_person.html` (photo or initial) and `_milestone.html`.
- Text is auto-escaped everywhere; multi-line fields use `linebreaksbr`.
- Links come only from `validate_link`ed fields.

### 4.4 Static files

- `website/static/website/css/about.css`: loaded after `nav.css` and
  `index.css`. Holds the tokens in §3.2, mobile-first, logical properties,
  visible `:focus-visible` rings and the `prefers-reduced-motion` guard.
- The ink line is inline SVG in the template:
  - `preserveAspectRatio="none"`, `vector-effect: non-scaling-stroke`, a
    gentle wobble path with `pathLength="1"`;
  - it's drawn by a scroll-driven `stroke-dashoffset` keyframe inside
    `@supports (animation-timeline: view())`.
- No `about.js` (D10). Nothing from a CDN (ADR-021).

### 4.5 Tests (`website/test_about.py`)

- **View:**
  - URL name `website:about`, 200;
  - the seeded page renders its hero, values and highlights, and not the
    inactive milestones or facts, nor the quote (off by default);
  - exactly one `<h1>`;
  - HEAD is OK, POST returns 405.
- **Sections on/off:** each switch hides its section. A section with no
  active items isn't rendered (no empty heading). Inactive items are hidden.
- **Fallbacks:**
  - hero image → bundled static, highlight `static_fallback`;
  - person: linked staff name/avatar → overrides win → initial when no
    photo;
  - people of inactive `Staff` hidden;
  - `clean()` requires staff or name;
  - locations: branch name/address, override wins, inactive location or
    branch hidden.
- **Escaping:** `<script>` in a title, a quote and a caption is rendered
  escaped.
- **Links:** `javascript:` is refused by `validate_link` on the CTA, hero
  and secondary URLs. The secondary button is hidden when its text or URL is
  empty.
- **Admin:** the changelist redirects to the single record; add and delete
  are forbidden; the change page renders with all six inlines; staff
  autocomplete is configured.
- **Image cleanup:** a replaced hero image and a deleted photo's file are
  removed after commit.
- **Migrations:**
  - **seed**: creates the expected rows (inactive ones inactive); a
    re-run doesn't duplicate; the reverse deletes them.
  - **menu forward**: «درباره ما» rows at `#` get `/about/` in both the nav
    and footer; an edited row is untouched; «کلاس ها» at `#` is
    deactivated; a renamed or linked «کلاس ها» row and other `#` rows
    («وبلاگ», «مقاله», «معلمان») are untouched.
  - **menu reverse**: only rows still at `/about/` go back to `#`; only an
    inactive «کلاس ها» at `#` is re-activated.
- **Navbar:** «درباره ما» is `aria-current="page"` on `/about/`, and
  «کلاس ها» isn't rendered.
- **Query count:**
  - flat: adding 5 rows to every inline, 5 people linked to staff and
    3 locations doesn't change the count;
  - exact count locked with `assertNumQueries`.
- **Existing tests:** I'll update any test that asserts the seeded nav list,
  if one does, and won't delete any.

### 4.6 Verification

- `makemigrations --check --dry-run`.
- Migrations forward, back to `0005` and forward again on a **scratch SQLite
  copy**, checking the menu rows at each step.
- `website` tests on Postgres and SQLite.
- Full suite on Postgres (in the background, serially), compared with a
  **baseline full run on `main`** taken before I change anything.
- Headless Chrome (Playwright in a scratch venv, the system Chrome) on the
  scratch copy with sample content (milestones, facts, people, photos,
  quote switched on):
  - 1280px and 375px full pages;
  - the nav drawer;
  - `scrollWidth` checks at 375px;
  - one screenshot with `prefers-reduced-motion: reduce`.

  I'll share the screenshots.

### 4.7 Docs (on the feature branch)

- `docs/apps/website.md`: models, admin, view, front end, migrations.
- `docs/database.md` + `docs/database-mermaid.md`: six new tables and the FK
  to `staff.Staff`.
- `docs/changelog.md`.
- ADR-025 if D5 is approved.
- Report `docs/plans/2026-10-about-page.md`.

---

## 5. What I will NOT touch

- «وبلاگ», «مقاله» (the blog task), «معلمان» and «سوالات متداول» rows.
- Landing and contact templates, `index.css`, `contact.css` and `base.html`.
  No shared-token hoisting (D9).
- `school.Branch`, `staff.Staff` and any other app's data. Their rows are
  only read.
- Any existing website content row, except the two menu updates in D7/D8,
  and only under their exact conditions.
- The local Docker database and production: no `migrate`, no
  `collectstatic`.
- No commits, pushes or merges beyond this plan file, unless you ask.

## 6. Manual steps at deploy (for the report)

- Run `migrate` (website 0006–0008), then `collectstatic`, by hand as usual.
- In the admin (**صفحه درباره ما**):
  - write the real story;
  - turn milestones and facts into real ones and tick «فعال»;
  - add the people;
  - upload real photos (with parents' consent for children's photos);
  - get the director's words and switch the quote on.

## 7. Open questions

1. «معلمان» is still a `#` menu item. Later, it could point to
   `/about/#team`. Not in this task unless you say so.
2. Registration: the CTA's second button stays empty until the registration
   page exists.
