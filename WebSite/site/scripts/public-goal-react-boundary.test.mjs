import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { dirname, resolve } from "node:path";
import test from "node:test";
import { fileURLToPath } from "node:url";

const scriptsDir = dirname(fileURLToPath(import.meta.url));
const repoRoot = resolve(scriptsDir, "..", "..", "..");

const callers = [
  "WebSite/site-react/app/_components/HomeClient.tsx",
  "WebSite/site-react/app/goals/_components/GoalsClient.tsx",
  "WebSite/site-react/app/goal/_components/GoalDetail.tsx",
];
const goalMetadataPages = [
  "WebSite/site-react/app/goal/page.tsx",
  "WebSite/site-react/app/goals/page.tsx",
];
const goalCopyPages = [
  "WebSite/site-react/app/_components/HomeClient.tsx",
  "WebSite/site-react/app/goals/_components/GoalsClient.tsx",
  "WebSite/site-react/app/goal/_components/GoalDetail.tsx",
  ...goalMetadataPages,
];
const relatedReactCopyPages = [
  "WebSite/site-react/components/TinyBot.tsx",
  "WebSite/site-react/app/commons/_components/CommonsClient.tsx",
  "WebSite/site-react/app/fine-print/_components/FinePrintClient.tsx",
  "WebSite/site-react/app/soul/page.tsx",
  "WebSite/site-react/app/start/_components/StartClient.tsx",
];
const loopClient = "WebSite/site-react/app/loop/_components/LoopClient.tsx";
const loopPage = "WebSite/site-react/app/loop/page.tsx";
const liveClient = "WebSite/site-react/lib/live.ts";
const reactAtlas = "WebSite/site-react/lib/graph/atlas.ts";

function source(path) {
  return readFileSync(resolve(repoRoot, path), "utf8");
}

test("React public Goal surfaces never perform or advertise live Goal reads", () => {
  for (const path of callers) {
    const body = source(path);
    const prose = body.replace(/\s+/g, " ");

    assert.doesNotMatch(
      body,
      /\bfetchPublicGoals?\b/,
      `${path} must not import or call the private-capable Goal readers`,
    );
    assert.match(
      body,
      /mcp-snapshot\.json/,
      `${path} must render only the checked-in public snapshot`,
    );
    assert.doesNotMatch(
      prose,
      /\b(?:goal|goals|board)\b.{0,64}\b(?:read live|live read|fetched fresh|refresh mcp|upgrad(?:e|es|ed|ing))\b/i,
      `${path} must not claim that Goal data upgrades or refreshes live`,
    );
    assert.doesNotMatch(
      prose,
      /\b(?:read|reads|reading|fetch(?:ed|es|ing)?)\b.{0,48}\blive\b.{0,48}\b(?:goal|goals|board)\b/i,
      `${path} must not claim that Goal data is read or fetched live`,
    );
  }
});

test("React snapshot Goal surfaces fail closed unless visibility is explicitly public", () => {
  for (const path of callers) {
    const body = source(path);
    assert.doesNotMatch(
      body,
      /visibility\s*\?\?\s*["']public["']/,
      `${path} must not default missing visibility to public`,
    );
    assert.doesNotMatch(
      body,
      /visibility\s*!==\s*["']private["']/,
      `${path} must not treat every non-private value as public`,
    );
  }

  assert.doesNotMatch(
    source(reactAtlas),
    /visibility\s*\?\?\s*["']public["']/,
    `${reactAtlas} must not default missing visibility to public`,
  );
});

test("React public copy does not promise current Goal reads through a visitor connector", () => {
  for (const path of goalCopyPages) {
    const prose = source(path).replace(/\s+/g, " ");
    assert.doesNotMatch(
      prose,
      /\b(?:current|live)\s+(?:authorized\s+)?(?:Goal|goal|goals|records|board)\b|\bliving board\b/i,
      `${path} must describe the dated snapshot instead of current Goal data`,
    );
    assert.doesNotMatch(
      prose,
      /\b(?:connector|chatbot)\b.{0,80}\b(?:inspect|read|open)\b.{0,50}\b(?:Goal|goal|records)\b/i,
      `${path} must not direct visitors to an unsafe Goal-record read`,
    );
  }
});

test("React workflow activity uses only the public graph collection", () => {
  const client = source(loopClient);
  const page = source(loopPage);
  const live = source(liveClient);
  const combined = `${client}\n${page}\n${live}`;

  assert.match(
    client,
    /\bfetchPublicUniverses\b/,
    `${loopClient} must use the proven-safe public universe reader`,
  );
  assert.doesNotMatch(
    combined,
    /\bfetchWorkflowActivity\b|\bWorkflowActivity\b|\bWorkflowRun\b/,
    "the React activity surface must not preserve a run-shaped public API",
  );
  assert.doesNotMatch(
    combined,
    /\bpublicGraphCall\(\s*["'](?:run|runs|goal|goals)["']/,
    "the React live client must not request private-capable graph targets",
  );
  assert.doesNotMatch(
    client,
    /\b(?:run id|recent workflow runs?|what users have run)\b/i,
    `${loopClient} must not present public graph discovery as run history`,
  );
  assert.match(client, /\bnot\s+run records\b/i);
  assert.match(client, /read_graph target=graphs/);
  assert.match(client, /user-authored/i);
  assert.match(client, /\bcopy\b/i);
  assert.match(client, /\bremix\b/i);
  assert.match(client, /\bunavailable\b/i);
});

test("related React navigation advertises public graphs, not Goal or run history", () => {
  for (const path of relatedReactCopyPages) {
    const prose = source(path).replace(/\s+/g, " ");
    assert.doesNotMatch(
      prose,
      /\brecent user-authored runs\b|\blive and historical activity\b|\blive public goals\b|\bwhat(?:&apos;|')s already running\b|\bgoals?\b.{0,48}\bread live\b|\bread live\b.{0,48}\bgoals?\b/i,
      `${path} must not promise unsafe public Goal or run projections`,
    );
  }

  const combined = relatedReactCopyPages.map(source).join("\n");
  assert.match(combined, /\buser-authored\b/i);
  assert.match(combined, /\bremix\b/i);
  assert.match(combined, /\bpublic graph\b/i);
});

test("TinyBot describes dated Goal examples and timestamp-only workflow activity", () => {
  const body = source("WebSite/site-react/components/TinyBot.tsx").replace(/\s+/g, " ");

  assert.match(body, /checked-in snapshot/i);
  assert.match(body, /public-universe timestamp/i);
  assert.doesNotMatch(body, /\bactiveRun\b|\bqueue\b/);
  assert.doesNotMatch(
    body,
    /\ba run is moving\b|\bevery run logged\b|\bcounted live\b|\blive and historical runs\b/i,
  );
});

test("React Start and Soul never promote stale or private-capable Goal evidence", () => {
  const start = source("WebSite/site-react/app/start/_components/StartClient.tsx");
  const soul = source("WebSite/site-react/app/soul/page.tsx");

  assert.doesNotMatch(
    start,
    /\b(?:inspect|read|show|open)\b.{0,64}\b(?:Goal|goal|goals|branch|branches)\b/i,
    "Start prompts must use public discovery or compose user-owned work",
  );
  assert.match(start, /dated checked-in snapshot/i);

  assert.doesNotMatch(
    soul,
    /\bTINY_RUNGS\b|\bread from the live brain\b|\bread 9 Jun 2026\b|\bd1424d86cb5f\b/i,
    "Soul must not preserve the stale Tiny ladder fixture",
  );
  assert.match(soul, /checked-in public snapshot/i);
  assert.doesNotMatch(soul, /\blive public goals\b/i);
  assert.doesNotMatch(
    soul,
    /\bread real ladders in the wild\b/i,
    "Soul must not promise ladder evidence that the public snapshot may not contain",
  );
});
