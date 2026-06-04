<!-- /economy — legacy URL. Content now at /fine-print. Redirect so old links don't 404. -->
<script lang="ts">
  import { onMount } from 'svelte';
  onMount(() => { window.location.replace('/fine-print'); });
</script>
<svelte:head>
  <title>Economy moved — Workflow</title>
  <meta http-equiv="refresh" content="0; url=/fine-print" />
  <link rel="canonical" href="/fine-print" />
</svelte:head>
<section style="padding-top:120px;text-align:center;">
  <p style="font-family:var(--font-mono);font-size:14px;color:var(--fg-3);">Moved to <a href="/fine-print" style="color:var(--ember-600);">/fine-print</a>…</p>
</section>
