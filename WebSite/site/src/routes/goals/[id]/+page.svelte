<!--
  /goals/[id] — a single goal's detail page. The persona crawl found every
  trail ending at an unlinked goal-id chip; this is where that chip leads.

  Client-side only (see +page.ts: prerender=false, ssr=false). It renders from
  the checked-in public snapshot and says plainly when an id is unavailable.
  Browser Goal lookup stays absent until the server exposes a public-only
  projection. All stamps go through $lib/fmt.
-->
<script lang="ts">
  import { page } from '$app/state';
  import bakedMcp from '$lib/content/mcp-snapshot.json';
  import { fmtStamp } from '$lib/fmt';
  import Ladder from '$lib/components/Ladder.svelte';
  import Term from '$lib/components/Term.svelte';
  import Tick from '$lib/components/Tick.svelte';

  type Rung = { key?: string; name: string; description?: string; lit?: boolean; evidence_url?: string };
  type Goal = {
    id: string;
    name: string;
    description: string;
    tags: string[];
    visibility: string;
    createdMs: number | null;
    updatedMs: number | null;
    rungs: Rung[];
  };

  const id = $derived(String(page.params.id ?? ''));

  function toTags(raw: unknown): string[] {
    if (Array.isArray(raw)) return raw.map((t) => String(t).trim()).filter(Boolean);
    if (typeof raw === 'string') return raw.split(',').map((t) => t.trim()).filter(Boolean);
    return [];
  }

  // Snapshot ladders may carry {name, rung_key, description}. A rung lights
  // only with a real evidence URL behind it.
  function toRungs(raw: unknown): Rung[] {
    if (!Array.isArray(raw)) return [];
    return raw
      .map((r: any) => ({
        key: r?.rung_key ?? r?.key ?? r?.name,
        name: String(r?.name ?? r?.rung_key ?? '').trim(),
        description: r?.description ? String(r.description) : undefined,
        lit: Boolean(r?.lit && r?.evidence_url),
        evidence_url: r?.evidence_url ?? undefined
      }))
      .filter((r) => r.name);
  }

  // Snapshot timestamps may be Unix epoch seconds or ISO strings.
  function toMs(value: unknown): number | null {
    if (typeof value === 'number' && Number.isFinite(value)) return value > 1e12 ? value : value * 1000;
    if (typeof value === 'string') {
      const n = Number(value);
      if (Number.isFinite(n) && n > 0) return n > 1e12 ? n : n * 1000;
      const p = Date.parse(value);
      if (!Number.isNaN(p)) return p;
    }
    return null;
  }

  function fromBaked(gid: string): Goal | null {
    const raw = ((bakedMcp as any).goals ?? []).find(
      (g: any) => String(g.id ?? g.goal_id ?? '') === gid
    );
    if (!raw || String(raw.visibility ?? '').toLowerCase() !== 'public') return null;
    return {
      id: gid,
      name: String(raw.name ?? ''),
      description: String(raw.summary ?? raw.description ?? ''),
      tags: toTags(raw.tags),
      visibility: String(raw.visibility),
      createdMs: toMs(raw.created_at),
      updatedMs: toMs(raw.updated_at ?? raw.created_at),
      rungs: toRungs(raw.gate_ladder)
    };
  }

  // The browser renders only the checked-in public snapshot.
  const bakedStamp = fmtStamp((bakedMcp as any).fetched_at);
  const goal = $derived(id ? fromBaked(id) : null);

  // This prompt carries the dated published content itself. It never asks the
  // visitor's connector to retrieve the source Goal or its branches.
  const bridgePrompt = $derived(
    goal?.name
      ? `Using this dated public snapshot record as inspiration—not as current state—help me design my own user-authored workflow. Published goal: "${goal.name}" (${id}). Outcome: ${goal.description || 'No outcome text was included.'}`
      : `Using this dated public snapshot record as inspiration—not as current state—help me design my own user-authored workflow. Published goal id: ${id}.`
  );
  let copied = $state(false);
  let copyTimer: number | null = null;
  async function copyBridge() {
    try {
      await navigator.clipboard.writeText(bridgePrompt);
      copied = true;
      if (copyTimer) clearTimeout(copyTimer);
      copyTimer = window.setTimeout(() => (copied = false), 1800);
    } catch { /* clipboard unavailable; the text is visible anyway */ }
  }

  const litCount = $derived((goal?.rungs ?? []).filter((r) => r.lit).length);
</script>

<svelte:head>
  <title>{goal?.name ? `${goal.name} — goal on Tiny` : `Goal ${id} — Tiny`}</title>
  <meta
    name="description"
    content="A goal retained in TinyAssets' checked-in public snapshot, including its outcome, tags, and evidence-gated ladder when recorded."
  />
</svelte:head>

<article class="detail">
  <div class="container">
    <p class="eyebrow"><a class="back" href="/goals">← the board</a> · goal</p>

    {#if !goal}
      <h1 class="detail__title">This goal is not in the public snapshot.</h1>
      <p class="detail__state ev">
        Nothing public in the checked-in snapshot answers to <code>{id}</code>.
        It may be private, newer than the snapshot, retired, or mistyped.
        Current Goal lookup is unavailable until the server enforces a
        public-only projection.
      </p>
      <p class="detail__back-cta">
        <a class="cta" href="/goals">← back to the board</a>
      </p>
    {:else}
      <h1 class="detail__title">{goal.name || `Goal ${id}`}</h1>

      <p class="detail__meta ev" aria-live="polite">
        <span class="detail__stamp"><span class="dot" aria-hidden="true"></span>checked-in snapshot {bakedStamp}</span>
        <Tick label={`goal ${goal.id || id}`} />
      </p>

      {#if goal.description}
        <!-- The lab-notebook detail belongs here, in a readable measure and
             NOT clamped — this is the one place the full body is meant to be. -->
        <div class="detail__body">
          {#each goal.description.split(/\n{2,}/).filter(Boolean) as para}
            <p>{para}</p>
          {/each}
        </div>
      {/if}

      {#if goal.tags.length}
        <ul class="detail__tags ev" aria-label="tags">
          {#each goal.tags as tag}
            <li>{tag}</li>
          {/each}
        </ul>
      {/if}

      <dl class="detail__dates ev">
        {#if goal.createdMs}
          <div><dt>created</dt><dd>{fmtStamp(goal.createdMs)}</dd></div>
        {/if}
        {#if goal.updatedMs}
          <div><dt>updated</dt><dd>{fmtStamp(goal.updatedMs)}</dd></div>
        {/if}
        {#if !goal.createdMs && !goal.updatedMs}
          <div><dt>dates</dt><dd>none recorded in this snapshot</dd></div>
        {/if}
      </dl>

      <section class="detail__ladder" aria-labelledby="ladder-title">
        <h2 id="ladder-title" class="detail__h2">The outcome
          <Term def="A ladder is a sequence of real-world rungs toward the outcome. A rung only lights with an evidence URL attached, so the outcome stays checkable instead of merely claimed.">ladder</Term>.</h2>
        {#if goal.rungs.length}
          <Ladder rungs={goal.rungs} start="now" />
          <p class="detail__honest ev">
            {goal.rungs.length} rung{goal.rungs.length === 1 ? '' : 's'} ·
            {litCount} lit — the honest snapshot count. A rung only lights once
            a real evidence URL is attached.
          </p>
        {:else}
          <p class="detail__honest ev">
            No ladder is recorded for this goal in the checked-in snapshot.
          </p>
        {/if}
      </section>

      <!-- The chatbot bridge carries the published snapshot text into a new
           composition. It does not request the source Goal record. -->
      <section class="bridge" aria-labelledby="bridge-title">
        <p class="eyebrow">remix the published outcome</p>
        <h2 id="bridge-title" class="detail__h2">Design your own workflow.</h2>
        <p class="bridge__lede">
          Paste this into any chatbot to compose from the dated public snapshot
          record shown above. Source Goal and branch records stay untouched:
        </p>
        <button type="button" class="bridge__prompt" onclick={copyBridge} aria-label={`Copy prompt: ${bridgePrompt}`}>
          <code>{bridgePrompt}</code>
          <span class="bridge__copy">{copied ? 'copied ✓' : 'copy'}</span>
        </button>
        <p class="bridge__note">
          New here? <a href="/start">How to connect →</a>
        </p>
      </section>
    {/if}
  </div>
</article>

<style>
  .container { max-width: 1160px; margin: 0 auto; padding-inline: clamp(18px, 4vw, 32px); }
  .detail { padding: clamp(40px, 7vw, 84px) 0 clamp(64px, 9vw, 110px); }
  .eyebrow { display: block; }
  .back { color: var(--fg-3); text-decoration: none; }
  .back:hover { color: var(--live-700); }

  .detail__title {
    font-family: var(--font-display);
    font-size: clamp(34px, 5.6vw, 60px);
    font-weight: 400;
    line-height: 1.04;
    letter-spacing: -0.025em;
    margin: 12px 0 16px;
    max-width: 24ch;
    color: var(--fg-1);
  }
  .detail__meta {
    display: flex; align-items: center; flex-wrap: wrap; gap: 12px;
    margin: 0 0 22px; font-size: 11.5px; color: var(--fg-3);
  }
  .detail__stamp { display: inline-flex; align-items: center; gap: 8px; }

  .detail__state {
    display: flex; align-items: center; gap: 10px; flex-wrap: wrap;
    margin: 8px 0 22px; padding: 14px 16px;
    background: var(--bg-inset); border: 1px dashed var(--border-2); border-radius: var(--radius-md);
    font-size: 13.5px; line-height: 1.6; color: var(--fg-2); max-width: 64ch;
  }
  .detail__state code {
    font-family: var(--font-mono); font-size: 12px; color: var(--fg-1);
    background: var(--bg-1); padding: 1px 5px; border-radius: 3px;
  }

  .detail__body { margin: 0 0 24px; max-width: 70ch; }
  .detail__body p { font-size: 15.5px; line-height: 1.7; color: var(--fg-2); margin: 0 0 14px; }
  .detail__body p:last-child { margin-bottom: 0; }

  .detail__tags { list-style: none; margin: 0 0 22px; padding: 0; display: flex; flex-wrap: wrap; gap: 6px; }
  .detail__tags li {
    font-family: var(--font-mono);
    border: 1px solid var(--border-1); border-radius: var(--radius-sm);
    color: var(--fg-3); font-size: 10.5px; letter-spacing: 0.01em;
    padding: 3px 9px; background: var(--bg-1);
  }

  .detail__dates {
    display: flex; flex-wrap: wrap; gap: 22px; margin: 0 0 30px;
    padding: 14px 0; border-top: 1px solid var(--border-1); border-bottom: 1px solid var(--border-1);
  }
  .detail__dates div { display: grid; gap: 2px; }
  .detail__dates dt { font-family: var(--font-mono); font-size: 9.5px; letter-spacing: 0.12em; text-transform: uppercase; color: var(--fg-4); }
  .detail__dates dd { margin: 0; font-size: 13px; color: var(--fg-2); }

  .detail__h2 {
    font-family: var(--font-display);
    font-size: clamp(22px, 3.4vw, 32px); font-weight: 500;
    letter-spacing: -0.015em; line-height: 1.1;
    margin: 0 0 16px; color: var(--fg-1);
  }
  .detail__ladder { margin: 0 0 40px; }
  .detail__honest { margin: 14px 0 0; font-size: 12px; line-height: 1.55; color: var(--fg-3); max-width: 64ch; }

  /* ── Bridge ── */
  .bridge {
    margin-top: 8px; padding: 26px;
    background: var(--bg-2); border: 1px solid var(--border-2); border-radius: var(--radius-lg);
  }
  .bridge .eyebrow { margin-bottom: 6px; }
  .bridge__lede { font-size: 14.5px; line-height: 1.6; color: var(--fg-2); margin: 0 0 14px; max-width: 62ch; }
  .bridge__prompt {
    display: flex; align-items: flex-start; justify-content: space-between; gap: 12px;
    width: 100%; text-align: left; margin: 0 0 12px;
    padding: 14px 16px;
    background: var(--bg-inset); border: 1px solid var(--border-1); border-radius: var(--radius-md);
    cursor: pointer;
    transition: border-color var(--dur-fast) var(--ease-standard), background var(--dur-fast) var(--ease-standard);
  }
  .bridge__prompt:hover { border-color: var(--live-600); background: var(--live-100); }
  .bridge__prompt code { background: none; border: none; padding: 0; color: var(--fg-1); font-size: 13.5px; line-height: 1.5; white-space: normal; }
  .bridge__copy { flex: none; font-family: var(--font-mono); font-size: 9.5px; letter-spacing: 0.12em; text-transform: uppercase; color: var(--live-700); padding-top: 2px; }
  .bridge__note { font-size: 13px; color: var(--fg-3); margin: 0; }
  .bridge__note a { color: var(--ember-700); font-weight: 600; }

  .detail__back-cta { display: flex; align-items: center; gap: 14px; flex-wrap: wrap; margin: 18px 0 0; }
  .cta { color: var(--ember-700); font-weight: 600; font-size: 14px; text-decoration: none; }
  .cta:hover { text-decoration: underline; }

  .dot {
    width: 7px; height: 7px; border-radius: 50%; flex: none;
    background: var(--fg-4); display: inline-block;
  }
</style>
