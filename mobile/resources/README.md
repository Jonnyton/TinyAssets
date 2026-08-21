# App icon + splash source

Drop your artwork here, then run `npx @capacitor/assets generate --android`:

- `icon.png` — 1024×1024 PNG, square, no transparency needed (used for the
  launcher icon + adaptive icon foreground).
- `splash.png` — 2732×2732 PNG (optional; a centered logo on the #0b0b0f
  background matches the loading page).

These are the *source* images; the generator produces the density-specific
Android resources under `android/app/src/main/res/`. Until you add `icon.png`,
the app builds with Capacitor's default icon.
