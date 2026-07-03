<!--
  AppDownload — the SDK/app download button, shared by / (hero) and /start.

  Static link to ANDROID_DOWNLOAD_URL (see appRelease.ts) — the predicted
  location of the mobile app's build once .github/workflows/release-android.yml
  publishes it. Today it 404s (clients/android isn't on main yet); the moment
  that lands, this link starts working with no further site change.
-->
<script lang="ts">
  import { ANDROID_DOWNLOAD_URL } from '$lib/mcp/appRelease';

  let { variant = 'full' }: { variant?: 'compact' | 'full' } = $props();

  const GH_REPO = 'https://github.com/Jonnyton/TinyAssets';
  const IOS_SOURCE = `${GH_REPO}/tree/main/clients/ios`;
</script>

{#if variant === 'compact'}
  <a class="btn btn--ghost" href={ANDROID_DOWNLOAD_URL}>Download SDK →</a>
{:else}
  <div class="dl dl--full">
    <article class="dl__card">
      <header class="dl__head">
        <h3 class="dl__h">Android / SDK</h3>
      </header>
      <p class="dl__p">
        A native one-screen conversation surface for your universe — Kotlin +
        Jetpack Compose, source at <code>clients/android</code>.
      </p>
      <a class="btn btn--primary" href={ANDROID_DOWNLOAD_URL}>Download SDK →</a>
      <p class="dl__note">
        Debug-signed APK; Android will ask you to allow installs from this
        source the first time. Not yet on the Play Store.
      </p>
    </article>

    <article class="dl__card">
      <header class="dl__head">
        <h3 class="dl__h">iPhone</h3>
        <span class="dl__badge dl__badge--pending">build from source</span>
      </header>
      <p class="dl__p">
        SwiftUI client, same one-screen surface — source at
        <code>clients/ios</code>. No App Store or TestFlight listing exists
        yet, so there's no direct install; open the Xcode project and run it
        yourself.
      </p>
      <pre class="dl__pre"><code>cd clients/ios{'\n'}open TinyAssets.xcodeproj</code></pre>
      <a class="dl__cta" href={IOS_SOURCE} target="_blank" rel="noreferrer">iOS source on GitHub ↗</a>
    </article>
  </div>
{/if}

<style>
  .btn {
    display: inline-block;
    font-family: var(--font-sans);
    font-size: 14px;
    font-weight: 600;
    letter-spacing: 0.01em;
    padding: 11px 22px;
    border-radius: var(--radius-pill);
    text-decoration: none;
    transition: background var(--dur-fast) var(--ease-standard), color var(--dur-fast) var(--ease-standard), border-color var(--dur-fast) var(--ease-standard);
  }
  .btn--primary { background: var(--ink-text-900); color: var(--paper-50); border: 1px solid var(--ink-text-900); }
  .btn--primary:hover { background: var(--ember-700); border-color: var(--ember-700); color: #fff; text-decoration: none; }
  .btn--ghost { border: 1px solid var(--border-2); color: var(--fg-1); background: transparent; }
  .btn--ghost:hover { border-color: var(--ink-text-900); text-decoration: none; }

  /* ── Full (start) ── */
  .dl--full { display: grid; grid-template-columns: repeat(2, 1fr); gap: 16px; }
  @media (max-width: 760px) { .dl--full { grid-template-columns: 1fr; } }
  .dl__card {
    display: grid; gap: 10px; align-content: start;
    padding: 22px;
    background: var(--bg-2);
    border: 1px solid var(--border-1);
    border-radius: var(--radius-lg);
  }
  .dl__head { display: flex; align-items: center; justify-content: space-between; gap: 10px; }
  .dl__h { font-size: 19px; margin: 0; }
  .dl__badge {
    font-family: var(--font-mono); font-size: 9.5px; letter-spacing: 0.1em; text-transform: uppercase;
    padding: 3px 9px; border-radius: var(--radius-pill); border: 1px solid var(--border-1);
    color: var(--fg-3); white-space: nowrap;
  }
  .dl__badge--pending { color: var(--signal-warn); border-color: rgba(201, 111, 36, 0.45); }
  .dl__p { font-size: 14px; line-height: 1.55; color: var(--fg-2); margin: 0; }
  .dl__p code { font-size: 12.5px; }
  .dl__note { font-size: 12.5px; line-height: 1.55; color: var(--fg-3); margin: 0; }
  .dl__pre { margin: 2px 0 0; padding: 11px 13px; font-size: 12.5px; }
  .dl__pre code { font-size: 12.5px; }
  .dl__cta { font-family: var(--font-sans); font-size: 13.5px; font-weight: 600; color: var(--ember-700); width: fit-content; }
</style>
