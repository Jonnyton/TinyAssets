<!--
  /fine-print — "Vital signs & fine print": the ops room. Field Notes rebuild.

  This is the instrument panel. Tiny's pulse up top, then plain-words
  explanations of exactly how each reading is measured (this page is the
  canonical target the VitalSigns "how this is measured" tick points at →
  section id="vitals"), the engine's own release receipt read live, the
  public watchdogs that watch it, and the honest fine print.

  Honesty rails: nothing baked is shown as live. The release receipt is a
  live read with explicit reading / failure / empty states. Every external
  link goes somewhere real. No money-as-investment language. Loop awake /
  asleep is never hardcoded — VitalSigns derives it from a live read.
-->
<script lang="ts">
  import { onMount } from 'svelte';
  import VitalSigns from '$lib/components/VitalSigns.svelte';
  import Tick from '$lib/components/Tick.svelte';
  import Term from '$lib/components/Term.svelte';
  import baked from '$lib/content/mcp-snapshot.json';

  const GH_REPO = 'https://github.com/Jonnyton/Workflow';
  const GH_ACTIONS = 'https://github.com/Jonnyton/Workflow/actions';
  const MCP_BARE = 'tinyassets.io/mcp';

  // First-paint context from the freshly-baked snapshot, ONLY ever shown
  // with its own fetched-at stamp so it can't be mistaken for a live read.
  const bakedFetchedAt: string = (baked as any).fetched_at ?? '';

  function rel(s?: string | null): string {
    if (!s) return 'unknown';
    const ms = Date.parse(s);
    if (Number.isNaN(ms)) return s;
    const diff = Date.now() - ms;
    if (diff < 90_000) return 'just now';
    if (diff < 3_600_000) return `${Math.floor(diff / 60_000)}m ago`;
    if (diff < 86_400_000) return `${Math.floor(diff / 3_600_000)}h ago`;
    return `${Math.floor(diff / 86_400_000)}d ago`;
  }

  function stamp(s?: string | null): string {
    if (!s) return '';
    const ms = Date.parse(s);
    if (Number.isNaN(ms)) return s;
    return new Date(ms).toLocaleString(undefined, {
      day: 'numeric', month: 'short', year: 'numeric', hour: '2-digit', minute: '2-digit'
    });
  }

  // ── Release receipt — read live from the engine's own get_status. ──
  // The engine reports about itself: which commit is deployed, when, which
  // image, and whether its release canary bundle passed. Never baked.
  const MCP_PATH = import.meta.env.DEV ? '/mcp-live' : '/mcp';
  let rcState = $state<'reading' | 'ok' | 'empty' | 'error'>('reading');
  let rcError = $state<string | null>(null);
  let rcFetchedAt = $state<string | null>(null);
  let release = $state<Record<string, any> | null>(null);

  // The engine's get_status payload uses snake_case; we read the fields the
  // receipt cares about with small fallbacks, and only render a link when a
  // real URL is present.
  function pick(obj: Record<string, any> | null, ...keys: string[]): any {
    if (!obj) return undefined;
    for (const k of keys) if (obj[k] !== undefined && obj[k] !== null && obj[k] !== '') return obj[k];
    return undefined;
  }

  let sessionId: string | null = null;
  async function mcpRpc(method: string, params: any, id: number): Promise<any> {
    const headers: Record<string, string> = {
      'Content-Type': 'application/json',
      Accept: 'application/json, text/event-stream'
    };
    if (sessionId) headers['Mcp-Session-Id'] = sessionId;
    const res = await fetch(MCP_PATH, {
      method: 'POST',
      headers,
      body: JSON.stringify({ jsonrpc: '2.0', id, method, params }),
      credentials: 'omit'
    });
    const sid = res.headers.get('Mcp-Session-Id');
    if (sid && !sessionId) sessionId = sid;
    if (!res.ok) throw new Error(`MCP HTTP ${res.status}: ${res.statusText}`);
    let text = await res.text();
    if ((res.headers.get('Content-Type') ?? '').includes('text/event-stream')) {
      const line = text.split('\n').find((l) => l.startsWith('data:'));
      if (!line) throw new Error('SSE response missing data line');
      text = line.replace(/^data:\s*/, '');
    }
    const json = JSON.parse(text);
    if (json.error) throw new Error(`MCP error ${json.error.code}: ${json.error.message}`);
    return json.result;
  }

  async function readReceipt() {
    rcState = 'reading';
    rcError = null;
    sessionId = null;
    try {
      await mcpRpc('initialize', {
        protocolVersion: '2025-06-18',
        clientInfo: { name: 'tinyassets-fine-print', version: '0.1.0' },
        capabilities: {}
      }, 1);
      const result = await mcpRpc('tools/call', { name: 'get_status', arguments: {} }, 2);
      const payload =
        result?.structuredContent && typeof result.structuredContent === 'object'
          ? result.structuredContent
          : (() => {
              const t = result?.content?.find((c: any) => c?.type === 'text');
              if (!t?.text) return null;
              try { return JSON.parse(t.text); } catch { return null; }
            })();
      const rel = payload?.release_state ?? null;
      rcFetchedAt = new Date().toISOString();
      if (rel && typeof rel === 'object' && Object.keys(rel).length) {
        release = rel;
        rcState = 'ok';
      } else {
        release = null;
        rcState = 'empty';
      }
    } catch (err: any) {
      rcError = err?.message ?? String(err);
      rcState = 'error';
      release = null;
    }
  }

  onMount(() => { void readReceipt(); });

  // Receipt rows — derived from the live payload, links only when real.
  let gitSha = $derived(pick(release, 'git_sha', 'gitSha', 'sha', 'commit'));
  let deployedAt = $derived(pick(release, 'deployed_at', 'deployedAt'));
  let imageTag = $derived(pick(release, 'image_tag', 'imageTag', 'image', 'tag'));
  let canaryStatus = $derived(pick(release, 'canary_bundle_status', 'canaryBundleStatus', 'canary_status'));
  let buildRunUrl = $derived(pick(release, 'build_run_url', 'buildRunUrl', 'build_url'));
  let deployRunUrl = $derived(pick(release, 'deploy_run_url', 'deployRunUrl', 'deploy_url'));

  // Public watchdogs — GitHub Actions that watch the system. Linked to the
  // real Actions tab; neutral one-liners, no claimed pass/fail state here
  // (the Actions tab is the live truth, and the receipt above carries the
  // engine's own canary verdict).
  const WATCHDOGS = [
    {
      file: 'uptime-canary.yml',
      what: 'Probes the public MCP endpoint on a schedule and after any DNS, tunnel, or Worker change — the out-of-band check that catches a silently-dropped route.'
    },
    {
      file: 'community-loop-watch.yml',
      what: 'Watches the self-patch loop end to end — intake, investigation, gate, release — and opens an alarm when a stage stalls.'
    }
  ];
</script>

<svelte:head>
  <title>Vital signs &amp; fine print — Tiny</title>
  <meta
    name="description"
    content="The instrument panel: Tiny's live pulse, plain-words explanations of how each reading is measured, the engine's own release receipt, the public watchdogs, and the honest fine print."
  />
</svelte:head>

<!-- 1 · Hero — the instrument panel ────────────────────────────────────── -->
<section class="cover" aria-labelledby="cover-title">
  <div class="container cover__inner">
    <p class="eyebrow">field notes · the ops room</p>
    <h1 id="cover-title" class="cover__title">The instrument panel.</h1>
    <p class="cover__lede">
      Every other page on this site makes a claim. This one explains how the
      claims are measured, what the engine reports about itself, and who
      watches it when no human is looking. No marketing here — just the
      readings and the fine print.
    </p>
    <p class="cover__caption voice">
      — if I'm asleep, this page says so before I do.
    </p>
    <VitalSigns variant="hero" />
    <p class="cover__stamp ev">
      first paint seeded from snapshot {stamp(bakedFetchedAt)} · every reading
      above is upgraded by a live read on load and carries its own stamp
    </p>
  </div>
</section>

<!-- 2 · How the pulse is measured ───────────────────────────────────────── -->
<section id="vitals" class="ch" aria-labelledby="vitals-title">
  <div class="container ch__inner">
    <p class="eyebrow">entry one · how the pulse is measured</p>
    <h2 id="vitals-title">Four readings, in plain words.</h2>
    <p class="voice vitals__lede">
      — the pulse strip up top is four separate facts, never collapsed into
      one. Here's exactly what each one means, so a green dot can never bluff
      you.
    </p>

    <dl class="measures">
      <div class="measure">
        <dt><span class="dot live" aria-hidden="true"></span> server live</dt>
        <dd>
          The <Term def="MCP — the Model Context Protocol. The open standard chatbots use to add outside tools. Tiny is one such tool.">MCP</Term>
          endpoint at <code>{MCP_BARE}</code> answered <em>this browser's</em>
          call, just now. It's reachability measured from where you're sitting —
          not a status page someone typed by hand. If the call fails, the strip
          says unreachable and shows the real error.
        </dd>
      </div>
      <div class="measure">
        <dt><span class="dot idle" aria-hidden="true"></span> loop awake</dt>
        <dd>
          A public universe shows activity within the last hour, <em>or</em> a
          run is executing right now. If neither is true, the loop is asleep —
          and the strip says asleep, plainly. This state is read live every
          time; it is never hardcoded, because the site got that wrong once and
          left a flat line showing as a pulse.
        </dd>
      </div>
      <div class="measure">
        <dt><span class="dot" aria-hidden="true"></span> lifetime runs</dt>
        <dd>
          The engine's queue keeps running counters of work it has taken
          through: <em>succeeded</em>, <em>failed</em>, and <em>pending</em>.
          The strip reports those numbers as the engine reports them — failures
          included, because a counter that only counts wins isn't a counter.
        </dd>
      </div>
      <div class="measure">
        <dt><span class="dot" aria-hidden="true"></span> deployed</dt>
        <dd>
          The engine's own release receipt: the git commit it's running and the
          time it says it deployed that commit. It's the engine describing
          itself, not the website guessing. The full receipt — image, canary
          verdict, and the GitHub Actions runs that built and shipped it — is
          read live just below.
        </dd>
      </div>
    </dl>
  </div>
</section>

<!-- 3 · Release receipt ─────────────────────────────────────────────────── -->
<section class="ch ch--receipt" aria-labelledby="receipt-title">
  <div class="container ch__inner">
    <p class="eyebrow">entry two · the engine's own receipt</p>
    <h2 id="receipt-title">What's actually deployed, by its own account.</h2>
    <p class="receipt__lede">
      Read live from <code>get_status</code> when you opened this page. These
      are the engine's words about its own release — not a value typed into
      this site.
    </p>

    <div class="receipt" aria-live="polite" data-state={rcState}>
      {#if rcState === 'reading'}
        <p class="receipt__msg ev"><span class="dot idle" aria-hidden="true"></span> reading the release receipt from <code>{MCP_BARE}</code>…</p>
      {:else if rcState === 'error'}
        <p class="receipt__msg ev"><span class="dot error" aria-hidden="true"></span> couldn't read the receipt — this is a true reading.</p>
        <p class="receipt__err ev">{rcError}</p>
        <button class="receipt__refresh" onclick={() => void readReceipt()}>Refresh MCP</button>
      {:else if rcState === 'empty'}
        <p class="receipt__msg ev"><span class="dot idle" aria-hidden="true"></span> the engine answered, but reported no release_state in this read.</p>
        <p class="receipt__note">That's an honest gap, not a deployment claim. Read again, or check the build &amp; deploy runs on GitHub Actions directly.</p>
        <div class="receipt__links">
          <a href={GH_ACTIONS} target="_blank" rel="noreferrer">GitHub Actions ↗</a>
          <button class="receipt__refresh" onclick={() => void readReceipt()}>Refresh MCP</button>
        </div>
      {:else}
        <table class="rc-table">
          <tbody>
            <tr>
              <th scope="row">git sha</th>
              <td>{gitSha ?? '—'}</td>
            </tr>
            <tr>
              <th scope="row">deployed at</th>
              <td>{deployedAt ? `${stamp(deployedAt)} · ${rel(deployedAt)}` : '—'}</td>
            </tr>
            <tr>
              <th scope="row">image tag</th>
              <td>{imageTag ?? '—'}</td>
            </tr>
            <tr>
              <th scope="row">canary bundle</th>
              <td>{canaryStatus ?? '—'}</td>
            </tr>
            <tr>
              <th scope="row">build run</th>
              <td>
                {#if buildRunUrl}
                  <a href={buildRunUrl} target="_blank" rel="noreferrer">build workflow run ↗</a>
                {:else}
                  <span class="rc-none">not in this read — <a href={GH_ACTIONS} target="_blank" rel="noreferrer">all Actions ↗</a></span>
                {/if}
              </td>
            </tr>
            <tr>
              <th scope="row">deploy run</th>
              <td>
                {#if deployRunUrl}
                  <a href={deployRunUrl} target="_blank" rel="noreferrer">deploy workflow run ↗</a>
                {:else}
                  <span class="rc-none">not in this read — <a href={GH_ACTIONS} target="_blank" rel="noreferrer">all Actions ↗</a></span>
                {/if}
              </td>
            </tr>
          </tbody>
        </table>
        <p class="receipt__stamp ev">
          read live {rel(rcFetchedAt)} ·
          <button class="receipt__refresh receipt__refresh--inline" onclick={() => void readReceipt()}>Refresh MCP</button>
        </p>
      {/if}
    </div>
  </div>
</section>

<!-- 4 · Public watchdogs ────────────────────────────────────────────────── -->
<section class="ch ch--watch" aria-labelledby="watch-title">
  <div class="container ch__inner">
    <p class="eyebrow">entry three · the public watchdogs</p>
    <h2 id="watch-title">Who watches it when no one's looking.</h2>
    <p class="watch__lede">
      Two GitHub Actions watch the live system on a schedule. They're public —
      their run history, pass and fail, is on the Actions tab anyone can open.
    </p>
    <ul class="watch">
      {#each WATCHDOGS as w (w.file)}
        <li class="watch__item">
          <code class="watch__file">{w.file}</code>
          <p class="watch__what">{w.what}</p>
        </li>
      {/each}
    </ul>
    <p class="watch__foot">
      <a href={GH_ACTIONS} target="_blank" rel="noreferrer">Open the Actions tab on GitHub ↗</a>
      — the live run history is the truth, not this page.
    </p>
  </div>
</section>

<!-- 5 · The fine print ──────────────────────────────────────────────────── -->
<section class="ch ch--legal" aria-labelledby="legal-title">
  <div class="container ch__inner">
    <p class="eyebrow">entry four · the fine print</p>
    <h2 id="legal-title">The part that has to be exact.</h2>
    <p class="legal__money voice">
      On money: any value or credit moving through Tiny today settles on a
      <em>test rail</em> — there's no payment method to ask for and nothing to
      buy. <strong>Nothing on this site is investment advice, and none of it
      represents equity, profit-sharing, or a price prediction.</strong>
    </p>
    <ul class="legal">
      <li class="legal__item">
        <a class="legal__link" href="/legal">Terms, token disclosures, risk &amp; DMCA →</a>
        <p class="legal__note">The full legal page: terms of use, token / currency disclosures, the risk statement, and the DMCA / takedown path.</p>
      </li>
    </ul>
  </div>
</section>

<!-- 6 · Close ───────────────────────────────────────────────────────────── -->
<section class="ch ch--close" aria-labelledby="close-title">
  <div class="container ch__inner">
    <h2 id="close-title">Seen the gauges. Now watch the work.</h2>
    <nav class="close__cards">
      <a class="close__card" href="/loop">
        <span class="close__k eyebrow">the patch loop</span>
        <strong>Watch how it maintains itself →</strong>
        <span class="close__sub">friction becomes a patch request, a real PR, a release — live runs and gates.</span>
      </a>
      <a class="close__card" href="/commons">
        <span class="close__k eyebrow">the public commons</span>
        <strong>Browse the brain — and the glossary →</strong>
        <span class="close__sub">every term of art, plus the searchable wiki it all reads from.</span>
      </a>
    </nav>
  </div>
</section>

<style>
  .container { max-width: 1160px; margin: 0 auto; padding-inline: clamp(18px, 4vw, 32px); }

  /* ── Cover ── */
  .cover { padding: clamp(48px, 8vw, 92px) 0 clamp(36px, 6vw, 64px); border-bottom: 1px solid var(--border-1); }
  .cover__inner { max-width: 820px; display: grid; gap: 0; }
  .cover__title {
    font-size: clamp(44px, 7vw, 84px);
    font-weight: 400;
    line-height: 1.0;
    letter-spacing: -0.03em;
    margin: 14px 0 18px;
  }
  .cover__lede { font-size: clamp(16px, 1.7vw, 18px); line-height: 1.62; color: var(--fg-2); max-width: 60ch; margin: 0 0 16px; }
  .cover__caption { font-size: 15px; font-style: italic; color: var(--fg-3); margin: 0 0 24px; max-width: 48ch; }
  .cover__stamp { display: block; margin-top: 14px; font-size: 11px; color: var(--fg-3); max-width: 60ch; line-height: 1.5; }

  /* ── Shared section chrome ── */
  .ch { padding: clamp(48px, 7vw, 84px) 0; border-bottom: 1px solid var(--border-1); }
  .ch__inner { max-width: 760px; }
  .ch h2 {
    font-size: clamp(28px, 4.4vw, 44px);
    font-weight: 500;
    line-height: 1.06;
    letter-spacing: -0.02em;
    margin: 12px 0 16px;
  }
  .ch .eyebrow { display: block; }
  .ch code {
    background: var(--paper-200);
    border: 1px solid var(--border-1);
    border-radius: var(--radius-xs);
    color: var(--ink-text-700);
    font-family: var(--font-mono);
    font-size: 0.85em;
    padding: 1px 5px;
  }

  /* ── Measures (how the pulse is measured) ── */
  .vitals__lede { margin: 0 0 8px; color: var(--fg-2); }
  .measures { display: grid; gap: 14px; margin: 26px 0 0; }
  .measure {
    display: grid; gap: 6px;
    padding: 18px 20px;
    background: var(--bg-2);
    border: 1px solid var(--border-1);
    border-radius: var(--radius-lg);
  }
  .measure dt {
    display: inline-flex; align-items: center; gap: 9px;
    font-family: var(--font-sans);
    font-size: 14px; font-weight: 600;
    color: var(--fg-1);
    letter-spacing: 0.01em;
  }
  .measure dd {
    margin: 0;
    font-size: 14px; line-height: 1.62;
    color: var(--fg-2);
    max-width: 66ch;
  }
  .measure dd em { color: var(--fg-1); font-style: normal; font-weight: 600; }
  .measure dd code { font-size: 12.5px; }

  /* ── Release receipt ── */
  .ch--receipt { background: var(--bg-1); }
  .receipt__lede { font-size: 15px; line-height: 1.6; color: var(--fg-2); max-width: 64ch; margin: 0 0 18px; }
  .receipt {
    padding: 18px 20px;
    background: var(--bg-2);
    border: 1px solid var(--border-1);
    border-radius: var(--radius-lg);
    display: grid; gap: 12px;
  }
  .receipt[data-state="error"] { border-color: rgba(182, 39, 68, 0.4); }
  .receipt__msg { display: inline-flex; align-items: center; gap: 9px; font-size: 12.5px; color: var(--fg-2); margin: 0; }
  .receipt__msg .dot { align-self: center; }
  .receipt__msg code { font-size: 0.92em; }
  .receipt__err {
    color: var(--signal-error); font-size: 11.5px; margin: 0;
    overflow-wrap: anywhere; padding-left: 16px;
  }
  .receipt__note { font-size: 13px; line-height: 1.55; color: var(--fg-3); margin: 0; max-width: 64ch; }
  .receipt__links { display: flex; align-items: center; gap: 14px; flex-wrap: wrap; }
  .rc-table { width: 100%; border-collapse: collapse; }
  .rc-table tr { border-top: 1px solid var(--border-1); }
  .rc-table tr:first-child { border-top: none; }
  .rc-table th {
    text-align: left; vertical-align: top;
    width: 130px;
    padding: 10px 14px 10px 0;
    font-family: var(--font-mono);
    font-size: 10.5px; font-weight: 500;
    letter-spacing: 0.1em; text-transform: uppercase;
    color: var(--fg-3);
    white-space: nowrap;
  }
  .rc-table td {
    padding: 10px 0;
    font-family: var(--font-mono);
    font-size: 13px;
    color: var(--fg-1);
    overflow-wrap: anywhere;
  }
  .rc-table a { color: var(--live-700); border-bottom: 1px dashed rgba(31, 138, 92, 0.5); }
  .rc-table a:hover { color: var(--live-600); text-decoration: none; }
  .rc-none { color: var(--fg-3); font-size: 11.5px; }
  .rc-none a { font-size: inherit; }
  .receipt__stamp { display: inline-flex; align-items: center; gap: 8px; flex-wrap: wrap; font-size: 11px; color: var(--fg-3); margin: 0; }
  .receipt__refresh {
    background: transparent; border: 1px solid var(--border-2); border-radius: var(--radius-pill);
    color: var(--live-700); cursor: pointer;
    font-family: var(--font-mono); font-size: 10px; letter-spacing: 0.08em; text-transform: uppercase;
    padding: 4px 12px;
    transition: border-color var(--dur-fast) var(--ease-standard), background var(--dur-fast) var(--ease-standard);
  }
  .receipt__refresh--inline { padding: 3px 10px; }
  .receipt__refresh:hover { border-color: var(--live-600); background: var(--live-100); }

  /* ── Public watchdogs ── */
  .watch__lede { font-size: 15px; line-height: 1.6; color: var(--fg-2); max-width: 64ch; margin: 0 0 8px; }
  .watch { list-style: none; margin: 24px 0 0; padding: 0; display: grid; gap: 12px; }
  .watch__item {
    display: grid; gap: 7px;
    padding: 16px 18px;
    background: var(--bg-2);
    border: 1px solid var(--border-1);
    border-radius: var(--radius-md);
  }
  .watch__file {
    font-family: var(--font-mono); font-size: 12.5px;
    color: var(--violet-200); width: fit-content;
    background: var(--bg-inset); border: 1px solid var(--border-1);
    border-radius: var(--radius-xs); padding: 2px 8px;
  }
  .watch__what { font-size: 13.5px; line-height: 1.55; color: var(--fg-2); margin: 0; max-width: 70ch; }
  .watch__foot { font-size: 13.5px; line-height: 1.6; color: var(--fg-3); margin: 20px 0 0; max-width: 66ch; }

  /* ── The fine print ── */
  .legal__money {
    font-size: 16px; line-height: 1.62; color: var(--fg-1);
    margin: 0 0 22px; max-width: 64ch;
  }
  .legal__money em { color: var(--ember-700); font-style: italic; }
  .legal__money strong { color: var(--fg-1); font-weight: 600; }
  .legal { list-style: none; margin: 0; padding: 0; display: grid; gap: 12px; }
  .legal__item {
    display: grid; gap: 6px;
    padding: 18px 20px;
    background: var(--bg-2);
    border: 1px solid var(--border-1);
    border-radius: var(--radius-lg);
  }
  .legal__link { font-family: var(--font-display); font-size: 18px; font-weight: 500; color: var(--fg-1); width: fit-content; }
  .legal__link:hover { color: var(--ember-700); text-decoration: none; }
  .legal__note { font-size: 13.5px; line-height: 1.55; color: var(--fg-3); margin: 0; max-width: 66ch; }

  /* ── Close ── */
  .ch--close { border-bottom: none; padding-bottom: clamp(72px, 10vw, 120px); }
  .close__cards { display: grid; grid-template-columns: repeat(2, 1fr); gap: 16px; margin-top: 22px; }
  @media (max-width: 760px) { .close__cards { grid-template-columns: 1fr; } }
  .close__card {
    display: grid; gap: 6px;
    padding: 24px 26px;
    background: var(--bg-2);
    border: 1px solid var(--border-2);
    border-radius: var(--radius-lg);
    text-decoration: none;
    color: inherit;
    transition: border-color var(--dur-fast) var(--ease-standard), box-shadow var(--dur-fast) var(--ease-standard);
  }
  .close__card:hover { border-color: var(--ink-text-900); box-shadow: var(--shadow-md); text-decoration: none; }
  .close__k { display: block; }
  .close__card strong { font-family: var(--font-display); font-size: clamp(20px, 2.6vw, 26px); font-weight: 500; letter-spacing: -0.015em; line-height: 1.14; color: var(--fg-1); }
  .close__sub { font-size: 13.5px; color: var(--fg-2); }
</style>
