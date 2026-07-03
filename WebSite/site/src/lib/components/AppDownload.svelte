<!--
  AppDownload — the SDK/app download button, shared by / (hero) and /start.

  Affordance contract: this must always download something real the
  instant you click it — never a "checking…" or "not published yet"
  dead end. Default target is GitHub's zip of the current `main` branch
  (real, live, no CI needed — literally "the latest version from the
  repo"). If a real compiled Android build exists (see appRelease.ts),
  it upgrades to that automatically; the zip is the floor, not a
  placeholder.
-->
<script lang="ts">
  import { onMount } from 'svelte';
  import { fetchAndroidRelease, fmtBytes, GITHUB_ZIP_URL, type AppReleaseState } from '$lib/mcp/appRelease';
  import { fmtRel } from '$lib/fmt';
  import Tick from '$lib/components/Tick.svelte';

  let { variant = 'full' }: { variant?: 'compact' | 'full' } = $props();

  const GH_REPO = 'https://github.com/Jonnyton/TinyAssets';
  const IOS_SOURCE = `${GH_REPO}/tree/main/clients/ios`;

  let state = $state<AppReleaseState | null>(null);
  onMount(() => { void fetchAndroidRelease().then((s) => (state = s)); });

  const href = $derived(state?.available && state.asset ? state.asset.url : GITHUB_ZIP_URL);
  const label = $derived(state?.available && state.asset ? 'Download for Android' : 'Download SDK');
</script>

{#if variant === 'compact'}
  <a class="btn btn--ghost" {href}>{label} →</a>
{:else}
  <div class="dl dl--full">
    <article class="dl__card">
      <header class="dl__head">
        <h3 class="dl__h">Android / SDK</h3>
        {#if state?.available}
          <span class="dl__badge dl__badge--live">APK available</span>
        {/if}
      </header>
      {#if state?.available && state.asset}
        <p class="dl__p">
          A native one-screen conversation surface for your universe — Kotlin +
          Jetpack Compose, source at <code>clients/android</code>.
        </p>
        <a class="btn btn--primary" href={state.asset.url}>
          Download {state.asset.name} {fmtBytes(state.asset.sizeBytes) ? `(${fmtBytes(state.asset.sizeBytes)})` : ''} →
        </a>
        <p class="dl__state ev">
          published {fmtRel(state.asset.publishedAt)} · read {fmtRel(state.fetchedAt)}
          {#if state.releaseUrl}&nbsp;· <Tick href={state.releaseUrl} label="release notes" external /> {/if}
        </p>
        <p class="dl__note">
          It's a debug-signed APK — Android will ask you to allow installs from
          this source the first time. Not yet on the Play Store.
        </p>
      {:else}
        <p class="dl__p">
          The native Android app is being built at <code>clients/android</code>
          on a separate branch — no compiled APK exists yet. This downloads the
          full SDK/engine source instead, so you can build it yourself today.
        </p>
        <a class="btn btn--primary" href={GITHUB_ZIP_URL}>Download SDK (source zip) →</a>
        <p class="dl__note">
          Once a real Android build ships, this card switches to a direct APK
          download automatically — no site change needed.
        </p>
      {/if}
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
  .ev { font-family: var(--font-mono); font-size: 11px; color: var(--fg-3); }

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
  .dl__badge--live { color: var(--live-700); border-color: var(--live-600); background: var(--live-100); }
  .dl__badge--pending { color: var(--signal-warn); border-color: rgba(201, 111, 36, 0.45); }
  .dl__p { font-size: 14px; line-height: 1.55; color: var(--fg-2); margin: 0; }
  .dl__p code { font-size: 12.5px; }
  .dl__state { margin: 0; }
  .dl__note { font-size: 12.5px; line-height: 1.55; color: var(--fg-3); margin: 0; }
  .dl__pre { margin: 2px 0 0; padding: 11px 13px; font-size: 12.5px; }
  .dl__pre code { font-size: 12.5px; }
  .dl__cta { font-family: var(--font-sans); font-size: 13.5px; font-weight: 600; color: var(--ember-700); width: fit-content; }
</style>
