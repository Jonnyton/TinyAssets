<!--
  VitalSigns — Tiny's pulse, read live from the same MCP endpoint visitors
  are invited to paste into their chatbot.

  Two truths, never collapsed into one dot:
    server  — is the engine reachable right now? (green / red)
    loop    — is work actually moving? (awake green / asleep amber)

  Asleep is a first-class, honestly-labeled state. No fake liveness:
  before the live read lands, the strip says it's reading — it never
  renders baked numbers as current.
-->
<script lang="ts">
  import { onMount } from 'svelte';
  import { fetchVitals, type Vitals } from '$lib/mcp/live';
  import { fmtRel } from '$lib/fmt';
  import Tick from './Tick.svelte';

  let { variant = 'strip' }: { variant?: 'hero' | 'strip' } = $props();

  let vitals = $state<Vitals | null>(null);
  let reading = $state(true);

  async function refresh() {
    reading = true;
    vitals = await fetchVitals();
    reading = false;
  }

  onMount(() => { void refresh(); });
</script>

<div class="vitals" class:hero={variant === 'hero'} aria-live="polite">
  {#if reading && !vitals}
    <span class="cell"><span class="dot" aria-hidden="true"></span><span class="k">reading my vital signs…</span></span>
  {:else if vitals && !vitals.reachable}
    <span class="cell"><span class="dot error" aria-hidden="true"></span><span class="k">engine unreachable from your browser</span></span>
    <span class="cell quiet">this is itself a true reading — <span class="ev">{vitals.error}</span></span>
    <button class="refresh" onclick={refresh} disabled={reading}>{reading ? 'reading…' : 'Refresh MCP'}</button>
  {:else if vitals}
    <span class="cell">
      <span class="dot live" aria-hidden="true"></span>
      <span class="k">engine live</span>
      {#if vitals.deployedAt}<span class="ev">deployed {fmtRel(vitals.deployedAt)}{#if vitals.gitSha}&nbsp;· {vitals.gitSha}{/if}</span>{/if}
    </span>
    <span class="cell">
      <span class="dot" class:live={vitals.loopAwake} class:idle={!vitals.loopAwake} aria-hidden="true"></span>
      {#if vitals.loopAwake && vitals.activeRun}
        <span class="k">loop awake · a run is moving</span>
      {:else if vitals.loopAwake}
        <span class="k">loop awake</span>
        {#if vitals.lastMovedAt}<span class="ev">last signal {fmtRel(vitals.lastMovedAt)}</span>{/if}
      {:else}
        <span class="k">loop asleep</span>
        {#if vitals.lastMovedAt}<span class="ev">last signal {fmtRel(vitals.lastMovedAt)}</span>{/if}
      {/if}
    </span>
    {#if vitals.queue}
      <span class="cell">
        <span class="k">lifetime runs</span>
        <span class="ev">{vitals.queue.succeeded.toLocaleString()} done · {vitals.queue.failed} failed · {vitals.queue.pending} queued</span>
      </span>
    {/if}
    <span class="cell quiet">
      <span class="ev">read {fmtRel(vitals.fetchedAt)}</span>
      <Tick href="/fine-print" label="how this is measured" />
    </span>
    <button class="refresh" onclick={refresh} disabled={reading}>{reading ? 'reading…' : 'Refresh MCP'}</button>
  {/if}
</div>

<style>
  .vitals {
    display: flex;
    flex-wrap: wrap;
    align-items: center;
    gap: 10px 20px;
    padding: 10px 16px;
    border: 1px solid var(--border-1);
    border-radius: var(--radius-md);
    background: var(--bg-2);
    width: fit-content;
    max-width: 100%;
  }
  .vitals.hero { padding: 12px 18px; }
  .cell { display: inline-flex; align-items: baseline; gap: 8px; }
  .cell .dot { align-self: center; }
  .k {
    font-family: var(--font-sans);
    font-size: 13px;
    font-weight: 500;
    color: var(--fg-1);
    white-space: nowrap;
  }
  .ev {
    font-family: var(--font-mono);
    font-size: 11px;
    color: var(--fg-3);
    letter-spacing: 0.01em;
  }
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
    padding: 4px 12px;
    transition: border-color var(--dur-fast) var(--ease-standard), background var(--dur-fast) var(--ease-standard);
  }
  .refresh:hover:not(:disabled) { border-color: var(--live-600); background: var(--live-100); }
  .refresh:disabled { opacity: 0.6; cursor: default; }

  /* hero variant = a dark READOUT panel (Tiny SHOWS its pulse) */
  .vitals.hero {
    display: grid;
    gap: 11px;
    width: 100%;
    padding: 18px 18px;
    background-color: var(--panel);
    background-image:
      linear-gradient(var(--panel-line) 1px, transparent 1px),
      linear-gradient(90deg, var(--panel-line) 1px, transparent 1px);
    background-size: 26px 26px;
    border: 1px solid #2c2a1d;
    border-radius: var(--radius-sm);
  }
  .vitals.hero .cell { display: flex; align-items: baseline; }
  .vitals.hero .k { color: var(--on-panel); }
  .vitals.hero .ev { color: var(--on-panel-soft); font-size: 12px; }
  .vitals.hero .cell.quiet .k { color: var(--on-panel-soft); }
  .vitals.hero :global(a) { color: var(--ember-300); }
  .vitals.hero :global(a:hover) { color: #ffd7df; }
  .vitals.hero .dot.live { background: var(--live-bright); box-shadow: 0 0 0 3px rgba(70, 180, 131, 0.22); }
  .vitals.hero .refresh { color: var(--live-bright); border-color: #3c4a40; }
  .vitals.hero .refresh:hover:not(:disabled) { border-color: var(--live-bright); background: rgba(70, 180, 131, 0.12); }
</style>
