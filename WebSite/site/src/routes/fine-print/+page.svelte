<!--
  /fine-print — "Vital signs & fine print": the ops room. Field Notes rebuild.

  This is the instrument panel. Tiny's pulse up top, then plain-words
  explanations of exactly how each reading is measured (this page is the
  canonical target the VitalSigns "how this is measured" tick points at →
  section id="vitals"), an explicit unavailable public release receipt, the
  public uptime evidence, and the honest fine print.

  Honesty rails: nothing baked is shown as live. Operator status is not
  downloaded by this public page. Every external
  link goes somewhere real. No money-as-investment language. Generic workflow
  activity is never hardcoded — VitalSigns derives it only from
  visibility-filtered public-universe timestamps.
-->
<script lang="ts">
  import VitalSigns from '$lib/components/VitalSigns.svelte';
  import Tick from '$lib/components/Tick.svelte';
  import Term from '$lib/components/Term.svelte';
  import baked from '$lib/content/mcp-snapshot.json';

  const GH_REPO = 'https://github.com/Jonnyton/TinyAssets';
  const GH_ACTIONS = 'https://github.com/Jonnyton/TinyAssets/actions';
  const MCP_BARE = 'tinyassets.io/mcp';

  // First-paint context from the freshly-baked snapshot, ONLY ever shown
  // with its own fetched-at stamp so it can't be mistaken for a live read.
  const bakedFetchedAt: string = (baked as any).fetched_at ?? '';

  function stamp(s?: string | null): string {
    if (!s) return '';
    const ms = Date.parse(s);
    if (Number.isNaN(ms)) return s;
    return new Date(ms).toLocaleString(undefined, {
      day: 'numeric', month: 'short', year: 'numeric', hour: '2-digit', minute: '2-digit'
    });
  }

  // Public uptime evidence — GitHub Actions that watch platform availability. Linked to the
  // real Actions tab; neutral one-liners, no claimed pass/fail state here
  // (the Actions tab is the source for that workflow history).
  const UPTIME_CHECKS = [
    {
      file: 'uptime-canary.yml',
      what: 'Probes the public MCP endpoint on a schedule and after any DNS, tunnel, or Worker change — platform reachability evidence, separate from user-workflow activity.'
    }
  ];
</script>

<svelte:head>
  <title>Vital signs &amp; fine print — Tiny</title>
  <meta
    name="description"
    content="The instrument panel: public reachability and timestamp signals, source limits, explicit release-receipt unavailability, uptime evidence, and the honest fine print."
  />
</svelte:head>

<!-- 1 · Hero — the instrument panel ────────────────────────────────────── -->
<section class="cover" aria-labelledby="cover-title">
  <div class="container cover__inner">
    <p class="eyebrow">field notes · the ops room</p>
    <h1 id="cover-title" class="cover__title">The instrument panel.</h1>
    <p class="cover__lede">
      This page labels how its public operational readings are measured, what
      they omit, and where the linked uptime evidence comes from. No marketing
      here — just bounded readings and the fine print.
    </p>
    <p class="cover__caption voice">
      — when a reading is unavailable, this page says so.
    </p>
    <VitalSigns variant="hero" />
    <p class="cover__stamp ev">
      first paint seeded from snapshot {stamp(bakedFetchedAt)} · reachability
      and public-universe timestamps refresh live; unavailable operator fields
      stay unavailable
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
        <dt><span class="dot idle" aria-hidden="true"></span> workflow activity</dt>
        <dd>
          A visibility-filtered public universe has a recorded activity
          timestamp within the last hour. That is a timestamp signal only: it
          is not run state and cannot prove that anything is executing. If no
          recent timestamp exists, the strip says so plainly.
        </dd>
      </div>
      <div class="measure">
        <dt><span class="dot" aria-hidden="true"></span> lifetime runs</dt>
        <dd>
          Public queue counters are unavailable. This browser does not request
          operator status merely to display lifetime run totals.
        </dd>
      </div>
      <div class="measure">
        <dt><span class="dot" aria-hidden="true"></span> deployed</dt>
        <dd>
          A public release receipt is unavailable. The checked-in site snapshot
          is page provenance, not proof of which engine image is deployed.
        </dd>
      </div>
    </dl>
  </div>
</section>

<!-- 3 · Release receipt ─────────────────────────────────────────────────── -->
<section class="ch ch--receipt" aria-labelledby="receipt-title">
  <div class="container ch__inner">
    <p class="eyebrow">entry two · release provenance</p>
    <h2 id="receipt-title">Public release receipt unavailable.</h2>
    <p class="receipt__lede">
      This browser does not download the operator status payload. The checked-in
      public site snapshot is dated {stamp(bakedFetchedAt)}, but that date is
      not a deployment attestation.
    </p>

    <div class="receipt" aria-live="polite" data-state="unavailable">
      <p class="receipt__msg ev">
        <span class="dot idle" aria-hidden="true"></span>
        release details unavailable on the public website
      </p>
      <p class="receipt__note">
        Build and deploy workflow history remains available from GitHub without
        treating it as an engine-signed release receipt.
      </p>
      <div class="receipt__links">
        <a href={GH_ACTIONS} target="_blank" rel="noreferrer">GitHub Actions ↗</a>
      </div>
    </div>
  </div>
</section>

<!-- 4 · Public uptime evidence ─────────────────────────────────────────── -->
<section class="ch ch--watch" aria-labelledby="watch-title">
  <div class="container ch__inner">
    <p class="eyebrow">entry three · public uptime evidence</p>
    <h2 id="watch-title">Who watches it when no one's looking.</h2>
    <p class="watch__lede">
      A GitHub Action watches platform reachability on a schedule. Its public
      run history is uptime evidence only; it is not evidence that user task
      work is moving.
    </p>
    <ul class="watch">
      {#each UPTIME_CHECKS as w (w.file)}
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
    <h2 id="close-title">Seen the gauges. Now explore the work.</h2>
    <nav class="close__cards">
      <a class="close__card" href="/loop">
        <span class="close__k eyebrow">workflow activity</span>
        <strong>See public user-authored activity →</strong>
        <span class="close__sub">Live connector signals with their source and read time labelled.</span>
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
  .receipt__msg { display: inline-flex; align-items: center; gap: 9px; font-size: 12.5px; color: var(--fg-2); margin: 0; }
  .receipt__msg .dot { align-self: center; }
  .receipt__note { font-size: 13px; line-height: 1.55; color: var(--fg-3); margin: 0; max-width: 64ch; }
  .receipt__links { display: flex; align-items: center; gap: 14px; flex-wrap: wrap; }

  /* ── Public uptime checks ── */
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

  /* ── Release receipt → dark unavailable card. No operator payload is read. ── */
  .receipt { background: var(--panel); border-color: var(--panel-line); }
  .receipt__msg { color: var(--on-panel-soft); }
  .receipt__note { color: var(--on-panel-soft); }
  .receipt__links a { color: var(--ember-300); }
</style>
