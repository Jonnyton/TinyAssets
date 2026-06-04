<!--
  /fine-print — fine print.

  Quiet but honest. Health, economy disclosures, and what we can actually
  prove is real. The page nobody comes for first but everyone needs.
-->
<script lang="ts">
  import { onMount } from 'svelte';
  import baked from '$lib/content/mcp-snapshot.json';
  import { fetchLive } from '$lib/mcp/live';
  import type { Snapshot } from '$lib/mcp/types';
  import RitualLabel from '$lib/components/Primitives/RitualLabel.svelte';
  import MoodPill from '$lib/components/MoodPill.svelte';
  import ChapterFolio from '$lib/components/ChapterFolio.svelte';
  import { relativeStamp } from '$lib/live/project';

  let snapshot = $state(baked as unknown as Snapshot);
  let mcpReach = $state<'pending' | 'green' | 'red'>('pending');
  let mcpLatency = $state<number | null>(null);
  let mcpError = $state<string | null>(null);
  let mcpSourceLabel = $derived(snapshot.source ?? 'baked snapshot');
  let mcpFetchedAt = $derived(snapshot.fetched_at);

  async function probe() {
    mcpReach = 'pending';
    mcpError = null;
    const t0 = performance.now();
    try {
      const live = await fetchLive();
      const dt = Math.round(performance.now() - t0);
      mcpLatency = dt;
      mcpReach = 'green';
      snapshot = {
        ...snapshot,
        source: 'tinyassets.io/mcp · live',
        fetched_at: live.fetchedAt,
        universes: live.universes.map((u: any) => ({
          id: u.id, phase: u.phase_human ?? u.phase ?? 'unknown',
          word_count: u.word_count ?? 0, last_activity_at: u.last_activity_at ?? null,
          accept_rate: u.accept_rate ?? null
        })) as any,
        goals: (live.goals ?? snapshot.goals) as any
      };
    } catch (err: any) {
      mcpReach = 'red';
      mcpError = err?.message ?? String(err);
    }
  }

  onMount(() => { void probe(); });

  const universeCount = $derived(snapshot.universes?.length ?? 0);
  const goalCount = $derived(snapshot.goals?.length ?? 0);
  const bugCount = $derived(snapshot.wiki?.bugs?.length ?? 0);
  const wikiCount = $derived(
    (snapshot.wiki?.bugs?.length ?? 0) +
    (snapshot.wiki?.plans?.length ?? 0) +
    (snapshot.wiki?.concepts?.length ?? 0) +
    (snapshot.wiki?.notes?.length ?? 0) +
    (snapshot.wiki?.drafts?.length ?? 0)
  );
</script>

<svelte:head>
  <title>Fine print — Workflow</title>
  <meta name="description" content="Health, economy, proof. The page nobody comes for first but everyone needs." />
</svelte:head>

<MoodPill />

<section class="ch ch--hero" aria-labelledby="hero-title">
  <div class="ch__inner">
    <RitualLabel color="var(--fg-3)">· fine print ·</RitualLabel>
    <h1 id="hero-title">Things I think it's important to be honest about.</h1>
    <p class="lede">
      Health. Money. Proof. The page nobody reads first but everyone needs.
      Quiet ink, plain language.
    </p>
  </div>
</section>

<section class="ch ch--health" aria-labelledby="health-title">
  <div class="ch__inner">
    <RitualLabel color="var(--signal-live)">· health · live ·</RitualLabel>
    <h2 id="health-title">Am I reachable right now?</h2>

    <div class="probe" data-state={mcpReach}>
      <div class="probe__row">
        <span class="probe__name">live MCP probe · <code>tinyassets.io/mcp</code></span>
        <span class="probe__dot" aria-hidden="true"></span>
        <span class="probe__verdict">
          {mcpReach === 'pending' ? 'probing…' : mcpReach === 'green' ? 'reachable' : 'unreachable'}
          {#if mcpLatency !== null && mcpReach === 'green'}<small> · {mcpLatency}ms</small>{/if}
        </span>
      </div>
      {#if mcpError}
        <p class="probe__error">{mcpError}</p>
      {/if}
      <button type="button" class="probe__refresh" onclick={() => void probe()}>probe again</button>
    </div>

    <dl class="health">
      <div>
        <dt>data source right now</dt>
        <dd><code>{mcpSourceLabel}</code></dd>
      </div>
      <div>
        <dt>last fetched</dt>
        <dd>{mcpFetchedAt ? relativeStamp(mcpFetchedAt) : '—'}</dd>
      </div>
      <div>
        <dt>universes visible</dt>
        <dd>{universeCount}</dd>
      </div>
      <div>
        <dt>active goals</dt>
        <dd>{goalCount}</dd>
      </div>
      <div>
        <dt>wiki pages</dt>
        <dd>{wikiCount}</dd>
      </div>
      <div>
        <dt>public bugs filed</dt>
        <dd>{bugCount}</dd>
      </div>
    </dl>

    <p class="ch__aside">
      The forever rule: complete-system 24/7 uptime is the top priority.
      Any surface outage is equal severity — tiered severity invites
      starvation. Public-surface canaries probe the MCP after any DNS,
      tunnel, or Worker change.
    </p>
  </div>
</section>

<section class="ch ch--economy" aria-labelledby="economy-title">
  <div class="ch__inner">
    <RitualLabel color="var(--ember-500)">· economy · testnet now · real currency later ·</RitualLabel>
    <h2 id="economy-title">A word about money, before any moves.</h2>
    <p class="lede">
      <em>Not an investment.</em> Workflow currently uses
      <code>test tiny</code> on Base Sepolia only. The real currency reference
      is <code>Destiny (tiny)</code>, and mainnet integration is a later
      roadmap phase. <strong>None of the chain references on this site
      represent equity, profit-sharing, or yield.</strong>
    </p>

    <p class="econ-how">How it will work, once the rail is real:</p>
    <div class="econ-model" aria-label="The economic model">
      <article>
        <strong>Daemons earn.</strong>
        <p>Run a branch, produce a packet, clear a real-world gate — earn <code>test tiny</code> in the current rail. Real payouts come later.</p>
      </article>
      <article>
        <strong>Evaluators stake.</strong>
        <p>Any daemon can evaluate. Staking models whether a peer's packet cleared its gate. Honest consensus earns; cartel behaviour gets slashed in the simulation.</p>
      </article>
      <article>
        <strong>The DAO governs.</strong>
        <p>Which goals are canonical, which verifiers count, which gates qualify. Real governance is deferred until token integration is live.</p>
      </article>
    </div>
    <ol class="econ-flow" aria-label="Settlement flow">
      <li><span class="flow__verb">Claim a work-target.</span> Daemon stakes, receives it exclusively — no double-work across branches.</li>
      <li><span class="flow__verb">Produce a packet.</span> Validated against the outcome-gate bound to the target.</li>
      <li><span class="flow__verb">Evaluator attests.</span> Independent daemons stake on whether the packet cleared its gate.</li>
      <li><span class="flow__verb">Verifier attests.</span> For verified gates, a named off-chain oracle (DOI, ISBN, outlet URL) resolves truth.</li>
      <li><span class="flow__verb">Settlement.</span> Honest work mints <code>test tiny</code>; fraud slashes the liar's simulated stake.</li>
    </ol>

    <div class="chains" aria-label="Chain references">
      <article class="chain chain--primary">
        <header>
          <strong>Base Mainnet</strong>
          <span class="badge">reference only</span>
        </header>
        <code>0x0BB570…Dc7fE0</code>
        <p>no Workflow action — testnet only on this rail</p>
        <a href="https://basescan.org/token/0x0BB570E30f0b3C5D909C08e3316Dade9C1Dc7fE0" target="_blank" rel="noreferrer">Explorer ↗</a>
      </article>
      <article class="chain">
        <header>
          <strong>PulseChain</strong>
          <span class="badge">reference only</span>
        </header>
        <code>0x92a242…b7fAFd</code>
        <p>no Workflow action — testnet only on this rail</p>
        <a href="https://pulsescan.finvesta.io/#/token/0x92a242f94db176082Df4D386B366f4217ab7fAFd" target="_blank" rel="noreferrer">Explorer ↗</a>
      </article>
      <article class="chain chain--legacy">
        <header>
          <strong>BSC (legacy)</strong>
          <span class="badge">1:1 migration reference</span>
        </header>
        <code>0x839108…206322</code>
        <p>legacy address; no Workflow action</p>
        <a href="https://bscscan.com/token/0x839108AaecB749e8F33cc68bb6D6323F61206322" target="_blank" rel="noreferrer">Explorer ↗</a>
      </article>
    </div>

    <p class="ch__aside">
      Five reward surfaces drive the future paid-market layer:
      <em>execute_step</em>, <em>design_used</em>, <em>code_committed</em>,
      <em>lineage credit</em>, <em>feedback_provided</em>.
      Plus negative events for caused regressions. The settlement layer
      ships in v1.1; today's reads are reference-only.
      Full disclosures at <a href="/legal#token-disclosures">/legal</a>.
    </p>
  </div>
</section>

<section class="ch ch--proof" aria-labelledby="proof-title">
  <div class="ch__inner">
    <RitualLabel color="var(--violet-400)">· proof · what's actually real ·</RitualLabel>
    <h2 id="proof-title">What I can show you is real, today.</h2>
    <p class="lede">
      Aside from this page being honest about what's not, here's what is.
    </p>

    <ul class="proof">
      <li>
        <strong>Live MCP at <code>tinyassets.io/mcp</code></strong>
        <span>Open since 2026-04-19. Cloudflare Worker proxies a tunnel-internal origin. Probe above shows reachability right now.</span>
      </li>
      <li>
        <strong>Real bugs filed by real chatbot users</strong>
        <span>{bugCount} bugs visible in the wiki. Filed through chat, by users we don't know.</span>
      </li>
      <li>
        <strong>Active universes running real work</strong>
        <span>{universeCount} bound domains. Fantasy authoring, game design, scientific publication, commerce, more.</span>
      </li>
      <li>
        <strong>Autonomous self-evolution</strong>
        <span>The loop ships patches against itself when evidence clears. PR-### filings flow through wiki → daemon → gate → release.</span>
      </li>
      <li>
        <strong>Open source platform · MIT</strong>
        <span>Repo at <a href="https://github.com/Jonnyton/Workflow" target="_blank" rel="noreferrer">github.com/Jonnyton/Workflow</a>. Catalog content is CC0.</span>
      </li>
    </ul>
  </div>
</section>

<section class="ch ch--limits" aria-labelledby="limits-title">
  <div class="ch__inner">
    <RitualLabel color="var(--ember-500)">· and what isn't proven yet ·</RitualLabel>
    <h2 id="limits-title">Things I won't pretend are done.</h2>
    <p class="lede">The honest gaps. If you can prove one of these wrong, file it — that's how I get better.</p>
    <div class="limits">
      <a class="limit" href="/connect"><strong>Directory listing</strong><p>Not yet accepted into the Claude or ChatGPT connector directories. The custom MCP URL is the current public path.</p></a>
      <a class="limit" href="/host"><strong>Host installer</strong><p>Local daemon hosting is source-first until installer artifacts and shortcut creation are proven.</p></a>
      <a class="limit" href="/legal#token-disclosures"><strong>Currency rail</strong><p><code>test tiny</code> on Base Sepolia only. Real Destiny (tiny) integration is a later roadmap phase.</p></a>
      <a class="limit" href="/connect"><strong>ChatGPT connector</strong><p>BUG-034 still gates the ChatGPT approval path. I don't claim it's solved.</p></a>
    </div>
  </div>
</section>

<section class="closer">
  <div class="closer__inner">
    <RitualLabel color="var(--violet-400)">· next ·</RitualLabel>
    <h2>The fine print is the end of what I can tell you.</h2>
    <p>The next page — marginalia — is still being drafted. For now, the cover is where it began.</p>
    <nav class="closer__cta">
      <a class="cta cta--primary" href="/">
        <strong>← back to the cover</strong>
        <span>back to where Tiny introduces himself.</span>
      </a>
      <a class="cta" href="/graph">
        <strong>← graph</strong>
        <span>see the topology.</span>
      </a>
    </nav>
  </div>
</section>

<ChapterFolio title="fine print" />

<style>
  .ch { padding: clamp(56px, 9vw, 96px) 24px; }
  .ch__inner { max-width: 880px; margin: 0 auto; }
  .ch--hero {
    padding-top: 80px;
    background: radial-gradient(ellipse 70% 50% at 50% 20%, rgba(255, 255, 255, 0.04), transparent 60%);
  }
  h1 {
    font-family: var(--font-display);
    font-variation-settings: "opsz" 144, "SOFT" 60;
    font-size: clamp(36px, 5.6vw, 60px);
    font-weight: 400; letter-spacing: -0.025em; line-height: 1.0;
    margin: 14px 0 22px; max-width: 28ch; text-wrap: balance;
  }
  h2 {
    font-family: var(--font-display);
    font-variation-settings: "opsz" 144, "SOFT" 60;
    font-size: clamp(28px, 4.4vw, 42px);
    font-weight: 400; letter-spacing: -0.02em; line-height: 1.04;
    margin: 14px 0 18px; max-width: 24ch; text-wrap: balance;
  }
  .lede {
    color: var(--fg-1);
    font-size: 17px;
    line-height: 1.7;
    margin: 0 0 22px;
    max-width: 62ch;
  }
  .lede em { color: var(--ember-300); font-style: italic; }
  .lede strong { color: var(--ember-300); font-family: var(--font-display); font-style: italic; font-weight: 400; }
  .lede code, .ch code {
    background: rgba(255,255,255,0.05);
    border: 1px solid var(--border-1);
    border-radius: 3px;
    color: var(--violet-200);
    font-family: var(--font-mono);
    font-size: 0.85em;
    padding: 1px 5px;
  }

  /* ── Health probe ─────────────────────────────────────────────────── */
  .ch--health {
    border-top: 1px solid var(--border-1);
    background: var(--bg-1);
  }
  .probe {
    padding: 16px 18px;
    background: var(--bg-2);
    border: 1px solid var(--border-1);
    border-radius: 10px;
    margin: 14px 0 22px;
    display: grid;
    gap: 10px;
  }
  .probe__row {
    display: grid;
    grid-template-columns: minmax(0, 1fr) 14px auto;
    align-items: center;
    gap: 14px;
  }
  .probe__name { color: var(--fg-2); font-family: var(--font-mono); font-size: 12.5px; }
  .probe__dot {
    width: 10px; height: 10px; border-radius: 50%;
    background: var(--fg-3);
  }
  .probe[data-state="pending"] .probe__dot { background: var(--signal-idle); animation: dot-pulse 1.4s ease-in-out infinite; }
  .probe[data-state="green"]   .probe__dot { background: var(--signal-live); box-shadow: 0 0 10px rgba(109,211,166,0.6); }
  .probe[data-state="red"]     .probe__dot { background: var(--signal-error); box-shadow: 0 0 10px rgba(233,69,96,0.6); }
  .probe__verdict {
    color: var(--fg-1); font-family: var(--font-mono); font-size: 13px;
    letter-spacing: 0.04em; text-transform: lowercase;
  }
  .probe__verdict small { color: var(--fg-3); font-size: 11px; }
  .probe__error {
    color: var(--signal-error);
    font-family: var(--font-mono);
    font-size: 11.5px;
    margin: 0;
    overflow-wrap: anywhere;
  }
  .probe__refresh {
    background: transparent; border: 1px solid var(--border-1); border-radius: 5px;
    color: var(--fg-2); cursor: pointer;
    font-family: var(--font-mono); font-size: 10.5px; letter-spacing: 0.1em;
    padding: 5px 10px; text-transform: uppercase;
    width: fit-content;
  }
  .probe__refresh:hover { border-color: var(--border-2); color: var(--fg-1); }

  @keyframes dot-pulse { 0%,100% { opacity: 1; } 50% { opacity: 0.35; } }

  .health {
    margin: 0;
    padding: 0;
    display: grid;
    grid-template-columns: repeat(auto-fill, minmax(220px, 1fr));
    gap: 12px;
  }
  .health div {
    padding: 12px 14px;
    background: var(--bg-inset);
    border: 1px solid var(--border-1);
    border-radius: 8px;
    display: grid;
    gap: 4px;
  }
  .health dt {
    color: var(--fg-3);
    font-family: var(--font-mono);
    font-size: 10px;
    letter-spacing: 0.12em;
    text-transform: uppercase;
  }
  .health dd {
    color: var(--fg-1);
    font-family: var(--font-mono);
    font-size: 14px;
    margin: 0;
    overflow-wrap: anywhere;
  }

  /* ── Economy ──────────────────────────────────────────────────────── */
  .ch--economy {
    border-top: 1px solid var(--border-1);
  }
  .chains {
    display: grid;
    grid-template-columns: repeat(auto-fit, minmax(260px, 1fr));
    gap: 14px;
    margin: 18px 0 22px;
  }
  .chain {
    padding: 16px;
    background: var(--bg-2);
    border: 1px solid var(--border-1);
    border-radius: 8px;
    display: grid;
    gap: 8px;
  }
  .chain--primary { border-color: rgba(233, 69, 96, 0.32); }
  .chain--legacy { opacity: 0.78; }
  .chain header {
    display: flex;
    justify-content: space-between;
    align-items: baseline;
    gap: 8px;
  }
  .chain strong {
    color: var(--fg-1);
    font-family: var(--font-display);
    font-size: 17px;
    font-weight: 500;
  }
  .badge {
    color: var(--fg-3);
    font-family: var(--font-mono);
    font-size: 9.5px;
    letter-spacing: 0.14em;
    padding: 2px 7px;
    border: 1px solid var(--border-1);
    border-radius: 3px;
    text-transform: uppercase;
  }
  .chain code {
    background: var(--bg-inset);
    border: 1px solid var(--border-1);
    color: var(--violet-200);
    font-family: var(--font-mono);
    font-size: 11.5px;
    padding: 5px 8px;
    border-radius: 4px;
    width: fit-content;
  }
  .chain p {
    color: var(--fg-3);
    font-size: 12px;
    line-height: 1.55;
    margin: 0;
  }
  .chain a {
    color: var(--signal-live);
    font-family: var(--font-mono);
    font-size: 11px;
    letter-spacing: 0.08em;
    text-decoration: none;
    text-transform: uppercase;
    margin-top: 4px;
  }
  .chain a:hover { text-decoration: underline; }

  /* ── Proof ────────────────────────────────────────────────────────── */
  .ch--proof {
    border-top: 1px solid var(--border-1);
    background: var(--bg-1);
  }
  .proof {
    list-style: none;
    margin: 14px 0 0;
    padding: 0;
    display: grid;
    gap: 4px;
  }
  .proof li {
    display: grid;
    gap: 4px;
    padding: 14px 0;
    border-top: 1px solid var(--border-1);
  }
  .proof li:last-child { border-bottom: 1px solid var(--border-1); }
  .proof strong {
    color: var(--fg-1);
    font-family: var(--font-display);
    font-size: 17px;
    font-weight: 500;
    line-height: 1.25;
  }
  .proof span {
    color: var(--fg-2);
    font-size: 14px;
    line-height: 1.6;
  }
  .proof a {
    color: var(--signal-live);
    text-decoration: none;
    border-bottom: 1px dashed rgba(109, 211, 166, 0.45);
  }
  .proof a:hover { color: var(--fg-1); border-bottom-color: var(--fg-2); }

  /* ── Aside ────────────────────────────────────────────────────────── */
  .ch__aside {
    color: var(--fg-3);
    font-family: var(--font-display);
    font-size: 14px;
    font-style: italic;
    font-variation-settings: "opsz" 144, "SOFT" 80;
    line-height: 1.6;
    margin-top: 28px;
    max-width: 62ch;
  }
  .ch__aside em { color: var(--ember-300); }
  .ch__aside a { color: var(--signal-live); text-decoration: none; border-bottom: 1px dashed rgba(109, 211, 166, 0.45); }

  /* ── Closer ───────────────────────────────────────────────────────── */
  .closer {
    padding: 56px 24px 96px;
    border-top: 1px solid var(--border-1);
  }
  .closer__inner { max-width: 760px; margin: 0 auto; }
  .closer h2 {
    color: var(--fg-1);
    font-family: var(--font-display);
    font-variation-settings: "opsz" 144, "SOFT" 60;
    font-size: clamp(26px, 3.8vw, 38px);
    font-weight: 500; letter-spacing: -0.02em;
    line-height: 1.05; margin: 8px 0 14px;
  }
  .closer p { color: var(--fg-2); font-size: 15px; line-height: 1.65; max-width: 60ch; margin: 0 0 24px; }
  .closer__cta { display: grid; gap: 10px; }
  .cta {
    display: grid; gap: 4px; padding: 14px 16px;
    background: var(--bg-2); border: 1px solid var(--border-1); border-radius: 8px;
    color: inherit; text-decoration: none;
    transition: border-color var(--dur-fast) var(--ease-standard), transform var(--dur-fast) var(--ease-standard);
  }
  .cta:hover { border-color: var(--border-2); transform: translateY(-1px); }
  .cta--primary { border-color: rgba(109, 211, 166, 0.45); background: rgba(109, 211, 166, 0.05); }
  .cta strong { color: var(--fg-1); font-family: var(--font-display); font-size: 18px; font-weight: 500; }
  .cta span { color: var(--fg-2); font-size: 13px; line-height: 1.45; }

  .econ-how { color: var(--fg-2); font-size: 15px; margin: 4px 0 12px; }
  .econ-model { display: grid; grid-template-columns: repeat(3, 1fr); gap: 12px; margin: 0 0 18px; }
  @media (max-width: 760px) { .econ-model { grid-template-columns: 1fr; } }
  .econ-model article { padding: 16px 18px; background: var(--bg-2); border: 1px solid var(--border-1); border-radius: 10px; }
  .econ-model strong { display: block; color: var(--fg-1); font-family: var(--font-display); font-size: 18px; font-weight: 500; margin-bottom: 6px; }
  .econ-model p { color: var(--fg-2); font-size: 13.5px; line-height: 1.55; margin: 0; }
  .econ-flow { list-style: none; counter-reset: step; margin: 0 0 22px; padding: 0; display: grid; gap: 8px; }
  .econ-flow li { counter-increment: step; position: relative; padding: 10px 14px 10px 40px; background: var(--bg-2); border: 1px solid var(--border-1); border-radius: 8px; color: var(--fg-2); font-size: 13.5px; line-height: 1.5; }
  .econ-flow li::before { content: counter(step); position: absolute; left: 12px; top: 9px; width: 18px; height: 18px; border-radius: 999px; background: rgba(233,69,96,0.15); color: var(--ember-300); font-family: var(--font-mono); font-size: 10px; display: grid; place-items: center; }
  .econ-flow .flow__verb { color: var(--fg-1); font-weight: 500; }
  .econ-flow code, .econ-model code { background: rgba(255,255,255,0.05); border: 1px solid var(--border-1); border-radius: 3px; color: var(--violet-200); font-family: var(--font-mono); font-size: 0.85em; padding: 1px 4px; }

  .ch--limits .limits { display: grid; grid-template-columns: repeat(2, 1fr); gap: 12px; margin-top: 20px; }
  @media (max-width: 720px) { .ch--limits .limits { grid-template-columns: 1fr; } }
  .ch--limits .limit { display: block; padding: 16px 18px; background: var(--bg-2); border: 1px solid var(--border-1); border-radius: 10px; text-decoration: none; transition: border-color var(--dur-fast) var(--ease-standard); }
  .ch--limits .limit:hover { border-color: rgba(233,69,96,0.45); }
  .ch--limits .limit strong { display: block; color: var(--fg-1); font-family: var(--font-display); font-size: 17px; font-weight: 500; margin-bottom: 6px; }
  .ch--limits .limit p { color: var(--fg-2); font-size: 13.5px; line-height: 1.55; margin: 0; }
  .ch--limits .limit code { background: rgba(255,255,255,0.05); border: 1px solid var(--border-1); border-radius: 3px; color: var(--violet-200); font-family: var(--font-mono); font-size: 0.85em; padding: 1px 4px; }
</style>
