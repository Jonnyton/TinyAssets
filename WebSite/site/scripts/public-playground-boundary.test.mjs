import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { dirname, resolve } from "node:path";
import test from "node:test";
import { fileURLToPath } from "node:url";

const here = dirname(fileURLToPath(import.meta.url));
const clientSource = readFileSync(
  resolve(here, "../src/lib/mcp/playground.ts"),
  "utf8",
);
const componentSource = readFileSync(
  resolve(here, "../src/lib/components/Playground.svelte"),
  "utf8",
);

test("public Playground exposes only graph discovery through read_graph", () => {
  for (const [name, source] of [
    ["client", clientSource],
    ["component", componentSource],
  ]) {
    assert.doesNotMatch(
      source,
      /target\s*=\s*(?:goal|goals|run|runs)\b/i,
      `${name} must not advertise or issue unsafe Goal/run reads`,
    );
  }

  assert.match(clientSource, /assertPublicPlaygroundCall\(\s*tool\s*,\s*args\s*\)/);
  assert.match(componentSource, /read_graph target=graphs limit=100/);
});

test("public Playground cannot parse or execute exact and query page reads", () => {
  assert.match(
    clientSource,
    /callTool[\s\S]{0,300}assertPublicPlaygroundCall\(\s*name\s*,\s*args\s*\)[\s\S]{0,300}ensureInit\(\)/,
    "execution must validate before initializing or issuing an RPC",
  );
  assert.match(
    clientSource,
    /parseInput[\s\S]*assertPublicPlaygroundCall\(\s*tool\s*,\s*args\s*\)/,
    "the parser must use the same executable boundary as callTool",
  );
  assert.doesNotMatch(componentSource, /\bread_page\s+(?:page|query|category)=/i);
  assert.doesNotMatch(clientSource, /\bread_page\s+(?:page|query|category)=/i);
  assert.doesNotMatch(componentSource, /\bget_status\b/);
  assert.doesNotMatch(clientSource, /PUBLIC_READ_TOOLS[^;]*\bget_status\b/);
});

test("public Playground performs no background Goal or run harvesting", () => {
  for (const forbidden of [
    "harvestWorkflowNotes",
    "listRecentRuns",
    "WorkflowNote",
    "RecentRun",
    "refreshNotes",
    "refreshRuns",
    "injectNoteCall",
    "injectRunCall",
  ]) {
    assert.doesNotMatch(clientSource, new RegExp(`\\b${forbidden}\\b`));
    assert.doesNotMatch(componentSource, new RegExp(`\\b${forbidden}\\b`));
  }
  assert.doesNotMatch(componentSource, /\bsetInterval\s*\(/);
});

test("public Playground retains user-buildable and remixable design language", () => {
  assert.match(componentSource, /\buser-buildable\b/i);
  assert.match(componentSource, /\bremixable\b/i);
  assert.match(componentSource, /\bdiscovery\b/i);
});
