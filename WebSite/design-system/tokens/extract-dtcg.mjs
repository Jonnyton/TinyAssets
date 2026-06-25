// extract-dtcg.mjs — generate a W3C DTCG (Design Tokens Community Group, 2025.10)
// token file FROM the canonical CSS `:root`. The CSS stays the source of truth
// (exact var names, zero site breakage); this emits the machine-readable mirror
// that AI design tools + multi-provider agents consume. Deterministic, so it can
// run in CI and never drift from the live tokens.
//
// Output: tokens/tiny.tokens.json  (media type application/design-tokens+json)
// ASSUMPTION: token values live in the first `:root { ... }` block of
//   src/styles/tokens.css. Override SRC via env TINY_TOKENS_SRC if relocated.

import { readFileSync, writeFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import { dirname, resolve } from "node:path";

const __dirname = dirname(fileURLToPath(import.meta.url));
const SRC = process.env.TINY_TOKENS_SRC
  ? resolve(process.env.TINY_TOKENS_SRC)
  : resolve(__dirname, "../src/styles/tokens.css");
const OUT = resolve(__dirname, "tiny.tokens.json");

const css = readFileSync(SRC, "utf8");

// Grab the first :root { ... } block.
const rootMatch = css.match(/:root\s*\{([\s\S]*?)\n\}/);
if (!rootMatch) {
  console.error("extract-dtcg: no :root block found in", SRC);
  process.exit(1);
}
const body = rootMatch[1];

// Parse `--name: value;` declarations (comments stripped).
const decls = new Map();
const order = [];
const declRe = /--([a-z0-9-]+)\s*:\s*([^;]+);/gi;
let m;
const stripComments = body.replace(/\/\*[\s\S]*?\*\//g, "");
while ((m = declRe.exec(stripComments)) !== null) {
  const name = m[1].trim();
  const value = m[2].trim();
  if (!decls.has(name)) order.push(name);
  decls.set(name, value);
}

// Resolve var(--x) chains to a concrete value (for $value); keep raw for $extensions.
function resolve_(value, seen = new Set()) {
  const ref = value.match(/^var\(\s*--([a-z0-9-]+)\s*\)$/i);
  if (ref && decls.has(ref[1]) && !seen.has(ref[1])) {
    seen.add(ref[1]);
    return resolve_(decls.get(ref[1]), seen);
  }
  return value;
}

const isColor = (v) =>
  /^#([0-9a-f]{3,8})$/i.test(v) || /^(rgb|rgba|hsl|hsla)\(/i.test(v);

// Category + DTCG $type for a token, by name prefix then value shape.
function classify(name, resolved) {
  const colorPrefixes = [
    "paper", "ground", "ink-text", "ember", "live", "violet", "bone", "ink",
    "signal", "bg", "fg", "accent", "border", "panel", "on-panel",
    "graph-violet", "live-bright", "violet-bright",
  ];
  if (name.startsWith("font-")) return { group: "fontFamily", type: "fontFamily" };
  if (name.startsWith("fs-")) return { group: "fontSize", type: "dimension" };
  if (name.startsWith("lh-")) return { group: "lineHeight", type: "number" };
  if (name.startsWith("ls-")) return { group: "letterSpacing", type: "dimension" };
  if (name.startsWith("radius-")) return { group: "radius", type: "dimension" };
  if (name.startsWith("s-")) return { group: "space", type: "dimension" };
  if (name.startsWith("shadow-") || name.startsWith("glow-")) return { group: "shadow", type: "shadow" };
  if (name.startsWith("dur-")) return { group: "duration", type: "duration" };
  if (name.startsWith("ease-")) return { group: "easing", type: "cubicBezier" };
  if (colorPrefixes.some((p) => name === p || name.startsWith(p + "-")) || isColor(resolved)) {
    return { group: "color", type: "color" };
  }
  return { group: "other", type: "string" };
}

const out = {
  $description:
    "Tiny — Field Notes design tokens (DTCG 2025.10). Generated from src/styles/tokens.css; do not hand-edit. Exact CSS variable names preserved under $extensions['tiny.var'].",
};

for (const name of order) {
  const raw = decls.get(name);
  const resolved = resolve_(raw);
  const { group, type } = classify(name, resolved);
  out[group] ??= {};
  // Key the token by its css var name (minus the leading --) so the mapping is unambiguous.
  out[group][name] = {
    $type: type,
    $value: resolved,
    $extensions: {
      "tiny.var": `--${name}`,
      ...(raw !== resolved ? { "tiny.alias": raw } : {}),
    },
  };
}

writeFileSync(OUT, JSON.stringify(out, null, 2) + "\n", "utf8");

const counts = Object.fromEntries(
  Object.entries(out)
    .filter(([k]) => k !== "$description")
    .map(([k, v]) => [k, Object.keys(v).length])
);
console.log("extract-dtcg: wrote", OUT);
console.log("groups:", counts);
console.log("total tokens:", order.length);
