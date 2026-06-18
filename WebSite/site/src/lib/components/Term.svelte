<!--
  Term — inline first-use definition.
  The old site's biggest first-visit failure was a jargon wall: commons,
  universe, branch, gate, daemon used before definition. Any term of art
  gets wrapped in this on first use per page: dotted underline, plain-words
  definition on hover/focus/tap. Screen readers get the definition inline.
-->
<script lang="ts">
  let { def, children }: { def: string; children?: any } = $props();
</script>

<!-- svelte-ignore a11y_no_noninteractive_tabindex — focusability is the point: keyboard users summon the definition tooltip -->
<span class="term" tabindex="0" role="note" aria-label={def}>
  {@render children?.()}<span class="term__tip" aria-hidden="true">{def}</span>
</span>

<style>
  .term {
    position: relative;
    border-bottom: 1px dotted var(--border-2);
    cursor: help;
    outline: none;
  }
  .term:focus-visible { border-radius: 2px; box-shadow: 0 0 0 2px var(--live-100); }
  .term__tip {
    position: absolute;
    left: 50%;
    bottom: calc(100% + 8px);
    transform: translateX(-50%) translateY(2px);
    width: max-content;
    max-width: 280px;
    background: var(--ink-text-900);
    color: var(--paper-50);
    font-family: var(--font-sans);
    font-size: 12.5px;
    font-style: normal;
    line-height: 1.45;
    letter-spacing: 0;
    text-align: left;
    padding: 8px 11px;
    border-radius: var(--radius-sm);
    box-shadow: var(--shadow-md);
    opacity: 0;
    pointer-events: none;
    transition: opacity var(--dur-fast) var(--ease-standard), transform var(--dur-fast) var(--ease-standard);
    z-index: 30;
  }
  .term:hover .term__tip,
  .term:focus .term__tip {
    opacity: 1;
    transform: translateX(-50%) translateY(0);
  }
  @media (max-width: 700px) {
    .term__tip { max-width: min(280px, 78vw); }
  }
</style>
