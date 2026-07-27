import assert from "node:assert/strict";
import { readFileSync, readdirSync } from "node:fs";
import { dirname, resolve } from "node:path";
import test from "node:test";
import { fileURLToPath } from "node:url";

import {
  assertCompleteCrawl,
  publicGoalCall,
  pageInventoryCall,
  publicGraphCall,
  publicPageCall,
  publicRunCall,
  requireCollection,
  requireObjectResult,
  requirePageBody,
  splitPageInventory,
} from "../../shared/mcp/public-read-contract.js";

const here = dirname(fileURLToPath(import.meta.url));
const snapshotSourcePath = resolve(here, "snapshot-mcp.mjs");
const publicSourceRoot = resolve(here, "../src");
const reactSourceRoot = resolve(here, "../../site-react");
const sharedSourceRoot = resolve(here, "../../shared");
const viteConfigPath = resolve(here, "../vite.config.js");
const reactDeployWorkflowPath = resolve(
  here,
  "../../../.github/workflows/deploy-site-react.yml",
);
const previewWorkflowPath = resolve(
  here,
  "../../../.github/workflows/preview-worker.yml",
);

function readPublicSourceTree(directory) {
  return readdirSync(directory, { withFileTypes: true })
    .flatMap((entry) => {
      if ([".next", "build", "node_modules", "out"].includes(entry.name)) {
        return [];
      }
      const path = resolve(directory, entry.name);
      if (entry.isDirectory()) return [readPublicSourceTree(path)];
      if (!/\.(?:[cm]?[jt]sx?|svelte)$/.test(entry.name)) return [];
      return [readFileSync(path, "utf8")];
    })
    .join("\n");
}

test("canonical public read descriptors use only advertised MCP handles", () => {
  assert.deepEqual(pageInventoryCall(), {
    name: "read_page",
    args: {
      changed_since: "1970-01-01T00:00:00Z",
      max_results: 100,
    },
  });
  assert.deepEqual(pageInventoryCall("2026-07-27T00:00:00Z"), {
    name: "read_page",
    args: {
      changed_since: "2026-07-27T00:00:00Z",
      max_results: 100,
    },
  });
  assert.deepEqual(publicGraphCall("goals", 30), {
    name: "read_graph",
    args: { target: "goals", limit: 30 },
  });
  assert.deepEqual(publicGraphCall("graphs", 8), {
    name: "read_graph",
    args: { target: "graphs", limit: 8 },
  });
  assert.deepEqual(publicGraphCall("runs", 8), {
    name: "read_graph",
    args: { target: "runs", limit: 8 },
  });
  assert.deepEqual(publicGoalCall("goal-123"), {
    name: "read_graph",
    args: { target: "goal", goal_id: "goal-123" },
  });
  assert.deepEqual(publicRunCall("run-123"), {
    name: "read_graph",
    args: { target: "run", run_id: "run-123" },
  });
  assert.deepEqual(publicPageCall("pages/concepts/example.md"), {
    name: "read_page",
    args: { page: "pages/concepts/example" },
  });
});

test("page inventory preserves promoted/draft identity and fails closed on scope or truncation", () => {
  assert.deepEqual(
    splitPageInventory({
      results: [
        { path: "pages/concepts/one.md", title: "One", is_draft: false },
        { path: "drafts/notes/two.md", title: "Two", is_draft: true },
      ],
      count: 2,
      total_matches: 2,
      truncated_count: 0,
      scope: "all",
      scope_note: "",
    }),
    {
      promoted: [
        { path: "pages/concepts/one.md", title: "One", is_draft: false },
      ],
      drafts: [{ path: "drafts/notes/two.md", title: "Two", is_draft: true }],
    },
  );

  assert.throws(
    () =>
      splitPageInventory({
        results: [],
        count: 0,
        total_matches: 101,
        truncated_count: 101,
        scope: "all",
        scope_note: "",
      }),
    /truncated 101 of 101/,
  );
  assert.throws(
    () =>
      splitPageInventory({
        results: [{ path: "pages/concepts/one.md", is_draft: false }],
        count: 1,
        total_matches: 2,
        truncated_count: 0,
        scope: "all",
        scope_note: "",
      }),
    /inconsistent completeness metadata/,
  );
  assert.throws(
    () =>
      splitPageInventory({
        results: [{ path: "pages/concepts/one.md", is_draft: false }],
        count: 1,
        total_matches: 1,
        truncated_count: 0,
        scope: "discovery",
        scope_note: "Default discovery scope omitted coordination pages.",
      }),
    /incomplete.*scope:\s*discovery/i,
  );
  assert.throws(
    () =>
      splitPageInventory({
        results: [],
        count: 0,
        total_matches: 0,
        truncated_count: 0,
      }),
    /incomplete.*scope:\s*unknown/i,
  );
  assert.throws(
    () => splitPageInventory({ error: "read denied" }),
    /read denied/,
  );
});

test("canonical collection reads reject structured errors and missing arrays", () => {
  assert.deepEqual(
    requireCollection({ goals: [{ id: "g-1" }] }, "goals", "read_graph goals"),
    [{ id: "g-1" }],
  );
  assert.deepEqual(
    requireObjectResult({ release_state: {} }, "get_status"),
    { release_state: {} },
  );
  assert.throws(
    () => requireCollection({ error: "denied" }, "goals", "read_graph goals"),
    /denied/,
  );
  assert.throws(
    () => requireCollection({}, "universes", "read_graph graphs"),
    /universes array/,
  );
  assert.throws(
    () => requireObjectResult({ error: "unavailable" }, "get_status"),
    /unavailable/,
  );
  assert.deepEqual(
    requirePageBody({ content: "# Public page" }, "read_page body"),
    { content: "# Public page" },
  );
  assert.throws(
    () => requirePageBody({ error: "not found" }, "read_page body"),
    /not found/,
  );
  assert.throws(
    () => requirePageBody({}, "read_page body"),
    /content string/,
  );
});

test("snapshot page crawl cannot succeed with skipped or failed bodies", () => {
  assert.doesNotThrow(() => assertCompleteCrawl(2, 2, 0));
  assert.throws(() => assertCompleteCrawl(2, 1, 0), /attempted 1 of 2/);
  assert.throws(() => assertCompleteCrawl(2, 2, 1), /1 page read failed/);
  assert.doesNotMatch(
    readFileSync(snapshotSourcePath, "utf8"),
    /SNAPSHOT_MAX_PAGES|MAX_CRAWL_PAGES/,
  );
});

test("website readers contain no calls to retired MCP tool names", () => {
  const source =
    readFileSync(snapshotSourcePath, "utf8") +
    "\n" +
    readPublicSourceTree(publicSourceRoot) +
    "\n" +
    readPublicSourceTree(reactSourceRoot) +
    "\n" +
    readPublicSourceTree(sharedSourceRoot);

  assert.doesNotMatch(
    source,
    /(?:tool|callTool)\(\s*['"](?:wiki|goals|universe|extensions)['"]/,
  );
  const retiredObjectCall =
    /callTool\(\s*\{\s*name:\s*['"](?:wiki|goals|universe|extensions)['"]/;
  assert.doesNotMatch(source, retiredObjectCall);
  for (const name of ["wiki", "goals", "universe", "extensions"]) {
    assert.match(`callTool({ name: '${name}', arguments: {} })`, retiredObjectCall);
  }
  assert.doesNotMatch(source, /\b(?:wiki|goals|universe|extensions)\s+action=/);
});

test("home goal boards do not depend on the incomplete page inventory", () => {
  const svelteHome = readFileSync(resolve(here, "../src/routes/+page.svelte"), "utf8");
  const reactHome = readFileSync(
    resolve(here, "../../site-react/app/_components/HomeClient.tsx"),
    "utf8",
  );
  assert.doesNotMatch(svelteHome, /\bfetchLive\b/);
  assert.doesNotMatch(reactHome, /\bfetchLive\b/);
  assert.match(svelteHome, /\bfetchPublicGoals\b/);
  assert.match(reactHome, /\bfetchPublicGoals\b/);
});

test("shared contract works in dev and gates both React preview and deploy", () => {
  const viteConfig = readFileSync(viteConfigPath, "utf8");
  assert.match(viteConfig, /const websiteRoot = decodeURIComponent\(new URL\(['"]\.\.\/['"]/);
  assert.match(
    viteConfig,
    /fs:\s*\{[\s\S]*allow:\s*\[websiteRoot\]/,
  );

  const reactDeploy = readFileSync(reactDeployWorkflowPath, "utf8");
  const preview = readFileSync(previewWorkflowPath, "utf8");
  assert.match(reactDeploy, /working-directory:\s*WebSite\/site[\s\S]*npm test/);
  assert.match(preview, /working-directory:\s*WebSite\/site[\s\S]*npm test/);
  assert.match(preview, /WebSite\/shared\/\*\*/);
});

test("explicit snapshot refresh reports a refused refresh as failure", () => {
  const snapshotSource = readFileSync(snapshotSourcePath, "utf8");
  const rollbackWorkflow = readFileSync(
    resolve(here, "../../../.github/workflows/deploy-site.yml"),
    "utf8",
  );
  assert.match(snapshotSource, /SNAPSHOT_REQUIRED/);
  assert.match(rollbackWorkflow, /SNAPSHOT_REQUIRED:\s*['"]1['"]/);
});
