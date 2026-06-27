<script lang="ts">
  let { data } = $props();
  const n = data.node;
</script>

<svelte:head>
  <title>{n.name} — TinyAssets Catalog</title>
  <meta name="description" content="{n.concept?.purpose ?? 'TinyAssets node'}" />
  <meta property="og:title" content="{n.name}" />
  <meta property="og:description" content="{n.concept?.purpose ?? ''}" />
  <link rel="canonical" href="https://tinyassets.io/catalog/{n.node_id}" />
</svelte:head>

<article>
  <header>
    <h1>{n.name}</h1>
    <p class="domain">Domain: {n.domain}</p>
    <div class="badges">
      <span class="badge">↑ {n.quality?.upvote_count ?? 0}</span>
      <span class="badge">used {n.quality?.usage_count ?? 0}</span>
      {#if n.quality?.success_rate != null}
        <span class="badge">{Math.round(n.quality.success_rate * 100)}% success</span>
      {/if}
      <span class="badge license">CC0-1.0</span>
    </div>
  </header>

  <section>
    <h2>Purpose</h2>
    <p>{n.concept?.purpose ?? '—'}</p>
  </section>

  <section>
    <h2>Actions</h2>
    <button disabled>Remix in Claude.ai (wired in real build)</button>
    <button disabled>Fork to my workspace (auth-gated)</button>
  </section>

  <footer>
    <p class="meta">node_id: <code>{n.node_id}</code></p>
  </footer>
</article>
