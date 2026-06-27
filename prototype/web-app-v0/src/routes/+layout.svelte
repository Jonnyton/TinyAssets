<script lang="ts">
  let { children } = $props();
</script>

<header>
  <nav>
    <a href="/">TinyAssets</a>
    <a href="/catalog">Catalog</a>
    <a href="/connect">Connect</a>
    <a href="/host">Host</a>
    <a href="/contribute">Contribute</a>
    <a href="/status">Status</a>
  </nav>
</header>

<main>
  {@render children()}
</main>

<footer>
  <a href="/legal">Legal</a>
  <span>Content CC0-1.0. Platform MIT.</span>
</footer>
