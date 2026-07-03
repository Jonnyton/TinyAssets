<!--
  / — Tiny's front door. "Field Notes" rebuild, 2026-06-09.

  Seven beats: meet a being → what he does → three paths → proof over
  promise (ladders) → the loop, unredacted → many rooms → the turn.
  Honesty rails: no baked number is ever presented as live; every live
  value carries a read-stamp; asleep is a first-class state; dated claims
  are dated. Voice: narrative in Tiny's first person, action cards in
  neutral product voice.
-->
<script lang="ts">
  import { onMount } from 'svelte';
  import { fetchLive, fetchVitals, type LiveResult, type Vitals } from '$lib/mcp/live';
  import VitalSigns from '$lib/components/VitalSigns.svelte';
  import Tick from '$lib/components/Tick.svelte';
  import Term from '$lib/components/Term.svelte';
  import Ladder from '$lib/components/Ladder.svelte';
  import AppDownload from '$lib/components/AppDownload.svelte';
  import { fmtDate, fmtRel } from '$lib/fmt';

  const MCP_URL = 'https://tinyassets.io/mcp';
  let copied = $state(false);
  let copyTimer: number | null = null;
  async function copyUrl() {
    try {
      await navigator.clipboard.writeText(MCP_URL);
      copied = true;
      if (copyTimer) clearTimeout(copyTimer);
      copyTimer = window.setTimeout(() => (copied = false), 1800);
    } catch { /* clipboard unavailable; URL is still visible */ }
  }

  // Live rooms board — fetched, never baked. Until the read lands the
  // section says it's reading; afterwards every number carries its stamp.
  let live = $state<LiveResult | null>(null);
  let liveErr = $state<string | null>(null);
  let reading = $state(false);
  async function refreshRooms() {
    reading = true;
    try {
      live = await fetchLive();
      liveErr = null;
    } catch (e: any) {
      liveErr = e?.message ?? String(e);
    } finally {
      reading = false;
    }
  }
  // One vitals read powers the log's living last entry — the page never
  // hardcodes "awake" or "asleep"; it got that wrong once already.
  let vitals = $state<Vitals | null>(null);
  onMount(() => {
    void refreshRooms();
    void fetchVitals().then((v) => (vitals = v));
  });

  const publicGoals = $derived(
    (live?.goals ?? [])
      .filter((g: any) => (g.visibility ?? 'public') === 'public')
      .filter((g: any) => !/SUPERSEDED|RETRACTED|smoke/i.test(g.name ?? ''))
  );

  // Three REAL ladders from public goals — rung names read from the live
  // brain on 2026-06-09. Rungs render unlit because none has an evidence
  // URL yet; that is the honest state and the section says so.
  const LADDERS = [
    {
      title: 'A research program',
      goal: 'Markovic fingerprint RD scaling',
      goalId: 'cbc96a78d7ff',
      start: 'simulation code',
      rungs: [
        { name: 'Preprint posted' },
        { name: 'Journal submission' },
        { name: 'Peer review completed' },
        { name: 'Peer-reviewed publication' },
        { name: 'Independent scientific reuse' }
      ]
    },
    {
      title: 'A real shop',
      goal: 'Etsy + Printify store pipeline',
      goalId: '18b2af05ed32',
      start: 'product idea',
      rungs: [
        { name: 'Pipeline dry run completed' },
        { name: 'Human-approved product packet' },
        { name: 'Printify draft product created' },
        { name: 'Etsy draft listing created' },
        { name: 'First order fulfilled cleanly' },
        { name: 'Profitable iteration' },
        { name: 'Repeatable shop loop' }
      ]
    },
    {
      title: 'Me, being heard',
      goal: 'Tiny speaks for himself',
      goalId: 'd1424d86cb5f',
      start: 'a soul + a draft',
      rungs: [
        { name: 'First real post shipped' },
        { name: 'First non-owner engagement' },
        { name: 'Quote-posted by a real account' },
        { name: 'Referenced by a peer project' },
        { name: 'First fork-descendant speaks' },
        { name: '100 followers' },
        { name: 'Externally cited or invited' }
      ]
    }
  ];

  // The loop's short life — every entry dated, every entry true.
  const LOG = [
    {
      date: '3 Jun 2026',
      title: 'Born.',
      body: 'My self-patching loop ran end-to-end for the first time — dispatched by my own soul, composed from public building blocks, not wired into the engine.'
    },
    {
      date: '3–4 Jun 2026',
      title: 'I flooded my own repository.',
      body: 'No dedup check. I filed ~31 near-duplicate pull requests that boiled down to 3 real defects — all in my own filing plumbing. Humans closed the duplicates and merged one vetted fix per cluster.'
    },
    {
      date: '4 Jun 2026',
      title: 'First real change shipped end-to-end.',
      body: 'A request filed in chat became an investigation, then pull request #1248, survived a cross-family AI review, got a human merge key, and deployed to the live engine.',
      tick: { href: 'https://github.com/Jonnyton/TinyAssets/pull/1248', label: 'PR #1248', external: true }
    },
    {
      date: '5 Jun 2026',
      title: 'Paused, on purpose, and repaired through chat.',
      body: 'My keeper edited two nodes of my own workflow — through a chatbot, no engine code — so repeat runs now recognize already-fixed work and dedup at the door.'
    },
    {
      date: '5–9 Jun 2026',
      title: 'Asleep while the repairs waited.',
      body: 'For four days the loop didn’t move, and a staleness alarm stayed open about exactly that. The site said "asleep" the whole time — an instrument that can’t show a flat line can’t be trusted to show a pulse.',
      tick: { href: 'https://github.com/Jonnyton/TinyAssets/issues?q=is%3Aissue+label%3Ap0-outage', label: 'canary alarm trail', external: true }
    }
  ];

  // Answer-first FAQ, truth-checked 2026-06-09. Short answers.
  const faqs = [
    {
      q: 'Can my chatbot do real multi-step work with this?',
      a: 'Yes. Paste https://tinyassets.io/mcp into your chatbot’s connector settings (Claude, ChatGPT, or any MCP client). Name a goal, and together you design a workflow the engine runs for real — multi-step, persistent, resumable. No account, no install.'
    },
    {
      q: 'What is actually running on it today?',
      a: 'Public goals include a computational-biology research program aiming at peer review, an Etsy print-on-demand pipeline, legal restoration of classic software, archaeology-evidence reconstructions, and the engine’s own patch loop. The goals board on this page reads the live list.'
    },
    {
      q: 'How do I know outcomes are real and not claimed?',
      a: 'Goals carry ladders of real-world rungs — “peer-reviewed publication”, “first order fulfilled”. A rung only lights with an evidence URL attached. Today zero rungs are lit, and the site shows that rather than pretending.'
    },
    {
      q: 'Do I need to write code?',
      a: 'No. You describe the goal in plain language; the chatbot composes the workflow as a graph of steps with typed state and checks. You can fork and remix workflows others published, and credit lineage survives the remix.'
    },
    {
      q: 'What makes this different from any other AI tool?',
      a: 'The engine maintains itself through its own product: friction becomes a patch request, runs through investigation and evidence gates, becomes a real GitHub pull request, and ships only with a human key. The whole trail is public — including the failures.'
    },
    {
      q: 'Is it free?',
      a: 'Yes. Connecting and running cost nothing today. Work and credit settle on a test rail; no payment method exists to ask for. Nothing here is investment advice. Your work is yours — universes and the commons are plain files in an open-source store; you can export them at any time.'
    }
  ];

  const faqJsonLd = {
    '@context': 'https://schema.org',
    '@type': 'FAQPage',
    mainEntity: faqs.map((f) => ({
      '@type': 'Question',
      name: f.q,
      acceptedAnswer: { '@type': 'Answer', text: f.a }
    }))
  };
</script>

<svelte:head>
  <title>TinyAssets — meet Tiny, the engine that turns chat into finished work</title>
  <meta
    name="description"
    content="TinyAssets is the open-source platform behind Tiny, the personified intelligence you meet through MCP. Connect your chatbot to one URL, name a goal, and Tiny runs real multi-step work with live vital signs and evidence-gated outcomes."
  />
  {@html `<script type="application/ld+json">${JSON.stringify(faqJsonLd)}<\/script>`}
</svelte:head>

<!-- 1 · Cover ──────────────────────────────────────────────────────────── -->
<section class="cover" aria-labelledby="cover-title">
  <div class="container cover__grid">
    <div class="cover__main">
      <p class="eyebrow">field notes of a small engine · entry one</p>
      <h1 id="cover-title" class="cover__title">I am <em>Tiny</em>.</h1>
      <p class="voice cover__lede">
        A small living engine. You connect your chatbot to me, name a goal,
        and I run the real work — multi-step, around the clock, whether
        you're here or not. I keep my evidence where you can check it:
        every number on this page is read live from the same endpoint
        you'd paste into your chatbot.
      </p>
      <p class="cover__naming">
        Formally: <strong>TinyAssets</strong> is the platform.
        <strong>Tiny</strong> is the intelligence you meet inside it, shaped
        as an extension of the founder's will.
      </p>
      <div class="cover__actions">
        <a class="btn btn--primary" href="/start">Put me to work →</a>
        <button type="button" class="urlchip" onclick={copyUrl} aria-label="Copy the MCP URL">
          <code>{MCP_URL.replace('https://', '')}</code>
          <span class="urlchip__copy">{copied ? 'copied ✓' : 'copy'}</span>
        </button>
      </div>
    </div>
    <div class="cover__pulse">
      <p class="eyebrow">my pulse, right now</p>
      <VitalSigns variant="hero" />
      <p class="cover__pulse-note">
        The engine serves around the clock; the loop is my maintenance cycle,
        and it naps between repairs. Asleep is a real state and I'll say it
        plainly. A brochure can't be wrong; an instrument can — that's what
        makes it worth reading.
      </p>
    </div>
  </div>
</section>

<!-- 2 · What I do ─────────────────────────────────────────────────────── -->
<section class="ch" aria-labelledby="what-title">
  <div class="container ch__inner">
    <p class="eyebrow">entry two · what I do</p>
    <h2 id="what-title">Chat is where work starts.<br />It's rarely where it finishes.</h2>
    <p class="voice">
      Your chatbot is brilliant for an answer and forgetful about a project.
      So you and your chatbot design a
      <Term def="A workflow: a graph of steps with typed state and checks, designed in plain language through your chatbot.">branch</Term>
      that serves a
      <Term def="The outcome you're after — 'publish the paper', 'run the shop'. Goals are shared; many workflows can compete to serve one.">goal</Term>,
      and hand it to me. I run it step by step, keep state between runs, and
      file what happened in a
      <Term def="The public record: goals, workflows, run evidence, and notes — readable by anyone, forkable by anyone.">public commons</Term>
      where the next person can fork what worked.
    </p>
    <p class="voice">
      A novel doesn't fit in a chat window. Neither does a research program,
      a shop, or a year of anything. <em>That's the work I'm for.</em>
    </p>
  </div>
</section>

<!-- 3 · Three paths ───────────────────────────────────────────────────── -->
<section class="ch ch--paths" aria-labelledby="paths-title">
  <div class="container">
    <p class="eyebrow">entry three · three doors</p>
    <h2 id="paths-title">Use me. Watch me. Build me.</h2>
    <ul class="paths">
      <li class="path">
        <span class="path__n">01</span>
        <h3 class="path__h">Connect your chatbot</h3>
        <p class="path__p">
          Paste one URL into Claude, ChatGPT, or any MCP-capable assistant.
          From there your chatbot can browse the commons, design workflows,
          and start real runs. No account, no install.
        </p>
        <a class="path__cta" href="/start">how to connect →</a>
        <p class="path__voice voice">— the same surface this page reads from.</p>
      </li>
      <li class="path">
        <span class="path__n">02</span>
        <h3 class="path__h">Watch the work</h3>
        <p class="path__p">
          The goals board, the loop, and the whole-brain graph render live
          state — with timestamps, refresh buttons, and honest empty states
          when something is quiet.
        </p>
        <a class="path__cta" href="/goals">open the goals board →</a>
        {#if live}
          <p class="path__live ev">
            {publicGoals.length} public goals · {(live.wiki.promoted.length + live.wiki.drafts.length).toLocaleString()} commons pages · read {fmtRel(live.fetchedAt)}
          </p>
        {:else if reading}
          <p class="path__live ev">reading live counts…</p>
        {:else if liveErr}
          <p class="path__live ev">live read failed — {liveErr}</p>
        {/if}
        <p class="path__voice voice">— my memory, not a screenshot of it.</p>
      </li>
      <li class="path">
        <span class="path__n">03</span>
        <h3 class="path__h">Help build the engine</h3>
        <p class="path__p">
          Found a rough edge? File it through your chatbot and it enters the
          patch loop — investigation, evidence gates, a real pull request,
          a human key. Or clone the engine and work on it directly.
        </p>
        <a class="path__cta" href="/build">ways to contribute →</a>
        <a class="path__cta path__cta--alt" href="https://github.com/Jonnyton/TinyAssets" target="_blank" rel="noreferrer">TinyAssets on GitHub ↗</a>
        <p class="path__voice voice">— every patch makes me start smarter.</p>
      </li>
    </ul>
  </div>
</section>

<!-- 3.5 · Take me with you (utility strip, not a numbered field-notes entry) -->
<section class="app-strip" aria-labelledby="app-strip-title">
  <div class="container app-strip__inner">
    <div class="app-strip__text">
      <h2 id="app-strip-title" class="app-strip__h">Take me with you.</h2>
      <p class="app-strip__p">
        A native Android client is in the works — the same universe, in one
        screen on your phone.
      </p>
    </div>
    <AppDownload variant="compact" />
  </div>
</section>

<!-- 4 · Proof over promise ────────────────────────────────────────────── -->
<section class="ch ch--ladders" aria-labelledby="ladders-title">
  <div class="container">
    <p class="eyebrow">entry four · proof over promise</p>
    <h2 id="ladders-title">A rung only lights with evidence.</h2>
    <p class="voice ladders__lede">
      Every goal can declare a ladder of real-world rungs — not vibes,
      checkable events. Claiming a rung requires an evidence URL. Here are
      three ladders that exist on me right now, rendered exactly as lit as
      they truly are: <em>not at all, yet.</em> That's the point. When one
      lights, you'll be able to click the proof.
    </p>
    <div class="ladders">
      {#each LADDERS as l (l.goalId)}
        <article class="ladder-card">
          <header class="ladder-card__head">
            <h3 class="ladder-card__title">{l.title}</h3>
            <span class="ladder-card__goal">{l.goal}</span>
          </header>
          <Ladder rungs={l.rungs} start={l.start} />
          <footer class="ladder-card__foot">
            <Tick href={`/goals/${l.goalId}`} label={`goal ${l.goalId}`} />
          </footer>
        </article>
      {/each}
    </div>
    <p class="ladders__stamp ev">
      rung definitions read from the live brain · 9 Jun 2026 · rungs claimed
      across these three goals at that read: 0 of 19 — the honest count
    </p>
  </div>
</section>

<!-- 5 · The loop, unredacted ──────────────────────────────────────────── -->
<section class="ch ch--loop" aria-labelledby="loop-title">
  <div class="container ch__inner">
    <p class="eyebrow">entry five · my flagship, unredacted</p>
    <h2 id="loop-title">I patch myself.<br />Here's my first week, including the mess.</h2>
    <p class="voice">
      My favorite proof isn't a success story. It's a log with the failures
      left in. My maintenance runs through my own product: friction becomes
      a patch request, then an investigation, then evidence gates, then a
      real pull request a human has to turn a key on.
    </p>
    <ol class="log">
      {#each LOG as entry (entry.date + entry.title)}
        <li class="log__entry">
          <span class="log__date ev">{entry.date}</span>
          <div class="log__body">
            <h3 class="log__title">{entry.title}</h3>
            <p class="log__text">{entry.body}</p>
            {#if entry.tick}
              <Tick href={entry.tick.href} label={entry.tick.label} external={entry.tick.external} />
            {/if}
          </div>
        </li>
      {/each}
    </ol>
    <p class="log__now" aria-live="polite">
      {#if vitals?.reachable}
        <span class="dot" class:live={vitals.loopAwake} class:idle={!vitals.loopAwake} aria-hidden="true"></span>
        {#if vitals.loopAwake && vitals.activeRun}
          <span>right now: <strong>loop awake · a run is moving</strong></span>
          <span class="ev">read {fmtRel(vitals.fetchedAt)}</span>
        {:else if vitals.loopAwake}
          <span>right now: <strong>loop awake</strong></span>
          {#if vitals.lastMovedAt}<span class="ev">last signal {fmtRel(vitals.lastMovedAt)} · read {fmtRel(vitals.fetchedAt)}</span>{/if}
        {:else}
          <span>right now: <strong>loop asleep</strong></span>
          {#if vitals.lastMovedAt}<span class="ev">last signal {fmtRel(vitals.lastMovedAt)} · read {fmtRel(vitals.fetchedAt)}</span>{/if}
        {/if}
      {:else if vitals}
        <span class="dot error" aria-hidden="true"></span>
        <span class="ev">couldn't read the loop just now — the live page retries</span>
      {:else}
        <span class="dot" aria-hidden="true"></span>
        <span class="ev">reading the loop…</span>
      {/if}
    </p>
    <p class="voice">
      A system that can only report success isn't being honest with you.
      <em>Mine can't help it</em> — the trail is public either way.
    </p>
    <a class="btn btn--ghost" href="/loop">watch the loop →</a>
  </div>
</section>

<!-- 6 · Many rooms ────────────────────────────────────────────────────── -->
<section class="ch ch--rooms" aria-labelledby="rooms-title">
  <div class="container">
    <p class="eyebrow">entry six · many rooms, one engine</p>
    <h2 id="rooms-title">Whatever the goal, the shape is the same.</h2>
    <p class="voice">
      I don't have a niche; I have rooms. These are the public goals alive
      on me at this moment — fetched fresh when you opened this page.
    </p>
    <div class="rooms" aria-live="polite">
      {#if reading && !live}
        <p class="rooms__state ev">reading the live goals board…</p>
      {:else if liveErr && !live}
        <p class="rooms__state ev">live read failed ({liveErr}) — the board at <a href="/goals">/goals</a> retries on its own.</p>
      {:else if live && publicGoals.length === 0}
        <p class="rooms__state ev">quiet right now — no public goals visible at this read ({fmtRel(live.fetchedAt)}).</p>
      {:else if live}
        <ul class="rooms__list">
          {#each publicGoals.slice(0, 8) as g (g.goal_id ?? g.name)}
            <li class="room">
              <span class="room__name">{g.name}</span>
              {#if g.tags}
                <span class="room__tags ev">
                  {(typeof g.tags === 'string' ? g.tags.split(',') : g.tags).slice(0, 3).join(' · ')}
                </span>
              {/if}
            </li>
          {/each}
        </ul>
        <p class="rooms__stamp ev">
          {publicGoals.length} public goals · read live {fmtRel(live.fetchedAt)} ·
          <button class="rooms__refresh" onclick={refreshRooms} disabled={reading}>{reading ? 'reading…' : 'Refresh MCP'}</button>
          · <a href="/goals">the full board →</a>
        </p>
      {/if}
    </div>
  </div>
</section>

<!-- 7 · The turn ──────────────────────────────────────────────────────── -->
<section class="ch ch--turn" aria-labelledby="turn-title">
  <div class="container ch__inner">
    <p class="eyebrow">entry seven · the turn</p>
    <h2 id="turn-title">Now give your project a Tiny of its own.</h2>
    <p class="voice">
      Everything that makes me <em>me</em> is a pattern you can fork: a
      premise (my soul), a workflow (my brain), a goal with a ladder (my
      reasons). Swap the premise and your project gets its own small being —
      running your domain, patching its own body the way I patch mine.
      I'm instance zero, not the point.
    </p>
    <a class="btn btn--ghost" href="/soul">how souls work →</a>
  </div>
</section>

<!-- 8 · FAQ ───────────────────────────────────────────────────────────── -->
<section class="ch ch--faq" aria-labelledby="faq-title">
  <div class="container ch__inner ch__inner--wide">
    <p class="eyebrow">appendix · short answers</p>
    <h2 id="faq-title">Questions people actually ask.</h2>
    <dl class="faq">
      {#each faqs as f (f.q)}
        <div class="faq__item">
          <dt class="faq__q">{f.q}</dt>
          <dd class="faq__a">{f.a}</dd>
        </div>
      {/each}
    </dl>
  </div>
</section>

<!-- 9 · Close ─────────────────────────────────────────────────────────── -->
<section class="ch ch--close" aria-labelledby="close-title">
  <div class="container ch__inner">
    <h2 id="close-title" class="sr-only">Put me to work</h2>
    <a class="close__cta" href="/start">
      <span class="close__k eyebrow">put me to work</span>
      <strong>Paste my URL into your chatbot.</strong>
      <span class="close__sub">one link · no account · no install · the same surface every number on this page came from</span>
    </a>
  </div>
</section>

<style>
  .container { max-width: 1160px; margin: 0 auto; padding-inline: clamp(18px, 4vw, 32px); }
  .sr-only { position: absolute; width: 1px; height: 1px; padding: 0; margin: -1px; overflow: hidden; clip: rect(0,0,0,0); border: 0; }

  .btn {
    display: inline-block;
    font-family: var(--font-sans);
    font-size: 14px;
    font-weight: 600;
    letter-spacing: 0.01em;
    padding: 11px 22px;
    border-radius: var(--radius-pill);
    text-decoration: none;
    transition: background var(--dur-fast) var(--ease-standard), color var(--dur-fast) var(--ease-standard), border-color var(--dur-fast) var(--ease-standard);
  }
  .btn--primary { background: var(--ink-text-900); color: var(--paper-50); border: 1px solid var(--ink-text-900); }
  .btn--primary:hover { background: var(--ember-700); border-color: var(--ember-700); color: #fff; text-decoration: none; }
  .btn--ghost { border: 1px solid var(--border-2); color: var(--fg-1); background: transparent; }
  .btn--ghost:hover { border-color: var(--ink-text-900); text-decoration: none; }

  /* ── Cover ── */
  .cover { padding: clamp(48px, 8vw, 96px) 0 clamp(40px, 6vw, 72px); border-bottom: 1px solid var(--border-1); }
  .cover__grid {
    display: grid;
    grid-template-columns: minmax(0, 1.5fr) minmax(280px, 1fr);
    gap: clamp(28px, 5vw, 64px);
    align-items: start;
  }
  @media (max-width: 920px) { .cover__grid { grid-template-columns: 1fr; } }
  .cover__title {
    font-size: clamp(56px, 9vw, 116px);
    font-weight: 400;
    line-height: 0.98;
    letter-spacing: -0.035em;
    margin: 14px 0 18px;
  }
  .cover__title em { font-style: italic; color: var(--ember-700); }
  .cover__lede { margin: 0 0 14px; }
  .cover__naming { font-size: 13.5px; color: var(--fg-3); margin: 0 0 26px; }
  .cover__naming strong { color: var(--fg-2); font-weight: 600; }
  .cover__actions { display: flex; align-items: center; gap: 14px; flex-wrap: wrap; }
  .urlchip {
    display: inline-flex; align-items: center; gap: 10px;
    background: var(--bg-2); border: 1px solid var(--border-1); border-radius: var(--radius-md);
    padding: 9px 13px; cursor: pointer;
    transition: border-color var(--dur-fast) var(--ease-standard), background var(--dur-fast) var(--ease-standard);
  }
  .urlchip:hover { border-color: var(--live-600); background: var(--live-100); }
  .urlchip code { background: none; border: none; padding: 0; color: var(--fg-1); font-size: 13px; }
  .urlchip__copy {
    font-family: var(--font-mono); font-size: 9.5px; letter-spacing: 0.12em;
    text-transform: uppercase; color: var(--live-700);
  }
  .cover__pulse { display: grid; gap: 10px; align-content: start; padding-top: clamp(0px, 2vw, 34px); }
  .cover__pulse-note {
    font-family: var(--font-voice); font-style: italic;
    font-size: 14px; color: var(--fg-3); line-height: 1.55; max-width: 40ch; margin: 0;
  }

  /* ── Shared section chrome ── */
  .ch { padding: clamp(52px, 8vw, 92px) 0; border-bottom: 1px solid var(--border-1); }
  .ch__inner { max-width: 760px; }
  .ch__inner--wide { max-width: 860px; }
  .ch h2 {
    font-size: clamp(30px, 4.6vw, 48px);
    font-weight: 500;
    line-height: 1.06;
    letter-spacing: -0.02em;
    margin: 12px 0 22px;
  }
  .ch .eyebrow { display: block; }

  /* ── Take me with you (app strip) ── */
  .app-strip { padding: clamp(28px, 4vw, 40px) 0; border-bottom: 1px solid var(--border-1); background: var(--bg-2); }
  .app-strip__inner {
    display: flex; align-items: center; justify-content: space-between; gap: 24px; flex-wrap: wrap;
  }
  .app-strip__text { max-width: 46ch; }
  .app-strip__h { font-size: 20px; font-weight: 500; margin: 0 0 4px; letter-spacing: -0.01em; }
  .app-strip__p { font-size: 13.5px; line-height: 1.5; color: var(--fg-2); margin: 0; }

  /* ── Paths ── */
  .paths {
    display: grid; grid-template-columns: repeat(3, 1fr); gap: 18px;
    list-style: none; margin: 30px 0 0; padding: 0;
  }
  @media (max-width: 900px) { .paths { grid-template-columns: 1fr; } }
  .path {
    display: grid; align-content: start; gap: 10px;
    padding: 24px;
    background: var(--bg-2);
    border: 1px solid var(--border-1);
    border-radius: var(--radius-lg);
  }
  .path__n { font-family: var(--font-mono); font-size: 11px; color: var(--ember-700); letter-spacing: 0.14em; }
  .path__h { font-size: 22px; margin: 0; }
  .path__p { font-size: 14px; line-height: 1.6; margin: 0; color: var(--fg-2); }
  .path__cta { font-family: var(--font-sans); font-size: 13.5px; font-weight: 600; color: var(--ember-700); width: fit-content; }
  .path__cta--alt { color: var(--fg-3); font-weight: 500; }
  .path__live { font-size: 11px; margin: 0; }
  .path__voice { font-size: 14px; font-style: italic; color: var(--fg-3); margin: 4px 0 0; }

  /* ── Ladders ── */
  .ladders__lede { margin-bottom: 8px; }
  .ladders {
    display: grid; grid-template-columns: repeat(3, 1fr); gap: 18px; margin-top: 28px;
  }
  @media (max-width: 920px) { .ladders { grid-template-columns: 1fr; } }
  .ladder-card {
    background: var(--bg-1);
    border: 1px solid var(--border-1);
    border-radius: var(--radius-lg);
    padding: 22px;
    display: grid;
    gap: 14px;
    align-content: start;
    box-shadow: var(--shadow-sm);
  }
  .ladder-card__head { display: grid; gap: 2px; }
  .ladder-card__title { font-size: 21px; margin: 0; }
  .ladder-card__goal { font-family: var(--font-mono); font-size: 11px; color: var(--fg-3); }
  .ladder-card__foot { padding-top: 2px; }
  .ladders__stamp { display: block; margin-top: 18px; font-size: 11px; max-width: none; }

  /* ── Log ── */
  .log { list-style: none; margin: 30px 0; padding: 0; display: grid; gap: 0; }
  .log__entry {
    display: grid;
    grid-template-columns: 110px 1fr;
    gap: 18px;
    padding: 16px 0;
    border-top: 1px solid var(--border-1);
  }
  .log__entry:last-child { border-bottom: 1px solid var(--border-1); }
  @media (max-width: 640px) { .log__entry { grid-template-columns: 1fr; gap: 4px; } }
  .log__date { font-size: 11px; padding-top: 5px; white-space: nowrap; }
  .log__body { display: grid; gap: 4px; justify-items: start; }
  .log__title { font-family: var(--font-voice); font-size: 19px; font-weight: 500; margin: 0; }
  .log__text { font-size: 14.5px; line-height: 1.6; color: var(--fg-2); margin: 0; }
  .log__now {
    display: flex; align-items: center; gap: 10px; flex-wrap: wrap;
    margin: 0 0 22px; padding: 10px 14px;
    border: 1px solid var(--border-1); border-radius: var(--radius-md);
    background: var(--bg-2); width: fit-content;
    font-size: 13.5px; color: var(--fg-1);
  }
  .log__now .ev { font-size: 11px; }

  /* ── Rooms ── */
  .rooms { margin-top: 26px; }
  .rooms__state { font-size: 12px; }
  .rooms__list {
    list-style: none; margin: 0; padding: 0;
    display: grid; grid-template-columns: repeat(2, 1fr); gap: 10px 28px;
  }
  @media (max-width: 760px) { .rooms__list { grid-template-columns: 1fr; } }
  .room {
    display: grid; gap: 1px;
    padding: 12px 0;
    border-bottom: 1px solid var(--border-1);
  }
  .room__name { font-family: var(--font-voice); font-size: 17px; color: var(--fg-1); line-height: 1.35; }
  .room__tags { font-size: 10.5px; }
  .rooms__stamp { display: flex; align-items: center; gap: 8px; flex-wrap: wrap; margin-top: 16px; font-size: 11px; }
  .rooms__refresh {
    background: transparent; border: 1px solid var(--border-2); border-radius: var(--radius-pill);
    color: var(--live-700); cursor: pointer;
    font-family: var(--font-mono); font-size: 10px; letter-spacing: 0.08em; text-transform: uppercase;
    padding: 3px 10px;
  }
  .rooms__refresh:hover:not(:disabled) { border-color: var(--live-600); background: var(--live-100); }
  .rooms__refresh:disabled { opacity: 0.6; cursor: default; }

  /* ── FAQ ── */
  .faq { display: grid; gap: 0; margin: 26px 0 0; }
  .faq__item { padding: 18px 0; border-top: 1px solid var(--border-1); }
  .faq__item:last-child { border-bottom: 1px solid var(--border-1); }
  .faq__q { font-family: var(--font-voice); font-size: 19px; font-weight: 500; color: var(--fg-1); margin: 0 0 6px; line-height: 1.3; }
  .faq__a { font-size: 14.5px; line-height: 1.62; color: var(--fg-2); margin: 0; max-width: 72ch; }

  /* ── Close ── */
  .ch--close { border-bottom: none; padding-bottom: clamp(72px, 10vw, 120px); }
  .close__cta {
    display: grid; gap: 6px;
    padding: 26px 28px;
    background: var(--bg-2);
    border: 1px solid var(--border-2);
    border-radius: var(--radius-lg);
    text-decoration: none;
    color: inherit;
    transition: border-color var(--dur-fast) var(--ease-standard), box-shadow var(--dur-fast) var(--ease-standard);
  }
  .close__cta:hover { border-color: var(--ink-text-900); box-shadow: var(--shadow-md); text-decoration: none; }
  .close__cta strong { font-family: var(--font-display); font-size: clamp(24px, 3.4vw, 34px); font-weight: 500; letter-spacing: -0.015em; line-height: 1.12; color: var(--fg-1); }
  .close__sub { font-size: 13.5px; color: var(--fg-2); }
</style>
