<!--
  Static SPA fallback (404 / error). Field Notes paper chrome so a missed
  path still looks like the rest of the site. Links point only at routes
  that exist in the current nav (/commons, /start), never retired ones.
-->
<script lang="ts">
  import { page } from '$app/state';
</script>

<svelte:head>
  <title>{page.status} — Tiny</title>
  <meta name="description" content="That path doesn't resolve. Head home, browse the public commons, open the graph, or connect a chatbot." />
</svelte:head>

<section class="err">
  <div class="wrap">
    <p class="eyebrow">· status {page.status} ·</p>
    <h1>{page.status === 404 ? 'Nothing is bound at that path.' : 'Something tripped on the way through.'}</h1>
    <p class="lead">
      {#if page.status === 404}
        The path <code>{page.url.pathname}</code> doesn't resolve to any page in my brain. It was renamed, never shipped, or you followed a link that has gone stale.
      {:else}
        The server returned <code>{page.status}</code>{#if page.error?.message}: <code>{page.error.message}</code>{/if}. If it keeps happening, file it through your chatbot and I'll pick it up.
      {/if}
    </p>
    <div class="ctas">
      <a class="cta cta--primary" href="/">Back home</a>
      <a class="cta" href="/commons">Browse the commons</a>
      <a class="cta" href="/graph">Open the graph</a>
      <a class="cta" href="/start">Connect a chatbot</a>
    </div>
  </div>
</section>

<style>
  .err { padding-block: clamp(80px, 16vw, 160px); }
  .wrap { max-width: 640px; margin: 0 auto; padding-inline: clamp(18px, 4vw, 32px); }
  .eyebrow {
    display: block;
    font-family: var(--font-mono);
    font-size: 11px;
    text-transform: uppercase;
    letter-spacing: 0.14em;
    color: var(--ember-600);
    margin: 0 0 10px;
  }
  h1 {
    font-family: var(--font-display);
    font-size: clamp(38px, 7vw, 62px);
    font-weight: 400;
    letter-spacing: -0.035em;
    line-height: 1.0;
    margin: 0 0 16px;
    max-width: 18ch;
    color: var(--fg-1);
  }
  .lead {
    font-family: var(--font-voice);
    font-size: clamp(16px, 2vw, 19px);
    line-height: 1.6;
    color: var(--fg-2);
    max-width: 56ch;
    margin: 0 0 28px;
  }
  .lead code {
    background: var(--paper-200);
    border: 1px solid var(--border-1);
    padding: 1px 6px;
    border-radius: 4px;
    font-family: var(--font-mono);
    font-size: 0.85em;
    color: var(--fg-2);
  }
  .ctas { display: flex; gap: 10px; flex-wrap: wrap; }
  .cta {
    font-family: var(--font-sans);
    font-size: 14px;
    font-weight: 600;
    text-decoration: none;
    padding: 10px 18px;
    border-radius: var(--radius-pill);
    border: 1px solid var(--border-1);
    color: var(--fg-1);
    transition: background var(--dur-fast) var(--ease-standard), border-color var(--dur-fast) var(--ease-standard);
  }
  .cta:hover { background: var(--bg-2); text-decoration: none; }
  .cta--primary { background: var(--accent); border-color: var(--accent); color: var(--fg-on-ember); }
  .cta--primary:hover { background: var(--accent-hover); border-color: var(--accent-hover); }
</style>
