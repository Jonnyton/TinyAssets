<!-- /account — Phase 2+ stub. Auth-gated full implementation requires Supabase Auth + GitHub OAuth wiring. -->
<script lang="ts">
  import RitualLabel from '$lib/components/Primitives/RitualLabel.svelte';
  import { compactNumber, createPulse } from '$lib/live/project';

  const pulse = createPulse();
</script>

<svelte:head>
  <title>Account — Workflow</title>
</svelte:head>

<section class="stub">
  <div class="wrap">
    <RitualLabel>Account · auth-gated · Phase 2</RitualLabel>
    <h1>No website account yet.</h1>
    <p>For now, identity lives in the surfaces that already work: your chatbot connector, your GitHub handle, and the daemon host you choose to run.</p>
    <div class="actions" aria-label="Current account alternatives">
      <a href="/connect">
        <span>User</span>
        <strong>Connect your MCP</strong>
        <small>{compactNumber(pulse.mcp.goals.length)} goals · {compactNumber(pulse.mcp.wiki.bugs.length)} bugs</small>
      </a>
      <a href="https://github.com/Jonnyton/Workflow" target="_blank" rel="noreferrer">
        <span>Contributor</span>
        <strong>Use GitHub identity</strong>
        <small>{compactNumber(pulse.branchCount)} visible branches</small>
      </a>
      <a href="/host">
        <span>Host</span>
        <strong>Run a daemon</strong>
        <small>{compactNumber(pulse.mcp.universes.length)} universes visible</small>
      </a>
    </div>
    <p class="phase">Phase 2 will add GitHub sign-in, export, deletion, and session management. Until then, this page stays honest instead of showing inactive account controls.</p>
  </div>
</section>

<style>
  .stub { padding-block: 80px; }
  .wrap { max-width: 720px; margin: 0 auto; padding-inline: clamp(16px, 4vw, 32px); color: var(--fg-2); }
  h1 { font-family: var(--font-display); font-size: clamp(48px, 8vw, 72px); font-weight: 400; letter-spacing: -0.035em; line-height: 0.95; margin: 14px 0 18px; }
  p { line-height: 1.7; margin: 0 0 14px; font-size: 16px; }
  .actions { display: grid; grid-template-columns: repeat(3, 1fr); gap: 10px; margin: 24px 0; }
  .actions a { background: var(--bg-2); border: 1px solid var(--border-1); border-radius: 8px; color: inherit; display: grid; gap: 8px; min-width: 0; padding: 18px; text-decoration: none; transition: border-color var(--dur-base) var(--ease-summon), background var(--dur-base) var(--ease-summon), transform var(--dur-base) var(--ease-summon); }
  .actions a:hover { border-color: rgba(109, 211, 166, 0.42); background: rgba(109, 211, 166, 0.045); transform: translateY(-1px); }
  .actions span, .actions small { color: var(--fg-3); font-family: var(--font-mono); font-size: 10px; letter-spacing: 0.1em; text-transform: uppercase; }
  .actions strong { color: var(--fg-1); font-family: var(--font-display); font-size: 22px; font-weight: 500; line-height: 1.1; }
  .phase { color: var(--fg-3); font-size: 14px; }
  @media (max-width: 760px) { .actions { grid-template-columns: 1fr; } }
</style>
