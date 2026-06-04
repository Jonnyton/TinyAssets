<!-- /alliance — async-first community channels. No phone, no fake form, no booked calls. -->
<script lang="ts">
  import LiveSourceBar from '$lib/components/LiveSourceBar.svelte';
  import RitualLabel from '$lib/components/Primitives/RitualLabel.svelte';
  import Button from '$lib/components/Primitives/Button.svelte';
  import legal from '$lib/content/legal-info.json';
  import { compactNumber, createPulse } from '$lib/live/project';

  const pulse = createPulse();
  let name = $state('');
  let email = $state('');
  let mission = $state('');

  function handleSubmit(e: Event) {
    e.preventDefault();
    const subject = encodeURIComponent('Tiny Alliance — ' + (name || 'new member'));
    const body = encodeURIComponent(
      `Name: ${name}\nEmail: ${email}\n\nMission:\n${mission}\n\n— sent from tinyassets.io/alliance`
    );
    // Opens user's mail client — works in every browser, no backend, no broken promises.
    window.location.href = `mailto:${legal.contact.general}?subject=${subject}&body=${body}`;
  }
</script>

<svelte:head>
  <title>Tiny Alliance — Workflow</title>
  <meta name="description" content="Join the Tiny Alliance. Contributors, daemon hosts, evaluators, and anyone who wants real-world-effect work to actually ship." />
</svelte:head>

<section class="hero">
  <div class="container">
    <RitualLabel color="var(--ember-500)">· Tiny Alliance · community ·</RitualLabel>
    <h1>Join the Tiny Alliance.</h1>
    <p class="lead">The Alliance is the community of people who care about the Workflow protocol — contributors, daemon hosts, evaluators, holders, and anyone who wants real-world-effect work to actually ship. Share what you're passionate about. We'll find a place for you.</p>
    <p class="lead lead--soft">We do this asynchronously. No calls — talk to us in writing or through your chatbot. We read everything.</p>
    <LiveSourceBar label="Community intake" detail={`${compactNumber(pulse.mcp.wiki.bugs.length)} public bugs, ${compactNumber(pulse.mcp.goals.length)} goals, and ${compactNumber(pulse.branchCount)} branches can receive written work.`} tone="ember" />
    <div class="entry-paths" aria-label="Alliance entry paths">
      <a href="/connect">
        <span>Chatbot path</span>
        <strong>Connect your MCP</strong>
        <p>Ask your chatbot to browse, file, or route work.</p>
      </a>
      <a href="https://github.com/Jonnyton/Workflow/issues/new" target="_blank" rel="noreferrer">
        <span>Public path</span>
        <strong>Start on GitHub</strong>
        <p>Bring an idea, bug, RFC, or contribution thread.</p>
      </a>
      <a href="#alliance-form">
        <span>Direct path</span>
        <strong>Write the Alliance</strong>
        <p>Use email for partnerships or private coordination.</p>
      </a>
    </div>
  </div>
</section>

<section class="form-block">
  <div class="container">
    <form id="alliance-form" class="form" onsubmit={handleSubmit}>
      <RitualLabel>Send a message</RitualLabel>
      <label>Name <input type="text" name="name" required bind:value={name} /></label>
      <label>Email <input type="email" name="email" required bind:value={email} /></label>
      <label class="full">What community mission are you most passionate about?
        <textarea name="mission" rows="6" required bind:value={mission} placeholder="A real-world goal you'd want a daemon to help pursue — your own, or someone else's."></textarea>
      </label>
      <Button variant="primary">Send via email →</Button>
      <p class="meta">Opens your email client with the message pre-filled. Or write directly: <a href="mailto:{legal.contact.general}">{legal.contact.general}</a></p>
    </form>

    <aside class="channels">
      <RitualLabel color="var(--violet-400)">Other ways to plug in</RitualLabel>
      <h3>Async, written, public-by-default.</h3>
      <p class="channels__lead">The project runs the way the protocol runs — asynchronously, in writing, in front of everyone. Pick the surface that matches what you have to say.</p>

      <ul class="channels__list">
        <li>
          <span class="channel__name">Talk to the project itself</span>
          <p class="channel__desc">Wire up the MCP connector and ask your chatbot. It can browse goals, file feature requests, and draft patches on your behalf.</p>
          <a href="/connect" class="channel__cta">Connect a chatbot →</a>
        </li>
        <li>
          <span class="channel__name">Discuss in the open</span>
          <p class="channel__desc">GitHub Issues is the public forum today. Questions, RFCs, "I want to ship X" threads, and "what about Y" threads start there while Discussions stays unavailable.</p>
          <a href="https://github.com/Jonnyton/Workflow/issues" target="_blank" rel="noreferrer" class="channel__cta">github.com/Jonnyton/Workflow/issues ↗</a>
        </li>
        <li>
          <span class="channel__name">File a thread</span>
          <p class="channel__desc">Found a bug, want a feature, or have a pattern to add to the canon? File it — your chatbot can do this for you, or you can open a GitHub issue directly.</p>
          <a href="https://github.com/Jonnyton/Workflow/issues/new" target="_blank" rel="noreferrer" class="channel__cta">Open an issue ↗</a>
        </li>
        <li>
          <span class="channel__name">Write us</span>
          <p class="channel__desc">For anything that doesn't fit a public thread — partnerships, evaluator inquiries, host coordination.</p>
          <a href="mailto:{legal.contact.general}" class="channel__cta">{legal.contact.general}</a>
        </li>
      </ul>

      <p class="channels__footnote">No phone. No "book a call." Show your work in writing — the project will return the favor.</p>
    </aside>
  </div>
</section>

<style>
  .hero, .form-block { padding-block: 56px; border-top: 1px solid var(--border-1); }
  .hero { padding-top: 80px; border-top: none; }
  h1 { font-family: var(--font-display); font-size: clamp(48px, 8vw, 72px); font-weight: 400; letter-spacing: -0.035em; line-height: 0.95; margin: 14px 0 18px; }
  h3 { font-family: var(--font-display); font-size: 20px; font-weight: 500; margin: 8px 0 10px; color: var(--fg-1); letter-spacing: -0.01em; }
  .lead { font-size: 16px; color: var(--fg-2); line-height: 1.6; max-width: 64ch; margin: 0 0 14px; }
  .lead--soft { font-size: 14px; color: var(--fg-3); font-style: italic; margin-top: 0; }
  .entry-paths { display: grid; grid-template-columns: repeat(3, 1fr); gap: 12px; margin-top: 18px; }
  .entry-paths a { background: var(--bg-2); border: 1px solid var(--border-1); border-radius: 8px; color: inherit; display: grid; gap: 7px; min-width: 0; padding: 18px; text-decoration: none; transition: border-color var(--dur-base) var(--ease-summon), background var(--dur-base) var(--ease-summon), transform var(--dur-base) var(--ease-summon); }
  .entry-paths a:hover { border-color: rgba(109, 211, 166, 0.42); background: rgba(109, 211, 166, 0.045); transform: translateY(-1px); }
  .entry-paths span { color: var(--fg-3); font-family: var(--font-mono); font-size: 10px; letter-spacing: 0.12em; text-transform: uppercase; }
  .entry-paths strong { color: var(--fg-1); font-family: var(--font-display); font-size: 24px; font-weight: 500; line-height: 1.08; }
  .entry-paths p { color: var(--fg-2); font-size: 13.5px; line-height: 1.5; margin: 0; }
  @media (max-width: 760px) { .entry-paths { grid-template-columns: 1fr; } }
  .form-block .container { display: grid; grid-template-columns: 1.1fr 1fr; gap: 32px; align-items: start; }
  @media (max-width: 800px) { .form-block .container { grid-template-columns: 1fr; } }

  .form { box-sizing: border-box; min-width: 0; width: 100%; background: var(--bg-2); border: 1px solid var(--border-1); border-radius: 14px; padding: 24px 26px; display: flex; flex-direction: column; gap: 12px; }
  .form label { display: flex; flex-direction: column; gap: 6px; font-family: var(--font-mono); font-size: 11px; color: var(--fg-3); text-transform: uppercase; letter-spacing: 0.14em; }
  .form input, .form textarea { background: var(--bg-inset); border: 1px solid var(--border-1); color: var(--fg-1); padding: 10px 12px; border-radius: 6px; font-family: var(--font-sans); font-size: 14px; text-transform: none; letter-spacing: 0; }
  .form input:focus, .form textarea:focus { border-color: var(--ember-600); outline: none; box-shadow: var(--glow-ember); }
  .meta { font-size: 12px; color: var(--fg-3); font-style: italic; margin: 4px 0 0; }
  .meta a { color: var(--ember-600); text-decoration: none; }

  .channels { box-sizing: border-box; min-width: 0; width: 100%; background: var(--bg-2); border: 1px solid var(--border-1); border-radius: 14px; padding: 24px 26px; }
  .channels__lead { font-size: 13.5px; color: var(--fg-2); line-height: 1.6; margin: 0 0 16px; }
  .channels__list { list-style: none; padding: 0; margin: 0 0 16px; display: flex; flex-direction: column; gap: 14px; }
  .channels__list li { padding: 14px 16px; background: var(--bg-inset); border-radius: 8px; border: 1px solid transparent; }
  .channel__name { display: block; font-family: var(--font-display); font-size: 14px; font-weight: 600; color: var(--fg-1); letter-spacing: -0.005em; margin-bottom: 4px; }
  .channel__desc { font-size: 13px; color: var(--fg-2); line-height: 1.55; margin: 0 0 8px; }
  .channel__cta { display: inline-block; font-family: var(--font-mono); font-size: 11px; color: var(--ember-600); text-decoration: none; letter-spacing: 0.06em; }
  .channel__cta:hover { text-decoration: underline; }
  .channels__footnote { font-size: 12px; color: var(--fg-3); font-style: italic; margin: 12px 0 0; padding-top: 12px; border-top: 1px solid var(--border-1); }
</style>
