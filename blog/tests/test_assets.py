"""
Nothing in the blog loads from another site (ADR-021), and the vendored
editor is exactly the files its README records.
"""

import hashlib
import re
from pathlib import Path

from django.conf import settings
from django.test import SimpleTestCase

BLOG = Path(__file__).resolve().parent.parent
TRIX = Path(settings.BASE_DIR) / "static" / "vendor" / "trix"

# <script src="https://…">, <link href="//…">, @import url("http://…"), url(https://…) in CSS.
EXTERNAL = re.compile(
    r"""(<script\b[^>]*\bsrc\s*=\s*["']?\s*(https?:)?//)"""
    r"""|(<link\b[^>]*\bhref\s*=\s*["']?\s*(https?:)?//)"""
    r"""|(@import\s+(url\()?\s*["']?\s*(https?:)?//)"""
    r"""|(url\(\s*["']?\s*(https?:)?//)""",
    re.IGNORECASE,
)


class NoExternalAssetsTests(SimpleTestCase):
    def files(self, folder, *patterns):
        found = [path for pattern in patterns for path in (BLOG / folder).rglob(pattern)]
        self.assertTrue(found, f"no files under blog/{folder}")
        return found

    def test_no_blog_template_loads_an_external_script_or_stylesheet(self):
        for path in self.files("templates", "*.html", "*.txt", "*.xml"):
            with self.subTest(template=str(path.relative_to(BLOG))):
                self.assertIsNone(EXTERNAL.search(path.read_text(encoding="utf-8")))

    def test_no_blog_stylesheet_imports_from_another_site(self):
        for path in self.files("static", "*.css"):
            with self.subTest(stylesheet=str(path.relative_to(BLOG))):
                self.assertIsNone(EXTERNAL.search(path.read_text(encoding="utf-8")))

    def test_the_pattern_catches_what_it_should(self):
        for snippet in (
            '<script src="https://cdn.example/x.js"></script>',
            "<script defer src='//cdn.example/x.js'></script>",
            '<link rel="stylesheet" href="http://fonts.example/css">',
            '@import url("https://fonts.example/css");',
            "background: url(//cdn.example/a.png)",
        ):
            with self.subTest(snippet=snippet):
                self.assertIsNotNone(EXTERNAL.search(snippet))
        for snippet in (
            '<script src="{% static \'blog/js/editor.js\' %}"></script>',
            '<link rel="canonical" href="{{ canonical }}">',
            '<a href="https://t.me/share/url">',
        ):
            with self.subTest(snippet=snippet):
                self.assertIsNone(EXTERNAL.search(snippet))


class VendoredTrixTests(SimpleTestCase):
    def test_every_vendored_file_matches_its_recorded_sha256(self):
        readme = (TRIX / "README.md").read_text(encoding="utf-8")
        recorded = dict(re.findall(r"\| `([^`]+)` \| `([0-9a-f]{64})` \|", readme))
        files = {path.name for path in TRIX.iterdir() if path.name != "README.md"}
        self.assertEqual(set(recorded), files)
        for name, digest in recorded.items():
            with self.subTest(file=name):
                self.assertEqual(hashlib.sha256((TRIX / name).read_bytes()).hexdigest(), digest)

    def test_readme_records_version_and_source(self):
        readme = (TRIX / "README.md").read_text(encoding="utf-8")
        self.assertIn("Version: 2.1.19", readme)
        self.assertIn("https://registry.npmjs.org/trix/-/trix-2.1.19.tgz", readme)
