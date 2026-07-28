import assert from "node:assert/strict";
import {
  chmod,
  link,
  mkdir,
  mkdtemp,
  readFile,
  symlink,
  writeFile,
} from "node:fs/promises";
import { tmpdir } from "node:os";
import path from "node:path";
import test from "node:test";

import {
  DEFAULT_LIMITS,
  validateAndCopyPreviewArtifact,
} from "./validate-preview-artifact.mjs";

async function fixture(t) {
  const temporary = await mkdtemp(path.join(tmpdir(), "tinyassets-preview-artifact-"));
  t.after(async () => {
    const { rm } = await import("node:fs/promises");
    await rm(temporary, { recursive: true, force: true });
  });

  const source = path.join(temporary, "artifact");
  const destination = path.join(temporary, "validated");
  await mkdir(path.join(source, "_next", "static", "chunks"), { recursive: true });
  await writeFile(path.join(source, "index.html"), "<!doctype html><title>TinyAssets</title>\n");
  await writeFile(path.join(source, "404.html"), "<!doctype html><title>Not found</title>\n");
  await writeFile(path.join(source, "_next", "static", "chunks", "app.js"), "console.log('static');\n");
  await writeFile(path.join(source, "robots.txt"), "User-agent: *\nAllow: /\n");
  return { temporary, source, destination };
}

test("copies a valid static export and emits a deterministic sorted manifest", async (t) => {
  const { source, destination } = await fixture(t);

  const first = await validateAndCopyPreviewArtifact(source, destination);
  assert.deepEqual(
    first.files.map((entry) => entry.path),
    ["404.html", "_next/static/chunks/app.js", "index.html", "robots.txt"],
  );
  assert.equal(first.fileCount, 4);
  assert.equal(
    first.totalBytes,
    first.files.reduce((sum, entry) => sum + entry.size, 0),
  );
  assert.match(first.files[0].sha256, /^[a-f0-9]{64}$/);
  assert.equal(await readFile(path.join(destination, "index.html"), "utf8"), "<!doctype html><title>TinyAssets</title>\n");

  const secondDestination = path.join(path.dirname(destination), "validated-again");
  const second = await validateAndCopyPreviewArtifact(source, secondDestination);
  assert.deepEqual(second, first);
});

for (const [label, relativePath] of [
  ["newline", "bad\nname.js"],
  ["control", "bad\tname.js"],
  ["leading dot", ".hidden.js"],
  ["traversal-like", "safe..evil.js"],
]) {
  test(`rejects ${label} path components`, async (t) => {
    const { source, destination } = await fixture(t);
    try {
      await writeFile(path.join(source, relativePath), "hostile");
    } catch (error) {
      if (error?.code === "ENOENT" || error?.code === "EINVAL") {
        t.skip("filesystem does not permit this hostile filename");
        return;
      }
      throw error;
    }
    await assert.rejects(
      validateAndCopyPreviewArtifact(source, destination),
      /unsafe artifact path component/i,
    );
  });
}

for (const [label, relativePath] of [
  ["package config", "package.json"],
  ["wrangler config", "wrangler.toml"],
  ["worker entrypoint", "_worker.js"],
  ["Cloudflare headers", "_headers"],
  ["Cloudflare redirects", "_redirects"],
  ["custom-domain marker", "CNAME"],
  ["archive", "payload.zip"],
  ["unexpected extension", "program.py"],
]) {
  test(`rejects ${label}`, async (t) => {
    const { source, destination } = await fixture(t);
    await writeFile(path.join(source, relativePath), "hostile");
    await assert.rejects(
      validateAndCopyPreviewArtifact(source, destination),
      /forbidden|extension/i,
    );
  });
}

test("rejects executable files where executable mode bits are supported", async (t) => {
  const { source, destination } = await fixture(t);
  const executable = path.join(source, "executable.js");
  await writeFile(executable, "hostile");
  await chmod(executable, 0o755);
  const { stat } = await import("node:fs/promises");
  if (((await stat(executable)).mode & 0o111) === 0) {
    t.skip("filesystem does not expose executable mode bits");
    return;
  }
  await assert.rejects(
    validateAndCopyPreviewArtifact(source, destination),
    /executable/i,
  );
});

test("rejects symlinks where symlink creation is supported", async (t) => {
  const { temporary, source, destination } = await fixture(t);
  const outside = path.join(temporary, "outside.js");
  await writeFile(outside, "hostile");
  try {
    await symlink(outside, path.join(source, "linked.js"), "file");
  } catch (error) {
    if (error?.code === "EPERM" || error?.code === "EACCES") {
      t.skip("symlink creation is not permitted");
      return;
    }
    throw error;
  }
  await assert.rejects(
    validateAndCopyPreviewArtifact(source, destination),
    /symlink|non-regular/i,
  );
});

test("rejects hard-linked files where hard links are supported", async (t) => {
  const { source, destination } = await fixture(t);
  try {
    await link(
      path.join(source, "index.html"),
      path.join(source, "_next", "static", "hard-link.html"),
    );
  } catch (error) {
    if (["EPERM", "EACCES", "ENOTSUP"].includes(error?.code)) {
      t.skip("hard-link creation is not permitted");
      return;
    }
    throw error;
  }
  await assert.rejects(
    validateAndCopyPreviewArtifact(source, destination),
    /hard-linked/i,
  );
});

test("rejects an oversized file before copying", async (t) => {
  const { source, destination } = await fixture(t);
  await writeFile(path.join(source, "large.js"), "12345");
  await assert.rejects(
    validateAndCopyPreviewArtifact(source, destination, {
      ...DEFAULT_LIMITS,
      maxFileBytes: 4,
    }),
    /per-file size limit/i,
  );
});

test("rejects excessive file count before copying", async (t) => {
  const { source, destination } = await fixture(t);
  await assert.rejects(
    validateAndCopyPreviewArtifact(source, destination, {
      ...DEFAULT_LIMITS,
      maxFileCount: 3,
    }),
    /file-count limit/i,
  );
});

test("rejects excessive total size before copying", async (t) => {
  const { source, destination } = await fixture(t);
  await assert.rejects(
    validateAndCopyPreviewArtifact(source, destination, {
      ...DEFAULT_LIMITS,
      maxTotalBytes: 10,
    }),
    /total-size limit/i,
  );
});

for (const missing of ["index.html", "404.html", "_next/static"]) {
  test(`rejects an artifact missing ${missing}`, async (t) => {
    const { source, destination } = await fixture(t);
    const { rm } = await import("node:fs/promises");
    await rm(path.join(source, ...missing.split("/")), { recursive: true, force: true });
    await assert.rejects(
      validateAndCopyPreviewArtifact(source, destination),
      (error) => error.message.toLowerCase().includes(missing.toLowerCase()),
    );
  });
}

test("requires a clean destination and keeps it untouched on validation failure", async (t) => {
  const { source, destination } = await fixture(t);
  await mkdir(destination);
  await writeFile(path.join(destination, "existing.txt"), "keep");
  await assert.rejects(
    validateAndCopyPreviewArtifact(source, destination),
    /destination.*empty/i,
  );
  assert.equal(await readFile(path.join(destination, "existing.txt"), "utf8"), "keep");
});
