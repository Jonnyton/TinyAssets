<!--
  AppDownload — the native-app download surface, shared by / and /start.

  Honesty rail: there is no baked download link. This reads GitHub's
  Releases API live for a rolling `android-latest` build (see
  appRelease.ts + docs/reference/mobile-app-setup.md § Release convention).
  Until CI has actually published that release the card says so plainly —
  same "asleep is a first-class state" discipline the rest of the site uses.
  iOS has no sideload distribution channel yet (no Apple Developer Program
  configured), so it always points at building from source, never a fake
  download button.
-->
<script lang="ts">
  import { onMount } from 'svelte';
  import { fetchAndroidRelease, fmtBytes, type AppReleaseState } from '$lib/mcp/appRelease';
  import { fmtRel } from '$lib/fmt';
  import Tick from '$lib/components/Tick.svelte';

  let { variant = 'full' }: { variant?: 'compact' | 'full' } = $props();

  const GH_REPO = 'https://github.com/Jonnyton/TinyAssets';
  const GH_ACTIONS = `${GH_REPO}/actions/workflows/release-android.yml`;
  const IOS_SOURCE = `${GH_REPO}/tree/main/clients/ios`;

  let state = $state<AppReleaseState | null>(null);
  let reading = $state(true);
  async function refresh() {
    reading = true;
    state = await fetchAndroidRelease();
    reading = false;
  }
  onMount(() => { void refresh(); });
</script>

{#if variant === 'compact'}
  <div class="dl dl--compact">
    {#if reading && !state}
      <span class="dl__status ev">checking for the Android build…</span>
    {:else if state?.available && state.asset}
      <a class="btn btn--primary" href={state.asset.url}>
        Download for Android {fmtBytes(state.asset.sizeBytes) ? `(${fmtBytes(state.asset.sizeBytes)})` : ''} →
      </a>
      <span class="dl__status ev">
        published {fmtRel(state.asset.publishedAt)} · read {fmtRel(state.fetchedAt)}
      </span>
    {:else}
      <a class="btn btn--ghost" href="/start#app">Get the mobile app →</a>
      <span class="dl__status ev">Android build not published yet</span>
    {/if}
  </div>
{:else}
  <div class="dl dl--full">
    <article class="dl__card">
      <header class="dl__head">
        <h3 class="dl__h">Android</h3>
        {#if state?.available}
          <span class="dl__badge dl__badge--live">build available</span>
        {:else if reading && !state}
          <span class="dl__badge">checking…</span>
        {:else}
          <span class="dl__badge dl__badge--pending">not published yet</span>
        {/if}
      </header>
      <p class="dl__p">
        A native one-screen conversation surface for your universe — Kotlin +
        Jetpack Compose, source at <code>clients/android</code>.
      </p>
      {#if reading && !state}
        <p class="dl__state ev">reading the latest release from GitHub…</p>
      {:else if state?.available && state.asset}
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
        <p class="dl__state ev">
          {#if state?.error}
            couldn't read GitHub releases just now ({state.error})
          {:else}
            no Android build published yet — CI publishes here automatically
            once the app scaffold ships.
          {/if}
        </p>
        <button class="dl__refresh" onclick={refresh} disabled={reading}>
          {reading ? 'reading…' : 'Refresh GitHub'}
        </button>
        <p class="dl__note">
          <a href={GH_ACTIONS} target="_blank" rel="noreferrer">watch the build on GitHub Actions ↗</a>
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

  /* ── Compact (home) ── */
  .dl--compact { display: flex; align-items: center; gap: 14px; flex-wrap: wrap; }
  .dl__status { white-space: nowrap; }

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
  .dl__refresh {
    background: transparent; border: 1px solid var(--border-2); border-radius: var(--radius-pill);
    color: var(--live-700); cursor: pointer;
    font-family: var(--font-mono); font-size: 10px; letter-spacing: 0.08em; text-transform: uppercase;
    padding: 4px 12px; width: fit-content;
  }
  .dl__refresh:hover:not(:disabled) { border-color: var(--live-600); background: var(--live-100); }
  .dl__refresh:disabled { opacity: 0.6; cursor: default; }
</style>
