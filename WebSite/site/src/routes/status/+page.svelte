<!--
  /status — retired route, now /fine-print. Soft-landing alias.
  The link is the primary affordance; the 2s meta refresh is a convenience.
-->
<svelte:head>
  <title>Fine print — Tiny</title>
  <link rel="canonical" href="https://tinyassets.io/fine-print" />
  <meta http-equiv="refresh" content="2;url=/fine-print" />
  <meta name="description" content="Live status, deploy receipts, and the legal links now live in the Fine print — Tiny's ops room." />
</svelte:head>

<section class="moved">
  <p class="eyebrow">this page moved</p>
  <p class="moved__line">
    Live status now lives in the <em>Fine print</em> — Tiny's ops room, with
    deploy receipts and the legal links alongside it.
  </p>
  <a class="moved__cta" href="/fine-print">Open the Fine print →</a>
  <p class="moved__sub ev">/status → /fine-print · taking you there in a moment</p>
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
