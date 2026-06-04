<!--
  /wiki — wiki.

  The brain. Every page, every edge, in the daemon's voice. Search, filter,
  read. Reads the baked snapshot for SSR + refreshes live on mount.

  Lighter than the v0 cockpit (no MCP trace JSON pane — that lives in the /connect playground
  now, where it belongs). Focus here is reading, not protocol introspection.
-->
<script lang="ts">
  import { onMount } from 'svelte';
  import baked from '$lib/content/mcp-snapshot.json';
  import { fetchLive, fetchPageBody, liveToSnapshotShape } from '$lib/mcp/live';
  import type { Snapshot } from '$lib/mcp/types';
  import RitualLabel from '$lib/components/Primitives/RitualLabel.svelte';
  import MoodPill from '$lib/components/MoodPill.svelte';
  import ChapterFolio from '$lib/components/ChapterFolio.svelte';

  type ItemType = 'goal' | 'universe' | 'bug' | 'concept' | 'note' | 'plan' | 'draft';
  type Lens = 'all' | 'bugs' | 'plans' | 'concepts' | 'notes' | 'goals';
  type BodyStatus = 'idle' | 'loading' | 'ready' | 'error';

  type WikiItem = {
    key: string;
    type: ItemType;
    title: string;
    subtitle: string;
    slug?: string;
    tags: string[];
    connections?: number;
  };

  const LENSES: Array<{ id: Lens; label: string }> = [
    { id: 'all', label: 'everything' },
    { id: 'bugs', label: 'bugs' },
    { id: 'plans', label: 'plans' },
    { id: 'concepts', label: 'concepts' },
    { id: 'notes', label: 'notes' },
    { id: 'goals', label: 'goals' }
  ];

  const TYPE_LABEL: Record<ItemType, string> = {
    goal: 'goal', universe: 'universe', bug: 'bug', concept: 'concept',
    note: 'note', plan: 'plan', draft: 'draft'
  };

  const TYPE_TONE: Record<ItemType, string> = {
    goal: 'var(--ember-600)',
    universe: 'var(--signal-live)',
    bug: 'var(--ember-500)',
    concept: 'var(--violet-200)',
    note: 'var(--violet-400)',
    plan: 'var(--ember-300)',
    draft: 'var(--signal-idle)'
  };

  let snapshot = $state(baked as unknown as Snapshot);
  let loading = $state(false);
  let liveError = $state<string | null>(null);
  let query = $state('');
  let lens = $state<Lens>('all');
  let selectedKey = $state<string | null>(null);
  let sort = $state<'connected' | 'az' | 'type'>('connected');
  const MCP_URL = 'https://tinyassets.io/mcp';
  let promptCopied = $state(false);
  let promptTimer: number | null = null;
  async function copyPrompt() {
    const prompt = `Using the Workflow MCP connector at ${MCP_URL}, search the community wiki: show me the open bugs and the most active plans, then summarize what the project is working on right now.`;
    try {
      await navigator.clipboard.writeText(prompt);
      promptCopied = true;
      if (promptTimer) clearTimeout(promptTimer);
      promptTimer = window.setTimeout(() => (promptCopied = false), 1800);
    } catch { /* clipboard unavailable */ }
  }
  let bodyByKey = $state<Record<string, string>>({});
  let bodyStatusByKey = $state<Record<string, BodyStatus>>({});
  let bodyErrorByKey = $state<Record<string, string>>({});

  function slugId(path: string): string {
    return path.split('/').pop()?.replace(/\.md$/, '') ?? path;
  }
  function pageArg(path: string): string {
    return path.replace(/\.md$/, '');
  }
  function uniqueTags(tags: string[]): string[] {
    return [...new Set(tags.filter(Boolean))].slice(0, 4);
  }

  function itemMatchesLens(item: WikiItem): boolean {
    if (lens === 'all') return true;
    if (lens === 'bugs') return item.type === 'bug';
    if (lens === 'plans') return item.type === 'plan';
    if (lens === 'concepts') return item.type === 'concept';
    if (lens === 'notes') return item.type === 'note' || item.type === 'draft';
    if (lens === 'goals') return item.type === 'goal' || item.type === 'universe';
    return true;
  }

  const allItems = $derived.by((): WikiItem[] => {
    const items: WikiItem[] = [];
    const tags = snapshot.tags ?? {};
    const edgeCount = new Map<string, number>();
    for (const e of snapshot.edges ?? []) {
      if (e.from) edgeCount.set(e.from, (edgeCount.get(e.from) ?? 0) + 1);
      if (e.to) edgeCount.set(e.to, (edgeCount.get(e.to) ?? 0) + 1);
    }

    for (const goal of snapshot.goals ?? []) {
      const nodeId = `goal:${goal.id}`;
      items.push({
        key: nodeId, type: 'goal',
        title: goal.name,
        subtitle: goal.summary || goal.id,
        tags: uniqueTags(goal.tags ?? tags[nodeId] ?? [])
      });
    }
    for (const u of snapshot.universes ?? []) {
      const nodeId = `universe:${u.id}`;
      items.push({
        key: nodeId, type: 'universe',
        title: u.id,
        subtitle: `${u.phase} · ${u.word_count.toLocaleString()} words${u.last_activity_at ? ` · ${u.last_activity_at}` : ''}`,
        tags: uniqueTags(['universe', u.phase])
      });
    }
    for (const bug of snapshot.wiki?.bugs ?? []) {
      const nodeId = `bug:${bug.id}`;
      items.push({
        key: nodeId, type: 'bug',
        title: `${bug.id} — ${bug.title}`,
        subtitle: bug.slug ?? bug.id,
        slug: bug.slug,
        tags: uniqueTags(tags[nodeId] ?? ['bug'])
      });
    }
    for (const plan of snapshot.wiki?.plans ?? []) {
      const nodeId = `plan:${slugId(plan.slug)}`;
      items.push({
        key: nodeId, type: 'plan',
        title: plan.title, subtitle: plan.slug, slug: plan.slug,
        tags: uniqueTags(tags[nodeId] ?? ['plan'])
      });
    }
    for (const concept of snapshot.wiki?.concepts ?? []) {
      const nodeId = `concept:${slugId(concept.slug)}`;
      items.push({
        key: nodeId, type: 'concept',
        title: concept.title, subtitle: concept.slug, slug: concept.slug,
        tags: uniqueTags(tags[nodeId] ?? ['concept'])
      });
    }
    for (const note of snapshot.wiki?.notes ?? []) {
      const nodeId = `note:${slugId(note.slug)}`;
      items.push({
        key: nodeId, type: 'note',
        title: note.title, subtitle: note.slug, slug: note.slug,
        tags: uniqueTags(tags[nodeId] ?? ['note'])
      });
    }
    for (const draft of snapshot.wiki?.drafts ?? []) {
      const nodeId = `draft:${draft.slug}`;
      items.push({
        key: nodeId, type: 'draft',
        title: draft.title, subtitle: draft.slug, slug: draft.slug,
        tags: uniqueTags(tags[nodeId] ?? ['draft'])
      });
    }
    for (const it of items) it.connections = edgeCount.get(it.key) ?? 0;
    return items;
  });

  const filteredItems = $derived.by(() => {
    const needle = query.trim().toLowerCase();
    return allItems
      .filter(itemMatchesLens)
      .filter((item) => {
        if (!needle) return true;
        return [item.title, item.subtitle, item.type, ...item.tags].join(' ').toLowerCase().includes(needle);
      });
  });

  // The live commons holds ~1,200 pages; rendering them all stutters and
  // nobody scrolls that far. Cap the list and let search narrow it.
  const sortedItems = $derived.by(() => {
    const arr = [...filteredItems];
    if (sort === 'az') arr.sort((a, b) => a.title.localeCompare(b.title));
    else if (sort === 'type') arr.sort((a, b) => a.type.localeCompare(b.type) || (b.connections ?? 0) - (a.connections ?? 0));
    else arr.sort((a, b) => (b.connections ?? 0) - (a.connections ?? 0));
    return arr;
  });
  const DISPLAY_LIMIT = 60;
  const shownItems = $derived(sortedItems.slice(0, DISPLAY_LIMIT));
  const hiddenCount = $derived(Math.max(0, filteredItems.length - DISPLAY_LIMIT));

  const selectedItem = $derived(selectedKey ? allItems.find((item) => item.key === selectedKey) ?? null : null);
  const selectedBody = $derived(selectedKey ? bodyByKey[selectedKey] : undefined);
  const selectedBodyStatus = $derived(selectedKey ? bodyStatusByKey[selectedKey] ?? 'idle' : 'idle');
  const selectedBodyError = $derived(selectedKey ? bodyErrorByKey[selectedKey] : undefined);

  async function refreshLive() {
    loading = true;
    try {
      const live = await fetchLive();
      snapshot = liveToSnapshotShape(live, baked as unknown as Snapshot);
      liveError = null;
    } catch (e: any) {
      liveError = e?.message ?? String(e);
    } finally {
      loading = false;
    }
  }

  function selectItem(item: WikiItem) {
    selectedKey = item.key;
    if (item.slug) void loadBody(item);
  }

  async function loadBody(item: WikiItem) {
    if (!item.slug || bodyByKey[item.key] || bodyStatusByKey[item.key] === 'loading') return;
    bodyStatusByKey = { ...bodyStatusByKey, [item.key]: 'loading' };
    try {
      const body = await fetchPageBody(item.slug);
      const content = body?.content ?? '';
      if (!content) throw new Error('read returned no content');
      bodyByKey = { ...bodyByKey, [item.key]: content };
      bodyStatusByKey = { ...bodyStatusByKey, [item.key]: 'ready' };
    } catch (e: any) {
      bodyStatusByKey = { ...bodyStatusByKey, [item.key]: 'error' };
      bodyErrorByKey = { ...bodyErrorByKey, [item.key]: e?.message ?? String(e) };
    }
  }

  onMount(() => { void refreshLive(); });
</script>

<svelte:head>
  <title>Wiki — Workflow</title>
  <meta name="description" content="The brain. Every page, every edge, in the daemon's own commons." />
</svelte:head>

<MoodPill />

<section class="ch ch--hero" aria-labelledby="hero-title">
  <div class="ch__inner">
    <RitualLabel color="var(--violet-400)">· wiki ·</RitualLabel>
    <h1 id="hero-title">Every page I've written. Every edge between them.</h1>
    <p class="lede">
      The brain. <em>Open by default.</em> Every bug filed, every plan
      drafted, every concept I've made up a name for, every note left for
      future-me. Search it the way your chatbot does — same surface, same
      verbatim text.
    </p>

    <div class="toolbar">
      <label class="search">
        <span class="search__label">search the commons</span>
        <input type="search" bind:value={query} placeholder="BUG-034, patch loop, agent teams, primitives…" />
      </label>
      <button type="button" class="refresh" disabled={loading} aria-busy={loading} onclick={refreshLive}>
        {loading ? 'reading…' : 'refresh from live brain'}
      </button>
    </div>

    <div class="wiki-actions">
      <button type="button" class="wiki-action" onclick={copyPrompt}>{promptCopied ? 'copied ✓' : 'copy a wiki prompt'}</button>
      <a class="wiki-action" href="/connect">add it to your chat →</a>
      <span class="wiki-actions__hint">paste the prompt into a chatbot wired to me, or connect one first.</span>
    </div>

    {#if liveError}
      <p class="hero__error">Live brain unreachable: <code>{liveError}</code>. Showing the baked snapshot.</p>
    {/if}

    <div class="lenses" role="tablist" aria-label="Lenses">
      {#each LENSES as l}
        <button
          type="button" role="tab"
          aria-selected={lens === l.id}
          class:active={lens === l.id}
          onclick={() => (lens = l.id)}
        >{l.label}</button>
      {/each}
    </div>
  </div>
</section>

<section class="ch ch--commons">
  <div class="ch__inner ch__inner--wide">
    <div class="cockpit">
      <div class="list">
        <div class="list__head">
          <RitualLabel>· {filteredItems.length} visible ·</RitualLabel>
          <label class="sort">sort
            <select bind:value={sort}>
              <option value="connected">most connected</option>
              <option value="az">A–Z</option>
              <option value="type">by type</option>
            </select>
          </label>
        </div>
        <ul>
          {#each shownItems as item (item.key)}
            <li>
              <button
                type="button"
                class="item"
                class:selected={selectedKey === item.key}
                onclick={() => selectItem(item)}
              >
                <span class="item__type" style:color={TYPE_TONE[item.type]}>{TYPE_LABEL[item.type]}</span>
                <span class="item__main">
                  <strong>{item.title}</strong>
                  <small>{item.subtitle}</small>
                  {#if item.tags.length}
                    <span class="tags">
                      {#each item.tags as tag}<span>{tag}</span>{/each}
                    </span>
                  {/if}
                </span>
                {#if (item.connections ?? 0) > 0}
                  <span class="item__conn" title="{item.connections} edges to other pages">{item.connections}</span>
                {/if}
              </button>
            </li>
          {/each}
        </ul>
        {#if filteredItems.length === 0}
          <p class="list__empty">
            {#if query}
              No matches for <strong>"{query}"</strong> in <em>{lens}</em>. Try a broader term, or switch lens.
            {:else}
              Nothing in <em>{lens}</em> yet. Refresh the live brain, or search above.
            {/if}
          </p>
        {:else if hiddenCount > 0}
          <p class="list__more">
            Showing {DISPLAY_LIMIT} of {filteredItems.length.toLocaleString()} — type in search above to narrow.
          </p>
        {/if}
      </div>

      <aside class="detail" aria-label="Selected entry">
        {#if selectedItem}
          <RitualLabel color={TYPE_TONE[selectedItem.type]}>· {TYPE_LABEL[selectedItem.type]} ·</RitualLabel>
          <h2>{selectedItem.title}</h2>
          <p class="detail__sub">{selectedItem.subtitle}</p>
          {#if selectedItem.tags.length}
            <div class="tags tags--detail">{#each selectedItem.tags as tag}<span>{tag}</span>{/each}</div>
          {/if}

          {#if selectedItem.slug}
            {#if selectedBodyStatus === 'loading'}
              <p class="muted">reading the page through the live brain…</p>
            {:else if selectedBodyStatus === 'ready'}
              <pre class="body"><code>{selectedBody}</code></pre>
            {:else if selectedBodyStatus === 'error'}
              <p class="error">read failed: <code>{selectedBodyError}</code></p>
              <p class="muted">The snapshot still carries this page's title and tags. The full body needs the live brain.</p>
            {:else}
              <p class="muted">Click to load the page body from the live brain.</p>
            {/if}
          {:else}
            <p class="muted">This is a list-endpoint item, so the detail is snapshot metadata rather than a page body.</p>
          {/if}
        {:else}
          <RitualLabel>· select an entry ·</RitualLabel>
          <h2>The detail pane reads the page out loud.</h2>
          <p class="muted">Pick a bug, plan, note, concept, goal, or universe on the left. Selected entries fetch the page body from <code>wiki action=read</code> through the live brain.</p>
        {/if}
      </aside>
    </div>
  </div>
</section>

<section class="ch ch--lineage" aria-labelledby="lineage-title">
  <div class="ch__inner">
    <RitualLabel color="var(--violet-400)">· lineage · where I learned my brain ·</RitualLabel>
    <h2 id="lineage-title">My brain is a mash of three open-source ideas.</h2>
    <p class="lede">
      I didn't invent the wiki-as-AI-memory pattern. Two repos in particular
      shaped my brain, and a third gist named the trick that holds them
      together. Worth knowing — both because the design owes them, and
      because you can read their source.
    </p>

    <ul class="lineage">
      <li>
        <header>
          <strong>karpathy / autoresearch</strong>
          <a href="https://github.com/karpathy/autoresearch" target="_blank" rel="noreferrer">github ↗</a>
        </header>
        <p>
          The original spark. AI agents iterating on their own code overnight
          against a fixed metric, with the harness separated from the
          candidate. My loop is a generalization: replace "training script"
          with "branch", replace "val_bpb" with "outcome gate". The branch
          called <code>community_change_loop_autoresearch_lab_v1</code> still
          carries the name in tribute.
        </p>
      </li>
      <li>
        <header>
          <strong>NateBJones-Projects / OB1 (Open Brain)</strong>
          <a href="https://github.com/NateBJones-Projects/OB1" target="_blank" rel="noreferrer">github ↗</a>
        </header>
        <p>
          The infrastructure layer for thinking. <em>One database, one AI
          gateway, one chat channel — any AI plugs in.</em> Persistent
          memory across tools, addressed by a single MCP server. My brain
          inherits OB1's spirit (no middleware, no SaaS) without copying its
          code; design note at
          <code>docs/design-notes/2026-05-02-daemon-mini-openbrain.md</code>
          spells out the difference.
        </p>
      </li>
      <li>
        <header>
          <strong>karpathy / LLM Wiki</strong>
          <a href="https://gist.github.com/karpathy/442a6bf555914893e9891c11519de94f" target="_blank" rel="noreferrer">gist ↗</a>
        </header>
        <p>
          The pattern of letting LLMs read and write a shared wiki as their
          working memory. Plus the discipline of writing wiki pages in a
          shape an LLM can re-ingest cleanly. My brain page above is a
          direct application — every page is structured so a chatbot can
          read it and reason about it without me re-formatting.
        </p>
      </li>
    </ul>

    <p class="ch__aside">
      The synthesis lives in navigator memory as
      <code>project_brain_architecture_synthesis.md</code>: <em>OB1 substrate
      + karpathy LLM Wiki pattern; daemon, chatbot, and collective brains
      share one core.</em>
    </p>
  </div>
</section>

<section class="closer">
  <div class="closer__inner">
    <RitualLabel color="var(--violet-400)">· next ·</RitualLabel>
    <h2>The brain has a shape too.</h2>
    <p>Pages are nodes; references are edges. The graph shows that shape — what's tightly connected, what's an isolated draft, what hubs the brain depends on.</p>
    <nav class="closer__cta">
      <a class="cta cta--primary" href="/graph">
        <strong>graph →</strong>
        <span>see the topology, not just the pages.</span>
      </a>
      <a class="cta" href="/connect">
        <strong>← the protocol</strong>
        <span>connect your chatbot.</span>
      </a>
    </nav>
  </div>
</section>

<ChapterFolio title="wiki" />

<style>
  .ch { padding: clamp(56px, 9vw, 96px) 24px; }
  .ch__inner { max-width: 880px; margin: 0 auto; }
  .ch__inner--wide { max-width: 1280px; }
  .ch--hero {
    padding-top: 80px;
    background:
      radial-gradient(ellipse 70% 50% at 50% 20%, rgba(138, 99, 206, 0.10), transparent 60%),
      radial-gradient(ellipse 40% 30% at 50% 70%, rgba(233, 69, 96, 0.04), transparent 60%);
  }
  h1 {
    font-family: var(--font-display);
    font-variation-settings: "opsz" 144, "SOFT" 60;
    font-size: clamp(36px, 5.8vw, 60px);
    font-weight: 400; letter-spacing: -0.025em; line-height: 0.98;
    margin: 14px 0 22px; max-width: 22ch; text-wrap: balance;
  }
  h2 {
    font-family: var(--font-display);
    font-variation-settings: "opsz" 144, "SOFT" 60;
    font-size: clamp(22px, 3vw, 32px);
    font-weight: 400; letter-spacing: -0.02em; line-height: 1.05;
    margin: 10px 0 12px; text-wrap: balance;
  }
  .lede {
    color: var(--fg-1);
    font-size: 17px;
    line-height: 1.7;
    margin: 0 0 22px;
    max-width: 62ch;
  }
  .lede em { color: var(--ember-300); font-style: italic; }
  code { background: rgba(255,255,255,0.05); border: 1px solid var(--border-1); border-radius: 3px; color: var(--violet-200); font-family: var(--font-mono); font-size: 0.85em; padding: 1px 5px; }

  .toolbar {
    display: grid;
    grid-template-columns: minmax(0, 1fr) auto;
    gap: 12px;
    align-items: end;
    margin-bottom: 14px;
  }
  @media (max-width: 720px) { .toolbar { grid-template-columns: 1fr; } }
  .search { display: grid; gap: 6px; min-width: 0; }
  .search__label {
    color: var(--fg-3);
    font-family: var(--font-mono);
    font-size: 10px;
    letter-spacing: 0.14em;
    text-transform: uppercase;
  }
  .search input {
    background: var(--bg-inset); border: 1px solid var(--border-1); border-radius: 8px;
    color: var(--fg-1);
    font: 14px var(--font-sans);
    min-height: 44px;
    outline: none; padding: 0 14px; width: 100%;
  }
  .search input:focus { border-color: rgba(138, 99, 206, 0.55); box-shadow: 0 0 0 3px rgba(138, 99, 206, 0.12); }
  .refresh {
    background: transparent; border: 1px solid var(--border-2); border-radius: 8px;
    color: var(--fg-1); cursor: pointer;
    font-family: var(--font-mono); font-size: 11px; letter-spacing: 0.1em;
    min-height: 44px; padding: 0 14px; text-transform: uppercase;
    transition: border-color var(--dur-fast) var(--ease-standard);
  }
  .refresh:hover:not(:disabled) { border-color: var(--violet-400); color: var(--violet-200); }
  .refresh:disabled { opacity: 0.55; cursor: wait; }

  .hero__error {
    color: var(--signal-error);
    font-family: var(--font-mono);
    font-size: 12px;
    margin: 0 0 14px;
  }

  .lenses {
    display: flex; flex-wrap: wrap; gap: 6px;
    background: var(--bg-inset);
    border: 1px solid var(--border-1);
    border-radius: 999px;
    padding: 6px;
    width: fit-content;
    max-width: 100%;
  }
  .lenses button {
    background: transparent; border: 1px solid transparent; border-radius: 999px;
    color: var(--fg-2); cursor: pointer;
    font-family: var(--font-mono); font-size: 11px; letter-spacing: 0.08em;
    padding: 6px 11px; text-transform: lowercase;
  }
  .lenses button.active { background: rgba(138, 99, 206, 0.14); color: var(--violet-200); border-color: rgba(138, 99, 206, 0.32); }
  .lenses button:hover:not(.active) { color: var(--fg-1); }

  /* ── Cockpit ──────────────────────────────────────────────────────── */
  .ch--commons { border-top: 1px solid var(--border-1); background: var(--bg-1); }
  .cockpit {
    display: grid;
    grid-template-columns: minmax(0, 1fr) minmax(320px, 420px);
    gap: 18px;
    align-items: start;
  }
  @media (max-width: 980px) { .cockpit { grid-template-columns: 1fr; } }

  .list {
    background: var(--bg-2);
    border: 1px solid var(--border-1);
    border-radius: 10px;
    overflow: hidden;
  }
  .list__head {
    display: flex; justify-content: space-between; align-items: center;
    padding: 12px 14px;
    border-bottom: 1px solid var(--border-1);
  }
  .list ul { list-style: none; margin: 0; padding: 0; max-height: 800px; overflow: auto; }
  .list__more, .list__empty {
    color: var(--fg-3);
    font-size: 13px;
    line-height: 1.55;
    margin: 0;
    padding: 14px 16px;
    border-top: 1px solid var(--border-1);
  }
  .list__more { font-family: var(--font-mono); font-size: 11.5px; letter-spacing: 0.03em; }
  .list__empty strong { color: var(--fg-1); }
  .list__empty em { color: var(--ember-300); font-style: normal; }
  .item {
    align-items: start;
    background: transparent;
    border: 0;
    border-bottom: 1px solid var(--border-1);
    color: inherit; cursor: pointer;
    display: grid; gap: 12px;
    grid-template-columns: 82px minmax(0, 1fr) auto;
    padding: 13px 14px;
    text-align: left;
    width: 100%;
  }
  @media (max-width: 540px) { .item { grid-template-columns: 1fr; } .item__conn { display: none; } }
  .item:hover, .item.selected { background: rgba(255, 255, 255, 0.035); }
  .item.selected { box-shadow: inset 3px 0 0 var(--violet-400); }
  .item__type {
    font-family: var(--font-mono);
    font-size: 10px; letter-spacing: 0.14em;
    margin-top: 3px; text-transform: uppercase;
  }
  .item__main { min-width: 0; }
  .item strong {
    color: var(--fg-1); display: block;
    font-size: 14px; line-height: 1.35;
    overflow-wrap: anywhere;
  }
  .item small {
    color: var(--fg-3); display: block;
    font-family: var(--font-mono); font-size: 10px;
    line-height: 1.45; margin-top: 4px;
    overflow-wrap: anywhere;
  }
  .tags { display: flex; flex-wrap: wrap; gap: 5px; margin-top: 8px; }
  .tags span {
    background: rgba(255, 255, 255, 0.05);
    border: 1px solid var(--border-1); border-radius: 4px;
    color: var(--fg-2);
    font-family: var(--font-mono); font-size: 10px; line-height: 1;
    padding: 4px 6px;
  }
  .tags--detail { margin-bottom: 16px; }

  .detail {
    padding: 18px 20px;
    background: var(--bg-2);
    border: 1px solid var(--border-1);
    border-radius: 10px;
    position: sticky;
    top: 88px;
  }
  @media (max-width: 980px) { .detail { position: static; } }
  .detail__sub { color: var(--fg-3); font-size: 12.5px; font-family: var(--font-mono); margin: 0 0 12px; overflow-wrap: anywhere; }
  .muted { color: var(--fg-3); font-size: 13px; line-height: 1.6; margin: 12px 0 0; }
  .muted code { font-size: 12px; }
  .error { color: var(--signal-error); font-family: var(--font-mono); font-size: 12px; margin: 10px 0 4px; }
  .body {
    background: var(--bg-inset);
    border: 1px solid var(--border-1);
    border-radius: 6px;
    margin: 10px 0 0;
    max-height: 440px;
    overflow: auto;
    padding: 14px;
  }
  .body code {
    background: transparent; border: 0; padding: 0;
    color: var(--fg-2);
    font-family: var(--font-mono); font-size: 11.5px; line-height: 1.55;
    white-space: pre-wrap;
  }

  /* ── Closer ───────────────────────────────────────────────────────── */
  .closer { padding: 56px 24px 96px; border-top: 1px solid var(--border-1); }
  .closer__inner { max-width: 760px; margin: 0 auto; }
  .closer h2 { font-family: var(--font-display); font-size: clamp(26px, 4vw, 38px); font-weight: 500; letter-spacing: -0.02em; line-height: 1.05; margin: 8px 0 14px; }
  .closer p { color: var(--fg-2); font-size: 15px; line-height: 1.65; max-width: 60ch; margin: 0 0 24px; }
  .closer__cta { display: grid; gap: 10px; }
  .cta {
    display: grid; gap: 4px; padding: 14px 16px;
    background: var(--bg-2); border: 1px solid var(--border-1); border-radius: 8px;
    color: inherit; text-decoration: none;
    transition: border-color var(--dur-fast) var(--ease-standard), transform var(--dur-fast) var(--ease-standard);
  }
  .cta:hover { border-color: var(--border-2); transform: translateY(-1px); }
  .cta--primary { border-color: rgba(138, 99, 206, 0.45); background: rgba(138, 99, 206, 0.05); }
  .cta strong { color: var(--fg-1); font-family: var(--font-display); font-size: 18px; font-weight: 500; }
  .cta span { color: var(--fg-2); font-size: 13px; line-height: 1.45; }

  /* ── Lineage ──────────────────────────────────────────────────────── */
  .ch--lineage { border-top: 1px solid var(--border-1); }
  .lineage {
    list-style: none;
    margin: 18px 0 24px;
    padding: 0;
    display: grid;
    gap: 12px;
  }
  .lineage li {
    padding: 16px 18px;
    background: var(--bg-2);
    border: 1px solid var(--border-1);
    border-left: 2px solid var(--violet-400);
    border-radius: 6px;
    display: grid;
    gap: 8px;
  }
  .lineage header {
    display: flex;
    justify-content: space-between;
    align-items: baseline;
    gap: 10px;
    flex-wrap: wrap;
  }
  .lineage strong {
    color: var(--fg-1);
    font-family: var(--font-display);
    font-size: 18px;
    font-weight: 500;
    letter-spacing: -0.01em;
  }
  .lineage a {
    color: var(--signal-live);
    font-family: var(--font-mono);
    font-size: 10.5px;
    letter-spacing: 0.08em;
    text-decoration: none;
    text-transform: uppercase;
  }
  .lineage a:hover { color: var(--fg-1); text-decoration: underline; }
  .lineage p {
    color: var(--fg-2);
    font-size: 14px;
    line-height: 1.6;
    margin: 0;
  }
  .lineage p em { color: var(--ember-300); font-style: italic; }
  .lineage p code { background: rgba(255,255,255,0.05); border: 1px solid var(--border-1); border-radius: 3px; color: var(--violet-200); font-family: var(--font-mono); font-size: 0.85em; padding: 1px 4px; }


  .wiki-actions { display: flex; align-items: center; gap: 12px; flex-wrap: wrap; margin-top: 14px; }
  .wiki-action { background: transparent; border: 1px solid rgba(138,99,206,0.45); border-radius: 999px; color: var(--violet-200); cursor: pointer; font-family: var(--font-mono); font-size: 11.5px; letter-spacing: 0.06em; padding: 8px 16px; text-decoration: none; transition: border-color var(--dur-fast) var(--ease-standard), background var(--dur-fast) var(--ease-standard); }
  .wiki-action:hover { border-color: rgba(138,99,206,0.85); background: rgba(138,99,206,0.08); }
  .wiki-actions__hint { color: var(--fg-3); font-size: 12px; }
  .list__head .sort { display: inline-flex; align-items: center; gap: 6px; color: var(--fg-3); font-family: var(--font-mono); font-size: 10.5px; letter-spacing: 0.06em; text-transform: uppercase; }
  .list__head .sort select { background: var(--bg-inset); border: 1px solid var(--border-1); border-radius: 6px; color: var(--fg-1); font-family: var(--font-mono); font-size: 11px; padding: 3px 6px; }
  .item__conn { align-self: center; flex: none; color: var(--violet-200); font-family: var(--font-mono); font-size: 12px; border: 1px solid var(--border-1); border-radius: 999px; padding: 2px 9px; }
</style>
