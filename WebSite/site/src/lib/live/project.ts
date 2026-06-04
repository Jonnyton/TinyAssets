import bakedMcp from '$lib/content/mcp-snapshot.json';
import bakedRepo from '$lib/content/repo-snapshot.json';
import { fetchLive, liveToSnapshotShape } from '$lib/mcp/live';
import type { Snapshot } from '$lib/mcp/types';

export type RepoBranch = {
  id: string;
  name: string;
  kind: string;
  commit: string;
  date?: string;
  subject?: string;
};

export type RepoArea = {
  id: string;
  label: string;
  kind?: string;
  description?: string;
};

export type RepoRoute = {
  id: string;
  path: string;
  label: string;
  lens?: string;
};

export type RepoSnapshot = {
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
    default_branch?: string;
    pushed_at?: string;
    open_issues?: number;
    watchers?: number;
  };
  branches: RepoBranch[];
  areas: RepoArea[];
  workflow_branches: Array<Record<string, any>>;
  routes: RepoRoute[];
  edges: Array<Record<string, any>>;
};

export type ProjectPulse = {
  mcp: Snapshot;
  repo: RepoSnapshot;
  knowledgeCount: number;
  branchCount: number;
  routeCount: number;
  activeUniverse: Snapshot['universes'][number] | null;
  currentGoal: Snapshot['goals'][number] | null;
  currentBug: Snapshot['wiki']['bugs'][number] | null;
};

export type LensKey =
  | 'home'
  | 'status'
  | 'connect'
  | 'goals'
  | 'host'
  | 'economy'
  | 'alliance';

export type LensDefinition = {
  eyebrow: string;
  title: string;
  question: string;
  watches: string;
  proof: string;
  primaryHref: string;
  primaryLabel: string;
};

export const initialMcpSnapshot = bakedMcp as Snapshot;
export const initialRepoSnapshot = bakedRepo as RepoSnapshot;

export const LENS_DEFINITIONS: Record<LensKey, LensDefinition> = {
  home: {
    eyebrow: 'Live command center',
    title: 'Use Workflow. Watch it work. Help build it.',
    question: 'Workflow lets your chatbot design and run real multi-step work through MCP. Connect it, open the live graph, or join the loop; each path reads current MCP and GitHub state.',
    watches: 'MCP commons + GitHub repo pulse',
    proof: 'Refresh either side; the readout below changes from the same sources the rest of the site uses.',
    primaryHref: '/graph',
    primaryLabel: 'Open whole-project graph'
  },
  status: {
    eyebrow: 'Operations room',
    title: 'Public health, current work, and deployment pulse.',
    question: 'Status answers: is the system alive, and what evidence says so?',
    watches: 'Connector freshness, repo head, visible universe state',
    proof: 'The controls are probes, not decoration: failed refreshes render as page-level evidence.',
    primaryHref: '/fine-print',
    primaryLabel: 'Read operations room'
  },
  connect: {
    eyebrow: 'Connector proof',
    title: 'The same MCP surface your chatbot will use.',
    question: 'Connect answers: can a browser prove the connector is reachable before I paste the URL?',
    watches: 'tinyassets.io/mcp read path',
    proof: 'The MCP refresh uses the dev proxy in preview and the same public route in production.',
    primaryHref: '/connect',
    primaryLabel: 'Copy connector URL'
  },
  goals: {
    eyebrow: 'Goal lens',
    title: 'Goals first; branches compete underneath.',
    question: 'Goals answers: what public work targets exist, and which ones can be remixed or routed into the loop?',
    watches: 'Public goals, related commons, repo branches',
    proof: 'The goal board is connector data first; related wiki records and branch signals are derived from current MCP/GitHub state.',
    primaryHref: '/goals',
    primaryLabel: 'Browse goals'
  },
  host: {
    eyebrow: 'Daemon fleet',
    title: 'Hosts are capacity for live work.',
    question: 'Host answers: what could a daemon run, and what release surface would host it?',
    watches: 'Universes, branches, release surfaces',
    proof: 'Universe rows are real connector state; installer and hosted-cloud controls stay honest about availability.',
    primaryHref: '/host',
    primaryLabel: 'Inspect host modes'
  },
  economy: {
    eyebrow: 'Settlement ledger',
    title: 'Work, gates, credit, and token rails.',
    question: 'Economy answers: what real work could eventually settle into value?',
    watches: 'Goals, gates, work packets, test tiny boundary',
    proof: 'Current reads stay on project state; real Destiny (tiny) contracts are reference-only until integration opens.',
    primaryHref: '/economy',
    primaryLabel: 'Read economy boundary'
  },
  alliance: {
    eyebrow: 'Community intake',
    title: 'Intent enters the same live loop.',
    question: 'Alliance answers: where does a feature request, bug, or partnership enter public work?',
    watches: 'Commons intake, goals, GitHub channels',
    proof: 'Every written channel routes back into the same public loop: wiki, goal, branch, or repo thread.',
    primaryHref: '/alliance',
    primaryLabel: 'Choose an intake path'
  }
};

export function createPulse(mcp: Snapshot = initialMcpSnapshot, repo: RepoSnapshot = initialRepoSnapshot): ProjectPulse {
  const knowledgeCount =
    mcp.wiki.bugs.length +
    mcp.wiki.concepts.length +
    mcp.wiki.notes.length +
    mcp.wiki.plans.length +
    mcp.wiki.drafts.length +
    (mcp.wiki.other?.length ?? 0);

  return {
    mcp,
    repo,
    knowledgeCount,
    branchCount: repo.branches.length + repo.workflow_branches.length,
    routeCount: repo.routes.length,
    activeUniverse: mcp.universes[0] ?? null,
    currentGoal: mcp.goals[0] ?? null,
    currentBug: mcp.wiki.bugs[0] ?? null
  };
}

export async function refreshMcpSnapshot(current: Snapshot = initialMcpSnapshot): Promise<Snapshot> {
  const live = await fetchLive();
  return liveToSnapshotShape(live, current);
}

export async function refreshRepoSnapshot(current: RepoSnapshot = initialRepoSnapshot): Promise<RepoSnapshot> {
  const [repoRes, branchesRes] = await Promise.all([
    fetch('https://api.github.com/repos/Jonnyton/Workflow'),
    fetch('https://api.github.com/repos/Jonnyton/Workflow/branches?per_page=100')
  ]);
  if (!repoRes.ok) throw new Error(`repo ${repoRes.status}`);
  if (!branchesRes.ok) throw new Error(`branches ${branchesRes.status}`);

  const repo = await repoRes.json();
  const branches = await branchesRes.json();
  const liveBranches: RepoBranch[] = branches.map((branch: any) => ({
    id: `git:${branch.name}`,
    name: branch.name,
    kind: branch.name === repo.default_branch ? 'default' : 'remote',
    commit: branch.commit?.sha?.slice(0, 7) ?? '',
    subject: branch.protected ? 'protected branch' : 'GitHub branch',
    date: repo.pushed_at
  }));

  return {
    ...current,
    fetched_at: new Date().toISOString(),
    source: 'GitHub API live',
    repo: {
      ...current.repo,
      owner: repo.owner?.login ?? current.repo.owner,
      name: repo.name ?? current.repo.name,
      remote_url: repo.html_url ?? current.repo.remote_url,
      default_branch: repo.default_branch,
      pushed_at: repo.pushed_at,
      open_issues: repo.open_issues_count,
      watchers: repo.watchers_count
    },
    branches: liveBranches.length ? liveBranches : current.branches
  };
}

export function shortHash(value: string | undefined): string {
  if (!value) return 'unknown';
  return value.length > 7 ? value.slice(0, 7) : value;
}

export function compactNumber(value: number | undefined | null): string {
  if (value === undefined || value === null) return '0';
  return new Intl.NumberFormat('en-US', { notation: value >= 10000 ? 'compact' : 'standard' }).format(value);
}

export function relativeStamp(value: string | null | undefined): string {
  if (!value) return 'snapshot';
  const parsed = Date.parse(value);
  if (Number.isNaN(parsed)) return value;
  return new Intl.DateTimeFormat('en-US', {
    month: 'short',
    day: 'numeric',
    hour: 'numeric',
    minute: '2-digit'
  }).format(new Date(parsed));
}
