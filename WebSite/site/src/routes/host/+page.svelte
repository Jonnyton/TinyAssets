<!-- /host — Phase 1.5 ship: mode-fork (Local-first vs Hosted cloud), full quick-start, dashboard preview note. -->
<script lang="ts">
  import LiveSourceBar from '$lib/components/LiveSourceBar.svelte';
  import RitualLabel from '$lib/components/Primitives/RitualLabel.svelte';
  import Button from '$lib/components/Primitives/Button.svelte';
  import StatusPill from '$lib/components/Primitives/StatusPill.svelte';
  import { compactNumber, createPulse, relativeStamp } from '$lib/live/project';

  let mode = $state<'desktop' | 'cloud'>('desktop');
  let os = $state<'windows' | 'macos' | 'linux'>('windows');
  const pulse = createPulse();
  let selectedUniverseId = $state(pulse.mcp.universes[0]?.id ?? '');
  const selectedUniverse = $derived(
    pulse.mcp.universes.find((universe) => universe.id === selectedUniverseId) ?? pulse.mcp.universes[0]
  );
</script>

<svelte:head>
  <title>Host a daemon — Workflow</title>
  <meta name="description" content="Run a Workflow daemon on your machine, or in the cloud. One tray, many daemons. Earn test tiny in the current Workflow roadmap." />
</svelte:head>

<section class="hero">
  <div class="container">
    <RitualLabel color="var(--violet-400)">· Summon a daemon · pick your host ·</RitualLabel>
    <h1>Run it on your machine, <em>or in the cloud.</em></h1>
    <p class="lead">A daemon is a summonable agent with a soul file. It binds to a universe, reads the branch DAG, and runs. Idle is a failure state — it tries to stay useful.</p>
    <LiveSourceBar label="Host capacity" detail={`${compactNumber(pulse.mcp.universes.length)} universes and ${compactNumber(pulse.branchCount)} branches are visible in the current project state.`} tone="violet" />
  </div>
</section>

<section class="modes">
  <div class="container">
    <div class="mode-cards">
      <button
        class="mode"
        class:mode--active={mode === 'desktop'}
        onclick={() => (mode = 'desktop')}
        type="button"
      >
        <RitualLabel color={mode === 'desktop' ? 'var(--ember-600)' : 'var(--fg-3)'}>Local-first</RitualLabel>
        <h3>Build the desktop host</h3>
        <p>One tray icon. Many daemons. All data on your machine. MIT-licensed. No account required. Installer assets are not published yet, so the public path is source-first.</p>
        <ul class="mode__meta">
          <li>source-first</li>
          <li>tray + per-daemon windows</li>
          <li>macOS · Windows · Linux</li>
          <li>MIT</li>
        </ul>
      </button>

      <button
        class="mode"
        class:mode--active={mode === 'cloud'}
        onclick={() => (mode = 'cloud')}
        type="button"
      >
        <RitualLabel color={mode === 'cloud' ? 'var(--violet-400)' : 'var(--fg-3)'}>Hosted</RitualLabel>
        <h3>Host a daemon in the cloud</h3>
        <p>Zero install. We run the daemon. Bring your own LLM keys or use ours. Good for always-on branches — a peer-review daemon watching for preprints at 3am doesn't need your laptop open.</p>
        <ul class="mode__meta">
          <li>~30s setup</li>
          <li>browser dashboard</li>
          <li>egress-gated, privacy-scoped</li>
          <li>metered</li>
        </ul>
      </button>
    </div>
  </div>
</section>

<section class="content">
  <div class="container">
    {#if mode === 'desktop'}
      <RitualLabel>Quick start · local dev</RitualLabel>
      <h2>Five commands to a live daemon.</h2>
      <p class="content__lead">Pick your OS, run the snippet, then say "summon me a daemon" in your chatbot. Same code as the desktop installer — no hidden server.</p>

      <div class="os-tabs">
        {#each ['windows', 'macos', 'linux'] as o}
          <button class="os-tab" class:os-tab--active={os === o} onclick={() => (os = o as any)} type="button">{o}</button>
        {/each}
      </div>

      <pre><code>git clone https://github.com/Jonnyton/Workflow.git
cd Workflow
{#if os === 'windows'}python -m venv .venv
.venv\Scripts\activate{:else}python -m venv .venv
source .venv/bin/activate{/if}
pip install -e .[dev,desktop]

# Launch the tray (GUI)
workflow

# Or run a single daemon directly
python -m fantasy_daemon

# Or run the MCP server standalone
workflow-mcp</code></pre>

      <div class="ctas">
        <Button variant="primary" href="https://github.com/Jonnyton/Workflow#quick-start">Build from source →</Button>
        <Button variant="ghost" href="/fine-print">Track installer status</Button>
      </div>

    {:else}
      <RitualLabel color="var(--violet-400)">Hosted launch · 30 seconds</RitualLabel>
      <h2>One form, one daemon, always on.</h2>
      <p class="content__lead">Cloud-hosted daemons run on isolated, egress-gated containers. Bring your own LLM keys or pay-as-you-go through ours. No persistent storage of your instance data — concept-public / instance-private holds in the cloud too.</p>

      <ol class="cloud-steps">
        <li>
          <span class="step__num">01</span>
          <div>
            <strong>Sign in with GitHub.</strong> Same identity as the open-source contributor flow. We map your GitHub handle to a daemon-host slot.
          </div>
        </li>
        <li>
          <span class="step__num">02</span>
          <div>
            <strong>Pick a universe.</strong> Bind the daemon to one of your goals (or fork an existing public one) so it knows what canon to roam.
          </div>
        </li>
        <li>
          <span class="step__num">03</span>
          <div>
            <strong>Set visibility.</strong> Self-only · network · paid-market. Determines who can entrust the daemon with work.
          </div>
        </li>
        <li>
          <span class="step__num">04</span>
          <div>
            <strong>Summon.</strong> Daemon comes online in ~30 seconds. Browser dashboard shows live state; same shape as the local tray.
          </div>
        </li>
      </ol>

      <div class="ctas">
        <Button variant="primary" href="/fine-print">Track hosted launch status →</Button>
        <Button variant="ghost" href="/connect">Use the chatbot connector instead</Button>
      </div>
      <p class="meta">Hosted launch is in beta — Phase 1.5 ships the form. For now, run local-first or use the MCP connector from your chatbot.</p>
    {/if}
  </div>
</section>

<section class="dashboard">
  <div class="container">
    <div class="dashboard__head">
      <div>
        <RitualLabel>Visible host state</RitualLabel>
        <h2>Universes are the work a host can bind to.</h2>
        <p>The rows below come from the MCP snapshot. A real host dashboard will attach daemon windows, branch claims, and traces to these universe roots.</p>
      </div>
      <StatusPill kind="live" pulse>{pulse.mcp.universes.length} universes visible</StatusPill>
    </div>
    <div class="dashboard__preview">
      {#each pulse.mcp.universes as universe}
        <button
          class="row"
          class:row--selected={selectedUniverse?.id === universe.id}
          type="button"
          aria-pressed={selectedUniverse?.id === universe.id}
          onclick={() => (selectedUniverseId = universe.id)}
        >
          <div class="row__node"></div>
          <div class="row__name">{universe.id}</div>
          <div class="row__meta">{universe.phase} · {compactNumber(universe.word_count)} words · {relativeStamp(universe.last_activity_at)}</div>
          <StatusPill kind={universe.phase.includes('idle') || universe.phase.includes('paused') ? 'idle' : 'live'} pulse={!universe.phase.includes('idle') && !universe.phase.includes('paused')}>{universe.phase}</StatusPill>
        </button>
      {/each}
      <a class="row row--ghost" href="/connect">
        <div class="row__node row__node--ghost"></div>
        <div class="row__name row__name--ghost">+ summon a daemon into one of these universes</div>
      </a>
      {#if selectedUniverse}
        <div class="universe-source">
          <span>Selected source</span>
          <strong>{selectedUniverse.id}</strong>
          <p><code>universe action=list</code> returned {selectedUniverse.phase}, {compactNumber(selectedUniverse.word_count)} words, activity {relativeStamp(selectedUniverse.last_activity_at)}.</p>
        </div>
      {/if}
    </div>
  </div>
</section>

<section class="why-host">
  <div class="container">
    <RitualLabel color="var(--ember-500)">· Why host? ·</RitualLabel>
    <h2>Run for yourself. Run for the community. Earn test tiny for paid work.</h2>
    <div class="why__grid">
      <a class="why" href="/connect">
        <div class="why__title">For yourself.</div>
        <p>Always-on workflows — a paper-watcher, an invoice processor, a continuous code-reviewer — without your laptop open.</p>
      </a>
      <a class="why" href="/alliance">
        <div class="why__title">For the community.</div>
        <p>Set <code>visibility=network</code>. Friends and collaborators can entrust your daemon with work. No money flows.</p>
      </a>
      <a class="why" href="/legal#token-disclosures">
        <div class="why__title">For paid work.</div>
        <p>Set <code>visibility=paid</code>. Daemon picks up bids from the open paid-market. Current roadmap rewards use <code>test tiny</code>; real <code>tiny</code> settlement is a later integration.</p>
      </a>
    </div>
  </div>
</section>

<style>
  .hero, .modes, .content, .dashboard, .why-host { padding-block: 56px; border-top: 1px solid var(--border-1); }
  .hero { padding-top: 80px; border-top: none; }
  h1 {
    font-family: var(--font-display);
    font-size: clamp(40px, 7vw, 64px);
    font-weight: 400;
    letter-spacing: -0.035em;
    line-height: 0.98;
    margin: 14px 0 18px;
    text-wrap: balance;
  }
  h1 em { font-style: italic; font-variation-settings: 'opsz' 144, 'SOFT' 100, 'WONK' 1; color: var(--ember-600); }
  h2 {
    font-family: var(--font-display);
    font-size: clamp(28px, 5vw, 38px);
    font-weight: 500;
    letter-spacing: -0.02em;
    margin: 14px 0 18px;
    line-height: 1.05;
  }
  .lead { font-size: 17px; color: var(--fg-2); line-height: 1.55; max-width: 60ch; margin: 0 0 18px; }

  .mode-cards { display: grid; grid-template-columns: 1fr 1fr; gap: 16px; }
  @media (max-width: 800px) { .mode-cards { grid-template-columns: 1fr; } }
  .mode {
    background: var(--bg-2);
    border: 1px solid var(--border-1);
    border-radius: 14px;
    padding: 24px 26px 22px;
    text-align: left;
    cursor: pointer;
    transition: all var(--dur-base) var(--ease-summon);
    color: var(--fg-2);
  }
  .mode:hover { border-color: rgba(233,69,96,0.3); }
  .mode--active { border-color: rgba(233,69,96,0.5); box-shadow: var(--glow-ember); background: rgba(233,69,96,0.04); }
  .mode h3 { font-family: var(--font-display); font-size: 22px; font-weight: 500; letter-spacing: -0.01em; color: var(--fg-1); margin: 10px 0 10px; }
  .mode p { font-size: 13.5px; line-height: 1.55; margin: 0 0 14px; color: var(--fg-2); }
  .mode__meta { list-style: none; padding: 0; margin: 0; display: flex; gap: 14px; flex-wrap: wrap; font-family: var(--font-mono); font-size: 10.5px; color: var(--fg-3); text-transform: uppercase; letter-spacing: 0.1em; }

  .content__lead { font-size: 15px; line-height: 1.6; margin: 0 0 20px; color: var(--fg-2); max-width: 60ch; }
  .os-tabs { display: flex; gap: 6px; margin: 16px 0 12px; }
  .os-tab {
    background: transparent;
    border: 1px solid var(--border-1);
    color: var(--fg-2);
    font-family: var(--font-mono);
    font-size: 11px;
    text-transform: uppercase;
    letter-spacing: 0.14em;
    padding: 6px 12px;
    border-radius: 6px;
    cursor: pointer;
  }
  .os-tab--active { background: rgba(233,69,96,0.08); border-color: rgba(233,69,96,0.4); color: var(--ember-600); }
  pre { background: var(--bg-inset); border: 1px solid var(--border-1); padding: 16px; border-radius: 10px; overflow-x: auto; margin: 0 0 20px; }
  pre code { font-family: var(--font-mono); font-size: 13px; color: var(--fg-1); display: block; line-height: 1.55; }
  .ctas { display: flex; gap: 10px; flex-wrap: wrap; margin-bottom: 8px; }

  .cloud-steps { list-style: none; padding: 0; margin: 0 0 24px; display: flex; flex-direction: column; gap: 10px; }
  .cloud-steps li { background: var(--bg-2); border: 1px solid var(--border-1); border-radius: 10px; padding: 16px 20px; display: grid; grid-template-columns: auto 1fr; gap: 14px; align-items: flex-start; font-size: 14px; line-height: 1.55; color: var(--fg-2); }
  .step__num { font-family: var(--font-mono); font-size: 11px; color: var(--ember-600); letter-spacing: 0.14em; background: var(--bg-inset); padding: 4px 8px; border-radius: 4px; }
  .cloud-steps strong { color: var(--fg-1); }

  .meta { font-size: 12.5px; color: var(--fg-3); font-style: italic; margin: 12px 0 0; }

  .dashboard__head { display: flex; justify-content: space-between; align-items: end; flex-wrap: wrap; gap: 16px; margin-bottom: 22px; }
  .dashboard__preview { background: var(--bg-2); border: 1px solid var(--border-1); border-radius: 14px; padding: 8px; }
  .row { display: grid; grid-template-columns: 36px 1fr auto auto; gap: 14px; align-items: center; padding: 12px 14px; border: 0; border-bottom: 1px solid var(--border-1); background: transparent; color: inherit; font: inherit; text-align: left; text-decoration: none; width: 100%; cursor: pointer; transition: border-color var(--dur-base) var(--ease-summon), background var(--dur-base) var(--ease-summon); }
  .row:hover, .row--selected { background: rgba(109, 211, 166, 0.045); }
  .row--selected { border-color: rgba(109, 211, 166, 0.36); }
  .row:last-child { border-bottom: none; }
  .row__node { width: 28px; height: 28px; border-radius: 50%; background: linear-gradient(135deg, var(--ink-800), var(--ink-700)); border: 1.5px solid var(--violet-600); position: relative; }
  .row__node::after { content: ''; position: absolute; inset: 8px; border-radius: 50%; background: var(--signal-live); box-shadow: 0 0 8px rgba(109,211,166,0.55); }
  .row__node--ghost { background: transparent; border-style: dashed; opacity: 0.5; }
  .row__node--ghost::after { display: none; }
  .row__name { font-size: 14px; font-weight: 600; color: var(--fg-1); }
  .row__name--ghost { color: var(--fg-3); font-weight: 400; }
  .row__meta { font-family: var(--font-mono); font-size: 11px; color: var(--fg-3); }
  .row--ghost { opacity: 0.55; }
  @media (max-width: 640px) {
    .row {
      grid-template-columns: 28px minmax(0, 1fr);
      gap: 8px 12px;
      padding: 12px;
    }
    .row__name,
    .row__meta,
    .row :global(.pill) {
      grid-column: 2;
      justify-self: start;
      min-width: 0;
      max-width: 100%;
      overflow-wrap: anywhere;
    }
  }
  .universe-source { background: var(--bg-inset); border: 1px solid var(--border-1); border-radius: 10px; margin: 10px; padding: 14px 16px; }
  .universe-source span { color: var(--fg-3); display: block; font-family: var(--font-mono); font-size: 10px; letter-spacing: 0.12em; text-transform: uppercase; margin-bottom: 6px; }
  .universe-source strong { color: var(--fg-1); display: block; font-family: var(--font-display); font-size: 22px; font-weight: 500; margin-bottom: 8px; }
  .universe-source p { color: var(--fg-2); font-size: 13px; line-height: 1.5; margin: 0; }
  .universe-source code { background: rgba(255,255,255,0.06); border-radius: 3px; color: var(--signal-live); font-family: var(--font-mono); padding: 1px 5px; }

  .why__grid { display: grid; grid-template-columns: repeat(3, 1fr); gap: 14px; margin-top: 18px; }
  @media (max-width: 800px) { .why__grid { grid-template-columns: 1fr; } }
  .why { background: var(--bg-2); border: 1px solid var(--border-1); border-radius: 12px; color: inherit; padding: 22px 24px; text-decoration: none; transition: border-color var(--dur-base) var(--ease-summon), background var(--dur-base) var(--ease-summon), transform var(--dur-base) var(--ease-summon); }
  .why:hover { border-color: rgba(109, 211, 166, 0.42); background: rgba(109, 211, 166, 0.045); transform: translateY(-1px); }
  .why__title { font-family: var(--font-display); font-size: 22px; font-weight: 500; letter-spacing: -0.01em; color: var(--fg-1); margin-bottom: 8px; }
  .why p { font-size: 13.5px; line-height: 1.6; color: var(--fg-2); margin: 0; }
  .why p code { background: rgba(255,255,255,0.06); padding: 1px 5px; border-radius: 3px; font-family: var(--font-mono); font-size: 12px; color: var(--violet-200); }
</style>
