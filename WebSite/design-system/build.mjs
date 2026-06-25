// build.mjs — compile the design system to a standard library dist/:
//   dist/index.js   (ESM, React/ReactDOM external)
//   dist/styles.css (tokens + base + all component CSS, one import)
//   dist/index.d.ts (types — emitted by tsc, run separately/below)
// This is the shape the claude.ai/design `/design-sync` package converter
// consumes (compiled dist + .d.ts + a styles entry), and what the product
// site imports.

import { build } from "esbuild";
import { renameSync, existsSync, rmSync } from "node:fs";
import { execSync } from "node:child_process";
import { fileURLToPath } from "node:url";
import { dirname, resolve } from "node:path";

const root = dirname(fileURLToPath(import.meta.url));
const dist = resolve(root, "dist");
if (existsSync(dist)) rmSync(dist, { recursive: true, force: true });

await build({
  entryPoints: [resolve(root, "src/index.ts")],
  outfile: resolve(dist, "index.js"),
  bundle: true,
  format: "esm",
  platform: "browser",
  target: ["es2020"],
  jsx: "automatic",
  external: ["react", "react-dom", "react/jsx-runtime"],
  loader: { ".css": "css" },
  logLevel: "info",
});

// esbuild emits the bundled CSS next to the JS entry (dist/index.css).
const emittedCss = resolve(dist, "index.css");
if (existsSync(emittedCss)) {
  renameSync(emittedCss, resolve(dist, "styles.css"));
}

// Type declarations.
execSync("npx tsc --emitDeclarationOnly --outDir dist", { cwd: root, stdio: "inherit" });

console.log("\nbuild: dist/index.js + dist/styles.css + dist/index.d.ts");
