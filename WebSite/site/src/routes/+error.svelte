<!--
  Static SPA fallback page. Rendered for any route the build didn't
  prerender. Keeps the brand chrome and points at known-good entry points.
-->
<script lang="ts">
  import { page } from '$app/state';
  import RitualLabel from '$lib/components/Primitives/RitualLabel.svelte';
  import Button from '$lib/components/Primitives/Button.svelte';
</script>

<svelte:head>
  <title>{page.status} — Workflow</title>
  <meta name="description" content="Page not found. Return home, summon a daemon, or browse the wiki." />
</svelte:head>

<section class="err">
  <div class="container">
    <RitualLabel color="var(--ember-500)">· status {page.status} ·</RitualLabel>
    <h1>{page.status === 404 ? 'No page bound at that path.' : 'Something tripped on the way through.'}</h1>
    <p class="lead">
      {#if page.status === 404}
        The path <code>{page.url.pathname}</code> doesn't resolve to any node in the constellation. The page was either renamed, never shipped, or you got here from an outbound link that's gone stale.
      {:else}
        The server returned <code>{page.status}</code>{#if page.error?.message}: <code>{page.error.message}</code>{/if}. If this keeps happening, file a thread.
      {/if}
    </p>
    <div class="ctas">
      <Button variant="primary" href="/">Return home</Button>
      <Button variant="ghost" href="/wiki">Browse the wiki</Button>
      <Button variant="ghost" href="/graph">Open the graph</Button>
      <Button variant="ghost" href="/connect">Join the loop</Button>
    </div>
  </div>
</section>

<style>
  .err { padding-top: 96px; padding-bottom: 96px; }
  h1 { font-family: var(--font-display); font-size: clamp(40px, 7vw, 64px); font-weight: 400; letter-spacing: -0.035em; line-height: 1; margin: 14px 0 18px; max-width: 22ch; }
  .lead { font-size: 16px; line-height: 1.6; color: var(--fg-2); max-width: 60ch; margin: 0 0 28px; }
  .lead code { background: rgba(255,255,255,0.06); padding: 1px 5px; border-radius: 3px; font-family: var(--font-mono); font-size: 13px; color: var(--violet-200); }
  .ctas { display: flex; gap: 10px; flex-wrap: wrap; }
</style>
