<script lang="ts">
  import strings from '$lib/i18n/en.json';
  const t = strings.landing;
</script>

<svelte:head>
  <title>TinyAssets — Summon the daemon</title>
  <meta name="description" content="{t.hero_subtitle}" />
  <meta property="og:title" content="{t.hero_title}" />
  <meta property="og:description" content="{t.hero_subtitle}" />
</svelte:head>

<section class="hero">
  <h1>{t.hero_title}</h1>
  <p>{t.hero_subtitle}</p>

  <div class="ctas">
    <a href="/connect" class="cta cta-primary">{t.cta_connect}</a>
    <a href="/host" class="cta">{t.cta_host}</a>
    <a href="/contribute" class="cta">{t.cta_contribute}</a>
  </div>
</section>
