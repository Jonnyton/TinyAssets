<!--
  /patch-loop — the community change (patch) loop.

  The build path: a user files friction → it moves through six stages →
  ships. Two layers shown: the fixed STAGES (the graph) and the live QUEUE
  (what's in those stages right now), pulled from the community_change_context
  MCP tool — the same surface a reviewer uses. Public-commons scoped.
-->
<script lang="ts">
  import { onMount } from 'svelte';
  import RitualLabel from '$lib/components/Primitives/RitualLabel.svelte';
  import MoodPill from '$lib/components/MoodPill.svelte';
  import ChapterFolio from '$lib/components/ChapterFolio.svelte';
  import { fetchChangeContext } from '$lib/mcp/live';

  let ctx = $state<any>(null);
  let loading = $state(true);
  let error = $state<string | null>(null);
  let fetchedAt = $state<string | null>(null);

  type Action = { kind: 'jump' | 'link' | 'ext'; label: string; target?: string; href?: string };
  type Stage = { id: string; label: string; desc: string; more: string; action: Action };
  const STAGES: Stage[] = [
    { id: 'intake', label: 'Intake', desc: 'You file a patch request — through your chatbot over MCP, or as a GitHub issue.',
      more: "Reports, bugs, and feature requests all land here as a labeled change request — the start of every patch.",
      action: { kind: 'jump', target: 'q-intake', label: 'see the open requests ↓' } },
    { id: 'investigation', label: 'Investigation', desc: 'The request becomes a reproducible patch packet with the context a writer needs.',
      more: "A daemon turns the raw request into repro steps, scope, and the files involved — so the writer starts with a real packet, not a sentence.",
      action: { kind: 'link', href: '/wiki', label: 'browse the commons →' } },
    { id: 'coding', label: 'Coding', desc: 'An agent team turns the packet into a branch and a diff.',
      more: "The writer runs as a real job — branch, diff, checks — and opens a PR when it has something to show.",
      action: { kind: 'jump', target: 'q-coding', label: 'see the runs ↓' } },
    { id: 'gate', label: 'Gate', desc: 'Judged for design-fit against the plan — not just green tests.',
      more: "Evidence and design-fit are weighed before anything lands. A passing test suite is necessary, not sufficient.",
      action: { kind: 'jump', target: 'q-standard', label: "see what it's judged against ↓" } },
    { id: 'release', label: 'Release', desc: 'Shipped with a rollback path.',
      more: "The branch merges and deploys with a rollback ready — shipping is reversible by design.",
      action: { kind: 'ext', href: 'https://github.com/Jonnyton/Workflow', label: 'see the repo ↗' } },
    { id: 'observe', label: 'Observe', desc: 'Watched live, then ratified or looped back. Learning gets recorded.',
      more: "A canary and live checks watch the change. If it regresses, it loops back to intake; either way, the learning gets written down.",
      action: { kind: 'jump', target: 'q-intake', label: '↑ back to intake — the loop closes' } }
  ];
  let selectedStage = $state('intake');
  function selectStage(id: string) { selectedStage = id; }
  function jump(target?: string) {
    if (!target || typeof document === 'undefined') return;
    const el = document.getElementById(target);
    if (!el) return;
    el.scrollIntoView({ behavior: 'smooth', block: 'center' });
    el.classList.add('pulse');
    window.setTimeout(() => el.classList.remove('pulse'), 1600);
  }

  async function load() {
    loading = true;
    try {
      ctx = await fetchChangeContext(8);
      fetchedAt = new Date().toISOString();
      error = null;
    } catch (e: any) {
      error = e?.message ?? String(e);
    } finally {
      loading = false;
    }
  }
  onMount(load);

  function dedupBy(arr: any[], keyOf: (x: any) => any): any[] {
    const seen = new Set<string>(); const out: any[] = [];
    for (const x of arr) { const k = String(keyOf(x) ?? ''); if (k && seen.has(k)) continue; if (k) seen.add(k); out.push(x); }
    return out;
  }
  const requests = $derived<any[]>(dedupBy([...(ctx?.open_change_requests ?? []), ...(ctx?.open_daemon_request_issues ?? [])], (x) => x.html_url ?? x.number));
  const runs = $derived<any[]>(ctx?.latest_auto_fix_runs ?? []);
  const prs = $derived<any[]>(dedupBy(ctx?.open_prs ?? [], (x) => x.html_url ?? x.number));
  const autoChangeCount = $derived<number>((ctx?.open_auto_change_prs ?? []).length);
  const reviewStandard = $derived<string[]>(ctx?.review_standard ?? []);

  function labelNames(labels: any[]): string[] {
    return (labels ?? []).map((l) => (typeof l === 'string' ? l : l?.name)).filter(Boolean).slice(0, 3);
  }
  function fmtRelative(s?: string | null): string {
    if (!s) return '';
    const ms = Date.parse(s);
    if (Number.isNaN(ms)) return s;
    const diff = Date.now() - ms;
    if (diff < 60_000) return 'just now';
    if (diff < 3_600_000) return `${Math.floor(diff / 60_000)}m ago`;
    if (diff < 86_400_000) return `${Math.floor(diff / 3_600_000)}h ago`;
    return `${Math.floor(diff / 86_400_000)}d ago`;
  }
  function runTone(r: any): string {
    const c = (r?.conclusion ?? r?.status ?? '').toLowerCase();
    if (c.includes('success')) return 'var(--signal-live)';
    if (c.includes('fail') || c.includes('cancel')) return 'var(--signal-error)';
    return 'var(--signal-idle)';
  }
</script>

<svelte:head>
  <title>Patch loop — Workflow</title>
  <meta name="description" content="The community patch loop: how a user files friction and watches it move through intake, investigation, coding, gate, release, and observe — live." />
</svelte:head>

<MoodPill />

<!-- Hero ─────────────────────────────────────────────────────────────────── -->
<section class="ch ch--hero" aria-labelledby="hero-title">
  <div class="ch__inner">
    <RitualLabel color="var(--signal-live)">· patch loop ·</RitualLabel>
    <h1 id="hero-title">How you help build me.</h1>
    <p class="lede">
      I patch myself through one loop, and it's the same loop you move. File a
      rough edge — through your chatbot or on GitHub — and watch it travel six
      stages from a sentence to a shipped change. This is that loop, and what's
      moving through it right now.
    </p>
  </div>
</section>

<!-- The six stages (the graph) ─────────────────────────────────────────────── -->
<section class="ch ch--stages" aria-labelledby="stages-title">
  <div class="ch__inner">
    <RitualLabel color="var(--violet-400)">· the shape ·</RitualLabel>
    <h2 id="stages-title">Six stages, every time.</h2>
    <ol class="stages">
      {#each STAGES as s, i (s.id)}
        <li>
          <button type="button" class="stage" class:active={selectedStage === s.id} aria-expanded={selectedStage === s.id} onclick={() => selectStage(s.id)}>
            <span class="stage__n">{i + 1}</span>
            <strong class="stage__label">{s.label}</strong>
            <p class="stage__desc">{s.desc}</p>
          </button>
        </li>
      {/each}
    </ol>
    {#each STAGES as s (s.id)}
      {#if selectedStage === s.id}
        <div class="stage-detail">
          <p>{s.more}</p>
          {#if s.action.kind === 'jump'}
            <button type="button" class="stage-action" onclick={() => jump(s.action.target)}>{s.action.label}</button>
          {:else}
            <a class="stage-action" href={s.action.href} target={s.action.kind === 'ext' ? '_blank' : undefined} rel={s.action.kind === 'ext' ? 'noreferrer' : undefined}>{s.action.label}</a>
          {/if}
        </div>
      {/if}
    {/each}
  </div>
</section>

<!-- The live queue ─────────────────────────────────────────────────────────── -->
<section class="ch ch--queue" aria-labelledby="queue-title">
  <div class="ch__inner">
    <div class="queue__head">
      <div>
        <RitualLabel color="var(--signal-live)">· what's in the loop right now ·</RitualLabel>
        <h2 id="queue-title">The live queue.</h2>
      </div>
      <div class="queue__controls">
        <button type="button" class="refresh" onclick={load} disabled={loading}>{loading ? 'reading…' : 'refresh'}</button>
        <span class="stamp">{error ? 'github/mcp unreachable' : fetchedAt ? `live · ${fmtRelative(fetchedAt)}` : 'reading…'}</span>
      </div>
    </div>

    {#if error}
      <p class="empty">Couldn't read the loop just now — <code>{error}</code>. It pulls live from GitHub through the connector; try refresh.</p>
    {/if}

    <!-- Intake -->
    <div class="block" id="q-intake">
      <h3 class="block__h">Intake <span class="block__count">{requests.length} open request{requests.length === 1 ? '' : 's'}</span></h3>
      {#if !loading && requests.length === 0}
        <p class="empty">Nothing waiting in intake — the queue is clear. File one through your chatbot and it lands here.</p>
      {:else}
        <ul class="cards">
          {#each requests as r (r.html_url ?? r.number)}
            <li class="card">
              <a href={r.html_url} target="_blank" rel="noreferrer">
                <span class="card__num">#{r.number}</span>
                <strong>{r.title}</strong>
                {#if labelNames(r.labels).length}
                  <span class="tags">{#each labelNames(r.labels) as t}<span>{t}</span>{/each}</span>
                {/if}
                <small>{fmtRelative(r.created_at)} · open ↗</small>
              </a>
            </li>
          {/each}
        </ul>
      {/if}
    </div>

    <!-- Coding -->
    <div class="block" id="q-coding">
      <h3 class="block__h">Coding <span class="block__count">{runs.length} recent run{runs.length === 1 ? '' : 's'}</span></h3>
      {#if !loading && runs.length === 0}
        <p class="empty">No auto-fix runs in the recent window. The writer fires on accepted packets, not on a timer.</p>
      {:else}
        <ul class="runs">
          {#each runs as run (run.id)}
            <li class="run">
              <a href={run.html_url} target="_blank" rel="noreferrer">
                <span class="run__dot" style:background={runTone(run)}></span>
                <code class="run__sha">{(run.head_sha ?? '').slice(0, 7) || 'run'}</code>
                <span class="run__status">{run.conclusion ?? run.status ?? 'queued'}</span>
                <small>{fmtRelative(run.created_at)} ↗</small>
              </a>
            </li>
          {/each}
        </ul>
      {/if}
    </div>

    <!-- Gate / release -->
    <div class="block">
      <h3 class="block__h">
        At the gate <span class="block__count">{prs.length} open PR{prs.length === 1 ? '' : 's'}{#if autoChangeCount > 0} · {autoChangeCount} auto-generated{/if}</span>
      </h3>
      {#if !loading && prs.length === 0}
        <p class="empty">No open PRs at the gate right now.</p>
      {:else}
        <ul class="cards">
          {#each prs as pr (pr.html_url ?? pr.number)}
            <li class="card">
              <a href={pr.html_url} target="_blank" rel="noreferrer">
                <span class="card__num">#{pr.number}</span>
                <strong>{pr.title}</strong>
                {#if labelNames(pr.labels).length}
                  <span class="tags">{#each labelNames(pr.labels) as t}<span>{t}</span>{/each}</span>
                {/if}
                <small>{fmtRelative(pr.created_at ?? pr.updated_at)} · review ↗</small>
              </a>
            </li>
          {/each}
        </ul>
      {/if}
    </div>
  </div>
</section>

<!-- The gate standard ──────────────────────────────────────────────────────── -->
{#if reviewStandard.length}
  <section class="ch ch--standard" id="q-standard" aria-labelledby="standard-title">
    <div class="ch__inner">
      <RitualLabel color="var(--ember-500)">· the gate ·</RitualLabel>
      <h2 id="standard-title">What a patch is judged against.</h2>
      <p class="lede">Tests passing isn't enough. Every change is held to the same standard before it lands:</p>
      <ul class="standard">
        {#each reviewStandard as rule}
          <li>{rule}</li>
        {/each}
      </ul>
    </div>
  </section>
{/if}

<!-- CTA / close ────────────────────────────────────────────────────────────── -->
<section class="closer">
  <div class="closer__inner">
    <RitualLabel color="var(--violet-400)">· enter the loop ·</RitualLabel>
    <h2>Found a rough edge? Move the loop.</h2>
    <p>Your chatbot files it as a patch request — and it starts at intake. Or open a PR on GitHub and meet it at the gate.</p>
    <nav class="closer__cta">
      <a class="cta cta--primary" href="/connect">
        <strong>file a patch through your chatbot →</strong>
        <span>paste my MCP URL, then describe the friction.</span>
      </a>
      <a class="cta" href="https://github.com/Jonnyton/Workflow" target="_blank" rel="noreferrer">
        <strong>open a PR on GitHub ↗</strong>
        <span>contribute a branch directly.</span>
      </a>
    </nav>
  </div>
</section>

<ChapterFolio title="patch loop" />

<style>
  .ch { padding: clamp(48px, 8vw, 88px) 24px; }
  .ch__inner { max-width: 980px; margin: 0 auto; }
  .ch--hero { padding-top: 80px; background: radial-gradient(ellipse 70% 50% at 50% 20%, rgba(109, 211, 166, 0.08), transparent 60%); }
  h1 {
    font-family: var(--font-display); font-variation-settings: "opsz" 144, "SOFT" 60;
    font-size: clamp(36px, 5.6vw, 60px); font-weight: 400; letter-spacing: -0.025em;
    line-height: 1.0; margin: 14px 0 20px; max-width: 22ch; text-wrap: balance;
  }
  h2 {
    font-family: var(--font-display); font-variation-settings: "opsz" 144, "SOFT" 60;
    font-size: clamp(26px, 4vw, 40px); font-weight: 500; letter-spacing: -0.02em;
    line-height: 1.05; margin: 12px 0 16px; text-wrap: balance;
  }
  .lede { color: var(--fg-1); font-size: 18px; line-height: 1.7; margin: 0 0 8px; max-width: 64ch; text-wrap: pretty; }

  /* stages */
  .ch--stages { border-top: 1px solid var(--border-1); }
  .stages { list-style: none; margin: 22px 0 0; padding: 0; display: grid; grid-template-columns: repeat(6, 1fr); gap: 10px; counter-reset: none; }
  @media (max-width: 900px) { .stages { grid-template-columns: repeat(3, 1fr); } }
  @media (max-width: 560px) { .stages { grid-template-columns: 1fr 1fr; } }
  .stages li { list-style: none; }
  .stage { display: block; width: 100%; text-align: left; font: inherit; color: inherit; cursor: pointer; position: relative; padding: 16px 14px; background: var(--bg-2); border: 1px solid var(--border-1); border-radius: 10px; transition: border-color var(--dur-fast) var(--ease-standard), transform var(--dur-fast) var(--ease-standard); }
  .stage:hover { border-color: rgba(109,211,166,0.5); transform: translateY(-2px); }
  .stage.active { border-color: var(--signal-live); background: rgba(109,211,166,0.06); }
  .stage-detail { margin-top: 12px; padding: 16px 18px; background: var(--bg-2); border: 1px solid rgba(109,211,166,0.3); border-radius: 10px; display: flex; align-items: center; justify-content: space-between; gap: 16px; flex-wrap: wrap; }
  .stage-detail p { color: var(--fg-1); font-size: 15px; line-height: 1.6; margin: 0; max-width: 64ch; }
  .stage-action { flex: none; background: transparent; border: 1px solid rgba(109,211,166,0.5); border-radius: 999px; color: var(--signal-live); cursor: pointer; font-family: var(--font-mono); font-size: 11.5px; letter-spacing: 0.06em; padding: 8px 16px; text-decoration: none; transition: border-color var(--dur-fast) var(--ease-standard), background var(--dur-fast) var(--ease-standard); }
  .stage-action:hover { border-color: rgba(109,211,166,0.9); background: rgba(109,211,166,0.08); }
  :global(.block.pulse), :global(.ch--standard.pulse) { animation: pulse-hl 1.6s ease; border-radius: 10px; }
  @keyframes pulse-hl { 0%, 100% { box-shadow: 0 0 0 0 rgba(109,211,166,0); } 25% { box-shadow: 0 0 0 3px rgba(109,211,166,0.5); } }
  .stage__n { display: inline-grid; place-items: center; width: 20px; height: 20px; border-radius: 999px; background: rgba(109,211,166,0.15); color: var(--signal-live); font-family: var(--font-mono); font-size: 10px; margin-bottom: 8px; }
  .stage__label { display: block; color: var(--fg-1); font-family: var(--font-display); font-size: 16px; font-weight: 500; margin-bottom: 6px; }
  .stage__desc { color: var(--fg-3); font-size: 12.5px; line-height: 1.5; margin: 0; }

  /* queue */
  .ch--queue { border-top: 1px solid var(--border-1); }
  .queue__head { display: flex; align-items: flex-end; justify-content: space-between; gap: 16px; flex-wrap: wrap; }
  .queue__controls { display: flex; align-items: center; gap: 12px; padding-bottom: 16px; }
  .refresh { background: transparent; border: 1px solid rgba(109,211,166,0.4); border-radius: 999px; color: var(--signal-live); cursor: pointer; font-family: var(--font-mono); font-size: 11px; letter-spacing: 0.12em; padding: 8px 16px; text-transform: uppercase; }
  .refresh:hover:not(:disabled) { border-color: rgba(109,211,166,0.8); background: rgba(109,211,166,0.06); }
  .refresh:disabled { opacity: 0.6; cursor: default; }
  .stamp { color: var(--fg-3); font-family: var(--font-mono); font-size: 11px; }

  .block { margin-top: 28px; }
  .block__h { color: var(--fg-1); font-family: var(--font-display); font-size: 20px; font-weight: 500; margin: 0 0 12px; display: flex; align-items: baseline; gap: 12px; flex-wrap: wrap; }
  .block__count { color: var(--fg-3); font-family: var(--font-mono); font-size: 11px; letter-spacing: 0.06em; text-transform: uppercase; font-weight: 400; }

  .cards { list-style: none; margin: 0; padding: 0; display: grid; grid-template-columns: repeat(auto-fill, minmax(300px, 1fr)); gap: 12px; }
  .card a { display: grid; gap: 6px; padding: 14px 16px; background: var(--bg-2); border: 1px solid var(--border-1); border-radius: 10px; text-decoration: none; transition: border-color var(--dur-fast) var(--ease-standard), transform var(--dur-fast) var(--ease-standard); }
  .card a:hover { border-color: var(--border-2); transform: translateY(-1px); }
  .card__num { color: var(--fg-3); font-family: var(--font-mono); font-size: 11px; }
  .card strong { color: var(--fg-1); font-size: 14.5px; line-height: 1.45; font-weight: 500; }
  .tags { display: flex; gap: 6px; flex-wrap: wrap; }
  .tags span { color: var(--violet-200); font-family: var(--font-mono); font-size: 10px; letter-spacing: 0.06em; border: 1px solid var(--border-1); border-radius: 999px; padding: 1px 8px; }
  .card small { color: var(--fg-3); font-family: var(--font-mono); font-size: 10.5px; }

  .runs { list-style: none; margin: 0; padding: 0; display: grid; gap: 6px; }
  .run a { display: flex; align-items: center; gap: 12px; padding: 9px 14px; background: var(--bg-2); border: 1px solid var(--border-1); border-radius: 8px; text-decoration: none; }
  .run a:hover { border-color: var(--border-2); }
  .run__dot { width: 8px; height: 8px; border-radius: 999px; flex: none; }
  .run__sha { color: var(--fg-1); font-family: var(--font-mono); font-size: 12px; }
  .run__status { color: var(--fg-2); font-size: 13px; flex: 1; }
  .run small { color: var(--fg-3); font-family: var(--font-mono); font-size: 10.5px; white-space: nowrap; }

  .empty { color: var(--fg-3); font-style: italic; margin: 0; padding: 14px 16px; border: 1px dashed var(--border-1); border-radius: 8px; line-height: 1.6; }
  .empty code { color: var(--signal-error); font-family: var(--font-mono); font-size: 11.5px; font-style: normal; }

  /* gate standard */
  .ch--standard { border-top: 1px solid var(--border-1); }
  .standard { list-style: none; margin: 18px 0 0; padding: 0; display: grid; gap: 10px; }
  .standard li { position: relative; padding: 14px 16px 14px 44px; background: var(--bg-2); border: 1px solid var(--border-1); border-radius: 9px; color: var(--fg-1); font-size: 15px; line-height: 1.55; }
  .standard li::before { content: '✓'; position: absolute; left: 16px; top: 13px; color: var(--ember-300); font-family: var(--font-mono); }

  /* closer */
  .closer { padding: 56px 24px 104px; border-top: 1px solid var(--border-1); }
  .closer__inner { max-width: 760px; margin: 0 auto; }
  .closer h2 { font-size: clamp(26px, 4vw, 38px); margin: 8px 0 12px; }
  .closer p { color: var(--fg-2); font-size: 16px; line-height: 1.65; max-width: 60ch; margin: 0 0 22px; }
  .closer__cta { display: grid; grid-template-columns: 1fr 1fr; gap: 10px; }
  @media (max-width: 640px) { .closer__cta { grid-template-columns: 1fr; } }
  .cta { display: grid; gap: 4px; padding: 16px 18px; background: var(--bg-2); border: 1px solid var(--border-1); border-radius: 10px; color: inherit; text-decoration: none; transition: border-color var(--dur-fast) var(--ease-standard), transform var(--dur-fast) var(--ease-standard); }
  .cta:hover { border-color: var(--border-2); transform: translateY(-1px); }
  .cta--primary { border-color: rgba(109,211,166,0.45); background: rgba(109,211,166,0.05); }
  .cta strong { color: var(--fg-1); font-family: var(--font-display); font-size: 17px; font-weight: 500; }
  .cta span { color: var(--fg-2); font-size: 13px; line-height: 1.45; }
</style>
