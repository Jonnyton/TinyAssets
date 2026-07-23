/**
 * appRelease.ts — where the mobile app's build will land.
 *
 * Direct, static link to the rolling `android-latest` GitHub release asset
 * that .github/workflows/release-android.yml publishes once clients/android
 * lands on main (see docs/reference/mobile-app-release-convention.md for the
 * full contract). No live check: this is the predicted, most-likely-correct
 * URL for the real build. Today it 404s (nothing published yet); the moment
 * CI publishes that release, this link starts working with no site change.
 */

const REPO = 'Jonnyton/TinyAssets';
const ANDROID_RELEASE_TAG = 'android-latest';
const ANDROID_ASSET_NAME = 'tinyassets-android-latest.apk';

export const ANDROID_DOWNLOAD_URL =
  `https://github.com/${REPO}/releases/download/${ANDROID_RELEASE_TAG}/${ANDROID_ASSET_NAME}`;
