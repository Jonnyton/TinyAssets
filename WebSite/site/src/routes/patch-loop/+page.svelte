<!-- /patch-loop is a static retired-product soft landing. -->
<svelte:head>
  <title>Build your own workflow — TinyAssets</title>
  <link rel="canonical" href="https://tinyassets.io/patterns" />
  <meta
    name="description"
    content="The former patch-loop product is retired. Task automations are ordinary user-authored, copyable, remixable workflows built from TinyAssets patterns."
  />
</svelte:head>

<section class="moved" aria-labelledby="moved-title">
  <p class="eyebrow">retired product surface</p>
  <h1 id="moved-title">Automation is a pattern you own.</h1>
  <p class="moved__line">
    TinyAssets no longer presents a platform-owned patch application. Recurring
    task automation is an ordinary workflow: authored by a user, copied or
    remixed from public patterns, and run only under that workflow's explicit
    choices and authority.
  </p>
  <div class="moved__actions">
    <a class="moved__cta" href="/patterns">Browse workflow patterns →</a>
    <a class="moved__cta moved__cta--quiet" href="/commons">Explore the commons →</a>
  </div>
</section>

<style>
  .moved {
    max-width: 680px;
    margin: 0 auto;
    display: grid;
    gap: 18px;
    padding: clamp(72px, 14vw, 140px) clamp(18px, 4vw, 32px);
  }
  .eyebrow { display: block; }
  h1 {
    margin: 0;
    font-size: clamp(38px, 7vw, 68px);
    font-weight: 500;
    line-height: 1;
    letter-spacing: -.035em;
  }
  .moved__line {
    max-width: 58ch;
    margin: 0;
    color: var(--fg-2);
    font-family: var(--font-voice);
    font-size: clamp(19px, 2.6vw, 24px);
    line-height: 1.5;
  }
  .moved__actions { display: flex; flex-wrap: wrap; gap: 12px; margin-top: 8px; }
  .moved__cta {
    padding: 11px 20px;
    border-radius: var(--radius-pill);
    background: var(--accent);
    color: var(--fg-on-ember);
    font-size: 14px;
    font-weight: 600;
    text-decoration: none;
  }
  .moved__cta:hover { background: var(--accent-hover); text-decoration: none; }
  .moved__cta--quiet {
    border: 1px solid var(--border-2);
    background: transparent;
    color: var(--fg-1);
  }
  .moved__cta--quiet:hover { border-color: var(--accent); background: transparent; }
</style>
