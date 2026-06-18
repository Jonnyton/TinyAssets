<!--
  /contribute — retired route, now /build. Soft-landing alias.
  The link is the primary affordance; the 2s meta refresh is a convenience.
-->
<svelte:head>
  <title>Build — Tiny</title>
  <link rel="canonical" href="https://tinyassets.io/build" />
  <meta http-equiv="refresh" content="2;url=/build" />
  <meta name="description" content="The contributor path is now Build — clone the engine, run it locally, and the real ways to contribute to Workflow." />
</svelte:head>

<section class="moved">
  <p class="eyebrow">this page moved</p>
  <p class="moved__line">
    Contributing is now <em>Build</em> — clone the open engine, run it
    locally, and every real way to help shape Workflow.
  </p>
  <a class="moved__cta" href="/build">Go to Build →</a>
  <p class="moved__sub ev">/contribute → /build · taking you there in a moment</p>
</section>

<style>
  .moved { max-width: 540px; margin: 0 auto; display: grid; gap: 16px; padding: clamp(72px, 14vw, 140px) clamp(18px, 4vw, 32px); }
  .eyebrow { display: block; }
  .moved__line { font-family: var(--font-voice); font-size: clamp(20px, 3vw, 26px); line-height: 1.42; color: var(--fg-1); margin: 0; max-width: 32ch; }
  .moved__line em { font-style: italic; color: var(--ember-700); }
  .moved__cta { justify-self: start; margin-top: 6px; font-family: var(--font-sans); font-size: 14px; font-weight: 600; color: var(--fg-on-ember); background: var(--accent); padding: 11px 20px; border-radius: var(--radius-pill); text-decoration: none; transition: background var(--dur-fast) var(--ease-standard); }
  .moved__cta:hover { background: var(--accent-hover); text-decoration: none; }
  .moved__sub { color: var(--fg-3); margin: 4px 0 0; }
</style>
