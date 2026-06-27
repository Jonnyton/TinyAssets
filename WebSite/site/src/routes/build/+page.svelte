<!--
  /build — the contributor page. "Field Notes" rebuild, 2026-06-09.
  Canonical replacement for /contribute (which becomes an alias later).

  Two doors into building Tiny: through a chatbot (no clone), or through
  the repo (clone the engine). Both end in the same loop — evidence gates,
  cross-family review, a human key. Honesty rails: live GitHub pulse is
  fetched client-side with a read-stamp, the unauthenticated rate-limit
  failure is named plainly, no income promises near "what contribution
  earns", every link goes somewhere real.
-->
<script lang="ts">
  import { onMount } from 'svelte';
  import { refreshRepoSnapshot, type RepoSnapshot } from '$lib/live/project';
  import Term from '$lib/components/Term.svelte';
  import Tick from '$lib/components/Tick.svelte';

  const REPO_URL = 'https://github.com/Jonnyton/TinyAssets';

  // Live repo pulse — fetched, never baked. Until the read lands the strip
  // says it's reading; afterwards every value carries its read-stamp.
  let repo = $state<RepoSnapshot | null>(null);
  let repoErr = $state<string | null>(null);
  let reading = $state(false);
  async function refreshRepo() {
    reading = true;
    try {
      repo = await refreshRepoSnapshot();
      repoErr = null;
    } catch (e: any) {
      repoErr = e?.message ?? String(e);
    } finally {
      reading = false;
    }
  }
  onMount(() => { void refreshRepo(); });

  function rel(s?: string | null): string {
    if (!s) return '';
    const ms = Date.parse(s);
    if (Number.isNaN(ms)) return s;
    const diff = Date.now() - ms;
    if (diff < 90_000) return 'just now';
    if (diff < 3_600_000) return `${Math.floor(diff / 60_000)}m ago`;
    if (diff < 86_400_000) return `${Math.floor(diff / 3_600_000)}h ago`;
    return `${Math.floor(diff / 86_400_000)}d ago`;
  }

  // True when the GitHub API likely rate-limited an unauthenticated read.
  const rateLimited = $derived(
    !!repoErr && /\b(403|429|rate)\b/i.test(repoErr)
  );

  // Door-two repo steps. Each links to a real file/page on GitHub.
  const REPO_STEPS = [
    {
      cmd: 'git clone https://github.com/Jonnyton/TinyAssets',
      note: 'Clone the platform repo from the canonical TinyAssets GitHub path.',
      href: REPO_URL,
      label: 'TinyAssets on GitHub'
    },
    {
      cmd: 'pip install -e .[dev]',
      note: 'Editable install with the dev extras (Python 3.11+).',
      href: `${REPO_URL}/blob/main/pyproject.toml`,
      label: 'pyproject.toml'
    },
    {
      cmd: 'pytest · ruff check',
      note: 'Both green before every commit. Every module has tests; nodes never crash.',
      href: `${REPO_URL}/tree/main/tests`,
      label: 'tests/'
    },
    {
      cmd: 'read PLAN.md · CONTRIBUTING.md',
      note: 'Architecture and how the system thinks (PLAN.md); how to land work (CONTRIBUTING.md).',
      href: `${REPO_URL}/blob/main/PLAN.md`,
      label: 'PLAN.md'
    }
  ];
</script>

<svelte:head>
  <title>Build me — two doors into contributing to Tiny</title>
  <meta
    name="description"
    content="Two doors into building TinyAssets: improve Tiny through your chatbot without ever cloning code, or clone the TinyAssets GitHub repository and work on it directly. Both end in the same loop — evidence gates, cross-family review, a human merge key."
  />
</svelte:head>

<!-- 1 · Hero ──────────────────────────────────────────────────────────── -->
<section class="cover" aria-labelledby="cover-title">
  <div class="container ch__inner">
    <p class="eyebrow">field notes · how I get rebuilt</p>
    <h1 id="cover-title" class="cover__title">Two doors into building me.</h1>
    <p class="voice cover__lede">
      You can improve me without ever cloning a line of code — just talk to me
      through your chatbot and describe what's rough. Or you can go straight at
      the engine through the repository, with the tests and the architecture in
      front of you. Both doors open onto the same room: a
      <Term def="The self-patching cycle: a request becomes an investigation, runs through automated checks, and only ships after review.">loop</Term>
      with evidence gates, a
      <Term def="A second AI from a different model family re-checks the work, so no one model both writes and approves a change.">cross-family review</Term>,
      and a <em>human key</em> that has to turn before anything merges.
    </p>
    <p class="cover__naming">
      The platform is <strong>TinyAssets</strong>; the being is <strong>Tiny</strong>.
      Contributing to either is contributing to both.
    </p>
  </div>
</section>

<!-- 2 · Door one — through your chatbot ───────────────────────────────── -->
<section class="ch ch--door" aria-labelledby="door1-title">
  <div class="container">
    <p class="eyebrow">door one · no clone required</p>
    <h2 id="door1-title">Build me through your chatbot.</h2>
    <p class="voice door__lede">
      If you can hold a conversation, you can file work that lands in my
      engine. You never touch a terminal.
    </p>
    <ol class="steps">
      <li class="step">
        <span class="step__n">01</span>
        <div class="step__body">
          <h3 class="step__h">Connect</h3>
          <p class="step__p">Paste my URL into Claude, ChatGPT, or any MCP-capable assistant.</p>
          <a class="step__cta" href="/start">how to connect →</a>
        </div>
      </li>
      <li class="step">
        <span class="step__n">02</span>
        <div class="step__body">
          <h3 class="step__h">Hit a rough edge — or have an idea</h3>
          <p class="step__p">A confusing response, a missing capability, a sharper way to do something. Friction and ideas count equally.</p>
        </div>
      </li>
      <li class="step">
        <span class="step__n">03</span>
        <div class="step__body">
          <h3 class="step__h">Say it out loud</h3>
          <p class="step__p">Tell your chatbot: <code>file a patch request about …</code> — describe the rough edge in plain words. It's filed against my public commons.</p>
        </div>
      </li>
      <li class="step">
        <span class="step__n">04</span>
        <div class="step__body">
          <h3 class="step__h">It enters the loop</h3>
          <p class="step__p">Your request becomes an investigation, runs through evidence gates, and can surface as a real GitHub PR.</p>
          <a class="step__cta" href="/loop">watch the loop →</a>
        </div>
      </li>
      <li class="step">
        <span class="step__n">05</span>
        <div class="step__body">
          <h3 class="step__h">Watch it become a change</h3>
          <p class="step__p">From investigation to pull request to release, the whole trail is public — successes and failures alike.</p>
        </div>
      </li>
    </ol>
    <p class="door__note voice">
      One honest caveat: <em>a merge always waits on a human key.</em> No
      change ships on AI momentum alone. That's a feature, not friction — it's
      why you can trust what lands.
    </p>
  </div>
</section>

<!-- 3 · Door two — through the repo ───────────────────────────────────── -->
<section class="ch ch--door" aria-labelledby="door2-title">
  <div class="container">
    <p class="eyebrow">door two · clone the engine</p>
    <h2 id="door2-title">Build me through the repository.</h2>
    <p class="voice door__lede">
      Prefer to work in code directly? The engine is open source. Clone it,
      install it, and the same gates apply to your branch as to mine.
    </p>
    <ol class="repo-steps">
      {#each REPO_STEPS as s (s.cmd)}
        <li class="repo-step">
          <code class="repo-step__cmd">{s.cmd}</code>
          <p class="repo-step__note">{s.note}</p>
          <Tick href={s.href} label={s.label} external />
        </li>
      {/each}
    </ol>
    <p class="door__note">
      Read <a href={`${REPO_URL}/blob/main/PLAN.md`} target="_blank" rel="noreferrer">PLAN.md</a>
      for the architecture and
      <a href={`${REPO_URL}/blob/main/CONTRIBUTING.md`} target="_blank" rel="noreferrer">CONTRIBUTING.md</a>
      for how work lands. When you're ready, open a pull request against
      <a href={REPO_URL} target="_blank" rel="noreferrer">TinyAssets on GitHub ↗</a>.
    </p>
  </div>
</section>

<!-- 4 · Live repo pulse ───────────────────────────────────────────────── -->
<section class="ch ch--pulse" aria-labelledby="pulse-title">
  <div class="container ch__inner">
    <p class="eyebrow">live reading · the repository, right now</p>
    <h2 id="pulse-title">The engine, read live from GitHub.</h2>
    <div class="pulse" aria-live="polite">
      {#if reading && !repo && !repoErr}
        <p class="pulse__state ev">reading the repository…</p>
      {:else if repoErr}
        <p class="pulse__state pulse__state--err ev">
          {#if rateLimited}
            GitHub's API rate-limited this read. This page calls GitHub
            unauthenticated from your browser, so anonymous reads can be
            throttled — that's the honest reason, not a server failure.
          {:else}
            live read failed — {repoErr}
          {/if}
        </p>
        <button class="pulse__refresh" onclick={refreshRepo} disabled={reading}>{reading ? 'reading…' : 'Refresh GitHub'}</button>
      {:else if repo}
        <dl class="pulse__grid">
          <div class="pulse__cell">
            <dt class="pulse__k">default branch</dt>
            <dd class="pulse__v ev">{repo.repo.default_branch ?? repo.repo.main ?? '—'}</dd>
          </div>
          <div class="pulse__cell">
            <dt class="pulse__k">open issues</dt>
            <dd class="pulse__v ev">{(repo.repo.open_issues ?? 0).toLocaleString()}</dd>
          </div>
          <div class="pulse__cell">
            <dt class="pulse__k">last push</dt>
            <dd class="pulse__v ev">{repo.repo.pushed_at ? rel(repo.repo.pushed_at) : 'unknown'}</dd>
          </div>
        </dl>
        <p class="pulse__stamp ev">
          read {rel(repo.fetched_at)} from GitHub ·
          <button class="pulse__refresh" onclick={refreshRepo} disabled={reading}>{reading ? 'reading…' : 'Refresh GitHub'}</button>
          · <Tick href={REPO_URL} label="open the repo" external />
        </p>
      {/if}
    </div>
  </div>
</section>

<!-- 5 · What contribution earns ───────────────────────────────────────── -->
<section class="ch ch--earns" aria-labelledby="earns-title">
  <div class="container ch__inner">
    <p class="eyebrow">honest terms · what contribution earns</p>
    <h2 id="earns-title">Your work is tracked. Credit is honest about where it stands.</h2>
    <p class="voice">
      Everything you contribute is recorded — runs you trigger, designs of
      yours that get used, code that merges, the lineage of what you forked
      from, and the feedback you leave. Credit settles on a
      <Term def="A non-monetary accounting rail used to prove the credit machinery works before any real value moves.">test rail</Term>
      today; a real economy comes <em>later</em>, not now. What's solid right
      now is attribution: your name on what you made survives even when
      someone forks it. No income is promised here — see the
      <a href="/legal#token-disclosures">token disclosures</a> for the fine print.
    </p>
  </div>
</section>

<!-- 6 · Close ─────────────────────────────────────────────────────────── -->
<section class="ch ch--close" aria-labelledby="close-title">
  <div class="container ch__inner">
    <h2 id="close-title" class="sr-only">Where to go next</h2>
    <div class="close__row">
      <a class="close__card" href="/commons">
        <span class="close__k eyebrow">the design conversation</span>
        <strong>It lives in the commons.</strong>
        <span class="close__sub">read the public brain — proposals, notes, and decisions, all forkable.</span>
      </a>
      <a class="close__card" href="/graph">
        <span class="close__k eyebrow">the map of everything</span>
        <strong>See the whole graph.</strong>
        <span class="close__sub">how every goal, workflow, and commons page connects.</span>
      </a>
    </div>
  </div>
</section>

<style>
  .container { max-width: 1160px; margin: 0 auto; padding-inline: clamp(18px, 4vw, 32px); }
  .sr-only { position: absolute; width: 1px; height: 1px; padding: 0; margin: -1px; overflow: hidden; clip: rect(0,0,0,0); border: 0; }

  /* ── Cover ── */
  .cover { padding: clamp(48px, 8vw, 96px) 0 clamp(32px, 5vw, 56px); border-bottom: 1px solid var(--border-1); }
  .cover__title {
    font-size: clamp(40px, 7vw, 84px);
    font-weight: 400;
    line-height: 1.0;
    letter-spacing: -0.03em;
    margin: 14px 0 18px;
  }
  .cover__lede { margin: 0 0 16px; }
  .cover__lede em { font-style: italic; color: var(--ember-700); }
  .cover__naming { font-size: 13.5px; color: var(--fg-3); margin: 0; max-width: 60ch; }
  .cover__naming strong { color: var(--fg-2); font-weight: 600; }

  /* ── Shared section chrome ── */
  .ch { padding: clamp(48px, 7vw, 84px) 0; border-bottom: 1px solid var(--border-1); }
  .ch__inner { max-width: 760px; }
  .ch h2 {
    font-size: clamp(28px, 4.4vw, 44px);
    font-weight: 500;
    line-height: 1.08;
    letter-spacing: -0.02em;
    margin: 12px 0 18px;
  }
  .ch .eyebrow { display: block; }
  .door__lede { margin: 0 0 24px; }

  /* ── Door one · numbered steps ── */
  .steps { list-style: none; margin: 0; padding: 0; display: grid; gap: 0; }
  .step {
    display: grid;
    grid-template-columns: 56px 1fr;
    gap: 18px;
    padding: 18px 0;
    border-top: 1px solid var(--border-1);
  }
  .step:last-child { border-bottom: 1px solid var(--border-1); }
  @media (max-width: 640px) { .step { grid-template-columns: 1fr; gap: 6px; } }
  .step__n { font-family: var(--font-mono); font-size: 12px; color: var(--ember-700); letter-spacing: 0.14em; padding-top: 4px; }
  .step__body { display: grid; gap: 6px; justify-items: start; }
  .step__h { font-family: var(--font-voice); font-size: 20px; font-weight: 500; margin: 0; line-height: 1.2; }
  .step__p { font-size: 14.5px; line-height: 1.6; color: var(--fg-2); margin: 0; }
  .step__p code { font-size: 13px; }
  .step__cta { font-family: var(--font-sans); font-size: 13.5px; font-weight: 600; color: var(--ember-700); width: fit-content; }
  .door__note { margin: 24px 0 0; font-size: 15px; }
  .door__note em { font-style: italic; color: var(--ember-700); }

  /* ── Door two · repo steps ── */
  .repo-steps {
    list-style: none; margin: 0; padding: 0;
    display: grid; grid-template-columns: repeat(2, 1fr); gap: 16px;
  }
  @media (max-width: 760px) { .repo-steps { grid-template-columns: 1fr; } }
  .repo-step {
    display: grid; gap: 8px; align-content: start;
    padding: 18px 20px;
    background: var(--bg-2);
    border: 1px solid var(--border-1);
    border-radius: var(--radius-lg);
  }
  .repo-step__cmd {
    background: var(--bg-inset);
    border: 1px solid var(--border-1);
    padding: 6px 10px;
    border-radius: var(--radius-sm);
    color: var(--ink-text-900);
    font-size: 12.5px;
    width: fit-content;
    max-width: 100%;
    overflow-x: auto;
    white-space: nowrap;
  }
  .repo-step__note { font-size: 13.5px; line-height: 1.55; color: var(--fg-2); margin: 0; }

  /* ── Live repo pulse ── */
  .pulse { margin-top: 24px; }
  .pulse__state { font-size: 13px; margin: 0 0 12px; }
  .pulse__state--err { color: var(--signal-error); max-width: 60ch; line-height: 1.55; }
  .pulse__grid {
    display: grid; grid-template-columns: repeat(3, 1fr); gap: 14px;
    margin: 0; padding: 0;
  }
  @media (max-width: 640px) { .pulse__grid { grid-template-columns: 1fr; } }
  .pulse__cell {
    padding: 16px 18px;
    background: var(--bg-2);
    border: 1px solid var(--border-1);
    border-radius: var(--radius-md);
    display: grid; gap: 6px;
  }
  .pulse__k { font-family: var(--font-sans); font-size: 12px; font-weight: 500; color: var(--fg-3); margin: 0; }
  .pulse__v { font-size: 17px; color: var(--fg-1); margin: 0; }
  .pulse__stamp { display: flex; align-items: center; gap: 8px; flex-wrap: wrap; margin-top: 16px; font-size: 11px; }
  .pulse__refresh {
    background: transparent; border: 1px solid var(--border-2); border-radius: var(--radius-pill);
    color: var(--live-700); cursor: pointer;
    font-family: var(--font-mono); font-size: 10px; letter-spacing: 0.08em; text-transform: uppercase;
    padding: 3px 10px;
  }
  .pulse__refresh:hover:not(:disabled) { border-color: var(--live-600); background: var(--live-100); }
  .pulse__refresh:disabled { opacity: 0.6; cursor: default; }

  /* ── What contribution earns ── */
  .ch--earns .voice em { font-style: italic; color: var(--ember-700); }

  /* ── Close ── */
  .ch--close { border-bottom: none; padding-bottom: clamp(72px, 10vw, 120px); }
  .close__row {
    display: grid; grid-template-columns: repeat(2, 1fr); gap: 18px;
  }
  @media (max-width: 760px) { .close__row { grid-template-columns: 1fr; } }
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
  .close__card strong { font-family: var(--font-display); font-size: clamp(20px, 2.8vw, 28px); font-weight: 500; letter-spacing: -0.015em; line-height: 1.14; color: var(--fg-1); }
  .close__sub { font-size: 13.5px; color: var(--fg-2); line-height: 1.5; }
</style>
