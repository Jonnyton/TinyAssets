<!--
  /loop is a provenance-labelled view of ordinary, user-authored workflow
  activity. It does not represent a privileged platform task route and does
  not read community workflow, issue, label, or compatibility-feed data.
-->
<script lang="ts">
  import { onMount } from 'svelte';
  import { fetchPublicGoals, fetchPublicUniverses } from '$lib/mcp/live';
  import { fmtRel } from '$lib/fmt';

  type ActivityRead = { goals: any[]; universes: any[]; fetchedAt: string };
  let live = $state<ActivityRead | null>(null);
  let error = $state<string | null>(null);
  let reading = $state(false);

  async function refresh() {
    reading = true;
    try {
      // The shared browser MCP session initializes lazily, so keep the first
      // public graph reads sequential.
      const universes = await fetchPublicUniverses();
      const goals = await fetchPublicGoals();
      live = { universes, goals, fetchedAt: new Date().toISOString() };
      error = null;
    } catch (cause: any) {
      error = cause?.message ?? String(cause);
    } finally {
      reading = false;
    }
  }

  onMount(() => {
    void refresh();
  });

  const recentUniverses = $derived(
    [...(live?.universes ?? [])]
      .filter((universe) => universe?.visibility !== 'private')
      .sort(
        (a, b) =>
          (Date.parse(b?.last_activity_at ?? '') || 0) -
          (Date.parse(a?.last_activity_at ?? '') || 0)
      )
      .slice(0, 8)
  );

  const publicGoals = $derived(
    (live?.goals ?? [])
      .filter((goal) => goal?.visibility !== 'private')
      .slice(0, 6)
  );

  function universeName(universe: any): string {
    return universe?.name ?? universe?.title ?? universe?.id ?? 'Untitled workflow space';
  }

  function goalName(goal: any): string {
    return goal?.name ?? goal?.title ?? goal?.goal_id ?? goal?.id ?? 'Untitled goal';
  }
</script>

<svelte:head>
  <title>Workflow activity — TinyAssets</title>
  <meta
    name="description"
    content="A provenance-labelled view of public, user-authored workflow activity on TinyAssets, with live MCP read times and honest unavailable states."
  />
</svelte:head>

<section class="cover" aria-labelledby="loop-title">
  <div class="container cover__inner">
    <p class="eyebrow">public activity · ordinary workflows</p>
    <h1 id="loop-title">Loops belong to the people who design them.</h1>
    <p class="voice cover__lede">
      TinyAssets supplies reusable goals, graphs, runs, and records. A recurring
      workflow is a user-authored composition of those pieces—not a hidden
      maintenance path built into the platform. This page shows public activity
      visible through the connector and labels exactly where the reading came
      from.
    </p>
    <div class="principles" aria-label="Workflow activity principles">
      <span>user-authored</span>
      <span>copyable</span>
      <span>remixable</span>
      <span>provenance-labelled</span>
    </div>
  </div>
</section>

<section class="ch" aria-labelledby="activity-title">
  <div class="container">
    <header class="activity__head">
      <div>
        <p class="eyebrow">live connector reading</p>
        <h2 id="activity-title">Recent public workflow spaces</h2>
      </div>
      <button class="refresh" type="button" onclick={refresh} disabled={reading}>
        {reading ? 'reading…' : 'Refresh MCP'}
      </button>
    </header>

    {#if reading && !live}
      <div class="state">
        <span class="dot" aria-hidden="true"></span>
        <p>Reading public workflow activity from the MCP connector…</p>
      </div>
    {:else if error && !live}
      <div class="state state--error">
        <span class="dot error" aria-hidden="true"></span>
        <div>
          <p>Workflow activity is unavailable at this read.</p>
          <p class="ev">{error}</p>
        </div>
      </div>
    {:else if live}
      <p class="provenance ev">
        source tinyassets.io/mcp · read {fmtRel(live.fetchedAt)} · public
        universe activity only
      </p>

      {#if recentUniverses.length}
        <ul class="activity">
          {#each recentUniverses as universe (universe.id ?? universeName(universe))}
            <li class="activity__item">
              <div>
                <strong>{universeName(universe)}</strong>
                <p>
                  {universe.phase_human ?? universe.phase ?? 'workflow state not published'}
                </p>
              </div>
              <span class="ev">
                {universe.last_activity_at
                  ? `last public signal ${fmtRel(universe.last_activity_at)}`
                  : 'no public activity timestamp'}
              </span>
            </li>
          {/each}
        </ul>
      {:else}
        <p class="empty">
          No public workflow activity is visible in this connector read. That
          means activity is absent or unpublished—not that a fallback process
          is running elsewhere.
        </p>
      {/if}
    {/if}
  </div>
</section>

<section class="ch ch--goals" aria-labelledby="goals-title">
  <div class="container">
    <p class="eyebrow">designs with owners</p>
    <h2 id="goals-title">Start from a goal, then choose a workflow.</h2>
    <p class="voice section__lede">
      Goals describe outcomes. Patterns provide reusable shapes. The person
      doing the work chooses which graph runs, which evidence matters, and
      whether anything repeats.
    </p>

    {#if publicGoals.length}
      <ul class="goals">
        {#each publicGoals as goal (goal.goal_id ?? goal.id ?? goalName(goal))}
          <li>
            <strong>{goalName(goal)}</strong>
            {#if goal.description}<p>{goal.description}</p>{/if}
          </li>
        {/each}
      </ul>
      <p class="provenance ev">goal names from the same live MCP read</p>
    {:else if live}
      <p class="empty">No public goals were returned in this read.</p>
    {:else}
      <p class="empty">Connect to load the current public goal list.</p>
    {/if}
  </div>
</section>

<section class="ch ch--close" aria-labelledby="close-title">
  <div class="container">
    <h2 id="close-title">Compose one for your work.</h2>
    <div class="close">
      <a href="/patterns">
        <span class="eyebrow">patterns</span>
        <strong>Browse reusable workflow shapes →</strong>
        <span>Start with a design, copy it, and adapt the decisions.</span>
      </a>
      <a href="/commons">
        <span class="eyebrow">commons</span>
        <strong>Explore public goals and records →</strong>
        <span>See the artifacts people and their chatbots chose to publish.</span>
      </a>
    </div>
  </div>
</section>

<style>
  .container {
    max-width: 1080px;
    margin: 0 auto;
    padding-inline: clamp(18px, 4vw, 32px);
  }
  .cover {
    padding: clamp(78px, 12vw, 144px) 0 clamp(56px, 9vw, 100px);
    border-bottom: 1px solid var(--border-1);
  }
  .cover__inner { max-width: 850px; }
  h1 {
    max-width: 15ch;
    margin: 12px 0 24px;
    font-size: clamp(44px, 8vw, 84px);
    font-weight: 500;
    line-height: .95;
    letter-spacing: -.04em;
  }
  h2 {
    margin: 10px 0 20px;
    font-size: clamp(30px, 4.6vw, 48px);
    font-weight: 500;
    line-height: 1.05;
    letter-spacing: -.025em;
  }
  .cover__lede, .section__lede {
    max-width: 70ch;
    color: var(--fg-2);
    font-size: clamp(18px, 2.3vw, 23px);
    line-height: 1.55;
  }
  .principles {
    display: flex;
    flex-wrap: wrap;
    gap: 8px;
    margin-top: 30px;
  }
  .principles span {
    border: 1px solid var(--border-2);
    border-radius: 999px;
    padding: 7px 11px;
    color: var(--fg-2);
    font-family: var(--font-mono);
    font-size: 12px;
  }
  .ch {
    padding: clamp(54px, 8vw, 92px) 0;
    border-bottom: 1px solid var(--border-1);
  }
  .activity__head {
    display: flex;
    align-items: end;
    justify-content: space-between;
    gap: 24px;
  }
  .refresh {
    flex: 0 0 auto;
    border: 1px solid var(--border-2);
    border-radius: 999px;
    background: transparent;
    padding: 9px 15px;
    color: var(--fg-1);
    font: 12px var(--font-mono);
    cursor: pointer;
  }
  .refresh:hover:not(:disabled) { border-color: var(--live-600); }
  .refresh:disabled { cursor: wait; opacity: .55; }
  .state, .empty {
    display: flex;
    gap: 12px;
    margin-top: 28px;
    border: 1px solid var(--border-1);
    border-radius: 12px;
    padding: 18px;
    color: var(--fg-2);
  }
  .state p, .empty { margin-block: 0; }
  .provenance { margin: 18px 0; color: var(--fg-3); }
  .activity, .goals {
    list-style: none;
    margin: 0;
    padding: 0;
    border-top: 1px solid var(--border-1);
  }
  .activity__item {
    display: grid;
    grid-template-columns: minmax(0, 1fr) auto;
    gap: 20px;
    padding: 18px 0;
    border-bottom: 1px solid var(--border-1);
  }
  .activity__item p, .goals p {
    margin: 6px 0 0;
    color: var(--fg-2);
    line-height: 1.5;
  }
  .goals {
    display: grid;
    grid-template-columns: repeat(2, minmax(0, 1fr));
    gap: 0 24px;
    margin-top: 30px;
  }
  .goals li {
    min-width: 0;
    padding: 20px 0;
    border-bottom: 1px solid var(--border-1);
  }
  .close {
    display: grid;
    grid-template-columns: repeat(2, minmax(0, 1fr));
    gap: 16px;
    margin-top: 28px;
  }
  .close a {
    display: grid;
    gap: 9px;
    border: 1px solid var(--border-2);
    border-radius: 14px;
    padding: 24px;
    color: inherit;
    text-decoration: none;
  }
  .close a:hover { border-color: var(--live-600); }
  .close a span:last-child { color: var(--fg-2); line-height: 1.5; }
  @media (max-width: 700px) {
    .activity__head { align-items: start; flex-direction: column; }
    .activity__item { grid-template-columns: 1fr; gap: 8px; }
    .goals, .close { grid-template-columns: 1fr; }
  }
</style>
