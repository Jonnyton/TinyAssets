/**
 * appRelease.ts — the download button's data source.
 *
 * The button must always DO something real the moment you click it, so the
 * default target is `GITHUB_ZIP_URL` — GitHub's own zip of the current
 * `main` branch. That's always live (no CI needed) and is, literally, "the
 * latest version from the repo".
 *
 * When a real compiled Android build exists, it's a better answer, so this
 * also live-reads GitHub's Releases API for a rolling release tagged
 * `android-latest` with a fixed-name asset (published by
 * .github/workflows/release-android.yml once clients/android lands on
 * main — see docs/reference/mobile-app-release-convention.md) and the UI
 * upgrades to that automatically. But the zip fallback means the button
 * never has a dead/pending state — it always downloads something.
 */

import { fetchWithTimeout } from '$lib/mcp/live';

const REPO = 'Jonnyton/TinyAssets';
export const GITHUB_ZIP_URL = `https://github.com/${REPO}/archive/refs/heads/main.zip`;
const ANDROID_RELEASE_TAG = 'android-latest';
const ANDROID_ASSET_NAME = 'tinyassets-android-latest.apk';

export type AppReleaseAsset = {
  name: string;
  url: string;
  sizeBytes: number;
  publishedAt: string | null;
};

export type AppReleaseState = {
  available: boolean;
  asset?: AppReleaseAsset;
  releaseUrl?: string;
  error?: string;
  fetchedAt: string;
};

/** Live-reads the rolling `android-latest` GitHub release. Honest empty
 *  state (available: false) until CI has actually published a build —
 *  never a baked/guessed download link. */
export async function fetchAndroidRelease(): Promise<AppReleaseState> {
  const fetchedAt = new Date().toISOString();
  try {
    const res = await fetchWithTimeout(
      `https://api.github.com/repos/${REPO}/releases/tags/${ANDROID_RELEASE_TAG}`,
      { headers: { Accept: 'application/vnd.github+json' } }
    );
    if (res.status === 404) return { available: false, fetchedAt };
    if (!res.ok) return { available: false, error: `GitHub releases ${res.status}`, fetchedAt };

    const release = await res.json();
    const assets: any[] = Array.isArray(release?.assets) ? release.assets : [];
    const asset =
      assets.find((a) => a?.name === ANDROID_ASSET_NAME) ??
      assets.find((a) => typeof a?.name === 'string' && a.name.toLowerCase().endsWith('.apk'));

    if (!asset) return { available: false, releaseUrl: release?.html_url, fetchedAt };

    return {
      available: true,
      asset: {
        name: asset.name,
        url: asset.browser_download_url,
        sizeBytes: Number(asset.size ?? 0),
        publishedAt: release.published_at ?? asset.updated_at ?? null
      },
      releaseUrl: release.html_url,
      fetchedAt
    };
  } catch (err: any) {
    return { available: false, error: err?.message ?? String(err), fetchedAt };
  }
}

export function fmtBytes(n: number): string {
  if (!n || n <= 0) return '';
  const mb = n / (1024 * 1024);
  return mb >= 1 ? `${mb.toFixed(1)} MB` : `${Math.max(1, Math.round(n / 1024))} KB`;
}
