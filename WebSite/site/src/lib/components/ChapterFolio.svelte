<!--
  PageFolio — fixed bottom-center page indicator (page title).

  Static prop-driven. Drop on any page to show its title bottom-center.
  Pairs with MoodPill (top-right) as the two universal chrome elements of the
  notebook. Both stay out of the way.
-->
<script lang="ts">
  type Props = {
    chapter?: number;
    title?: string;
    folio?: string;  // optional left-side label — e.g. "cover", "contents"
  };
  let { chapter, title, folio }: Props = $props();

  const folioText = $derived(folio ?? '');
</script>

<aside class="folio" aria-label="Notebook page">
  {#if folioText}<span class="folio__num">{folioText}</span>{/if}
  {#if folioText && title}<span class="folio__sep" aria-hidden="true">·</span>{/if}
  {#if title}<em class="folio__title">{title}</em>{/if}
</aside>

<style>
  .folio {
    position: fixed;
    bottom: 18px;
    left: 50%;
    transform: translateX(-50%);
    z-index: 4;
    display: inline-flex;
    align-items: center;
    gap: 8px;
    padding: 6px 14px;
    background: rgba(11, 11, 20, 0.82);
    border: 1px solid var(--border-1);
    border-radius: 999px;
    color: var(--fg-3);
    font-family: var(--font-mono);
    font-size: 10.5px;
    letter-spacing: 0.14em;
    text-transform: lowercase;
    backdrop-filter: blur(8px);
    -webkit-backdrop-filter: blur(8px);
    max-width: calc(100vw - 32px);
  }
  .folio__num { color: var(--fg-2); }
  .folio__sep { color: var(--fg-4); }
  .folio__title {
    color: var(--ember-300);
    font-family: var(--font-display);
    font-style: italic;
    font-size: 12px;
    letter-spacing: 0;
    text-transform: none;
  }
  @media (max-width: 700px) {
    .folio { bottom: 12px; padding: 5px 11px; font-size: 10px; }
    .folio__title { font-size: 11px; }
  }
</style>
