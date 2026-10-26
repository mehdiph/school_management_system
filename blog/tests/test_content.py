"""The body pipeline and its allow-list (ADR-026), on what Trix really sends (the Phase 1 spike)."""

import json
from html import escape

from django.test import SimpleTestCase, override_settings

from blog import content, text

ZWNJ = "\N{ZERO WIDTH NON-JOINER}"
IMG = "/media/blog/posts/abc.jpg"


def trix_figure(url=IMG, caption="", content_type="image/jpeg", width=800, height=600):
    attachment = {"contentType": content_type, "url": url, "href": url, "width": width, "height": height,
                  "filename": "photo.jpg", "filesize": 1234}
    attributes = {"presentation": "gallery", **({"caption": caption} if caption else {})}
    return (
        f'<figure data-trix-attachment="{escape(json.dumps(attachment))}" '
        f'data-trix-content-type="{content_type}" data-trix-attributes="{escape(json.dumps(attributes))}" '
        f'class="attachment attachment--preview"><a href="{url}"><img src="{url}" width="{width}" height="{height}">'
        f'<figcaption class="attachment__caption"><span class="attachment__name">photo.jpg</span> '
        f'<span class="attachment__size">1.2 KB</span></figcaption></a></figure>'
    )


class SanitizeTests(SimpleTestCase):
    def clean(self, html):
        return content.prepare(html).html

    def test_dangerous_markup_is_removed(self):
        cases = {
            "<p>a<script>alert(1)</script>b</p>": "<p>ab</p>",
            '<p onclick="alert(1)" onmouseover="x">a</p>': "<p>a</p>",
            '<p><img src="x" onerror="alert(1)"></p>': "",
            '<p><a href="javascript:alert(1)">x</a></p>': "<p>x</p>",
            '<p><a href="JaVaScRiPt:alert(1)">x</a></p>': "<p>x</p>",
            '<p><a href="data:text/html,<script>alert(1)</script>">x</a></p>': "<p>x</p>",
            '<p style="color:red" class="c" id="i">a</p>': "<p>a</p>",
            '<iframe src="https://example.org"></iframe><p>a</p>': "<p>a</p>",
            '<svg onload="alert(1)"><circle/></svg><p>a</p>': "<p>a</p>",
            "<math><mi>x</mi></math><p>a</p>": "<p>a</p>",
            "<style>p{color:red}</style><p>a</p>": "<p>a</p>",
            '<object data="x"></object><embed src="x"><p>a</p>': "<p>a</p>",
            '<p><img src="https://evil.example/x.png"></p>': "",
            '<p><img src="data:image/png;base64,AAAA"></p>': "",
            '<p><img src="/media/other/x.png"></p>': "",
            '<p><img src="/media/blog/../secrets.png"></p>': "",
            '<p><img src="//evil.example/media/blog/x.png"></p>': "",
            "<!-- a comment --><p>a</p>": "<p>a</p>",
            '<form action="/x"><input name="q"><button>x</button></form><p>a</p>': "<p>a</p>",
        }
        for dirty, clean in cases.items():
            with self.subTest(dirty=dirty):
                self.assertEqual(self.clean(dirty), clean)

    def test_allowed_markup_is_kept(self):
        html = (
            '<p>یک <strong>پررنگ</strong>، <em>کج</em>، <del>خط‌خورده</del> و '
            '<a href="https://example.org/a">پیوند</a>.<br>خط دوم.</p>'
            "<ul><li>یک</li></ul><ol><li>دو</li></ol><blockquote>نقل</blockquote><hr><pre>کد</pre>"
            '<p><a href="/contact/">نسبی</a> <a href="#بخش">لنگر</a> <a href="mailto:a@b.ir">ایمیل</a></p>'
        )
        cleaned = self.clean(html)
        for fragment in (
            "<strong>پررنگ</strong>", "<em>کج</em>", "<del>خط‌خورده</del>", "<br>", "<ul><li>یک</li></ul>",
            "<ol><li>دو</li></ol>", "<blockquote>نقل</blockquote>", "<hr>", "<pre>کد</pre>",
            '<a href="https://example.org/a" rel="noopener noreferrer">پیوند</a>',
            '<a href="/contact/" rel="noopener noreferrer">', '<a href="#بخش"', '<a href="mailto:a@b.ir"',
        ):
            self.assertIn(fragment, cleaned)

    def test_legacy_tags_are_renamed(self):
        self.assertEqual(self.clean("<p><b>a</b> <i>b</i> <s>c</s></p>"), "<p><strong>a</strong> <em>b</em> <del>c</del></p>")

    def test_h1_becomes_h2_and_h4_to_h6_become_h3(self):
        cleaned = self.clean("<h1>الف</h1><h4>ب</h4><h6>پ</h6>")
        self.assertEqual(cleaned, '<h2 id="الف">الف</h2><h3 id="ب">ب</h3><h3 id="پ">پ</h3>')

    def test_heading_ids_are_unique_and_make_the_toc(self):
        prepared = content.prepare(f"<h2>چرا کتاب{ZWNJ}خوانی؟</h2><h3>نکته</h3><h2>نکته</h2>")
        self.assertEqual(
            prepared.toc,
            [
                {"level": 2, "id": "چرا-کتابخوانی", "title": f"چرا کتاب{ZWNJ}خوانی؟"},
                {"level": 3, "id": "نکته", "title": "نکته"},
                {"level": 2, "id": "نکته-2", "title": "نکته"},
            ],
        )
        self.assertIn('<h2 id="نکته-2">', prepared.html)

    def test_author_ids_are_replaced(self):
        self.assertEqual(self.clean('<h2 id="main">a</h2>'), '<h2 id="a">a</h2>')

    def test_sanitize_and_prepare_are_idempotent(self):
        html = self.clean(
            '<div>بند<br><br>دوم</div><h1>عنوان</h1><ul><li>یک</li></ul>' + trix_figure(caption="زیرنویس")
        )
        self.assertEqual(content.sanitize(html), html)
        self.assertEqual(self.clean(html), html)

    def test_sanitize_runs_on_any_stored_string(self):
        # What is shown is cleaned again: a row written without Post.save() is still safe.
        self.assertEqual(content.sanitize('<p onclick="x">a<script>b</script></p>'), "<p>a</p>")

    @override_settings(MEDIA_URL="/uploads/")
    def test_image_prefix_follows_media_url(self):
        self.assertTrue(content.is_blog_media_url("/uploads/blog/posts/a.jpg"))
        self.assertFalse(content.is_blog_media_url("/media/blog/posts/a.jpg"))


class EditorShapeTests(SimpleTestCase):
    """Trix's markup (one <div> per block, <br> line breaks, attachments) -> plain paragraphs and figures."""

    def test_blank_lines_split_paragraphs_and_single_breaks_stay(self):
        html = f'<div dir="rtl">بند یکم.<br>خط دوم.<br><br>بند دوم.<br>&nbsp;<br>بند سوم.<br><br></div>'
        self.assertEqual(
            content.prepare(html).html,
            "<p>بند یکم.<br>خط دوم.</p><p>بند دوم.</p><p>بند سوم.</p>",
        )

    def test_empty_blocks_are_dropped(self):
        self.assertEqual(content.prepare("<div><br></div><p>&nbsp;</p><div>الف</div>").html, "<p>الف</p>")

    def test_trix_headings_lists_and_quotes(self):
        html = (
            '<h2 dir="rtl">عنوان</h2><h3 dir="rtl">زیرعنوان</h3><ul dir="rtl"><li>یک</li><li>دو</li></ul>'
            '<blockquote dir="rtl">نقل<br><br></blockquote>'
        )
        self.assertEqual(
            content.prepare(html).html,
            '<h2 id="عنوان">عنوان</h2><h3 id="زیرعنوان">زیرعنوان</h3><ul><li>یک</li><li>دو</li></ul>'
            "<blockquote>نقل</blockquote>",
        )

    def test_attachment_becomes_figure_with_caption_as_alt(self):
        html = f"<div>پیش از تصویر{trix_figure(caption='جشن پاییز')}پس از تصویر</div>"
        self.assertEqual(
            content.prepare(html).html,
            f'<p>پیش از تصویر</p><figure><img src="{IMG}" alt="جشن پاییز" width="800" height="600">'
            "<figcaption>جشن پاییز</figcaption></figure><p>پس از تصویر</p>",
        )

    def test_attachment_without_caption_has_empty_alt_and_no_file_name(self):
        cleaned = content.prepare(trix_figure()).html
        self.assertEqual(cleaned, f'<figure><img src="{IMG}" alt="" width="800" height="600"></figure>')
        self.assertNotIn("photo.jpg", cleaned)

    def test_gallery_wrapper_is_flattened(self):
        html = f'<div class="attachment-gallery attachment-gallery--2">{trix_figure()}{trix_figure()}</div>'
        self.assertEqual(content.prepare(html).html.count("<figure>"), 2)

    def test_foreign_or_broken_attachments_are_dropped(self):
        for figure in (
            trix_figure(url="https://evil.example/x.jpg"),
            trix_figure(url=None),
            trix_figure(content_type="application/pdf"),
            '<figure data-trix-attachment="{not json"><img src="/media/blog/a.jpg"></figure>',
        ):
            with self.subTest(figure=figure[:60]):
                self.assertNotIn("evil", content.prepare(figure).html)
                self.assertNotIn("pdf", content.prepare(figure).html)

    def test_word_paste_keeps_text_and_emphasis_only(self):
        # What Trix produced from a real Word paste in the spike.
        html = (
            '<div dir="rtl"><strong>کتاب‌خوانی در خانه</strong></div>'
            '<div dir="rtl">بچه‌ها وقتی <em>با پدر و مادرشان</em> می‌خوانند.</div>'
            '<div dir="rtl"><br>1. &nbsp; هر شب ده دقیقه<br><br></div>'
        )
        self.assertEqual(
            content.prepare(html).html,
            "<p><strong>کتاب‌خوانی در خانه</strong></p><p>بچه‌ها وقتی <em>با پدر و مادرشان</em> می‌خوانند.</p>"
            "<p>1. &nbsp; هر شب ده دقیقه</p>",
        )

    def test_text_without_tags_becomes_paragraphs(self):
        # The form without JavaScript: a plain textarea.
        self.assertEqual(
            content.prepare("بند یکم\nخط دوم\n\n\nبند <دوم> & سوم").html,
            "<p>بند یکم<br>خط دوم</p><p>بند &lt;دوم&gt; &amp; سوم</p>",
        )

    def test_round_trip_through_the_editor_keeps_captions(self):
        stored = content.prepare(trix_figure(caption="جشن پاییز")).html
        for_editor = content.to_editor(stored)
        self.assertIn("data-trix-attachment", for_editor)
        self.assertIn("جشن پاییز", for_editor)
        # Trix sends the attachment back as it got it: the stored body is unchanged.
        self.assertEqual(content.prepare(for_editor).html, stored)


class DerivedTextTests(SimpleTestCase):
    def test_plain_text_has_one_line_per_block_and_no_markup(self):
        prepared = content.prepare(f"<h2>عنوان</h2><p>بند <strong>یکم</strong><br>خط</p>{trix_figure(caption='زیرنویس')}")
        self.assertEqual(prepared.text, "عنوان\nبند یکم\nخط\nزیرنویس")

    def test_reading_minutes(self):
        with self.settings(BLOG_WORDS_PER_MINUTE=180):
            self.assertEqual(text.reading_minutes(""), 1)
            self.assertEqual(text.reading_minutes("کلمه " * 180), 1)
            self.assertEqual(text.reading_minutes("کلمه " * 181), 2)
            # A word joined by ZWNJ is one word.
            self.assertEqual(text.word_count(f"کتاب{ZWNJ}خوانی در خانه"), 3)

    def test_summary_cuts_at_a_word(self):
        self.assertEqual(text.summary("کوتاه"), "کوتاه")
        cut = text.summary("کلمه " * 100, limit=22)
        self.assertEqual(cut, "کلمه کلمه کلمه کلمه…")


class NormalizeTests(SimpleTestCase):
    def test_display_text_fixes_letters_and_spaces_only(self):
        self.assertEqual(text.normalize("  كتاب   ي  "), "کتاب ی")
        self.assertEqual(text.normalize("مسئله‌ها"), "مسئله‌ها")  # ئ and ZWNJ are kept on display
        self.assertEqual(text.normalize(f"کتاب{ZWNJ}{ZWNJ}خوانی"), f"کتاب{ZWNJ}خوانی")
        self.assertEqual(text.normalize(f"کتاب {ZWNJ}خوانی"), "کتاب خوانی")
        self.assertEqual(text.normalize("۱۲ آبان"), "۱۲ آبان")

    def test_search_key_folds_spellings(self):
        same = [f"کتاب{ZWNJ}خوانی", "کتاب خوانی", "کتابخوانی", "كتاب خواني", "کِتاب‌خوانی"]
        self.assertEqual(len({text.search_key(value) for value in same}), 1)
        self.assertEqual(text.search_key("۱۴۰۵ ٢٠"), "140520")
        self.assertEqual(text.search_key("مسئله"), text.search_key("مسیله"))
        self.assertEqual(text.search_key("ABC"), "abc")
