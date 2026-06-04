<!--
  MoodPill — tiny top-right indicator showing the daemon's current state.

  Derives mood from the most recent universe's last_activity_at:
   - within 1h   → "drafting"   (violet, pulsing)
   - within 24h  → "watching"   (signal-live, dim)
   - older       → "quiet"      (fg-3, still)
   - unreachable → "summoned"   (ember, single ring)

  Click the pill to open a small popover explaining what each state means
  and what data the pill is reading. Honest about the algorithm, no theatre.

  Live: refreshes every 30s once mounted.
-->
<script lang="ts">
  import { onMount } from 'svelte';
  import baked from '$lib/content/mcp-snapshot.json';
  import { fetchLive } from '$lib/mcp/live';
  import type { Snapshot } from '$lib/mcp/types';

  type Mood = 'drafting' | 'watching' | 'quiet' | 'summoned';

  type Props = { compact?: boolean };
  let { compact = false }: Props = $props();

  function moodFromUniverses(universes: Array<{ last_activity_at?: string | null }>): { mood: Mood; mostRecentMs: number } {
    let mostRecent = 0;
    for (const u of universes ?? []) {
      const ms = u.last_activity_at ? Date.parse(u.last_activity_at) : NaN;
      if (Number.isFinite(ms) && ms > mostRecent) mostRecent = ms;
    }
    if (!mostRecent) return { mood: 'quiet', mostRecentMs: 0 };
    const ageMs = Date.now() - mostRecent;
    if (ageMs < 60 * 60 * 1000) return { mood: 'drafting', mostRecentMs: mostRecent };
    if (ageMs < 24 * 60 * 60 * 1000) return { mood: 'watching', mostRecentMs: mostRecent };
    return { mood: 'quiet', mostRecentMs: mostRecent };
  }

  const initial = moodFromUniverses((baked as unknown as Snapshot).universes ?? []);
  let mood = $state<Mood>(initial.mood);
  let mostRecentMs = $state<number>(initial.mostRecentMs);
  let source = $state<'snapshot' | 'live' | 'unreachable'>('snapshot');
  let open = $state(false);

  async function refresh() {
    try {
      const live = await fetchLive();
      const next = moodFromUniverses(live.universes ?? []);
      mood = next.mood;
      mostRecentMs = next.mostRecentMs;
      source = 'live';
    } catch {
      source = 'unreachable';
      // Keep last-known mood — don't lie about state.
    }
  }

  function fmtAge(ms: number): string {
    if (!ms) return 'never (no universe activity_at visible)';
    const d = Date.now() - ms;
    if (d < 60_000) return 'just now';
    if (d < 3_600_000) return `${Math.floor(d / 60_000)} minute${Math.floor(d / 60_000) === 1 ? '' : 's'} ago`;
    if (d < 86_400_000) return `${Math.floor(d / 3_600_000)} hour${Math.floor(d / 3_600_000) === 1 ? '' : 's'} ago`;
    return `${Math.floor(d / 86_400_000)} day${Math.floor(d / 86_400_000) === 1 ? '' : 's'} ago`;
  }

  function onKey(e: KeyboardEvent) {
    if (e.key === 'Escape' && open) open = false;
  }

  onMount(() => {
    void refresh();
    const t = window.setInterval(() => void refresh(), 30_000);
    return () => window.clearInterval(t);
  });
</script>

<svelte:window onkeydown={onKey} />

<div class="mood-wrap" class:compact>
  <button
    type="button"
    class="mood-pill"
    data-mood={mood}
    aria-label={`Daemon mood: ${mood}. Click to learn what this means.`}
    aria-expanded={open}
    onclick={() => (open = !open)}
  >
    <span class="dot" aria-hidden="true"></span>
    <span class="label">{mood}</span>
  </button>

  {#if open}
    <button class="scrim" type="button" aria-label="Close mood pill explainer" onclick={() => (open = false)}></button>
    <aside class="pop" role="dialog" aria-label="Mood pill explainer">
      <header>
        <span class="kicker">the daemon's mood</span>
        <button class="close" type="button" aria-label="Close" onclick={() => (open = false)}>×</button>
      </header>
      <p class="pop__now">
        Right now: <strong data-mood={mood}>{mood}</strong>.
        {#if mostRecentMs}
          Most recent universe activity {fmtAge(mostRecentMs)}.
        {:else}
          No universe activity visible in the current snapshot.
        {/if}
      </p>
      <dl class="pop__legend">
        <div>
          <dt class="t-drafting">drafting</dt>
          <dd>a universe was active in the last hour. something's happening right now.</dd>
        </div>
        <div>
          <dt class="t-watching">watching</dt>
          <dd>a universe was active in the last 24h. recent work, quiet at this moment.</dd>
        </div>
        <div>
          <dt class="t-quiet">quiet</dt>
          <dd>nothing in the last day. the daemon's still here, just resting.</dd>
        </div>
        <div>
          <dt class="t-summoned">summoned</dt>
          <dd>the live brain is unreachable. mood reading is whatever we last knew.</dd>
        </div>
      </dl>
      <p class="pop__source">
        Source: <code>universe action=list</code> via <code>tinyassets.io/mcp</code>.
        Reading the {source === 'live' ? 'live brain' : source === 'snapshot' ? 'baked snapshot (live refresh pending)' : 'last good cache'}.
      </p>
    </aside>
  {/if}
</div>

<style>
  .mood-wrap {
    position: fixed;
    top: 76px;
    right: 14px;
    z-index: 5;
  }
  .mood-wrap.compact {
    position: static;
    top: auto;
    right: auto;
  }

  .mood-pill {
    display: inline-flex;
    align-items: center;
    gap: 8px;
    padding: 6px 11px 6px 9px;
    background: var(--bg-inset);
    border: 1px solid var(--border-1);
    border-radius: 999px;
    color: var(--fg-2);
    cursor: pointer;
    font-family: var(--font-mono);
    font-size: 10.5px;
    letter-spacing: 0.12em;
    text-transform: lowercase;
    backdrop-filter: blur(8px);
    -webkit-backdrop-filter: blur(8px);
    transition: border-color var(--dur-fast) var(--ease-standard);
  }
  .mood-pill:hover { border-color: var(--border-2); }
  .mood-pill:focus-visible { outline: 1px dashed var(--ember-500); outline-offset: 2px; }

  .dot {
    width: 7px;
    height: 7px;
    border-radius: 50%;
    background: var(--fg-3);
    box-shadow: 0 0 0 2px rgba(255, 255, 255, 0.03);
    transition: background var(--dur-slow) var(--ease-summon), box-shadow var(--dur-slow) var(--ease-summon);
  }

  .mood-pill[data-mood="drafting"] {
    border-color: rgba(138, 99, 206, 0.42);
    color: var(--violet-200);
  }
  .mood-pill[data-mood="drafting"] .dot {
    background: var(--violet-400);
    box-shadow: 0 0 10px rgba(138, 99, 206, 0.8);
    animation: mood-pulse 1.8s ease-in-out infinite;
  }

  .mood-pill[data-mood="watching"] {
    border-color: rgba(109, 211, 166, 0.32);
    color: var(--fg-1);
  }
  .mood-pill[data-mood="watching"] .dot {
    background: var(--signal-live);
    box-shadow: 0 0 6px rgba(109, 211, 166, 0.45);
  }

  .mood-pill[data-mood="quiet"] {
    border-color: var(--border-1);
    color: var(--fg-3);
  }
  .mood-pill[data-mood="quiet"] .dot {
    background: var(--fg-3);
  }

  .mood-pill[data-mood="summoned"] {
    border-color: rgba(233, 69, 96, 0.42);
    color: var(--ember-300);
  }
  .mood-pill[data-mood="summoned"] .dot {
    background: var(--ember-600);
    box-shadow: 0 0 10px rgba(233, 69, 96, 0.6);
  }

  @keyframes mood-pulse {
    0%, 100% { opacity: 1; transform: scale(1); }
    50% { opacity: 0.55; transform: scale(0.78); }
  }

  /* ── Popover ─────────────────────────────────────────────────────── */
  .scrim {
    position: fixed;
    inset: 0;
    z-index: 6;
    background: transparent;
    border: 0;
    cursor: zoom-out;
  }
  .pop {
    position: absolute;
    top: calc(100% + 8px);
    right: 0;
    z-index: 7;
    width: min(340px, 92vw);
    padding: 14px 16px 16px;
    background: var(--bg-1);
    border: 1px solid var(--border-2);
    border-radius: 8px;
    box-shadow: 0 18px 50px rgba(0,0,0,0.55);
    animation: pop-in var(--dur-base) var(--ease-summon);
  }
  .pop header {
    display: flex;
    justify-content: space-between;
    align-items: center;
    margin-bottom: 8px;
  }
  .kicker {
    color: var(--fg-3);
    font-family: var(--font-mono);
    font-size: 10.5px;
    letter-spacing: 0.14em;
    text-transform: uppercase;
  }
  .close {
    background: transparent;
    border: 0;
    color: var(--fg-2);
    cursor: pointer;
    font-family: var(--font-display);
    font-size: 22px;
    line-height: 1;
    padding: 0 4px;
  }
  .close:hover { color: var(--fg-1); }

  .pop__now {
    color: var(--fg-1);
    font-size: 13.5px;
    line-height: 1.55;
    margin: 0 0 10px;
  }
  .pop__now strong {
    font-family: var(--font-display);
    font-style: italic;
    font-weight: 500;
  }
  .pop__now strong[data-mood="drafting"]  { color: var(--violet-200); }
  .pop__now strong[data-mood="watching"]  { color: var(--signal-live); }
  .pop__now strong[data-mood="quiet"]     { color: var(--fg-3); }
  .pop__now strong[data-mood="summoned"]  { color: var(--ember-300); }

  .pop__legend {
    border-top: 1px solid var(--border-1);
    border-bottom: 1px solid var(--border-1);
    margin: 0 0 10px;
    padding: 10px 0;
    display: grid;
    gap: 8px;
  }
  .pop__legend div {
    display: grid;
    grid-template-columns: 78px 1fr;
    gap: 10px;
    align-items: baseline;
  }
  .pop__legend dt {
    font-family: var(--font-mono);
    font-size: 10.5px;
    letter-spacing: 0.1em;
    text-transform: lowercase;
  }
  .pop__legend dd {
    color: var(--fg-2);
    font-size: 12px;
    line-height: 1.5;
    margin: 0;
  }
  .t-drafting { color: var(--violet-200); }
  .t-watching { color: var(--signal-live); }
  .t-quiet    { color: var(--fg-3); }
  .t-summoned { color: var(--ember-300); }

  .pop__source {
    color: var(--fg-3);
    font-family: var(--font-mono);
    font-size: 10.5px;
    line-height: 1.5;
    margin: 0;
  }
  .pop__source code {
    background: transparent;
    border: 0;
    color: var(--violet-200);
    padding: 0;
  }

  @keyframes pop-in {
    from { opacity: 0; transform: translateY(-4px); }
    to   { opacity: 1; transform: translateY(0); }
  }

  @media (max-width: 700px) {
    .mood-wrap { top: 70px; right: 10px; }
    .mood-pill { padding: 5px 9px 5px 8px; font-size: 10px; }
    .pop { right: -4px; }
  }
</style>
