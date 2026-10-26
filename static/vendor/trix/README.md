# Trix (vendored)

* Version: 2.1.19 (MIT, see `LICENSE`), released 2026-05-09
* Source: `https://registry.npmjs.org/trix/-/trix-2.1.19.tgz`, files `dist/trix.umd.min.js`,
  its source map (kept so a manifest static storage can resolve the `sourceMappingURL`),
  `dist/trix.css` and `LICENSE`, unmodified
* Integrity of the tarball (npm `dist.integrity`):
  `sha512-E7RA3EOeUiUwNJlrF5onIOkqCA06xUU6GmHOVxXyMnGMValrDK3Ce7uaMVgiVUOvVt4mzUERAHAzD10mxoLpOg==`
* SHA-256 of the tarball: `9682d897ee94afc6a9fd463c85e6ec1b69c608890c4f366311f5b9562a5dbd5c`
* SHA-256 of each vendored file (checked by `blog.tests.test_assets`):

| File | SHA-256 |
|---|---|
| `trix.umd.min.js` | `5dcaa7c434ae9f3cf1a53651ea74bfad10cd6423c72cb86a8694969aaff67e51` |
| `trix.umd.min.js.map` | `3884691df1a8946da0185c9745a077b0eb35ce51cd3d8cd7a7b4968190d1aec4` |
| `trix.css` | `7a35d25d0204a594f9f89a6fef18f74321ee2dae3970da3ac11e22c4305536ac` |
| `LICENSE` | `fa0d1454375cbc7701bc13d916c3ae71e613b8ae718321641e678e09409393c4` |

Vendored rather than loaded from a CDN (ADR-021). Trix bundles DOMPurify 3.4.2, which it
uses to clean pasted HTML; it loads nothing from the network. Used by the blog's editor
(`blog/static/blog/js/editor.js`), in the admin and in the authoring area. What the editor
produces is sanitized again on the server (`blog/content.py`, ADR-026).

To upgrade: download the new tarball, check its `dist.integrity` against
`https://registry.npmjs.org/trix/<version>`, replace the four files, update the hashes in
this file (`sha256sum`), and run `blog.tests.test_assets` and the editor checks in
`docs/apps/blog.md`.
