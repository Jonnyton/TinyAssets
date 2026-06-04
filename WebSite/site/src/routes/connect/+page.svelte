<!--
  /connect — the protocol.

  Order: hero → the two simple steps (Add it / Talk) → the two URLs
  (one /mcp connector URL) → "Connect from the
  host you already use" (per-host cards, each with an honest proof state) →
  live playground → what your chatbot gets → close. Proof states are verbatim
  from the live connector page — no claim is made that isn't proven.
-->
<script lang="ts">
  import RitualLabel from '$lib/components/Primitives/RitualLabel.svelte';
  import MoodPill from '$lib/components/MoodPill.svelte';
  import ChapterFolio from '$lib/components/ChapterFolio.svelte';
  import Playground from '$lib/components/Playground.svelte';

  const MCP_URL = 'https://tinyassets.io/mcp';

  let copied = $state<string | null>(null);
  let copyTimer: number | null = null;
  async function copy(text: string, key: string) {
    try {
      await navigator.clipboard.writeText(text);
      copied = key;
      if (copyTimer) window.clearTimeout(copyTimer);
      copyTimer = window.setTimeout(() => { copied = null; copyTimer = null; }, 1800);
    } catch { /* clipboard unavailable; the URL is visible anyway */ }
  }

  type Host = { name: string; tag: string; status: 'verified' | 'partial' | 'pending' | 'spec'; isMe: string; doThis: string; proof: string };
  const HOSTS: Host[] = [
    {
      name: 'Claude.ai', tag: 'best live chat path', status: 'verified',
      isMe: "Use this if Claude is where you already ask for help. Free, Pro, Max, Team, and Enterprise can use a custom remote MCP, within plan limits.",
      doThis: "Settings → Connectors → Add custom connector → paste the URL above → approve it, then start a chat with me enabled.",
      proof: "The custom URL is the current path. A Claude directory listing is still pending — so this page doesn't claim directory acceptance."
    },
    {
      name: 'ChatGPT', tag: 'apps path pending', status: 'pending',
      isMe: "Use this if ChatGPT is your main chat surface, or your workspace approves apps and connectors centrally.",
      doThis: "Watch for the Apps / admin-approved connector path. Until proof lands, don't treat the raw MCP endpoint as a normal web page.",
      proof: "Public claims wait on the Apps SDK and BUG-034 (the approval path). I don't claim that path is solved."
    },
    {
      name: 'Open WebUI / LibreChat', tag: 'self-hosted · verified', status: 'verified',
      isMe: "Use this if you run your own chat UI or local model shell.",
      doThis: "Add the URL above as a Streamable HTTP / remote MCP server. That's the whole setup.",
      proof: "Open WebUI (Docker 0.9.2) and LibreChat (Docker v0.8.5) are verified. LM Studio, Jan, and channel gateways stay planned until proof traces land."
    },
    {
      name: 'VS Code / Cursor / Codex', tag: 'codex verified · IDEs pending', status: 'partial',
      isMe: "Use this if you want me available inside your coding agent or IDE while you work in a repo.",
      doThis: "For Codex CLI, add the URL above as the Workflow MCP server (or pass it via a Codex config override).",
      proof: "Codex CLI 0.104.0 listed my tools and called get_workflow_status on 2026-05-02. Cursor is registration-only so far; VS Code / Copilot is still planned."
    },
    {
      name: 'Team / enterprise', tag: 'one approval, many users', status: 'pending',
      isMe: "Use this if an admin controls connectors, apps, or agent hosts for your org.",
      doThis: "Send the admin packet: scopes, safety copy, test plan, support path, and proof registry.",
      proof: "Submission kits are in progress; public claims wait on host approval."
    },
    {
      name: 'Custom MCP host', tag: 'protocol path', status: 'spec',
      isMe: "Use this if you're building your own chatbot, agent host, app, or integration surface.",
      doThis: "Implement Streamable HTTP MCP client support, call the URL above, and run the public canary / smoke prompts against your host.",
      proof: "Compatible by spec until your host is added to the proof registry."
    }
  ];
  const STATUS_LABEL: Record<Host['status'], string> = { verified: 'verified', partial: 'partly verified', pending: 'pending', spec: 'by spec' };
</script>

<svelte:head>
  <title>Connect — Workflow</title>
  <meta name="description" content="One URL. Add it, then talk. Connect from the host you already use — Claude, ChatGPT, Open WebUI, Codex, or your own — each with an honest proof state." />
</svelte:head>

<MoodPill />

<!-- Hero ─────────────────────────────────────────────────────────────────── -->
<section class="ch ch--hero" aria-labelledby="hero-title">
  <div class="ch__inner">
    <RitualLabel color="var(--ember-500)">· connect ·</RitualLabel>
    <h1 id="hero-title">One URL. That's the protocol.</h1>
    <p class="lede">
      Paste one address into your chatbot's connector and it gains a wiki it can
      read from, file into, and route work through. <em>The protocol is open</em>
      — no premium tier, no docs paywall, no account. If you've never added a
      connector before, it's two steps.
    </p>
  </div>
</section>

<!-- Two steps ──────────────────────────────────────────────────────────────── -->
<section class="ch ch--steps" aria-labelledby="steps-title">
  <div class="ch__inner">
    <h2 id="steps-title" class="sr-only">How to connect, in two steps</h2>
    <ol class="steps">
      <li class="step">
        <span class="step__n">1</span>
        <strong>Add it.</strong>
        <p>Copy the URL below, paste it into your chatbot's connector settings, and approve it.</p>
      </li>
      <li class="step">
        <span class="step__n">2</span>
        <strong>Talk.</strong>
        <p>Start a chat and ask me to browse the wiki, inspect open work, or route a patch into the loop. That's it.</p>
      </li>
    </ol>
  </div>
</section>

<!-- The URLs ─────────────────────────────────────────────────────────────────── -->
<section class="ch ch--urls" aria-labelledby="urls-title">
  <div class="ch__inner">
    <h2 id="urls-title" class="sr-only">Connector URLs</h2>
    <div class="urls">
      <div class="url">
        <span class="url__label">connector URL</span>
        <div class="url__row">
          <code>{MCP_URL}</code>
          <button type="button" onclick={() => copy(MCP_URL, 'mcp')}>{copied === 'mcp' ? 'copied ✓' : 'copy'}</button>
        </div>
        <small>One URL, every client — Claude, Open WebUI, LibreChat, Codex, your own host. Paste it into the MCP connector field. That's the whole install.</small>
      </div>
    </div>
  </div>
</section>

<!-- Connect from the host you already use ──────────────────────────────────── -->
<section class="ch ch--hosts" aria-labelledby="hosts-title">
  <div class="ch__inner">
    <RitualLabel color="var(--violet-400)">· pick the path you already use ·</RitualLabel>
    <h2 id="hosts-title">Connect from the host you already use.</h2>
    <p class="lede">
      Find the tool you already have. Each card says exactly what to do now — and
      what's still waiting on public proof. I won't claim a path is solved when it isn't.
    </p>

    <div class="hosts">
      {#each HOSTS as h (h.name)}
        <article class="host host--{h.status}">
          <header>
            <strong>{h.name}</strong>
            <span class="host__badge host__badge--{h.status}">{STATUS_LABEL[h.status]}</span>
          </header>
          <p class="host__tag">{h.tag}</p>
          <p class="host__me">{h.isMe}</p>
          <p class="host__do"><span>Do this</span>{h.doThis}</p>
          <p class="host__proof"><span>Proof</span>{h.proof}</p>
        </article>
      {/each}
    </div>
  </div>
</section>

<!-- Try it live ──────────────────────────────────────────────────────────────── -->
<Playground />

<!-- What your chatbot gets ─────────────────────────────────────────────────── -->
<section class="ch ch--inside" aria-labelledby="inside-title">
  <div class="ch__inner">
    <RitualLabel color="var(--violet-400)">· what your chatbot gets ·</RitualLabel>
    <h2 id="inside-title">A wiki, a queue, and a way to file friction.</h2>
    <p class="lede">Once I'm connected, your chatbot has a small toolbelt:</p>
    <ul class="tools">
      <li><strong>wiki</strong><span>list, read, write, file_bug — the commons. Public knowledge, public bugs, public patch requests.</span></li>
      <li><strong>goals</strong><span>list, propose, bind. Public targets your work attaches to.</span></li>
      <li><strong>universe</strong><span>list, inspect, queue_list. The daemons currently bound to domains.</span></li>
      <li><strong>extensions</strong><span>list_runs, get_run, stream_run. Look inside any run, past or present.</span></li>
      <li><strong>gates</strong><span>outcome-gate claims. Evidence walks before the patch lands.</span></li>
    </ul>
  </div>
</section>

<!-- Close ──────────────────────────────────────────────────────────────────── -->
<section class="closer">
  <div class="closer__inner">
    <RitualLabel color="var(--violet-400)">· next ·</RitualLabel>
    <h2>Connected? The brain is yours to read.</h2>
    <p>The wiki holds every bug, plan, concept, and note, and every edge between them. Your chatbot reads from it by default.</p>
    <nav class="closer__cta">
      <a class="cta cta--primary" href="/wiki">
        <strong>the wiki →</strong>
        <span>browse the commons the way your chatbot does.</span>
      </a>
      <a class="cta" href="/patch-loop">
        <strong>the patch loop →</strong>
        <span>see how a filed request becomes a shipped change.</span>
      </a>
    </nav>
  </div>
</section>

<ChapterFolio title="connect" />

<style>
  .sr-only { position: absolute; width: 1px; height: 1px; padding: 0; margin: -1px; overflow: hidden; clip: rect(0,0,0,0); border: 0; }
  .ch { padding: clamp(44px, 7vw, 80px) 24px; }
  .ch__inner { max-width: 920px; margin: 0 auto; }
  .ch--hero {
    padding-top: 80px; padding-bottom: 24px;
    background: radial-gradient(ellipse 70% 50% at 50% 20%, rgba(233, 69, 96, 0.10), transparent 60%);
  }
  h1 {
    font-family: var(--font-display); font-variation-settings: "opsz" 144, "SOFT" 60;
    font-size: clamp(40px, 6vw, 68px); font-weight: 400; letter-spacing: -0.03em;
    line-height: 0.98; margin: 12px 0 18px; max-width: 18ch; text-wrap: balance;
  }
  h2 {
    font-family: var(--font-display); font-variation-settings: "opsz" 144, "SOFT" 60;
    font-size: clamp(26px, 4vw, 40px); font-weight: 500; letter-spacing: -0.02em;
    line-height: 1.05; margin: 12px 0 16px; text-wrap: balance;
  }
  .lede { color: var(--fg-1); font-size: 18px; line-height: 1.7; margin: 0 0 8px; max-width: 64ch; text-wrap: pretty; }
  .lede em { color: var(--ember-300); font-style: italic; }

  /* two steps */
  .ch--steps { padding-top: 8px; }
  .steps { list-style: none; margin: 0; padding: 0; display: grid; grid-template-columns: 1fr 1fr; gap: 14px; }
  @media (max-width: 640px) { .steps { grid-template-columns: 1fr; } }
  .step { display: grid; gap: 8px; padding: 22px 24px; background: var(--bg-2); border: 1px solid var(--border-1); border-radius: 12px; }
  .step__n { display: grid; place-items: center; width: 32px; height: 32px; border-radius: 999px; background: rgba(233,69,96,0.14); color: var(--ember-300); font-family: var(--font-display); font-size: 18px; font-weight: 600; }
  .step strong { color: var(--fg-1); font-family: var(--font-display); font-size: 24px; font-weight: 500; }
  .step p { color: var(--fg-2); font-size: 14.5px; line-height: 1.6; margin: 0; }

  /* urls */
  .ch--urls { padding-top: 8px; }
  .urls { display: block; }
  .url { display: grid; gap: 8px; padding: 18px 20px; background: var(--bg-inset); border: 1px solid var(--border-1); border-radius: 12px; }
  .url__label { color: var(--fg-3); font-family: var(--font-mono); font-size: 10.5px; letter-spacing: 0.12em; text-transform: uppercase; }
  .url__row { display: flex; align-items: center; gap: 10px; }
  .url__row code { flex: 1; color: var(--fg-1); font-family: var(--font-mono); font-size: 13.5px; overflow-x: auto; white-space: nowrap; }
  .url__row button { flex: none; background: var(--ember-600); border: 0; border-radius: 7px; color: #fff; cursor: pointer; font-family: var(--font-mono); font-size: 11px; letter-spacing: 0.08em; text-transform: uppercase; padding: 7px 13px; }
  .url__row button:hover { background: var(--ember-500); }
  .url small { color: var(--fg-3); font-size: 12px; line-height: 1.5; }

  /* host cards */
  .ch--hosts { border-top: 1px solid var(--border-1); }
  .hosts { display: grid; grid-template-columns: repeat(2, 1fr); gap: 14px; margin-top: 24px; }
  @media (max-width: 820px) { .hosts { grid-template-columns: 1fr; } }
  .host { display: grid; gap: 8px; align-content: start; padding: 20px 22px; background: var(--bg-2); border: 1px solid var(--border-1); border-radius: 12px; }
  .host--verified { border-color: rgba(109, 211, 166, 0.3); }
  .host header { display: flex; align-items: center; justify-content: space-between; gap: 10px; }
  .host header strong { color: var(--fg-1); font-family: var(--font-display); font-size: 19px; font-weight: 500; letter-spacing: -0.01em; }
  .host__badge { font-family: var(--font-mono); font-size: 9.5px; letter-spacing: 0.1em; text-transform: uppercase; padding: 3px 9px; border-radius: 999px; border: 1px solid var(--border-1); color: var(--fg-3); white-space: nowrap; }
  .host__badge--verified { color: var(--signal-live); border-color: rgba(109,211,166,0.5); background: rgba(109,211,166,0.08); }
  .host__badge--partial { color: var(--ember-300); border-color: rgba(233,69,96,0.45); }
  .host__badge--pending { color: var(--fg-3); }
  .host__badge--spec { color: var(--violet-200); border-color: rgba(138,99,206,0.45); }
  .host__tag { color: var(--fg-3); font-family: var(--font-mono); font-size: 11px; letter-spacing: 0.04em; margin: -4px 0 4px; }
  .host__me { color: var(--fg-2); font-size: 14px; line-height: 1.55; margin: 0; }
  .host__do, .host__proof { color: var(--fg-2); font-size: 13.5px; line-height: 1.55; margin: 0; }
  .host__do span, .host__proof span { display: block; color: var(--fg-3); font-family: var(--font-mono); font-size: 9.5px; letter-spacing: 0.12em; text-transform: uppercase; margin-bottom: 2px; }
  .host__do span { color: var(--ember-600); }

  /* toolbelt */
  .ch--inside { border-top: 1px solid var(--border-1); }
  .tools { list-style: none; margin: 18px 0 0; padding: 0; display: grid; gap: 8px; }
  .tools li { display: grid; grid-template-columns: 110px 1fr; gap: 14px; padding: 12px 16px; background: var(--bg-2); border: 1px solid var(--border-1); border-radius: 9px; align-items: baseline; }
  @media (max-width: 560px) { .tools li { grid-template-columns: 1fr; gap: 4px; } }
  .tools strong { color: var(--ember-300); font-family: var(--font-mono); font-size: 13px; }
  .tools span { color: var(--fg-2); font-size: 13.5px; line-height: 1.55; }

  /* close */
  .closer { padding: 56px 24px 104px; border-top: 1px solid var(--border-1); }
  .closer__inner { max-width: 760px; margin: 0 auto; }
  .closer h2 { font-size: clamp(26px, 4vw, 38px); margin: 8px 0 12px; }
  .closer p { color: var(--fg-2); font-size: 16px; line-height: 1.65; max-width: 60ch; margin: 0 0 22px; }
  .closer__cta { display: grid; grid-template-columns: 1fr 1fr; gap: 10px; }
  @media (max-width: 640px) { .closer__cta { grid-template-columns: 1fr; } }
  .cta { display: grid; gap: 4px; padding: 16px 18px; background: var(--bg-2); border: 1px solid var(--border-1); border-radius: 10px; color: inherit; text-decoration: none; transition: border-color var(--dur-fast) var(--ease-standard), transform var(--dur-fast) var(--ease-standard); }
  .cta:hover { border-color: var(--border-2); transform: translateY(-1px); }
  .cta--primary { border-color: rgba(138, 99, 206, 0.45); background: rgba(138, 99, 206, 0.05); }
  .cta strong { color: var(--fg-1); font-family: var(--font-display); font-size: 17px; font-weight: 500; }
  .cta span { color: var(--fg-2); font-size: 13px; line-height: 1.45; }
</style>
