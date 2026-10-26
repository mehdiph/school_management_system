"""
The HTML of a post's body: from what the editor sends to what is stored
and shown (ADR-026).

``prepare(html)`` runs on every save (``Post.save``), whoever saves:

1. the editor's markup is parsed (``tinyhtml5``, the HTML5 parser
   WeasyPrint already brings) and reshaped into plain semantic HTML.
   Trix writes one ``<div>`` per block with ``<br>`` line breaks, and
   images as ``<figure data-trix-attachment=…>``. Blocks become ``<p>``,
   cut into paragraphs at blank lines, and each image becomes
   ``<figure><img><figcaption>``, with its caption as the ``alt`` too.
   Text without any tag (the form without JavaScript) becomes paragraphs.
2. the result goes through ``sanitize``, an ``nh3`` allow-list:
   - only the tags in ``TAGS``;
   - links only to http(s), mailto, relative paths and ``#``, with
     ``rel="noopener noreferrer"``;
   - images only from ``MEDIA_URL`` + ``blog/`` (uploads re-encoded by
     the blog), never hotlinked or ``data:``;
   - ``script``, ``style``, ``iframe``, ``object``… are removed with
     their content; no ``on*``, ``style``, ``class`` attribute survives.
3. headings get ids for the table of contents, and the plain text is
   taken for search, the reading time and the automatic excerpt.

The stored body is sanitized again when it is shown (``sanitize`` is
idempotent), so a row written by any other path is still safe.
``to_editor`` turns a stored body back into Trix's markup, so captions
survive editing.
"""

import html as html_lib
import json
import re
from dataclasses import dataclass, field
from urllib.parse import urlsplit

import nh3
import tinyhtml5
from django.conf import settings
from django.utils.text import slugify

from .text import normalize

TAGS = {
    "p", "h2", "h3", "strong", "em", "del", "a", "ul", "ol", "li",
    "blockquote", "br", "hr", "figure", "figcaption", "img", "pre",
}
ATTRIBUTES = {"a": {"href"}, "img": {"src", "alt", "width", "height"}, "h2": {"id"}, "h3": {"id"}}
# Removed together with everything inside them.
CLEAN_CONTENT_TAGS = {
    "script", "style", "iframe", "object", "embed", "noscript", "template",
    "svg", "math", "textarea", "select", "button", "title", "head",
}
URL_SCHEMES = {"http", "https", "mailto"}
MAX_IMAGE_SIDE = 4000

BLOCK_TAGS = {"p", "h2", "h3", "ul", "ol", "blockquote", "figure", "hr", "pre"}
VOID_TAGS = {"br", "hr", "img"}
RENAMED_TAGS = {
    "div": "p", "h1": "h2", "h4": "h3", "h5": "h3", "h6": "h3",
    "b": "strong", "i": "em", "s": "del", "strike": "del",
}
NBSP = "\N{NO-BREAK SPACE}"
_ID = re.compile(r"[\w-]{1,100}")
_HAS_TAG = re.compile(r"<\s*[a-zA-Z!/]")
_BLANK_LINE = re.compile(r"\n\s*\n")


# ---------------------------------------------------------------- tree helpers


@dataclass
class Node:
    """An element (``tag``) or a text node (``tag is None``)."""

    tag: str | None = None
    attrs: dict = field(default_factory=dict)
    children: list = field(default_factory=list)
    text: str = ""

    @property
    def is_text(self):
        return self.tag is None

    def text_content(self):
        if self.is_text:
            return self.text
        return "".join(child.text_content() for child in self.children)


def _text(value):
    return [Node(text=value)] if value else []


def _from_etree(element):
    node = Node(tag=element.tag.lower(), attrs=dict(element.attrib))
    node.children = _text(element.text)
    for child in element:
        # Comments have a callable tag; SVG and MathML a namespaced one
        # ("{http://www.w3.org/2000/svg}svg"): both go, with their content.
        if isinstance(child.tag, str) and not child.tag.startswith("{"):
            node.children.append(_from_etree(child))
        node.children += _text(child.tail)
    return node


def parse(html):
    """Top-level nodes of an HTML fragment."""

    root = tinyhtml5.parse(f"<!doctype html><html><body>{html or ''}</body></html>", namespace_html_elements=False)
    body = root.find("body")
    return _from_etree(body).children if body is not None else []


def serialize(nodes):
    out = []
    for node in nodes:
        if node.is_text:
            out.append(html_lib.escape(node.text, quote=False))
            continue
        attrs = "".join(f' {name}="{html_lib.escape(value)}"' for name, value in node.attrs.items())
        out.append(f"<{node.tag}{attrs}>")
        if node.tag not in VOID_TAGS:
            out.append(serialize(node.children))
            out.append(f"</{node.tag}>")
    return "".join(out)


def _is_blank(node):
    return (node.is_text and not node.text.replace(NBSP, " ").strip()) or node.tag == "br"


# ------------------------------------------------------------------ the editor


def is_blog_media_url(value):
    """True for a path under ``MEDIA_URL`` + ``blog/`` (uploads of the blog), nothing else."""

    parts = urlsplit(value or "")
    prefix = f"{settings.MEDIA_URL}blog/"
    return (
        not parts.scheme
        and not parts.netloc
        and not parts.query
        and parts.path.startswith(prefix)
        and ".." not in parts.path.split("/")
        and "\\" not in parts.path
    )


def _dimension(value):
    try:
        number = int(value)
    except (TypeError, ValueError):
        return None
    return str(number) if 0 < number <= MAX_IMAGE_SIDE else None


def _figure(src, caption="", width=None, height=None):
    """``<figure><img><figcaption>``, or None when ``src`` is not a blog upload."""

    if not is_blog_media_url(src):
        return None
    caption = normalize(caption)
    img = Node("img", {"src": src, "alt": caption})
    for name, value in (("width", _dimension(width)), ("height", _dimension(height))):
        if value:
            img.attrs[name] = value
    children = [img]
    if caption:
        children.append(Node("figcaption", children=[Node(text=caption)]))
    return Node("figure", children=children)


def _json_attr(node, name):
    try:
        value = json.loads(node.attrs.get(name) or "{}")
    except ValueError:
        return {}
    return value if isinstance(value, dict) else {}


def _find(node, tag):
    for child in node.children:
        if child.tag == tag:
            return child
        if not child.is_text:
            found = _find(child, tag)
            if found:
                return found
    return None


def _image_figure(node):
    """A figure or bare image from the editor (or from anywhere) -> a clean figure, or None."""

    if node.tag == "img":
        return _figure(node.attrs.get("src"), node.attrs.get("alt", ""), node.attrs.get("width"), node.attrs.get("height"))

    attachment = _json_attr(node, "data-trix-attachment")
    if attachment:
        if not str(attachment.get("contentType", "")).startswith("image"):
            return None
        caption = _json_attr(node, "data-trix-attributes").get("caption", "")
        return _figure(attachment.get("url"), str(caption), attachment.get("width"), attachment.get("height"))

    img = _find(node, "img")
    if img is None:
        return None
    caption_node = _find(node, "figcaption")
    caption = caption_node.text_content() if caption_node else img.attrs.get("alt", "")
    return _figure(img.attrs.get("src"), caption, img.attrs.get("width"), img.attrs.get("height"))


def _reshape(nodes):
    """Rename tags, turn images into figures and drop galleries' wrappers, recursively."""

    result = []
    for node in nodes:
        if node.is_text:
            result.append(node)
            continue
        if node.tag in ("figure", "img"):
            figure = _image_figure(node)
            if figure:
                result.append(figure)
            continue
        if node.tag == "div" and "attachment-gallery" in node.attrs.get("class", ""):
            result += _reshape(node.children)
            continue
        node.tag = RENAMED_TAGS.get(node.tag, node.tag)
        node.children = _reshape(node.children)
        result.append(node)
    return result


def _trim(children):
    """Children without leading and trailing blanks (whitespace, nbsp, <br>)."""

    start, end = 0, len(children)
    while start < end and _is_blank(children[start]):
        start += 1
    while end > start and _is_blank(children[end - 1]):
        end -= 1
    return children[start:end]


def _split_paragraph(node):
    """
    A ``<p>`` -> paragraphs and figures: cut where two or more ``<br>``
    follow each other (a blank line in the editor), and around figures
    and other blocks, which can't sit inside a paragraph.
    """

    pieces, current, breaks = [], [], []

    def flush():
        nonlocal current
        trimmed = _trim(current)
        if trimmed:
            pieces.append(Node("p", children=trimmed))
        current = []

    for child in node.children:
        if child.tag == "br" or (breaks and _is_blank(child)):
            breaks.append(child)
            continue
        if breaks:
            if sum(1 for b in breaks if b.tag == "br") >= 2:
                flush()
            else:
                current += breaks
            breaks = []
        if child.tag in BLOCK_TAGS:
            flush()
            pieces += _blocks([child])
        else:
            current.append(child)
    flush()
    return pieces


def _blocks(nodes):
    """Top-level (or blockquote / list item) content as a list of blocks."""

    result, inline = [], []

    def flush_inline():
        nonlocal inline
        if _trim(inline):
            result.extend(_split_paragraph(Node("p", children=inline)))
        inline = []

    for node in nodes:
        if node.is_text or node.tag not in BLOCK_TAGS:
            inline.append(node)
            continue
        flush_inline()
        if node.tag == "p":
            result += _split_paragraph(node)
        elif node.tag in ("h2", "h3", "pre"):
            node.children = _trim(node.children)
            if node.children:
                result.append(node)
        elif node.tag == "blockquote":
            node.children = _trim(node.children)
            if node.children:
                result.append(node)
        elif node.tag in ("ul", "ol"):
            for item in node.children:
                if item.tag == "li":
                    item.children = _trim(item.children)
            if any(item.tag == "li" for item in node.children):
                result.append(node)
        else:
            result.append(node)
    flush_inline()
    return result


def plain_to_html(text):
    """Text typed without the editor -> paragraphs at blank lines, ``<br>`` at single line breaks."""

    paragraphs = [p.strip() for p in _BLANK_LINE.split(text.replace("\r\n", "\n")) if p.strip()]
    return "".join(
        "<p>{}</p>".format("<br>".join(html_lib.escape(line.strip(), quote=False) for line in p.split("\n")))
        for p in paragraphs
    )


# ------------------------------------------------------------------- sanitizing


def _attribute_filter(tag, attribute, value):
    if tag == "img" and attribute == "src":
        return value if is_blog_media_url(value) else None
    if tag == "img" and attribute in ("width", "height"):
        return _dimension(value)
    if attribute == "id":
        return value if _ID.fullmatch(value) else None
    return value


def sanitize(html):
    """The allow-list of ADR-026. Idempotent; safe to run on any string."""

    return nh3.clean(
        html or "",
        tags=TAGS,
        clean_content_tags=CLEAN_CONTENT_TAGS,
        attributes=ATTRIBUTES,
        attribute_filter=_attribute_filter,
        url_schemes=URL_SCHEMES,
        link_rel="noopener noreferrer",
        strip_comments=True,
    )


# --------------------------------------------------------------- derived data


@dataclass
class Prepared:
    html: str
    text: str
    toc: list


def _unwrap_dead_links(nodes):
    """Links whose address the allow-list refused are left as their text."""

    result = []
    for node in nodes:
        if node.is_text:
            result.append(node)
            continue
        node.children = _unwrap_dead_links(node.children)
        if node.tag == "a" and not node.attrs.get("href"):
            result += node.children
        else:
            result.append(node)
    return result


def _add_heading_ids(nodes):
    toc, used = [], set()
    for node in nodes:
        if node.tag not in ("h2", "h3"):
            continue
        title = normalize(node.text_content())
        base = slugify(title, allow_unicode=True)[:80].strip("-") or "بخش"
        anchor, n = base, 2
        while anchor in used:
            anchor, n = f"{base}-{n}", n + 1
        used.add(anchor)
        node.attrs = {"id": anchor}
        toc.append({"level": int(node.tag[1]), "id": anchor, "title": title})
    return toc


def _plain_text(nodes):
    parts = []
    for node in nodes:
        if node.tag == "img":
            continue
        if node.is_text:
            parts.append(node.text)
        elif node.tag == "br":
            parts.append("\n")
        else:
            parts.append(_plain_text(node.children))
            if node.tag in BLOCK_TAGS or node.tag in ("li", "figcaption"):
                parts.append("\n")
    return "".join(parts)


def prepare(html):
    """Editor (or plain-text) input -> the stored body, its plain text and its table of contents."""

    html = html or ""
    if html.strip() and not _HAS_TAG.search(html):
        html = plain_to_html(html)
    clean = sanitize(serialize(_blocks(_reshape(parse(html)))))
    nodes = _blocks(_unwrap_dead_links(parse(clean)))  # again: the allow-list may have emptied a block
    toc = _add_heading_ids(nodes)
    text = "\n".join(normalize(line) for line in _plain_text(nodes).split("\n") if normalize(line))
    return Prepared(html=sanitize(serialize(nodes)), text=text, toc=toc)


# ---------------------------------------------------------------- back to Trix


def to_editor(html):
    """
    A stored body -> the same content in Trix's own markup: each figure
    becomes an attachment that keeps its caption when Trix loads it.
    """

    nodes = parse(html)

    def convert(children):
        out = []
        for node in children:
            if node.tag == "figure":
                img = _find(node, "img")
                if img is None:
                    continue
                caption_node = _find(node, "figcaption")
                attachment = {"contentType": "image", "url": img.attrs.get("src", "")}
                for name in ("width", "height"):
                    if _dimension(img.attrs.get(name)):
                        attachment[name] = int(img.attrs[name])
                attributes = {"presentation": "gallery"}
                if caption_node and caption_node.text_content().strip():
                    attributes["caption"] = caption_node.text_content().strip()
                out.append(Node("figure", {
                    "data-trix-attachment": json.dumps(attachment, ensure_ascii=False),
                    "data-trix-content-type": "image",
                    "data-trix-attributes": json.dumps(attributes, ensure_ascii=False),
                }, [Node("img", {"src": attachment["url"]})]))
            elif node.is_text:
                out.append(node)
            else:
                node.children = convert(node.children)
                out.append(node)
        return out

    return serialize(convert(nodes))
