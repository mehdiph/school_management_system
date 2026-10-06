# Chart.js (vendored)

* Version: 4.5.1 (MIT, see `LICENSE.md`)
* Source: `https://registry.npmjs.org/chart.js/-/chart.js-4.5.1.tgz`, files `dist/chart.umd.min.js` and its source map (kept so a manifest static storage can resolve the `sourceMappingURL`), unmodified
* Integrity of the tarball (npm `dist.integrity`):
  `sha512-GIjfiT9dbmHRiYi6Nl2yFCq7kkwdkp1W/lp2J99rX0yo9tgJGn3lKQATztIjb5tVtevcBtIdICNWqlq5+E8/Pw==`

Vendored rather than loaded from a CDN: production must not depend on
external CDNs (they may be blocked). Used by the director panel's
attendance trend (`director/static/director/js/attendance_chart.js`).

To upgrade: download the new tarball, check its `dist.integrity`
against `https://registry.npmjs.org/chart.js/<version>`, replace
`chart.umd.min.js` and `LICENSE.md`, and update this file.
