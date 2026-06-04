<script lang="ts">
  import '../app.css';
  import TopNav from '$lib/components/TopNav.svelte';
  import Footer from '$lib/components/Footer.svelte';

  let { children } = $props();

  // Structured data (schema.org). Not required for AI search per Google's
  // guidance, but recommended for rich results + general machine understanding.
  const jsonLd = {
    '@context': 'https://schema.org',
    '@graph': [
      {
        '@type': 'Organization',
        '@id': 'https://tinyassets.io/#org',
        name: 'Workflow',
        alternateName: 'Tiny',
        url: 'https://tinyassets.io/',
        logo: 'https://tinyassets.io/logo-mark.png',
        sameAs: ['https://github.com/Jonnyton/Workflow']
      },
      {
        '@type': 'WebSite',
        '@id': 'https://tinyassets.io/#site',
        url: 'https://tinyassets.io/',
        name: 'Workflow',
        alternateName: 'Tiny',
        description: 'A goal-agnostic engine you connect to your chatbot over MCP. Bind it to any domain — a novel, a paper, an invoice queue — and it runs the real work, then patches itself to run it better.',
        publisher: { '@id': 'https://tinyassets.io/#org' }
      },
      {
        '@type': 'SoftwareApplication',
        name: 'Workflow',
        alternateName: 'Tiny',
        applicationCategory: 'DeveloperApplication',
        operatingSystem: 'Web, Windows, macOS, Linux',
        url: 'https://tinyassets.io/',
        description: 'Connect your chatbot over MCP and give your platform a soul: its own memory, its own purpose, and a patch loop that keeps it aligned to you as it grows.',
        offers: { '@type': 'Offer', price: '0', priceCurrency: 'USD' }
      }
    ]
  };

</script>

<svelte:head>
  <meta property="og:site_name" content="Workflow" />
  <meta property="og:type" content="website" />
  <meta property="og:title" content="Tiny — a goal-agnostic engine that runs real work and patches itself" />
  <meta property="og:description" content="Connect your chatbot over MCP and bind me to any domain — a novel, a paper, an invoice queue. I run the work, then patch myself to run it better. Give your platform a soul." />
  <meta property="og:image" content="https://tinyassets.io/og-image.png" />
  <meta property="og:url" content="https://tinyassets.io/" />
  <meta name="twitter:card" content="summary_large_image" />
  <meta name="twitter:title" content="Tiny — the goal-agnostic engine, speaking for itself" />
  <meta name="twitter:description" content="Connect your chatbot, watch it run real work, and give your platform a soul." />
  <meta name="twitter:image" content="https://tinyassets.io/og-image.png" />
  {@html `<script type="application/ld+json">${JSON.stringify(jsonLd)}<\/script>`}
</svelte:head>

<TopNav />

<main>
  {@render children()}
</main>

<Footer />
