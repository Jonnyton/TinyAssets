import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { dirname, resolve } from "node:path";
import test from "node:test";
import { fileURLToPath } from "node:url";

const here = dirname(fileURLToPath(import.meta.url));
const repoRoot = resolve(here, "..", "..", "..");

function source(path) {
  return readFileSync(resolve(repoRoot, path), "utf8");
}

const liveClients = [
  "WebSite/site-react/lib/live.ts",
  "WebSite/site/src/lib/mcp/live.ts",
];

const discoverySurfaces = [
  "WebSite/site-react/app/commons/_components/CommonsClient.tsx",
  "WebSite/site-react/app/graph/_components/GraphClient.tsx",
  "WebSite/site/src/routes/commons/+page.svelte",
  "WebSite/site/src/routes/graph/+page.svelte",
  "WebSite/site/src/lib/components/LiveSourceBar.svelte",
];

test("both live clients carry validated discovery scope and the exact omission note", () => {
  for (const path of liveClients) {
    const body = source(path);
    assert.doesNotMatch(
      body,
      /export\s+async\s+function\s+callTool\b/,
      `${path} must keep the generic RPC primitive module-private`,
    );
    assert.match(body, /pageDiscovery/);
    assert.match(body, /scope:\s*wiki(?:List)?\.scope/);
    assert.match(body, /scopeNote:\s*wiki(?:List)?\.scopeNote/);
    assert.doesNotMatch(
      body,
      /pageInventory\?*\.scope_note/,
      `${path} must consume metadata returned by the validated inventory parser`,
    );
  }
});

test("every live page-count surface renders discovery scope and its omission note", () => {
  for (const path of discoverySurfaces) {
    const body = source(path);
    assert.match(body, /discovery/i, `${path} must label the discovery scope`);
    assert.match(
      body,
      /scopeNote|scope_note/,
      `${path} must visibly render the server omission note`,
    );
  }
});

test("Commons and Graph copy does not claim discovery is the complete public brain", () => {
  const copy = [
    ...discoverySurfaces.slice(0, 4),
    "WebSite/site-react/app/commons/page.tsx",
    "WebSite/site-react/app/graph/page.tsx",
  ].map(source).join("\n").replace(/\s+/g, " ");

  assert.doesNotMatch(copy, /Everything I know.{0,20}is.{0,10}public/i);
  assert.doesNotMatch(copy, /Every page below was fetched fresh/i);
  assert.doesNotMatch(copy, /Every one of the .*pages in my memory/i);
  assert.doesNotMatch(copy, /public brain.{0,80}every wiki page/i);
  assert.match(copy, /discoverable/i);
  assert.match(copy, /not (?:a )?complete inventory/i);
});

test("global navigation and metadata never relabel discovery as the whole brain", () => {
  const copy = [
    "WebSite/site-react/components/TinyBot.tsx",
    "WebSite/site/src/lib/components/TinyBot.svelte",
    "WebSite/site-react/app/layout.tsx",
    "WebSite/site/src/routes/+layout.svelte",
    "WebSite/site-react/app/notebook/page.tsx",
    "WebSite/site/src/routes/notebook/+page.svelte",
    "WebSite/site-react/app/graph/_components/GraphClient.tsx",
    "WebSite/site/src/routes/graph/+page.svelte",
  ].map(source).join("\n").replace(/\s+/g, " ");

  assert.doesNotMatch(copy, /my whole memory|everything I know.{0,20}public/i);
  assert.doesNotMatch(copy, /my whole brain|every page a live reading/i);
  assert.doesNotMatch(copy, /live, verifiable state on every page/i);
  assert.doesNotMatch(copy, /browse every page in the commons/i);
});

test("public copy never totalizes a scoped, dated, or unavailable source", () => {
  const globalCopy = [
    "WebSite/site-react/app/_components/HomeClient.tsx",
    "WebSite/site/src/routes/+page.svelte",
    "WebSite/site-react/app/graph/_components/GraphClient.tsx",
    "WebSite/site/src/routes/graph/+page.svelte",
    "WebSite/site-react/app/commons/_components/CommonsClient.tsx",
    "WebSite/site/src/routes/commons/+page.svelte",
    "WebSite/site-react/components/Footer.tsx",
    "WebSite/site/src/lib/components/Footer.svelte",
    "WebSite/site-react/components/VitalSigns.tsx",
    "WebSite/site/src/lib/components/VitalSigns.svelte",
    "WebSite/site-react/lib/live.ts",
    "WebSite/site/src/lib/mcp/live.ts",
    "WebSite/site-react/app/goals/page.tsx",
    "WebSite/site/src/routes/goals/+page.svelte",
    "WebSite/site-react/components/TinyBot.tsx",
    "WebSite/site/src/lib/components/TinyBot.svelte",
    "WebSite/site/src/lib/components/MoodPill.svelte",
  ].map(source).join("\n").replace(/\s+/g, " ");

  assert.doesNotMatch(
    globalCopy,
    /whole[- ]brain|whole map|every wiki page|one dot per wiki page|my head.{0,30}seen from above/i,
  );
  assert.doesNotMatch(globalCopy, /same surface.{0,40}every number/i);
  assert.doesNotMatch(
    globalCopy,
    /what Tiny is working on|what(?:'|’)s being worked on|what's on me right now/i,
  );
  assert.doesNotMatch(
    globalCopy,
    /goals for restoring classic games.{0,180}producing research papers/i,
    "the FAQ must derive its claim from the curated snapshot rather than naming removed Goals",
  );
  assert.doesNotMatch(globalCopy, /Today zero rungs/i);
  assert.doesNotMatch(globalCopy, /pick it up today|that one(?:'|’)s open|no workflow is moving/i);
  assert.doesNotMatch(globalCopy, /a run is moving|\bactiveRun\b/i);
  assert.doesNotMatch(
    globalCopy,
    /live brain|something(?:'|’)s happening right now|my memory, not a screenshot|a universe was active/i,
  );
});

test("global paired surfaces carry bounded source labels", () => {
  const pairs = [
    [
      "WebSite/site-react/app/_components/HomeClient.tsx",
      "WebSite/site/src/routes/+page.svelte",
      /checked-in public snapshot/i,
    ],
    [
      "WebSite/site-react/app/graph/_components/GraphClient.tsx",
      "WebSite/site/src/routes/graph/+page.svelte",
      /discovery-scoped/i,
    ],
    [
      "WebSite/site-react/components/Footer.tsx",
      "WebSite/site/src/lib/components/Footer.svelte",
      /published discovery/i,
    ],
    [
      "WebSite/site-react/app/goals/page.tsx",
      "WebSite/site/src/routes/goals/+page.svelte",
      /dated public/i,
    ],
    [
      "WebSite/site-react/components/TinyBot.tsx",
      "WebSite/site/src/lib/components/TinyBot.svelte",
      /timestamp signal/i,
    ],
  ];

  for (const [reactPath, sveltePath, label] of pairs) {
    assert.match(source(reactPath), label, `${reactPath} must carry the bounded label`);
    assert.match(source(sveltePath), label, `${sveltePath} must carry the bounded label`);
  }
});

test("Host surfaces distinguish unavailable discovery from a proven empty result", () => {
  for (const path of [
    "WebSite/site-react/app/host/_components/HostClient.tsx",
    "WebSite/site/src/routes/host/+page.svelte",
  ]) {
    const body = source(path);
    assert.doesNotMatch(
      body,
      /visibility\s*\?\?\s*["']public["']/,
      `${path} must not default missing universe visibility to public`,
    );
    assert.match(body, /public["'],\s*["']metadata_only/);
    assert.match(body, /Public universe discovery is unavailable/);
    assert.match(body, /no independently published universe rows/i);
    const unavailableState = body.indexOf("rows.length === 0 && liveErr && !live");
    const successfulEmptyState = Math.max(
      body.indexOf("rows.length === 0 && live ?"),
      body.indexOf("rows.length === 0 && live}"),
    );
    assert.ok(unavailableState >= 0, `${path} must render an unavailable state`);
    assert.ok(
      successfulEmptyState > unavailableState,
      `${path} must check failed discovery before successful empty discovery`,
    );
  }
});

test("public graph discovery is never labelled as active or executing work", () => {
  for (const path of [
    "WebSite/site/src/lib/components/Playground.svelte",
    "WebSite/site-react/app/host/_components/HostClient.tsx",
    "WebSite/site/src/routes/host/+page.svelte",
  ]) {
    const body = source(path);
    assert.doesNotMatch(body, /Active universes|These are running on the box/i);
    assert.match(body, /Public universes|shared-engine discovery/i);
  }
});

test("proof and status aliases promise only the public Fine Print boundary", () => {
  for (const path of [
    "WebSite/site-react/app/proof/page.tsx",
    "WebSite/site/src/routes/proof/+page.svelte",
    "WebSite/site-react/app/status/page.tsx",
    "WebSite/site/src/routes/status/+page.svelte",
  ]) {
    const body = source(path).replace(/\s+/g, " ");
    assert.doesNotMatch(body, /deploy receipts?|run records?|live status/i);
    assert.match(body, /unavailable/i);
  }

  const svelteFinePrint = source("WebSite/site/src/routes/fine-print/+page.svelte");
  assert.doesNotMatch(
    svelteFinePrint,
    /content="[^"]*engine(?:'|’)s own release receipt/i,
  );
  assert.match(svelteFinePrint, /release-receipt unavailability/i);
});

test("public Fine Print pages never download or advertise raw get_status", () => {
  for (const path of [
    "WebSite/site-react/app/fine-print/_components/FinePrintClient.tsx",
    "WebSite/site/src/routes/fine-print/+page.svelte",
  ]) {
    const body = source(path);
    assert.doesNotMatch(
      body,
      /callTool\(\s*["']get_status["']|name:\s*["']get_status["']|read live from\s*<code>get_status/i,
      `${path} must not fetch or advertise the operator status payload`,
    );
    assert.match(body, /unavailable|checked-in/i);
  }
});

test("Graph keeps live discovery evidence separate from checked-in Goal and edge evidence", () => {
  for (const path of [
    "WebSite/site-react/app/graph/_components/GraphClient.tsx",
    "WebSite/site/src/routes/graph/+page.svelte",
  ]) {
    const body = source(path);
    const liveLayer = body.match(/data-source-layer=["']live-discovery["'][\s\S]{0,900}?<\/p>/)?.[0] ?? "";
    const snapshotLayer = body.match(/data-source-layer=["']checked-in-evidence["'][\s\S]{0,700}?<\/p>/)?.[0] ?? "";

    assert.match(liveLayer, /page dots/i, `${path} must put page counts in the live discovery layer`);
    assert.match(liveLayer, /universes/i, `${path} must put universe counts in the live discovery layer`);
    assert.doesNotMatch(liveLayer, /\bgoals?\b|\bcross-references?\b|\bedges?\b/i);
    assert.match(snapshotLayer, /checked-in snapshot/i);
    assert.match(snapshotLayer, /\bgoals?\b/i);
    assert.match(snapshotLayer, /\b(?:cross-references?|edges?)\b/i);
    assert.doesNotMatch(snapshotLayer, /\blive read\b/i);
  }
});

test("Fine Print defines activity only from visibility-filtered universe timestamps", () => {
  for (const path of [
    "WebSite/site-react/app/fine-print/_components/FinePrintClient.tsx",
    "WebSite/site/src/routes/fine-print/+page.svelte",
  ]) {
    const body = source(path).replace(/\s+/g, " ");
    assert.match(body, /visibility-filtered public universe/i);
    assert.match(body, /timestamp signal/i);
    assert.doesNotMatch(
      body,
      /\buser-authored run is executing\b|\ba run is moving\b|\bactive run\b/i,
      `${path} must not infer executing-run state from universe timestamps`,
    );
  }
});
