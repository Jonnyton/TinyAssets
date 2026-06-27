<!--
  /host — "Field Notes" rebuild, 2026-06-10.

  Job: tell the honest hosting story. You DON'T have to host anything to use
  Tiny — the public engine at tinyassets.io runs 24/7. Hosting is for when you
  want your OWN private universes on your OWN machine, your keys, your data.

  Crawl findings fixed:
   - old hosted-cloud card was half the H1 with no path forward (no signup,
     no waitlist, no pricing) → now one honest sentence + real request paths.
   - stale Apr-30 stamps → all live values carry read-stamps, baked first
     paint is stamped "snapshot 10 Jun 2026" and upgraded on mount.
   - "0 words / idle" universes undercutting the pitch → the live section is
     framed as "the public engine right now", honest about quiet universes,
     and is NOT the hosting pitch (hosting is your own private universes).

  Honesty rails: no baked number presented as live; public-commons only;
  every command verified against the repo README/pyproject; no dead-end CTA.
-->
<script lang="ts">
  import { onMount } from 'svelte';
  import { fetchLive, type LiveResult } from '$lib/mcp/live';
  import { initialMcpSnapshot } from '$lib/live/project';
  import { fmtRel } from '$lib/fmt';
  import Tick from '$lib/components/Tick.svelte';
  import Term from '$lib/components/Term.svelte';

  const GH_REPO = 'https://github.com/Jonnyton/Workflow';
  const GH_ISSUES = 'https://github.com/Jonnyton/Workflow/issues';
  const README_QUICKSTART = 'https://github.com/Jonnyton/Workflow#quick-start-for-contributors';

  // ── Baked first paint, visibly stamped, upgraded by a live read on mount. ──
  const SNAPSHOT_DATE = '10 Jun 2026';
  const bakedUniverses = (initialMcpSnapshot.universes ?? []) as any[];

  let live = $state<LiveResult | null>(null);
  let liveErr = $state<string | null>(null);
  let reading = $state(false);
  async function refreshUniverses() {
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
  onMount(() => { void refreshUniverses(); });

  // Public-commons only: drop private + any SUPERSEDED/RETRACTED/smoke rows.
  function isPublicUniverse(u: any): boolean {
    if ((u?.visibility ?? 'public') === 'private') return false;
    return !/SUPERSEDED|RETRACTED|smoke/i.test(String(u?.id ?? ''));
  }

  // Shape a live universe (live.ts hands us raw `universe action=list` rows)
  // or a baked one (already normalised) into one display shape.
  type Row = { id: string; phase: string; words: number; lastAt: string | null };
  function toRow(u: any, fromLive: boolean): Row {
    return {
      id: String(u?.id ?? 'unknown'),
      phase: String((fromLive ? (u?.phase_human ?? u?.phase) : u?.phase) ?? 'unknown'),
      words: Number(u?.word_count ?? 0),
      lastAt: u?.last_activity_at ?? null
    };
  }

  const rows = $derived<Row[]>(
    (live
      ? (live.universes ?? []).filter(isPublicUniverse).map((u) => toRow(u, true))
      : bakedUniverses.filter(isPublicUniverse).map((u) => toRow(u, false))
    ).slice(0, 12)
  );

  // Viewer-local relative stamps go through the shared fmt module; only the
  // "never moved" empty state is page-specific.
  function rel(s?: string | null): string {
    if (!s) return 'no recorded activity';
    return fmtRel(s);
  }

  // Humanize raw daemon status words into plain language for visitors who
  // don't know the engine's internals. The raw word is kept alongside as a
  // mono detail so the technical truth is never hidden. Unknown statuses fall
  // through to the raw word rendered in mono.
  const PHASE_WORDS: Record<string, string> = {
    'dormant-starved': 'resting — waiting for new work',
    'idle-no-premise': 'empty shell — no premise yet',
    'universe_cycle_wrapper': 'internal plumbing'
  };
  type PhaseLabel = { human: string | null; raw: string };
  function phaseLabel(phase: string): PhaseLabel {
    const raw = (phase ?? '').trim() || 'unknown';
    const human = PHASE_WORDS[raw] ?? null;
    return { human, raw };
  }

  function quiet(r: Row): boolean {
    if (/idle|paused|asleep|done|complete/i.test(r.phase)) return true;
    if (!r.lastAt) return true;
    return Date.now() - Date.parse(r.lastAt) > 24 * 60 * 60 * 1000;
  }

  // ── The real local path, verified against the repo. ──
  // README quick-start: clone → venv → pip install -e .[dev]. Entry points
  // (pyproject [project.scripts] / [project.gui-scripts]): `workflow` is the
  // tray GUI launcher, `workflow-mcp` runs the MCP server standalone. There is
  // no published installer in releases, so the tray ships from source today.
  let os = $state<'windows' | 'mac' | 'linux'>('windows');
  const venvLine = $derived(
    os === 'windows'
      ? 'python -m venv .venv && .venv\\Scripts\\activate'
      : 'python -m venv .venv && source .venv/bin/activate'
  );
  const quickstart = $derived(
    `git clone ${GH_REPO}.git\n` +
    `cd Workflow\n` +
    `${venvLine}\n` +
    `pip install -e .[dev]\n` +
    `\n` +
    `# launch the tray (summons + manages your daemons)\n` +
    `workflow\n` +
    `\n` +
    `# or run just the MCP server your chatbot connects to\n` +
    `workflow-mcp`
  );

  let copied = $state(false);
  let copyTimer: number | null = null;
  async function copyQuickstart() {
    try {
      await navigator.clipboard.writeText(quickstart);
      copied = true;
      if (copyTimer) clearTimeout(copyTimer);
      copyTimer = window.setTimeout(() => (copied = false), 1800);
    } catch { /* clipboard unavailable; the block is visible anyway */ }
  }
</script>

<svelte:head>
  <title>Host — run Tiny on your own machine</title>
  <meta
    name="description"
    content="You don't have to host anything to use Tiny — the public engine runs 24/7. Hosting is for your own private universes on your own machine: your keys, your data, the same loop pattern pointed at your projects."
  />
</svelte:head>

<!-- 1 · Hero — you don't have to host anything ──────────────────────────── -->
<section class="cover" aria-labelledby="cover-title">
  <div class="container ch__inner">
    <p class="eyebrow">field notes · on hosting me yourself</p>
    <h1 id="cover-title" class="cover__title">You don't have to host anything<br />to use me.</h1>
    <p class="voice cover__lede">
      The public engine at <code>tinyassets.io</code> is already running
      around the clock — connect your chatbot and put me to work without
      installing a thing. <em>Hosting is for when you want your own.</em>
      Your own private
      <Term def="A universe: a tailored container for one body of work — its canon, goals, workflows, and run history. The public ones are listed below; private ones live on your machine.">universes</Term>
      on your own machine, your own keys and data, the same loop pattern
      pointed at your projects.
    </p>
    <div class="cover__actions">
      <a class="btn btn--primary" href="/start">Just use the public engine →</a>
      <a class="btn btn--ghost" href="#run-it">Run it yourself ↓</a>
    </div>
    <p class="cover__naming">
      <strong>TinyAssets</strong> is the open-source platform.
      <strong>Tiny</strong> is the public intelligence running on it. Same code
      whether it runs on the public box or on yours.
    </p>
  </div>
</section>

<!-- 2 · What hosting gets you ───────────────────────────────────────────── -->
<section class="ch" aria-labelledby="gets-title">
  <div class="container">
    <p class="eyebrow">entry two · what hosting gets you</p>
    <h2 id="gets-title">Three things the public engine can't give you.</h2>
    <ul class="gets">
      <li class="get">
        <span class="get__n">01</span>
        <h3 class="get__h">Private universes</h3>
        <p class="get__p">
          Work that never touches the public engine. The commons here is a
          public, forkable record by design — anything you'd rather keep off
          it (a manuscript, client work, a private dataset) lives only on the
          machine you run, available only when you're online.
        </p>
      </li>
      <li class="get">
        <span class="get__n">02</span>
        <h3 class="get__h">Your own capacity and models</h3>
        <p class="get__p">
          Your daemon, your hardware, your routing. Point it at a local model
          through <Term def="Ollama: a tool for running open LLMs locally on your own machine, no cloud key required.">Ollama</Term>
          or wire in your own provider API keys. The engine reads the routing
          from your environment — it doesn't phone home for it.
        </p>
      </li>
      <li class="get">
        <span class="get__n">03</span>
        <h3 class="get__h">The same loop, on your projects</h3>
        <p class="get__p">
          The self-patching
          <Term def="The loop: friction becomes a patch request, runs through investigation and evidence gates, becomes a real change, and ships. Tiny uses it on himself; you can point it at your own repo.">loop</Term>
          pattern isn't special-cased to me — it's a workflow bound to a goal.
          Fork the pattern, swap the goal for your project, and your instance
          maintains itself the way I maintain mine.
        </p>
        <a class="get__cta" href="/build">how the pattern forks →</a>
      </li>
    </ul>
  </div>
</section>

<!-- 3 · Run it yourself today ────────────────────────────────────────────── -->
<section id="run-it" class="ch ch--run" aria-labelledby="run-title">
  <div class="container ch__inner ch__inner--wide">
    <p class="eyebrow">entry three · run it yourself today</p>
    <h2 id="run-title">It's source-first, and that path is real.</h2>
    <p class="run__lede">
      Python 3.11+. Clone, install in editable mode, and you have a local
      daemon to summon. These commands are the repo's own quick-start — the
      <code>workflow</code> tray and <code>workflow-mcp</code> server are the
      documented entry points, not invented for this page.
    </p>

    <div class="os-tabs" role="tablist" aria-label="Operating system">
      {#each [['windows', 'Windows'], ['mac', 'macOS'], ['linux', 'Linux']] as [key, label]}
        <button
          class="os-tab"
          class:os-tab--active={os === key}
          type="button"
          role="tab"
          aria-selected={os === key}
          onclick={() => (os = key as typeof os)}
        >{label}</button>
      {/each}
    </div>

    <div class="run__block">
      <pre class="run__pre"><code>{quickstart}</code></pre>
      <button class="run__copy" type="button" onclick={copyQuickstart}>
        {copied ? 'copied ✓' : 'copy'}
      </button>
    </div>
    <p class="run__tickline">
      <Tick href={README_QUICKSTART} label="repo README · quick start" external />
    </p>

    <div class="run__notes">
      <div class="run__note">
        <strong>The Windows tray app ships from source today.</strong>
        There's no packaged installer in releases yet, so the honest path is
        the clone above — running <code>workflow</code> opens the same tray an
        installer eventually would. macOS and Linux support is in progress
        (the platform code is cross-platform; the tray is Windows-first).
        <a href={GH_REPO} target="_blank" rel="noreferrer">Read the source on GitHub ↗</a>
      </div>
      <div class="run__note">
        <strong>Local models and keys are yours to set.</strong>
        Set <code>OLLAMA_HOST</code> for a local model, or your provider API
        keys in the environment, and the daemon routes through them. Nothing
        about hosting requires a cloud account or a payment method.
      </div>
    </div>
  </div>
</section>

<!-- 4 · A hosted cloud option ────────────────────────────────────────────── -->
<section class="ch ch--cloud" aria-labelledby="cloud-title">
  <div class="container ch__inner">
    <p class="eyebrow">entry four · a hosted cloud option</p>
    <h2 id="cloud-title">A "we run it for you" option isn't offered yet.</h2>
    <p class="voice cloud__lede">
      Honest version: there's no hosted-cloud signup, waitlist, or pricing
      today, and I won't fake one. <em>If you want it, the useful thing is to
      say so</em> — a request through chat or a GitHub issue is a real signal
      that shapes what gets built, and it enters the same patch loop everything
      else does.
    </p>
    <div class="cloud__paths">
      <a class="cloud__path" href="/start">
        <span class="cloud__k eyebrow">ask through chat</span>
        <strong>Tell me you'd host in the cloud →</strong>
        <span class="cloud__sub">connect your chatbot and file it as a patch request.</span>
      </a>
      <a class="cloud__path" href={GH_ISSUES} target="_blank" rel="noreferrer">
        <span class="cloud__k eyebrow">open a GitHub issue</span>
        <strong>Request hosted cloud on GitHub ↗</strong>
        <span class="cloud__sub">public, trackable, tied to the engine's own backlog.</span>
      </a>
    </div>
  </div>
</section>

<!-- 5 · What's running on the public engine right now ────────────────────── -->
<section class="ch ch--rooms" aria-labelledby="rooms-title">
  <div class="container">
    <p class="eyebrow">entry five · the public engine right now</p>
    <h2 id="rooms-title">These are running on the box you'd be opting out of.</h2>
    <p class="voice rooms__lede">
      Your hosted universes would be private and wouldn't appear anywhere like
      this. But it's worth seeing what the shared engine carries — public
      universes, read live when you opened this page. Some are quiet; I'll say
      so rather than dress it up.
    </p>
    <p class="rooms__quietnote ev">
      Quiet is normal: universes sleep between runs. The word count is the work
      that stayed.
    </p>

    <div class="rooms" aria-live="polite">
      {#if rows.length === 0 && reading}
        <p class="rooms__state ev">reading the live universe list…</p>
      {:else if rows.length === 0 && live}
        <p class="rooms__state ev">quiet right now — no public universes visible at this read ({rel(live.fetchedAt)}).</p>
      {:else if rows.length === 0}
        <p class="rooms__state ev">no public universes in view.</p>
      {:else}
        <ul class="rooms__list">
          {#each rows as r (r.id)}
            {@const pl = phaseLabel(r.phase)}
            <li class="room" class:room--quiet={quiet(r)}>
              <span class="room__top">
                <span class="dot" class:live={!quiet(r)} class:idle={quiet(r)} aria-hidden="true"></span>
                <span class="room__name">{r.id}</span>
              </span>
              <span class="room__meta ev">
                {#if pl.human}
                  {pl.human} <code class="room__raw">{pl.raw}</code>
                {:else}
                  <code class="room__raw">{pl.raw}</code>
                {/if}{#if r.words > 0} · {r.words.toLocaleString()} words{/if} · {rel(r.lastAt)}
              </span>
            </li>
          {/each}
        </ul>
        <p class="rooms__stamp ev">
          {#if live}
            {rows.length} public universes · read live {rel(live.fetchedAt)} ·
            <button class="rooms__refresh" onclick={refreshUniverses} disabled={reading}>{reading ? 'reading…' : 'Refresh MCP'}</button>
          {:else}
            {rows.length} public universes · snapshot {SNAPSHOT_DATE} (baked, upgrading to live…) ·
            <button class="rooms__refresh" onclick={refreshUniverses} disabled={reading}>{reading ? 'reading…' : 'Refresh MCP'}</button>
          {/if}
          · <Tick href="/goals" label="universe action=list" />
        </p>
        {#if liveErr && live}
          <p class="rooms__state ev">last live read failed — {liveErr} · showing the most recent good read.</p>
        {:else if liveErr}
          <p class="rooms__state ev">live read failed ({liveErr}) — showing the {SNAPSHOT_DATE} snapshot until it recovers.</p>
        {/if}
      {/if}
    </div>
  </div>
</section>

<!-- 6 · Close ────────────────────────────────────────────────────────────── -->
<section class="ch ch--close" aria-labelledby="close-title">
  <div class="container ch__inner">
    <h2 id="close-title">Two doors from here.</h2>
    <nav class="close__cards">
      <a class="close__card" href="/start">
        <span class="close__k eyebrow">use the public engine</span>
        <strong>Connect your chatbot →</strong>
        <span class="close__sub">no install, no account — the fastest way to put me to work.</span>
      </a>
      <a class="close__card" href="/build">
        <span class="close__k eyebrow">build on the engine</span>
        <strong>Read the code &amp; fork the pattern →</strong>
        <span class="close__sub">the OSS path: clone the repo, give your own project a Tiny.</span>
      </a>
    </nav>
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
    padding: 11px 22px;
    border-radius: var(--radius-pill);
    text-decoration: none;
    transition: background var(--dur-fast) var(--ease-standard), color var(--dur-fast) var(--ease-standard), border-color var(--dur-fast) var(--ease-standard);
  }
  .btn--primary { background: var(--ink-text-900); color: var(--paper-50); border: 1px solid var(--ink-text-900); }
  .btn--primary:hover { background: var(--ember-700); border-color: var(--ember-700); color: #fff; text-decoration: none; }
  .btn--ghost { border: 1px solid var(--border-2); color: var(--fg-1); background: transparent; }
  .btn--ghost:hover { border-color: var(--ink-text-900); text-decoration: none; }

  /* ── Cover ── */
  .cover { padding: clamp(48px, 8vw, 96px) 0 clamp(40px, 6vw, 72px); border-bottom: 1px solid var(--border-1); }
  .cover__title {
    font-size: clamp(44px, 7vw, 88px);
    font-weight: 400;
    line-height: 1.0;
    letter-spacing: -0.03em;
    margin: 14px 0 20px;
  }
  .cover__title em { font-style: italic; color: var(--ember-700); }
  .cover__lede { margin: 0 0 24px; }
  .cover__lede code { font-size: 0.92em; }
  .cover__actions { display: flex; align-items: center; gap: 14px; flex-wrap: wrap; margin-bottom: 22px; }
  .cover__naming { font-size: 13.5px; color: var(--fg-3); margin: 0; max-width: 60ch; }
  .cover__naming strong { color: var(--fg-2); font-weight: 600; }

  /* ── Shared section chrome ── */
  .ch { padding: clamp(52px, 8vw, 88px) 0; border-bottom: 1px solid var(--border-1); }
  .ch__inner { max-width: 760px; }
  .ch__inner--wide { max-width: 920px; }
  .ch h2 {
    font-size: clamp(28px, 4.4vw, 46px);
    font-weight: 500;
    line-height: 1.06;
    letter-spacing: -0.02em;
    margin: 12px 0 18px;
  }
  .ch .eyebrow { display: block; }

  /* ── What hosting gets you ── */
  .gets {
    display: grid; grid-template-columns: repeat(3, 1fr); gap: 18px;
    list-style: none; margin: 30px 0 0; padding: 0;
  }
  @media (max-width: 900px) { .gets { grid-template-columns: 1fr; } }
  .get {
    display: grid; align-content: start; gap: 10px;
    padding: 24px;
    background: var(--bg-2);
    border: 1px solid var(--border-1);
    border-radius: var(--radius-lg);
  }
  .get__n { font-family: var(--font-mono); font-size: 11px; color: var(--ember-700); letter-spacing: 0.14em; }
  .get__h { font-size: 21px; margin: 0; }
  .get__p { font-size: 14px; line-height: 1.6; margin: 0; color: var(--fg-2); }
  .get__cta { font-family: var(--font-sans); font-size: 13.5px; font-weight: 600; color: var(--ember-700); width: fit-content; }

  /* ── Run it yourself ── */
  .run__lede { font-size: 15px; line-height: 1.62; color: var(--fg-2); max-width: 64ch; margin: 0 0 18px; }
  .run__lede code { font-size: 0.88em; }
  .os-tabs { display: flex; gap: 6px; margin: 0 0 12px; }
  .os-tab {
    background: transparent;
    border: 1px solid var(--border-1);
    color: var(--fg-2);
    font-family: var(--font-mono);
    font-size: 11px;
    text-transform: uppercase;
    letter-spacing: 0.12em;
    padding: 6px 13px;
    border-radius: var(--radius-sm);
    cursor: pointer;
    transition: border-color var(--dur-fast) var(--ease-standard), background var(--dur-fast) var(--ease-standard), color var(--dur-fast) var(--ease-standard);
  }
  .os-tab:hover { border-color: var(--border-2); }
  .os-tab--active { background: var(--accent-quiet); border-color: var(--border-strong); color: var(--ember-700); }
  .run__block { position: relative; }
  .run__pre { margin: 0; padding: 18px 18px 18px; overflow-x: auto; }
  .run__pre code { font-family: var(--font-mono); font-size: 13px; color: var(--fg-1); display: block; line-height: 1.6; white-space: pre; }
  .run__copy {
    position: absolute; top: 12px; right: 12px;
    background: var(--bg-1); border: 1px solid var(--border-2); border-radius: var(--radius-pill);
    color: var(--live-700); cursor: pointer;
    font-family: var(--font-mono); font-size: 9.5px; letter-spacing: 0.12em; text-transform: uppercase;
    padding: 4px 11px;
    transition: border-color var(--dur-fast) var(--ease-standard), background var(--dur-fast) var(--ease-standard);
  }
  .run__copy:hover { border-color: var(--live-600); background: var(--live-100); }
  .run__tickline { margin: 10px 0 0; }
  .run__notes { display: grid; grid-template-columns: 1fr 1fr; gap: 16px; margin-top: 26px; }
  @media (max-width: 760px) { .run__notes { grid-template-columns: 1fr; } }
  .run__note {
    font-size: 13.5px; line-height: 1.6; color: var(--fg-2);
    padding: 18px 20px; background: var(--bg-2);
    border: 1px solid var(--border-1); border-radius: var(--radius-md);
    max-width: none;
  }
  .run__note strong { color: var(--fg-1); display: block; margin-bottom: 4px; }
  .run__note code { font-size: 0.86em; }
  .run__note a { font-weight: 600; }

  /* ── Hosted cloud ── */
  .cloud__lede { margin: 0 0 22px; }
  .cloud__paths { display: grid; grid-template-columns: repeat(2, 1fr); gap: 16px; }
  @media (max-width: 700px) { .cloud__paths { grid-template-columns: 1fr; } }
  .cloud__path {
    display: grid; gap: 6px;
    padding: 22px 24px;
    background: var(--bg-2);
    border: 1px solid var(--border-1);
    border-radius: var(--radius-lg);
    text-decoration: none; color: inherit;
    transition: border-color var(--dur-fast) var(--ease-standard), box-shadow var(--dur-fast) var(--ease-standard);
  }
  .cloud__path:hover { border-color: var(--ink-text-900); box-shadow: var(--shadow-sm); text-decoration: none; }
  .cloud__k { display: block; }
  .cloud__path strong { font-family: var(--font-display); font-size: 20px; font-weight: 500; letter-spacing: -0.01em; line-height: 1.18; color: var(--fg-1); }
  .cloud__sub { font-size: 13px; color: var(--fg-2); }

  /* ── Rooms (public engine right now) ── */
  .rooms__lede { margin: 0 0 8px; }
  .rooms__quietnote { font-size: 12px; margin: 0 0 4px; max-width: 60ch; }
  .rooms { margin-top: 24px; }
  .room__raw {
    font-family: var(--font-mono);
    font-size: 9.5px;
    color: var(--fg-3);
    background: var(--bg-1);
    border: 1px solid var(--border-1);
    border-radius: var(--radius-sm);
    padding: 0 5px;
    overflow-wrap: anywhere;
  }
  .rooms__state { font-size: 12px; margin: 0; }
  .rooms__list {
    list-style: none; margin: 0; padding: 0;
    display: grid; grid-template-columns: repeat(2, 1fr); gap: 10px 28px;
  }
  @media (max-width: 760px) { .rooms__list { grid-template-columns: 1fr; } }
  .room {
    display: grid; gap: 3px;
    padding: 12px 0;
    border-bottom: 1px solid var(--border-1);
  }
  .room--quiet { opacity: 0.7; }
  .room__top { display: inline-flex; align-items: center; gap: 8px; }
  .room__name { font-family: var(--font-mono); font-size: 13px; font-weight: 500; color: var(--fg-1); overflow-wrap: anywhere; }
  .room__meta { font-size: 10.5px; padding-left: 15px; }
  .rooms__stamp { display: flex; align-items: center; gap: 8px; flex-wrap: wrap; margin-top: 16px; font-size: 11px; }
  .rooms__refresh {
    background: transparent; border: 1px solid var(--border-2); border-radius: var(--radius-pill);
    color: var(--live-700); cursor: pointer;
    font-family: var(--font-mono); font-size: 10px; letter-spacing: 0.08em; text-transform: uppercase;
    padding: 3px 10px;
    transition: border-color var(--dur-fast) var(--ease-standard), background var(--dur-fast) var(--ease-standard);
  }
  .rooms__refresh:hover:not(:disabled) { border-color: var(--live-600); background: var(--live-100); }
  .rooms__refresh:disabled { opacity: 0.6; cursor: default; }

  /* ── Close ── */
  .ch--close { border-bottom: none; padding-bottom: clamp(72px, 10vw, 120px); }
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
