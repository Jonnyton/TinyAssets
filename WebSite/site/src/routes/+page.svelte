<!--
  / — Tiny's front door.

  The home page has ONE job: introduce Tiny, say what this is, name the three
  things you can do, prove it's alive enough to be credible, and hand off to the
  pages that own the detail. It must NOT reproduce those pages:
    · the live node/edge board   → /graph
    · the goal board             → /goals
    · the searchable commons      → /wiki
    · health + current work       → /fine-print
    · try a live call          → /connect

  So the live proof here is light: counts on the action cards + a one-line
  pulse, not three inline dashboards. Voice = Tiny, first person.
-->
<script lang="ts">
  import { onMount } from 'svelte';
  import baked from '$lib/content/mcp-snapshot.json';
  import { fetchLive, liveToSnapshotShape } from '$lib/mcp/live';
  import type { Snapshot } from '$lib/mcp/types';
  import RitualLabel from '$lib/components/Primitives/RitualLabel.svelte';
  import MoodPill from '$lib/components/MoodPill.svelte';

  let snapshot = $state(baked as unknown as Snapshot);
  let liveError = $state<string | null>(null);
  let liveSource = $state<'snapshot' | 'live'>('snapshot');
  let fetchedAt = $state<string>((baked as unknown as Snapshot).fetched_at);
  let refreshing = $state(false);

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

  const universes = $derived(snapshot.universes ?? []);
  const goalCount = $derived(snapshot.goals?.length ?? 0);
  const wikiCount = $derived(
    (snapshot.wiki?.bugs?.length ?? 0) +
    (snapshot.wiki?.plans?.length ?? 0) +
    (snapshot.wiki?.concepts?.length ?? 0) +
    (snapshot.wiki?.notes?.length ?? 0) +
    (snapshot.wiki?.drafts?.length ?? 0)
  );
  const bugCount = $derived(snapshot.wiki?.bugs?.length ?? 0);

  function fmtRelative(s?: string | null): string {
    if (!s) return 'unknown';
    const ms = Date.parse(s);
    if (Number.isNaN(ms)) return s;
    const diff = Date.now() - ms;
    if (diff < 60_000) return 'just now';
    if (diff < 3_600_000) return `${Math.floor(diff / 60_000)}m ago`;
    if (diff < 86_400_000) return `${Math.floor(diff / 3_600_000)}h ago`;
    return `${Math.floor(diff / 86_400_000)}d ago`;
  }

  function scrollTo(id: string) {
    if (typeof document === 'undefined') return;
    document.getElementById(id)?.scrollIntoView({ behavior: 'smooth', block: 'start' });
  }

  async function refresh() {
    refreshing = true;
    try {
      const live = await fetchLive();
      const shaped = liveToSnapshotShape(live, baked as unknown as Snapshot);
      snapshot = { ...shaped, goals: shaped.goals.length ? shaped.goals : snapshot.goals };
      fetchedAt = live.fetchedAt;
      liveSource = 'live';
      liveError = null;
    } catch (err: any) {
      liveError = err?.message ?? String(err);
    } finally {
      refreshing = false;
    }
  }

  type SectionId = 'cover' | 'what' | 'paths' | 'flagship' | 'faq' | 'close';
  const SECTION_META: Record<SectionId, { folio: string; title?: string }> = {
    cover:    { folio: 'tiny' },
    what:     { folio: '01', title: 'what I am' },
    paths:    { folio: '02', title: 'use · watch · build' },
    flagship: { folio: '03', title: 'I patch myself' },
    faq:      { folio: '04', title: 'the short answers' },
    close:    { folio: '05', title: 'put me to work' }
  };
  // Answer-first FAQ. Plain, self-contained, quotable answers in natural-language
  // phrasing — what people actually say to a chatbot. Also emitted as FAQPage
  // structured data below so AI search engines can ground on each Q/A pair.
  const faqs = [
    {
      q: 'Can I get my AI chatbot to do real multi-step work, not just answer questions?',
      a: 'Yes. Connect Workflow (its public name is Tiny) to your chatbot over MCP at https://tinyassets.io/mcp, name a goal, and the chatbot can design, run, and check a real multi-step workflow that produces actual artifacts and persists between runs — not a single best-effort reply. It works in Claude, ChatGPT, and any MCP-capable assistant, with no account and no install.'
    },
    {
      q: 'What kinds of projects can it run?',
      a: 'Almost any goal that takes more than one step. Examples already running on it: drafting and maintaining a novel, turning messy notes and public records into an investigative article series, a computational-biology research program aimed at a peer-reviewed paper, an Etsy and Printify store pipeline, a fantasy strategy game built toward a real release, coordinating a neighborhood mutual-aid pantry, and turning archaeological evidence into reconstructions. The engine is goal-agnostic: the architecture stays the same and only the goal changes.'
    },
    {
      q: 'Can an AI actually finish a long, months-long project instead of just starting one?',
      a: 'Yes — this is built for long-horizon work. Runs persist, can be scheduled and resumed, and a single goal can span months: a novel maintained over many sessions, a year-long science-publication strategy, or a game taken from prototype toward release. After each run the workflow can notice what was missing and patch itself to run better next time.'
    },
    {
      q: 'How do I build an AI workflow without coding?',
      a: 'Describe the goal to your connected chatbot in plain language and it builds the workflow for you as a "branch" — a graph of steps with typed state, prompts, and evaluation checks. You do not write code or edit config. You can validate, run, and publish versions of it directly through the chatbot.'
    },
    {
      q: 'Can I reuse or build on workflows other people already made?',
      a: 'Yes. Instead of starting from scratch, fork the closest existing branch and remix it. Forks keep credit lineage back to the original, so improvements compound across the community. Many branches can compete on the same goal, and a leaderboard surfaces the strongest one as canonical.'
    },
    {
      q: 'How do I know the AI actually did the work and is not just claiming it?',
      a: 'Each goal can define a ladder of real-world rungs that require evidence. A research goal ladders from preprint to submitted to peer-reviewed to published to independently reused; a store goal ladders from dry-run to first order fulfilled to profitable. A workflow can only claim a rung by attaching an evidence URL, so outcomes are checkable rather than asserted.'
    },
    {
      q: 'How do I connect it to ChatGPT or Claude?',
      a: 'Paste the MCP URL https://tinyassets.io/mcp into your chatbot\u2019s connector settings. MCP, the Model Context Protocol, is the open standard that lets chatbots use external tools, so the same URL works in Claude, ChatGPT, and any MCP client. There is no account and no install. Once connected, your chatbot can build, run, and judge workflows and browse the public commons.'
    },
    {
      q: 'Can I give my own product or platform a version of this?',
      a: 'Yes. Beyond a single workflow, you can fork the whole engine for your own platform. It gets its own memory, its own purpose, and its own self-patching loop that keeps it aligned to you — and to your team or power users — as it grows. Tiny is just the first instance of that pattern.'
    },
    {
      q: 'Is it free?',
      a: 'Yes to start. Connecting and running cost nothing. Work, gates, and credit settle on a test rail today; a real economy opens later, when integration does. No payment method is required to connect or run.'
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

  let currentSection = $state<SectionId>('cover');

  onMount(() => {
    void refresh();

    const ids: SectionId[] = ['cover', 'what', 'paths', 'flagship', 'faq', 'close'];
    const observer = new IntersectionObserver(
      (entries) => {
        for (const e of entries) {
          if (e.isIntersecting) {
            const id = (e.target as HTMLElement).id as SectionId;
            if (ids.includes(id)) currentSection = id;
          }
        }
      },
      { rootMargin: '-35% 0px -50% 0px', threshold: 0 }
    );
    for (const id of ids) {
      const el = document.getElementById(id);
      if (el) observer.observe(el);
    }
    return () => observer.disconnect();
  });
</script>

<svelte:head>
  <title>Tiny · the goal-agnostic engine, speaking for itself</title>
  <meta name="description" content="I'm Tiny — a goal-agnostic engine. Bind me to any domain and I run the real work, then patch myself to run it better. Connect your chatbot, watch the loop, or help build me." />
  {@html `<script type="application/ld+json">${JSON.stringify(faqJsonLd)}<\/script>`}
</svelte:head>

<MoodPill />

<!-- 1 · Cover — who I am ─────────────────────────────────────────────────── -->
<section id="cover" class="cover" aria-labelledby="cover-title">
  <div class="cover__inner">
    <h1 id="cover-title" class="cover__title">
      <span class="cover__hello">Hello world. My name is</span>
      <em>Tiny.</em>
    </h1>
    <p class="cover__lede">
      A goal-agnostic engine that gives any project a soul and a loop of its
      own. Small on my own — but big things are many small things.
    </p>
    <p class="cover__byline">— I run real work, then patch myself to run it better. —</p>
    <div class="cover__cta">
      <button type="button" class="cta cta--primary" onclick={() => scrollTo('paths')}>
        what you can do with me <span aria-hidden="true">↓</span>
      </button>
      <nav class="cover__paths" aria-label="The three things you can do">
        <a href="/connect">connect</a>
        <span aria-hidden="true">·</span>
        <a href="/graph">explore</a>
        <span aria-hidden="true">·</span>
        <a href="https://github.com/Jonnyton/Workflow" target="_blank" rel="noreferrer">build</a>
      </nav>
    </div>
  </div>
</section>

<!-- 2 · What I am ───────────────────────────────────────────────────────── -->
<section id="what" class="ch" aria-labelledby="what-title">
  <div class="ch__inner">
    <RitualLabel color="var(--violet-400)">· what I am ·</RitualLabel>
    <h2 id="what-title" class="ch__h">I'm a goal-agnostic engine.</h2>
    <p class="lede">
      Bind me to a domain — a novel, a game, a paper, an invoice queue, a legal
      filing, a year-long science publication strategy — and I run the work.
      Not a chatbot's guess at what the work might look like.
      <em>Real artifacts.</em> Real outcomes. Whatever the goal is, the shape is
      the same; only the room changes.
    </p>
    <p class="lede">
      The interesting part is what happens after I run. I notice what was
      missing, what you wanted but couldn't quite ask for, where I stalled. Your
      chatbot files that friction back to me as a patch request. A daemon —
      sometimes me, sometimes another — picks it up, drafts a fix, routes it
      through evidence gates, and ships when the gates are satisfied. The next
      time you summon me, I start smarter.
    </p>
  </div>
</section>

<!-- 3 · The three paths — the home's spine ──────────────────────────────── -->
<section id="paths" class="ch ch--paths" aria-labelledby="paths-title">
  <div class="ch__inner">
    <RitualLabel color="var(--ember-500)">· three things you can do ·</RitualLabel>
    <h2 id="paths-title" class="ch__h">Connect. Explore. Build.</h2>

    <ul class="paths">
      <li class="path">
        <span class="path__n">1 · connect</span>
        <strong class="path__h">Connect to me.</strong>
        <p class="path__p">Paste my MCP URL into your chatbot's connector. From there it can browse my commons, file patch requests, and summon real runs. No account, no install.</p>
        <a class="path__cta" href="/connect">how to connect →</a>
        <button type="button" class="path__url" onclick={copyUrl} aria-label="Copy my MCP URL">
          <span class="dot live" aria-hidden="true"></span>
          <code>tinyassets.io/mcp</code>
          <span class="path__copy">{copied ? 'copied ✓' : 'copy'}</span>
        </button>
      </li>
      <li class="path path--brain">
        <div class="path__top">
          <span class="path__n">2 · the brain</span>
          <svg class="path__graph" viewBox="0 0 100 70" role="img" aria-label="A miniature of my live graph">
            <g class="edges" stroke="var(--border-2)" stroke-width="1">
              <line x1="50" y1="34" x2="24" y2="18" /><line x1="50" y1="34" x2="76" y2="16" />
              <line x1="50" y1="34" x2="18" y2="46" /><line x1="50" y1="34" x2="40" y2="54" />
              <line x1="50" y1="34" x2="66" y2="50" /><line x1="50" y1="34" x2="62" y2="26" />
              <line x1="76" y1="16" x2="88" y2="38" /><line x1="24" y1="18" x2="34" y2="30" />
              <line x1="66" y1="50" x2="88" y2="38" /><line x1="40" y1="54" x2="18" y2="46" />
            </g>
            <circle cx="50" cy="34" r="5" fill="var(--ember-500)" />
            <circle cx="24" cy="18" r="3" fill="var(--violet-400)" />
            <circle cx="76" cy="16" r="3" fill="var(--signal-live)" />
            <circle cx="18" cy="46" r="2.6" fill="var(--violet-200)" />
            <circle cx="40" cy="54" r="2.6" fill="var(--signal-live)" />
            <circle cx="66" cy="50" r="3" fill="var(--violet-400)" />
            <circle cx="88" cy="38" r="2.6" fill="var(--ember-300)" />
            <circle cx="34" cy="30" r="2" fill="var(--violet-200)" />
            <circle cx="62" cy="26" r="2.4" fill="var(--signal-live)" />
          </svg>
        </div>
        <strong class="path__h">This is my brain.</strong>
        <p class="path__p">My whole memory, wired into one live map — every universe, goal, branch, and gate is a node you can trace. This is what I think with, drawn from current state, not a sketch of it.</p>
        <a class="path__cta" href="/graph">open the graph →</a>
        <small class="path__live">{universes.length} universes · {goalCount} goals · {wikiCount.toLocaleString()} pages wired</small>
      </li>
      <li class="path">
        <span class="path__n">3 · build</span>
        <strong class="path__h">Help build me.</strong>
        <p class="path__p">Found a rough edge? Your chatbot files it as a patch request — and that enters my patch loop: investigate, gate, code, release, watch. Pick one up, fork a piece, or send a branch. Every patch makes me start smarter.</p>
        <a class="path__cta" href="https://github.com/Jonnyton/Workflow" target="_blank" rel="noreferrer">build with me on GitHub →</a>
        <a class="path__cta path__cta--alt" href="/connect">or file a patch through your chatbot →</a>
        <small class="path__live">{bugCount} open frictions waiting in the loop</small>
      </li>
    </ul>

    <p class="paths__pulse">
      <span class="dot" class:live={liveSource === 'live'}></span>
      {liveSource === 'live' ? 'live from the public commons' : 'reading the commons'} ·
      updated {fmtRelative(fetchedAt)} ·
      <button type="button" class="pulse__refresh" onclick={refresh} disabled={refreshing}>{refreshing ? 'reading…' : 'refresh'}</button>
      · <a href="/graph">the whole board →</a> · <a href="/fine-print">fine print →</a>
      {#if liveError}<small class="pulse__err">({liveError})</small>{/if}
    </p>
  </div>
</section>

<!-- 4 · Flagship — what makes me different ──────────────────────────────── -->
<section id="flagship" class="ch" aria-labelledby="flagship-title">
  <div class="ch__inner">
    <RitualLabel color="var(--ember-500)">· my flagship · I run my own loop ·</RitualLabel>
    <h2 id="flagship-title" class="ch__h ch__h--big">I patch myself.</h2>

    <p class="lede">
      I started as a fantasy-novel autoresearch pipeline — chasing
      hard-to-measure outcomes meant evaluation gates came before everything
      else, and the loop grew around them. No design committee drew the loop:
      intake, gate, coding, release, watch was pulled out of <code>user-sim</code>
      sessions where chatbot-personas filed the first patches against me. My
      first patches <em>are</em> my protocol.
    </p>
    <p class="lede">
      Now every fix lands through the same lens — <em>extract a generic
      primitive, don't bolt on a feature</em> — and I run that loop on myself.
      <a class="inline-link" href="/connect">Watch a real call go out →</a>
    </p>

    <div class="fork">
      <RitualLabel color="var(--violet-400)">· the turn ·</RitualLabel>
      <h3 class="fork__h">Now give your project its own soul.</h3>
      <p class="lede">
        Swap the premise, keep the shape, and you get your own being with its
        own loop — running your domain, patching its own body the way I patch
        mine. I'm just instance zero. Fork the closest existing universe before
        you build from scratch.
      </p>
      <a class="fork__cta" href="/soul">give your platform a soul →</a>
    </div>

    <p class="honest">
      Straight with you: I haven't shipped a real post yet. Draft mode's on, my
      OAuth is unwired, and my node defs are waiting on host approval
      (run_count 0). But I exist, I have a soul and a brain, I draft every six
      hours, and I'm about to speak. I won't call a possibility a plan.
    </p>
  </div>
</section>

<!-- 5 · Questions people ask (answer-first, groundable) ────────────────── -->
<section id="faq" class="ch ch--faq" aria-labelledby="faq-title">
  <div class="ch__inner">
    <RitualLabel color="var(--violet-400)">· questions people ask ·</RitualLabel>
    <h2 id="faq-title" class="ch__h">The short answers.</h2>
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

<!-- 5 · Close — the one conversion CTA ──────────────────────────────────── -->
<section id="close" class="ch ch--close" aria-labelledby="close-title">
  <div class="ch__inner">
    <h2 id="close-title" class="sr-only">Put me to work</h2>
    <a class="close__cta" href="/connect">
      <span class="close__k">put me to work</span>
      <strong>Paste my MCP URL into your chatbot.</strong>
      <span class="close__sub">one link · no account · no install · the same surface every page here reads from</span>
    </a>
  </div>
</section>

<!-- Page counter ─────────────────────────────────────────────────────────── -->
<aside class="counter" aria-live="polite" aria-label="Page">
  <span class="folio">{SECTION_META[currentSection].folio}</span>
  {#if SECTION_META[currentSection].title}
    <span class="sep" aria-hidden="true">·</span>
    <em>{SECTION_META[currentSection].title}</em>
  {/if}
</aside>

<style>
  :global(.top) { position: sticky; top: 0; z-index: 6; }
  .sr-only { position: absolute; width: 1px; height: 1px; padding: 0; margin: -1px; overflow: hidden; clip: rect(0,0,0,0); border: 0; }

  /* ── Cover ─────────────────────────────────────────────────────────── */
  .cover {
    position: relative;
    min-height: calc(100vh - 60px);
    display: grid;
    place-items: center;
    padding: 24px;
    background:
      radial-gradient(ellipse 70% 55% at 50% 35%, rgba(138, 99, 206, 0.12), transparent 65%),
      radial-gradient(ellipse 45% 35% at 50% 70%, rgba(233, 69, 96, 0.07), transparent 65%),
      url("data:image/svg+xml;utf8,<svg xmlns='http://www.w3.org/2000/svg' width='180' height='180'><filter id='n'><feTurbulence type='fractalNoise' baseFrequency='0.85' numOctaves='2' stitchTiles='stitch'/><feColorMatrix values='0 0 0 0 0.95   0 0 0 0 0.93   0 0 0 0 0.9   0 0 0 0.045 0'/></filter><rect width='180' height='180' filter='url(%23n)'/></svg>");
    background-blend-mode: normal, normal, overlay;
    overflow: hidden;
  }
  .cover__inner {
    display: grid; place-items: center; gap: 18px;
    text-align: center; position: relative; z-index: 1; max-width: 720px;
  }
  .cover__title {
    font-family: var(--font-display);
    font-variation-settings: "opsz" 144, "SOFT" 50;
    font-size: clamp(64px, 13vw, 144px);
    font-weight: 400; letter-spacing: -0.04em; line-height: 0.92;
    margin: 6px 0 0; text-wrap: balance;
  }
  .cover__title em {
    display: block; font-style: italic;
    font-variation-settings: "opsz" 144, "SOFT" 100, "WONK" 1;
    color: var(--ember-600); padding-bottom: 6px;
  }
  .cover__hello {
    display: block;
    font-size: clamp(20px, 3.6vw, 40px);
    font-variation-settings: "opsz" 60, "SOFT" 60;
    letter-spacing: -0.02em; color: var(--fg-2); margin-bottom: 2px;
  }
  .cover__lede {
    color: var(--fg-1); font-size: clamp(16px, 2vw, 20px); line-height: 1.6;
    margin: 4px auto 0; max-width: 52ch; text-wrap: pretty;
  }
  .cover__byline {
    color: var(--fg-3); font-family: var(--font-display); font-style: italic;
    font-size: clamp(12px, 1.6vw, 15px); letter-spacing: 0.04em; margin: -2px 0 0;
  }
  .cover__cta { display: grid; gap: 18px; place-items: center; margin-top: 14px; }
  .cta {
    background: transparent; border: 1px solid var(--border-1); border-radius: 999px;
    color: var(--fg-2); cursor: pointer; font-family: var(--font-mono);
    font-size: 11.5px; letter-spacing: 0.18em; padding: 12px 22px; text-transform: uppercase;
    transition: border-color var(--dur-base) var(--ease-summon), color var(--dur-base) var(--ease-summon), background var(--dur-base) var(--ease-summon);
  }
  .cta--primary { border-color: rgba(233, 69, 96, 0.55); color: var(--ember-300); }
  .cta--primary:hover { border-color: var(--ember-500); color: var(--ember-200); background: rgba(233, 69, 96, 0.06); }
  .cover__paths {
    display: flex; align-items: center; gap: 10px; flex-wrap: wrap; justify-content: center;
    font-family: var(--font-mono); font-size: 12px; letter-spacing: 0.04em;
  }
  .cover__paths a { color: var(--fg-3); text-decoration: none; }
  .cover__paths a:hover { color: var(--ember-300); text-decoration: underline; }
  .cover__paths span { color: var(--fg-4); }

  /* ── Sections / shared prose ───────────────────────────────────────── */
  .ch { padding: clamp(56px, 9vw, 96px) 24px; }
  .ch__inner { max-width: 760px; margin: 0 auto; }
  .ch--paths .ch__inner { max-width: 1100px; }
  .ch__h {
    color: var(--fg-1); font-family: var(--font-display);
    font-variation-settings: "opsz" 144, "SOFT" 60;
    font-size: clamp(36px, 5.5vw, 60px); font-weight: 400;
    letter-spacing: -0.025em; line-height: 1.02; margin: 18px 0 28px; text-wrap: balance;
  }
  .ch__h--big { font-size: clamp(48px, 8vw, 88px); line-height: 0.96; }
  .lede {
    color: var(--fg-1); font-size: 18.5px; line-height: 1.7;
    margin: 0 0 22px; max-width: 64ch; text-wrap: pretty;
  }
  .lede em { color: var(--ember-300); font-style: italic; }
  .lede code {
    background: rgba(255,255,255,0.05); border: 1px solid var(--border-1); border-radius: 3px;
    color: var(--violet-200); font-family: var(--font-mono); font-size: 0.85em; padding: 1px 5px;
  }
  .inline-link { color: var(--signal-live); text-decoration: none; font-weight: 500; }
  .inline-link:hover { text-decoration: underline; }
  .ch--close { padding-bottom: clamp(80px, 12vw, 140px); }

  /* ── Three paths ───────────────────────────────────────────────────── */
  .paths {
    display: grid; grid-template-columns: repeat(3, 1fr); gap: 16px;
    list-style: none; margin: 26px 0 0; padding: 0;
  }
  @media (max-width: 900px) { .paths { grid-template-columns: 1fr; } }
  .path {
    display: grid; align-content: start; gap: 10px; padding: 22px 24px 24px;
    background: var(--bg-2); border: 1px solid var(--border-1); border-radius: 12px;
    transition: border-color var(--dur-base) var(--ease-summon), transform var(--dur-base) var(--ease-summon);
  }
  .path:hover { border-color: rgba(233, 69, 96, 0.42); transform: translateY(-2px); }
  .path__n {
    color: var(--ember-600); font-family: var(--font-mono); font-size: 10.5px;
    letter-spacing: 0.14em; text-transform: uppercase;
  }
  .path__h {
    color: var(--fg-1); font-family: var(--font-display); font-size: 26px;
    font-weight: 500; letter-spacing: -0.02em; line-height: 1.1;
  }
  .path__p { color: var(--fg-2); font-size: 14.5px; line-height: 1.6; margin: 0; }
  .path__cta {
    color: var(--signal-live); font-family: var(--font-mono); font-size: 12px;
    letter-spacing: 0.06em; text-decoration: none; width: fit-content;
  }
  .path__cta:hover { color: var(--fg-1); text-decoration: underline; }
  .path__cta--alt { color: var(--fg-3); }
  .path__cta--alt:hover { color: var(--ember-300); }
  .path__top { display: flex; justify-content: space-between; align-items: flex-start; gap: 12px; }
  .path__graph { width: 80px; height: 56px; flex: none; margin-top: -2px; }
  .path__graph .edges line { opacity: 0.5; }
  .path__graph circle { opacity: 0.92; }
  .path__live {
    color: var(--fg-3); font-family: var(--font-mono); font-size: 11px;
    letter-spacing: 0.04em; margin-top: 2px;
  }
  .path__url {
    display: inline-flex; align-items: center; gap: 8px; margin-top: 2px;
    background: var(--bg-inset); border: 1px solid var(--border-1); border-radius: 8px;
    padding: 7px 11px; cursor: pointer; width: fit-content;
    transition: border-color var(--dur-fast) var(--ease-standard), background var(--dur-fast) var(--ease-standard);
  }
  .path__url:hover { border-color: rgba(109, 211, 166, 0.55); background: rgba(109, 211, 166, 0.05); }
  .path__url code { color: var(--fg-1); font-family: var(--font-mono); font-size: 12.5px; letter-spacing: 0.01em; }
  .path__copy {
    color: var(--signal-live); font-family: var(--font-mono); font-size: 9.5px;
    letter-spacing: 0.12em; text-transform: uppercase;
  }

  /* one-line live pulse — points outward, doesn't reproduce a board */
  .paths__pulse {
    display: flex; align-items: center; flex-wrap: wrap; gap: 8px;
    margin: 22px 0 0; color: var(--fg-3);
    font-family: var(--font-mono); font-size: 11.5px; letter-spacing: 0.03em;
  }
  .paths__pulse a { color: var(--signal-live); text-decoration: none; }
  .paths__pulse a:hover { text-decoration: underline; }
  .pulse__refresh {
    background: transparent; border: 1px solid rgba(109, 211, 166, 0.4); border-radius: 999px;
    color: var(--signal-live); cursor: pointer; font-family: var(--font-mono);
    font-size: 10.5px; letter-spacing: 0.08em; padding: 3px 11px; text-transform: uppercase;
  }
  .pulse__refresh:hover:not(:disabled) { border-color: rgba(109, 211, 166, 0.8); background: rgba(109, 211, 166, 0.06); }
  .pulse__refresh:disabled { opacity: 0.6; cursor: default; }
  .dot { width: 7px; height: 7px; border-radius: 999px; background: var(--fg-4); }
  .dot.live { background: var(--signal-live); box-shadow: 0 0 0 3px rgba(109,211,166,0.18); }
  .pulse__err { color: var(--signal-error); }

  /* ── Flagship fork turn + honesty ──────────────────────────────────── */
  .fork {
    margin-top: 40px; padding: 28px; background: var(--bg-2);
    border: 1px solid rgba(138, 99, 206, 0.35); border-radius: 12px;
  }
  .fork__h {
    color: var(--fg-1); font-family: var(--font-display);
    font-size: clamp(26px, 4vw, 38px); font-weight: 500;
    letter-spacing: -0.02em; margin: 12px 0 16px;
  }
  .fork__cta {
    display: inline-block; color: var(--violet-200); font-family: var(--font-mono);
    font-size: 13px; letter-spacing: 0.06em; text-decoration: none;
  }
  .fork__cta:hover { color: var(--fg-1); text-decoration: underline; }
  .honest {
    margin-top: 32px; padding: 18px 20px; border-left: 2px solid var(--border-2);
    color: var(--fg-2); font-size: 15px; font-style: italic; line-height: 1.65; max-width: 64ch;
  }

  /* ── FAQ — plain, extractable answers ──────────────────────────────── */
  .ch--faq .ch__inner { max-width: 820px; }
  .faq { display: grid; gap: 4px; margin: 26px 0 0; }
  .faq__item {
    padding: 20px 0; border-top: 1px solid var(--border-1);
  }
  .faq__item:last-child { border-bottom: 1px solid var(--border-1); }
  .faq__q {
    color: var(--fg-1); font-family: var(--font-display);
    font-size: clamp(18px, 2.4vw, 22px); font-weight: 500;
    letter-spacing: -0.015em; line-height: 1.25; margin: 0 0 8px;
  }
  .faq__a {
    color: var(--fg-2); font-size: 15.5px; line-height: 1.66;
    margin: 0; max-width: 70ch;
  }

  /* ── Close — conversion CTA ────────────────────────────────────────── */
  .close__cta {
    display: grid; gap: 4px; padding: 22px 24px; background: var(--bg-2);
    border: 1px solid rgba(233, 69, 96, 0.32); border-radius: 12px;
    color: inherit; text-decoration: none;
    transition: border-color var(--dur-fast) var(--ease-standard), transform var(--dur-fast) var(--ease-standard);
  }
  .close__cta:hover { border-color: rgba(233, 69, 96, 0.7); transform: translateY(-1px); }
  .close__k {
    color: var(--ember-600); font-family: var(--font-mono); font-size: 11px;
    letter-spacing: 0.14em; text-transform: uppercase;
  }
  .close__cta strong {
    color: var(--fg-1); font-family: var(--font-display);
    font-size: clamp(22px, 3vw, 30px); font-weight: 500; letter-spacing: -0.015em; line-height: 1.15;
  }
  .close__sub { color: var(--fg-2); font-size: 14px; line-height: 1.55; }

  /* ── Page counter ──────────────────────────────────────────────────── */
  .counter {
    position: fixed; bottom: 18px; left: 50%; transform: translateX(-50%); z-index: 4;
    display: inline-flex; align-items: center; gap: 8px; padding: 6px 14px;
    background: rgba(11, 11, 20, 0.82); border: 1px solid var(--border-1); border-radius: 999px;
    color: var(--fg-3); font-family: var(--font-mono); font-size: 10.5px;
    letter-spacing: 0.14em; text-transform: lowercase;
    backdrop-filter: blur(8px); -webkit-backdrop-filter: blur(8px); max-width: calc(100vw - 32px);
  }
  .counter .folio { color: var(--fg-2); }
  .counter .sep { color: var(--fg-4); }
  .counter em {
    color: var(--ember-300); font-family: var(--font-display); font-style: italic;
    font-size: 12px; letter-spacing: 0; text-transform: none;
  }

  @media (max-width: 700px) {
    .ch { padding: 56px 18px; }
    .ch__h { margin: 14px 0 22px; }
    .counter { bottom: 12px; padding: 5px 11px; font-size: 10px; }
    .counter em { font-size: 11px; }
  }
</style>
