<script lang="ts">
  import {
    createPulse,
    compactNumber,
    refreshMcpSnapshot,
    refreshRepoSnapshot,
    relativeStamp,
    shortHash
  } from '$lib/live/project';

  type Tone = 'live' | 'ember' | 'violet';

  let {
    label = 'Live sources',
    detail = 'MCP and GitHub refresh against the same sources used by this page.',
    tone = 'live'
  }: {
    label?: string;
    detail?: string;
    tone?: Tone;
  } = $props();

  let pulse = $state(createPulse());
  let busy = $state<'mcp' | 'github' | null>(null);
  let error = $state<string | null>(null);

  async function refreshMcp() {
    busy = 'mcp';
    try {
      pulse = createPulse(await refreshMcpSnapshot(pulse.mcp), pulse.repo);
      error = null;
    } catch (e: any) {
      error = `MCP ${e?.message ?? String(e)}`;
    } finally {
      busy = null;
    }
  }

  async function refreshGithub() {
    busy = 'github';
    try {
      pulse = createPulse(pulse.mcp, await refreshRepoSnapshot(pulse.repo));
      error = null;
    } catch (e: any) {
      error = `GitHub ${e?.message ?? String(e)}`;
    } finally {
      busy = null;
    }
  }
</script>

<div class={`source-bar source-bar--${tone}`} aria-live="polite">
  <div class="source-copy">
    <span>{label}</span>
    <strong>{detail}</strong>
  </div>
  <div class="source-actions">
    <button type="button" disabled={busy !== null} aria-busy={busy === 'mcp'} onclick={refreshMcp}>
      Refresh MCP
    </button>
    <button type="button" disabled={busy !== null} aria-busy={busy === 'github'} onclick={refreshGithub}>
      Refresh GitHub
    </button>
  </div>
  <div class="source-stamps">
    <span>MCP {relativeStamp(pulse.mcp.fetched_at)} · {compactNumber(pulse.knowledgeCount)} commons · {compactNumber(pulse.mcp.goals.length)} goals</span>
    <span>GitHub {relativeStamp(pulse.repo.fetched_at)} · {compactNumber(pulse.branchCount)} branches · head {shortHash(pulse.repo.repo.head)}</span>
    {#if busy}
      <span>{busy === 'mcp' ? 'Refreshing MCP feed' : 'Refreshing GitHub feed'}</span>
    {/if}
    {#if error}
      <span class="source-error">{error}</span>
    {/if}
  </div>
</div>

<style>
  .source-bar {
    background: var(--bg-2);
    border: 1px solid var(--border-1);
    border-radius: 8px;
    display: grid;
    grid-template-columns: minmax(0, 1fr) auto;
    gap: 12px 18px;
    margin: 22px 0;
    padding: 14px;
  }

  .source-bar--live {
    border-color: rgba(109, 211, 166, 0.22);
  }

  .source-bar--ember {
    border-color: rgba(233, 69, 96, 0.24);
  }

  .source-bar--violet {
    border-color: rgba(138, 99, 206, 0.28);
  }

  .source-copy {
    min-width: 0;
  }

  .source-copy span,
  .source-stamps {
    color: var(--fg-3);
    font-family: var(--font-mono);
    font-size: 10.5px;
    letter-spacing: 0.1em;
    text-transform: uppercase;
  }

  .source-copy strong {
    color: var(--fg-1);
    display: block;
    font-size: 13.5px;
    font-weight: 600;
    line-height: 1.35;
    margin-top: 5px;
  }

  .source-actions {
    display: flex;
    gap: 8px;
    justify-content: flex-end;
  }

  .source-actions button {
    background: var(--bg-inset);
    border: 1px solid var(--border-1);
    border-radius: 6px;
    color: var(--fg-1);
    cursor: pointer;
    font-family: var(--font-mono);
    font-size: 10.5px;
    letter-spacing: 0.1em;
    min-height: 34px;
    padding: 0 12px;
    text-transform: uppercase;
  }

  .source-actions button:hover {
    border-color: rgba(109, 211, 166, 0.42);
  }

  .source-actions button:disabled {
    color: var(--fg-4);
    cursor: wait;
  }

  .source-stamps {
    display: flex;
    flex-wrap: wrap;
    gap: 10px;
    grid-column: 1 / -1;
  }

  .source-error {
    color: var(--signal-error);
  }

  @media (max-width: 720px) {
    .source-bar {
      grid-template-columns: 1fr;
    }

    .source-actions {
      justify-content: stretch;
    }

    .source-actions button {
      flex: 1;
    }
  }
</style>
