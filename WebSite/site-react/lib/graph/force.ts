/**
 * force.ts — the Obsidian-style force layout for /graph.
 *
 * Every wiki page is its own dot (1,200+ of them), clustered around its
 * category hub the way Obsidian notes cluster around tags. Two kinds of
 * links, drawn differently and disclosed honestly in the page legend:
 *
 *   - 'ref'    — a REAL page→page reference from the snapshot (deduped
 *                across ref/source kinds). These are the bright lines.
 *   - 'member' — filing: page→its category hub, goal→the goals hub,
 *                universe→the universes hub. Metadata, not citation;
 *                drawn as the faintest spokes.
 *
 * The simulation is d3-force (the way everyone does this): many-body
 * repulsion, link springs, weak centering, collision. Degree (real refs
 * only) sizes a page's dot.
 */
import {
  forceSimulation,
  forceLink,
  forceManyBody,
  forceX,
  forceY,
  forceCollide,
  type Simulation,
  type ForceLink
} from 'd3-force';
import type { CategoryId, Snapshotish, WikiPage } from './atlas';
import { isPublicGoal } from './atlas';

export type FKind = 'page' | 'tag' | 'goal' | 'universe';
export type FCluster = CategoryId | 'goals' | 'universes' | 'tags';

export type FNode = {
  id: string;
  kind: FKind;
  cluster: FCluster;
  label: string;
  /** wiki path for pages — feeds the copy-read-prompt bridge */
  path?: string;
  /** goal / universe id for navigation + panels */
  refId?: string;
  r: number;
  degree: number;
  count?: number;
  // d3-force mutates these:
  x?: number;
  y?: number;
  vx?: number;
  vy?: number;
  fx?: number | null;
  fy?: number | null;
};

export type FLink = {
  source: string | FNode;
  target: string | FNode;
  kind: 'ref' | 'member';
};

export type ForceGraph = {
  nodes: FNode[];
  links: FLink[];
  refLinkCount: number;
  /** real-reference neighbours + membership neighbours, for hover focus */
  adjacency: Map<string, Set<string>>;
  pageCount: number;
};

/** `pages/plans/foo.md` → `plan:foo`; `drafts/concepts/bar.md` → `draft:bar` */
function edgeIdFor(path: string): string | null {
  const base = path.split('/').pop()?.replace(/\.md$/, '');
  if (!base) return null;
  if (path.startsWith('drafts/')) return `draft:${base}`;
  const dir = path.split('/')[1];
  const prefix =
    dir === 'bugs' ? 'bug' : dir === 'notes' ? 'note' : dir === 'plans' ? 'plan' : dir === 'concepts' ? 'concept' : null;
  return prefix ? `${prefix}:${base}` : null;
}

export const CLUSTER_LABEL: Record<FCluster, string> = {
  patch: 'patch requests · bugs',
  notes: 'notes',
  plans: 'plans',
  concepts: 'concepts',
  drafts: 'drafts',
  goals: 'goals',
  universes: 'universes',
  tags: 'shared tags'
};

export function buildForceGraph(
  snap: Snapshotish,
  pagesByCategory: Record<CategoryId, WikiPage[]>
): ForceGraph {
  const nodes: FNode[] = [];
  const links: FLink[] = [];
  const byId = new Map<string, FNode>();

  const add = (n: FNode) => {
    nodes.push(n);
    byId.set(n.id, n);
  };

  // ── Category hubs (the "tags") ──
  const cats: CategoryId[] = ['patch', 'plans', 'notes', 'concepts', 'drafts'];
  const maxCount = Math.max(1, ...cats.map((c) => pagesByCategory[c].length));
  for (const cat of cats) {
    const count = pagesByCategory[cat].length;
    add({
      id: `tag:${cat}`,
      kind: 'tag',
      cluster: cat,
      label: CLUSTER_LABEL[cat],
      r: 7 + 11 * Math.sqrt(count / maxCount),
      degree: 0,
      count
    });
  }

  // ── Every page is a dot ──
  for (const cat of cats) {
    for (const p of pagesByCategory[cat]) {
      const id = edgeIdFor(p.path) ?? `page:${p.path}`;
      if (byId.has(id)) continue;
      add({ id, kind: 'page', cluster: cat, label: p.title, path: p.path, r: 1.8, degree: 0 });
      links.push({ source: id, target: `tag:${cat}`, kind: 'member' });
    }
  }

  // ── Goals + universes, each family around its own hub ──
  const goals = (snap.goals ?? []).filter(isPublicGoal);
  if (goals.length) {
    add({ id: 'tag:goals', kind: 'tag', cluster: 'goals', label: 'goals', r: 9, degree: 0, count: goals.length });
    for (const g of goals) {
      add({ id: `goal:${g.id}`, kind: 'goal', cluster: 'goals', label: g.name, refId: g.id, r: 3.6, degree: 0 });
      links.push({ source: `goal:${g.id}`, target: 'tag:goals', kind: 'member' });
    }
  }
  const universes = snap.universes ?? [];
  if (universes.length) {
    add({
      id: 'tag:universes',
      kind: 'tag',
      cluster: 'universes',
      label: 'universes',
      r: 8,
      degree: 0,
      count: universes.length
    });
    for (const u of universes) {
      add({ id: `universe:${u.id}`, kind: 'universe', cluster: 'universes', label: u.id, refId: u.id, r: 3.6, degree: 0 });
      links.push({ source: `universe:${u.id}`, target: 'tag:universes', kind: 'member' });
    }
  }

  // ── Real references, deduped (the snapshot doubles each as ref+source) ──
  const seen = new Set<string>();
  let refLinkCount = 0;
  for (const e of snap.edges ?? []) {
    const key = e.from < e.to ? `${e.from}|${e.to}` : `${e.to}|${e.from}`;
    if (seen.has(key)) continue;
    seen.add(key);
    const a = byId.get(e.from);
    const b = byId.get(e.to);
    if (!a || !b || a === b) continue;
    links.push({ source: a.id, target: b.id, kind: 'ref' });
    a.degree += 1;
    b.degree += 1;
    refLinkCount += 1;
  }

  // Degree sizes a page's dot — connected pages read as landmarks.
  let pageCount = 0;
  for (const n of nodes) {
    if (n.kind === 'page') {
      pageCount += 1;
      n.r = 1.8 + Math.min(4.5, Math.sqrt(n.degree) * 1.4);
    }
  }

  // ── Shared-tag relatedness ──
  // Pages carrying the same wiki tag cluster around a small tag hub, the way
  // Obsidian clusters notes under a tag. This is a WEAKER signal than a real
  // reference: it's drawn as faint 'member' spokes and labelled "shared tags",
  // never dressed up as a citation. Surfaces relatedness the snapshot already
  // knows about (the baked `tags` map) that would otherwise read as orphans.
  const GENERIC_TAGS = new Set([
    'bug', 'bugs', 'draft', 'drafts', 'wiki', 'public', 'universe', 'universes',
    'workflow', 'note', 'notes', 'plan', 'plans', 'concept', 'concepts'
  ]);
  const tagMembers = new Map<string, string[]>();
  for (const [nodeId, tagList] of Object.entries(snap.tags ?? {})) {
    if (!byId.has(nodeId)) continue;
    for (const raw of tagList ?? []) {
      const t = String(raw).trim().toLowerCase();
      if (!t || GENERIC_TAGS.has(t)) continue;
      const arr = tagMembers.get(t) ?? [];
      arr.push(nodeId);
      tagMembers.set(t, arr);
    }
  }
  for (const [t, members] of tagMembers) {
    const uniq = [...new Set(members)];
    if (uniq.length < 2) continue;
    const hubId = `tag:#${t}`;
    if (byId.has(hubId)) continue;
    add({
      id: hubId,
      kind: 'tag',
      cluster: 'tags',
      label: `#${t}`,
      r: 3.5 + 2 * Math.sqrt(uniq.length),
      degree: 0,
      count: uniq.length
    });
    for (const m of uniq) links.push({ source: m, target: hubId, kind: 'member' });
  }

  // Hover focus = direct neighbours over BOTH link kinds.
  const adjacency = new Map<string, Set<string>>();
  const addAdj = (a: string, b: string) => {
    if (!adjacency.has(a)) adjacency.set(a, new Set());
    adjacency.get(a)!.add(b);
  };
  for (const l of links) {
    const s = typeof l.source === 'string' ? l.source : l.source.id;
    const t = typeof l.target === 'string' ? l.target : l.target.id;
    addAdj(s, t);
    addAdj(t, s);
  }

  return { nodes, links, refLinkCount, adjacency, pageCount };
}

/**
 * Seed positions in cluster wedges (so the sim settles fast and predictably),
 * then hand the graph to d3-force with Obsidian-ish parameters.
 */
export function createSimulation(graph: ForceGraph): Simulation<FNode, undefined> {
  const clusters: FCluster[] = ['plans', 'patch', 'goals', 'notes', 'drafts', 'concepts', 'universes', 'tags'];
  const angleOf = new Map<FCluster, number>();
  clusters.forEach((c, i) => angleOf.set(c, (i / clusters.length) * Math.PI * 2 - Math.PI / 2));

  // Mulberry32 — deterministic seeding so reloads look the same.
  let seed = 0x6d2b79f5;
  const rng = () => {
    seed = (seed + 0x6d2b79f5) | 0;
    let t = Math.imul(seed ^ (seed >>> 15), 1 | seed);
    t = (t + Math.imul(t ^ (t >>> 7), 61 | t)) ^ t;
    return ((t ^ (t >>> 14)) >>> 0) / 4294967296;
  };

  for (const n of graph.nodes) {
    const a = angleOf.get(n.cluster) ?? 0;
    if (n.kind === 'tag') {
      n.x = Math.cos(a) * 220;
      n.y = Math.sin(a) * 220;
    } else {
      const jitterA = a + (rng() - 0.5) * 1.1;
      const jitterR = 140 + rng() * 240;
      n.x = Math.cos(jitterA) * jitterR;
      n.y = Math.sin(jitterA) * jitterR;
    }
  }

  const link = forceLink<FNode, FLink & { index?: number }>(graph.links as (FLink & { index?: number })[])
    .id((d) => d.id)
    .distance((l) => (l.kind === 'ref' ? 60 : 34))
    .strength((l) => (l.kind === 'ref' ? 0.26 : 0.05));

  return forceSimulation<FNode>(graph.nodes)
    .force('link', link as ForceLink<FNode, FLink>)
    .force(
      'charge',
      forceManyBody<FNode>()
        .strength((d) => (d.kind === 'tag' ? -320 : d.kind === 'page' ? -22 : -46))
        .distanceMax(720)
        .theta(0.9)
    )
    .force('x', forceX<FNode>(0).strength(0.026))
    .force('y', forceY<FNode>(0).strength(0.03))
    .force(
      'collide',
      forceCollide<FNode>()
        .radius((d) => d.r + 1.6)
        .strength(0.8)
    )
    .velocityDecay(0.32)
    .alpha(1)
    .alphaMin(0.015)
    .stop();
}
