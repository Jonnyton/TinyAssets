<!-- /notebook — legacy URL. Content now at /. Redirect so old links don't 404. -->
<script lang="ts">
  import { onMount } from 'svelte';
  onMount(() => { window.location.replace('/'); });
</script>
<svelte:head>
  <title>Moved — Workflow</title>
  <meta http-equiv="refresh" content="0; url=/" />
  <link rel="canonical" href="/" />
</svelte:head>
<section style="padding-top:120px;text-align:center;">
  <p style="font-family:var(--font-mono);font-size:14px;color:var(--fg-3);">Moved to <a href="/" style="color:var(--ember-600);">/</a>…</p>
</section>
