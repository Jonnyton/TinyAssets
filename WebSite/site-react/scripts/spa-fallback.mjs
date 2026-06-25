// Post-build: overwrite out/404.html with a tiny SPA-fallback redirector.
//
// Static hosts (GitHub Pages, the preview Worker) serve 404.html for any path
// that wasn't exported. This redirector preserves the requested path in `?p=`
// and bounces to /redirecting/, which client-routes to it — so deep-linking a
// goal id that wasn't prerendered (e.g. /goals/<new-id>/) resolves like the old
// SvelteKit SPA instead of dead-ending on a 404.
//
// Honors PAGES_BASE_PATH (subpath hosting, e.g. the GitHub Pages snapshot).

import { writeFileSync } from "node:fs";
import { resolve } from "node:path";

const base = process.env.PAGES_BASE_PATH || "";

// Inline, minified redirect script. Strips the base prefix from the path so the
// value passed to the Next router (which re-adds basePath) stays correct.
const redirect =
  "(function(){var l=window.location,b=" +
  JSON.stringify(base) +
  ',p=l.pathname;if(b&&p.indexOf(b)===0){p=p.slice(b.length);}l.replace(l.origin+b+"/redirecting/?p="+encodeURIComponent(p+l.search+l.hash));})();';

const html =
  '<!doctype html>\n<html lang="en"><head><meta charset="utf-8">' +
  '<meta name="robots" content="noindex"><title>Tiny</title>' +
  "<script>" +
  redirect +
  "</script></head><body></body></html>\n";

const outPath = resolve(process.cwd(), "out", "404.html");
writeFileSync(outPath, html, "utf8");
console.log(`spa-fallback: wrote ${outPath} (base=${base || "<root>"})`);
