<!-- /contribute is a compatibility entry. The contributor path now lives in /connect. -->
<script lang="ts">
  import Button from '$lib/components/Primitives/Button.svelte';
  import RitualLabel from '$lib/components/Primitives/RitualLabel.svelte';
</script>

<svelte:head>
  <title>Contribute moved to the loop - Workflow</title>
  <meta name="description" content="Workflow contribution now happens through the live loop page." />
  <meta http-equiv="refresh" content="0; url=/connect" />
  <link rel="canonical" href="/connect" />
</svelte:head>

<section class="alias">
  <div class="container">
    <RitualLabel color="var(--signal-live)">· Route merged ·</RitualLabel>
    <h1>Contribute is now part of the loop.</h1>
    <p>The live loop page is the canonical place to watch real project friction move through intake, investigation, gates, branches, release, and observation.</p>
    <Button variant="primary" href="/connect">Open the loop</Button>
  </div>
</section>

<style>
  .alias {
    min-height: 58vh;
    display: grid;
    align-items: center;
    padding-block: 80px;
  }
  h1 {
    max-width: 14ch;
    margin: 14px 0 16px;
    color: var(--fg-1);
    font-family: var(--font-display);
    font-size: clamp(42px, 7vw, 72px);
    font-weight: 400;
    letter-spacing: 0;
    line-height: 0.98;
  }
  p {
    max-width: 58ch;
    margin: 0 0 24px;
    color: var(--fg-2);
    font-size: 16px;
    line-height: 1.65;
  }
</style>
