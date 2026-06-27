<!--
  RitualLabel — small-caps mono label for kickers, metadata, "inscribed" text.
  Ported from design-source/ui_kits/tinyassets-web/Primitives.jsx
-->
<script lang="ts">
  let {
    children,
    color = undefined as string | undefined
  } = $props();
</script>

<span class="ritual-label" style:color>
  {@render children?.()}
</span>

<style>
  .ritual-label {
    font-family: var(--font-mono);
    font-size: var(--fs-xs);
    text-transform: uppercase;
    letter-spacing: var(--ls-caps);
    color: var(--fg-3);
    font-weight: 500;
  }
</style>
