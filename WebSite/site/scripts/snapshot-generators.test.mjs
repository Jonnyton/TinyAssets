import assert from "node:assert/strict";
import {
  mkdtempSync,
  readFileSync,
  renameSync,
  rmSync,
  writeFileSync,
} from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
import test from "node:test";

import {
  assertNoRetiredSignatures,
  atomicWriteMirrors,
  buildMcpSnapshot,
  buildRepoSnapshot,
  pageReadHandle,
  parseToolResponse,
  serializeSnapshot,
} from "./snapshot-helpers.mjs";

const completePages = {
  changed_since: "1970-01-01T00:00:00Z",
  results: [],
  count: 0,
  total_matches: 0,
  truncated_count: 0,
  scope: "discovery",
};

test("parseToolResponse prefers structured content and parses JSON text fallback", () => {
  assert.deepEqual(
    parseToolResponse({
      structuredContent: { goals: [], count: 0 },
      content: [{ type: "text", text: '{"ignored":true}' }],
    }),
    { goals: [], count: 0 },
  );
  assert.deepEqual(
    parseToolResponse({
      content: [{ type: "text", text: '{"result":"{\\"count\\":0}"}' }],
    }),
    { count: 0 },
  );
  assert.deepEqual(
    parseToolResponse({
      structuredContent: ["wrong-shape"],
      content: [{ type: "text", text: '{"count":0}' }],
    }),
    { count: 0 },
  );
});

test("pageReadHandle uses the exact basename expected by the public resolver", () => {
  assert.equal(
    pageReadHandle("drafts/references/meridian-ashes-book-1-architecture.md"),
    "meridian-ashes-book-1-architecture",
  );
});

test("buildMcpSnapshot rejects a truncated or non-discovery page inventory", () => {
  const common = {
    fetchedAt: "2026-07-26T00:00:00.000Z",
    goalsResult: { goals: [], count: 0 },
    graphsResult: { universes: [], count: 0 },
    pageBodies: new Map(),
  };

  assert.throws(
    () =>
      buildMcpSnapshot({
        ...common,
        pagesResult: { ...completePages, total_matches: 1, truncated_count: 1 },
      }),
    /truncated/,
  );
  assert.throws(
    () =>
      buildMcpSnapshot({
        ...common,
        pagesResult: { ...completePages, scope: "coordination" },
      }),
    /discovery/,
  );
});

test("exact retired goals are removed while unproven universe names and user text survive", () => {
  const snapshot = buildMcpSnapshot({
    fetchedAt: "2026-07-26T00:00:00.000Z",
    goalsResult: {
      goals: [
        { goal_id: "4ff5862cc26d", name: "retired platform goal" },
        {
          goal_id: "4ff5862cc26d-user",
          name: "A user-authored patch loop study",
          description:
            "Users may compose automations with ordinary primitives.",
        },
      ],
      count: 2,
    },
    graphsResult: {
      universes: [
        { id: "patch-loop-live", phase_human: "offline" },
        { id: "patch-loop-live-user-copy", phase_human: "active" },
      ],
      count: 2,
    },
    pagesResult: completePages,
    pageBodies: new Map(),
  });

  assert.deepEqual(
    snapshot.goals.map((goal) => goal.id),
    ["4ff5862cc26d-user"],
  );
  assert.deepEqual(
    snapshot.universes.map((universe) => universe.id),
    ["patch-loop-live", "patch-loop-live-user-copy"],
  );
  assert.equal(snapshot.goals[0].name, "A user-authored patch loop study");
  assert.doesNotThrow(() => assertNoRetiredSignatures(snapshot));
});

test("buildMcpSnapshot requires unique bounded graph IDs and complete direct-page proof", () => {
  const page = {
    path: "pages/notes/example.md",
    title: "Example",
    updated: "2026-07-26T00:00:00Z",
    is_draft: false,
  };
  const common = {
    fetchedAt: "2026-07-26T00:00:00.000Z",
    goalsResult: { goals: [], count: 0 },
    graphsResult: { universes: [], count: 0 },
    pagesResult: {
      ...completePages,
      results: [page],
      count: 1,
      total_matches: 1,
    },
  };
  const completeBody = {
    path: page.path,
    is_draft: false,
    content: "# Example 🧠",
    truncated: false,
    total_chars: 11,
    read_start: 0,
    read_end: 11,
    next_offset: null,
    source_read_proof: {
      path: page.path,
      title: page.title,
      updated: page.updated,
      is_draft: false,
      sha256: "a".repeat(64),
    },
  };

  assert.doesNotThrow(() =>
    buildMcpSnapshot({
      ...common,
      pageBodies: new Map([[page.path, completeBody]]),
    }),
  );
  assert.throws(
    () =>
      buildMcpSnapshot({
        ...common,
        pageBodies: new Map([
          [
            page.path,
            {
              ...completeBody,
              source_read_proof: {
                ...completeBody.source_read_proof,
                title: "Wrong",
              },
            },
          ],
        ]),
      }),
    /proof/,
  );
  assert.throws(
    () =>
      buildMcpSnapshot({
        ...common,
        graphsResult: {
          universes: [{ id: "duplicate" }, { id: "duplicate" }],
          count: 2,
        },
        pageBodies: new Map([[page.path, completeBody]]),
      }),
    /duplicate/,
  );
});

test("repo snapshot is rebuilt from explicit clean topology and retains the generic coding branch", () => {
  const topology = {
    schema_version: 1,
    areas: [{ id: "area:coding-system", label: "Coding system" }],
    workflow_branches: [
      {
        id: "branch:agent_team_3node_v4",
        name: "agent_team_3node_v4",
        area: "coding",
        state: "caveated",
        summary: "Generic lead, developer, and verifier team composition.",
      },
    ],
    routes: [
      { id: "route:/patch-loop", path: "/patch-loop", label: "Patterns" },
    ],
    edges: [
      {
        from: "area:coding-system",
        to: "branch:agent_team_3node_v4",
        kind: "branch",
      },
    ],
  };

  const snapshot = buildRepoSnapshot({
    fetchedAt: "2026-07-26T00:00:00.000Z",
    repo: { id: "repo:TinyAssets", name: "TinyAssets" },
    branches: [
      {
        id: "git:feature/user-patch-loop",
        name: "feature/user-patch-loop",
        kind: "local",
      },
    ],
    topology,
  });

  assert.deepEqual(
    snapshot.workflow_branches.map((branch) => branch.id),
    ["branch:agent_team_3node_v4"],
  );
  assert.equal(snapshot.routes[0].path, "/patch-loop");
  assert.equal(snapshot.branches[0].name, "feature/user-patch-loop");
  assert.doesNotThrow(() => assertNoRetiredSignatures(snapshot));
});

test("checked-in repo topology is the reviewed clean fixture", () => {
  const topology = JSON.parse(
    readFileSync(
      new URL("../src/lib/content/repo-topology.json", import.meta.url),
      "utf8",
    ),
  );

  assert.equal(topology.areas.length, 9);
  assert.equal(topology.workflow_branches.length, 2);
  assert.equal(topology.routes.length, 8);
  assert.equal(topology.edges.length, 28);
  assert.equal(
    topology.workflow_branches.find(
      (branch) => branch.id === "branch:agent_team_3node_v4",
    )?.summary,
    "Reusable lead, developer, and checker coding-team workflow.",
  );
  assert.doesNotThrow(() => assertNoRetiredSignatures(topology));
});

test("retired signature assertion rejects exact shipped IDs without keyword censorship", () => {
  assert.throws(
    () => assertNoRetiredSignatures({ areas: [{ id: "area:patch-loop" }] }),
    /area:patch-loop/,
  );
  assert.throws(
    () =>
      assertNoRetiredSignatures({
        workflow_branches: [{ id: "branch:change_loop_v1" }],
      }),
    /branch:change_loop_v1/,
  );
  assert.doesNotThrow(() =>
    assertNoRetiredSignatures({
      title: "Patch loop retrospective",
      route: "/patch-loop",
      id: "area:patch-loop-user-copy",
    }),
  );
});

test("snapshot serialization is deterministic", () => {
  const first = {
    z: 1,
    nested: { beta: true, alpha: false },
    rows: [{ z: 2, a: 1 }],
  };
  const second = {
    rows: [{ a: 1, z: 2 }],
    nested: { alpha: false, beta: true },
    z: 1,
  };
  assert.equal(serializeSnapshot(first), serializeSnapshot(second));
});

test("atomicWriteMirrors writes byte-identical outputs", () => {
  const dir = mkdtempSync(join(tmpdir(), "tinyassets-snapshot-parity-"));
  try {
    const first = join(dir, "svelte.json");
    const second = join(dir, "react.json");
    const bytes = serializeSnapshot({ current: true });

    atomicWriteMirrors([first, second], bytes);

    assert.equal(readFileSync(first, "utf8"), bytes);
    assert.equal(readFileSync(second, "utf8"), bytes);
  } finally {
    rmSync(dir, { recursive: true, force: true });
  }
});

test("atomicWriteMirrors restores every prior output when a mirror replacement fails", () => {
  const dir = mkdtempSync(join(tmpdir(), "tinyassets-snapshot-rollback-"));
  try {
    const first = join(dir, "svelte.json");
    const second = join(dir, "react.json");
    writeFileSync(first, "old-svelte\n");
    writeFileSync(second, "old-react\n");
    let installed = 0;

    assert.throws(
      () =>
        atomicWriteMirrors(
          [first, second],
          serializeSnapshot({ current: true }),
          {
            renameSync(from, to) {
              if (from.includes(".snapshot-tmp-")) {
                installed += 1;
                if (installed === 2)
                  throw new Error("injected second mirror failure");
              }
              renameSync(from, to);
            },
          },
        ),
      /injected second mirror failure/,
    );

    assert.equal(readFileSync(first, "utf8"), "old-svelte\n");
    assert.equal(readFileSync(second, "utf8"), "old-react\n");
  } finally {
    rmSync(dir, { recursive: true, force: true });
  }
});
