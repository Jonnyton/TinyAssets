<!--
  /connect — radical simplicity. Add the connector. Then talk.
  Ported from design-source/ui_kits/workflow-web/Connect.jsx.
-->
<script lang="ts">
  import strings from '$lib/i18n/en.json';
  import LiveSourceBar from '$lib/components/LiveSourceBar.svelte';
  import RitualLabel from '$lib/components/Primitives/RitualLabel.svelte';

  const t = strings.connect;
  const url = t.mcp_url;
  const directoryUrl = 'https://tinyassets.io/mcp-directory';
  const requestEnvelope = JSON.stringify(
    {
      full_custom_connector: url,
      directory_review_endpoint: directoryUrl,
      calls: [
        { tool: 'wiki', arguments: { action: 'list' } },
        { tool: 'goals', arguments: { action: 'list' } },
        { tool: 'universe', arguments: { action: 'list' } }
      ]
    },
    null,
    2
  );
  const protocolFacts = [
    { label: 'read wiki', href: '/wiki' },
    { label: 'map work', href: '/graph' },
    { label: 'watch the loop', href: '/loop' },
    { label: 'inspect graph', href: '/graph' },
    { label: 'proof registry', href: 'https://github.com/Jonnyton/Workflow/blob/main/docs/ops/mcp-host-proof-registry.md', external: true },
    { label: 'AI docs', href: '/llms.txt' }
  ];
  const unlockCards = [
    {
      label: 'Community wiki',
      title: 'Ask it to read the public wiki.',
      body: 'Work targets, bugs, plans, notes, and drafts come back through the same MCP surface the site uses.',
      href: '/wiki',
      action: 'Open wiki'
    },
    {
      label: 'Proof packet',
      title: 'Ask what is actually proven.',
      body: 'The proof page ties connector, wiki, graph, loop, repo, and known limits into one evidence path.',
      href: '/proof',
      action: 'Open proof'
    },
    {
      label: 'Loop',
      title: 'Ask it to route work into the loop.',
      body: 'Patch requests, investigation, gates, PRs, release, and watch are the operating path.',
      href: '/loop',
      action: 'Watch loop'
    },
    {
      label: 'Graph',
      title: 'Ask how the project hangs together.',
      body: 'The graph shows live relationships across bugs, branches, work targets, tags, and repo state.',
      href: '/graph',
      action: 'Open graph'
    }
  ];
  const customerPaths = [
    {
      title: 'Claude.ai',
      status: 'Best live chat path',
      account: 'Use this if Claude is where you already ask for help. Free, Pro, Max, Team, and Enterprise can use custom remote MCP with plan limits.',
      setup: `Click Add it, paste ${url} into Claude connector settings, approve it, then start a chat with Workflow enabled.`,
      proof: 'Custom URL is the current path. Claude directory listing is still pending, so the page does not claim directory acceptance.',
      anchor: '#mcp-server-url'
    },
    {
      title: 'ChatGPT',
      status: 'Apps path pending',
      account: 'Use this if ChatGPT is your main chat surface or your workspace will approve apps/connectors centrally.',
      setup: 'Watch for the Apps or admin-approved connector path. Until proof lands, do not treat the raw MCP endpoint as a normal browser page.',
      proof: 'ChatGPT public claims wait for Apps SDK, BUG-034, and workspace approval proof.',
      anchor: '#proof-state'
    },
    {
      title: 'Open WebUI / LibreChat',
      status: 'Verified self-hosted path',
      account: 'Use this if you run your own chat UI, local model shell, or channel gateway and do not want a Claude or ChatGPT login.',
      setup: `For Open WebUI or LibreChat, add ${directoryUrl} as a Streamable HTTP / remote MCP server. Use ${url} only when a host needs the full custom connector surface.`,
      proof: 'Open WebUI local Docker 0.9.2 and LibreChat local Docker v0.8.5 are verified. LM Studio, Jan, and OpenClaw/channel gateways stay planned until proof traces land.',
      anchor: '#proof-state'
    },
    {
      title: 'VS Code / Cursor / Codex',
      status: 'Codex verified; other IDEs pending',
      account: 'Use this if you want Workflow available inside your coding agent or IDE while you work in a repo.',
      setup: `For Codex CLI, add ${directoryUrl} as the Workflow MCP server or pass it with a Codex config override. Use ${url} only when the host needs the full custom connector surface.`,
      proof: 'Codex CLI 0.104.0 listed Workflow tools and called get_workflow_status on 2026-05-02. Cursor is registration-only so far; VS Code/Copilot is still planned.',
      anchor: '#technical-proof'
    },
    {
      title: 'Team / enterprise workspace',
      status: 'One approval for many users',
      account: 'Use this if an admin controls connectors, apps, or agent tools for ChatGPT Business/Enterprise/Edu, Claude Team/Enterprise, Mistral, or Copilot Studio.',
      setup: 'Send the admin packet: scopes, safety copy, test plan, support path, and proof registry.',
      proof: 'Submission kits are in progress; public claims wait for host approval.',
      anchor: '#proof-state'
    },
    {
      title: 'Custom MCP host',
      status: 'Protocol path',
      account: 'Use this if you are building your own chatbot, agent host, app, or integration surface.',
      setup: `Implement Streamable HTTP MCP client support, call ${url}, and run the public canary/smoke prompts against your host.`,
      proof: 'Compatible by spec until your host is added to the proof registry.',
      anchor: '#technical-proof'
    }
  ];
  const proofRows = [
    {
      label: 'Custom remote MCP',
      status: 'Live',
      body: `${url} is the user-facing endpoint for hosts that accept a custom remote MCP URL.`
    },
    {
      label: 'Claude.ai',
      status: 'Best current hosted path',
      body: 'Claude custom connector setup is the clearest hosted-chat path today. Directory listing remains separate.'
    },
    {
      label: 'Open WebUI and LibreChat',
      status: 'Verified self-hosted path',
      body: `No-login local Docker proof exists for Open WebUI and LibreChat via ${directoryUrl}. LM Studio, Jan, and OpenClaw stay planned until host-specific proof lands.`
    },
    {
      label: 'Codex CLI',
      status: 'Verified developer CLI path',
      body: `Codex CLI 0.104.0 can register ${directoryUrl}, list Workflow tools, and call get_workflow_status. Cursor and VS Code still need full read-call proof.`
    },
    {
      label: 'Directories and app stores',
      status: 'Registry live; host directories pending',
      body: 'The MCP Registry listing is live. Claude directory, ChatGPT Apps, and workspace-admin listings are only claimed after acceptance proof lands.'
    }
  ];

  let copied = $state(false);
  let copiedDirectory = $state(false);

  async function copyText(value: string) {
    try {
      await navigator.clipboard.writeText(value);
      return true;
    } catch {
      if (typeof document === 'undefined') return false;
      const textArea = document.createElement('textarea');
      textArea.value = value;
      textArea.setAttribute('readonly', '');
      textArea.style.left = '-9999px';
      textArea.style.opacity = '0';
      textArea.style.position = 'fixed';
      document.body.appendChild(textArea);
      textArea.select();
      try {
        return document.execCommand('copy');
      } finally {
        document.body.removeChild(textArea);
      }
    }
  }

  async function copyUrl() {
    if (await copyText(url)) {
      copied = true;
      setTimeout(() => (copied = false), 1400);
    }
  }

  async function copyDirectoryUrl() {
    if (await copyText(directoryUrl)) {
      copiedDirectory = true;
      setTimeout(() => (copiedDirectory = false), 1400);
    }
  }
</script>

<svelte:head>
  <title>Connect — Workflow</title>
  <meta name="description" content={t.tagline} />
</svelte:head>

<section class="connect">
  <div class="wrap">
    <RitualLabel color="var(--signal-live)">· User entry · tinyassets.io/mcp ·</RitualLabel>
    <h1 class="title">Connect your MCP.</h1>
    <p class="lead">
      Paste one URL into your MCP-capable chatbot or agent host. Your host can browse the community wiki, inspect work targets and universes, and route work into the same loop the site shows.
    </p>

    <section class="primary-flow" aria-label="Primary connection actions">
      <button type="button" class="flow-card flow-card--copy" class:copied onclick={copyUrl}>
        <span class="flow-card__num">1</span>
        <span class="flow-card__title">Add it.</span>
        <span class="flow-card__body">Copy the MCP URL, paste it into your chatbot connector settings, then approve.</span>
        <span class="flow-card__action">{copied ? 'Copied URL' : 'Copy MCP URL'}</span>
      </button>
      <a class="flow-card" href="/wiki">
        <span class="flow-card__num">2</span>
        <span class="flow-card__title">Talk.</span>
        <span class="flow-card__body">Start a chat and ask Workflow to read the community wiki, inspect open work, or route a patch into the loop.</span>
        <span class="flow-card__action">Open live wiki</span>
      </a>
    </section>

    <div class="endpoint-grid">
      <div class="card" id="mcp-server-url">
        <div class="card__label">Full custom connector URL</div>
        <div class="row">
          <input class="row__input" readonly value={url} aria-label="MCP server URL" />
          <button
            class="row__btn"
            class:copied
            onclick={copyUrl}
            aria-label="Copy MCP URL"
          >
            {copied ? 'Copied!' : 'Copy'}
          </button>
        </div>
        <p class="endpoint-note">Use this today in custom remote MCP connector settings.</p>
      </div>

      <div class="card" id="directory-status">
        <div class="card__label">Directory / review endpoint</div>
        <div class="row">
          <input class="row__input" readonly value={directoryUrl} aria-label="MCP directory review endpoint" />
          <button
            class="row__btn"
            class:copied={copiedDirectory}
            onclick={copyDirectoryUrl}
            aria-label="Copy MCP directory review endpoint"
          >
            {copiedDirectory ? 'Copied!' : 'Copy'}
          </button>
        </div>
        <p class="endpoint-note">Live for registry and host review. Not a claim that any host directory has accepted Workflow.</p>
      </div>
    </div>

    <LiveSourceBar label="Connector proof" detail="Refresh the public MCP route or GitHub source before copying the URL." />

    <section class="chooser" aria-labelledby="chooser-title">
      <RitualLabel color="var(--signal-live)">· Pick the customer path ·</RitualLabel>
      <h2 id="chooser-title">Connect from the host you already use.</h2>
      <p class="chooser__lead">
        Pick the card with the tool you already use. Each path says what to do now, and what still waits for public proof.
      </p>

      <div class="path-grid">
        {#each customerPaths as path (path.title)}
          <article class="path-card">
            <div class="path-card__top">
              <h3>{path.title}</h3>
              <span>{path.status}</span>
            </div>
            <dl>
              <div>
                <dt>This is me</dt>
                <dd>{path.account}</dd>
              </div>
              <div>
                <dt>Do this</dt>
                <dd>{path.setup}</dd>
              </div>
              <div>
                <dt>Proof state</dt>
                <dd>{path.proof}</dd>
              </div>
            </dl>
            <a href={path.anchor}>See path</a>
          </article>
        {/each}
      </div>
    </section>

    <section class="after-connect" aria-labelledby="after-connect-title">
      <div class="section-head">
        <RitualLabel color="var(--signal-live)">· After it connects ·</RitualLabel>
        <h2 id="after-connect-title">Ask for real project state.</h2>
        <p>
          Workflow is useful because the connector can read the living project, not because the page explains a protocol. These are the first things a connected chatbot should be able to show you.
        </p>
      </div>

      <div class="unlock-grid">
        {#each unlockCards as item (item.title)}
          <a class="unlock-card" href={item.href}>
            <span class="unlock-card__label">{item.label}</span>
            <strong>{item.title}</strong>
            <span>{item.body}</span>
            <small>{item.action}</small>
          </a>
        {/each}
      </div>
    </section>

    <section class="proof-state" id="proof-state" aria-labelledby="proof-title">
      <div class="section-head section-head--tight">
        <RitualLabel color="var(--ember-500)">· Proof, not promises ·</RitualLabel>
        <h2 id="proof-title">Ready where it has evidence.</h2>
        <p>
          The page separates what works today from directory and host claims that still need acceptance traces.
        </p>
      </div>

      <div class="proof-list">
        {#each proofRows as row (row.label)}
          <div class="proof-row">
            <strong>{row.label}</strong>
            <span>{row.status}</span>
            <p>{row.body}</p>
          </div>
        {/each}
      </div>
    </section>

    <details class="technical-proof" id="technical-proof">
      <summary>
        <span>Technical proof for builders and reviewers</span>
        <small>Endpoint shape, public references, and directory caveat</small>
      </summary>
      <div class="technical-proof__body">
        <div>
          <p>
            The full connector URL is for users and custom hosts. The directory endpoint is for reviewed listings. Both describe the same Workflow system without claiming a directory listing before proof exists.
          </p>
          <div class="protocol__facts">
            {#each protocolFacts as fact}
              <a href={fact.href} target={fact.external ? '_blank' : undefined} rel={fact.external ? 'noreferrer' : undefined}>{fact.label}</a>
            {/each}
          </div>
        </div>
        <pre><code>{requestEnvelope}</code></pre>
      </div>
    </details>
  </div>
</section>

<style>
  .connect { padding-block: 80px; }
  .wrap {
    max-width: 820px;
    margin: 0 auto;
    padding-inline: clamp(16px, 4vw, 32px);
  }
  .title {
    font-family: var(--font-display);
    font-variation-settings: 'opsz' 144, 'SOFT' 50;
    font-size: clamp(48px, 8vw, 80px);
    font-weight: 400;
    letter-spacing: -0.035em;
    line-height: 0.95;
    margin: 20px 0 20px;
  }
  .lead {
    font-size: 18px;
    color: var(--fg-2);
    margin: 0 0 22px;
    line-height: 1.5;
  }
  .primary-flow {
    display: grid;
    gap: 14px;
    grid-template-columns: repeat(2, minmax(0, 1fr));
    margin-bottom: 16px;
  }
  .flow-card {
    background:
      linear-gradient(180deg, rgba(109, 211, 166, 0.08), rgba(109, 211, 166, 0.015)),
      var(--bg-2);
    border: 1px solid rgba(109, 211, 166, 0.3);
    border-radius: 8px;
    color: inherit;
    cursor: pointer;
    display: grid;
    gap: 10px;
    min-height: 210px;
    min-width: 0;
    padding: 22px;
    text-align: left;
    text-decoration: none;
    transition:
      background var(--dur-base) var(--ease-summon),
      border-color var(--dur-base) var(--ease-summon),
      transform var(--dur-base) var(--ease-summon);
  }
  .flow-card:hover,
  .flow-card.copied {
    background:
      linear-gradient(180deg, rgba(109, 211, 166, 0.12), rgba(109, 211, 166, 0.035)),
      var(--bg-2);
    border-color: rgba(109, 211, 166, 0.58);
    transform: translateY(-1px);
  }
  .flow-card__num {
    color: var(--ember-600);
    font-family: var(--font-display);
    font-size: 48px;
    font-weight: 400;
    line-height: 0.9;
  }
  .flow-card__title {
    color: var(--fg-1);
    font-family: var(--font-display);
    font-size: 32px;
    font-weight: 500;
    letter-spacing: 0;
    line-height: 1;
  }
  .flow-card__body {
    color: var(--fg-2);
    font-size: 14px;
    line-height: 1.55;
  }
  .flow-card__action {
    align-self: end;
    color: var(--signal-live);
    font-family: var(--font-mono);
    font-size: 11px;
    letter-spacing: 0.08em;
    text-transform: uppercase;
  }
  .card {
    background: var(--bg-2);
    border: 1px solid var(--border-1);
    border-radius: 8px;
    padding: 28px;
    margin-bottom: 16px;
  }
  .endpoint-grid {
    display: grid;
    gap: 14px;
    margin-bottom: 14px;
  }
  .endpoint-grid .card {
    margin-bottom: 0;
  }
  .endpoint-note {
    color: var(--fg-3);
    font-size: 12px;
    line-height: 1.5;
    margin: 10px 0 0;
  }
  .card__label {
    font-family: var(--font-mono);
    font-size: 11px;
    color: var(--fg-3);
    text-transform: uppercase;
    letter-spacing: 0.14em;
    margin-bottom: 14px;
  }
  .row { display: flex; }
  .row__input {
    flex: 1;
    background: var(--bg-inset);
    color: var(--fg-1);
    border: 1px solid var(--border-1);
    border-right: none;
    border-radius: 8px 0 0 8px;
    padding: 16px 18px;
    font-family: var(--font-mono);
    font-size: 15px;
    min-width: 0;
    outline: none;
  }
  .row__btn {
    background: var(--ember-600);
    color: var(--fg-on-ember);
    border: none;
    padding: 0 28px;
    border-radius: 0 8px 8px 0;
    font-family: var(--font-sans);
    font-size: 15px;
    font-weight: 600;
    cursor: pointer;
    min-width: 130px;
    transition: all 200ms;
  }
  .row__btn.copied {
    background: var(--signal-live);
    color: #0e2b1d;
  }
  @media (max-width: 560px) {
    .card { padding: 22px; }
    .row { display: grid; grid-template-columns: 1fr; }
    .row__input {
      min-width: 0;
      border-right: 1px solid var(--border-1);
      border-radius: 8px 8px 0 0;
      font-size: 11px;
      padding: 14px 12px;
    }
    .row__btn {
      min-width: 0;
      border-radius: 0 0 8px 8px;
      padding: 12px 16px;
    }
  }
  .chooser {
    border-top: 1px solid var(--border-1);
    margin: 36px 0 48px;
    padding-top: 44px;
  }
  .chooser h2,
  .section-head h2 {
    color: var(--fg-1);
    font-family: var(--font-display);
    font-size: clamp(30px, 5vw, 48px);
    font-weight: 500;
    letter-spacing: 0;
    line-height: 1;
    margin: 14px 0 12px;
  }
  .chooser__lead {
    color: var(--fg-2);
    font-size: 15px;
    line-height: 1.6;
    margin: 0 0 22px;
  }
  .path-grid {
    display: grid;
    gap: 12px;
    grid-template-columns: repeat(2, minmax(0, 1fr));
  }
  .path-card {
    background: var(--bg-2);
    border: 1px solid var(--border-1);
    border-radius: 8px;
    display: grid;
    gap: 14px;
    padding: 18px;
  }
  .path-card__top {
    display: grid;
    gap: 8px;
  }
  .path-card h3 {
    color: var(--fg-1);
    font-family: var(--font-display);
    font-size: 24px;
    font-weight: 500;
    letter-spacing: 0;
    line-height: 1.05;
    margin: 0;
  }
  .path-card__top span {
    border: 1px solid rgba(109, 211, 166, 0.32);
    border-radius: 4px;
    color: var(--signal-live);
    font-family: var(--font-mono);
    font-size: 10px;
    justify-self: start;
    letter-spacing: 0.08em;
    padding: 4px 7px;
    text-transform: uppercase;
  }
  .path-card dl {
    display: grid;
    gap: 10px;
    margin: 0;
  }
  .path-card dl div {
    display: grid;
    gap: 3px;
  }
  .path-card dt {
    color: var(--fg-3);
    font-family: var(--font-mono);
    font-size: 10px;
    letter-spacing: 0.1em;
    text-transform: uppercase;
  }
  .path-card dd {
    color: var(--fg-2);
    font-size: 13px;
    line-height: 1.5;
    margin: 0;
  }
  .path-card a {
    color: var(--fg-1);
    font-family: var(--font-mono);
    font-size: 11px;
    letter-spacing: 0.08em;
    text-transform: uppercase;
  }
  .after-connect,
  .proof-state {
    border-top: 1px solid var(--border-1);
    margin: 0 0 46px;
    padding-top: 42px;
  }
  .section-head {
    margin-bottom: 20px;
    max-width: 680px;
  }
  .section-head--tight {
    margin-bottom: 16px;
  }
  .section-head p {
    color: var(--fg-2);
    font-size: 15px;
    line-height: 1.6;
    margin: 0;
  }
  .unlock-grid {
    display: grid;
    gap: 12px;
    grid-template-columns: repeat(2, minmax(0, 1fr));
  }
  .unlock-card {
    background: var(--bg-2);
    border: 1px solid var(--border-1);
    border-radius: 8px;
    color: inherit;
    display: grid;
    gap: 10px;
    min-width: 0;
    padding: 18px;
    text-decoration: none;
    transition:
      background var(--dur-base) var(--ease-summon),
      border-color var(--dur-base) var(--ease-summon),
      transform var(--dur-base) var(--ease-summon);
  }
  .unlock-card:hover {
    background: rgba(109, 211, 166, 0.045);
    border-color: rgba(109, 211, 166, 0.42);
    transform: translateY(-1px);
  }
  .unlock-card__label,
  .unlock-card small {
    font-family: var(--font-mono);
    font-size: 10px;
    letter-spacing: 0.1em;
    text-transform: uppercase;
  }
  .unlock-card__label {
    color: var(--ember-500);
  }
  .unlock-card strong {
    color: var(--fg-1);
    font-family: var(--font-display);
    font-size: 24px;
    font-weight: 500;
    letter-spacing: 0;
    line-height: 1.05;
  }
  .unlock-card span:not(.unlock-card__label) {
    color: var(--fg-2);
    font-size: 13px;
    line-height: 1.5;
  }
  .unlock-card small {
    color: var(--signal-live);
    margin-top: 2px;
  }
  .proof-list {
    border: 1px solid var(--border-1);
    border-radius: 8px;
    overflow: hidden;
  }
  .proof-row {
    background: var(--bg-2);
    display: grid;
    gap: 8px;
    grid-template-columns: minmax(0, 0.9fr) minmax(0, 0.58fr) minmax(0, 1.52fr);
    padding: 14px;
  }
  .proof-row + .proof-row {
    border-top: 1px solid var(--border-1);
  }
  .proof-row strong,
  .proof-row span {
    font-family: var(--font-mono);
    font-size: 11px;
  }
  .proof-row strong {
    color: var(--fg-1);
  }
  .proof-row span {
    color: var(--ember-500);
    text-transform: uppercase;
  }
  .proof-row p {
    color: var(--fg-2);
    font-size: 12.5px;
    line-height: 1.45;
    margin: 0;
  }
  @media (max-width: 760px) {
    .path-grid,
    .unlock-grid,
    .proof-row {
      grid-template-columns: 1fr;
    }
  }
  .technical-proof {
    background: var(--bg-2);
    border: 1px solid var(--border-1);
    border-radius: 8px;
    margin-bottom: 48px;
    overflow: hidden;
  }
  .technical-proof summary {
    align-items: center;
    cursor: pointer;
    display: grid;
    gap: 6px;
    grid-template-columns: 1fr;
    list-style: none;
    padding: 18px 20px;
  }
  .technical-proof summary::-webkit-details-marker {
    display: none;
  }
  .technical-proof summary span {
    color: var(--fg-1);
    font-family: var(--font-display);
    font-size: 24px;
    font-weight: 500;
    letter-spacing: 0;
    line-height: 1.05;
  }
  .technical-proof summary small {
    color: var(--fg-3);
    font-family: var(--font-mono);
    font-size: 10px;
    letter-spacing: 0.1em;
    text-transform: uppercase;
  }
  .technical-proof[open] summary {
    border-bottom: 1px solid var(--border-1);
  }
  .technical-proof__body {
    display: grid;
    gap: 16px;
    grid-template-columns: minmax(0, 0.85fr) minmax(0, 1fr);
    padding: 20px;
  }
  .technical-proof p {
    color: var(--fg-2);
    font-size: 13.5px;
    line-height: 1.6;
    margin: 0 0 14px;
  }
  .technical-proof pre {
    background: var(--bg-inset);
    border: 1px solid var(--border-1);
    border-radius: 8px;
    margin: 0;
    overflow-x: auto;
    padding: 14px;
  }
  .technical-proof code {
    color: var(--fg-1);
    display: block;
    font-family: var(--font-mono);
    font-size: 12px;
    line-height: 1.55;
  }
  .protocol__facts {
    display: flex;
    flex-wrap: wrap;
    gap: 6px;
  }
  .protocol__facts a {
    border: 1px solid var(--border-1);
    border-radius: 4px;
    color: var(--fg-2);
    font-family: var(--font-mono);
    font-size: 10px;
    letter-spacing: 0.08em;
    padding: 4px 7px;
    text-decoration: none;
    text-transform: uppercase;
    transition: border-color var(--dur-base) var(--ease-summon), color var(--dur-base) var(--ease-summon);
  }
  .protocol__facts a:hover { border-color: rgba(109, 211, 166, 0.42); color: var(--signal-live); }
  @media (max-width: 760px) {
    .technical-proof__body { grid-template-columns: 1fr; }
  }
  @media (max-width: 760px) {
    .primary-flow {
      grid-template-columns: 1fr;
    }
    .flow-card {
      min-height: 0;
    }
  }
</style>
