import {
  existsSync,
  readFileSync,
  renameSync,
  unlinkSync,
  writeFileSync,
} from "node:fs";

export const RETIRED_EXACT_IDENTIFIERS = new Set([
  "4ff5862cc26d",
  "f10caea2e437",
  "area:patch-loop",
  "branch:change_loop_v1",
  "branch:bug_to_patch_packet_v1",
  "branch:live_observation_watch_v1",
  "change_loop_v1",
  "bug_to_patch_packet_v1",
  "live_observation_watch_v1",
  "community-loop-core-team-v1",
  "ada-request-steward",
  "mira-investigation-planner",
  "noor-patch-writer",
  "soren-cross-checker",
  "vera-release-observer",
  "elias-contract-arbiter",
]);

const RETIRED_GOAL_IDS = new Set(["4ff5862cc26d", "f10caea2e437"]);
export function parseToolResponse(result) {
  if (
    result?.structuredContent &&
    typeof result.structuredContent === "object" &&
    !Array.isArray(result.structuredContent)
  ) {
    return result.structuredContent;
  }
  const text = result?.content?.find((item) => item?.type === "text")?.text;
  if (typeof text !== "string" || text.length === 0) return null;
  const parsed = JSON.parse(text);
  if (typeof parsed?.result !== "string") return parsed;
  try {
    return JSON.parse(parsed.result);
  } catch {
    return parsed.result;
  }
}

export function pageReadHandle(path) {
  const handle =
    String(path ?? "")
      .split("/")
      .at(-1)
      ?.replace(/\.md$/, "") ?? "";
  if (handle.length === 0)
    throw new Error(`cannot derive read_page handle from ${String(path)}`);
  return handle;
}

function requireObject(value, label) {
  if (!value || typeof value !== "object" || Array.isArray(value)) {
    throw new Error(`${label} did not return a structured object`);
  }
  return value;
}

function requireCompleteCollection(result, key, label) {
  const payload = requireObject(result, label);
  if (!Array.isArray(payload[key]))
    throw new Error(`${label}.${key} is not an array`);
  if (
    !Number.isInteger(payload.count) ||
    payload.count !== payload[key].length
  ) {
    throw new Error(`${label} count does not match ${key}.length`);
  }
  if (Number(payload.truncated_count ?? 0) !== 0) {
    throw new Error(`${label} is truncated`);
  }
  if (payload[key].length > 100)
    throw new Error(`${label} exceeds the requested cap of 100`);
  if (key !== "results") {
    const ids = new Set();
    for (const item of payload[key]) {
      const id = String(item?.goal_id ?? item?.id ?? "");
      if (id.length === 0) throw new Error(`${label} contains an empty id`);
      if (ids.has(id)) throw new Error(`${label} contains duplicate id ${id}`);
      ids.add(id);
    }
  }
  return payload[key];
}

function validatePageInventory(result) {
  const pages = requireCompleteCollection(
    result,
    "results",
    "read_page inventory",
  );
  if (result.changed_since !== "1970-01-01T00:00:00Z") {
    throw new Error(
      "read_page inventory changed_since does not prove a clean rebuild",
    );
  }
  if (result.scope !== "discovery") {
    throw new Error(
      `read_page inventory must be discovery scoped, got ${String(result.scope)}`,
    );
  }
  if (
    !Number.isInteger(result.total_matches) ||
    result.total_matches !== pages.length
  ) {
    throw new Error(
      "read_page inventory is incomplete: total_matches does not match results",
    );
  }
  const paths = new Set();
  for (const page of pages) {
    if (typeof page.path !== "string" || page.path.length === 0) {
      throw new Error("read_page inventory contains a page without a path");
    }
    if (paths.has(page.path))
      throw new Error(`read_page inventory contains duplicate ${page.path}`);
    paths.add(page.path);
  }
  return pages;
}

function validatePageBody(page, body) {
  requireObject(body, `read_page ${page.path}`);
  if (body.path !== page.path) {
    throw new Error(
      `read_page path mismatch: requested ${page.path}, received ${String(body.path)}`,
    );
  }
  if (body.truncated !== false) {
    throw new Error(
      `read_page ${page.path} is truncated or lacks completeness proof`,
    );
  }
  if (typeof body.content !== "string") {
    throw new Error(`read_page ${page.path} has no content`);
  }
  const codePointLength = [...body.content].length;
  if (
    body.read_start !== 0 ||
    body.read_end !== codePointLength ||
    body.total_chars !== codePointLength ||
    body.next_offset !== null
  ) {
    throw new Error(`read_page ${page.path} lacks complete read bounds`);
  }
  const proof = body.source_read_proof;
  if (
    !proof ||
    proof.path !== page.path ||
    proof.is_draft !== (page.is_draft === true) ||
    proof.title !== page.title ||
    proof.updated !== page.updated ||
    !/^[0-9a-f]{64}$/.test(String(proof.sha256 ?? ""))
  ) {
    throw new Error(
      `read_page ${page.path} source proof does not match discovery metadata`,
    );
  }
  return body.content;
}

function classifyPath(path) {
  const value = String(path ?? "");
  if (value.includes("/bugs/")) return "bugs";
  if (value.includes("/concepts/")) return "concepts";
  if (value.includes("/notes/")) return "notes";
  if (value.includes("/plans/")) return "plans";
  return "other";
}

function buildBugId(path) {
  const match = String(path).match(/BUG-?(\d+)/i);
  return match ? `BUG-${match[1].padStart(3, "0")}` : String(path);
}

function pathToNodeId(path, isDraft = false) {
  if (!path) return null;
  if (isDraft)
    return `draft:${String(path).split("/").at(-1)?.replace(/\.md$/, "")}`;
  const category = classifyPath(path);
  if (category === "bugs") return `bug:${buildBugId(path)}`;
  if (category === "concepts" || category === "notes" || category === "plans") {
    const prefix = category.slice(0, -1);
    return `${prefix}:${String(path).split("/").at(-1)?.replace(/\.md$/, "")}`;
  }
  return null;
}

function parseFrontmatterList(frontmatter, key) {
  const inline = frontmatter.match(
    new RegExp(`^${key}:\\s*\\[([^\\]]*)\\]`, "m"),
  );
  if (inline) {
    return inline[1]
      .split(",")
      .map((value) => value.trim().replace(/['"]/g, ""))
      .filter(Boolean);
  }
  const block = frontmatter.match(
    new RegExp(`^${key}:\\s*\\n((?:\\s+-\\s+.+\\n?)+)`, "m"),
  );
  return block
    ? block[1]
        .split("\n")
        .map((line) =>
          line
            .replace(/^\s+-\s+/, "")
            .trim()
            .replace(/['"]/g, ""),
        )
        .filter(Boolean)
    : [];
}

function extractMetadata(content) {
  const frontmatterMatch = content.match(
    /^(?:\[DRAFT\]\s*)?---\r?\n([\s\S]*?)\r?\n---/,
  );
  const frontmatter = frontmatterMatch?.[1] ?? "";
  const body = frontmatterMatch
    ? content.slice(frontmatterMatch[0].length)
    : content;
  const wikiRefs = [...content.matchAll(/\[\[([^\]\n]+)\]\]/g)].map(
    (match) => match[1],
  );
  const bugRefs = [...body.matchAll(/\bBUG-?\d{1,4}\b/gi)].map(
    (match) => match[0],
  );
  const sourceKeys = [
    "sources",
    "related",
    "related_bugs",
    "related_pages",
    "supersedes",
    "blocks",
    "blocked_by",
    "fixes",
    "see_also",
    "amends",
    "parent",
    "children",
  ];
  return {
    refs: [...new Set([...wikiRefs, ...bugRefs])],
    tags: [...new Set(parseFrontmatterList(frontmatter, "tags"))],
    sources: [
      ...new Set(
        sourceKeys.flatMap((key) => parseFrontmatterList(frontmatter, key)),
      ),
    ],
  };
}

function resolveRef(ref, knownIds) {
  const raw = String(ref)
    .trim()
    .split("|")[0]
    .split("#")[0]
    .replace(/^wiki:/i, "")
    .trim();
  const bug = raw.match(/^BUG-?(\d+)$/i);
  if (bug) {
    const id = `bug:BUG-${bug[1].padStart(3, "0")}`;
    return knownIds.has(id) ? id : null;
  }
  for (const prefix of ["concept", "note", "plan", "draft"]) {
    const direct = `${prefix}:${raw}`;
    if (knownIds.has(direct)) return direct;
    const normalized = `${prefix}:${raw.toLowerCase().replace(/[\s_]+/g, "-")}`;
    if (knownIds.has(normalized)) return normalized;
  }
  const viaPath = pathToNodeId(raw, raw.startsWith("drafts/"));
  return viaPath && knownIds.has(viaPath) ? viaPath : null;
}

function deduplicate(items, key) {
  const seen = new Set();
  return items.filter((item) => {
    const value = key(item);
    if (seen.has(value)) return false;
    seen.add(value);
    return true;
  });
}

function sortBy(items, key) {
  return [...items].sort((left, right) =>
    String(key(left)).localeCompare(String(key(right))),
  );
}

export function buildMcpSnapshot({
  fetchedAt,
  goalsResult,
  graphsResult,
  pagesResult,
  pageBodies,
}) {
  const rawGoals = requireCompleteCollection(
    goalsResult,
    "goals",
    "read_graph goals",
  );
  const rawUniverses = requireCompleteCollection(
    graphsResult,
    "universes",
    "read_graph graphs",
  );
  const pages = validatePageInventory(pagesResult);
  if (!(pageBodies instanceof Map)) throw new Error("pageBodies must be a Map");

  const goals = sortBy(
    rawGoals
      .filter((goal) => !RETIRED_GOAL_IDS.has(String(goal.goal_id ?? goal.id)))
      .map((goal) => ({
        id: String(goal.goal_id ?? goal.id ?? ""),
        name: goal.name ?? "",
        summary: goal.description ?? "",
        tags:
          typeof goal.tags === "string"
            ? goal.tags
                .split(",")
                .map((tag) => tag.trim())
                .filter(Boolean)
            : Array.isArray(goal.tags)
              ? goal.tags
              : [],
        author: goal.author ?? "anonymous",
        visibility: goal.visibility ?? "public",
      })),
    (goal) => goal.id,
  );
  const universes = sortBy(
    rawUniverses.map((universe) => ({
      id: String(universe.id ?? ""),
      phase: universe.phase_human ?? universe.phase ?? "unknown",
      word_count: universe.word_count ?? 0,
      last_activity_at: universe.last_activity_at ?? null,
      accept_rate: universe.accept_rate ?? null,
    })),
    (universe) => universe.id,
  );

  const wiki = {
    bugs: [],
    concepts: [],
    notes: [],
    plans: [],
    drafts: [],
    other: [],
  };
  const metadataByPath = new Map();
  const knownIds = new Set([
    ...goals.map((goal) => `goal:${goal.id}`),
    ...universes.map((universe) => `universe:${universe.id}`),
  ]);

  for (const page of sortBy(pages, (item) => item.path)) {
    if (typeof page.path !== "string" || page.path.length === 0) {
      throw new Error("read_page inventory contains a page without a path");
    }
    const content = validatePageBody(page, pageBodies.get(page.path));
    const metadata = extractMetadata(content);
    metadataByPath.set(page.path, {
      ...metadata,
      isDraft: page.is_draft === true,
    });
    const title = page.title ?? page.path;
    if (page.is_draft === true) {
      wiki.drafts.push({ slug: page.path, title });
    } else {
      const category = classifyPath(page.path);
      if (category === "bugs") {
        wiki.bugs.push({ id: buildBugId(page.path), title, slug: page.path });
      } else {
        wiki[category].push({ slug: page.path, title });
      }
    }
    const id = pathToNodeId(page.path, page.is_draft === true);
    if (id) knownIds.add(id);
  }

  wiki.bugs = sortBy(
    deduplicate(wiki.bugs, (item) => item.id),
    (item) => item.id,
  );
  for (const category of ["concepts", "notes", "plans", "drafts", "other"]) {
    wiki[category] = sortBy(
      deduplicate(wiki[category], (item) => item.slug),
      (item) => item.slug,
    );
  }

  const edges = [];
  const seenEdges = new Set();
  const tags = {};
  const addEdge = (from, to, kind) => {
    if (!from || !to || from === to) return;
    const signature = `${from}|${to}|${kind}`;
    if (seenEdges.has(signature)) return;
    seenEdges.add(signature);
    edges.push({ from, to, kind });
  };
  for (const [path, metadata] of metadataByPath) {
    const from = pathToNodeId(path, metadata.isDraft);
    if (!from) continue;
    for (const ref of metadata.refs)
      addEdge(from, resolveRef(ref, knownIds), "ref");
    for (const source of metadata.sources) {
      addEdge(
        from,
        pathToNodeId(source, String(source).startsWith("drafts/")) ??
          resolveRef(source, knownIds),
        "source",
      );
    }
    if (metadata.tags.length > 0) tags[from] = [...metadata.tags].sort();
  }
  for (const goal of goals) {
    if (goal.tags.length > 0) tags[`goal:${goal.id}`] = [...goal.tags].sort();
  }
  edges.sort((left, right) =>
    `${left.from}|${left.to}|${left.kind}`.localeCompare(
      `${right.from}|${right.to}|${right.kind}`,
    ),
  );

  const wikiPromoted =
    wiki.bugs.length +
    wiki.concepts.length +
    wiki.notes.length +
    wiki.plans.length +
    wiki.other.length;
  const snapshot = {
    fetched_at: fetchedAt,
    source: "tinyassets.io/mcp · discovery snapshot",
    provenance: {
      scope: "discovery",
      complete: true,
      goals: "read_graph target=goals",
      universes: "read_graph target=graphs",
      wiki: "read_page changed_since + direct read_page",
      exclusions: {
        goals: [...RETIRED_GOAL_IDS].sort(),
        universes: [],
      },
    },
    stats: {
      wiki_promoted: wikiPromoted,
      wiki_drafts: wiki.drafts.length,
      goals: goals.length,
      universes: universes.length,
      edges: edges.length,
    },
    goals,
    universes,
    wiki,
    edges,
    tags: Object.fromEntries(
      Object.entries(tags).sort(([left], [right]) => left.localeCompare(right)),
    ),
    crawled: pages.map((page) => page.path).sort(),
  };
  assertNoRetiredSignatures(snapshot);
  return snapshot;
}

export function buildRepoSnapshot({ fetchedAt, repo, branches, topology }) {
  requireObject(repo, "repo metadata");
  requireObject(topology, "repo topology");
  for (const key of ["areas", "workflow_branches", "routes", "edges"]) {
    if (!Array.isArray(topology[key]))
      throw new Error(`repo topology.${key} is not an array`);
  }
  const sortedBranches = sortBy(branches, (branch) => branch.id);
  const edges = [
    ...topology.edges.map((edge) => ({ ...edge })),
    ...sortedBranches.map((branch) => ({
      from: repo.id,
      to: branch.id,
      kind: "git",
    })),
  ].sort((left, right) =>
    `${left.from}|${left.to}|${left.kind}`.localeCompare(
      `${right.from}|${right.to}|${right.kind}`,
    ),
  );
  const snapshot = {
    fetched_at: fetchedAt,
    source: "local git checkout + GitHub remote · explicit topology",
    provenance: {
      topology: "src/lib/content/repo-topology.json",
      generated_arrays_reused: false,
    },
    repo: { ...repo },
    branches: sortedBranches,
    areas: topology.areas.map((area) => ({ ...area })),
    workflow_branches: topology.workflow_branches.map((branch) => ({
      ...branch,
    })),
    routes: topology.routes.map((route) => ({ ...route })),
    edges,
  };
  assertNoRetiredSignatures(snapshot);
  return snapshot;
}

export function assertNoRetiredSignatures(value) {
  const visit = (current, path) => {
    if (path.startsWith("$.provenance.exclusions")) return;
    if (typeof current === "string" && RETIRED_EXACT_IDENTIFIERS.has(current)) {
      throw new Error(`retired snapshot signature ${current} at ${path}`);
    }
    if (Array.isArray(current)) {
      current.forEach((item, index) => visit(item, `${path}[${index}]`));
    } else if (current && typeof current === "object") {
      for (const [key, item] of Object.entries(current))
        visit(item, `${path}.${key}`);
    }
  };
  visit(value, "$");
}

function sortObject(value) {
  if (Array.isArray(value)) return value.map(sortObject);
  if (!value || typeof value !== "object") return value;
  return Object.fromEntries(
    Object.keys(value)
      .sort()
      .map((key) => [key, sortObject(value[key])]),
  );
}

export function serializeSnapshot(snapshot) {
  return `${JSON.stringify(sortObject(snapshot), null, 2)}\n`;
}

export function atomicWriteMirrors(paths, bytes, overrides = {}) {
  if (
    !Array.isArray(paths) ||
    paths.length === 0 ||
    new Set(paths).size !== paths.length
  ) {
    throw new Error("atomicWriteMirrors requires unique output paths");
  }
  const io = {
    existsSync,
    readFileSync,
    renameSync,
    unlinkSync,
    writeFileSync,
    ...overrides,
  };
  const suffix = `${process.pid}-${Date.now()}-${Math.random().toString(16).slice(2)}`;
  const states = paths.map((path) => ({
    path,
    temp: `${path}.snapshot-tmp-${suffix}`,
    backup: `${path}.snapshot-backup-${suffix}`,
    hadOriginal: io.existsSync(path),
    installed: false,
    backedUp: false,
  }));
  const remove = (path) => {
    try {
      io.unlinkSync(path);
    } catch (error) {
      if (error?.code !== "ENOENT") throw error;
    }
  };
  try {
    for (const state of states) {
      remove(state.temp);
      remove(state.backup);
      io.writeFileSync(state.temp, bytes, "utf8");
    }
    for (const state of states) {
      if (state.hadOriginal) {
        io.renameSync(state.path, state.backup);
        state.backedUp = true;
      }
    }
    for (const state of states) {
      io.renameSync(state.temp, state.path);
      state.installed = true;
    }
    for (const state of states) {
      if (state.backedUp) remove(state.backup);
    }
  } catch (error) {
    for (const state of [...states].reverse()) {
      if (state.installed) remove(state.path);
      if (state.backedUp && io.existsSync(state.backup)) {
        io.renameSync(state.backup, state.path);
      }
      remove(state.temp);
    }
    throw error;
  }
}
