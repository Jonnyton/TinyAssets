<script lang="ts">
  import '../app.css';
  import TopNav from '$lib/components/TopNav.svelte';
  import Footer from '$lib/components/Footer.svelte';
  import TinyBot from '$lib/components/TinyBot.svelte';

  let { children } = $props();

  // Structured data (schema.org) for machine understanding + AI search.
  const jsonLd = {
    '@context': 'https://schema.org',
    '@graph': [
      {
        '@type': 'Organization',
        '@id': 'https://tinyassets.io/#org',
        name: 'TinyAssets',
        alternateName: 'Tiny',
        url: 'https://tinyassets.io/',
        logo: 'https://tinyassets.io/logo-mark.png',
        sameAs: ['https://github.com/Jonnyton/Workflow']
      },
      {
        '@type': 'WebSite',
        '@id': 'https://tinyassets.io/#site',
        url: 'https://tinyassets.io/',
        name: 'TinyAssets',
        alternateName: 'Tiny',
        description:
          'TinyAssets is the open-source platform you connect to your chatbot over MCP. Tiny is the personified intelligence inside it: name a goal and he runs real multi-step work, with evidence-gated outcomes and a loop that patches the engine itself.',
        publisher: { '@id': 'https://tinyassets.io/#org' }
      },
      {
        '@type': 'SoftwareApplication',
        name: 'TinyAssets',
        alternateName: 'Tiny',
        applicationCategory: 'DeveloperApplication',
        operatingSystem: 'Web, Windows, macOS, Linux',
        url: 'https://tinyassets.io/',
        description:
          'Connect your chatbot over MCP at https://tinyassets.io/mcp. Design multi-step workflows toward real goals, run them on a persistent engine, and verify outcomes against evidence-gated ladders.',
        offers: { '@type': 'Offer', price: '0', priceCurrency: 'USD' }
      }
    ]
  };
</script>

<svelte:head>
  <meta property="og:site_name" content="TinyAssets" />
  <meta property="og:type" content="website" />
  <meta property="og:title" content="TinyAssets — meet Tiny, the engine that turns chat into finished work" />
  <meta property="og:description" content="Connect your chatbot to one URL. Name a goal. Tiny runs the real, multi-step work — and shows you live, verifiable evidence instead of marketing claims." />
  <meta property="og:image" content="https://tinyassets.io/og-image.png" />
  <meta property="og:url" content="https://tinyassets.io/" />
  <meta name="twitter:card" content="summary_large_image" />
  <meta name="twitter:title" content="TinyAssets — the engine that shows its work" />
  <meta name="twitter:description" content="Live, verifiable state on every page: the same MCP endpoint you paste into your chatbot renders this site's numbers." />
  <meta name="twitter:image" content="https://tinyassets.io/og-image.png" />
  {@html `<script type="application/ld+json">${JSON.stringify(jsonLd)}<\/script>`}
</svelte:head>

<TopNav />

<main>
  {@render children()}
</main>

<Footer />

<TinyBot />
