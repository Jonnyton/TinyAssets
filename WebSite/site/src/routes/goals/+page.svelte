<!-- /goals — canonical live goal board. -->
<script lang="ts">
  import RitualLabel from '$lib/components/Primitives/RitualLabel.svelte';
  import {
    compactNumber,
    initialMcpSnapshot,
    initialRepoSnapshot,
    refreshMcpSnapshot,
    refreshRepoSnapshot,
    relativeStamp,
    shortHash,
    type RepoBranch
  } from '$lib/live/project';
  import type { Snapshot } from '$lib/mcp/types';

  type Goal = Snapshot['goals'][number];
  type WikiKind = 'bug' | 'concept' | 'note' | 'plan' | 'draft';
  type WikiEvidence = {
    key: string;
    nodeId: string;
    kind: WikiKind;
    title: string;
    subtitle: string;
    tags: string[];
    score: number;
    relation: string;
    href: string;
  };
  type BranchEvidence = {
    key: string;
    name: string;
    kind: string;
    summary: string;
    meta: string;
    href: string;
    external: boolean;
    score: number;
  };
  type FocusKind = 'goals' | 'goal' | 'commons' | 'branch';

  const STOP_WORDS = new Set([
    'and',
    'the',
    'that',
    'this',
    'with',
    'from',
    'into',
    'through',
    'under',
    'public',
    'workflow',
    'mcp',
    'chatbot',
    'chatbots',
    'goal',
    'goals',
    'bug',
    'bugs',
    'branch',
    'branches',
    'live',
    'state',
    'states',
    'route',
    'routes',
    'user',
    'users'
  ]);

  let mcp = $state(initialMcpSnapshot);
  let repo = $state(initialRepoSnapshot);
  let selectedGoalId = $state(initialMcpSnapshot.goals[0]?.id ?? '');
  let selectedEvidenceKey = $state('');
  let selectedBranchKey = $state('');
  let focusKind = $state<FocusKind>('goals');
  let activeTag = $state('all');
  let query = $state('');
  let mcpLoading = $state(false);
  let githubLoading = $state(false);
  let mcpError = $state('');
  let githubError = $state('');
  let copiedPrompt = $state(false);

  const goals = $derived(mcp.goals ?? []);
  const selectedGoal = $derived(goals.find((goal) => goal.id === selectedGoalId) ?? goals[0] ?? null);
  const repoUrl = $derived(repo.repo.remote_url?.replace(/\.git$/, '') || 'https://github.com/Jonnyton/Workflow');
  const allTags = $derived.by(() => {
    const counts = new Map<string, number>();
    for (const goal of goals) {
      for (const tag of goal.tags ?? []) counts.set(tag, (counts.get(tag) ?? 0) + 1);
    }
    return [...counts.entries()]
      .toSorted((a, b) => b[1] - a[1] || a[0].localeCompare(b[0]))
      .slice(0, 14);
  });
  const filteredGoals = $derived.by(() => {
    const needle = query.trim().toLowerCase();
    return goals.filter((goal) => {
      const tagMatch = activeTag === 'all' || goal.tags?.includes(activeTag);
      const queryMatch =
        !needle ||
        [goal.name, goal.summary, goal.id, ...(goal.tags ?? [])].join(' ').toLowerCase().includes(needle);
      return tagMatch && queryMatch;
    });
  });
  const wikiEvidence = $derived.by(() => (selectedGoal ? relatedWikiEvidence(selectedGoal, mcp) : []));
  const branchEvidence = $derived.by(() => (selectedGoal ? relatedBranchEvidence(selectedGoal, repo) : []));
  const selectedEvidence = $derived.by(
    () => wikiEvidence.find((item) => item.key === selectedEvidenceKey) ?? wikiEvidence[0] ?? null
  );
  const selectedBranch = $derived.by(
    () => branchEvidence.find((branch) => branch.key === selectedBranchKey) ?? branchEvidence[0] ?? null
  );
  const explicitGoalEdges = $derived.by(() => {
    if (!selectedGoal) return [];
    const goalNode = `goal:${selectedGoal.id}`;
    return (mcp.edges ?? []).filter((edge) => edge.from === goalNode || edge.to === goalNode);
  });

  async function refreshMcp() {
    mcpLoading = true;
    mcpError = '';
    try {
      const next = await refreshMcpSnapshot(mcp);
      mcp = next;
      if (!next.goals.some((goal) => goal.id === selectedGoalId)) {
        selectedGoalId = next.goals[0]?.id ?? '';
        selectedEvidenceKey = '';
        selectedBranchKey = '';
        focusKind = 'goals';
      }
    } catch (error) {
      mcpError = error instanceof Error ? error.message : String(error);
    } finally {
      mcpLoading = false;
    }
  }

  async function refreshGithub() {
    githubLoading = true;
    githubError = '';
    try {
      repo = await refreshRepoSnapshot(repo);
    } catch (error) {
      githubError = error instanceof Error ? error.message : String(error);
    } finally {
      githubLoading = false;
    }
  }

  function selectGoal(goalId: string) {
    selectedGoalId = goalId;
    selectedEvidenceKey = '';
    selectedBranchKey = '';
    focusKind = 'goal';
  }

  function selectEvidence(key: string) {
    selectedEvidenceKey = key;
    focusKind = 'commons';
  }

  function selectBranch(key: string) {
    selectedBranchKey = key;
    focusKind = 'branch';
  }

  function returnToEvidence() {
    selectedEvidenceKey = '';
    selectedBranchKey = '';
    focusKind = 'goal';
  }

  function returnToGoals() {
    selectedEvidenceKey = '';
    selectedBranchKey = '';
    focusKind = 'goals';
  }

  function toggleTag(tag: string) {
    activeTag = activeTag === tag ? 'all' : tag;
  }

  async function copyGoalPrompt() {
    if (!selectedGoal) return;
    try {
      await navigator.clipboard.writeText(promptFor(selectedGoal));
      copiedPrompt = true;
      window.setTimeout(() => (copiedPrompt = false), 1400);
    } catch {
      copiedPrompt = false;
    }
  }

  function promptFor(goal: Goal): string {
    return `Using Workflow, browse the live goal "${goal.name}" (${goal.id}), show related commons context and the safest next action I can take through MCP.`;
  }

  function slugId(path: string): string {
    return path.split('/').pop()?.replace(/\.md$/, '') ?? path;
  }

  function uniq(values: string[]): string[] {
    return [...new Set(values.filter(Boolean))];
  }

  function words(value: string | undefined): string[] {
    return uniq(
      (value ?? '')
        .toLowerCase()
        .split(/[^a-z0-9]+/)
        .filter((word) => word.length > 2 && !STOP_WORDS.has(word))
    );
  }

  function goalNeedles(goal: Goal): string[] {
    const tagParts = (goal.tags ?? []).flatMap((tag) => [tag.toLowerCase(), ...words(tag)]);
    const summaryTerms = words(goal.summary).filter((word) => word.length > 6).slice(0, 10);
    return uniq([...tagParts, ...words(goal.name), ...summaryTerms]);
  }

  function scoreAgainst(needles: string[], values: Array<string | undefined>): number {
    const haystack = values.filter(Boolean).join(' ').toLowerCase();
    return needles.reduce((score, needle) => {
      if (!needle || !haystack.includes(needle)) return score;
      return score + (needle.includes('-') ? 4 : 1);
    }, 0);
  }

  function tagLine(tags: string[] | undefined): string {
    const clean = (tags ?? []).filter(Boolean);
    return clean.length ? clean.slice(0, 8).join(', ') : 'none in current snapshot';
  }

  function branchSource(branch: BranchEvidence): string {
    return branch.external ? 'GitHub branch' : 'Workflow branch definition';
  }

  function wikiItems(snapshot: Snapshot): Omit<WikiEvidence, 'score' | 'relation'>[] {
    const tags = snapshot.tags ?? {};
    const items: Omit<WikiEvidence, 'score' | 'relation'>[] = [];
    for (const bug of snapshot.wiki?.bugs ?? []) {
      const nodeId = `bug:${bug.id}`;
      items.push({
        key: nodeId,
        nodeId,
        kind: 'bug',
        title: `${bug.id} — ${bug.title}`,
        subtitle: bug.slug ?? bug.id,
        tags: tags[nodeId] ?? ['bug'],
        href: '/wiki'
      });
    }
    for (const plan of snapshot.wiki?.plans ?? []) {
      const nodeId = `plan:${slugId(plan.slug)}`;
      items.push({
        key: nodeId,
        nodeId,
        kind: 'plan',
        title: plan.title,
        subtitle: plan.slug,
        tags: tags[nodeId] ?? ['plan'],
        href: '/wiki'
      });
    }
    for (const concept of snapshot.wiki?.concepts ?? []) {
      const nodeId = `concept:${slugId(concept.slug)}`;
      items.push({
        key: nodeId,
        nodeId,
        kind: 'concept',
        title: concept.title,
        subtitle: concept.slug,
        tags: tags[nodeId] ?? ['concept'],
        href: '/wiki'
      });
    }
    for (const note of snapshot.wiki?.notes ?? []) {
      const nodeId = `note:${slugId(note.slug)}`;
      items.push({
        key: nodeId,
        nodeId,
        kind: 'note',
        title: note.title,
        subtitle: note.slug,
        tags: tags[nodeId] ?? ['note'],
        href: '/wiki'
      });
    }
    for (const draft of snapshot.wiki?.drafts ?? []) {
      const nodeId = `draft:${draft.slug}`;
      items.push({
        key: nodeId,
        nodeId,
        kind: 'draft',
        title: draft.title,
        subtitle: draft.slug,
        tags: tags[nodeId] ?? ['draft'],
        href: '/wiki'
      });
    }
    return items;
  }

  function relatedWikiEvidence(goal: Goal, snapshot: Snapshot): WikiEvidence[] {
    const goalNode = `goal:${goal.id}`;
    const edgeMap = new Set<string>();
    for (const edge of snapshot.edges ?? []) {
      if (edge.from === goalNode) edgeMap.add(edge.to);
      if (edge.to === goalNode) edgeMap.add(edge.from);
    }
    const needles = goalNeedles(goal);
    return wikiItems(snapshot)
      .map((item) => {
        const explicit = edgeMap.has(item.nodeId);
        const score =
          scoreAgainst(needles, [item.title, item.subtitle, ...item.tags]) +
          (explicit ? 20 : 0) +
          (item.kind === 'bug' && needles.some((needle) => ['patch', 'patch-loop'].includes(needle)) ? 3 : 0);
        return {
          ...item,
          score,
          relation: explicit ? 'explicit MCP edge' : 'matched by live tags/title'
        };
      })
      .filter((item) => item.score >= 2)
      .toSorted((a, b) => b.score - a.score || a.title.localeCompare(b.title))
      .slice(0, 6);
  }

  function relatedBranchEvidence(goal: Goal, snapshot: typeof initialRepoSnapshot): BranchEvidence[] {
    const needles = goalNeedles(goal);
    const workflowBranches: BranchEvidence[] = (snapshot.workflow_branches ?? []).map((branch: Record<string, any>) => {
      const score = scoreAgainst(needles, [branch.name, branch.summary, branch.area, branch.state]);
      return {
        key: String(branch.id ?? branch.name),
        name: String(branch.name ?? branch.id),
        kind: String(branch.area ?? 'workflow branch'),
        summary: String(branch.summary ?? 'Workflow branch from the repo snapshot.'),
        meta: String(branch.state ?? 'snapshot'),
        href: '/graph',
        external: false,
        score
      };
    });
    const gitBranches: BranchEvidence[] = (snapshot.branches ?? []).map((branch: RepoBranch) => {
      const score = scoreAgainst(needles, [branch.name, branch.subject, branch.kind]);
      return {
        key: branch.id,
        name: branch.name,
        kind: branch.kind,
        summary: branch.subject ?? 'GitHub branch from the repo snapshot.',
        meta: `${shortHash(branch.commit)}${branch.date ? ` · ${relativeStamp(branch.date)}` : ''}`,
        href: `${repoUrl}/tree/${encodeURIComponent(branch.name)}`,
        external: true,
        score
      };
    });
    return [...workflowBranches, ...gitBranches]
      .filter((branch) => branch.score >= 2)
      .toSorted((a, b) => b.score - a.score || a.name.localeCompare(b.name))
      .slice(0, 5);
  }
</script>

<svelte:head>
  <title>Goals — Workflow</title>
  <meta
    name="description"
    content="Browse live Workflow goals, related MCP commons records, and branch signals from the same data a chatbot can read."
  />
  <link rel="canonical" href="https://tinyassets.io/goals" />
</svelte:head>

<section class="goals">
  <div class="wrap">
    <header class="section-head">
      <div>
        <RitualLabel color="var(--signal-live)">· Goal lens · live MCP goals ·</RitualLabel>
        <h1>Start from goals. Let branches compete underneath.</h1>
      </div>
      <div class="intro">
        <p>
          Your chatbot can browse these goals directly through the MCP connector. Pick a goal to see the live commons records and branch signals currently attached to it.
        </p>
        <div class="refresh-box" aria-label="Live data controls">
          <button type="button" onclick={refreshMcp} disabled={mcpLoading} aria-busy={mcpLoading}>
            Refresh MCP
          </button>
          <button type="button" onclick={refreshGithub} disabled={githubLoading} aria-busy={githubLoading}>
            Refresh GitHub
          </button>
          <span>MCP {relativeStamp(mcp.fetched_at)}</span>
          <span>GitHub {relativeStamp(repo.fetched_at)}</span>
        </div>
      </div>
    </header>

    {#if mcpError || githubError}
      <div class="errors" role="status">
        {#if mcpError}<p>MCP refresh failed: <code>{mcpError}</code></p>{/if}
        {#if githubError}<p>GitHub refresh failed: <code>{githubError}</code></p>{/if}
      </div>
    {/if}

    <div class="source-strip" aria-label="Goal source">
      <article>
        <span>MCP source</span>
        <strong>{mcp.source}</strong>
        <small>{compactNumber(goals.length)} public goals · {relativeStamp(mcp.fetched_at)}</small>
      </article>
      <article>
        <span>Selected goal</span>
        <strong>{selectedGoal?.id ?? 'none'}</strong>
        <small>{compactNumber(wikiEvidence.length)} commons records · {compactNumber(branchEvidence.length)} branch signals</small>
      </article>
      <article>
        <span>GitHub source</span>
        <strong>{repo.source}</strong>
        <small>head {shortHash(repo.repo.head)} · {relativeStamp(repo.fetched_at)}</small>
      </article>
    </div>

    <section class="toolbar" aria-label="Goal filters">
      <label>
        <span>Search goals</span>
        <input bind:value={query} placeholder="patch, games, research..." />
      </label>
      <div class="tag-cloud" aria-label="Goal tag filters">
        <button type="button" class:active={activeTag === 'all'} aria-pressed={activeTag === 'all'} onclick={() => (activeTag = 'all')}>
          All
        </button>
        {#each allTags as [tag, count] (tag)}
          <button type="button" class:active={activeTag === tag} aria-pressed={activeTag === tag} onclick={() => toggleTag(tag)}>
            {tag}<small>{count}</small>
          </button>
        {/each}
      </div>
    </section>

    {#if focusKind === 'goals'}
      <div class="goal-board" aria-label="Live goals">
        {#each filteredGoals as goal, index (goal.id)}
          <button
            type="button"
            class="goal-card"
            class:active={selectedGoal?.id === goal.id}
            aria-pressed={selectedGoal?.id === goal.id}
            onclick={() => selectGoal(goal.id)}
          >
            <span class="goal-card__rank">G{index + 1}</span>
            <span class="goal-card__title">{goal.name}</span>
            <span class="goal-card__summary">{goal.summary}</span>
            <span class="goal-card__tags">
              {#if goal.tags.length}
                {#each goal.tags.slice(0, 4) as tag}
                  <span>{tag}</span>
                {/each}
              {:else}
                <span>untagged</span>
              {/if}
            </span>
            <span class="goal-card__foot">
              <span>{goal.visibility}</span>
              <span>{goal.id}</span>
            </span>
          </button>
        {:else}
          <div class="empty">
            <strong>No matching live goals.</strong>
            <p>Clear the search or tag filter to return to the current MCP goal set.</p>
          </div>
        {/each}
      </div>
    {:else if selectedGoal}
      <section class="goal-detail" aria-labelledby="selected-goal-title">
        <div class="goal-detail__nav">
          <button type="button" class="back-button" onclick={returnToGoals}>Back to all goals</button>
        </div>

        <div class="detail-head">
          <div>
            <RitualLabel color="var(--ember-500)">· Selected goal · {selectedGoal.id} ·</RitualLabel>
            <h2 id="selected-goal-title">{selectedGoal.name}</h2>
            <p>{selectedGoal.summary}</p>
          </div>
          <div class="detail-actions">
            <button type="button" onclick={copyGoalPrompt}>{copiedPrompt ? 'Copied prompt' : 'Copy prompt'}</button>
            <a href="/connect">Use through MCP</a>
            <a href="/graph">Open in graph</a>
            <a href="/connect">Route into loop</a>
          </div>
        </div>

        <div class="detail-stats" aria-label="Selected goal live evidence">
          <article>
            <span>Commons</span>
            <strong>{compactNumber(wikiEvidence.length)} related</strong>
            <small>from live tags, titles, and explicit edges</small>
          </article>
          <article>
            <span>Branches</span>
            <strong>{compactNumber(branchEvidence.length)} signals</strong>
            <small>workflow branches and GitHub refs</small>
          </article>
          <article>
            <span>Graph</span>
            <strong>{compactNumber(explicitGoalEdges.length)} explicit edges</strong>
            <small>open graph to inspect the whole project map</small>
          </article>
        </div>

        {#if focusKind === 'goal'}
          <div class="evidence-grid">
            <section class="evidence-card" aria-labelledby="commons-title">
              <div class="evidence-card__head">
                <h3 id="commons-title">Related commons</h3>
                <small>{wikiEvidence.length ? 'live match reasons' : 'empty state is explicit'}</small>
              </div>
              <div class="evidence-list">
                {#each wikiEvidence as item (item.key)}
                  <button
                    type="button"
                    class="evidence-item"
                    aria-pressed={false}
                    onclick={() => selectEvidence(item.key)}
                  >
                    <span>{item.kind}</span>
                    <strong>{item.title}</strong>
                    <small>{item.relation}</small>
                  </button>
                {:else}
                  <p class="empty-copy">No related wiki records were found from current tags, titles, or explicit goal edges.</p>
                {/each}
              </div>
            </section>

            <section class="evidence-card" aria-labelledby="branches-title">
              <div class="evidence-card__head">
                <h3 id="branches-title">Branch signals</h3>
                <small>{branchEvidence.length ? 'workflow + GitHub matches' : 'no branch match yet'}</small>
              </div>
              <div class="evidence-list">
                {#each branchEvidence as branch (branch.key)}
                  <button
                    type="button"
                    class="evidence-item"
                    aria-pressed={false}
                    onclick={() => selectBranch(branch.key)}
                  >
                    <span>{branch.kind}</span>
                    <strong>{branch.name}</strong>
                    <small>{branch.summary} · {branch.meta}</small>
                  </button>
                {:else}
                  <p class="empty-copy">No repo or workflow branch currently matches this goal. That is a real gap, not a hidden leaderboard.</p>
                {/each}
              </div>
            </section>
          </div>
        {:else}
          <section class="click-detail click-detail--{focusKind}" aria-live="polite" aria-label="Clicked item detail">
            <div class="click-detail__nav">
              <button type="button" class="back-button" onclick={returnToEvidence}>Back to related items</button>
            </div>

            {#if focusKind === 'commons' && selectedEvidence}
            <div>
              <RitualLabel>· Evidence detail · {selectedEvidence.kind} ·</RitualLabel>
              <h3>{selectedEvidence.title}</h3>
              <p>{selectedEvidence.subtitle}</p>
              <div class="detail-grid" aria-label="Selected commons fields">
                <article>
                  <span>Node ID</span>
                  <strong>{selectedEvidence.nodeId}</strong>
                </article>
                <article>
                  <span>Why shown</span>
                  <strong>{selectedEvidence.relation}</strong>
                </article>
                <article>
                  <span>Source</span>
                  <strong>MCP wiki snapshot</strong>
                </article>
                <article>
                  <span>Tags</span>
                  <strong>{tagLine(selectedEvidence.tags)}</strong>
                </article>
              </div>
              <div class="evidence-tags">
                {#each selectedEvidence.tags.slice(0, 6) as tag}
                  <span>{tag}</span>
                {/each}
              </div>
            </div>
            <div class="detail-side">
              <a href={selectedEvidence.href}>Open live wiki</a>
              <a href="/graph">Show relationship graph</a>
            </div>
          {:else if focusKind === 'branch' && selectedBranch}
            <div>
              <RitualLabel>· Branch detail · {selectedBranch.kind} ·</RitualLabel>
              <h3>{selectedBranch.name}</h3>
              <p>{selectedBranch.summary}</p>
              <div class="detail-grid" aria-label="Selected branch fields">
                <article>
                  <span>Source</span>
                  <strong>{branchSource(selectedBranch)}</strong>
                </article>
                <article>
                  <span>State</span>
                  <strong>{selectedBranch.meta}</strong>
                </article>
                <article>
                  <span>Match</span>
                  <strong>goal text and tag overlap</strong>
                </article>
                <article>
                  <span>Route</span>
                  <strong>{selectedBranch.external ? 'GitHub source' : 'project graph'}</strong>
                </article>
              </div>
            </div>
            <div class="detail-side">
              <a href={selectedBranch.href} target={selectedBranch.external ? '_blank' : undefined} rel={selectedBranch.external ? 'noreferrer' : undefined}>
                {selectedBranch.external ? 'Open branch' : 'Open in graph'}
              </a>
              <a href="/connect">Route into loop</a>
            </div>
          {:else}
            <div>
              <RitualLabel>· Click detail ·</RitualLabel>
              <h3>No related item selected.</h3>
              <p>Click a goal, commons record, or branch signal to inspect the live detail behind it.</p>
            </div>
            <div class="detail-side">
              <a href="/wiki">Open live wiki</a>
            </div>
          {/if}
          </section>
        {/if}
      </section>
    {/if}
  </div>
</section>

<style>
  .goals {
    padding-block: 72px 48px;
  }

  .wrap {
    color: var(--fg-2);
    margin: 0 auto;
    max-width: 1120px;
    padding-inline: clamp(16px, 4vw, 32px);
  }

  .section-head {
    align-items: end;
    display: grid;
    gap: 30px;
    grid-template-columns: minmax(0, 1fr) minmax(280px, 0.56fr);
    margin-bottom: 18px;
  }

  h1,
  h2,
  h3,
  p {
    margin: 0;
  }

  h1 {
    color: var(--fg-1);
    font-family: var(--font-display);
    font-size: clamp(42px, 7vw, 68px);
    font-weight: 400;
    letter-spacing: 0;
    line-height: 0.98;
    margin-top: 12px;
    text-wrap: balance;
  }

  .intro p {
    font-size: 15px;
    line-height: 1.7;
    margin-bottom: 14px;
  }

  .refresh-box {
    background: var(--bg-inset);
    border: 1px solid var(--border-1);
    border-radius: 8px;
    display: grid;
    gap: 8px;
    grid-template-columns: repeat(2, minmax(0, 1fr));
    padding: 12px;
  }

  .refresh-box button,
  .detail-actions button,
  .detail-actions a,
  .tag-cloud button,
  .click-detail a,
  .back-button {
    align-items: center;
    border-radius: 6px;
    display: inline-flex;
    justify-content: center;
    min-height: 36px;
    text-decoration: none;
  }

  .refresh-box button,
  .detail-actions button,
  .detail-actions a,
  .click-detail a,
  .back-button {
    background: rgba(109, 211, 166, 0.1);
    border: 1px solid rgba(109, 211, 166, 0.28);
    color: var(--fg-1);
    cursor: pointer;
    font-family: var(--font-mono);
    font-size: 11px;
    letter-spacing: 0.08em;
    padding: 8px 10px;
    text-transform: uppercase;
  }

  .refresh-box button:hover,
  .detail-actions button:hover,
  .detail-actions a:hover,
  .click-detail a:hover,
  .back-button:hover {
    background: rgba(109, 211, 166, 0.16);
    border-color: rgba(109, 211, 166, 0.5);
  }

  .refresh-box button:disabled {
    cursor: wait;
    opacity: 0.65;
  }

  .refresh-box span {
    color: var(--fg-3);
    font-family: var(--font-mono);
    font-size: 11px;
  }

  .errors {
    background: rgba(233, 93, 123, 0.1);
    border: 1px solid rgba(233, 93, 123, 0.36);
    border-radius: 8px;
    margin-bottom: 16px;
    padding: 12px 14px;
  }

  .errors p {
    font-family: var(--font-mono);
    font-size: 12px;
    line-height: 1.5;
    overflow-wrap: anywhere;
  }

  .source-strip {
    display: grid;
    gap: 10px;
    grid-template-columns: repeat(3, minmax(0, 1fr));
    margin-bottom: 14px;
  }

  .source-strip article,
  .detail-stats article {
    background: var(--bg-inset);
    border: 1px solid var(--border-1);
    border-radius: 8px;
    min-width: 0;
    padding: 14px;
  }

  .source-strip span,
  .detail-stats span,
  .evidence-item span {
    color: var(--fg-3);
    display: block;
    font-family: var(--font-mono);
    font-size: 10px;
    letter-spacing: 0.12em;
    text-transform: uppercase;
  }

  .source-strip strong,
  .detail-stats strong {
    color: var(--fg-1);
    display: block;
    font-family: var(--font-display);
    font-size: 22px;
    font-weight: 500;
    line-height: 1.08;
    margin-top: 8px;
    overflow-wrap: anywhere;
  }

  .source-strip small,
  .detail-stats small,
  .evidence-item small,
  .goal-card__foot {
    color: var(--fg-3);
    font-family: var(--font-mono);
    font-size: 11px;
    line-height: 1.45;
    overflow-wrap: anywhere;
  }

  .toolbar {
    align-items: start;
    background: rgba(255, 255, 255, 0.03);
    border: 1px solid var(--border-1);
    border-radius: 8px;
    display: grid;
    gap: 12px;
    grid-template-columns: 260px minmax(0, 1fr);
    margin-bottom: 12px;
    padding: 14px;
  }

  .toolbar label span {
    color: var(--fg-3);
    display: block;
    font-family: var(--font-mono);
    font-size: 10px;
    letter-spacing: 0.12em;
    margin-bottom: 8px;
    text-transform: uppercase;
  }

  .toolbar input {
    background: rgba(255, 255, 255, 0.04);
    border: 1px solid var(--border-1);
    border-radius: 6px;
    color: var(--fg-1);
    font: inherit;
    min-height: 40px;
    padding: 8px 10px;
    width: 100%;
  }

  .tag-cloud,
  .goal-card__tags,
  .evidence-tags {
    display: flex;
    flex-wrap: wrap;
    gap: 7px;
  }

  .tag-cloud button,
  .goal-card__tags span,
  .evidence-tags span {
    background: transparent;
    border: 1px solid var(--border-1);
    border-radius: 5px;
    color: var(--fg-2);
    font-family: var(--font-mono);
    font-size: 10.5px;
    gap: 6px;
    letter-spacing: 0.02em;
    padding: 6px 8px;
  }

  .tag-cloud button {
    cursor: pointer;
  }

  .tag-cloud button:hover,
  .tag-cloud button.active {
    background: rgba(246, 193, 119, 0.1);
    border-color: rgba(246, 193, 119, 0.46);
    color: var(--fg-1);
  }

  .tag-cloud small {
    color: var(--fg-3);
  }

  .goal-board {
    display: grid;
    gap: 10px;
    grid-template-columns: repeat(2, minmax(0, 1fr));
  }

  .goal-card {
    background: var(--bg-2);
    border: 1px solid var(--border-1);
    border-radius: 8px;
    color: inherit;
    cursor: pointer;
    display: flex;
    flex-direction: column;
    min-height: 292px;
    min-width: 0;
    padding: 20px;
    text-align: left;
    transition:
      background var(--dur-base) var(--ease-summon),
      border-color var(--dur-base) var(--ease-summon),
      transform var(--dur-base) var(--ease-summon);
  }

  .goal-card:hover,
  .goal-card.active {
    background: rgba(109, 211, 166, 0.055);
    border-color: rgba(109, 211, 166, 0.5);
    transform: translateY(-1px);
  }

  .goal-card__rank {
    color: var(--ember-600);
    font-family: var(--font-mono);
    font-size: 10px;
    letter-spacing: 0.14em;
    margin-bottom: 10px;
    text-transform: uppercase;
  }

  .goal-card__title {
    color: var(--fg-1);
    display: block;
    font-family: var(--font-display);
    font-size: 24px;
    font-weight: 500;
    letter-spacing: 0;
    line-height: 1.12;
    margin-bottom: 10px;
  }

  .goal-card__summary {
    color: var(--fg-2);
    display: block;
    font-size: 13.5px;
    line-height: 1.6;
    margin-bottom: 14px;
  }

  .goal-card__tags {
    margin-top: auto;
    padding-top: 4px;
  }

  .goal-card__foot {
    display: flex;
    gap: 10px;
    justify-content: space-between;
    margin-top: 14px;
  }

  .empty,
  .empty-copy {
    background: var(--bg-inset);
    border: 1px dashed var(--border-2);
    border-radius: 8px;
    color: var(--fg-2);
    font-size: 14px;
    line-height: 1.6;
    margin: 0;
    padding: 16px;
  }

  .goal-detail {
    margin-top: 0;
    padding-top: 0;
  }

  .goal-detail__nav {
    margin-bottom: 14px;
  }

  .detail-head {
    align-items: start;
    display: grid;
    gap: 18px;
    grid-template-columns: minmax(0, 1fr) minmax(220px, 300px);
  }

  .detail-head h2 {
    color: var(--fg-1);
    font-family: var(--font-display);
    font-size: clamp(32px, 5vw, 54px);
    font-weight: 400;
    letter-spacing: 0;
    line-height: 1;
    margin-top: 10px;
    text-wrap: balance;
  }

  .detail-head p {
    font-size: 15px;
    line-height: 1.7;
    margin-top: 14px;
    max-width: 760px;
  }

  .detail-actions {
    display: grid;
    gap: 8px;
  }

  .detail-stats {
    display: grid;
    gap: 10px;
    grid-template-columns: repeat(3, minmax(0, 1fr));
    margin-top: 18px;
  }

  .evidence-grid {
    display: grid;
    gap: 12px;
    grid-template-columns: repeat(2, minmax(0, 1fr));
    margin-top: 14px;
  }

  .evidence-card {
    background: var(--bg-2);
    border: 1px solid var(--border-1);
    border-radius: 8px;
    min-width: 0;
    padding: 16px;
  }

  .evidence-card__head {
    align-items: baseline;
    display: flex;
    gap: 12px;
    justify-content: space-between;
    margin-bottom: 10px;
  }

  .evidence-card h3,
  .click-detail h3 {
    color: var(--fg-1);
    font-family: var(--font-display);
    font-size: 24px;
    font-weight: 500;
    letter-spacing: 0;
    line-height: 1.12;
  }

  .evidence-card__head small {
    color: var(--fg-3);
    font-family: var(--font-mono);
    font-size: 10px;
    text-align: right;
  }

  .evidence-list {
    display: grid;
    gap: 8px;
    max-height: 410px;
    overflow: auto;
    padding-right: 3px;
  }

  .evidence-item {
    background: var(--bg-inset);
    border: 1px solid var(--border-1);
    border-radius: 8px;
    color: inherit;
    cursor: pointer;
    display: block;
    font: inherit;
    min-width: 0;
    padding: 12px;
    text-align: left;
    text-decoration: none;
    width: 100%;
  }

  .evidence-item:hover,
  .evidence-item.active {
    border-color: rgba(115, 167, 255, 0.5);
  }

  .evidence-item strong {
    color: var(--fg-1);
    display: block;
    font-size: 13px;
    line-height: 1.35;
    margin: 6px 0;
    overflow-wrap: anywhere;
  }

  .click-detail {
    align-items: start;
    background: var(--bg-inset);
    border: 1px solid var(--border-1);
    border-radius: 8px;
    display: grid;
    gap: 14px;
    grid-template-columns: minmax(0, 1fr) minmax(180px, 240px);
    margin-top: 14px;
    padding: 16px;
  }

  .click-detail__nav {
    grid-column: 1 / -1;
  }

  .back-button {
    width: fit-content;
  }

  .click-detail p {
    font-size: 13px;
    line-height: 1.6;
    margin-top: 8px;
    overflow-wrap: anywhere;
  }

  .detail-grid {
    display: grid;
    gap: 8px;
    grid-template-columns: repeat(2, minmax(0, 1fr));
    margin-top: 14px;
  }

  .detail-grid article {
    background: rgba(255, 255, 255, 0.035);
    border: 1px solid var(--border-1);
    border-radius: 6px;
    min-width: 0;
    padding: 10px;
  }

  .detail-grid span {
    color: var(--fg-3);
    display: block;
    font-family: var(--font-mono);
    font-size: 10px;
    letter-spacing: 0.12em;
    text-transform: uppercase;
  }

  .detail-grid strong {
    color: var(--fg-1);
    display: block;
    font-family: var(--font-mono);
    font-size: 11px;
    line-height: 1.45;
    margin-top: 6px;
    overflow-wrap: anywhere;
  }

  .detail-side {
    display: grid;
    gap: 8px;
  }

  .evidence-tags {
    margin-top: 12px;
  }

  @media (max-width: 900px) {
    .section-head,
    .toolbar,
    .detail-head,
    .evidence-grid,
    .click-detail {
      grid-template-columns: 1fr;
    }

    .source-strip,
    .detail-stats {
      grid-template-columns: repeat(2, minmax(0, 1fr));
    }
  }

  @media (max-width: 700px) {
    .goals {
      padding-block: 44px 30px;
    }

    .source-strip,
    .detail-stats,
    .goal-board,
    .refresh-box {
      grid-template-columns: 1fr;
    }

    .goal-card {
      min-height: 0;
    }
  }
</style>
