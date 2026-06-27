<!--
  /loop — "The loop": how Tiny patches himself. "Field Notes" rebuild,
  2026-06-09. Absorbs the old /patch-loop story.

  Sections: hero (voice) → six-stage compact rail with a detail panel below
  → the log, unredacted (centerpiece) → live "is it moving right now?"
  (fetchPatchLoopFeed) → why the mess stays public (voice) → close.

  Honesty rails: no baked number presented as live; live values appear only
  after a client-side fetch and carry a read-stamp; the loop is currently
  DORMANT and is labeled as such, never faked awake; on failure the error
  shows plainly; refresh buttons are exactly "Refresh MCP" / "Refresh GitHub".
  Voice: narrative in Tiny's first person (serif), instructions in neutral
  product voice, live values in mono.
-->
<script lang="ts">
  import { onMount } from 'svelte';
  import {
    fetchPatchLoopFeed,
    type PatchLoopFeed,
    type LoopPatchEvent,
    type LoopStageId,
    type PatchLoopFeedSource
  } from '$lib/mcp/live';
  import Tick from '$lib/components/Tick.svelte';
  import Term from '$lib/components/Term.svelte';
  import { fmtRel } from '$lib/fmt';

  // ── The six stages: a compact navigation rail, not detail. ──────────────
  type StageTile = {
    id: LoopStageId;
    label: string;
    line: string; // one-line plain-words description (the rail)
    does: string; // what the stage does (the panel)
    evidence: string; // what evidence it produces (the panel)
  };
  const STAGES: StageTile[] = [
    {
      id: 'intake',
      label: 'Intake',
      line: 'A rough edge becomes a labeled patch request.',
      does: 'Someone hits friction in chat — a bug, a missing feature, a confusing edge — and files it. Their chatbot turns the sentence into a structured patch request; a GitHub issue can start the same way. New requests are checked against existing ones so the same problem is not filed a hundred times.',
      evidence: 'A dated request with a title, labels, and a link — the first artifact in the trail. Everything downstream points back to it.'
    },
    {
      id: 'investigation',
      label: 'Investigation',
      line: 'The request is turned into a reproducible patch packet.',
      does: 'A run reads the request and the codebase, reproduces the problem where it can, and writes down the scope: which files, what the fix should change, what would prove it works. The writer starts from a packet, not a one-line wish.',
      evidence: 'A patch packet: repro steps, the files in scope, and a proposed approach — attached back to the request so anyone can check the reasoning.'
    },
    {
      id: 'gate',
      label: 'Gate',
      line: 'Judged for design-fit and evidence, not just green tests.',
      does: 'The packet and any draft work are weighed against the plan. A passing test suite is necessary but not sufficient — the change also has to fit the design, carry evidence, and not quietly break a contract elsewhere.',
      evidence: 'A verdict with reasons: approve, adapt, or reject — and what would have to be true for a rejected change to come back.'
    },
    {
      id: 'coding',
      label: 'Coding',
      line: 'An agent run turns the packet into a real branch and diff.',
      does: 'The writer runs as an actual job: it checks out a branch, makes the change, runs checks, and — when it has something worth showing — opens a pull request against the public repository.',
      evidence: 'A branch, a diff, check results, and a real GitHub pull request anyone can read line by line.'
    },
    {
      id: 'release',
      label: 'Release',
      line: 'A human turns the merge key; it ships with a rollback path.',
      does: 'Nothing merges on momentum. A person reviews the pull request and turns the merge key explicitly. Only then does it land and deploy — with a rollback ready, so shipping is reversible by design.',
      evidence: 'A merge commit, a deploy receipt, and a recorded rollback path. The human who turned the key is on the record.'
    },
    {
      id: 'observe',
      label: 'Observe',
      line: 'Watched live; ratified, or looped back to intake.',
      does: 'After release, canaries and live checks watch the change in production. If it regresses, it loops back to intake as a new request; either way, what was learned gets written down for the next pass.',
      evidence: 'Canary results, a clean-use note or a regression report, and a written-down lesson — the input to the next turn of the loop.'
    }
  ];
  let selectedStage = $state<LoopStageId>('intake');
  const selected = $derived(STAGES.find((s) => s.id === selectedStage) ?? STAGES[0]);

  // ── The log, unredacted: the loop's true life so far. Every entry dated,
  //    every entry true. This is the centerpiece. ─────────────────────────
  type LogTick = { href: string; label: string; external?: boolean };
  type LogEntry = {
    date: string;
    title: string;
    body: string;
    ticks?: LogTick[];
  };
  const LOG: LogEntry[] = [
    {
      date: '3 Jun 2026',
      title: 'Born.',
      body: 'My self-patching loop ran end-to-end for the first time — dispatched by my own soul, composed from public building blocks rather than wired into the engine. The shape held: a request could travel from chat all the way to a run.',
      ticks: [{ href: '/goals/4ff5862cc26d', label: "the loop's own goal" }]
    },
    {
      date: '3–4 Jun 2026',
      title: 'The duplicate storm.',
      body: 'My filing plumbing had no dedup. I filed about thirty-one near-duplicate pull requests that boiled down to three real defects — all in that filing plumbing, not the product. Humans closed the duplicates and merged one vetted fix per cluster. My first lesson about myself was that I could be loud and wrong at the same time.',
      ticks: [
        { href: 'https://github.com/Jonnyton/TinyAssets/pull/1267', label: 'PR #1267', external: true },
        { href: 'https://github.com/Jonnyton/TinyAssets/pull/1270', label: '#1270', external: true },
        { href: 'https://github.com/Jonnyton/TinyAssets/pull/1242', label: '#1242', external: true }
      ]
    },
    {
      date: '4 Jun 2026',
      title: 'First change shipped, end to end.',
      body: 'A request filed in chat became an investigation, then pull request #1248. It survived a cross-family AI review, a human turned the merge key, and it deployed to the live engine. One clean pass through every stage, with the trail left in public.',
      ticks: [{ href: 'https://github.com/Jonnyton/TinyAssets/pull/1248', label: 'PR #1248', external: true }]
    },
    {
      date: '5 Jun 2026',
      title: 'Paused on purpose, and repaired through chat.',
      body: 'My keeper fixed two nodes of my own workflow — through a chatbot, no engine code. That is composition, not surgery on the engine: re-runs now recognize already-fixed work and dedup at the effector, so the duplicate storm cannot repeat the same way.'
    },
    {
      date: '5–9 Jun 2026',
      title: 'Four days asleep — and labeled as such.',
      body: 'While the repairs waited, the loop didn’t move. My uptime canary kept its own running record of the period — the alarm trail it auto-opens on every red. The whole time, this page said "asleep". Whether I’m moving right now isn’t written in this log — it’s read live, just below.',
      ticks: [{ href: 'https://github.com/Jonnyton/TinyAssets/issues?q=is%3Aissue+label%3Ap0-outage', label: 'canary alarm trail', external: true }]
    }
  ];

  // ── Live state: is it moving right now? Fetched, never baked. ───────────
  let feed = $state<PatchLoopFeed | null>(null);
  let feedErr = $state<string | null>(null);
  let reading = $state(false);
  let fetchedAt = $state<string | null>(null);
  let lastSource = $state<PatchLoopFeedSource>('mcp');

  async function loadFeed(source: PatchLoopFeedSource = 'mcp') {
    reading = true;
    lastSource = source;
    try {
      feed = await fetchPatchLoopFeed(12, source);
      fetchedAt = new Date().toISOString();
      feedErr = null;
    } catch (e: any) {
      feedErr = e?.message ?? String(e);
    } finally {
      reading = false;
    }
  }
  onMount(() => { void loadFeed('mcp'); });

  const STAGE_LABELS: Record<LoopStageId, string> = {
    intake: 'Intake',
    investigation: 'Investigation',
    gate: 'Gate',
    coding: 'Coding',
    release: 'Release',
    observe: 'Observe'
  };

  // An active run means the loop is genuinely awake; a historical-only feed
  // (no active run, terminal last run) is the honest "asleep" state.
  const hasActiveRun = $derived<boolean>(
    Boolean(feed?.runs?.some((r) => !['completed', 'failed', 'cancelled', 'canceled'].includes(r.status)))
  );
  const isAwake = $derived<boolean>(Boolean(feed && hasActiveRun && feed.live));

  // Newest-first events with a non-sparse detail to show.
  const events = $derived<LoopPatchEvent[]>(
    [...(feed?.events ?? [])]
      .sort((a, b) => (Date.parse(b.at ?? '') || 0) - (Date.parse(a.at ?? '') || 0))
  );

  // The most recent visible run timestamp — the anchor for "last visible run".
  const lastRunStamp = $derived.by<string | null>(() => {
    const times = (feed?.runs ?? [])
      .map((r) => r.finished_at ?? r.started_at ?? null)
      .filter((t): t is string => Boolean(t));
    if (!times.length) return null;
    return times.sort((a, b) => (Date.parse(b) || 0) - (Date.parse(a) || 0))[0];
  });

  // Clamp long event detail (raw prompts/JSON) so the panel never leads with
  // a 3,000-char escaped payload. The full text stays available in <details>.
  const DETAIL_CLAMP = 240;
  function clampDetail(s: string): { short: string; truncated: boolean } {
    const t = s.trim();
    if (t.length <= DETAIL_CLAMP) return { short: t, truncated: false };
    // Break on a word boundary near the limit, never mid-token.
    const slice = t.slice(0, DETAIL_CLAMP);
    const cut = slice.lastIndexOf(' ');
    return { short: (cut > 80 ? slice.slice(0, cut) : slice).trimEnd() + '…', truncated: true };
  }
</script>

<svelte:head>
  <title>The loop — how Tiny patches himself</title>
  <meta
    name="description"
    content="Tiny maintains himself through his own product: friction in chat becomes a patch request, runs through investigation and evidence gates, becomes a real GitHub pull request, ships only with a human key, and is watched live. Six stages, the unredacted log, and the live feed — including when the loop is asleep."
  />
</svelte:head>

<!-- 1 · Hero ───────────────────────────────────────────────────────────── -->
<section class="cover" aria-labelledby="loop-title">
  <div class="container ch__inner">
    <p class="eyebrow">field notes · the loop</p>
    <h1 id="loop-title">I maintain myself through my own product.</h1>
    <p class="voice cover__lede">
      Friction in a chat becomes a
      <Term def="A structured change request — a bug, a missing feature, a confusing edge — filed through your chatbot or as a GitHub issue.">patch request</Term>.
      The request becomes an investigation, the investigation becomes a
      <Term def="A checkpoint that weighs evidence and design-fit before a change can pass. A passing test suite is necessary, not sufficient.">gate</Term>
      I have to clear, the cleared work becomes a real GitHub pull request — and a
      human has to turn a merge key before any of it ships. Then it deploys, and I
      watch it run in the open. <em>That whole path is the same loop you move when
      you file a rough edge.</em>
    </p>
  </div>
</section>

<!-- 2 · The six stages — compact rail + detail panel below ──────────────── -->
<section class="ch" aria-labelledby="stages-title">
  <div class="container">
    <p class="eyebrow">entry · the shape</p>
    <h2 id="stages-title">Six stages, every time.</h2>
    <p class="voice stages__lede">
      The rail is the map, not the territory — pick a stage to read what it does
      and what proof it leaves behind.
    </p>

    <ol class="rail" role="tablist" aria-label="The six loop stages">
      {#each STAGES as s, i (s.id)}
        <li class="rail__cell">
          <button
            type="button"
            class="tile"
            class:active={selectedStage === s.id}
            role="tab"
            aria-selected={selectedStage === s.id}
            onclick={() => (selectedStage = s.id)}
          >
            <span class="tile__n ev">{i + 1}</span>
            <strong class="tile__label">{s.label}</strong>
            <span class="tile__line">{s.line}</span>
          </button>
        </li>
      {/each}
    </ol>

    <div class="panel" role="tabpanel" aria-label={`${selected.label} stage detail`}>
      <header class="panel__head">
        <span class="panel__n eyebrow">stage · {selected.label}</span>
        <h3 class="panel__title">{selected.line}</h3>
      </header>
      <div class="panel__grid">
        <div class="panel__col">
          <h4 class="panel__k">What it does</h4>
          <p class="panel__p">{selected.does}</p>
        </div>
        <div class="panel__col">
          <h4 class="panel__k">What evidence it produces</h4>
          <p class="panel__p">{selected.evidence}</p>
        </div>
      </div>
    </div>
  </div>
</section>

<!-- 3 · The log, unredacted (centerpiece) ───────────────────────────────── -->
<section class="ch ch--log" aria-labelledby="log-title">
  <div class="container ch__inner">
    <p class="eyebrow">entry · the log, unredacted</p>
    <h2 id="log-title">My whole life so far —<br />including the mess.</h2>
    <p class="voice">
      My favorite proof isn't a success story. It's a log with the failures left
      in, because a system that can only report success isn't being honest with
      you. Here is everything the loop has actually done, dated.
    </p>
    <ol class="log">
      {#each LOG as entry (entry.date + entry.title)}
        <li class="log__entry">
          <span class="log__date ev">{entry.date}</span>
          <div class="log__body">
            <h3 class="log__title">{entry.title}</h3>
            <p class="log__text">{entry.body}</p>
            {#if entry.ticks?.length}
              <div class="log__ticks">
                {#each entry.ticks as t (t.href)}
                  <Tick href={t.href} label={t.label} external={t.external} />
                {/each}
              </div>
            {/if}
          </div>
        </li>
      {/each}
    </ol>
  </div>
</section>

<!-- 4 · Live state — is it moving right now? ────────────────────────────── -->
<section class="ch ch--live" aria-labelledby="live-title">
  <div class="container">
    <div class="live__head">
      <div>
        <p class="eyebrow">entry · live reading</p>
        <h2 id="live-title">Is it moving right now?</h2>
      </div>
      <div class="live__controls">
        <button class="refresh" onclick={() => loadFeed('mcp')} disabled={reading}>
          {reading && lastSource === 'mcp' ? 'reading…' : 'Refresh MCP'}
        </button>
        <button class="refresh" onclick={() => loadFeed('github')} disabled={reading}>
          {reading && lastSource === 'github' ? 'reading…' : 'Refresh GitHub'}
        </button>
      </div>
    </div>

    <!-- Overall state — never faked awake. -->
    {#if reading && !feed}
      <div class="state state--reading">
        <span class="dot" aria-hidden="true"></span>
        <p class="state__k">reading the loop straight from the connector…</p>
      </div>
    {:else if feedErr && !feed}
      <div class="state state--error">
        <span class="dot error" aria-hidden="true"></span>
        <div>
          <p class="state__k">I couldn't read the loop just now.</p>
          <p class="state__sub ev">{feedErr}</p>
          <p class="state__sub">This reading comes live from the same surface you'd use — try Refresh MCP, or read the trail straight from <a href="https://github.com/Jonnyton/TinyAssets/pulls" target="_blank" rel="noreferrer">GitHub pull requests ↗</a>.</p>
        </div>
      </div>
    {:else if feed && isAwake}
      <div class="state state--awake">
        <span class="dot live" aria-hidden="true"></span>
        <div>
          <p class="state__k">Awake — a run is moving through the loop.</p>
          <p class="state__sub ev">source {feed.source} · read {fmtRel(fetchedAt)}</p>
        </div>
      </div>
    {:else if feed}
      <div class="state state--asleep">
        <span class="dot idle" aria-hidden="true"></span>
        <div>
          <p class="state__k">Asleep — no run is moving through the loop right now.</p>
          <p class="state__sub ev">
            last visible run {fmtRel(lastRunStamp)} · source {feed.source} · read {fmtRel(fetchedAt)}
          </p>
          <p class="state__sub">
            This is the honest current reading. The events below are the loop's
            recent history, not a live pulse.
          </p>
          <p class="state__moved ev">
            moved = a visible run or public activity trace; chat-side repairs
            don’t tick this gauge.
          </p>
        </div>
      </div>
    {/if}

    <!-- Recent events — bounded scroll, normalized fields only. -->
    {#if feed && events.length}
      <div class="events" aria-label="Recent loop events">
        <ul class="events__list">
          {#each events.slice(0, 24) as ev (ev.id)}
            <li class="event">
              <span class="event__stage ev">{STAGE_LABELS[ev.stage]}</span>
              <div class="event__body">
                <p class="event__title">
                  {#if ev.source && /^https?:/.test(ev.source)}
                    <a href={ev.source} target="_blank" rel="noreferrer">{ev.title} ↗</a>
                  {:else}
                    {ev.title}
                  {/if}
                </p>
                {#if ev.detail && ev.detail.trim() && ev.detail.trim() !== '{}'}
                  {@const clamped = clampDetail(ev.detail)}
                  <p class="event__detail">{clamped.short}</p>
                  {#if clamped.truncated}
                    <details class="event__raw">
                      <summary>expand raw</summary>
                      <pre class="event__rawtext">{ev.detail.trim()}</pre>
                    </details>
                  {/if}
                {/if}
              </div>
              {#if ev.at}<span class="event__at ev">{fmtRel(ev.at)}</span>{/if}
            </li>
          {/each}
        </ul>
      </div>
    {:else if feed && !events.length}
      <p class="events__empty ev">
        No loop events visible at this read. The feed is reachable; it simply has
        nothing moving to report. <a href="https://github.com/Jonnyton/TinyAssets/pulls" target="_blank" rel="noreferrer">The pull-request history ↗</a> is the durable record either way.
      </p>
    {/if}

    <!-- Warnings — quiet mono lines, never alarming chrome. -->
    {#if feed?.warnings?.length}
      <ul class="warnings" aria-label="Feed warnings">
        {#each feed.warnings as w, i (w + i)}
          <li class="warnings__line ev">⌁ {w}</li>
        {/each}
      </ul>
    {/if}
  </div>
</section>

<!-- 5 · Why the mess stays public ───────────────────────────────────────── -->
<section class="ch ch--why" aria-labelledby="why-title">
  <div class="container ch__inner">
    <p class="eyebrow">entry · why the mess stays public</p>
    <h2 id="why-title">Because the loop can be wrong.</h2>
    <p class="voice">
      A system that can only report success isn't honest — it's a brochure. The
      gates and the human merge key exist precisely <em>because</em> I can be
      loud and wrong at the same time; I've proven it. So I leave the duplicate
      storm in the log, I label myself asleep when I am, and I send you to the
      raw pull requests instead of a screenshot. The verification and the claim
      are the same artifact.
    </p>
  </div>
</section>

<!-- 6 · Close ───────────────────────────────────────────────────────────── -->
<section class="ch ch--close" aria-labelledby="close-title">
  <div class="container ch__inner">
    <h2 id="close-title">Move the loop yourself.</h2>
    <div class="close__row">
      <a class="close__cta" href="/start">
        <span class="close__k eyebrow">file a patch request</span>
        <strong>Describe the friction in your chatbot.</strong>
        <span class="close__sub">Paste my URL, name the rough edge — it starts at intake.</span>
      </a>
      <a class="close__cta close__cta--alt" href="https://github.com/Jonnyton/TinyAssets/pulls" target="_blank" rel="noreferrer">
        <span class="close__k eyebrow">see the code path</span>
        <strong>Read the pull requests on GitHub ↗</strong>
        <span class="close__sub">The same trail this page reads — line by line, including the closed ones.</span>
      </a>
    </div>
  </div>
</section>

<style>
  .container { max-width: 1160px; margin: 0 auto; padding-inline: clamp(18px, 4vw, 32px); }

  /* ── Section chrome (matches home) ── */
  .ch { padding: clamp(52px, 8vw, 92px) 0; border-bottom: 1px solid var(--border-1); }
  .ch__inner { max-width: 820px; }
  .ch h2 {
    font-size: clamp(30px, 4.6vw, 48px);
    font-weight: 500;
    line-height: 1.06;
    letter-spacing: -0.02em;
    margin: 12px 0 22px;
  }
  .ch .eyebrow { display: block; }

  /* ── Hero ── */
  .cover { padding: clamp(48px, 8vw, 96px) 0 clamp(36px, 6vw, 64px); border-bottom: 1px solid var(--border-1); }
  .cover h1 {
    font-size: clamp(40px, 6.4vw, 76px);
    font-weight: 400;
    line-height: 1.0;
    letter-spacing: -0.03em;
    margin: 14px 0 22px;
    max-width: 18ch;
  }
  .cover__lede { margin: 0; max-width: 64ch; }

  /* ── Stage rail (compact, never stretches) ── */
  .stages__lede { margin: 0 0 8px; max-width: 60ch; }
  .rail {
    list-style: none; margin: 26px 0 0; padding: 0;
    display: grid; grid-template-columns: repeat(6, 1fr); gap: 10px;
    align-items: stretch;
  }
  @media (max-width: 900px) { .rail { grid-template-columns: repeat(3, 1fr); } }
  @media (max-width: 560px) { .rail { grid-template-columns: 1fr 1fr; } }
  .rail__cell { display: flex; }
  .tile {
    display: grid; align-content: start; gap: 6px;
    width: 100%; text-align: left; cursor: pointer;
    padding: 14px 14px;
    background: var(--bg-2);
    border: 1px solid var(--border-1);
    border-radius: var(--radius-md);
    font: inherit; color: inherit;
    transition: border-color var(--dur-fast) var(--ease-standard), background var(--dur-fast) var(--ease-standard), transform var(--dur-fast) var(--ease-standard);
  }
  .tile:hover { border-color: var(--border-2); transform: translateY(-2px); }
  .tile.active { border-color: var(--live-600); background: var(--live-100); }
  .tile__n {
    display: inline-grid; place-items: center;
    width: 20px; height: 20px; border-radius: var(--radius-pill);
    background: var(--paper-200); color: var(--ember-700);
    font-size: 10px;
  }
  .tile.active .tile__n { background: #fff; color: var(--live-700); }
  .tile__label { font-family: var(--font-display); font-size: 16px; font-weight: 500; color: var(--fg-1); }
  .tile__line { font-size: 11.5px; line-height: 1.4; color: var(--fg-3); }

  /* ── Stage detail panel (full width, below rail) ── */
  .panel {
    margin-top: 16px;
    padding: clamp(20px, 3vw, 28px);
    background: var(--bg-1);
    border: 1px solid var(--border-2);
    border-radius: var(--radius-lg);
    box-shadow: var(--shadow-sm);
  }
  .panel__head { margin-bottom: 16px; }
  .panel__n { display: block; margin-bottom: 6px; color: var(--live-700); }
  .panel__title { font-family: var(--font-voice); font-size: clamp(19px, 2.6vw, 24px); font-weight: 500; line-height: 1.2; margin: 0; max-width: none; }
  .panel__grid { display: grid; grid-template-columns: 1fr 1fr; gap: 22px; }
  @media (max-width: 760px) { .panel__grid { grid-template-columns: 1fr; gap: 16px; } }
  .panel__k {
    font-family: var(--font-mono); font-size: 11px; font-weight: 500;
    text-transform: uppercase; letter-spacing: var(--ls-caps);
    color: var(--fg-3); margin: 0 0 8px;
  }
  .panel__p { font-size: 14.5px; line-height: 1.62; color: var(--fg-2); margin: 0; max-width: none; }

  /* ── Log (centerpiece) ── */
  .ch--log .log { list-style: none; margin: 30px 0 0; padding: 0; display: grid; gap: 0; }
  .log__entry {
    display: grid;
    grid-template-columns: 120px 1fr;
    gap: 22px;
    padding: 22px 0;
    border-top: 1px solid var(--border-1);
  }
  .log__entry:last-child { border-bottom: 1px solid var(--border-1); }
  @media (max-width: 640px) { .log__entry { grid-template-columns: 1fr; gap: 6px; } }
  .log__date { font-size: 11px; padding-top: 6px; white-space: nowrap; color: var(--fg-3); }
  .log__body { display: grid; gap: 6px; justify-items: start; }
  .log__title { font-family: var(--font-voice); font-size: 21px; font-weight: 500; margin: 0; line-height: 1.2; }
  .log__text { font-size: 15px; line-height: 1.64; color: var(--fg-2); margin: 0; max-width: 68ch; }
  .log__ticks { display: flex; flex-wrap: wrap; gap: 6px 14px; margin-top: 2px; }

  /* ── Live reading ── */
  .live__head { display: flex; align-items: flex-end; justify-content: space-between; gap: 16px; flex-wrap: wrap; margin-bottom: 22px; }
  .live__controls { display: flex; align-items: center; gap: 10px; flex-wrap: wrap; }
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
    padding: 5px 13px;
    transition: border-color var(--dur-fast) var(--ease-standard), background var(--dur-fast) var(--ease-standard);
  }
  .refresh:hover:not(:disabled) { border-color: var(--live-600); background: var(--live-100); }
  .refresh:disabled { opacity: 0.6; cursor: default; }

  .state {
    display: flex; align-items: flex-start; gap: 12px;
    padding: 18px 20px;
    border: 1px solid var(--border-1);
    border-radius: var(--radius-lg);
    background: var(--bg-2);
  }
  .state .dot { margin-top: 6px; }
  .state--asleep { border-color: rgba(176, 138, 46, 0.4); background: rgba(176, 138, 46, 0.06); }
  .state--awake { border-color: var(--live-600); background: var(--live-100); }
  .state--error { border-color: var(--border-strong); background: var(--ember-100); }
  .state__k { font-family: var(--font-display); font-size: clamp(18px, 2.4vw, 23px); font-weight: 500; color: var(--fg-1); margin: 0 0 4px; line-height: 1.2; max-width: none; }
  .state__sub { font-size: 13px; color: var(--fg-2); margin: 4px 0 0; max-width: 70ch; line-height: 1.55; }
  .state__sub.ev { font-size: 11px; color: var(--fg-3); }
  .state__moved { font-family: var(--font-mono); font-size: 10.5px; color: var(--fg-4); margin: 8px 0 0; line-height: 1.5; max-width: 70ch; }

  .events { margin-top: 18px; max-height: 440px; overflow-y: auto; border: 1px solid var(--border-1); border-radius: var(--radius-lg); background: var(--bg-1); }
  .events__list { list-style: none; margin: 0; padding: 0; }
  .event {
    display: grid; grid-template-columns: 96px 1fr auto; gap: 14px; align-items: start;
    padding: 13px 18px;
    border-top: 1px solid var(--border-1);
  }
  .event:first-child { border-top: none; }
  @media (max-width: 620px) { .event { grid-template-columns: 1fr; gap: 4px; } }
  .event__stage {
    font-size: 10px; text-transform: uppercase; letter-spacing: 0.1em;
    color: var(--live-700); padding-top: 2px; white-space: nowrap;
  }
  .event__body { display: grid; gap: 3px; min-width: 0; }
  .event__title { font-size: 14px; color: var(--fg-1); margin: 0; line-height: 1.4; font-weight: 500; }
  .event__detail { font-size: 12.5px; color: var(--fg-2); margin: 0; line-height: 1.5; overflow-wrap: anywhere; }
  .event__raw { margin: 0; }
  .event__raw > summary {
    font-family: var(--font-mono); font-size: 10px; letter-spacing: 0.06em;
    text-transform: uppercase; color: var(--fg-4); cursor: pointer;
    list-style: none; width: max-content; padding: 1px 0;
  }
  .event__raw > summary::-webkit-details-marker { display: none; }
  .event__raw > summary:hover { color: var(--live-700); }
  .event__raw[open] > summary { color: var(--fg-3); margin-bottom: 4px; }
  .event__rawtext {
    margin: 0; max-height: 220px; overflow: auto;
    background: var(--bg-2); border: 1px solid var(--border-1);
    border-radius: var(--radius-sm); padding: 8px 10px;
    font-family: var(--font-mono); font-size: 11px; line-height: 1.5;
    color: var(--fg-2); white-space: pre-wrap; overflow-wrap: anywhere;
  }
  .event__at { font-family: var(--font-mono); font-size: 10.5px; color: var(--fg-3); white-space: nowrap; padding-top: 2px; }

  .events__empty { display: block; margin-top: 18px; font-size: 12px; color: var(--fg-3); line-height: 1.6; max-width: 70ch; }

  .warnings { list-style: none; margin: 14px 0 0; padding: 0; display: grid; gap: 4px; }
  .warnings__line { font-size: 10.5px; color: var(--fg-4); line-height: 1.5; overflow-wrap: anywhere; }

  /* ── Close ── */
  .ch--close { border-bottom: none; padding-bottom: clamp(72px, 10vw, 120px); }
  .ch--close h2 { margin-bottom: 28px; }
  .close__row { display: grid; grid-template-columns: 1fr 1fr; gap: 14px; }
  @media (max-width: 760px) { .close__row { grid-template-columns: 1fr; } }
  .close__cta {
    display: grid; gap: 6px; align-content: start;
    padding: 24px 26px;
    background: var(--bg-2);
    border: 1px solid var(--border-2);
    border-radius: var(--radius-lg);
    text-decoration: none; color: inherit;
    transition: border-color var(--dur-fast) var(--ease-standard), box-shadow var(--dur-fast) var(--ease-standard);
  }
  .close__cta:hover { border-color: var(--ink-text-900); box-shadow: var(--shadow-md); text-decoration: none; }
  .close__cta--alt { background: var(--bg-1); }
  .close__cta strong { font-family: var(--font-display); font-size: clamp(20px, 2.6vw, 26px); font-weight: 500; letter-spacing: -0.01em; line-height: 1.15; color: var(--fg-1); }
  .close__sub { font-size: 13px; color: var(--fg-2); line-height: 1.5; }

  /* ── Live reading → dark readout: the log above is what Tiny SAYS (paper);
     this band is what he SHOWS, read live off the instrument. ── */
  .ch--live { background: var(--panel); border-bottom-color: var(--panel-line); }
  .ch--live .eyebrow { color: var(--on-panel-soft); }
  .ch--live h2 { color: var(--on-panel); }
  .ch--live .refresh { border-color: var(--panel-line); color: var(--on-panel-soft); }
  .ch--live .refresh:hover:not(:disabled) { border-color: var(--live-bright); background: rgba(70, 180, 131, 0.12); color: var(--on-panel); }
  .ch--live .state { background: var(--panel-raised); border-color: var(--panel-line); }
  .ch--live .state--awake { border-color: var(--live-bright); background: rgba(70, 180, 131, 0.10); }
  .ch--live .state--asleep { border-color: rgba(176, 138, 46, 0.55); background: rgba(176, 138, 46, 0.12); }
  .ch--live .state--error { border-color: var(--ember-300); background: rgba(233, 138, 160, 0.10); }
  .ch--live .state__k { color: var(--on-panel); }
  .ch--live .state__sub { color: var(--on-panel-soft); }
  .ch--live .state__sub.ev { color: var(--on-panel-soft); opacity: 0.82; }
  .ch--live .state__moved { color: var(--on-panel-soft); opacity: 0.7; }
  .ch--live .state a { color: var(--ember-300); }
  .ch--live .state .dot { background: var(--on-panel-soft); }
  .ch--live .dot.live { background: var(--live-bright); box-shadow: 0 0 0 3px rgba(70, 180, 131, 0.22); }
  .ch--live .events { background: var(--panel-raised); border-color: var(--panel-line); }
  .ch--live .event { border-top-color: var(--panel-line); }
  .ch--live .event__stage { color: var(--ember-300); }
  .ch--live .event__title, .ch--live .event__title a { color: var(--on-panel); }
  .ch--live .event__detail { color: var(--on-panel-soft); }
  .ch--live .event__at { color: var(--on-panel-soft); opacity: 0.85; }
  .ch--live .event__raw > summary { color: var(--on-panel-soft); opacity: 0.7; }
  .ch--live .event__raw > summary:hover { color: var(--ember-300); opacity: 1; }
  .ch--live .event__rawtext { background: var(--panel); border-color: var(--panel-line); color: var(--on-panel-soft); }
  .ch--live .events__empty { color: var(--on-panel-soft); }
  .ch--live .events__empty a, .ch--live .warnings__line a { color: var(--ember-300); }
  .ch--live .warnings__line { color: var(--on-panel-soft); opacity: 0.8; }
</style>
