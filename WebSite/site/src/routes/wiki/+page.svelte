<!--
  /wiki — live community wiki cockpit.
  Renders the baked MCP snapshot immediately. Browser-side live MCP reads are
  explicit actions because Cloudflare Access currently gates the public route.
-->
<script lang="ts">
  import baked from "$lib/content/mcp-snapshot.json";
  import { fetchLive, fetchPageBody, liveToSnapshotShape } from "$lib/mcp/live";
  import type { Snapshot } from "$lib/mcp/types";
  import RitualLabel from "$lib/components/Primitives/RitualLabel.svelte";
  import StatusPill from "$lib/components/Primitives/StatusPill.svelte";
  import LiveBadge from "$lib/components/LiveBadge.svelte";

  type Lens = "explore" | "bugs" | "work" | "plans" | "graph" | "pulse";
  type SortMode = "connected" | "type" | "title";
  type ItemType =
    | "goal"
    | "universe"
    | "bug"
    | "concept"
    | "note"
    | "plan"
    | "draft";
  type BodyStatus = "idle" | "loading" | "ready" | "error";
  type CopyState = "idle" | "copied" | "error";
  type WikiItem = {
    key: string;
    nodeId: string;
    type: ItemType;
    title: string;
    subtitle: string;
    slug?: string;
    tags: string[];
    connectionCount: number;
  };

  const LENSES: Array<{ id: Lens; label: string }> = [
    { id: "explore", label: "Explore" },
    { id: "bugs", label: "Bugs" },
    { id: "work", label: "Work" },
    { id: "plans", label: "Plans" },
    { id: "graph", label: "Graph" },
    { id: "pulse", label: "Pulse" },
  ];

  const WIKI_PROMPT =
    "Use Workflow to browse the community wiki. Show me current bugs, work targets, universes, and the most connected wiki pages, then suggest one patch or wiki improvement I can help with.";

  const TYPE_LABEL: Record<ItemType, string> = {
    goal: "work target",
    universe: "universe",
    bug: "bug",
    concept: "concept",
    note: "note",
    plan: "plan",
    draft: "draft",
  };

  const TYPE_TONE: Record<ItemType, string> = {
    goal: "var(--ember-600)",
    universe: "var(--signal-live)",
    bug: "var(--ember-500)",
    concept: "var(--violet-200)",
    note: "var(--violet-400)",
    plan: "var(--ember-300)",
    draft: "var(--signal-idle)",
  };

  let snapshot: Snapshot = $state(baked as unknown as Snapshot);
  let loading = $state(false);
  let liveError = $state<string | null>(null);
  let query = $state("");
  let lens = $state<Lens>("explore");
  let sortMode = $state<SortMode>("connected");
  let selectedKey = $state<string | null>(null);
  let bodyByKey = $state<Record<string, string>>({});
  let bodyStatusByKey = $state<Record<string, BodyStatus>>({});
  let bodyErrorByKey = $state<Record<string, string>>({});
  let copyState = $state<CopyState>("idle");
  let copyTimer = $state<number | undefined>(undefined);

  function slugId(path: string): string {
    return path.split("/").pop()?.replace(/\.md$/, "") ?? path;
  }

  function pageArg(path: string): string {
    return path.replace(/\.md$/, "");
  }

  function uniqueTags(tags: string[]): string[] {
    return [...new Set(tags.filter(Boolean))].slice(0, 5);
  }

  function itemMatchesLens(item: WikiItem): boolean {
    if (lens === "explore" || lens === "graph" || lens === "pulse") return true;
    if (lens === "bugs") return item.type === "bug";
    if (lens === "work")
      return item.type === "goal" || item.type === "universe";
    return (
      item.type === "plan" ||
      item.type === "concept" ||
      item.type === "note" ||
      item.type === "draft"
    );
  }

  function bySort(a: WikiItem, b: WikiItem): number {
    if (sortMode === "connected")
      return (
        b.connectionCount - a.connectionCount || a.title.localeCompare(b.title)
      );
    if (sortMode === "type")
      return a.type.localeCompare(b.type) || a.title.localeCompare(b.title);
    return a.title.localeCompare(b.title);
  }

  const degreeByNode = $derived.by(() => {
    const degree = new Map<string, number>();
    for (const edge of snapshot.edges ?? []) {
      degree.set(edge.from, (degree.get(edge.from) ?? 0) + 1);
      degree.set(edge.to, (degree.get(edge.to) ?? 0) + 1);
    }
    return degree;
  });

  const allItems = $derived.by((): WikiItem[] => {
    const items: WikiItem[] = [];
    const tags = snapshot.tags ?? {};

    for (const goal of snapshot.goals ?? []) {
      const nodeId = `goal:${goal.id}`;
      items.push({
        key: nodeId,
        nodeId,
        type: "goal",
        title: goal.name,
        subtitle: goal.summary || goal.id,
        tags: uniqueTags(goal.tags ?? tags[nodeId] ?? []),
        connectionCount: degreeByNode.get(nodeId) ?? 0,
      });
    }

    for (const universe of snapshot.universes ?? []) {
      const nodeId = `universe:${universe.id}`;
      items.push({
        key: nodeId,
        nodeId,
        type: "universe",
        title: universe.id,
        subtitle: `${universe.phase} · ${universe.word_count.toLocaleString()} words${universe.last_activity_at ? ` · ${universe.last_activity_at}` : ""}`,
        tags: uniqueTags(["universe", universe.phase]),
        connectionCount: degreeByNode.get(nodeId) ?? 0,
      });
    }

    for (const bug of snapshot.wiki?.bugs ?? []) {
      const nodeId = `bug:${bug.id}`;
      items.push({
        key: nodeId,
        nodeId,
        type: "bug",
        title: `${bug.id} — ${bug.title}`,
        subtitle: bug.slug ?? bug.id,
        slug: bug.slug,
        tags: uniqueTags(tags[nodeId] ?? ["bug"]),
        connectionCount: degreeByNode.get(nodeId) ?? 0,
      });
    }

    for (const plan of snapshot.wiki?.plans ?? []) {
      const nodeId = `plan:${slugId(plan.slug)}`;
      items.push({
        key: nodeId,
        nodeId,
        type: "plan",
        title: plan.title,
        subtitle: plan.slug,
        slug: plan.slug,
        tags: uniqueTags(tags[nodeId] ?? ["plan"]),
        connectionCount: degreeByNode.get(nodeId) ?? 0,
      });
    }

    for (const concept of snapshot.wiki?.concepts ?? []) {
      const nodeId = `concept:${slugId(concept.slug)}`;
      items.push({
        key: nodeId,
        nodeId,
        type: "concept",
        title: concept.title,
        subtitle: concept.slug,
        slug: concept.slug,
        tags: uniqueTags(tags[nodeId] ?? ["concept"]),
        connectionCount: degreeByNode.get(nodeId) ?? 0,
      });
    }

    for (const note of snapshot.wiki?.notes ?? []) {
      const nodeId = `note:${slugId(note.slug)}`;
      items.push({
        key: nodeId,
        nodeId,
        type: "note",
        title: note.title,
        subtitle: note.slug,
        slug: note.slug,
        tags: uniqueTags(tags[nodeId] ?? ["note"]),
        connectionCount: degreeByNode.get(nodeId) ?? 0,
      });
    }

    for (const draft of snapshot.wiki?.drafts ?? []) {
      const nodeId = `draft:${draft.slug}`;
      items.push({
        key: nodeId,
        nodeId,
        type: "draft",
        title: draft.title,
        subtitle: draft.slug,
        slug: draft.slug,
        tags: uniqueTags(tags[nodeId] ?? ["draft"]),
        connectionCount: degreeByNode.get(nodeId) ?? 0,
      });
    }

    return items;
  });

  const filteredItems = $derived.by(() => {
    const needle = query.trim().toLowerCase();
    return allItems
      .filter(itemMatchesLens)
      .filter((item) => {
        if (!needle) return true;
        return [item.title, item.subtitle, item.type, ...item.tags]
          .join(" ")
          .toLowerCase()
          .includes(needle);
      })
      .toSorted(bySort);
  });

  const topConnected = $derived.by(() =>
    allItems
      .toSorted((a, b) => b.connectionCount - a.connectionCount)
      .slice(0, 8),
  );
  const selectedItem = $derived(
    selectedKey
      ? (allItems.find((item) => item.key === selectedKey) ?? null)
      : null,
  );
  const selectedBody = $derived(
    selectedKey ? bodyByKey[selectedKey] : undefined,
  );
  const selectedBodyStatus = $derived(
    selectedKey ? (bodyStatusByKey[selectedKey] ?? "idle") : "idle",
  );
  const selectedBodyError = $derived(
    selectedKey ? bodyErrorByKey[selectedKey] : undefined,
  );

  const relatedItems = $derived.by(() => {
    if (!selectedItem) return [];
    return (snapshot.edges ?? [])
      .filter(
        (edge) =>
          edge.from === selectedItem.nodeId || edge.to === selectedItem.nodeId,
      )
      .map((edge) => {
        const otherId = edge.from === selectedItem.nodeId ? edge.to : edge.from;
        const item = allItems.find((candidate) => candidate.nodeId === otherId);
        return {
          key: item?.key ?? otherId,
          title: item?.title ?? otherId,
          type: item?.type ?? "note",
          kind: edge.kind ?? "ref",
          direction: edge.from === selectedItem.nodeId ? "out" : "in",
        };
      })
      .slice(0, 12);
  });

  const protocolTrace = $derived.by(() => {
    if (!selectedItem) {
      return {
        request: {
          calls: [
            { tool: "wiki", arguments: { action: "list" } },
            { tool: "goals", arguments: { action: "list" } },
            { tool: "universe", arguments: { action: "list" } },
          ],
        },
        response: {
          source: snapshot.source,
          fetched_at: snapshot.fetched_at,
          counts: snapshot.stats,
        },
      };
    }

    if (selectedItem.slug) {
      return {
        request: {
          tool: "wiki",
          arguments: { action: "read", page: pageArg(selectedItem.slug) },
        },
        response: {
          status: selectedBodyStatus,
          content_chars: selectedBody?.length ?? 0,
          related_edges: relatedItems.length,
          error: selectedBodyError,
        },
      };
    }

    return {
      request: {
        tool: selectedItem.type === "goal" ? "goals" : "universe",
        arguments: { action: "list" },
      },
      response: {
        status: "snapshot metadata",
        node_id: selectedItem.nodeId,
        related_edges: relatedItems.length,
      },
    };
  });

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

  async function copyWikiPrompt() {
    try {
      await navigator.clipboard.writeText(WIKI_PROMPT);
      copyState = "copied";
    } catch {
      copyState = "error";
    }

    if (copyTimer) window.clearTimeout(copyTimer);
    if (copyState === "copied") {
      copyTimer = window.setTimeout(() => {
        copyState = "idle";
      }, 2400);
    }
  }

  function selectItem(item: WikiItem) {
    selectedKey = item.key;
  }

  async function loadBody(item: WikiItem | null) {
    if (
      !item?.slug ||
      bodyByKey[item.key] ||
      bodyStatusByKey[item.key] === "loading"
    )
      return;

    bodyStatusByKey = { ...bodyStatusByKey, [item.key]: "loading" };
    bodyErrorByKey = { ...bodyErrorByKey, [item.key]: "" };
    try {
      const body = await fetchPageBody(item.slug);
      const content = body?.content ?? "";
      if (!content) throw new Error("read returned no content");
      bodyByKey = { ...bodyByKey, [item.key]: content };
      bodyStatusByKey = { ...bodyStatusByKey, [item.key]: "ready" };
    } catch (e: any) {
      bodyStatusByKey = { ...bodyStatusByKey, [item.key]: "error" };
      bodyErrorByKey = {
        ...bodyErrorByKey,
        [item.key]: e?.message ?? String(e),
      };
    }
  }

  async function loadSelectedBody() {
    await loadBody(selectedItem);
  }

  function selectByKey(key: string) {
    const item = allItems.find((candidate) => candidate.key === key);
    if (item) selectItem(item);
  }
</script>

<svelte:head>
  <title>Live wiki — Workflow</title>
  <meta
    name="description"
    content="Browse the live Workflow community wiki: bugs, plans, work targets, universes, graph links, and MCP proof in one public surface."
  />
</svelte:head>

<section class="hero">
  <div class="container">
    <div class="head__row">
      <RitualLabel color="var(--ember-500)"
        >· {snapshot.source} · community wiki ·</RitualLabel
      >
      <div class="head__actions">
        <LiveBadge
          fetchedAt={snapshot.fetched_at}
          source={snapshot.source}
          {loading}
        />
        <button
          type="button"
          class="refresh"
          disabled={loading}
          aria-busy={loading}
          onclick={refreshLive}
        >
          Refresh MCP
        </button>
      </div>
    </div>
    <h1>The community wiki is the public work surface.</h1>
    <p class="lead">
      Bugs, plans, work targets, universes, drafts, tags, and graph edges all
      resolve here through the same MCP-shaped records a connected chatbot can
      read.
    </p>
    <div class="hero__actions" aria-label="Community wiki actions">
      <a class="hero__action hero__action--primary" href="/connect"
        >Add it to chat</a
      >
      <button type="button" class="hero__action" onclick={copyWikiPrompt}>
        {copyState === "copied"
          ? "Copied prompt"
          : copyState === "error"
            ? "Copy failed"
            : "Copy wiki prompt"}
      </button>
      <a class="hero__action" href="/graph">Open graph</a>
    </div>
    <p class="copy-status" aria-live="polite">
      {copyState === "copied"
        ? "Prompt copied for any MCP-capable chatbot."
        : copyState === "error"
          ? `Copy manually: ${WIKI_PROMPT}`
          : ""}
    </p>
    {#if liveError}
      <p class="error">
        Live browser fetch failed: <code>{liveError}</code> — showing the baked MCP
        snapshot.
      </p>
    {/if}
  </div>
</section>

<section class="cockpit">
  <div class="container cockpit__grid">
    <div class="surface">
      <div class="toolbar" aria-label="Wiki controls">
        <label class="search">
          <span>Search wiki</span>
          <input
            bind:value={query}
            type="search"
            placeholder="BUG-034, patch loop, agent teams..."
          />
        </label>
        <div class="segments" role="tablist" aria-label="Wiki lenses">
          {#each LENSES as option}
            <button
              type="button"
              class:active={lens === option.id}
              role="tab"
              aria-selected={lens === option.id}
              onclick={() => (lens = option.id)}
            >
              {option.label}
            </button>
          {/each}
        </div>
        <label class="sort">
          <span>Sort</span>
          <select bind:value={sortMode}>
            <option value="connected">Most connected</option>
            <option value="type">Type</option>
            <option value="title">Title</option>
          </select>
        </label>
      </div>

      {#if lens === "pulse"}
        <div class="pulse">
          <article>
            <RitualLabel color="var(--signal-live)"
              >· Current pulse ·</RitualLabel
            >
            <h2>
              {snapshot.universes.length} universes, {snapshot.goals.length} work
              targets.
            </h2>
            <p>
              The public feed is thin live state: identity, phase, counts, and
              artifact handles. The durable material stays in community wiki
              pages and graph references.
            </p>
          </article>
          <div class="pulse__facts">
            {#each snapshot.universes as universe}
              <button
                type="button"
                class="pulse__fact"
                onclick={() => selectByKey(`universe:${universe.id}`)}
              >
                <span>{universe.id}</span>
                <strong>{universe.phase}</strong>
                <small>{universe.word_count.toLocaleString()} words</small>
              </button>
            {/each}
          </div>
        </div>
      {:else if lens === "graph"}
        <div class="graphlens">
          <article>
            <RitualLabel color="var(--violet-400)"
              >· Relationship lens ·</RitualLabel
            >
            <h2>The graph is already in the snapshot.</h2>
            <p>
              Edges come from page bodies: wiki links, bare bug tokens, and
              frontmatter references. The list below is ordered by how much each
              node ties the community wiki together.
            </p>
          </article>
          <ol class="connected">
            {#each topConnected as item}
              <li>
                <button type="button" onclick={() => selectItem(item)}>
                  <span class="connected__rank">{item.connectionCount}</span>
                  <span class="connected__body">
                    <strong>{item.title}</strong>
                    <small>{TYPE_LABEL[item.type]} · {item.nodeId}</small>
                  </span>
                </button>
              </li>
            {/each}
          </ol>
        </div>
      {/if}

      <div class="results__head">
        <RitualLabel>· {filteredItems.length} visible ·</RitualLabel>
        <span>{query ? `filtered by "${query}"` : "snapshot browse"}</span>
      </div>

      <ul class="results">
        {#each filteredItems as item (item.key)}
          <li>
            <button
              type="button"
              class="item"
              class:selected={selectedKey === item.key}
              onclick={() => selectItem(item)}
            >
              <span class="item__type" style:color={TYPE_TONE[item.type]}
                >{TYPE_LABEL[item.type]}</span
              >
              <span class="item__main">
                <strong>{item.title}</strong>
                <small>{item.subtitle}</small>
                {#if item.tags.length}
                  <span class="tags">
                    {#each item.tags as tag}<span>{tag}</span>{/each}
                  </span>
                {/if}
              </span>
              <span class="item__edges">{item.connectionCount}</span>
            </button>
          </li>
        {/each}
      </ul>
    </div>

    <aside class="detail" aria-label="Selected wiki item">
      {#if selectedItem}
        <div class="detail__head">
          <RitualLabel color={TYPE_TONE[selectedItem.type]}
            >· {TYPE_LABEL[selectedItem.type]} ·</RitualLabel
          >
          <StatusPill
            kind={selectedItem.type === "universe"
              ? "live"
              : selectedItem.type === "draft"
                ? "idle"
                : "self"}
          >
            {selectedItem.connectionCount} edges
          </StatusPill>
        </div>
        <h2>{selectedItem.title}</h2>
        <p>{selectedItem.subtitle}</p>
        {#if selectedItem.tags.length}
          <div class="tags tags--detail">
            {#each selectedItem.tags as tag}<span>{tag}</span>{/each}
          </div>
        {/if}

        <div class="readout">
          <RitualLabel>· Body readout ·</RitualLabel>
          {#if selectedItem.slug}
            {#if selectedBodyStatus === "loading"}
              <p class="muted">
                Fetching <code>wiki action=read</code> through the browser MCP path...
              </p>
            {:else if selectedBodyStatus === "ready"}
              <pre class="body"><code>{selectedBody}</code></pre>
            {:else if selectedBodyStatus === "error"}
              <p class="error error--panel">
                Browser-side read failed: <code>{selectedBodyError}</code>
              </p>
              <p class="muted">
                The snapshot still carries this page's title, tags, and graph
                links. True browser reads need the public read-only MCP route
                described in DEPLOY.md.
              </p>
            {:else}
              <p class="muted">
                Fetch the body through <code>wiki action=read</code>. This may
                fail in-browser until the public read-only MCP route is open.
              </p>
              <button
                type="button"
                class="inline-action"
                onclick={loadSelectedBody}>Fetch body</button
              >
            {/if}
          {:else}
            <p class="muted">
              This item comes from a list endpoint, so the detail is snapshot
              metadata rather than a wiki page body.
            </p>
          {/if}
        </div>

        <div class="related">
          <RitualLabel>· Related nodes ·</RitualLabel>
          {#if relatedItems.length}
            <div class="related__list">
              {#each relatedItems as related}
                <button type="button" onclick={() => selectByKey(related.key)}>
                  <span>{related.kind} · {related.direction}</span>
                  <strong>{related.title}</strong>
                </button>
              {/each}
            </div>
          {:else}
            <p class="muted">No parsed graph edge points at this node yet.</p>
          {/if}
        </div>
      {:else}
        <RitualLabel>· Select a wiki item ·</RitualLabel>
        <h2>The detail pane shows the proof path.</h2>
        <p>
          Choose a wiki page, work target, draft, or universe to inspect tags,
          edges, body text, and the MCP request shape behind it.
        </p>
      {/if}

      <details class="trace">
        <summary>
          <span>Technical proof</span>
          <strong>MCP request trace</strong>
        </summary>
        <pre><code>{JSON.stringify(protocolTrace, null, 2)}</code></pre>
      </details>
    </aside>
  </div>
</section>

<style>
  .hero {
    padding-top: 80px;
    padding-bottom: 40px;
  }

  .head__row,
  .detail__head {
    display: flex;
    align-items: center;
    justify-content: space-between;
    gap: 12px;
    flex-wrap: wrap;
  }

  .head__actions {
    align-items: center;
    display: flex;
    gap: 10px;
    flex-wrap: wrap;
  }

  .hero__actions {
    align-items: center;
    display: flex;
    flex-wrap: wrap;
    gap: 10px;
    margin-top: 22px;
  }

  .hero__action {
    align-items: center;
    background: var(--bg-2);
    border: 1px solid var(--border-2);
    border-radius: 6px;
    color: var(--fg-1);
    cursor: pointer;
    display: inline-flex;
    font: 12px var(--font-mono);
    justify-content: center;
    letter-spacing: 0.08em;
    min-height: 38px;
    padding: 0 14px;
    text-decoration: none;
    text-transform: uppercase;
  }

  .hero__action:hover {
    background: rgba(255, 255, 255, 0.05);
    border-color: rgba(255, 255, 255, 0.28);
  }

  .hero__action--primary {
    background: var(--ember-600);
    border-color: var(--ember-600);
    color: var(--bg-0);
  }

  .hero__action--primary:hover {
    background: var(--ember-500);
  }

  .copy-status {
    color: var(--fg-3);
    font-family: var(--font-mono);
    font-size: 11px;
    min-height: 18px;
    margin: 8px 0 0;
  }

  .lead {
    color: var(--fg-2);
    font-size: clamp(16px, 2vw, 19px);
    line-height: 1.55;
    margin: 14px 0 0;
    max-width: 760px;
  }

  .refresh,
  .inline-action {
    background: transparent;
    border: 1px solid var(--border-2);
    border-radius: 6px;
    color: var(--fg-1);
    cursor: pointer;
    font: 11px var(--font-mono);
    letter-spacing: 0.1em;
    min-height: 32px;
    padding: 0 10px;
    text-transform: uppercase;
  }

  .refresh:hover,
  .inline-action:hover {
    background: rgba(255, 255, 255, 0.04);
    border-color: rgba(255, 255, 255, 0.22);
  }

  .refresh:disabled {
    color: var(--fg-4);
    cursor: wait;
  }

  h1 {
    font-family: var(--font-display);
    font-size: clamp(44px, 7vw, 72px);
    font-weight: 400;
    letter-spacing: -0.035em;
    line-height: 0.95;
    margin: 14px 0 18px;
    max-width: 11ch;
  }

  h2 {
    font-family: var(--font-display);
    font-size: clamp(22px, 3vw, 30px);
    font-weight: 500;
    letter-spacing: -0.02em;
    margin: 10px 0 12px;
  }

  .error {
    color: var(--signal-error);
    font-family: var(--font-mono);
    font-size: 12px;
    line-height: 1.55;
    margin: 0 0 16px;
    max-width: 80ch;
  }

  .error code {
    color: var(--signal-error);
  }

  .cockpit {
    border-top: 1px solid var(--border-1);
    padding: 28px 0 64px;
  }

  .cockpit__grid {
    display: grid;
    grid-template-columns: minmax(0, 1fr) minmax(320px, 420px);
    gap: 18px;
    align-items: start;
  }

  @media (max-width: 980px) {
    .cockpit__grid {
      grid-template-columns: 1fr;
    }
  }

  .surface,
  .detail {
    background: var(--bg-2);
    border: 1px solid var(--border-1);
    border-radius: 8px;
  }

  .surface {
    overflow: hidden;
  }

  .detail {
    padding: 18px;
    position: sticky;
    top: 88px;
  }

  @media (max-width: 980px) {
    .detail {
      position: static;
    }
  }

  .toolbar {
    display: grid;
    grid-template-columns: minmax(220px, 1fr) auto 150px;
    gap: 12px;
    padding: 14px;
    border-bottom: 1px solid var(--border-1);
    align-items: end;
  }

  @media (max-width: 900px) {
    .toolbar {
      grid-template-columns: 1fr;
    }
  }

  label span,
  .results__head span {
    color: var(--fg-3);
    display: block;
    font-family: var(--font-mono);
    font-size: 10px;
    letter-spacing: 0.12em;
    margin-bottom: 6px;
    text-transform: uppercase;
  }

  input,
  select {
    background: var(--bg-inset);
    border: 1px solid var(--border-1);
    border-radius: 6px;
    color: var(--fg-1);
    font: 13px var(--font-sans);
    min-height: 38px;
    outline: none;
    padding: 0 12px;
    width: 100%;
  }

  input:focus,
  select:focus {
    border-color: rgba(233, 69, 96, 0.55);
    box-shadow: 0 0 0 3px rgba(233, 69, 96, 0.12);
  }

  .segments {
    align-items: center;
    background: var(--bg-inset);
    border: 1px solid var(--border-1);
    border-radius: 8px;
    display: flex;
    flex-wrap: wrap;
    gap: 4px;
    padding: 4px;
  }

  .segments button {
    background: transparent;
    border: 1px solid transparent;
    border-radius: 5px;
    color: var(--fg-2);
    cursor: pointer;
    font: 11px var(--font-mono);
    letter-spacing: 0.08em;
    min-height: 30px;
    padding: 0 10px;
    text-transform: uppercase;
  }

  .segments button.active,
  .segments button:hover {
    background: rgba(233, 69, 96, 0.12);
    border-color: rgba(233, 69, 96, 0.24);
    color: var(--fg-1);
  }

  .pulse,
  .graphlens {
    display: grid;
    grid-template-columns: minmax(0, 1fr) minmax(240px, 360px);
    gap: 16px;
    padding: 18px;
    border-bottom: 1px solid var(--border-1);
  }

  @media (max-width: 800px) {
    .pulse,
    .graphlens {
      grid-template-columns: 1fr;
    }
  }

  .pulse p,
  .graphlens p,
  .detail p,
  .muted {
    color: var(--fg-2);
    font-size: 13px;
    line-height: 1.6;
    margin: 0 0 12px;
  }

  .pulse__facts,
  .connected {
    display: flex;
    flex-direction: column;
    gap: 8px;
    list-style: none;
    margin: 0;
    padding: 0;
  }

  .pulse__fact,
  .connected button,
  .related__list button {
    background: var(--bg-inset);
    border: 1px solid var(--border-1);
    border-radius: 6px;
    color: var(--fg-1);
    cursor: pointer;
    padding: 10px 12px;
    text-align: left;
    width: 100%;
  }

  .pulse__fact:hover,
  .connected button:hover,
  .related__list button:hover {
    border-color: var(--border-2);
    background: rgba(255, 255, 255, 0.04);
  }

  .pulse__fact span,
  .pulse__fact strong,
  .pulse__fact small {
    display: block;
  }

  .pulse__fact span,
  .connected small,
  .related__list span {
    color: var(--fg-3);
    font-family: var(--font-mono);
    font-size: 10px;
    letter-spacing: 0.08em;
    text-transform: uppercase;
  }

  .pulse__fact strong,
  .connected strong,
  .related__list strong {
    color: var(--fg-1);
    display: block;
    font-size: 13px;
    line-height: 1.35;
    margin-top: 3px;
  }

  .pulse__fact small {
    color: var(--fg-2);
    font-family: var(--font-mono);
    font-size: 11px;
    margin-top: 4px;
  }

  .connected button {
    align-items: center;
    display: grid;
    grid-template-columns: 42px 1fr;
    gap: 10px;
  }

  .connected__rank {
    color: var(--ember-600);
    font-family: var(--font-display);
    font-size: 28px;
    line-height: 1;
    text-align: center;
  }

  .results__head {
    align-items: center;
    border-bottom: 1px solid var(--border-1);
    display: flex;
    justify-content: space-between;
    padding: 12px 14px;
  }

  .results__head span {
    margin: 0;
    text-transform: none;
  }

  .results {
    list-style: none;
    margin: 0;
    max-height: 760px;
    overflow: auto;
    padding: 0;
  }

  .item {
    align-items: start;
    background: transparent;
    border: 0;
    border-bottom: 1px solid var(--border-1);
    color: inherit;
    cursor: pointer;
    display: grid;
    gap: 12px;
    grid-template-columns: 82px minmax(0, 1fr) 42px;
    padding: 13px 14px;
    text-align: left;
    width: 100%;
  }

  @media (max-width: 620px) {
    .item {
      grid-template-columns: 1fr;
    }
  }

  .item:hover,
  .item.selected {
    background: rgba(255, 255, 255, 0.035);
  }

  .item.selected {
    box-shadow: inset 3px 0 0 var(--ember-600);
  }

  .item__type {
    font-family: var(--font-mono);
    font-size: 10px;
    letter-spacing: 0.14em;
    margin-top: 3px;
    text-transform: uppercase;
  }

  .item__main {
    min-width: 0;
  }

  .item strong {
    color: var(--fg-1);
    display: block;
    font-size: 14px;
    line-height: 1.35;
    overflow-wrap: anywhere;
  }

  .item small {
    color: var(--fg-3);
    display: block;
    font-family: var(--font-mono);
    font-size: 10px;
    line-height: 1.45;
    margin-top: 4px;
    overflow-wrap: anywhere;
  }

  .item__edges {
    align-self: start;
    background: var(--bg-inset);
    border: 1px solid var(--border-1);
    border-radius: 999px;
    color: var(--fg-2);
    font-family: var(--font-mono);
    font-size: 11px;
    padding: 3px 8px;
    text-align: center;
  }

  .tags {
    display: flex;
    flex-wrap: wrap;
    gap: 5px;
    margin-top: 8px;
  }

  .tags span {
    background: rgba(255, 255, 255, 0.05);
    border: 1px solid var(--border-1);
    border-radius: 4px;
    color: var(--fg-2);
    font-family: var(--font-mono);
    font-size: 10px;
    line-height: 1;
    padding: 4px 6px;
  }

  .tags--detail {
    margin-bottom: 16px;
  }

  .readout,
  .related,
  .trace {
    border-top: 1px solid var(--border-1);
    margin-top: 16px;
    padding-top: 16px;
  }

  .body,
  .trace pre {
    background: var(--bg-inset);
    border: 1px solid var(--border-1);
    border-radius: 6px;
    margin: 10px 0 0;
    max-height: 380px;
    overflow: auto;
    padding: 12px;
  }

  .body code,
  .trace code {
    background: transparent;
    border: 0;
    color: var(--fg-2);
    font-size: 11px;
    line-height: 1.55;
    padding: 0;
    white-space: pre-wrap;
  }

  .trace summary {
    align-items: center;
    color: var(--fg-1);
    cursor: pointer;
    display: flex;
    justify-content: space-between;
    gap: 12px;
    list-style: none;
    min-height: 38px;
    padding-block: 4px;
    touch-action: manipulation;
  }

  .trace summary::-webkit-details-marker {
    display: none;
  }

  .trace summary span {
    color: var(--violet-200);
    font-family: var(--font-mono);
    font-size: 10px;
    letter-spacing: 0.12em;
    text-transform: uppercase;
  }

  .trace summary strong {
    font-size: 13px;
    font-weight: 600;
  }

  .related__list {
    display: flex;
    flex-direction: column;
    gap: 8px;
    margin-top: 10px;
  }

  .error--panel {
    margin-top: 10px;
  }
</style>
