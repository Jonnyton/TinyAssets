<!-- /loop — legacy URL. Content now at /connect. Redirect so old links don't 404. -->
<script lang="ts">
  import { onMount } from 'svelte';
  onMount(() => { window.location.replace('/connect'); });
</script>
<svelte:head>
  <title>The playground moved — Workflow</title>
  <meta http-equiv="refresh" content="0; url=/connect" />
  <link rel="canonical" href="/connect" />
</svelte:head>
<section style="padding-top:120px;text-align:center;">
  <p style="font-family:var(--font-mono);font-size:14px;color:var(--fg-3);">Moved to <a href="/connect" style="color:var(--ember-600);">/connect</a>…</p>
</section>
