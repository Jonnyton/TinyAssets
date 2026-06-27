<script lang="ts">
  import strings from '$lib/i18n/en.json';
  const t = strings.catalog;
</script>

<svelte:head>
  <title>Catalog — TinyAssets</title>
</svelte:head>

<h1>{t.title}</h1>
<p>{t.empty_state}</p>
<!-- v0 placeholder; real build pulls top-N from nodes_hot materialized view -->
