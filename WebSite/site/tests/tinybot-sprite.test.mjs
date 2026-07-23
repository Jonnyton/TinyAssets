import assert from "node:assert/strict";
import { createHash } from "node:crypto";
import { readFile } from "node:fs/promises";
import test from "node:test";

const assetUrl = new URL("../static/tiny-pet.png", import.meta.url);
const componentUrl = new URL(
  "../src/lib/components/TinyBot.svelte",
  import.meta.url,
);
const reactAssetUrl = new URL(
  "../../site-react/public/tiny-pet.png",
  import.meta.url,
);
const reactComponentUrl = new URL(
  "../../site-react/components/TinyBot.tsx",
  import.meta.url,
);
const reactStylesUrl = new URL(
  "../../site-react/components/TinyBot.module.css",
  import.meta.url,
);
const reactConfigUrl = new URL(
  "../../site-react/next.config.mjs",
  import.meta.url,
);

const approvedSha256 =
  "4ed3d0426884b7ef7dafc3b364a64850b40cd6e99a655dbd72a2aee09d9a80ed";

test("both sites use the exact approved 8 by 9 animated platform sprite sheet", async () => {
  const [png, reactPng] = await Promise.all([
    readFile(assetUrl),
    readFile(reactAssetUrl),
  ]);

  for (const asset of [png, reactPng]) {
    assert.equal(asset.subarray(1, 4).toString("ascii"), "PNG");
    assert.equal(asset.readUInt32BE(16), 1536);
    assert.equal(asset.readUInt32BE(20), 1872);
    assert.equal(
      createHash("sha256").update(asset).digest("hex"),
      approvedSha256,
    );
  }

  const [component, reactComponent, reactStyles, reactConfig] =
    await Promise.all([
      readFile(componentUrl, "utf8"),
      readFile(reactComponentUrl, "utf8"),
      readFile(reactStylesUrl, "utf8"),
      readFile(reactConfigUrl, "utf8"),
    ]);

  assert.match(component, /background-image:\s*url\('\/tiny-pet\.png'\)/);
  assert.match(
    reactComponent,
    /process\.env\.NEXT_PUBLIC_BASE_PATH[\s\S]*\/tiny-pet\.png/,
  );
  assert.match(reactConfig, /NEXT_PUBLIC_BASE_PATH:\s*basePath/);

  const stateRows = {
    idle: 0,
    "run-right": -208,
    "run-left": -416,
    wave: -624,
    jump: -832,
    failure: -1040,
    waiting: -1248,
    "active-work": -1456,
    review: -1664,
  };

  for (const styles of [component, reactStyles]) {
    for (const [state, row] of Object.entries(stateRows)) {
      assert.match(
        styles,
        new RegExp(
          `\\.sprite--${state}\\s*\\{[^}]*background-position-y:\\s*${row}(?:px)?;`,
          "s",
        ),
      );
    }
  }

  assert.match(component, /const restingSprite = \$derived<SpriteState>/);
  assert.match(component, /const runnerSprite = \$derived<SpriteState>/);
  assert.match(
    component,
    /mode === 'error'[\s\S]*mode === 'asleep'[\s\S]*vitals\?\.activeRun[\s\S]*jumping[\s\S]*waving[\s\S]*bubble/,
  );
  assert.match(
    reactComponent,
    /mode === "error"[\s\S]*mode === "asleep"[\s\S]*view\.vitals\?\.activeRun[\s\S]*view\.jumping[\s\S]*view\.waving[\s\S]*view\.bubble/,
  );
  assert.ok(
    reactComponent.indexOf("function BotSprite") <
      reactComponent.indexOf("export function TinyBot"),
    "BotSprite must stay at module scope so movement renders do not restart its animation",
  );
  for (const source of [component, reactComponent]) {
    assert.match(source, /(?:onclick|onClick)=\{poke\}/);
    assert.match(source, /(?:onclick|onClick)=\{dismiss\}/);
    assert.match(source, /(?:onclick|onClick)=\{show\}/);
  }
  for (const styles of [component, reactStyles]) {
    assert.match(styles, /@media \(prefers-reduced-motion: reduce\)/);
  }
  assert.doesNotMatch(component, /<svg class="bot__svg"/);
  assert.doesNotMatch(reactComponent, /function BotSvg/);
});
