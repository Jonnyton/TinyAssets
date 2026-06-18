<!--
  /account — honest stub, NOT a redirect.
  Accounts don't exist yet, and connecting Tiny needs none. The link to
  /start is the real next step; no auto-redirect, no baked numbers.
-->
<svelte:head>
  <title>No account needed — Tiny</title>
  <link rel="canonical" href="https://tinyassets.io/account" />
  <meta name="description" content="There are no website accounts yet — and connecting Tiny needs none. Identity lives in your chatbot connector and your GitHub handle." />
</svelte:head>

<section class="stub">
  <p class="eyebrow">no account here</p>
  <h1>Accounts don't exist yet — connecting needs none.</h1>
  <p class="stub__line">
    There's no sign-up to do. Tiny connects through your chatbot's connector
    with one URL, and for code, your GitHub handle is the only identity that
    matters. When website accounts are real — sign-in, export, deletion —
    this page will say so, instead of showing controls that do nothing.
  </p>
  <a class="stub__cta" href="/start">Connect without an account →</a>
</section>

<style>
  .stub { max-width: 600px; margin: 0 auto; display: grid; gap: 18px; padding: clamp(72px, 13vw, 130px) clamp(18px, 4vw, 32px); }
  .eyebrow { display: block; }
  h1 { font-family: var(--font-display); font-size: clamp(32px, 5.5vw, 54px); font-weight: 400; letter-spacing: -0.03em; line-height: 1.02; margin: 6px 0 0; max-width: 18ch; }
  .stub__line { font-family: var(--font-voice); font-size: clamp(16px, 1.9vw, 19px); line-height: 1.6; color: var(--fg-2); margin: 0; max-width: 56ch; }
  .stub__cta { justify-self: start; margin-top: 4px; font-family: var(--font-sans); font-size: 14px; font-weight: 600; color: var(--fg-on-ember); background: var(--accent); padding: 11px 20px; border-radius: var(--radius-pill); text-decoration: none; transition: background var(--dur-fast) var(--ease-standard); }
  .stub__cta:hover { background: var(--accent-hover); text-decoration: none; }
</style>
