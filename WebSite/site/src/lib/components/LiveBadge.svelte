<!--
  LiveBadge — small status pill showing whether data is from the live MCP
  feed or the baked snapshot, with an "X ago" relative timestamp.

  ago is computed only on the client (inside $effect) to avoid SSR/CSR
  hydration mismatch — Date.now() at SSR build time differs from Date.now()
  in the user's browser by hours/days, which Svelte 5 detects as a
  hydration mismatch and warns about. Computing client-only matches the
  intent (the ago is meant to be relative to the user's NOW).
-->
<script lang="ts">
  let { fetchedAt = '', source = '', loading = false } = $props<{ fetchedAt?: string; source?: string; loading?: boolean }>();

  let ago = $state('');

  function computeAgo(at: string): string {
    if (!at) return '';
    const ms = Date.now() - new Date(at).getTime();
    const sec = Math.round(ms / 1000);
    if (sec < 60) return `${sec}s ago`;
    const min = Math.round(sec / 60);
    if (min < 60) return `${min}m ago`;
    const hr = Math.round(min / 60);
    if (hr < 24) return `${hr}h ago`;
    return `${Math.round(hr / 24)}d ago`;
  }

  $effect(() => {
    ago = computeAgo(fetchedAt);
    // Re-tick once a minute so the user sees freshness change without reload.
    const t = setInterval(() => { ago = computeAgo(fetchedAt); }, 60_000);
    return () => clearInterval(t);
  });

  const isLive = $derived(source.includes('live'));
</script>

<span class="badge" class:live={isLive} class:loading>
  <span class="dot"></span>
  <span class="label">
    {#if loading}fetching live…{:else if isLive}live{#if ago} · {ago}{/if}{:else}snapshot{#if ago} · {ago}{/if}{/if}
  </span>
</span>

<style>
  .badge {
    display: inline-flex;
    align-items: center;
    gap: 8px;
    padding: 4px 11px 4px 9px;
    border-radius: 999px;
    font-family: var(--font-mono);
    font-size: 10px;
    font-weight: 500;
    letter-spacing: 0.1em;
    text-transform: uppercase;
    border: 1px solid var(--border-1);
    background: rgba(255, 255, 255, 0.04);
    color: var(--fg-2);
  }
  .badge.live {
    border-color: rgba(109, 211, 166, 0.3);
    color: #8de6bf;
    background: rgba(109, 211, 166, 0.08);
  }
  .badge.loading {
    border-color: rgba(217, 168, 74, 0.3);
    color: #e6bc6c;
    background: rgba(217, 168, 74, 0.08);
  }
  .dot {
    width: 7px;
    height: 7px;
    border-radius: 50%;
    background: var(--fg-3);
  }
  .badge.live .dot {
    background: var(--signal-live);
    box-shadow: 0 0 8px var(--signal-live);
    animation: pulse 1.8s infinite ease-in-out;
  }
  .badge.loading .dot {
    background: var(--signal-idle);
    animation: pulse 1.2s infinite ease-in-out;
  }
  @keyframes pulse {
    0%, 100% { opacity: 1; }
    50% { opacity: 0.45; }
  }
</style>
