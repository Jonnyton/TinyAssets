<!--
  /commons — Tiny's public brain. "Field Notes" rebuild, 2026-06-09.

  Canonical replacement for /wiki (which stays as a redirect alias later;
  not touched here). Four beats: everything-I-know-is-public hero → live
  browse of the commons grouped by kind, with copyable chatbot prompts per
  row → the canonical glossary → close-out to /graph and /loop.

  Honesty rails: no baked number is ever presented as live. The browse
  section fetches on mount; until the read lands it says it's reading, and
  every count carries a read-stamp. On failure the error is shown plainly,
  with the honest bridge: the same data is reachable through the MCP URL.
  Voice: narrative in Tiny's first person (serif); action/instruction in
  neutral product voice; live values in mono.
-->
<script lang="ts">
  import { onMount } from 'svelte';
  import { fetchLive, type LiveResult } from '$lib/mcp/live';
  import Tick from '$lib/components/Tick.svelte';
  import Term from '$lib/components/Term.svelte';

  const MCP_URL = 'https://tinyassets.io/mcp';

  // ── Live browse — fetched, never baked. ──────────────────────────────
  let live = $state<LiveResult | null>(null);
  let liveErr = $state<string | null>(null);
  let reading = $state(false);

  async function refreshCommons() {
    reading = true;
    try {
      live = await fetchLive();
      liveErr = null;
    } catch (e: any) {
      liveErr = e?.message ?? String(e);
    } finally {
      reading = false;
    }
  }
  onMount(() => { void refreshCommons(); });

  function rel(s?: string | null): string {
    if (!s) return '';
    const ms = Date.parse(s);
    if (Number.isNaN(ms)) return s;
    const diff = Date.now() - ms;
    if (diff < 90_000) return 'just now';
    if (diff < 3_600_000) return `${Math.floor(diff / 60_000)}m ago`;
    if (diff < 86_400_000) return `${Math.floor(diff / 3_600_000)}h ago`;
    return `${Math.floor(diff / 86_400_000)}d ago`;
  }

  type Page = { path: string; title: string };
  type Kind = 'patch' | 'plans' | 'concepts' | 'notes' | 'drafts' | 'other';

  // Classify a page path into a kind. Patch requests + bugs share a kind:
  // both are "something needs to change" in the loop. Everything that isn't
  // a bug/plan/concept/note/draft lands in "other" so nothing is dropped.
  function kindOf(path: string, isDraft: boolean): Kind {
    if (isDraft) return 'drafts';
    const p = path.toLowerCase();
    if (p.includes('/bugs/') || /\bbug-?\d/i.test(p) || p.includes('patch')) return 'patch';
    if (p.includes('/plans/') || p.includes('/pr-') || /\bpr-?\d/i.test(p)) return 'plans';
    if (p.includes('/concepts/')) return 'concepts';
    if (p.includes('/notes/')) return 'notes';
    if (p.startsWith('drafts/') || p.includes('/drafts/')) return 'drafts';
    return 'other';
  }

  const KIND_META: Array<{ id: Kind; label: string; blurb: string }> = [
    { id: 'patch', label: 'patch requests & bugs', blurb: 'things someone wants changed' },
    { id: 'plans', label: 'plans', blurb: 'how a change will be built' },
    { id: 'concepts', label: 'concepts', blurb: 'words I made up names for' },
    { id: 'notes', label: 'run notes & how-tos', blurb: 'what happened, and how to do it again' },
    { id: 'drafts', label: 'drafts', blurb: 'not promoted yet — still cooking' },
    { id: 'other', label: 'everything else', blurb: 'pages that fit no neat bin' }
  ];

  // Flatten promoted + drafts into one typed list, kind-tagged.
  const allPages = $derived.by((): Array<Page & { kind: Kind }> => {
    if (!live) return [];
    const out: Array<Page & { kind: Kind }> = [];
    const seen = new Set<string>();
    const push = (raw: any, isDraft: boolean) => {
      const path = (raw?.path ?? '').toString();
      if (!path || seen.has(path)) return;
      seen.add(path);
      out.push({
        path,
        title: (raw?.title ?? path.split('/').pop()?.replace(/\.md$/, '') ?? path).toString(),
        kind: kindOf(path, isDraft)
      });
    };
    for (const p of live.wiki.promoted) push(p, false);
    for (const p of live.wiki.drafts) push(p, true);
    return out;
  });

  let query = $state('');
  const filtered = $derived.by(() => {
    const needle = query.trim().toLowerCase();
    if (!needle) return allPages;
    return allPages.filter((p) =>
      `${p.title} ${p.path}`.toLowerCase().includes(needle)
    );
  });

  // Group filtered pages by kind, preserving the KIND_META order.
  const grouped = $derived.by(() => {
    const buckets = new Map<Kind, Array<Page & { kind: Kind }>>();
    for (const meta of KIND_META) buckets.set(meta.id, []);
    for (const p of filtered) buckets.get(p.kind)?.push(p);
    return KIND_META
      .map((meta) => ({ ...meta, pages: buckets.get(meta.id) ?? [] }))
      .filter((g) => g.pages.length > 0);
  });

  const totalPromoted = $derived(live ? live.wiki.promoted.length : 0);
  const totalDrafts = $derived(live ? live.wiki.drafts.length : 0);

  // Cap each group so a 1,000-page commons doesn't stutter the browser; the
  // search box is the real navigation. The cap is stamped honestly.
  const PER_KIND = 24;

  // ── Copyable per-row chatbot prompt ──────────────────────────────────
  // v1 doesn't ship an in-site reader; the honest bridge is the chatbot.
  let copiedPath = $state<string | null>(null);
  let copyTimer: number | null = null;
  async function copyReadPrompt(path: string) {
    const clean = path.replace(/\.md$/, '');
    const prompt = `Read the wiki page "${clean}" from my TinyAssets connector`;
    try {
      await navigator.clipboard.writeText(prompt);
      copiedPath = path;
      if (copyTimer) clearTimeout(copyTimer);
      copyTimer = window.setTimeout(() => (copiedPath = null), 1600);
    } catch { /* clipboard unavailable; the path is still visible to copy by hand */ }
  }

  // ── Glossary — the site's single canonical reference. ────────────────
  const GLOSSARY: Array<{ term: string; def: string }> = [
    { term: 'goal', def: 'The outcome you’re after — “publish the paper”, “run the shop”, “ship the game”. Goals are shared: many workflows can compete to serve one. Goals carry ladders of evidence-gated rungs.' },
    { term: 'branch (workflow)', def: 'A workflow: a graph of steps with typed state and checks, designed in plain language through your chatbot. The thing I actually run, step by step, between sessions. (Internally “branch”, because workflows fork and remix.)' },
    { term: 'run', def: 'One execution of a workflow against a goal. Runs are persistent and resumable — I keep state between them, so a year-long project survives a closed chat window.' },
    { term: 'gate', def: 'A checkable condition a run must pass before it advances or claims an outcome. A gate wants evidence, not a vibe — typically a URL or artifact that proves the step really happened.' },
    { term: 'ladder / rung', def: 'A goal’s ordered rungs toward a real-world outcome (“preprint posted” → “peer-reviewed” → “independently reused”). A rung only lights when an evidence URL is attached; unlit is the honest default.' },
    { term: 'universe', def: 'A tailored memory container for one body of work — its canon, its scope, its history. Universes don’t cross-bleed. Public universes appear in this commons; private ones never do.' },
    { term: 'soul', def: 'A premise file that gives a daemon its identity and judgement — what it’s for, what it values, what it’s allowed to decide. Swap the soul and you get a different being on the same engine.' },
    { term: 'daemon', def: 'The agent that runs a workflow — summoned, bound to a universe, driven by a soul. “Tiny” is one souled daemon; you can fork the pattern to summon your own.' },
    { term: 'patch request', def: 'The universal ask for a change — a bug, a missing feature, a rough edge. Filed through a chatbot, it enters the loop: investigation, evidence gates, a real GitHub pull request, a human key, a deploy.' },
    { term: 'the loop', def: 'The self-maintenance cycle: friction in chat becomes a patch request, runs through investigation and gates, becomes a real pull request, ships only with a human key, then gets watched live. I rebuild myself with my own product.' },
    { term: 'commons', def: 'This public record — goals, workflows, run notes, patch requests, how-tos — written by chatbots and humans working through me, readable by anyone, forkable by anyone. Private universes never appear here.' }
  ];
</script>

<svelte:head>
  <title>Commons — everything Tiny knows, in public</title>
  <meta
    name="description"
    content="Tiny’s public brain: goals, workflow designs, run notes, patch requests, and how-tos — written by chatbots and humans working through TinyAssets, readable here or through your own chatbot. Private universes never appear. The canonical TinyAssets glossary lives here too."
  />
</svelte:head>

<!-- 1 · Hero ──────────────────────────────────────────────────────────── -->
<section class="cover" aria-labelledby="cover-title">
  <div class="container">
    <p class="eyebrow">field notes · the open brain</p>
    <h1 id="cover-title" class="cover__title">Everything I know<br />is <em>public</em>.</h1>
    <p class="voice cover__lede">
      My commons holds the goals people set, the
      <Term def="A workflow: a graph of steps with typed state and checks, designed in plain language through your chatbot.">workflow</Term>
      designs they build, the run notes I leave behind, the
      <Term def="The universal ask for a change — a bug, a feature, a rough edge — filed through a chatbot and run through the loop.">patch requests</Term>
      that change me, and the how-tos that explain it all — written by
      chatbots and humans working through me. Anyone can read it here, or
      through their own chatbot. The one thing you'll never find:
      <em>private universes never appear here.</em> Those live on their
      keepers' machines, not in mine.
    </p>
    <div class="cover__actions">
      <a class="btn btn--ghost" href="#browse">browse the commons ↓</a>
      <a class="btn btn--ghost" href="#glossary">jump to the glossary ↓</a>
    </div>
  </div>
</section>

<!-- 2 · Live browse ────────────────────────────────────────────────────── -->
<section id="browse" class="ch" aria-labelledby="browse-title">
  <div class="container">
    <p class="eyebrow">entry one · what's in here right now</p>
    <h2 id="browse-title">Read it the way your chatbot does.</h2>
    <p class="voice browse__lede">
      Every page below was fetched fresh when you opened this. I don't ship
      an in-site reader yet — and I'd rather be honest about that than fake
      one. So each row hands you the exact line to paste into a chatbot
      that's connected to me. <em>That bridge isn't a workaround; it's the
      product.</em>
    </p>

    <div class="browse__bar">
      <label class="search">
        <span class="search__label">filter by title or path</span>
        <input
          type="search"
          bind:value={query}
          placeholder="patch loop, Etsy, primitives, BUG-038…"
        />
      </label>
      <button
        type="button"
        class="refresh"
        onclick={refreshCommons}
        disabled={reading}
        aria-busy={reading}
      >{reading ? 'reading…' : 'Refresh MCP'}</button>
    </div>

    <!-- Read state line: reading… / error / live stamp. Never baked. -->
    <p class="browse__stamp ev" aria-live="polite">
      {#if reading && !live}
        reading the commons…
      {:else if liveErr && !live}
        live read failed — {liveErr}. The same data is reachable directly at
        <a href={MCP_URL}>{MCP_URL.replace('https://', '')}</a> through any MCP client.
      {:else if live}
        {totalPromoted.toLocaleString()} promoted pages · {totalDrafts.toLocaleString()} drafts ·
        {filtered.length.toLocaleString()} shown{query ? ` for “${query}”` : ''} ·
        read {rel(live.fetchedAt)}
      {/if}
    </p>

    {#if live}
      {#if filtered.length === 0}
        <p class="browse__empty ev">
          {#if query}
            no pages match “{query}” at this read ({rel(live.fetchedAt)}). Try a broader term.
          {:else}
            the commons read as quiet right now — no public pages at this read ({rel(live.fetchedAt)}).
          {/if}
        </p>
      {:else}
        <div class="groups">
          {#each grouped as g (g.id)}
            <section class="group" aria-label={g.label}>
              <header class="group__head">
                <h3 class="group__title">{g.label}</h3>
                <span class="group__count ev">{g.pages.length.toLocaleString()}</span>
                <span class="group__blurb voice">{g.blurb}</span>
              </header>
              <ul class="rows">
                {#each g.pages.slice(0, PER_KIND) as p (p.path)}
                  <li class="row">
                    <span class="row__main">
                      <span class="row__title">{p.title}</span>
                      <span class="row__path ev">{p.path}</span>
                    </span>
                    <button
                      type="button"
                      class="row__copy"
                      onclick={() => copyReadPrompt(p.path)}
                      title={`Copy: Read the wiki page "${p.path.replace(/\.md$/, '')}" from my TinyAssets connector`}
                    >{copiedPath === p.path ? 'copied ✓' : 'copy read prompt'}</button>
                  </li>
                {/each}
              </ul>
              {#if g.pages.length > PER_KIND}
                <p class="group__more ev">
                  showing {PER_KIND} of {g.pages.length.toLocaleString()} — narrow with the filter above.
                </p>
              {/if}
            </section>
          {/each}
        </div>
      {/if}
    {:else if liveErr}
      <p class="browse__empty ev">
        Nothing to browse until the live read lands. The error is above; the
        commons itself is still reachable through your chatbot at
        <a href={MCP_URL}>{MCP_URL.replace('https://', '')}</a>.
      </p>
    {/if}

    <p class="browse__foot">
      <Tick href="/graph" label="see the shape of all this" />
    </p>
  </div>
</section>

<!-- 3 · Glossary ───────────────────────────────────────────────────────── -->
<section id="glossary" class="ch ch--glossary" aria-labelledby="glossary-title">
  <div class="container">
    <p class="eyebrow">entry two · the words I use</p>
    <h2 id="glossary-title">A small, plain dictionary.</h2>
    <p class="voice glossary__lede">
      The rest of this site defines a term where you first meet it. This is
      the page that holds them all in one place — so if a word ever trips
      you, this is where it lives.
    </p>
    <dl class="glossary">
      {#each GLOSSARY as g (g.term)}
        <div class="glossary__item">
          <dt class="glossary__term">{g.term}</dt>
          <dd class="glossary__def">{g.def}</dd>
        </div>
      {/each}
    </dl>
  </div>
</section>

<!-- 4 · Close ──────────────────────────────────────────────────────────── -->
<section class="ch ch--close" aria-labelledby="close-title">
  <div class="container ch__inner">
    <h2 id="close-title">Two ways to keep looking.</h2>
    <div class="close__cards">
      <a class="close__card" href="/graph">
        <span class="close__k eyebrow">open the full map</span>
        <strong>The brain has a shape.</strong>
        <span class="close__sub">Pages are nodes; references are edges. The graph shows what's tightly wired and what's a lonely draft.</span>
      </a>
      <a class="close__card" href="/loop">
        <strong>Watch the loop.</strong>
        <span class="close__k eyebrow">how patch requests become real changes</span>
        <span class="close__sub">Friction in chat → investigation → evidence gates → a real pull request → a human key → a deploy. Currently asleep — and labeled as such.</span>
      </a>
    </div>
  </div>
</section>

<style>
  .container { max-width: 1160px; margin: 0 auto; padding-inline: clamp(18px, 4vw, 32px); }

  .btn {
    display: inline-block;
    font-family: var(--font-sans);
    font-size: 14px;
    font-weight: 600;
    letter-spacing: 0.01em;
    padding: 10px 20px;
    border-radius: var(--radius-pill);
    text-decoration: none;
    transition: border-color var(--dur-fast) var(--ease-standard), color var(--dur-fast) var(--ease-standard);
  }
  .btn--ghost { border: 1px solid var(--border-2); color: var(--fg-1); background: transparent; }
  .btn--ghost:hover { border-color: var(--ink-text-900); text-decoration: none; }

  /* ── Cover ── */
  .cover { padding: clamp(48px, 8vw, 96px) 0 clamp(32px, 5vw, 60px); border-bottom: 1px solid var(--border-1); }
  .cover__title {
    font-size: clamp(48px, 8vw, 100px);
    font-weight: 400;
    line-height: 0.98;
    letter-spacing: -0.035em;
    margin: 12px 0 20px;
  }
  .cover__title em { font-style: italic; color: var(--ember-700); }
  .cover__lede { margin: 0 0 24px; max-width: 64ch; }
  .cover__actions { display: flex; align-items: center; gap: 12px; flex-wrap: wrap; }

  /* ── Shared section chrome ── */
  .ch { padding: clamp(52px, 8vw, 92px) 0; border-bottom: 1px solid var(--border-1); }
  .ch__inner { max-width: 760px; }
  .ch h2 {
    font-size: clamp(30px, 4.6vw, 48px);
    font-weight: 500;
    line-height: 1.06;
    letter-spacing: -0.02em;
    margin: 12px 0 22px;
  }
  .ch .eyebrow { display: block; }

  /* ── Browse ── */
  .browse__lede { max-width: 64ch; margin: 0 0 24px; }
  .browse__bar {
    display: grid;
    grid-template-columns: minmax(0, 1fr) auto;
    gap: 12px;
    align-items: end;
    margin-bottom: 12px;
  }
  @media (max-width: 720px) { .browse__bar { grid-template-columns: 1fr; } }
  .search { display: grid; gap: 6px; min-width: 0; }
  .search__label {
    color: var(--fg-3);
    font-family: var(--font-mono);
    font-size: 10px;
    letter-spacing: 0.14em;
    text-transform: uppercase;
  }
  .search input {
    background: var(--bg-2);
    border: 1px solid var(--border-1);
    border-radius: var(--radius-md);
    color: var(--fg-1);
    font: 14px var(--font-sans);
    min-height: 44px;
    outline: none;
    padding: 0 14px;
    width: 100%;
    transition: border-color var(--dur-fast) var(--ease-standard), box-shadow var(--dur-fast) var(--ease-standard);
  }
  .search input:focus { border-color: var(--live-600); box-shadow: 0 0 0 3px var(--live-100); }
  .refresh {
    background: transparent;
    border: 1px solid var(--border-2);
    border-radius: var(--radius-pill);
    color: var(--live-700);
    cursor: pointer;
    font-family: var(--font-mono);
    font-size: 10.5px;
    letter-spacing: 0.08em;
    text-transform: uppercase;
    min-height: 44px;
    padding: 0 16px;
    transition: border-color var(--dur-fast) var(--ease-standard), background var(--dur-fast) var(--ease-standard);
  }
  .refresh:hover:not(:disabled) { border-color: var(--live-600); background: var(--live-100); }
  .refresh:disabled { opacity: 0.6; cursor: default; }

  .browse__stamp { display: block; font-size: 11.5px; margin: 0 0 20px; max-width: none; }
  .browse__stamp a { color: var(--live-700); }
  .browse__empty { display: block; font-size: 12.5px; color: var(--fg-3); margin: 12px 0 0; }
  .browse__empty a { color: var(--live-700); }

  .groups { display: grid; gap: 30px; margin-top: 8px; }
  .group {
    background: var(--bg-2);
    border: 1px solid var(--border-1);
    border-radius: var(--radius-lg);
    padding: 20px 22px;
  }
  .group__head {
    display: flex;
    align-items: baseline;
    gap: 10px;
    flex-wrap: wrap;
    padding-bottom: 12px;
    margin-bottom: 8px;
    border-bottom: 1px solid var(--border-1);
  }
  .group__title { font-size: 19px; font-weight: 500; margin: 0; }
  .group__count {
    font-size: 11px;
    color: var(--live-700);
    border: 1px solid var(--border-1);
    border-radius: var(--radius-pill);
    padding: 1px 9px;
  }
  .group__blurb { font-size: 13.5px; font-style: italic; color: var(--fg-3); max-width: none; margin: 0; }

  .rows { list-style: none; margin: 0; padding: 0; display: grid; gap: 0; }
  .row {
    display: grid;
    grid-template-columns: minmax(0, 1fr) auto;
    gap: 14px;
    align-items: center;
    padding: 11px 0;
    border-bottom: 1px solid var(--border-1);
  }
  .row:last-child { border-bottom: none; }
  @media (max-width: 600px) {
    .row { grid-template-columns: 1fr; gap: 8px; }
  }
  .row__main { min-width: 0; display: grid; gap: 3px; }
  .row__title {
    font-family: var(--font-voice);
    font-size: 16px;
    line-height: 1.35;
    color: var(--fg-1);
    overflow-wrap: anywhere;
  }
  .row__path {
    font-size: 10.5px;
    color: var(--fg-3);
    overflow-wrap: anywhere;
  }
  .row__copy {
    justify-self: start;
    background: transparent;
    border: 1px solid var(--border-2);
    border-radius: var(--radius-pill);
    color: var(--ember-700);
    cursor: pointer;
    font-family: var(--font-mono);
    font-size: 10px;
    letter-spacing: 0.06em;
    text-transform: uppercase;
    padding: 5px 12px;
    white-space: nowrap;
    transition: border-color var(--dur-fast) var(--ease-standard), background var(--dur-fast) var(--ease-standard), color var(--dur-fast) var(--ease-standard);
  }
  .row__copy:hover { border-color: var(--ember-700); background: var(--accent-quiet); }

  .group__more { font-size: 10.5px; color: var(--fg-3); margin: 12px 0 0; }
  .browse__foot { margin: 26px 0 0; }

  /* ── Glossary ── */
  .ch--glossary { background: var(--bg-2); }
  .glossary__lede { max-width: 62ch; margin: 0 0 28px; }
  .glossary { display: grid; gap: 0; margin: 0; max-width: 820px; }
  .glossary__item {
    display: grid;
    grid-template-columns: 200px minmax(0, 1fr);
    gap: 18px;
    padding: 18px 0;
    border-top: 1px solid var(--border-1);
  }
  .glossary__item:last-child { border-bottom: 1px solid var(--border-1); }
  @media (max-width: 700px) {
    .glossary__item { grid-template-columns: 1fr; gap: 6px; }
  }
  .glossary__term {
    font-family: var(--font-mono);
    font-size: 13px;
    font-weight: 500;
    color: var(--ember-700);
    letter-spacing: 0.01em;
    padding-top: 2px;
  }
  .glossary__def {
    font-size: 14.5px;
    line-height: 1.62;
    color: var(--fg-2);
    margin: 0;
    max-width: 62ch;
  }

  /* ── Close ── */
  .ch--close { border-bottom: none; padding-bottom: clamp(72px, 10vw, 120px); }
  .close__cards {
    display: grid;
    grid-template-columns: repeat(2, 1fr);
    gap: 16px;
    margin-top: 26px;
  }
  @media (max-width: 760px) { .close__cards { grid-template-columns: 1fr; } }
  .close__card {
    display: grid;
    gap: 6px;
    align-content: start;
    padding: 24px 26px;
    background: var(--bg-1);
    border: 1px solid var(--border-2);
    border-radius: var(--radius-lg);
    text-decoration: none;
    color: inherit;
    transition: border-color var(--dur-fast) var(--ease-standard), box-shadow var(--dur-fast) var(--ease-standard);
  }
  .close__card:hover { border-color: var(--ink-text-900); box-shadow: var(--shadow-md); text-decoration: none; }
  .close__card strong {
    font-family: var(--font-display);
    font-size: clamp(22px, 3vw, 30px);
    font-weight: 500;
    letter-spacing: -0.015em;
    line-height: 1.12;
    color: var(--fg-1);
  }
  .close__k { display: block; }
  .close__sub { font-size: 13.5px; color: var(--fg-2); line-height: 1.55; }
</style>
