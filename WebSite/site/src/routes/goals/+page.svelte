<!--
  /goals — the living board of what's being worked on. "Field Notes"
  rebuild, 2026-06-09.

  Crawl fixes applied: jargon wall removed (goal / workflow / ladder each
  get a first-use <Term>; "commons records", "branch signals", "canon-gate",
  "Goal lens" all dropped). No repo-internals readouts — the old
  "GitHub source: local git checkout" leak is gone entirely. The board is
  not empty without JS: it paints from the baked snapshot immediately,
  visibly stamped with its fetched date, then upgrades to a live read on
  mount. Every live value carries a read-stamp; baked is labelled baked.
  Public-commons only: private / SUPERSEDED / RETRACTED / smoke filtered out.
-->
<script lang="ts">
  import { onMount } from 'svelte';
  import { callTool } from '$lib/mcp/live';
  import bakedMcp from '$lib/content/mcp-snapshot.json';
  import { fmtDate, fmtRel } from '$lib/fmt';
  import Ladder from '$lib/components/Ladder.svelte';
  import Term from '$lib/components/Term.svelte';
  import Tick from '$lib/components/Tick.svelte';

  // ── A board goal, normalized from either the baked snapshot or a live read.
  type Rung = { key?: string; name: string; description?: string; lit?: boolean; evidence_url?: string };
  type BoardGoal = {
    id: string;
    name: string;
    description: string;
    tags: string[];
    visibility: string;
    rungs: Rung[];
    updatedMs: number | null;
  };

  // Public-commons rail: nothing private, nothing retired, no smoke tests.
  function isPublicGoal(name: string, visibility: string): boolean {
    if ((visibility ?? 'public').toLowerCase() === 'private') return false;
    return !/SUPERSEDED|RETRACTED|smoke/i.test(name ?? '');
  }

  function toTags(raw: unknown): string[] {
    if (Array.isArray(raw)) return raw.map((t) => String(t).trim()).filter(Boolean);
    if (typeof raw === 'string') return raw.split(',').map((t) => t.trim()).filter(Boolean);
    return [];
  }

  // Live goals carry a gate_ladder of {name, rung_key, description}. No rung
  // arrives with evidence attached today, so every rung renders unlit — that
  // is the honest state, and the section copy owns it.
  function toRungs(raw: unknown): Rung[] {
    if (!Array.isArray(raw)) return [];
    return raw
      .map((r: any) => ({
        key: r?.rung_key ?? r?.key ?? r?.name,
        name: String(r?.name ?? r?.rung_key ?? '').trim(),
        description: r?.description ? String(r.description) : undefined,
        // A rung only lights with a real evidence URL; absent one, unlit.
        lit: Boolean(r?.lit && r?.evidence_url),
        evidence_url: r?.evidence_url ?? undefined
      }))
      .filter((r) => r.name);
  }

  // Live timestamps are Unix epoch SECONDS (floats); baked goals carry none.
  function toMs(value: unknown): number | null {
    if (typeof value === 'number' && Number.isFinite(value)) return value * 1000;
    if (typeof value === 'string') {
      const n = Number(value);
      if (Number.isFinite(n) && n > 0) return n * 1000;
      const p = Date.parse(value);
      if (!Number.isNaN(p)) return p;
    }
    return null;
  }

  function normalizeBaked(raw: any): BoardGoal[] {
    return (raw?.goals ?? [])
      .filter((g: any) => isPublicGoal(g.name, g.visibility))
      .map((g: any) => ({
        id: String(g.id ?? g.goal_id ?? ''),
        name: String(g.name ?? ''),
        // Baked snapshot calls the body "summary"; live calls it "description".
        description: String(g.summary ?? g.description ?? ''),
        tags: toTags(g.tags),
        visibility: String(g.visibility ?? 'public'),
        rungs: toRungs(g.gate_ladder),
        updatedMs: toMs(g.updated_at ?? g.created_at)
      }));
  }

  function normalizeLive(raw: any): BoardGoal[] {
    return (raw?.goals ?? [])
      .filter((g: any) => isPublicGoal(g.name, g.visibility))
      .map((g: any) => ({
        id: String(g.goal_id ?? g.id ?? ''),
        name: String(g.name ?? ''),
        description: String(g.description ?? g.summary ?? ''),
        tags: toTags(g.tags),
        visibility: String(g.visibility ?? 'public'),
        rungs: toRungs(g.gate_ladder),
        updatedMs: toMs(g.updated_at ?? g.created_at)
      }))
      // Newest-updated first; goals with no timestamp sink to the bottom.
      .sort((a: BoardGoal, b: BoardGoal) => (b.updatedMs ?? 0) - (a.updatedMs ?? 0));
  }

  // First paint: baked, stamped with the snapshot's own fetched date. The
  // page is never blank-without-JS — these render server-side. The stamp goes
  // through $lib/fmt so it reads in the visitor's own local time.
  const bakedStampDate = fmtDate((bakedMcp as any).fetched_at);
  let goals = $state<BoardGoal[]>(normalizeBaked(bakedMcp));

  // 'baked' until a live read lands; then 'live' with a read-stamp.
  let phase = $state<'baked' | 'reading' | 'live' | 'error'>('baked');
  let readAt = $state<string | null>(null);
  let errMsg = $state<string | null>(null);

  async function refreshMcp() {
    phase = 'reading';
    errMsg = null;
    try {
      const res = await callTool('goals', { action: 'list' });
      const next = normalizeLive(res);
      goals = next;
      readAt = new Date().toISOString();
      phase = 'live';
    } catch (e: any) {
      errMsg = e?.message ?? String(e);
      phase = 'error';
    }
  }

  onMount(() => {
    void refreshMcp();
  });

  // ── Curation: keep the board honest without lying. Obvious internal test
  // debris (smoke/probe/post-redaction fixtures) is split into a labelled,
  // collapsed section rather than scrubbed silently — visitors can still see
  // it exists. Everything else is a real public goal.
  const TEST_DEBRIS = /smoke|probe|post-redaction/i;
  function isTestDebris(g: BoardGoal): boolean {
    return TEST_DEBRIS.test(g.name);
  }
  const realGoals = $derived(goals.filter((g) => !isTestDebris(g)));
  const debrisGoals = $derived(goals.filter(isTestDebris));

  // ── Domain filter. Each chip maps to a set of tag substrings; a goal matches
  // a domain if any of its tags contains any of the domain's terms. "All" is
  // the unfiltered view. Matching is client-side over the already-public set.
  type Domain = 'all' | 'research' | 'commerce' | 'games' | 'writing' | 'meta';
  const DOMAINS: { id: Domain; label: string; terms: string[] }[] = [
    { id: 'all', label: 'All', terms: [] },
    { id: 'research', label: 'research', terms: ['research', 'science', 'simulation', 'evidence', 'paper', 'archaeolog', 'biolog', 'physics', 'study'] },
    { id: 'commerce', label: 'commerce', terms: ['commerce', 'shop', 'retail', 'market', 'business', 'invoice', 'order', 'product', 'sales'] },
    { id: 'games', label: 'games & retro', terms: ['game', 'retro', 'arcade', 'rpg', 'classic-game', 'unreal', 'gameplay', 'level'] },
    { id: 'writing', label: 'writing', terms: ['writing', 'fiction', 'novel', 'story', 'screenplay', 'narrative', 'manuscript', 'prose', 'fantasy'] },
    { id: 'meta', label: 'meta/platform', terms: ['platform', 'workflow-substrate', 'primitive', 'meta', 'substrate', 'reusable-branch', 'convention', 'self'] }
  ];
  let activeDomain = $state<Domain>('all');
  function matchesDomain(g: BoardGoal, domain: Domain): boolean {
    if (domain === 'all') return true;
    const terms = DOMAINS.find((d) => d.id === domain)?.terms ?? [];
    if (!terms.length) return true;
    const hay = g.tags.join(' ').toLowerCase();
    return terms.some((t) => hay.includes(t));
  }
  const visibleGoals = $derived(realGoals.filter((g) => matchesDomain(g, activeDomain)));

  // The neutral prompt a visitor pastes into their own chatbot to add a goal.
  const ADD_PROMPT = "Propose a goal called <name> about <outcome>.";
  let copied = $state(false);
  let copyTimer: number | null = null;
  async function copyAddPrompt() {
    try {
      await navigator.clipboard.writeText(ADD_PROMPT);
      copied = true;
      if (copyTimer) clearTimeout(copyTimer);
      copyTimer = window.setTimeout(() => (copied = false), 1800);
    } catch { /* clipboard unavailable; the text is visible anyway */ }
  }

  const litCount = $derived(visibleGoals.reduce((n, g) => n + g.rungs.filter((r) => r.lit).length, 0));
  const ladderGoals = $derived(visibleGoals.filter((g) => g.rungs.length > 0).length);
</script>

<svelte:head>
  <title>Goals — the board of what Tiny is working on</title>
  <meta
    name="description"
    content="The living board of public goals on Tiny. A goal is an outcome; workflows compete to serve it; evidence-gated ladders make the outcome checkable. Read live from the same MCP endpoint your chatbot uses."
  />
  <link rel="canonical" href="https://tinyassets.io/goals" />
</svelte:head>

<!-- 1 · Hero — Tiny's voice ─────────────────────────────────────────────── -->
<section class="cover" aria-labelledby="cover-title">
  <div class="container">
    <p class="eyebrow">field notes · the board</p>
    <h1 id="cover-title" class="cover__title">These are the goals people gave me.</h1>
    <p class="voice cover__lede">
      A <Term def="A goal is the outcome someone is after — 'publish the paper', 'run the shop', 'ship the game'. It's shared: many workflows can compete to serve the same one.">goal</Term>
      is an outcome, not a method. Around each one,
      <Term def="A workflow is a graph of steps with typed state and checks, designed in plain language through your chatbot. Several can compete to reach the same goal; the best-performing one becomes canonical.">workflows</Term>
      compete to reach it — and a goal's
      <Term def="A ladder is a sequence of real-world rungs toward the outcome ('preprint posted', 'peer-reviewed', 'first order fulfilled'). A rung only lights with an evidence URL attached, so the outcome stays checkable instead of merely claimed.">ladder</Term>
      keeps the whole thing honest: each rung is a checkable event, and a rung
      only lights once there's evidence behind it. The board below reads from
      the same endpoint your chatbot would.
    </p>
  </div>
</section>

<!-- 2 · The board ───────────────────────────────────────────────────────── -->
<section class="ch ch--board" aria-labelledby="board-title">
  <div class="container">
    <header class="board__head">
      <div>
        <p class="eyebrow">entry · the public board</p>
        <h2 id="board-title">What's on me right now.</h2>
      </div>
      <div class="board__meta" aria-live="polite">
        {#if phase === 'live'}
          <span class="board__stamp ev"><span class="dot live" aria-hidden="true"></span>{realGoals.length} public goals · read live {fmtRel(readAt)}</span>
        {:else if phase === 'reading'}
          <span class="board__stamp ev"><span class="dot" aria-hidden="true"></span>reading the live board… (showing snapshot {bakedStampDate})</span>
        {:else if phase === 'error'}
          <span class="board__stamp ev"><span class="dot error" aria-hidden="true"></span>live read failed — showing snapshot {bakedStampDate}</span>
        {:else}
          <span class="board__stamp ev"><span class="dot" aria-hidden="true"></span>{realGoals.length} public goals · snapshot {bakedStampDate}</span>
        {/if}
        <button class="board__refresh" onclick={refreshMcp} disabled={phase === 'reading'}>
          {phase === 'reading' ? 'reading…' : 'Refresh MCP'}
        </button>
      </div>
    </header>

    {#if phase === 'error' && errMsg}
      <p class="board__err ev">The live read errored ({errMsg}). The cards below are the last good snapshot from {bakedStampDate}, not a live reading. Try Refresh MCP.</p>
    {/if}

    <!-- Domain filter chips. Match on tags, client-side, over the public set. -->
    <div class="board__filter" role="group" aria-label="Filter goals by domain">
      {#each DOMAINS as d}
        <button
          type="button"
          class="chip"
          class:chip--on={activeDomain === d.id}
          aria-pressed={activeDomain === d.id}
          onclick={() => (activeDomain = d.id)}
        >{d.label}</button>
      {/each}
    </div>

    {#if visibleGoals.length === 0}
      <p class="board__empty ev">
        {#if realGoals.length === 0}
          Quiet right now — no public goals visible at this read. The board retries on its own; you can also press Refresh MCP.
        {:else}
          No public goals match <strong>{DOMAINS.find((d) => d.id === activeDomain)?.label}</strong> in this read. Try <button class="linkish" onclick={() => (activeDomain = 'all')}>All</button>.
        {/if}
      </p>
    {:else}
      <ul class="board">
        {#each visibleGoals as g (g.id || g.name)}
          <li class="goal" class:goal--baked={phase !== 'live'}>
            <div class="goal__top">
              <h3 class="goal__name">
                <a class="goal__link" href="/goals/{g.id}">{g.name}</a>
              </h3>
              {#if g.description}
                <p class="goal__desc">{g.description}</p>
              {/if}
            </div>

            {#if g.tags.length}
              <ul class="goal__tags ev" aria-label="tags">
                {#each g.tags.slice(0, 5) as tag}
                  <li>{tag}</li>
                {/each}
                {#if g.tags.length > 5}
                  <li class="goal__tags-more">+{g.tags.length - 5}</li>
                {/if}
              </ul>
            {/if}

            {#if g.rungs.length}
              <div class="goal__ladder">
                <p class="goal__ladder-label eyebrow">outcome ladder · {g.rungs.length} rungs</p>
                <Ladder rungs={g.rungs} start="now" compact={true} />
              </div>
            {/if}

            <footer class="goal__foot">
              <Tick href="/goals/{g.id}" label={`goal ${g.id || 'unknown'}`} />
            </footer>
          </li>
        {/each}
      </ul>

      <p class="board__foot ev">
        {#if phase === 'live'}
          {visibleGoals.length} public goal{visibleGoals.length === 1 ? '' : 's'} shown{activeDomain === 'all' ? '' : ` · ${DOMAINS.find((d) => d.id === activeDomain)?.label} filter`} ·
          {ladderGoals} carry an outcome ladder · {litCount} rung{litCount === 1 ? '' : 's'} lit — the honest count · read {fmtRel(readAt)}
        {:else}
          showing the {bakedStampDate} snapshot · ladders and exact counts upgrade once the live read lands
        {/if}
      </p>
      <p class="board__honest ev">
        {visibleGoals.length} public goal{visibleGoals.length === 1 ? '' : 's'} shown · private goals exist but never render here — they live on a host's own machine and never publish to the public commons.
      </p>
    {/if}

    {#if debrisGoals.length}
      <details class="board__debris">
        <summary>internal test goals ({debrisGoals.length})</summary>
        <p class="board__debris-note ev">
          These are smoke / probe / fixture goals left by automated tests, not real public work. They're kept visible for honesty, just folded away.
        </p>
        <ul class="board__debris-list">
          {#each debrisGoals as g (g.id || g.name)}
            <li>
              <a href="/goals/{g.id}">{g.name}</a>
              <Tick href="/goals/{g.id}" label={`goal ${g.id || 'unknown'}`} />
            </li>
          {/each}
        </ul>
      </details>
    {/if}
  </div>
</section>

<!-- 3 · Put a goal on me ─────────────────────────────────────────────────── -->
<section class="ch ch--add" aria-labelledby="add-title">
  <div class="container ch__inner">
    <p class="eyebrow">entry · add to the board</p>
    <h2 id="add-title">Put a goal on me.</h2>
    <p class="add__lede">
      You don't fill out a form. You tell your own chatbot, and it proposes
      the goal through the connector. Two steps:
    </p>
    <ol class="add__steps">
      <li>
        <span class="add__n">1</span>
        <div>
          <strong>Connect your chatbot.</strong>
          <p>Paste one URL into Claude, ChatGPT, or any MCP-capable assistant — no account, no install.</p>
          <a class="add__cta" href="/start">how to connect →</a>
        </div>
      </li>
      <li>
        <span class="add__n">2</span>
        <div>
          <strong>Say what you want.</strong>
          <p>With the connector enabled, send your chatbot a sentence like this — swap the bracketed bits for your own:</p>
          <button type="button" class="add__prompt" onclick={copyAddPrompt} aria-label={`Copy prompt: ${ADD_PROMPT}`}>
            <code>{ADD_PROMPT}</code>
            <span class="add__copy">{copied ? 'copied ✓' : 'copy'}</span>
          </button>
          <p class="add__note">
            Your chatbot proposes it; you and it design a workflow toward it
            from there. The new goal shows up on this board on its next read.
          </p>
        </div>
      </li>
    </ol>
  </div>
</section>

<!-- 4 · Close ───────────────────────────────────────────────────────────── -->
<section class="ch ch--close" aria-labelledby="close-title">
  <div class="container ch__inner">
    <h2 id="close-title">Where this connects.</h2>
    <nav class="close__cards">
      <a class="close__card" href="/loop">
        <span class="close__k eyebrow">the patch loop</span>
        <strong>Watch a goal turn into shipped work →</strong>
        <span class="close__sub">friction becomes a patch request, an investigation, a real pull request, a release.</span>
      </a>
      <a class="close__card" href="/commons">
        <span class="close__k eyebrow">the public commons</span>
        <strong>Read the brain behind the board →</strong>
        <span class="close__sub">the glossary for every term here, plus the searchable record of goals, runs, and notes.</span>
      </a>
    </nav>
  </div>
</section>

<style>
  .container { max-width: 1160px; margin: 0 auto; padding-inline: clamp(18px, 4vw, 32px); }

  /* ── Cover ── */
  .cover { padding: clamp(48px, 8vw, 92px) 0 clamp(28px, 4vw, 44px); border-bottom: 1px solid var(--border-1); }
  .cover__title {
    font-size: clamp(40px, 7vw, 76px);
    font-weight: 400;
    line-height: 1.0;
    letter-spacing: -0.03em;
    margin: 14px 0 20px;
    max-width: 18ch;
  }
  .cover__lede { margin: 0; max-width: 64ch; }

  /* ── Shared section chrome ── */
  .ch { padding: clamp(44px, 7vw, 80px) 0; border-bottom: 1px solid var(--border-1); }
  .ch__inner { max-width: 760px; }
  .ch h2 {
    font-size: clamp(28px, 4.4vw, 46px);
    font-weight: 500;
    line-height: 1.06;
    letter-spacing: -0.02em;
    margin: 12px 0 18px;
  }
  .ch .eyebrow { display: block; }

  /* ── Board header ── */
  .board__head {
    display: flex; align-items: flex-end; justify-content: space-between;
    gap: 18px; flex-wrap: wrap; margin-bottom: 22px;
  }
  .board__head h2 { margin: 6px 0 0; }
  .board__meta { display: flex; align-items: center; gap: 12px; flex-wrap: wrap; }
  .board__stamp { display: inline-flex; align-items: center; gap: 8px; font-size: 11.5px; color: var(--fg-3); }
  .board__refresh {
    background: transparent; border: 1px solid var(--border-2); border-radius: var(--radius-pill);
    color: var(--live-700); cursor: pointer;
    font-family: var(--font-mono); font-size: 10px; letter-spacing: 0.08em; text-transform: uppercase;
    padding: 4px 12px;
    transition: border-color var(--dur-fast) var(--ease-standard), background var(--dur-fast) var(--ease-standard);
  }
  .board__refresh:hover:not(:disabled) { border-color: var(--live-600); background: var(--live-100); }
  .board__refresh:disabled { opacity: 0.6; cursor: default; }

  .board__err {
    margin: 0 0 18px; padding: 12px 14px;
    background: var(--ember-100); border: 1px solid rgba(182, 39, 68, 0.32);
    border-radius: var(--radius-md);
    font-size: 12px; line-height: 1.55; color: var(--ember-900); overflow-wrap: anywhere;
  }
  .board__empty {
    margin: 0; padding: 18px;
    background: var(--bg-inset); border: 1px dashed var(--border-2); border-radius: var(--radius-md);
    font-size: 13px; line-height: 1.6; color: var(--fg-2);
  }

  /* ── Domain filter ── */
  .board__filter { display: flex; flex-wrap: wrap; gap: 8px; margin: 0 0 18px; }
  .chip {
    background: transparent; border: 1px solid var(--border-2); border-radius: var(--radius-pill);
    color: var(--fg-3); cursor: pointer;
    font-family: var(--font-mono); font-size: 11px; letter-spacing: 0.02em;
    padding: 5px 13px;
    transition: border-color var(--dur-fast) var(--ease-standard), background var(--dur-fast) var(--ease-standard), color var(--dur-fast) var(--ease-standard);
  }
  .chip:hover { border-color: var(--live-600); color: var(--live-700); }
  .chip--on {
    border-color: var(--ink-text-900); background: var(--ink-text-900); color: var(--paper-50);
  }
  .chip--on:hover { border-color: var(--ink-text-900); color: var(--paper-50); }

  .linkish {
    background: none; border: none; padding: 0; cursor: pointer;
    color: var(--live-700); font: inherit; text-decoration: underline;
  }

  /* ── Board grid ── */
  .board {
    list-style: none; margin: 0; padding: 0;
    display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 16px;
  }
  @media (max-width: 900px) { .board { grid-template-columns: 1fr; } }
  .goal {
    display: grid; align-content: start; gap: 14px;
    padding: 22px;
    background: var(--bg-2);
    border: 1px solid var(--border-1);
    border-radius: var(--radius-lg);
    box-shadow: var(--shadow-sm);
    transition: border-color var(--dur-fast) var(--ease-standard), box-shadow var(--dur-fast) var(--ease-standard), opacity var(--dur-base) var(--ease-standard);
  }
  .goal:hover { border-color: var(--border-2); box-shadow: var(--shadow-md); }
  /* While still on baked data, dim very slightly so live feels like an upgrade. */
  .goal--baked { opacity: 0.92; }

  .goal__top { display: grid; gap: 8px; }
  .goal__name {
    font-family: var(--font-display);
    font-size: 21px; font-weight: 500; letter-spacing: -0.01em; line-height: 1.16;
    margin: 0; color: var(--fg-1);
  }
  .goal__link {
    color: inherit; text-decoration: none;
    transition: color var(--dur-fast) var(--ease-standard);
  }
  .goal__link:hover { color: var(--live-700); text-decoration: underline; text-underline-offset: 3px; }
  .goal__link:focus-visible { outline: 2px solid var(--live-600); outline-offset: 3px; border-radius: 2px; }
  .goal__desc {
    margin: 0; font-size: 14px; line-height: 1.55; color: var(--fg-2);
    /* clamp to ~3 lines */
    display: -webkit-box; -webkit-line-clamp: 3; line-clamp: 3; -webkit-box-orient: vertical;
    overflow: hidden; max-width: none;
  }

  .goal__tags {
    list-style: none; margin: 0; padding: 0;
    display: flex; flex-wrap: wrap; gap: 6px;
  }
  .goal__tags li {
    border: 1px solid var(--border-1); border-radius: var(--radius-sm);
    color: var(--fg-3); font-size: 10.5px; letter-spacing: 0.01em;
    padding: 3px 8px; background: var(--bg-1);
  }
  .goal__tags-more { color: var(--fg-4); border-style: dashed; }

  .goal__ladder {
    padding: 12px 0 2px;
    border-top: 1px solid var(--border-1);
  }
  .goal__ladder-label { display: block; margin-bottom: 8px; }

  .goal__foot { padding-top: 2px; }

  .board__foot {
    display: block; margin: 22px 0 0; font-size: 11.5px; color: var(--fg-3);
    line-height: 1.55; max-width: none;
  }
  .board__honest {
    display: block; margin: 6px 0 0; font-size: 11.5px; color: var(--fg-4);
    line-height: 1.55; max-width: 78ch;
  }

  /* ── Internal test goals (curated, not scrubbed) ── */
  .board__debris {
    margin: 22px 0 0; padding: 14px 16px;
    background: var(--bg-inset); border: 1px dashed var(--border-2); border-radius: var(--radius-md);
  }
  .board__debris summary {
    cursor: pointer; font-family: var(--font-mono); font-size: 11px;
    letter-spacing: 0.04em; color: var(--fg-3);
  }
  .board__debris summary:hover { color: var(--live-700); }
  .board__debris-note { margin: 10px 0 8px; font-size: 12px; line-height: 1.55; color: var(--fg-3); max-width: 70ch; }
  .board__debris-list { list-style: none; margin: 0; padding: 0; display: grid; gap: 8px; }
  .board__debris-list li {
    display: flex; align-items: baseline; gap: 10px; flex-wrap: wrap;
    font-size: 13px;
  }
  .board__debris-list a { color: var(--fg-2); text-decoration: none; }
  .board__debris-list a:hover { color: var(--live-700); text-decoration: underline; }

  /* ── Add a goal ── */
  .add__lede { font-size: 15px; line-height: 1.62; color: var(--fg-2); margin: 0 0 22px; max-width: 60ch; }
  .add__steps { list-style: none; margin: 0; padding: 0; display: grid; gap: 20px; }
  .add__steps > li { display: grid; grid-template-columns: 30px 1fr; gap: 14px; align-items: start; }
  .add__steps strong { display: block; font-family: var(--font-sans); font-size: 16px; font-weight: 600; color: var(--fg-1); margin-bottom: 4px; }
  .add__steps p { font-size: 14px; line-height: 1.55; color: var(--fg-2); margin: 0 0 10px; max-width: 60ch; }
  .add__n {
    font-family: var(--font-mono); font-size: 13px; color: var(--ember-700); font-weight: 500;
    width: 30px; height: 30px; border-radius: var(--radius-pill);
    border: 1px solid var(--border-2);
    display: inline-flex; align-items: center; justify-content: center;
  }
  .add__cta { font-family: var(--font-sans); font-size: 13.5px; font-weight: 600; color: var(--ember-700); width: fit-content; display: inline-block; }
  .add__prompt {
    display: flex; align-items: flex-start; justify-content: space-between; gap: 12px;
    width: 100%; text-align: left; margin: 2px 0 12px;
    padding: 13px 15px;
    background: var(--bg-inset); border: 1px solid var(--border-1); border-radius: var(--radius-md);
    cursor: pointer;
    transition: border-color var(--dur-fast) var(--ease-standard), background var(--dur-fast) var(--ease-standard);
  }
  .add__prompt:hover { border-color: var(--live-600); background: var(--live-100); }
  .add__prompt code { background: none; border: none; padding: 0; color: var(--fg-1); font-size: 13px; line-height: 1.5; white-space: normal; }
  .add__copy { flex: none; font-family: var(--font-mono); font-size: 9.5px; letter-spacing: 0.12em; text-transform: uppercase; color: var(--live-700); padding-top: 2px; }
  .add__note { font-size: 12.5px; color: var(--fg-3); margin: 0; max-width: 60ch; }

  /* ── Close ── */
  .ch--close { border-bottom: none; padding-bottom: clamp(64px, 9vw, 110px); }
  .close__cards { display: grid; grid-template-columns: repeat(2, 1fr); gap: 16px; margin-top: 22px; }
  @media (max-width: 760px) { .close__cards { grid-template-columns: 1fr; } }
  .close__card {
    display: grid; gap: 6px;
    padding: 24px 26px;
    background: var(--bg-2);
    border: 1px solid var(--border-2);
    border-radius: var(--radius-lg);
    text-decoration: none; color: inherit;
    transition: border-color var(--dur-fast) var(--ease-standard), box-shadow var(--dur-fast) var(--ease-standard);
  }
  .close__card:hover { border-color: var(--ink-text-900); box-shadow: var(--shadow-md); text-decoration: none; }
  .close__k { display: block; }
  .close__card strong { font-family: var(--font-display); font-size: clamp(20px, 2.6vw, 26px); font-weight: 500; letter-spacing: -0.015em; line-height: 1.14; color: var(--fg-1); }
  .close__sub { font-size: 13.5px; color: var(--fg-2); }
</style>
