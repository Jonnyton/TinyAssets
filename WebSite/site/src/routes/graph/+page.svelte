<!--
  /graph - whole-project atlas.
  Merges MCP snapshot nodes with repo/GitHub topology through a single
  ID-keyed node map. This is the "everything, no duplicates" surface.
-->
<script lang="ts">
  import baked from '$lib/content/mcp-snapshot.json';
  import repoBaked from '$lib/content/repo-snapshot.json';
  import { fetchLive, liveToSnapshotShape } from '$lib/mcp/live';
  import type { Snapshot, Edge } from '$lib/mcp/types';
  import RitualLabel from '$lib/components/Primitives/RitualLabel.svelte';
  import LiveBadge from '$lib/components/LiveBadge.svelte';

  type NodeType =
    | 'repo'
    | 'git'
    | 'area'
    | 'route'
    | 'branch'
    | 'goal'
    | 'universe'
    | 'bug'
    | 'concept'
    | 'note'
    | 'plan'
    | 'draft'
    | 'hub';
  type Lens = 'all' | 'loop' | 'repo' | 'writing' | 'coding' | 'website' | 'mcp';
  type SourceType = 'mcp' | 'repo' | 'website' | 'loop';

  type RepoSnapshot = {
    fetched_at: string;
    source: string;
    repo: {
      id: string;
      name: string;
      owner: string;
      remote_url: string;
      current_branch: string;
      head: string;
      main: string;
      dirty_note?: string;
    };
    branches: Array<{ id: string; name: string; kind: string; commit: string; date?: string; subject?: string }>;
    areas: Array<{ id: string; label: string; summary: string; paths?: string[] }>;
    workflow_branches: Array<{ id: string; name: string; area: string; state: string; summary: string }>;
    routes: Array<{ id: string; path: string; label: string; summary: string }>;
    edges: Array<Edge>;
  };

  type AtlasNode = {
    id: string;
    type: NodeType;
    title: string;
    summary: string;
    tags: string[];
    sources: SourceType[];
    paths: string[];
    lens: Lens[];
    x: number;
    y: number;
    vx: number;
    vy: number;
    r: number;
  };

  type AtlasEdge = Edge & { source?: SourceType; derived?: boolean };

  const W = 1220;
  const H = 780;
  const repoInitial = repoBaked as RepoSnapshot;

  const TYPE_META: Record<NodeType, { color: string; label: string; r: number }> = {
    repo: { color: '#e9d8a6', label: 'Repo', r: 18 },
    git: { color: '#94a3b8', label: 'Git branch', r: 10 },
    area: { color: '#67d2a1', label: 'Area', r: 13 },
    route: { color: '#e95d7b', label: 'Website', r: 10 },
    branch: { color: '#73a7ff', label: 'Workflow branch', r: 11 },
    goal: { color: 'var(--ember-600)', label: 'Work target', r: 13 },
    universe: { color: 'var(--signal-live)', label: 'Universe', r: 12 },
    bug: { color: 'var(--ember-500)', label: 'Bug', r: 6 },
    concept: { color: 'var(--violet-200)', label: 'Concept', r: 8 },
    note: { color: 'var(--violet-400)', label: 'Note', r: 8 },
    plan: { color: 'var(--ember-300)', label: 'Plan', r: 9 },
    draft: { color: 'var(--signal-idle)', label: 'Draft', r: 7 },
    hub: { color: '#f6c177', label: 'Relationship hub', r: 9 }
  };

  const GENERIC_TAGS = new Set(['bug', 'bugs', 'draft', 'wiki', 'public', 'universe', 'workflow']);

  const LENSES: Array<{ id: Lens; label: string }> = [
    { id: 'all', label: 'All' },
    { id: 'loop', label: 'Loop' },
    { id: 'repo', label: 'Repo' },
    { id: 'writing', label: 'Writing' },
    { id: 'coding', label: 'Coding' },
    { id: 'website', label: 'Website' },
    { id: 'mcp', label: 'MCP' }
  ];

  let snapshot: Snapshot = $state(baked as unknown as Snapshot);
  let repoSnapshot: RepoSnapshot = $state(repoInitial);
  let lens = $state<Lens>('all');
  let query = $state('');
  let active = $state<string | null>(null);
  let pinned = $state<string | null>('repo:Workflow');
  let mcpLoading = $state(false);
  let githubLoading = $state(false);
  let mcpError = $state<string | null>(null);
  let githubError = $state<string | null>(null);

  function slugId(path: string): string {
    return path.split('/').pop()?.replace(/\.md$/, '') ?? path;
  }

  function uniq<T>(items: T[]): T[] {
    return [...new Set(items.filter(Boolean))];
  }

  function hash(input: string): number {
    let value = 0;
    for (let i = 0; i < input.length; i++) value = (value * 31 + input.charCodeAt(i)) >>> 0;
    return value;
  }

  function anchorFor(type: NodeType): { x: number; y: number } {
    const anchors: Record<NodeType, { x: number; y: number }> = {
      repo: { x: 170, y: 150 },
      git: { x: 210, y: 330 },
      area: { x: 410, y: 250 },
      route: { x: 680, y: 150 },
      branch: { x: 650, y: 360 },
      goal: { x: 860, y: 310 },
      universe: { x: 410, y: 575 },
      bug: { x: 870, y: 560 },
      concept: { x: 1040, y: 430 },
      note: { x: 1040, y: 250 },
      plan: { x: 1030, y: 620 },
      draft: { x: 700, y: 640 },
      hub: { x: 590, y: 410 }
    };
    return anchors[type];
  }

  function seedNode(id: string, type: NodeType): Pick<AtlasNode, 'x' | 'y' | 'vx' | 'vy' | 'r'> {
    const anchor = anchorFor(type);
    const h = hash(id);
    const angle = (h % 628) / 100;
    const radius = 20 + (h % 90);
    return {
      x: Math.max(24, Math.min(W - 24, anchor.x + Math.cos(angle) * radius)),
      y: Math.max(24, Math.min(H - 24, anchor.y + Math.sin(angle) * radius)),
      vx: 0,
      vy: 0,
      r: TYPE_META[type].r
    };
  }

  function defaultLens(id: string, type: NodeType, sources: SourceType[], tags: string[]): Lens[] {
    const values: Lens[] = ['all'];
    if (sources.includes('repo') || type === 'repo' || type === 'git' || type === 'area' || type === 'branch') values.push('repo');
    if (sources.includes('mcp') || ['goal', 'universe', 'bug', 'concept', 'note', 'plan', 'draft'].includes(type)) values.push('mcp');
    if (sources.includes('website') || type === 'route' || id === 'area:website') values.push('website');
    if (
      sources.includes('loop') ||
      id === 'area:patch-loop' ||
      id === 'route:/loop' ||
      id.includes('change_loop') ||
      id.includes('patch_packet') ||
      tags.includes('patch-loop') ||
      ['bug:BUG-005', 'bug:BUG-009', 'bug:BUG-017', 'bug:BUG-019', 'bug:BUG-034', 'goal:4ff5862cc26d', 'goal:f10caea2e437'].includes(id)
    ) values.push('loop', 'coding');
    if (id.includes('fantasy') || id === 'area:fantasy-domain' || id === 'universe:concordance') values.push('writing');
    if (id === 'area:coding-system' || id.startsWith('branch:agent_team') || id.startsWith('branch:bug_to_patch') || tags.includes('agent-teams')) values.push('coding');
    return uniq(values);
  }

  function addNode(
    map: Map<string, AtlasNode>,
    node: {
      id: string;
      type: NodeType;
      title: string;
      summary?: string;
      tags?: string[];
      sources?: SourceType[];
      paths?: string[];
      lens?: Lens[];
    }
  ) {
    const existing = map.get(node.id);
    const sources = uniq([...(existing?.sources ?? []), ...(node.sources ?? [])]);
    const tags = uniq([...(existing?.tags ?? []), ...(node.tags ?? [])]);
    const lensValues = uniq([...(existing?.lens ?? []), ...(node.lens ?? []), ...defaultLens(node.id, node.type, sources, tags)]);
    const paths = uniq([...(existing?.paths ?? []), ...(node.paths ?? [])]);
    if (existing) {
      existing.title = existing.title || node.title;
      existing.summary = existing.summary || node.summary || node.title;
      existing.tags = tags;
      existing.sources = sources;
      existing.paths = paths;
      existing.lens = lensValues;
      return;
    }
    map.set(node.id, {
      id: node.id,
      type: node.type,
      title: node.title,
      summary: node.summary ?? node.title,
      tags,
      sources,
      paths,
      lens: lensValues,
      ...seedNode(node.id, node.type)
    });
  }

  function addEdge(edges: Map<string, AtlasEdge>, edge: AtlasEdge, nodes: Map<string, AtlasNode>) {
    if (!nodes.has(edge.from) || !nodes.has(edge.to)) return;
    const a = edge.from < edge.to ? edge.from : edge.to;
    const b = edge.from < edge.to ? edge.to : edge.from;
    const key = `${a}|${b}|${edge.kind ?? 'ref'}`;
    if (!edges.has(key)) edges.set(key, edge);
  }

  function wikiPageNodes(s: Snapshot, nodes: Map<string, AtlasNode>) {
    for (const bug of s.wiki?.bugs ?? []) {
      addNode(nodes, {
        id: `bug:${bug.id}`,
        type: 'bug',
        title: `${bug.id}: ${bug.title}`,
        summary: bug.slug ?? bug.title,
        tags: s.tags?.[`bug:${bug.id}`] ?? ['bug'],
        sources: ['mcp'],
        paths: bug.slug ? [bug.slug] : []
      });
    }
    for (const plan of s.wiki?.plans ?? []) addNode(nodes, { id: `plan:${slugId(plan.slug)}`, type: 'plan', title: plan.title, summary: plan.slug, tags: s.tags?.[`plan:${slugId(plan.slug)}`] ?? [], sources: ['mcp'], paths: [plan.slug] });
    for (const concept of s.wiki?.concepts ?? []) addNode(nodes, { id: `concept:${slugId(concept.slug)}`, type: 'concept', title: concept.title, summary: concept.slug, tags: s.tags?.[`concept:${slugId(concept.slug)}`] ?? [], sources: ['mcp'], paths: [concept.slug] });
    for (const note of s.wiki?.notes ?? []) addNode(nodes, { id: `note:${slugId(note.slug)}`, type: 'note', title: note.title, summary: note.slug, tags: s.tags?.[`note:${slugId(note.slug)}`] ?? [], sources: ['mcp'], paths: [note.slug] });
    for (const draft of s.wiki?.drafts ?? []) addNode(nodes, { id: `draft:${draft.slug}`, type: 'draft', title: draft.title, summary: draft.slug, tags: s.tags?.[`draft:${draft.slug}`] ?? [], sources: ['mcp'], paths: [draft.slug] });
  }

  function addHub(nodes: Map<string, AtlasNode>, id: string, title: string, summary: string, sources: SourceType[], lensValues?: Lens[]) {
    addNode(nodes, {
      id,
      type: 'hub',
      title,
      summary,
      sources,
      lens: lensValues
    });
  }

  function addCollectionEdges(
    nodes: Map<string, AtlasNode>,
    edges: Map<string, AtlasEdge>,
    hubId: string,
    targets: AtlasNode[],
    source: SourceType,
    kind = 'collection'
  ) {
    for (const target of targets) {
      addEdge(edges, { from: hubId, to: target.id, kind, source, derived: true }, nodes);
    }
  }

  function addRelationshipLayers(nodes: Map<string, AtlasNode>, edges: Map<string, AtlasEdge>, repoId: string) {
    const byType = (type: NodeType) => [...nodes.values()].filter((node) => node.type === type);
    const bugs = byType('bug');
    const goals = byType('goal');
    const universes = byType('universe');
    const drafts = byType('draft');
    const wikiPages = [...byType('bug'), ...byType('concept'), ...byType('note'), ...byType('plan'), ...byType('draft')];
    const gitBranches = byType('git');
    const areas = byType('area');

    addHub(nodes, 'hub:mcp-commons', 'MCP community wiki', 'Live MCP collection: work targets, universes, wiki pages, tags, and extracted references.', ['mcp'], ['all', 'mcp']);
    addHub(nodes, 'hub:wiki-pages', 'Wiki pages', 'Promoted and draft wiki pages returned by the public MCP feed.', ['mcp'], ['all', 'mcp']);
    addHub(nodes, 'hub:public-bugs', 'Public bug tracker', 'Every public BUG page belongs to the same MCP-backed bug tracker before stronger edges route it into the loop or a subsystem.', ['mcp'], ['all', 'mcp', 'loop', 'coding']);
    addHub(nodes, 'hub:public-goals', 'Work targets', 'Work-target records folded into the MCP community wiki.', ['mcp'], ['all', 'mcp']);
    addHub(nodes, 'hub:universes', 'Live universes', 'Universe rows currently visible through MCP.', ['mcp'], ['all', 'mcp', 'writing']);
    addHub(nodes, 'hub:wiki-drafts', 'Wiki drafts', 'Draft wiki pages are not loose debris; they are draft-state wiki material.', ['mcp'], ['all', 'mcp']);
    addHub(nodes, 'hub:github-branches', 'GitHub branches', 'Branch refs returned by GitHub or the local repo snapshot.', ['repo'], ['all', 'repo', 'coding']);

    addEdge(edges, { from: 'hub:mcp-commons', to: 'hub:wiki-pages', kind: 'collection', source: 'mcp', derived: true }, nodes);
    addEdge(edges, { from: 'hub:mcp-commons', to: 'hub:public-goals', kind: 'collection', source: 'mcp', derived: true }, nodes);
    addEdge(edges, { from: 'hub:mcp-commons', to: 'hub:universes', kind: 'collection', source: 'mcp', derived: true }, nodes);
    addEdge(edges, { from: 'hub:wiki-pages', to: 'hub:public-bugs', kind: 'collection', source: 'mcp', derived: true }, nodes);
    addEdge(edges, { from: 'hub:wiki-pages', to: 'hub:wiki-drafts', kind: 'collection', source: 'mcp', derived: true }, nodes);
    addEdge(edges, { from: repoId, to: 'hub:github-branches', kind: 'collection', source: 'repo', derived: true }, nodes);

    addCollectionEdges(nodes, edges, 'hub:public-bugs', bugs, 'mcp', 'tracked-in');
    addCollectionEdges(nodes, edges, 'hub:public-goals', goals, 'mcp');
    addCollectionEdges(nodes, edges, 'hub:universes', universes, 'mcp');
    addCollectionEdges(nodes, edges, 'hub:wiki-drafts', drafts, 'mcp');
    addCollectionEdges(nodes, edges, 'hub:wiki-pages', wikiPages.filter((node) => node.type !== 'bug' && node.type !== 'draft'), 'mcp');
    addCollectionEdges(nodes, edges, 'hub:github-branches', gitBranches, 'repo');
    addCollectionEdges(nodes, edges, repoId, areas, 'repo', 'contains');

    const tagged = new Map<string, AtlasNode[]>();
    for (const node of nodes.values()) {
      if (node.type === 'hub') continue;
      for (const tag of node.tags) {
        const normalized = tag.trim().toLowerCase();
        if (!normalized || GENERIC_TAGS.has(normalized)) continue;
        const bucket = tagged.get(normalized) ?? [];
        bucket.push(node);
        tagged.set(normalized, bucket);
      }
    }
    for (const [tag, targets] of tagged) {
      if (targets.length < 2) continue;
      const id = `hub:tag:${tag.replace(/[^a-z0-9]+/g, '-')}`;
      const sources = uniq(targets.flatMap((target) => target.sources));
      const source = sources.includes('mcp') ? 'mcp' : (sources[0] ?? 'repo');
      const sourceLenses = sources.filter((source) => source === 'mcp' || source === 'repo' || source === 'website' || source === 'loop') as Lens[];
      addHub(nodes, id, `#${tag}`, `Shared MCP/repo tag across ${targets.length} graph nodes.`, sources, ['all', ...sourceLenses]);
      addEdge(edges, { from: 'hub:mcp-commons', to: id, kind: 'tag', source, derived: true }, nodes);
      addCollectionEdges(nodes, edges, id, targets, source, 'tag');
    }
  }

  function buildAtlas(s: Snapshot, r: RepoSnapshot): { allNodes: AtlasNode[]; allEdges: AtlasEdge[] } {
    const nodes = new Map<string, AtlasNode>();
    const edgeMap = new Map<string, AtlasEdge>();

    addNode(nodes, {
      id: r.repo.id,
      type: 'repo',
      title: `${r.repo.owner}/${r.repo.name}`,
      summary: `${r.repo.remote_url} - current branch ${r.repo.current_branch} @ ${r.repo.head}. ${r.repo.dirty_note ?? ''}`,
      sources: ['repo'],
      paths: ['.']
    });
    for (const branch of r.branches ?? []) {
      addNode(nodes, {
        id: branch.id,
        type: 'git',
        title: branch.name,
        summary: `${branch.kind} branch @ ${branch.commit}${branch.subject ? ` - ${branch.subject}` : ''}`,
        sources: ['repo']
      });
    }
    for (const area of r.areas ?? []) {
      addNode(nodes, { id: area.id, type: 'area', title: area.label, summary: area.summary, sources: ['repo'], paths: area.paths ?? [] });
    }
    for (const branch of r.workflow_branches ?? []) {
      addNode(nodes, {
        id: branch.id,
        type: 'branch',
        title: branch.name,
        summary: `${branch.state} - ${branch.summary}`,
        tags: [branch.area, branch.state],
        sources: branch.id.includes('change_loop') || branch.id.includes('patch') || branch.id.includes('observation') ? ['repo', 'loop'] : ['repo']
      });
    }
    for (const route of r.routes ?? []) {
      addNode(nodes, { id: route.id, type: 'route', title: route.label, summary: `${route.path} - ${route.summary}`, sources: ['repo', 'website'], paths: [route.path] });
    }

    for (const goal of s.goals ?? []) {
      addNode(nodes, { id: `goal:${goal.id}`, type: 'goal', title: goal.name, summary: goal.summary, tags: goal.tags ?? [], sources: ['mcp'] });
    }
    for (const universe of s.universes ?? []) {
      addNode(nodes, {
        id: `universe:${universe.id}`,
        type: 'universe',
        title: universe.id,
        summary: `${universe.phase} - ${universe.word_count.toLocaleString()} words${universe.last_activity_at ? ` - last ${universe.last_activity_at}` : ''}`,
        tags: ['universe', universe.phase],
        sources: ['mcp']
      });
    }
    wikiPageNodes(s, nodes);

    for (const edge of s.edges ?? []) addEdge(edgeMap, { ...edge, source: 'mcp' }, nodes);
    for (const edge of r.edges ?? []) {
      const source: SourceType = edge.from.includes('patch-loop') || edge.to.includes('patch-loop') || edge.from.includes('change_loop') || edge.to.includes('change_loop') ? 'loop' : 'repo';
      addEdge(edgeMap, { ...edge, source }, nodes);
    }
    addRelationshipLayers(nodes, edgeMap, r.repo.id);

    return { allNodes: [...nodes.values()], allEdges: [...edgeMap.values()] };
  }

  function matchesLens(node: AtlasNode): boolean {
    if (lens === 'all') return true;
    return node.lens.includes(lens);
  }

  function matchesQuery(node: AtlasNode): boolean {
    const q = query.trim().toLowerCase();
    if (!q) return true;
    return [node.id, node.title, node.summary, ...node.tags, ...node.paths].join(' ').toLowerCase().includes(q);
  }

  function runSimulation(inputNodes: AtlasNode[], inputEdges: AtlasEdge[]): AtlasNode[] {
    const nodes = inputNodes.map((node) => ({ ...node, ...seedNode(node.id, node.type) }));
    const idIndex = new Map(nodes.map((node, index) => [node.id, index]));
    const links = inputEdges.flatMap((edge) => {
      const from = idIndex.get(edge.from);
      const to = idIndex.get(edge.to);
      return from !== undefined && to !== undefined ? [[from, to]] : [];
    });
    const repulsion = 1700;
    const springK = 0.02;
    const springLen = lens === 'all' ? 120 : 105;
    const centerK = 0.004;
    const damping = 0.78;

    for (let iter = 0; iter < 300; iter++) {
      for (let i = 0; i < nodes.length; i++) {
        const a = nodes[i];
        for (let j = i + 1; j < nodes.length; j++) {
          const b = nodes[j];
          const dx = a.x - b.x;
          const dy = a.y - b.y;
          const d2 = Math.max(dx * dx + dy * dy, 144);
          const d = Math.sqrt(d2);
          const force = repulsion / d2;
          const fx = (dx / d) * force;
          const fy = (dy / d) * force;
          a.vx += fx;
          a.vy += fy;
          b.vx -= fx;
          b.vy -= fy;
        }
        const anchor = anchorFor(a.type);
        a.vx += (anchor.x - a.x) * centerK;
        a.vy += (anchor.y - a.y) * centerK;
      }
      for (const [from, to] of links) {
        const a = nodes[from];
        const b = nodes[to];
        const dx = b.x - a.x;
        const dy = b.y - a.y;
        const d = Math.sqrt(dx * dx + dy * dy) || 1;
        const force = (d - springLen) * springK;
        const fx = (dx / d) * force;
        const fy = (dy / d) * force;
        a.vx += fx;
        a.vy += fy;
        b.vx -= fx;
        b.vy -= fy;
      }
      for (const node of nodes) {
        node.vx *= damping;
        node.vy *= damping;
        node.x = Math.max(22, Math.min(W - 22, node.x + node.vx));
        node.y = Math.max(22, Math.min(H - 22, node.y + node.vy));
      }
    }
    return nodes;
  }

  const atlas = $derived.by(() => buildAtlas(snapshot, repoSnapshot));
  const filteredBaseNodes = $derived.by(() => atlas.allNodes.filter((node) => matchesLens(node) && matchesQuery(node)));
  const filteredIdSet = $derived.by(() => new Set(filteredBaseNodes.map((node) => node.id)));
  const filteredEdges = $derived.by(() => atlas.allEdges.filter((edge) => filteredIdSet.has(edge.from) && filteredIdSet.has(edge.to)));
  const nodes = $derived.by(() => runSimulation(filteredBaseNodes, filteredEdges));
  const edges = $derived(filteredEdges);
  const nodeById = $derived(new Map(nodes.map((node) => [node.id, node])));
  const allNodeById = $derived(new Map(atlas.allNodes.map((node) => [node.id, node])));
  const visible = $derived(pinned ?? active);
  const visibleNode = $derived(visible ? nodeById.get(visible) ?? allNodeById.get(visible) ?? null : null);
  const neighborIds = $derived.by(() => {
    if (!visibleNode) return new Set<string>();
    const ids = new Set<string>([visibleNode.id]);
    for (const edge of atlas.allEdges) {
      if (edge.from === visibleNode.id) ids.add(edge.to);
      if (edge.to === visibleNode.id) ids.add(edge.from);
    }
    return ids;
  });
  const neighbors = $derived.by(() => [...neighborIds].filter((id) => id !== visibleNode?.id).map((id) => allNodeById.get(id)).filter(Boolean).slice(0, 16) as AtlasNode[]);
  const orphanCount = $derived.by(() => {
    const connected = new Set<string>();
    for (const edge of atlas.allEdges) {
      connected.add(edge.from);
      connected.add(edge.to);
    }
    return atlas.allNodes.filter((node) => !connected.has(node.id)).length;
  });
  const hubCount = $derived(atlas.allNodes.filter((node) => node.type === 'hub').length);
  const searchResults = $derived.by(() => filteredBaseNodes.slice(0, 18));

  function pin(id: string, ev?: MouseEvent) {
    ev?.stopPropagation();
    pinned = pinned === id ? null : id;
  }

  async function refreshMcp() {
    mcpLoading = true;
    try {
      const live = await fetchLive();
      snapshot = liveToSnapshotShape(live, baked as unknown as Snapshot);
      mcpError = null;
    } catch (error: any) {
      mcpError = error?.message ?? String(error);
    } finally {
      mcpLoading = false;
    }
  }

  async function refreshGithub() {
    githubLoading = true;
    try {
      const [repoRes, branchesRes] = await Promise.all([
        fetch('https://api.github.com/repos/Jonnyton/Workflow'),
        fetch('https://api.github.com/repos/Jonnyton/Workflow/branches?per_page=100')
      ]);
      if (!repoRes.ok) throw new Error(`repo ${repoRes.status}`);
      if (!branchesRes.ok) throw new Error(`branches ${branchesRes.status}`);
      const repo = await repoRes.json();
      const branches = await branchesRes.json();
      const mergedBranches = new Map(repoSnapshot.branches.map((branch) => [branch.id, branch]));
      for (const branch of branches) {
        const id = `git:${branch.name}`;
        mergedBranches.set(id, {
          ...(mergedBranches.get(id) ?? {}),
          id,
          name: branch.name,
          kind: 'github',
          commit: branch.commit?.sha?.slice(0, 7) ?? '',
          subject: branch.protected ? 'protected branch' : 'branch'
        });
      }
      repoSnapshot = {
        ...repoSnapshot,
        fetched_at: new Date().toISOString(),
        source: 'GitHub API live',
        repo: {
          ...repoSnapshot.repo,
          remote_url: repo.html_url,
          main: repo.default_branch,
          dirty_note: `GitHub live refresh. Default branch ${repo.default_branch}; pushed ${repo.pushed_at}.`
        },
        branches: [...mergedBranches.values()]
      };
      githubError = null;
    } catch (error: any) {
      githubError = error?.message ?? String(error);
    } finally {
      githubLoading = false;
    }
  }
</script>

<svelte:head>
  <title>Graph - Workflow</title>
  <meta name="description" content="Whole-project graph of Workflow: MCP community wiki, work targets, live universes, GitHub repo, branches, site pages, and project areas." />
</svelte:head>

<section class="hero">
  <div class="container">
    <div class="head__row">
      <RitualLabel color="var(--violet-400)">· Whole-project atlas · deduped by node ID ·</RitualLabel>
      <LiveBadge fetchedAt={snapshot.fetched_at} source={snapshot.source} loading={mcpLoading} />
    </div>
    <h1>Everything, wired up.</h1>
    <p class="lead">
      The graph now merges the live MCP community wiki with the real repo surface: GitHub branches, project areas, website pages, workflow branches, work targets, universes, bugs, notes, plans, and the patch loop. Collection and tag layers keep real project objects connected without hiding which edges are explicit evidence.
    </p>
  </div>
</section>

<section class="atlas">
  <div class="atlas__shell">
    <aside class="control-panel" aria-label="Graph controls">
      <div class="metric-grid">
        <div><strong>{atlas.allNodes.length}</strong><span>unique nodes</span></div>
        <div><strong>{atlas.allEdges.length}</strong><span>edges</span></div>
        <div><strong>{hubCount}</strong><span>relation hubs</span></div>
        <div><strong>{orphanCount}</strong><span>isolated</span></div>
      </div>

      <label class="search">
        <span>Search graph</span>
        <input bind:value={query} type="search" placeholder="BUG-034, loop, repo, writing..." />
      </label>

      <div class="lenses" aria-label="Graph lenses">
        {#each LENSES as item}
          <button class:selected={lens === item.id} aria-pressed={lens === item.id} onclick={() => (lens = item.id)}>{item.label}</button>
        {/each}
      </div>

      <div class="refresh-row">
        <button onclick={refreshMcp} disabled={mcpLoading} aria-busy={mcpLoading}>Refresh MCP</button>
        <button onclick={refreshGithub} disabled={githubLoading} aria-busy={githubLoading}>Refresh GitHub</button>
      </div>
      {#if mcpError}<p class="inline-error">MCP refresh failed: {mcpError}</p>{/if}
      {#if githubError}<p class="inline-error">GitHub refresh failed: {githubError}</p>{/if}

      <div class="source-note">
        <strong>{repoSnapshot.repo.owner}/{repoSnapshot.repo.name}</strong>
        <span>head {repoSnapshot.repo.head} · {repoSnapshot.branches.length} GitHub branches</span>
        <details class="source-note__raw">
          <summary>Raw dev snapshot</summary>
          <small>{repoSnapshot.repo.current_branch} · {repoSnapshot.repo.dirty_note ?? 'No dirty-worktree note recorded.'}</small>
        </details>
      </div>

      <div class="quick-list">
        <h2>{query ? 'Matches' : 'Visible nodes'}</h2>
        {#each searchResults as node}
          <button class:selected={pinned === node.id} onclick={(event) => pin(node.id, event)}>
            <span class="type-dot" style:background={TYPE_META[node.type].color}></span>
            <span>{node.title}</span>
          </button>
        {/each}
      </div>
    </aside>

    <div class="graph-stage">
      <div class="graph-stage__top">
        <div>
          <h2>{LENSES.find((item) => item.id === lens)?.label ?? 'All'} lens</h2>
          <p>{nodes.length} visible nodes from {atlas.allNodes.length} unique project nodes. Strong edges are explicit references; faint dashed edges are true collection/tag relationships from MCP and GitHub.</p>
        </div>
        <div class="legend">
          {#each Object.entries(TYPE_META) as [type, meta]}
            <span><i style:background={meta.color}></i>{meta.label}</span>
          {/each}
        </div>
      </div>

      <svg viewBox="0 0 {W} {H}" preserveAspectRatio="xMidYMid meet" class="graph" onclick={() => (pinned = null)} role="presentation">
        <g class="edges">
          {#each edges as edge (edge.from + '|' + edge.to + '|' + (edge.kind ?? 'ref'))}
            {@const from = nodeById.get(edge.from)}
            {@const to = nodeById.get(edge.to)}
            {#if from && to}
              <line
                x1={from.x}
                y1={from.y}
                x2={to.x}
                y2={to.y}
                class="edge"
                class:hot={visibleNode && neighborIds.has(edge.from) && neighborIds.has(edge.to)}
                class:loop={edge.source === 'loop'}
                class:derived={edge.derived}
              />
            {/if}
          {/each}
        </g>
        <g class="nodes">
          {#each nodes as node (node.id)}
            <g
              class="node"
              class:dim={visibleNode && !neighborIds.has(node.id)}
              class:hot={visibleNode && neighborIds.has(node.id)}
              class:pinned={pinned === node.id}
              transform="translate({node.x},{node.y})"
              onmouseenter={() => (active = node.id)}
              onmouseleave={() => (active = null)}
              onclick={(event) => pin(node.id, event)}
              onkeydown={(event) => {
                if (event.key === 'Enter' || event.key === ' ') {
                  event.preventDefault();
                  pin(node.id);
                }
              }}
              role="button"
              tabindex="0"
              aria-label={node.title}
            >
              <circle class="node__halo" r={node.r + 6} />
              <circle class="node__core" r={node.r} style:fill={TYPE_META[node.type].color} />
              {#if node.type === 'repo' || node.type === 'hub' || node.type === 'area' || node.type === 'route' || node.type === 'branch' || node.type === 'goal' || pinned === node.id || active === node.id}
                <text x={node.r + 7} y="4">{node.title}</text>
              {/if}
            </g>
          {/each}
        </g>
      </svg>
    </div>

    <aside class="detail-panel" aria-label="Selected node detail">
      {#if visibleNode}
        <RitualLabel color={TYPE_META[visibleNode.type].color}>· {TYPE_META[visibleNode.type].label} ·</RitualLabel>
        <h2>{visibleNode.title}</h2>
        <p>{visibleNode.summary}</p>
        <code>{visibleNode.id}</code>
        <div class="chips">
          {#each visibleNode.sources as source}
            <span>{source}</span>
          {/each}
          {#each visibleNode.tags.slice(0, 5) as tag}
            <span>{tag}</span>
          {/each}
        </div>
        {#if visibleNode.paths.length}
          <div class="paths">
            <h3>Paths</h3>
            {#each visibleNode.paths.slice(0, 6) as path}
              <small>{path}</small>
            {/each}
          </div>
        {/if}
        <div class="neighbors">
          <h3>Neighbors</h3>
          {#if neighbors.length}
            {#each neighbors as neighbor}
              <button onclick={(event) => pin(neighbor.id, event)}>
                <span class="type-dot" style:background={TYPE_META[neighbor.type].color}></span>
                <span>{neighbor.title}</span>
              </button>
            {/each}
          {:else}
            <p>No visible relationships. This is a true orphan in the current graph, not just a node waiting for collection or tag context.</p>
          {/if}
        </div>
        {#if pinned}<button class="unpin" onclick={(event) => { event.stopPropagation(); pinned = null; }}>Unpin</button>{/if}
      {:else}
        <RitualLabel>· Select a node ·</RitualLabel>
        <p class="empty">Hover or click any node. The panel shows source layers, paths, tags, and neighboring nodes so you can traverse the project like a knowledge graph.</p>
      {/if}
    </aside>
  </div>
</section>

<style>
  .hero { padding: 72px 0 28px; border-bottom: 1px solid var(--border-1); }
  .head__row { display: flex; align-items: center; justify-content: space-between; flex-wrap: wrap; gap: 12px; margin-bottom: 10px; }
  h1 { font-family: var(--font-display); font-size: clamp(48px, 8vw, 76px); font-weight: 400; letter-spacing: 0; line-height: 0.96; margin: 12px 0 16px; }
  .lead { color: var(--fg-2); font-size: 16px; line-height: 1.65; max-width: 76ch; margin: 0; }

  .atlas { padding: 20px clamp(12px, 2.5vw, 28px) 56px; }
  .atlas__shell {
    max-width: 1480px;
    margin: 0 auto;
    display: grid;
    grid-template-columns: 280px minmax(0, 1fr) 310px;
    gap: 14px;
    align-items: start;
  }
  .control-panel,
  .graph-stage,
  .detail-panel {
    border: 1px solid var(--border-1);
    border-radius: 8px;
    background: var(--bg-2);
  }
  .control-panel,
  .detail-panel {
    padding: 14px;
    position: sticky;
    top: 84px;
  }
  .metric-grid {
    display: grid;
    grid-template-columns: repeat(2, 1fr);
    overflow: hidden;
    border: 1px solid var(--border-1);
    border-radius: 8px;
    background: var(--bg-inset);
  }
  .metric-grid div { display: grid; gap: 3px; padding: 10px 8px; border-left: 1px solid var(--border-1); }
  .metric-grid div:nth-child(odd) { border-left: 0; }
  .metric-grid div:nth-child(n + 3) { border-top: 1px solid var(--border-1); }
  .metric-grid strong { color: var(--fg-1); font-family: var(--font-display); font-size: 24px; line-height: 1; font-weight: 500; }
  .metric-grid span { color: var(--fg-3); font-family: var(--font-mono); font-size: 10px; text-transform: uppercase; }

  .search { display: grid; gap: 7px; margin: 14px 0; }
  .search span,
  .quick-list h2,
  .paths h3,
  .neighbors h3 {
    color: var(--fg-3);
    font-family: var(--font-mono);
    font-size: 10.5px;
    font-weight: 500;
    text-transform: uppercase;
  }
  .search input {
    width: 100%;
    border: 1px solid var(--border-1);
    border-radius: 7px;
    background: var(--bg-inset);
    color: var(--fg-1);
    padding: 10px 11px;
    font: inherit;
  }
  .lenses { display: grid; grid-template-columns: repeat(2, 1fr); gap: 7px; }
  .lenses button,
  .refresh-row button,
  .quick-list button,
  .neighbors button,
  .unpin {
    border: 1px solid var(--border-1);
    border-radius: 7px;
    background: var(--bg-inset);
    color: var(--fg-2);
    cursor: pointer;
  }
  .lenses button,
  .refresh-row button,
  .unpin {
    min-height: 34px;
    font-family: var(--font-mono);
    font-size: 11px;
    text-transform: uppercase;
  }
  .lenses button:hover,
  .lenses button.selected,
  .quick-list button:hover,
  .quick-list button.selected,
  .neighbors button:hover {
    border-color: rgba(204, 120, 92, 0.65);
    color: var(--fg-1);
    background: rgba(204, 120, 92, 0.075);
  }
  .refresh-row { display: grid; grid-template-columns: 1fr 1fr; gap: 8px; margin: 12px 0; }
  .refresh-row button:disabled { opacity: 0.55; cursor: wait; }
  .inline-error { color: var(--signal-error); font-family: var(--font-mono); font-size: 11px; line-height: 1.45; margin: 8px 0; }
  .source-note {
    display: grid;
    gap: 4px;
    margin: 12px 0;
    padding: 10px;
    border-left: 2px solid rgba(103, 210, 161, 0.6);
    background: rgba(103, 210, 161, 0.055);
  }
  .source-note strong { color: var(--fg-1); font-size: 13px; }
  .source-note span,
  .source-note small { color: var(--fg-3); font-family: var(--font-mono); font-size: 10.5px; line-height: 1.45; }
  .source-note__raw summary { color: var(--fg-3); cursor: pointer; font-family: var(--font-mono); font-size: 10px; text-transform: uppercase; width: fit-content; }

  .quick-list { display: grid; gap: 7px; max-height: 360px; overflow: auto; padding-right: 3px; }
  .quick-list h2 { margin: 4px 0; }
  .quick-list button,
  .neighbors button {
    display: grid;
    grid-template-columns: auto minmax(0, 1fr);
    gap: 8px;
    align-items: center;
    min-height: 34px;
    padding: 7px 8px;
    text-align: left;
    font-size: 12px;
  }
  .type-dot { width: 9px; height: 9px; border-radius: 50%; }

  .graph-stage { overflow: hidden; }
  .graph-stage__top {
    display: grid;
    grid-template-columns: minmax(0, 1fr) minmax(220px, 0.8fr);
    gap: 12px;
    align-items: start;
    padding: 14px 16px;
    border-bottom: 1px solid var(--border-1);
  }
  .graph-stage__top h2 {
    color: var(--fg-1);
    font-family: var(--font-display);
    font-size: 26px;
    font-weight: 500;
    letter-spacing: 0;
    margin: 0 0 4px;
  }
  .graph-stage__top p { color: var(--fg-3); font-size: 13px; line-height: 1.5; margin: 0; }
  .legend { display: flex; flex-wrap: wrap; justify-content: flex-end; gap: 7px 10px; }
  .legend span { display: inline-flex; align-items: center; gap: 5px; color: var(--fg-3); font-family: var(--font-mono); font-size: 10px; text-transform: uppercase; }
  .legend i { width: 8px; height: 8px; border-radius: 50%; }
  .graph {
    display: block;
    width: 100%;
    aspect-ratio: 1220 / 780;
    min-height: 0;
    background: radial-gradient(circle at 50% 50%, rgba(255, 255, 255, 0.035), rgba(255, 255, 255, 0) 38%), var(--bg-inset);
  }
  .edge { stroke: rgba(255, 255, 255, 0.16); stroke-width: 1; transition: stroke var(--dur-base), opacity var(--dur-base), stroke-width var(--dur-base); }
  .edge.derived { stroke: rgba(246, 193, 119, 0.24); stroke-dasharray: 4 7; opacity: 0.62; }
  .edge.loop { stroke: rgba(233, 93, 123, 0.38); stroke-width: 1.2; }
  .edge.hot { stroke: var(--ember-600); stroke-width: 2; opacity: 0.9; stroke-dasharray: none; }
  .node { cursor: pointer; outline: none; }
  .node__halo { fill: transparent; stroke: currentColor; stroke-width: 0; opacity: 0; transition: opacity var(--dur-fast), stroke-width var(--dur-fast); }
  .node__core { transition: opacity var(--dur-base), filter var(--dur-fast); }
  .node text {
    fill: var(--fg-2);
    font-family: var(--font-mono);
    font-size: 10px;
    pointer-events: none;
    paint-order: stroke;
    stroke: var(--bg-inset);
    stroke-width: 3px;
  }
  .node:hover .node__halo,
  .node.hot .node__halo,
  .node.pinned .node__halo { opacity: 0.8; stroke-width: 2; }
  .node.pinned .node__halo { stroke: var(--ember-600); stroke-width: 3; }
  .node.dim .node__core,
  .node.dim text { opacity: 0.18; }
  .node.hot .node__core,
  .node.pinned .node__core { filter: drop-shadow(0 0 6px currentColor); }

  .detail-panel h2 {
    color: var(--fg-1);
    font-family: var(--font-display);
    font-size: 24px;
    font-weight: 500;
    letter-spacing: 0;
    line-height: 1.1;
    margin: 10px 0 8px;
  }
  .detail-panel p,
  .empty {
    color: var(--fg-2);
    font-size: 13.5px;
    line-height: 1.6;
    margin: 0 0 12px;
  }
  .detail-panel code {
    display: block;
    color: var(--violet-200);
    background: var(--bg-inset);
    border: 1px solid var(--border-1);
    border-radius: 6px;
    padding: 7px 8px;
    font-family: var(--font-mono);
    font-size: 11px;
    overflow-wrap: anywhere;
  }
  .chips { display: flex; flex-wrap: wrap; gap: 6px; margin: 12px 0; }
  .chips span {
    border: 1px solid var(--border-1);
    border-radius: 999px;
    padding: 3px 8px;
    color: var(--fg-3);
    font-family: var(--font-mono);
    font-size: 10px;
    text-transform: uppercase;
  }
  .paths,
  .neighbors { display: grid; gap: 7px; margin-top: 14px; }
  .paths small {
    color: var(--fg-3);
    background: var(--bg-inset);
    border: 1px solid var(--border-1);
    border-radius: 5px;
    padding: 6px 7px;
    font-family: var(--font-mono);
    font-size: 10.5px;
    overflow-wrap: anywhere;
  }
  .neighbors p { color: var(--fg-3); font-size: 13px; line-height: 1.5; margin: 0; }
  .unpin { width: 100%; margin-top: 14px; }

  @media (max-width: 1180px) {
    .atlas__shell { grid-template-columns: 260px minmax(0, 1fr); }
    .detail-panel { grid-column: 1 / -1; position: static; }
  }
  @media (max-width: 820px) {
    .hero { padding-top: 54px; }
    .atlas__shell,
    .graph-stage__top { grid-template-columns: 1fr; }
    .graph-stage { order: -1; }
    .control-panel { order: 0; }
    .detail-panel { order: 1; }
    .control-panel { position: static; }
    .legend { justify-content: flex-start; }
    .graph-stage__top { padding: 12px; }
    .legend { max-height: 68px; overflow: hidden; }
  }
  @media (max-width: 560px) {
    .atlas { padding-inline: 10px; }
    .metric-grid { grid-template-columns: 1fr; }
    .metric-grid div { border-left: 0; border-top: 1px solid var(--border-1); }
    .metric-grid div:first-child { border-top: 0; }
    .lenses { grid-template-columns: 1fr; }
  }
</style>
