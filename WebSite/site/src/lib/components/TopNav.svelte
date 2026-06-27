<!-- TopNav — paper chrome. Brand is TinyAssets; Tiny is the speaking persona.
     Active route gets an ink underline.
     Mobile hamburger drawer at <=1000px; items array drives both. -->
<script lang="ts">
  import { page } from '$app/state';
  import TinyAssetsMark from './WorkflowMark.svelte';

  const items = [
    { href: '/start', label: 'start' },
    { href: '/goals', label: 'goals' },
    { href: '/loop', label: 'loop' },
    { href: '/commons', label: 'commons' },
    { href: '/graph', label: 'graph' },
    { href: '/soul', label: 'soul' },
    { href: '/build', label: 'build' }
  ];

  let drawerOpen = $state(false);

  function isActive(path: string, href: string): boolean {
    if (href === '/') return path === '/';
    return path === href || path.startsWith(href + '/');
  }

  function close() { drawerOpen = false; }
</script>

<header class="top">
  <div class="container top__row">
    <a class="brand" href="/" aria-label="TinyAssets home" onclick={close}>
      <TinyAssetsMark size={26} />
      <span class="brand__name">TinyAssets</span>
      <span class="brand__sub ev">meet Tiny</span>
    </a>
    <nav class="nav" aria-label="Primary">
      {#each items as it (it.href)}
        <a href={it.href} class="nav__item" class:active={isActive(page.url.pathname, it.href)}>
          <span class="nav__label">{it.label}</span>
        </a>
      {/each}
    </nav>
    <button
      class="hamburger"
      class:open={drawerOpen}
      aria-label={drawerOpen ? 'Close menu' : 'Open menu'}
      aria-expanded={drawerOpen}
      onclick={() => (drawerOpen = !drawerOpen)}
    >
      <span></span><span></span><span></span>
    </button>
  </div>
</header>

{#if drawerOpen}
  <div class="drawer" role="dialog" aria-label="Site navigation">
    <nav aria-label="Mobile primary">
      <a href="/" class="drawer__item" class:active={isActive(page.url.pathname, '/')} onclick={close}>
        <strong>home</strong>
      </a>
      {#each items as it (it.href)}
        <a href={it.href} class="drawer__item" class:active={isActive(page.url.pathname, it.href)} onclick={close}>
          <strong>{it.label}</strong>
        </a>
      {/each}
    </nav>
  </div>
{/if}

<style>
  .top {
    position: sticky;
    top: 0;
    z-index: 50;
    background: rgba(250, 248, 242, 0.88);
    backdrop-filter: blur(10px);
    -webkit-backdrop-filter: blur(10px);
    border-bottom: 1px solid var(--border-1);
  }
  .top__row { display: flex; align-items: center; justify-content: space-between; padding-block: 11px; gap: 16px; }
  .brand { display: flex; align-items: baseline; gap: 10px; text-decoration: none; }
  .brand :global(.tinyassets-mark) { align-self: center; }
  .brand__name {
    font-family: var(--font-display);
    font-style: italic;
    font-size: 21px;
    font-weight: 500;
    letter-spacing: -0.01em;
    color: var(--fg-1);
  }
  .brand__sub { font-size: 10px; color: var(--fg-4); }
  @media (max-width: 480px) { .brand__sub { display: none; } }

  .nav { display: flex; gap: 2px; }
  @media (max-width: 1000px) { .nav { display: none; } }
  .nav__item {
    display: flex;
    align-items: center;
    text-decoration: none;
    padding: 7px 11px;
    border-radius: var(--radius-sm);
    position: relative;
    transition: background var(--dur-fast) var(--ease-standard);
  }
  .nav__label {
    color: var(--fg-2);
    font-family: var(--font-sans);
    font-size: 13.5px;
    font-weight: 500;
    line-height: 1.15;
    letter-spacing: 0.01em;
    white-space: nowrap;
    transition: color var(--dur-fast) var(--ease-standard);
  }
  .nav__item:hover { background: var(--bg-2); }
  .nav__item:hover .nav__label { color: var(--fg-1); }
  .nav__item.active .nav__label { color: var(--fg-1); }
  .nav__item.active::after {
    content: '';
    position: absolute;
    left: 11px; right: 11px; bottom: 2px;
    height: 1.5px;
    background: var(--ember-600);
  }

  .hamburger { display: none; flex-direction: column; gap: 4px; background: transparent; border: 1px solid var(--border-1); padding: 8px 9px; border-radius: var(--radius-sm); cursor: pointer; }
  .hamburger span { display: block; width: 18px; height: 2px; background: var(--fg-1); border-radius: 2px; transition: transform 0.18s ease, opacity 0.18s ease; }
  .hamburger.open span:nth-child(1) { transform: translateY(6px) rotate(45deg); }
  .hamburger.open span:nth-child(2) { opacity: 0; }
  .hamburger.open span:nth-child(3) { transform: translateY(-6px) rotate(-45deg); }
  @media (max-width: 1000px) { .hamburger { display: flex; } }

  .drawer {
    position: sticky;
    top: 49px;
    z-index: 49;
    background: var(--bg-1);
    border-bottom: 1px solid var(--border-1);
    padding: 12px clamp(16px, 4vw, 24px) 18px;
    box-shadow: var(--shadow-md);
    display: none;
  }
  @media (max-width: 1000px) { .drawer { display: block; } }
  .drawer nav { display: flex; flex-direction: column; gap: 2px; }
  .drawer__item { display: grid; gap: 2px; padding: 12px; border-radius: var(--radius-sm); text-decoration: none; color: var(--fg-2); }
  .drawer__item strong { color: var(--fg-1); font-family: var(--font-sans); font-size: 15.5px; font-weight: 500; }
  .drawer__item:hover { background: var(--bg-2); }
  .drawer__item.active { background: var(--bg-2); }
  .drawer__item.active strong { color: var(--ember-700); }
</style>
