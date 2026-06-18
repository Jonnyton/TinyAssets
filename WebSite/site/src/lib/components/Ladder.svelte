<!--
  Ladder — the gate-ladder visual.
  A goal's rungs toward a real-world outcome. A rung lights ONLY with an
  evidence URL behind it; everything else renders unlit. Unlit ladders are
  the honest default today — the copy treats that as the point, not a bug.
-->
<script lang="ts">
  type Rung = {
    key?: string;
    name: string;
    description?: string;
    lit?: boolean;
    evidence_url?: string;
  };
  let {
    rungs = [],
    start = 'start',
    compact = false
  }: { rungs: Rung[]; start?: string; compact?: boolean } = $props();
</script>

<ol class="ladder" class:compact>
  <li class="ladder__start" aria-hidden="true">{start}</li>
  {#each rungs as r, i (r.key ?? r.name)}
    <li class="rung" class:lit={r.lit}>
      <span class="rung__mark" aria-hidden="true">{r.lit ? '●' : '○'}</span>
      <span class="rung__body">
        <span class="rung__name">{r.name}</span>
        {#if !compact && r.description}
          <span class="rung__desc">{r.description}</span>
        {/if}
        {#if r.lit && r.evidence_url}
          <a class="rung__evidence" href={r.evidence_url} target="_blank" rel="noreferrer">evidence ↗</a>
        {/if}
      </span>
    </li>
  {/each}
</ol>

<style>
  .ladder {
    list-style: none;
    margin: 0;
    padding: 0;
    display: grid;
    gap: 0;
    position: relative;
  }
  .ladder__start {
    font-family: var(--font-mono);
    font-size: 10px;
    text-transform: uppercase;
    letter-spacing: 0.14em;
    color: var(--fg-4);
    padding: 0 0 6px 3px;
  }
  .rung {
    display: flex;
    gap: 10px;
    align-items: baseline;
    padding: 7px 0 7px 3px;
    position: relative;
  }
  /* the rail */
  .rung::before {
    content: '';
    position: absolute;
    left: 7.5px;
    top: 0;
    bottom: 0;
    width: 1px;
    background: var(--border-1);
  }
  .rung:last-child::before { bottom: 50%; }
  .rung__mark {
    position: relative;
    z-index: 1;
    font-size: 10px;
    line-height: 1.8;
    color: var(--fg-4);
    background: var(--bg-0);
    padding: 1px 0;
    flex: none;
    width: 16px;
    text-align: center;
  }
  .rung.lit .rung__mark { color: var(--live-600); }
  .rung__body { display: grid; gap: 1px; }
  .rung__name {
    font-family: var(--font-sans);
    font-size: 13.5px;
    font-weight: 500;
    color: var(--fg-2);
    line-height: 1.35;
  }
  .rung.lit .rung__name { color: var(--live-700); }
  .rung__desc {
    font-size: 12.5px;
    color: var(--fg-3);
    line-height: 1.45;
    max-width: 52ch;
  }
  .rung__evidence {
    font-family: var(--font-mono);
    font-size: 10.5px;
    color: var(--live-700);
    width: fit-content;
  }
  .compact .rung { padding: 4px 0 4px 3px; }
  .compact .rung__name { font-size: 12.5px; font-weight: 400; }
</style>
