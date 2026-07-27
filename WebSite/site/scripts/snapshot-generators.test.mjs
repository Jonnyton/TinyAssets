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
  normalizePublicOriginRefs,
  pageReadHandle,
  parseToolResponse,
  sanitizePublicMcpUrl,
  sanitizePublicRemoteUrl,
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

test("exact retired platform projections are removed while near-collisions and user text survive", () => {
  const snapshot = buildMcpSnapshot({
    fetchedAt: "2026-07-26T00:00:00.000Z",
    sourceUrl: "https://example.test/mcp",
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
    ["patch-loop-live-user-copy"],
  );
  assert.equal(snapshot.goals[0].name, "A user-authored patch loop study");
  assert.equal(
    snapshot.source,
    "https://example.test/mcp · discovery snapshot",
  );
  assert.equal(snapshot.provenance.endpoint, "https://example.test/mcp");
  assert.deepEqual(snapshot.provenance.exclusions.universes, [
    "patch-loop-live",
  ]);
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
    external_nodes: [],
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

test("public origin normalization excludes local state, strips origin prefix, and deduplicates", () => {
  const refs = normalizePublicOriginRefs([
    {
      name: "main",
      commit: "local123",
      date: "2026-07-26T00:00:00Z",
      subject: "local-only secret",
    },
    {
      name: "origin/main",
      commit: "public123",
      date: "2026-07-25T00:00:00Z",
      subject: "public main",
    },
    {
      name: "origin/feature",
      commit: "feature1",
      date: "2026-07-24T00:00:00Z",
      subject: "public feature",
    },
    {
      name: "origin/HEAD",
      commit: "public123",
      date: "2026-07-25T00:00:00Z",
      subject: "origin head",
    },
  ]);

  assert.deepEqual(
    refs.map((ref) => ({ id: ref.id, name: ref.name, commit: ref.commit })),
    [
      { id: "git:feature", name: "feature", commit: "feature1" },
      { id: "git:main", name: "main", commit: "public123" },
    ],
  );
  assert.equal(serializeSnapshot(refs).includes("local-only secret"), false);
});

test("public remote URL removes credentials and normalizes SSH syntax", () => {
  assert.equal(
    sanitizePublicRemoteUrl(
      "https://jonathan:ghp_supersecret@github.com/Jonnyton/TinyAssets.git",
    ),
    "https://github.com/Jonnyton/TinyAssets",
  );
  assert.equal(
    sanitizePublicRemoteUrl("git@github.com:Jonnyton/TinyAssets.git"),
    "https://github.com/Jonnyton/TinyAssets",
  );
});

test("public MCP URL strips credentials, query, and fragment and rejects non-http schemes", () => {
  assert.equal(
    sanitizePublicMcpUrl(
      "https://user:secret@example.test:8443/mcp?token=private#debug",
    ),
    "https://example.test:8443/mcp",
  );
  assert.throws(
    () => sanitizePublicMcpUrl("file:///private/tinyassets.sock"),
    /http/,
  );
});

test("MCP generator delegates mirror verification to the rollback-capable transaction", () => {
  const generator = readFileSync(
    new URL("./snapshot-mcp.mjs", import.meta.url),
    "utf8",
  );
  assert.equal(generator.includes("readFileSync"), false);
  assert.equal(generator.includes("post-write MCP snapshot"), false);
});

test("repo topology rejects duplicate edges, dangling endpoints, and retired identities", () => {
  const base = {
    schema_version: 1,
    areas: [{ id: "area:repo", label: "Repository" }],
    workflow_branches: [],
    routes: [],
    external_nodes: [],
    edges: [{ from: "repo:TinyAssets", to: "area:repo", kind: "contains" }],
  };
  const args = {
    fetchedAt: "2026-07-26T00:00:00.000Z",
    repo: { id: "repo:TinyAssets", name: "TinyAssets" },
    branches: [],
  };

  assert.throws(
    () =>
      buildRepoSnapshot({
        ...args,
        topology: { ...base, edges: [...base.edges, ...base.edges] },
      }),
    /duplicate edge/,
  );
  assert.throws(
    () =>
      buildRepoSnapshot({
        ...args,
        topology: {
          ...base,
          edges: [
            {
              from: "repo:TinyAssets",
              to: "bug:BUG-017",
              kind: "blocked-by",
            },
          ],
        },
      }),
    /unknown endpoint/,
  );
  assert.throws(
    () =>
      buildRepoSnapshot({
        ...args,
        topology: { ...base, areas: [{ id: "area:patch-loop" }] },
      }),
    /area:patch-loop/,
  );
});

test("retired signature assertion checks platform projections without censoring user content", () => {
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
      wiki: {
        notes: [
          {
            title: "area:patch-loop",
            slug: "pages/notes/community-history.md",
            tags: ["ada-request-steward"],
          },
        ],
      },
    }),
  );
});

test("frontmatter relationship fields and bounded title mentions remain graph edges", () => {
  const related = {
    path: "pages/notes/related.md",
    title: "A sufficiently specific related page title",
    updated: "2026-07-26T00:00:00Z",
    is_draft: false,
  };
  const source = {
    path: "pages/notes/source.md",
    title: "Source",
    updated: "2026-07-26T00:00:00Z",
    is_draft: false,
  };
  const body = (page, content) => ({
    path: page.path,
    is_draft: false,
    content,
    truncated: false,
    total_chars: [...content].length,
    read_start: 0,
    read_end: [...content].length,
    next_offset: null,
    source_read_proof: {
      path: page.path,
      title: page.title,
      updated: page.updated,
      is_draft: false,
      sha256: "b".repeat(64),
    },
  });
  const sourceContent = `---
supersedes_individual_bugs: [pages/notes/related.md]
related_canonical: [related]
related_concepts: [related]
---
A sufficiently specific related page title`;
  const relatedContent = "# Related";
  const snapshot = buildMcpSnapshot({
    fetchedAt: "2026-07-26T00:00:00.000Z",
    sourceUrl: "https://example.test/mcp",
    goalsResult: { goals: [], count: 0 },
    graphsResult: { universes: [], count: 0 },
    pagesResult: {
      ...completePages,
      results: [related, source],
      count: 2,
      total_matches: 2,
    },
    pageBodies: new Map([
      [related.path, body(related, relatedContent)],
      [source.path, body(source, sourceContent)],
    ]),
  });

  assert.ok(
    snapshot.edges.some(
      (edge) =>
        edge.from === "note:source" &&
        edge.to === "note:related" &&
        edge.kind === "source",
    ),
  );
  assert.ok(
    snapshot.edges.some(
      (edge) =>
        edge.from === "note:source" &&
        edge.to === "note:related" &&
        edge.kind === "title",
    ),
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

test("atomicWriteMirrors restores prior outputs when post-write parity verification fails", () => {
  const dir = mkdtempSync(join(tmpdir(), "tinyassets-snapshot-corruption-"));
  try {
    const first = join(dir, "svelte.json");
    const second = join(dir, "react.json");
    writeFileSync(first, "old-svelte\n");
    writeFileSync(second, "old-react\n");
    let reads = 0;

    assert.throws(
      () =>
        atomicWriteMirrors(
          [first, second],
          serializeSnapshot({ current: true }),
          {
            readFileSync(path, encoding) {
              reads += 1;
              if (reads === 2) return "corrupt\n";
              return readFileSync(path, encoding);
            },
          },
        ),
      /verification/,
    );
    assert.equal(readFileSync(first, "utf8"), "old-svelte\n");
    assert.equal(readFileSync(second, "utf8"), "old-react\n");
  } finally {
    rmSync(dir, { recursive: true, force: true });
  }
});

test("atomicWriteMirrors treats backup cleanup as best-effort after commit", () => {
  const dir = mkdtempSync(join(tmpdir(), "tinyassets-snapshot-cleanup-"));
  try {
    const first = join(dir, "svelte.json");
    const second = join(dir, "react.json");
    writeFileSync(first, "old-svelte\n");
    writeFileSync(second, "old-react\n");
    const bytes = serializeSnapshot({ current: true });

    assert.doesNotThrow(() =>
      atomicWriteMirrors([first, second], bytes, {
        unlinkSync(path) {
          if (path.includes(".snapshot-backup-")) {
            const error = new Error("injected cleanup failure");
            error.code = "EPERM";
            throw error;
          }
          rmSync(path);
        },
      }),
    );
    assert.equal(readFileSync(first, "utf8"), bytes);
    assert.equal(readFileSync(second, "utf8"), bytes);
  } finally {
    rmSync(dir, { recursive: true, force: true });
  }
});
