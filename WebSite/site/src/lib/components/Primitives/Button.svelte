<!--
  Button — primary / secondary / ghost / link variants.
  Ported from design-source/ui_kits/workflow-web/Primitives.jsx
-->
<script lang="ts">
  type Variant = 'primary' | 'secondary' | 'ghost' | 'link';
  type Size = 'sm' | 'md' | 'lg';

  let {
    children,
    variant = 'primary' as Variant,
    size = 'md' as Size,
    href = undefined as string | undefined,
    disabled = false,
    onclick = undefined as ((e: MouseEvent) => void) | undefined,
    class: cls = ''
  } = $props();
</script>

{#if href}
  <a {href} class="btn btn--{variant} btn--{size} {cls}" class:disabled>
    {@render children?.()}
  </a>
{:else}
  <button
    class="btn btn--{variant} btn--{size} {cls}"
    {disabled}
    onclick={disabled ? undefined : onclick}
    type="button"
  >
    {@render children?.()}
  </button>
{/if}

<style>
  .btn {
    font-family: var(--font-sans);
    font-weight: 600;
    line-height: 1;
    border-radius: 8px;
    border: 1px solid transparent;
    cursor: pointer;
    transition: all var(--dur-base) var(--ease-summon);
    display: inline-flex;
    align-items: center;
    gap: 8px;
    white-space: nowrap;
    text-decoration: none;
  }
  .btn:disabled,
  .btn.disabled {
    cursor: not-allowed;
    background: rgba(255, 255, 255, 0.05);
    color: var(--fg-4);
    border-color: transparent;
  }
  /* Sizes */
  .btn--sm { font-size: 12px; padding: 7px 12px; }
  .btn--md { font-size: 14px; padding: 11px 18px; }
  .btn--lg { font-size: 15px; padding: 14px 22px; }
  /* Variants */
  .btn--primary {
    background: var(--ember-600);
    color: var(--fg-on-ember);
  }
  .btn--primary:hover:not(:disabled):not(.disabled) {
    background: var(--ember-500);
    box-shadow: var(--glow-ember);
  }
  .btn--primary:active:not(:disabled):not(.disabled) {
    background: var(--ember-700);
    transform: translateY(1px);
  }
  .btn--secondary {
    background: rgba(138, 99, 206, 0.14);
    color: var(--violet-200);
    border-color: rgba(138, 99, 206, 0.42);
  }
  .btn--secondary:hover:not(:disabled):not(.disabled) {
    background: rgba(138, 99, 206, 0.22);
    border-color: rgba(138, 99, 206, 0.7);
  }
  .btn--ghost {
    background: transparent;
    color: var(--fg-1);
    border-color: var(--border-2);
  }
  .btn--ghost:hover:not(:disabled):not(.disabled) {
    background: rgba(255, 255, 255, 0.04);
    border-color: rgba(255, 255, 255, 0.2);
  }
  .btn--link {
    background: transparent;
    color: var(--ember-600);
    padding: 0;
    border: none;
  }
  .btn--link:hover:not(:disabled):not(.disabled) {
    color: var(--ember-500);
    text-decoration: underline;
  }
</style>
