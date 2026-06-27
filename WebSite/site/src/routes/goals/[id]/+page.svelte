<!--
  /goals/[id] — a single goal's detail page. The persona crawl found every
  trail ending at an unlinked goal-id chip; this is where that chip leads.

  Client-side only (see +page.ts: prerender=false, ssr=false). It paints
  instantly from the baked snapshot if the goal is in it, stamped with the
  snapshot's fetched_at, then upgrades live via `goals action=get`, which is
  the only place the full description + gate ladder live. Honest states: a
  goal absent from the snapshot shows "reading…" until the live read settles;
  a live read that fails with nothing baked says so plainly; a private /
  not-returned goal says exactly that. All stamps go through $lib/fmt.
-->
<script lang="ts">
  import { onMount } from 'svelte';
  import { page } from '$app/state';
  import { callTool } from '$lib/mcp/live';
  import bakedMcp from '$lib/content/mcp-snapshot.json';
  import { fmtStamp, fmtRel } from '$lib/fmt';
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

  // Live gate ladders carry {name, rung_key, description}. A rung lights ONLY
  // with a real evidence URL behind it — absent one, it renders unlit. That's
  // the honest default, and the section copy owns it.
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

  // Live timestamps are Unix epoch seconds; fmt.ts handles either, but we
  // keep a nullable ms so "unknown" stays honest when a goal carries none.
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
    if (!raw) return null;
    return {
      id: gid,
      name: String(raw.name ?? ''),
      // The baked snapshot stores the body as "summary"; live returns the
      // fuller "description". Baked is the placeholder until live lands.
      description: String(raw.summary ?? raw.description ?? ''),
      tags: toTags(raw.tags),
      visibility: String(raw.visibility ?? 'public'),
      createdMs: toMs(raw.created_at),
      updatedMs: toMs(raw.updated_at ?? raw.created_at),
      rungs: toRungs(raw.gate_ladder)
    };
  }

  function fromLive(raw: any, gid: string): Goal | null {
    if (!raw || typeof raw !== 'object') return null;
    // `goals action=get` may return the goal directly or under a `goal` key.
    const g = raw.goal ?? raw;
    if (!g || typeof g !== 'object') return null;
    const liveId = String(g.goal_id ?? g.id ?? gid);
    if (!g.name && !g.description) return null;
    return {
      id: liveId,
      name: String(g.name ?? ''),
      description: String(g.description ?? g.summary ?? ''),
      tags: toTags(g.tags),
      visibility: String(g.visibility ?? 'public'),
      createdMs: toMs(g.created_at),
      updatedMs: toMs(g.updated_at ?? g.created_at),
      rungs: toRungs(g.gate_ladder)
    };
  }

  // First paint: baked if present (instant, stamped with the snapshot date).
  const bakedStamp = fmtStamp((bakedMcp as any).fetched_at);
  let goal = $state<Goal | null>(null);

  // 'baked' = showing snapshot; 'reading' = first live read in flight with
  // nothing baked; 'live' = upgraded; 'missing' = live says no such public
  // goal and nothing baked; 'private' = live returned it as private/withheld.
  let phase = $state<'baked' | 'reading' | 'live' | 'missing' | 'private'>('baked');
  let readAt = $state<string | null>(null);
  let errMsg = $state<string | null>(null);

  async function load() {
    const gid = id;
    const baked = gid ? fromBaked(gid) : null;
    if (baked) {
      goal = baked;
      phase = 'baked';
    } else {
      goal = null;
      phase = 'reading';
    }
    if (!gid) {
      phase = 'missing';
      return;
    }
    errMsg = null;
    try {
      const res = await callTool('goals', { action: 'get', goal_id: gid });
      const live = fromLive(res, gid);
      if (live) {
        // A goal that comes back private (or with no public body) is named,
        // not silently swallowed.
        if (live.visibility.toLowerCase() === 'private') {
          goal = live;
          phase = 'private';
        } else {
          goal = live;
          readAt = new Date().toISOString();
          phase = 'live';
        }
      } else if (baked) {
        // Live read returned nothing usable but we still have the snapshot.
        // Keep showing baked rather than blanking the page.
        phase = 'baked';
      } else {
        phase = 'missing';
      }
    } catch (e: any) {
      errMsg = e?.message ?? String(e);
      // Error + nothing baked = honestly can't show the goal.
      if (!baked) phase = 'missing';
      else phase = 'baked';
    }
  }

  onMount(() => {
    void load();
  });

  // The neutral prompt a visitor pastes into their own chatbot.
  const bridgePrompt = $derived(
    goal?.name
      ? `Show me the goal "${goal.name}" (${id}) on my TinyAssets connector and list its branches.`
      : `Show me the goal ${id} on my TinyAssets connector and list its branches.`
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
    content="A single goal on Tiny — its outcome, tags, and evidence-gated ladder, read live from the same MCP endpoint your chatbot uses."
  />
</svelte:head>

<article class="detail">
  <div class="container">
    <p class="eyebrow"><a class="back" href="/goals">← the board</a> · goal</p>

    {#if phase === 'reading'}
      <!-- Nothing baked for this id yet; the live read is settling. -->
      <h1 class="detail__title detail__title--quiet">reading goal {id}…</h1>
      <p class="detail__state ev">
        <span class="dot" aria-hidden="true"></span>
        Pulling this goal live from the connector. If it's a public goal, it'll
        appear in a moment. <button class="retry" onclick={load}>Refresh MCP</button>
      </p>
    {:else if phase === 'missing'}
      <h1 class="detail__title">I can't find a public goal with this id.</h1>
      <p class="detail__state ev">
        {#if errMsg}
          The live read errored ({errMsg}).
        {/if}
        Nothing public answers to <code>{id}</code> right now. It may have been
        retired, made private, or the id was mistyped.
      </p>
      <p class="detail__back-cta">
        <a class="cta" href="/goals">← back to the board</a>
        <button class="retry" onclick={load}>Refresh MCP</button>
      </p>
    {:else if goal}
      <h1 class="detail__title">{goal.name || `Goal ${id}`}</h1>

      <p class="detail__meta ev" aria-live="polite">
        {#if phase === 'live'}
          <span class="detail__stamp"><span class="dot live" aria-hidden="true"></span>read live {fmtRel(readAt)}</span>
        {:else if phase === 'private'}
          <span class="detail__stamp"><span class="dot" aria-hidden="true"></span>read live · this goal is private</span>
        {:else}
          <span class="detail__stamp"><span class="dot" aria-hidden="true"></span>snapshot {bakedStamp} · upgrading live…</span>
        {/if}
        <Tick label={`goal ${goal.id || id}`} />
        <button class="retry" onclick={load}>Refresh MCP</button>
      </p>

      {#if phase === 'private'}
        <p class="detail__private ev">
          This goal is marked <strong>private</strong>. Private goals live on a
          host's own machine and never publish their body to the public commons —
          so there's no description or ladder to show here. Only its existence
          and id are public.
        </p>
      {/if}

      {#if errMsg && phase === 'baked'}
        <p class="detail__err ev">
          The live read errored ({errMsg}). What's below is the {bakedStamp}
          snapshot, not a live reading. Try Refresh MCP.
        </p>
      {/if}

      {#if goal.description && phase !== 'private'}
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
        {#if !goal.createdMs && !goal.updatedMs && phase === 'live'}
          <div><dt>dates</dt><dd>none recorded on this goal</dd></div>
        {/if}
      </dl>

      {#if phase !== 'private'}
        <section class="detail__ladder" aria-labelledby="ladder-title">
          <h2 id="ladder-title" class="detail__h2">The outcome
            <Term def="A ladder is a sequence of real-world rungs toward the outcome. A rung only lights with an evidence URL attached, so the outcome stays checkable instead of merely claimed.">ladder</Term>.</h2>
          {#if goal.rungs.length}
            <Ladder rungs={goal.rungs} start="now" />
            <p class="detail__honest ev">
              {goal.rungs.length} rung{goal.rungs.length === 1 ? '' : 's'} ·
              {litCount} lit — the honest count. A rung only lights once a real
              evidence URL is attached; unlit rungs are planned, not yet proven.
            </p>
          {:else if phase === 'live'}
            <p class="detail__honest ev">
              No ladder is bound to this goal yet — its outcome hasn't been
              broken into evidence-gated rungs. That's a normal early state.
            </p>
          {:else}
            <p class="detail__honest ev">
              The ladder upgrades once the live read lands.
            </p>
          {/if}
        </section>
      {/if}

      <!-- The chatbot bridge: a copyable prompt the visitor pastes into their
           own assistant to open this goal on their connector. -->
      <section class="bridge" aria-labelledby="bridge-title">
        <p class="eyebrow">take it to your chatbot</p>
        <h2 id="bridge-title" class="detail__h2">Open this goal on your connector.</h2>
        <p class="bridge__lede">
          With the <Term def="A connector is the one URL you paste into Claude, ChatGPT, or any MCP-capable assistant to give it the TinyAssets tools — no account, no install.">connector</Term>
          enabled, paste this into your own chatbot to inspect this goal and the
          branches competing to reach it:
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
  .detail__title--quiet { color: var(--fg-3); }

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
  .detail__state code, .detail__err code, .detail__private code {
    font-family: var(--font-mono); font-size: 12px; color: var(--fg-1);
    background: var(--bg-1); padding: 1px 5px; border-radius: 3px;
  }

  .detail__private {
    margin: 0 0 22px; padding: 14px 16px;
    background: var(--bg-inset); border: 1px solid var(--border-2); border-radius: var(--radius-md);
    font-size: 14px; line-height: 1.62; color: var(--fg-2); max-width: 64ch;
  }
  .detail__err {
    margin: 0 0 20px; padding: 12px 14px;
    background: var(--ember-100); border: 1px solid rgba(182, 39, 68, 0.32);
    border-radius: var(--radius-md);
    font-size: 12.5px; line-height: 1.55; color: var(--ember-900); overflow-wrap: anywhere; max-width: 64ch;
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

  .retry {
    background: transparent; border: 1px solid var(--border-2); border-radius: var(--radius-pill);
    color: var(--live-700); cursor: pointer;
    font-family: var(--font-mono); font-size: 10px; letter-spacing: 0.08em; text-transform: uppercase;
    padding: 4px 12px;
    transition: border-color var(--dur-fast) var(--ease-standard), background var(--dur-fast) var(--ease-standard);
  }
  .retry:hover:not(:disabled) { border-color: var(--live-600); background: var(--live-100); }
  .retry:disabled { opacity: 0.6; cursor: default; }

  .dot {
    width: 7px; height: 7px; border-radius: 50%; flex: none;
    background: var(--fg-4); display: inline-block;
  }
  .dot.live { background: var(--live-600); box-shadow: 0 0 0 3px var(--live-100); }
</style>
