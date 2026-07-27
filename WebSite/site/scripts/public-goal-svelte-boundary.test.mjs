import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { dirname, resolve } from "node:path";
import test from "node:test";
import { fileURLToPath } from "node:url";

const here = dirname(fileURLToPath(import.meta.url));
const paths = {
  home: resolve(here, "../src/routes/+page.svelte"),
  board: resolve(here, "../src/routes/goals/+page.svelte"),
  detail: resolve(here, "../src/routes/goals/[id]/+page.svelte"),
  activity: resolve(here, "../src/routes/loop/+page.svelte"),
  atlas: resolve(here, "../src/lib/graph/atlas.ts"),
};
const sources = Object.fromEntries(
  Object.entries(paths).map(([name, path]) => [name, readFileSync(path, "utf8")]),
);

test("Svelte goal surfaces never call the unenforced goal projection", () => {
  for (const [name, source] of Object.entries(sources)) {
    assert.doesNotMatch(source, /\bfetchPublicGoals?\b/, name);
    assert.doesNotMatch(source, /read_graph\s+target\s*=\s*["']?goals?\b/i, name);
  }
});

test("Svelte goal surfaces use checked-in snapshots without live-upgrade states", () => {
  for (const name of ["home", "board", "detail", "activity"]) {
    assert.match(sources[name], /\bbakedMcp\b/, `${name} must read the checked-in snapshot`);
  }

  assert.doesNotMatch(sources.home, /\brefreshRooms\b|\bliveErr\b|live goals board|goals .* read live/i);
  assert.doesNotMatch(
    sources.board,
    /\bnormalizeLive\b|\brefreshMcp\b|\bphase\b|\breadAt\b|\berrMsg\b|live read|upgrad(?:e|es|ing)|Refresh MCP/i,
  );
  assert.doesNotMatch(
    sources.detail,
    /\bfromLive\b|\bphase\b|\breadAt\b|\berrMsg\b|live read|upgrad(?:e|es|ing)|Refresh MCP/i,
  );
  assert.doesNotMatch(sources.activity, /\bpublicGoals\b|goal names from the same live MCP read/i);
  assert.match(sources.activity, /goals .* checked-in snapshot/i);
});

test("generic user-authored automation activity stays live and remixable", () => {
  assert.match(sources.activity, /\bfetchPublicUniverses\b/);
  assert.match(sources.activity, /\buser-authored\b/i);
  assert.match(sources.activity, /\bremixable\b/i);
  assert.match(sources.activity, /universe activity only/i);
});

test("Svelte snapshot Goal surfaces fail closed unless visibility is explicitly public", () => {
  for (const [name, source] of Object.entries(sources)) {
    assert.doesNotMatch(
      source,
      /visibility\s*\?\?\s*['"]public['"]/,
      `${name} must not default missing visibility to public`,
    );
    assert.doesNotMatch(
      source,
      /(?:goal|g)(?:\?\.|\.)visibility\s*!==\s*['"]private['"]/,
      `${name} must not treat every non-private value as public`,
    );
  }
});

test("Svelte home derives Goal evidence from the checked-in snapshot instead of stale fixtures", () => {
  assert.doesNotMatch(
    sources.home,
    /cbc96a78d7ff|18b2af05ed32|d1424d86cb5f|9 Jun 2026|exist on me right now/i,
  );
  assert.match(sources.home, /\bsnapshotLadders\b/);
  assert.match(sources.home, /snapshot does not include ladder records/i);
});
