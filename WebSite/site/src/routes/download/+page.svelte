<!--
  /download — "choose your surface". The founder's routing rule (2026-08-23):
  get a visitor to the best LIVE surface fast — web app first, installable apps
  next, MCP connect for people already in a chatbot. Every surface is the SAME
  universe (one brain, keyed on your sign-in), so you can switch mid-thought.

  Honesty rails (website-editing skill): no fake download buttons. A surface is
  a real link only when the artifact actually exists; anything not yet shipped
  says so plainly with no clickable control.
-->
<script lang="ts">
  const APP_URL = 'https://tinyassets.io/mcp/app';
  const MCP_URL = 'https://tinyassets.io/mcp';
  const ANDROID_APK =
    'https://github.com/Jonnyton/TinyAssets/releases/download/android-latest/app-debug.apk';

  let copied = $state(false);
  let copyTimer: number | null = null;
  async function copyUrl() {
    try {
      await navigator.clipboard.writeText(MCP_URL);
      copied = true;
      if (copyTimer) clearTimeout(copyTimer);
      copyTimer = window.setTimeout(() => (copied = false), 1800);
    } catch { /* clipboard unavailable; URL is still visible */ }
  }
</script>

<svelte:head>
  <title>Get TinyAssets — every surface, one universe</title>
  <meta
    name="description"
    content="Use Tiny where you are: open the web app, install the desktop or phone app, or connect from any MCP chatbot. Sign in as the same person and it is one continuous universe on every surface."
  />
</svelte:head>

<section class="dl">
  <div class="container">
    <p class="eyebrow">choose your surface</p>
    <h1 class="dl__title">One universe. Meet it anywhere.</h1>
    <p class="dl__lede">
      Every surface below talks to the <strong>same</strong> universe — the same
      brain, the same memory, keyed to your sign-in. Start on the web, keep going
      on your phone, finish on the desktop; the thread comes with you.
    </p>

    <div class="dl__grid">
      <!-- Web app — always live, nothing to install -->
      <article class="card card--primary">
        <h2 class="card__h">Web app</h2>
        <p class="card__p">
          Nothing to install. Sign in and start in your browser — the fastest way
          in, on any device.
        </p>
        <a class="btn btn--primary" href={APP_URL}>Open the web app →</a>
        <p class="card__note">Works on any modern browser.</p>
      </article>

      <!-- Phone -->
      <article class="card">
        <h2 class="card__h">Phone</h2>
        <p class="card__p">
          A native shell over the same app, with sign-in that stays put.
        </p>
        <a class="btn btn--ghost" href={ANDROID_APK}>Download for Android ↓</a>
        <p class="card__note">
          Sideloadable debug build. <span class="soon">iOS — coming soon.</span>
        </p>
      </article>

      <!-- Desktop -->
      <article class="card">
        <h2 class="card__h">Desktop</h2>
        <p class="card__p">
          A native window for Windows, macOS, and Linux — the same universe on
          your machine.
        </p>
        <span class="btn btn--disabled" aria-disabled="true">In final review</span>
        <p class="card__note soon">
          Ships to this page shortly — being security-hardened before release.
        </p>
      </article>

      <!-- MCP connect -->
      <article class="card">
        <h2 class="card__h">In your chatbot</h2>
        <p class="card__p">
          Already living inside Claude, ChatGPT, or another MCP client? Connect
          with one URL.
        </p>
        <button type="button" class="urlchip" onclick={copyUrl} aria-label="Copy the MCP URL">
          <code>{MCP_URL.replace('https://', '')}</code>
          <span class="urlchip__copy">{copied ? 'copied ✓' : 'copy'}</span>
        </button>
        <p class="card__note"><a href="/start">How to connect →</a></p>
      </article>
    </div>
  </div>
</section>

<style>
  .dl { padding: 4rem 0 5rem; }
  .dl__title { font-size: clamp(2rem, 5vw, 3rem); margin: 0.4rem 0 0.8rem; }
  .dl__lede { max-width: 44rem; line-height: 1.55; opacity: 0.9; margin-bottom: 2.4rem; }
  .dl__grid {
    display: grid; gap: 1.1rem;
    grid-template-columns: repeat(auto-fit, minmax(15rem, 1fr));
  }
  .card {
    display: flex; flex-direction: column; gap: 0.6rem;
    border: 1px solid var(--hairline, rgba(255,255,255,0.14));
    border-radius: 14px; padding: 1.4rem;
    background: var(--surface, rgba(255,255,255,0.02));
  }
  .card--primary { border-color: var(--accent, #2d6cdf); }
  .card__h { font-size: 1.25rem; margin: 0; }
  .card__p { margin: 0; line-height: 1.5; opacity: 0.88; flex: 1; }
  .card__note { font-size: 0.82rem; opacity: 0.7; margin: 0.2rem 0 0; }
  .card .btn { align-self: flex-start; }
  .btn--disabled {
    align-self: flex-start; opacity: 0.55; cursor: default;
    border: 1px dashed var(--hairline, rgba(255,255,255,0.25));
    padding: 0.55rem 1rem; border-radius: 10px; font-size: 0.95rem;
  }
  .soon { opacity: 0.75; font-style: italic; }
  .urlchip {
    align-self: flex-start; display: inline-flex; gap: 0.5rem; align-items: center;
    border: 1px solid var(--hairline, rgba(255,255,255,0.2)); background: transparent;
    color: inherit; padding: 0.5rem 0.7rem; border-radius: 10px; cursor: pointer;
    font-family: inherit;
  }
  .urlchip code { font-size: 0.92rem; }
  .urlchip__copy { font-size: 0.72rem; text-transform: uppercase; letter-spacing: 0.04em; opacity: 0.7; }
</style>
