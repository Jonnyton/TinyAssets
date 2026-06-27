<!--
  /start — the conversion page. "Field Notes" rebuild, 2026-06-09.
  Canonical replacement for /connect (which becomes an alias later).

  Order: hero (prove the endpoint is up before you paste) → two real connect
  paths (Claude.ai verified, ChatGPT honestly reframed) → four persona
  starter prompts → other ways in (clone / run locally) → close to /goals,
  /loop. Honesty rails: the reachability proof is a live read with a
  read-stamp; no baked liveness; no dead-end "watch this space" cards —
  where a path isn't here yet we link the real status instead.
-->
<script lang="ts">
  import { onMount } from 'svelte';
  import { fetchVitals, type Vitals } from '$lib/mcp/live';
  import { fmtRel } from '$lib/fmt';
  import Tick from '$lib/components/Tick.svelte';
  import Term from '$lib/components/Term.svelte';

  const MCP_URL = 'https://tinyassets.io/mcp';
  const MCP_BARE = MCP_URL.replace('https://', '');
  const GH_REPO = 'https://github.com/Jonnyton/TinyAssets';
  const GH_ISSUES = 'https://github.com/Jonnyton/TinyAssets/issues';
  const GH_CONTRIBUTING = 'https://github.com/Jonnyton/TinyAssets/blob/main/CONTRIBUTING.md';

  // ── Copyable MCP URL chip (same idiom as home's urlchip). ──
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

  // ── Live reachability proof — read before you paste. Never baked. ──
  let vitals = $state<Vitals | null>(null);
  let reading = $state(true);
  async function refreshPulse() {
    reading = true;
    vitals = await fetchVitals();
    reading = false;
  }
  onMount(() => { void refreshPulse(); });

  // ── Six persona starter prompts — each copyable, each works today
  // via the universe / goals / wiki tools. ──
  type Prompt = { persona: string; flavor: string; text: string };
  const PROMPTS: Prompt[] = [
    {
      persona: 'The researcher',
      flavor: 'orient first',
      text: 'Tiny: inspect my universe and show me what goals exist.'
    },
    {
      persona: 'The maker',
      flavor: 'build something',
      text: 'Help me design a workflow toward <my goal> and run a dry run.'
    },
    {
      persona: 'The novelist',
      flavor: 'long project',
      text: 'Create a universe for my novel <title> with my premise, and propose a goal with a ladder toward a finished draft.'
    },
    {
      persona: 'The shop owner',
      flavor: 'commerce, carefully',
      text: 'Draft me a product packet for <idea> and stop before anything publishes or spends money.'
    },
    {
      persona: 'The curious',
      flavor: 'see the whole thing',
      text: 'Browse the public commons and tell me what this platform is working on right now.'
    },
    {
      persona: 'The contributor',
      flavor: 'file friction',
      text: 'File a patch request about <a rough edge I hit>.'
    }
  ];

  let copiedPrompt = $state<number | null>(null);
  let promptTimer: number | null = null;
  async function copyPrompt(i: number, text: string) {
    try {
      await navigator.clipboard.writeText(text);
      copiedPrompt = i;
      if (promptTimer) clearTimeout(promptTimer);
      promptTimer = window.setTimeout(() => (copiedPrompt = null), 1800);
    } catch { /* clipboard unavailable; the prompt is visible anyway */ }
  }
</script>

<svelte:head>
  <title>Start — connect your chatbot to Tiny</title>
  <meta
    name="description"
    content="Connect your chatbot to Tiny with one URL. Prove the endpoint is live before you paste, follow the Claude.ai or any-MCP-client steps, and bring a starter prompt that works today."
  />
</svelte:head>

<!-- 1 · Hero — prove the door is open, then paste ───────────────────────── -->
<section class="cover" aria-labelledby="cover-title">
  <div class="container cover__grid">
    <div class="cover__main">
      <p class="eyebrow">how to connect · entry one</p>
      <h1 id="cover-title" class="cover__title">Connect your chatbot.</h1>
      <p class="cover__lede">
        One URL turns any
        <Term def="MCP — the Model Context Protocol. The open standard chatbots use to add outside tools. Tiny is one such tool.">MCP</Term>-capable
        chatbot into a control station for Tiny: it can browse the public
        commons, design workflows with you, and start real runs. No account,
        no install — just paste the address below into your assistant's
        connector settings.
      </p>
      <div class="cover__actions">
        <button type="button" class="urlchip" onclick={copyUrl} aria-label="Copy the MCP URL">
          <code>{MCP_BARE}</code>
          <span class="urlchip__copy">{copied ? 'copied ✓' : 'copy'}</span>
        </button>
        <a class="cover__skip" href="#paths">jump to the steps ↓</a>
      </div>
    </div>

    <div class="cover__pulse">
      <p class="eyebrow">is the door open? read it yourself</p>
      <div class="pulse" aria-live="polite">
        {#if reading && !vitals}
          <span class="pulse__row"><span class="dot" aria-hidden="true"></span><span class="pulse__k">reading the endpoint…</span></span>
        {:else if vitals && !vitals.reachable}
          <span class="pulse__row"><span class="dot error" aria-hidden="true"></span><span class="pulse__k">endpoint unreachable from your browser</span></span>
          <span class="pulse__sub ev">this is a true reading — {vitals.error}</span>
          <button class="pulse__refresh" onclick={refreshPulse} disabled={reading}>{reading ? 'reading…' : 'Refresh MCP'}</button>
        {:else if vitals}
          <span class="pulse__row">
            <span class="dot live" aria-hidden="true"></span>
            <span class="pulse__k">engine live</span>
          </span>
          {#if vitals.deployedAt}
            <span class="pulse__sub ev">deployed {fmtRel(vitals.deployedAt)}{#if vitals.gitSha}&nbsp;· {vitals.gitSha}{/if}</span>
          {/if}
          <span class="pulse__row pulse__row--quiet">
            <span class="dot" class:live={vitals.loopAwake} class:idle={!vitals.loopAwake} aria-hidden="true"></span>
            <span class="pulse__k">{vitals.loopAwake ? 'loop awake' : 'loop asleep'}</span>
          </span>
          <span class="pulse__stamp ev">
            read {fmtRel(vitals.fetchedAt)}
            · <button class="pulse__refresh" onclick={refreshPulse} disabled={reading}>{reading ? 'reading…' : 'Refresh MCP'}</button>
          </span>
          <span class="pulse__tick"><Tick href="/fine-print" label="how this is measured" /></span>
        {/if}
      </div>
      <p class="cover__pulse-note voice">
        — you're reading my pulse through the same door you're about to
        walk through.
      </p>
    </div>
  </div>
</section>

<!-- 1.5 · Before you paste — two honest things ──────────────────────────── -->
<section class="ch ch--honest" aria-labelledby="honest-title">
  <div class="container ch__inner ch__inner--wide">
    <p class="eyebrow">before you paste · two honest things</p>
    <h2 id="honest-title">Where your work lives.</h2>
    <div class="honest">
      <article class="honest__card">
        <h3 class="honest__h">Public by default</h3>
        <p class="honest__p">
          Work you do on the public engine lands in a public,
          forkable <Term def="The commons — the shared, public store of universes, workflows, and runs. Anyone can read it, and anyone can fork from it.">commons</Term>
          that anyone can read.
        </p>
        <p class="honest__p">
          Keeping work private currently means running the engine yourself —
          <a href="/host">see how to host it</a>.
        </p>
      </article>
      <article class="honest__card">
        <h3 class="honest__h">Yours to take</h3>
        <p class="honest__p">
          Universes and the commons are plain files in an open-source store, so
          you can export your work at any time.
        </p>
        <p class="honest__p">
          The engine's code is <strong>MIT-licensed</strong> on
          <a href={GH_REPO} target="_blank" rel="noreferrer">GitHub ↗</a>.
        </p>
      </article>
    </div>
    <p class="honest__cap voice">
      — no surprises after the paste. This is the deal up front.
    </p>
  </div>
</section>

<!-- 2 · Two real connect paths ──────────────────────────────────────────── -->
<section id="paths" class="ch ch--paths" aria-labelledby="paths-title">
  <div class="container">
    <p class="eyebrow">entry two · the two simple steps</p>
    <h2 id="paths-title">Add the URL, then talk.</h2>
    <p class="paths__lede">
      Connecting is two steps in any client: register the connector, then
      start a chat with it enabled. The exact menu path differs per chatbot —
      here are the two that work today.
    </p>

    <div class="paths">
      <article class="connect">
        <header class="connect__head">
          <strong class="connect__name">Claude.ai</strong>
          <span class="connect__badge connect__badge--live">works today</span>
        </header>
        <p class="connect__who">
          Best path if Claude is where you already ask for help. Free, Pro,
          Max, Team, and Enterprise can add a custom remote connector, within
          plan limits.
        </p>
        <ol class="connect__steps">
          <li><span class="connect__n">1</span><span class="connect__t">Open <strong>Settings → Connectors</strong>.</span></li>
          <li><span class="connect__n">2</span><span class="connect__t">Choose <strong>Add custom connector</strong>.</span></li>
          <li><span class="connect__n">3</span><span class="connect__t">Paste <code>{MCP_BARE}</code> and approve it.</span></li>
          <li><span class="connect__n">4</span><span class="connect__t">Start a chat with the connector enabled and send a starter prompt below.</span></li>
        </ol>
        <p class="connect__note">
          The custom-URL path is the current one. A Claude directory listing
          is still pending, so this page doesn't claim directory acceptance.
        </p>
      </article>

      <article class="connect">
        <header class="connect__head">
          <strong class="connect__name">ChatGPT &amp; other MCP clients</strong>
          <span class="connect__badge connect__badge--partial">depends on the client</span>
        </header>
        <p class="connect__who">
          The same URL is a standard remote MCP server, so any MCP-capable
          client connects the same way — paste it into the connector / remote
          MCP field.
        </p>
        <ol class="connect__steps">
          <li><span class="connect__n">1</span><span class="connect__t">Open your client's <strong>connectors / MCP servers</strong> setting.</span></li>
          <li><span class="connect__n">2</span><span class="connect__t">Add <code>{MCP_BARE}</code> as a Streamable HTTP / remote MCP server.</span></li>
          <li><span class="connect__n">3</span><span class="connect__t">Enable it in a chat and send a starter prompt below.</span></li>
        </ol>
        <p class="connect__note">
          So which should you use today? The reliable path is
          <strong>Claude.ai</strong> — or any client that supports custom MCP
          connectors. On ChatGPT specifically, custom connectors require a paid
          plan with developer mode turned on, and availability still varies by
          workspace and region. We track where that actually stands here:
          <a href={GH_ISSUES} target="_blank" rel="noreferrer">current TinyAssets status on GitHub ↗</a>.
        </p>
      </article>
    </div>
  </div>
</section>

<!-- 3 · What to say first ───────────────────────────────────────────────── -->
<section class="ch ch--prompts" aria-labelledby="prompts-title">
  <div class="container">
    <p class="eyebrow">entry three · what to say first</p>
    <h2 id="prompts-title">Bring a first sentence.</h2>
    <p class="prompts__lede voice">
      — connected and not sure what to ask? Here are six openers, one per
      kind of visitor. Each works today through my universe, goals, and
      commons tools. Swap the bracketed bits for your own.
    </p>

    <ul class="prompts">
      {#each PROMPTS as p, i (p.persona)}
        <li class="prompt">
          <div class="prompt__head">
            <span class="prompt__persona">{p.persona}</span>
            <span class="prompt__flavor ev">{p.flavor}</span>
          </div>
          <button
            type="button"
            class="prompt__block"
            onclick={() => copyPrompt(i, p.text)}
            aria-label={`Copy prompt: ${p.text}`}
          >
            <code class="prompt__text">{p.text}</code>
            <span class="prompt__copy">{copiedPrompt === i ? 'copied ✓' : 'copy'}</span>
          </button>
        </li>
      {/each}
    </ul>
    <p class="prompts__foot">
      Wondering what a "goal" or the "commons" is? Open the live
      <a href="/goals">goals board</a> — it reads the real list straight from
      the engine.
    </p>
  </div>
</section>

<!-- 4 · Other ways in ───────────────────────────────────────────────────── -->
<section class="ch ch--oss" aria-labelledby="oss-title">
  <div class="container ch__inner ch__inner--wide">
    <p class="eyebrow">entry four · other ways in</p>
    <h2 id="oss-title">Or run the engine yourself.</h2>
    <p class="oss__lede">
      <strong>TinyAssets</strong> is the open-source platform.
      <strong>Tiny</strong> is the intelligence you meet through the connector
      above. You don't need to host anything to use it — but if you'd rather
      run it locally or read the code, both paths are real.
    </p>
    <div class="oss">
      <article class="oss__card">
        <h3 class="oss__h">Clone the repo</h3>
        <p class="oss__p">
          Read the engine, the loop, and every workflow definition. It's all
          public.
        </p>
        <pre class="oss__pre"><code>git clone {GH_REPO}.git</code></pre>
        <a class="oss__cta" href={GH_REPO} target="_blank" rel="noreferrer">TinyAssets on GitHub ↗</a>
      </article>
      <article class="oss__card">
        <h3 class="oss__h">Run it locally</h3>
        <p class="oss__p">
          Python 3.11+. Install in editable mode and you have a local daemon
          to work against.
        </p>
        <pre class="oss__pre"><code>pip install -e .</code></pre>
        <a class="oss__cta" href={GH_CONTRIBUTING} target="_blank" rel="noreferrer">CONTRIBUTING.md ↗</a>
      </article>
    </div>
  </div>
</section>

<!-- 5 · Close ───────────────────────────────────────────────────────────── -->
<section class="ch ch--close" aria-labelledby="close-title">
  <div class="container ch__inner">
    <h2 id="close-title">Connected. Now look around.</h2>
    <nav class="close__cards">
      <a class="close__card" href="/goals">
        <span class="close__k eyebrow">the goals board</span>
        <strong>See what's already running →</strong>
        <span class="close__sub">live public goals, each with its outcome ladder.</span>
      </a>
      <a class="close__card" href="/loop">
        <span class="close__k eyebrow">the patch loop</span>
        <strong>Watch how it maintains itself →</strong>
        <span class="close__sub">friction becomes a patch request, a real PR, a release.</span>
      </a>
    </nav>
  </div>
</section>

<style>
  .container { max-width: 1160px; margin: 0 auto; padding-inline: clamp(18px, 4vw, 32px); }

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
    font-size: clamp(44px, 7vw, 88px);
    font-weight: 400;
    line-height: 1.0;
    letter-spacing: -0.03em;
    margin: 14px 0 18px;
  }
  .cover__lede { margin: 0 0 22px; font-size: clamp(16px, 1.7vw, 18px); line-height: 1.62; color: var(--fg-2); max-width: 56ch; }
  .cover__actions { display: flex; align-items: center; gap: 16px; flex-wrap: wrap; }
  .cover__skip { font-family: var(--font-sans); font-size: 13px; font-weight: 500; color: var(--fg-3); }

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

  /* ── Hero pulse ── */
  .cover__pulse { display: grid; gap: 10px; align-content: start; padding-top: clamp(0px, 2vw, 30px); }
  .pulse {
    display: grid; gap: 7px; justify-items: start;
    padding: 14px 16px;
    border: 1px solid var(--border-1);
    border-radius: var(--radius-md);
    background: var(--bg-2);
    width: 100%;
  }
  .pulse__row { display: inline-flex; align-items: center; gap: 9px; }
  .pulse__row--quiet { opacity: 0.92; }
  .pulse__k { font-family: var(--font-sans); font-size: 13px; font-weight: 500; color: var(--fg-1); white-space: nowrap; }
  .pulse__sub { font-size: 11px; color: var(--fg-3); padding-left: 16px; }
  .pulse__stamp { display: inline-flex; align-items: center; gap: 8px; flex-wrap: wrap; font-size: 11px; color: var(--fg-3); }
  .pulse__tick { font-size: 10px; }
  .pulse__refresh {
    background: transparent; border: 1px solid var(--border-2); border-radius: var(--radius-pill);
    color: var(--live-700); cursor: pointer;
    font-family: var(--font-mono); font-size: 10px; letter-spacing: 0.08em; text-transform: uppercase;
    padding: 3px 10px;
    transition: border-color var(--dur-fast) var(--ease-standard), background var(--dur-fast) var(--ease-standard);
  }
  .pulse__refresh:hover:not(:disabled) { border-color: var(--live-600); background: var(--live-100); }
  .pulse__refresh:disabled { opacity: 0.6; cursor: default; }
  .cover__pulse-note {
    font-size: 14px; font-style: italic; color: var(--fg-3);
    line-height: 1.55; max-width: 40ch; margin: 0;
  }

  /* ── Shared section chrome ── */
  .ch { padding: clamp(52px, 8vw, 88px) 0; border-bottom: 1px solid var(--border-1); }
  .ch__inner { max-width: 760px; }
  .ch__inner--wide { max-width: 920px; }
  .ch h2 {
    font-size: clamp(28px, 4.4vw, 46px);
    font-weight: 500;
    line-height: 1.06;
    letter-spacing: -0.02em;
    margin: 12px 0 18px;
  }
  .ch .eyebrow { display: block; }

  /* ── Before you paste — two honest things ── */
  .honest { display: grid; grid-template-columns: repeat(2, 1fr); gap: 16px; margin-top: 26px; }
  @media (max-width: 760px) { .honest { grid-template-columns: 1fr; } }
  .honest__card {
    display: grid; gap: 8px; align-content: start;
    padding: 22px;
    background: var(--bg-2);
    border: 1px solid var(--border-1);
    border-radius: var(--radius-lg);
  }
  .honest__h { font-size: 17px; margin: 0; color: var(--fg-1); }
  .honest__p { font-size: 14px; line-height: 1.58; color: var(--fg-2); margin: 0; max-width: 52ch; }
  .honest__p strong { color: var(--fg-1); font-weight: 600; }
  .honest__cap {
    font-size: 14px; font-style: italic; color: var(--fg-3);
    line-height: 1.55; margin: 18px 0 0; max-width: 48ch;
  }

  /* ── Two connect paths ── */
  .paths__lede { font-size: 15px; line-height: 1.6; color: var(--fg-2); max-width: 64ch; margin: 0 0 8px; }
  .paths {
    display: grid; grid-template-columns: repeat(2, 1fr); gap: 18px; margin-top: 28px;
  }
  @media (max-width: 900px) { .paths { grid-template-columns: 1fr; } }
  .connect {
    display: grid; gap: 12px; align-content: start;
    padding: 24px;
    background: var(--bg-2);
    border: 1px solid var(--border-1);
    border-radius: var(--radius-lg);
  }
  .connect__head { display: flex; align-items: center; justify-content: space-between; gap: 10px; }
  .connect__name { font-family: var(--font-display); font-size: 20px; font-weight: 500; letter-spacing: -0.01em; color: var(--fg-1); }
  .connect__badge {
    font-family: var(--font-mono); font-size: 9.5px; letter-spacing: 0.1em; text-transform: uppercase;
    padding: 3px 9px; border-radius: var(--radius-pill); border: 1px solid var(--border-1);
    color: var(--fg-3); white-space: nowrap;
  }
  .connect__badge--live { color: var(--live-700); border-color: var(--live-600); background: var(--live-100); }
  .connect__badge--partial { color: var(--signal-warn); border-color: rgba(201, 111, 36, 0.45); }
  .connect__who { font-size: 14px; line-height: 1.55; color: var(--fg-2); margin: 0; }
  .connect__steps { list-style: none; margin: 4px 0; padding: 0; display: grid; gap: 9px; }
  .connect__steps li {
    display: grid; grid-template-columns: 22px 1fr; gap: 10px; align-items: baseline;
    font-size: 14px; line-height: 1.5; color: var(--fg-2);
  }
  .connect__t { min-width: 0; overflow-wrap: anywhere; }
  .connect__steps strong { color: var(--fg-1); font-weight: 600; }
  .connect__steps code { font-size: 12px; }
  .connect__n {
    font-family: var(--font-mono); font-size: 11px; color: var(--ember-700);
    font-weight: 500; align-self: start; padding-top: 1px;
  }
  .connect__note {
    font-size: 12.5px; line-height: 1.55; color: var(--fg-3);
    margin: 2px 0 0; padding-top: 12px; border-top: 1px solid var(--border-1); max-width: none;
  }

  /* ── Starter prompts ── */
  .prompts__lede { margin: 0 0 8px; color: var(--fg-2); }
  .prompts {
    list-style: none; margin: 28px 0 0; padding: 0;
    display: grid; grid-template-columns: repeat(2, 1fr); gap: 16px;
  }
  @media (max-width: 760px) { .prompts { grid-template-columns: 1fr; } }
  .prompt { display: grid; gap: 8px; }
  .prompt__head { display: flex; align-items: baseline; justify-content: space-between; gap: 10px; }
  .prompt__persona { font-family: var(--font-voice); font-size: 16px; font-weight: 500; color: var(--fg-1); }
  .prompt__flavor { font-size: 10.5px; color: var(--fg-3); text-transform: lowercase; }
  .prompt__block {
    display: flex; align-items: flex-start; justify-content: space-between; gap: 12px;
    width: 100%; text-align: left;
    padding: 14px 15px;
    background: var(--bg-inset);
    border: 1px solid var(--border-1);
    border-radius: var(--radius-md);
    cursor: pointer;
    transition: border-color var(--dur-fast) var(--ease-standard), background var(--dur-fast) var(--ease-standard);
  }
  .prompt__block:hover { border-color: var(--live-600); background: var(--live-100); }
  .prompt__text {
    background: none; border: none; padding: 0; color: var(--fg-1);
    font-size: 13px; line-height: 1.5; white-space: normal;
  }
  .prompt__copy {
    flex: none; font-family: var(--font-mono); font-size: 9.5px; letter-spacing: 0.12em;
    text-transform: uppercase; color: var(--live-700); padding-top: 2px;
  }
  .prompts__foot { font-size: 13px; line-height: 1.6; color: var(--fg-3); margin: 20px 0 0; max-width: 64ch; }

  /* ── Other ways in ── */
  .oss__lede { font-size: 15px; line-height: 1.62; color: var(--fg-2); margin: 0 0 8px; max-width: 64ch; }
  .oss__lede strong { color: var(--fg-1); font-weight: 600; }
  .oss { display: grid; grid-template-columns: repeat(2, 1fr); gap: 16px; margin-top: 26px; }
  @media (max-width: 760px) { .oss { grid-template-columns: 1fr; } }
  .oss__card {
    display: grid; gap: 10px; align-content: start;
    padding: 22px;
    background: var(--bg-2);
    border: 1px solid var(--border-1);
    border-radius: var(--radius-lg);
  }
  .oss__h { font-size: 19px; margin: 0; }
  .oss__p { font-size: 14px; line-height: 1.55; color: var(--fg-2); margin: 0; }
  .oss__pre { margin: 2px 0 4px; padding: 11px 13px; font-size: 12.5px; }
  .oss__pre code { font-size: 12.5px; }
  .oss__cta { font-family: var(--font-sans); font-size: 13.5px; font-weight: 600; color: var(--ember-700); width: fit-content; }

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
