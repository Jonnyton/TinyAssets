/**
 * atlas.ts — turns the MCP snapshot (or a live re-read of the same shape)
 * into a SMALL, designed constellation instead of a 1,000-dot hairball.
 *
 * The old /graph baked every wiki page as its own node (1,183 of them) and
 * force-directed the result into a meaningless blob. The atlas aggregates:
 *
 *   - each public goal           -> one labelled node   (~19)
 *   - each universe              -> one node             (11)
 *   - each wiki category         -> one large hub w/count (patch+bugs · notes
 *                                  · plans · concepts · drafts)
 *   - the repo                   -> one hub (GitHub link)
 *
 * Edges are the snapshot's page->page references COLLAPSED to category->category
 * weights, so a thick stroke means "these two kinds of pages cite each other a
 * lot". We never invent goal<->universe edges — the snapshot has no data that
 * derives them, and a fake connection would break the honesty rail.
 *
 * Geometry is deterministic (a designed radial composition), not physics:
 * wiki hubs on an inner ring, goals on an outer ring, universes in a side
 * cluster, the repo at the centre. Readable beats jittery.
 */

export type Snapshotish = {
  fetched_at?: string;
  stats?: { wiki_promoted?: number; wiki_drafts?: number; goals?: number; universes?: number; edges?: number };
  goals?: Array<{ id: string; name: string; summary?: string; tags?: string[]; visibility?: string }>;
  universes?: Array<{ id: string; phase?: string; word_count?: number; last_activity_at?: string | null }>;
  wiki?: {
    bugs?: Array<{ id: string; title: string; slug?: string }>;
    concepts?: Array<{ slug: string; title: string }>;
    notes?: Array<{ slug: string; title: string }>;
    plans?: Array<{ slug: string; title: string }>;
    drafts?: Array<{ slug: string; title: string }>;
    other?: Array<{ slug: string; title: string }>;
  };
  edges?: Array<{ from: string; to: string; kind?: string }>;
  /** node-id -> wiki tags, baked by snapshot-mcp.mjs; powers shared-tag clusters */
  tags?: Record<string, string[]>;
};

export type AtlasNodeKind = 'repo' | 'goal' | 'universe' | 'hub';

/** A wiki category id — the buckets we collapse 1,183 pages into. */
export type CategoryId = 'patch' | 'notes' | 'plans' | 'concepts' | 'drafts';

export type AtlasNode = {
  id: string;
  kind: AtlasNodeKind;
  /** Set only for hub nodes: which wiki category this hub represents. */
  category?: CategoryId;
  label: string;
  /** Truncated label for in-figure rendering (full label lives in `label`). */
  short?: string;
  /** Short mono sublabel — a count for hubs, a phase for universes. */
  sub?: string;
  count?: number;
  /** Goal/universe id (or repo URL) used for navigation + detail panels. */
  refId?: string;
  x: number;
  y: number;
  r: number;
  /** Which side the in-figure label sits on: 'l' anchors end, 'r' anchors start. */
  side?: 'l' | 'r';
  /** Visual family: drives stroke/fill in the page. */
  tone: 'goal' | 'universe' | 'wiki' | 'repo';
};

export type AtlasEdge = {
  from: string;
  to: string;
  /** Aggregated reference weight (unique page->page pairs collapsed). */
  weight: number;
};

export type WikiPage = {
  category: CategoryId;
  title: string;
  /** Canonical path (no trailing .md — ready for the copy-prompt). */
  path: string;
  /** Sort key — bigger is newer. Parsed from BUG id or a date in the slug. */
  order: number;
  dateLabel: string;
};

export type Atlas = {
  nodes: AtlasNode[];
  edges: AtlasEdge[];
  /** Pages bucketed by category, each sorted newest-first. */
  pagesByCategory: Record<CategoryId, WikiPage[]>;
  counts: Record<CategoryId, number>;
  publicGoalCount: number;
  universeCount: number;
  /** True total references in the snapshot before aggregation. */
  rawEdgeCount: number;
  width: number;
  height: number;
};

export const CANVAS_W = 1340;
export const CANVAS_H = 820;
// The radial brain is centred right-of-middle so the universe column has its
// own room on the far left and goal labels have room to breathe at the edges.
const CENTER = { x: 760, y: CANVAS_H / 2 };

/** Truncate a long label so it never collides with another node or the edge. */
function truncate(label: string, max = 30): string {
  const clean = label.trim();
  return clean.length <= max ? clean : clean.slice(0, max - 1).trimEnd() + '…';
}

export const CATEGORY_LABEL: Record<CategoryId, string> = {
  patch: 'patch requests · bugs',
  notes: 'notes',
  plans: 'plans',
  concepts: 'concepts',
  drafts: 'drafts'
};

export const CATEGORY_BLURB: Record<CategoryId, string> = {
  patch: 'something someone wants changed',
  notes: 'what happened, and how to do it again',
  plans: 'how a change gets built',
  concepts: 'words I gave names to',
  drafts: 'not promoted yet — still cooking'
};

const REPO_ID = 'repo';
export const REPO_URL = 'https://github.com/Jonnyton/Workflow';

/** The same public filter the rest of the site uses. */
export function isPublicGoal(g: { name?: string; visibility?: string }): boolean {
  return (g.visibility ?? 'public') === 'public' && !/SUPERSEDED|RETRACTED|smoke/i.test(g.name ?? '');
}

/** Map an edge endpoint (`plan:slug`, `bug:slug`, …) to a wiki category. */
function endpointCategory(endpoint: string): CategoryId | null {
  const prefix = endpoint.split(':', 1)[0];
  switch (prefix) {
    case 'bug':
      return 'patch';
    case 'note':
      return 'notes';
    case 'plan':
      return 'plans';
    case 'concept':
      return 'concepts';
    case 'draft':
      return 'drafts';
    default:
      return null;
  }
}

/** Parse a newest-first ordering key + a human date out of a wiki slug/id. */
function orderFromSlug(slug: string, bugId?: string): { order: number; dateLabel: string } {
  // Bugs are numbered; BUG-123 is newer than BUG-001.
  if (bugId) {
    const n = parseInt(bugId.replace(/\D/g, ''), 10) || 0;
    return { order: n, dateLabel: bugId };
  }
  // Most page slugs carry a trailing YYYY-MM-DD; use it as the order key.
  const m = slug.match(/(20\d\d)-(\d\d)-(\d\d)/);
  if (m) {
    const order = Date.UTC(Number(m[1]), Number(m[2]) - 1, Number(m[3]));
    return { order, dateLabel: `${m[1]}-${m[2]}-${m[3]}` };
  }
  return { order: 0, dateLabel: '' };
}

function bucketPages(snap: Snapshotish): Record<CategoryId, WikiPage[]> {
  const wiki = snap.wiki ?? {};
  const buckets: Record<CategoryId, WikiPage[]> = { patch: [], notes: [], plans: [], concepts: [], drafts: [] };

  for (const bug of wiki.bugs ?? []) {
    const path = (bug.slug ?? `pages/bugs/${bug.id}`).replace(/\.md$/, '');
    const { order, dateLabel } = orderFromSlug(path, bug.id);
    buckets.patch.push({ category: 'patch', title: `${bug.id}: ${bug.title}`, path, order, dateLabel });
  }
  const simple = (
    arr: Array<{ slug: string; title: string }> | undefined,
    category: CategoryId
  ) => {
    for (const p of arr ?? []) {
      const path = (p.slug ?? '').replace(/\.md$/, '');
      const { order, dateLabel } = orderFromSlug(path);
      buckets[category].push({ category, title: p.title || path.split('/').pop() || path, path, order, dateLabel });
    }
  };
  simple(wiki.notes, 'notes');
  simple(wiki.plans, 'plans');
  simple(wiki.concepts, 'concepts');
  // Live re-reads may route promoted-but-draft pages into wiki.other; fold
  // those into drafts so the count stays honest after Refresh MCP.
  simple([...(wiki.drafts ?? []), ...(wiki.other ?? [])], 'drafts');

  for (const cat of Object.keys(buckets) as CategoryId[]) {
    buckets[cat].sort((a, b) => b.order - a.order);
  }
  return buckets;
}

/** Collapse page->page reference edges into category<->category weights. */
function aggregateEdges(snap: Snapshotish): { edges: AtlasEdge[]; raw: number } {
  const seen = new Set<string>();
  const weights = new Map<string, number>();
  let raw = 0;
  for (const e of snap.edges ?? []) {
    raw += 1;
    const a = endpointCategory(e.from);
    const b = endpointCategory(e.to);
    if (!a || !b) continue;
    // Dedup ref+source duplicates of the same page pair before weighting.
    const pairKey = `${e.from}__${e.to}`;
    if (seen.has(pairKey)) continue;
    seen.add(pairKey);
    if (a === b) continue; // self-category loops add noise, not structure
    const key = a < b ? `hub:${a}|hub:${b}` : `hub:${b}|hub:${a}`;
    weights.set(key, (weights.get(key) ?? 0) + 1);
  }
  const edges: AtlasEdge[] = [];
  for (const [key, weight] of weights) {
    const [from, to] = key.split('|');
    edges.push({ from, to, weight });
  }
  return { edges, raw };
}

/** Even radial placement, starting at the top and sweeping clockwise. */
function ring(count: number, radiusX: number, radiusY: number, startDeg: number, cx = CENTER.x, cy = CENTER.y) {
  const pts: Array<{ x: number; y: number }> = [];
  for (let i = 0; i < count; i++) {
    const angle = ((startDeg + (360 / Math.max(count, 1)) * i) * Math.PI) / 180;
    pts.push({ x: cx + Math.cos(angle) * radiusX, y: cy + Math.sin(angle) * radiusY });
  }
  return pts;
}

export function buildAtlas(snap: Snapshotish): Atlas {
  const pagesByCategory = bucketPages(snap);
  const counts = {
    patch: pagesByCategory.patch.length,
    notes: pagesByCategory.notes.length,
    plans: pagesByCategory.plans.length,
    concepts: pagesByCategory.concepts.length,
    drafts: pagesByCategory.drafts.length
  } satisfies Record<CategoryId, number>;

  const { edges, raw } = aggregateEdges(snap);

  const publicGoals = (snap.goals ?? []).filter(isPublicGoal);
  const universes = snap.universes ?? [];

  const nodes: AtlasNode[] = [];

  // ── Repo hub at the centre. The whole brain hangs off the project. ──
  nodes.push({
    id: REPO_ID,
    kind: 'repo',
    label: 'Jonnyton/Workflow',
    sub: 'the repo',
    refId: REPO_URL,
    x: CENTER.x,
    y: CENTER.y,
    r: 30,
    tone: 'repo'
  });

  // ── Wiki category hubs — inner ring around the repo, sized by count. The
  //    heaviest objects in the brain, so they sit close to the centre. ──
  const order: CategoryId[] = ['patch', 'plans', 'notes', 'concepts', 'drafts'];
  const innerPts = ring(order.length, 196, 150, -90);
  const maxCount = Math.max(1, ...order.map((c) => counts[c]));
  order.forEach((cat, i) => {
    const c = counts[cat];
    const r = 24 + Math.round(32 * Math.sqrt(c / maxCount));
    nodes.push({
      id: `hub:${cat}`,
      kind: 'hub',
      category: cat,
      label: CATEGORY_LABEL[cat],
      sub: `${c.toLocaleString()}`,
      count: c,
      x: innerPts[i].x,
      y: innerPts[i].y,
      r,
      tone: 'wiki'
    });
  });

  // ── Public goals — an outer ellipse (ember). Each label fans out radially:
  //    nodes right-of-centre anchor their label rightward, nodes left-of-centre
  //    anchor leftward, so labels never pile up at the poles and never clip the
  //    figure. We start at the 1-o'clock position so no label sits dead-centre
  //    at the top where left/right neighbours would collide. ──
  const goalRadiusX = 286;
  const goalRadiusY = 332;
  const goalPts = ring(publicGoals.length, goalRadiusX, goalRadiusY, -66);
  publicGoals.forEach((g, i) => {
    const x = goalPts[i].x;
    nodes.push({
      id: `goal:${g.id}`,
      kind: 'goal',
      label: g.name,
      short: truncate(g.name, 30),
      refId: g.id,
      x,
      y: goalPts[i].y,
      r: 8,
      side: x >= CENTER.x ? 'r' : 'l',
      tone: 'goal'
    });
  });

  // ── Universes — a clean column on the far left (violet), their own family,
  //    not mixed into the goal arc. Labels anchor rightward into the gap. ──
  const uGapY = Math.min(56, (CANVAS_H - 120) / Math.max(universes.length, 1));
  const uStartY = (CANVAS_H - uGapY * (universes.length - 1)) / 2;
  const uX = 120;
  universes.forEach((u, i) => {
    nodes.push({
      id: `universe:${u.id}`,
      kind: 'universe',
      label: u.id,
      short: truncate(u.id, 26),
      sub: u.phase ?? '',
      refId: u.id,
      x: uX,
      y: uStartY + i * uGapY,
      r: 7,
      side: 'r',
      tone: 'universe'
    });
  });

  // Repo connects to the plans hub: every reference edge in the snapshot
  // originates from a plan, so plans are the brain's wiring spine.
  if (counts.plans > 0) {
    edges.push({ from: REPO_ID, to: 'hub:plans', weight: 0 });
  }

  return {
    nodes,
    edges,
    pagesByCategory,
    counts,
    publicGoalCount: publicGoals.length,
    universeCount: universes.length,
    rawEdgeCount: raw,
    width: CANVAS_W,
    height: CANVAS_H
  };
}
