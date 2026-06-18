<!--
  Tick — the provenance device.
  Any live number or claim on the site carries one of these: a small mono
  tick naming where the value actually comes from (a goal id, wiki page,
  PR number, deploy receipt). Clicking opens the raw source. The marketing
  claim and the verification are the same artifact.
-->
<script lang="ts">
  let {
    href = '',
    label = 'source',
    external = false
  }: { href?: string; label?: string; external?: boolean } = $props();
</script>

{#if href}
  <a class="tick" {href} target={external ? '_blank' : undefined} rel={external ? 'noreferrer' : undefined}>
    <span class="tick__glyph" aria-hidden="true">⌁</span>{label}{#if external}<span class="tick__ext" aria-hidden="true">↗</span>{/if}
  </a>
{:else}
  <span class="tick tick--flat"><span class="tick__glyph" aria-hidden="true">⌁</span>{label}</span>
{/if}

<style>
  .tick {
    display: inline-flex;
    align-items: baseline;
    gap: 4px;
    font-family: var(--font-mono);
    font-size: 10.5px;
    letter-spacing: 0.04em;
    color: var(--fg-3);
    text-decoration: none;
    border-bottom: 1px dotted var(--border-2);
    padding-bottom: 1px;
    white-space: nowrap;
    transition: color var(--dur-fast) var(--ease-standard), border-color var(--dur-fast) var(--ease-standard);
  }
  a.tick:hover { color: var(--live-700); border-color: var(--live-600); text-decoration: none; }
  .tick--flat { border-bottom-style: none; }
  .tick__glyph { color: var(--live-600); font-size: 10px; }
  .tick__ext { font-size: 9px; color: var(--fg-4); }
</style>
