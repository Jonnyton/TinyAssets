<script lang="ts">
  import strings from '$lib/i18n/en.json';
  const t = strings.legal;
</script>

<svelte:head>
  <title>Legal — TinyAssets</title>
</svelte:head>

<h1>{t.title}</h1>

<h2>{t.tos}</h2>
<p>You must meet your chatbot provider's age requirements. Use the platform responsibly.</p>
<p>(Real ToS document goes here; v0 placeholder.)</p>

<h2>{t.privacy}</h2>
<p>We run per-piece privacy judgement. Concept-layer content is public by default (CC0). Instance data stays on your host and never enters our training data.</p>
<p>See <a href="/docs/catalogs/privacy-principles-and-data-leak-taxonomy">Privacy Principles Catalog</a> for the full model.</p>

<h2>{t.license}</h2>
<p>{t.license}</p>
