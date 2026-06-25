// gen-schemas.mjs — aggregate every component's *.schema.json + *.prompt.md into
// one machine-readable manifest (dist/manifest.json). This is the framework-
// neutral AI contract the research calls the highest-leverage artifact: agents
// query it for props/variants/rules instead of guessing, at a fraction of the
// tokens of prose docs. Regenerate on every change so it never drifts.

import { readdirSync, readFileSync, writeFileSync, existsSync, mkdirSync } from "node:fs";
import { fileURLToPath } from "node:url";
import { dirname, resolve, join } from "node:path";

const root = dirname(fileURLToPath(import.meta.url)) + "/..";
const componentsDir = resolve(root, "src/components");
const dist = resolve(root, "dist");
if (!existsSync(dist)) mkdirSync(dist, { recursive: true });

const components = [];
for (const name of readdirSync(componentsDir, { withFileTypes: true })) {
  if (!name.isDirectory()) continue;
  const dir = join(componentsDir, name.name);
  const schemaPath = join(dir, `${name.name}.schema.json`);
  const promptPath = join(dir, `${name.name}.prompt.md`);
  if (!existsSync(schemaPath)) continue;
  const schema = JSON.parse(readFileSync(schemaPath, "utf8"));
  components.push({
    ...schema,
    usage: existsSync(promptPath) ? readFileSync(promptPath, "utf8") : undefined,
  });
}

const tokens = JSON.parse(readFileSync(resolve(root, "tokens/tiny.tokens.json"), "utf8"));

const manifest = {
  name: "@tiny/design-system",
  designLanguage: "Field Notes",
  styles: "@tiny/design-system/styles.css",
  tokensRef: "tokens/tiny.tokens.json",
  tokenGroups: Object.fromEntries(
    Object.entries(tokens)
      .filter(([k]) => k !== "$description")
      .map(([k, v]) => [k, Object.keys(v).length])
  ),
  components,
};

writeFileSync(resolve(dist, "manifest.json"), JSON.stringify(manifest, null, 2) + "\n");
console.log(`gen-schemas: ${components.length} components → dist/manifest.json`);
