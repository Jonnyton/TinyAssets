import assert from "node:assert/strict";
import { spawnSync } from "node:child_process";
import { mkdtemp, rm, writeFile } from "node:fs/promises";
import { tmpdir } from "node:os";
import { join } from "node:path";
import test from "node:test";
import { fileURLToPath } from "node:url";

import {
  PREVIEW_WORKER_NAME,
  validatePreviewUpload,
} from "./validate-preview-upload.mjs";

const VERSION_ID = "12345678-1234-4abc-8def-1234567890ab";
const EXPECTED_ALIAS = "p16-r5m-a3";
const WORKERS_SUBDOMAIN = "tinyassets-preview";
const VERSION_URL = `https://12345678-${PREVIEW_WORKER_NAME}.${WORKERS_SUBDOMAIN}.workers.dev`;
const ALIAS_URL = `https://${EXPECTED_ALIAS}-${PREVIEW_WORKER_NAME}.${WORKERS_SUBDOMAIN}.workers.dev`;

function validOutput() {
  return [
    " ⛅️ wrangler 4.114.0",
    "Uploaded tiny-site-react-preview",
    `Worker Version ID: ${VERSION_ID}`,
    `Version Preview URL: ${VERSION_URL}`,
    `Version Preview Alias URL: ${ALIAS_URL}`,
    "",
  ].join("\n");
}

function replaceLine(output, label, replacement) {
  return output
    .split("\n")
    .map((line) =>
      line.startsWith(`${label}:`) ? `${label}: ${replacement}` : line,
    )
    .join("\n");
}

test("returns one deterministic normalized immutable-upload receipt", () => {
  const receipt = {
    versionId: VERSION_ID,
    versionUrl: VERSION_URL,
    aliasUrl: ALIAS_URL,
    alias: EXPECTED_ALIAS,
    workerName: PREVIEW_WORKER_NAME,
    workersDevSubdomain: WORKERS_SUBDOMAIN,
  };
  assert.deepEqual(
    validatePreviewUpload(validOutput(), EXPECTED_ALIAS),
    receipt,
  );
  assert.deepEqual(
    validatePreviewUpload(validOutput(), EXPECTED_ALIAS),
    receipt,
  );
});

test("CLI reads Wrangler output and prints the normalized receipt", async () => {
  const directory = await mkdtemp(join(tmpdir(), "tinyassets-preview-upload-"));
  try {
    const outputPath = join(directory, "wrangler-output.log");
    await writeFile(outputPath, validOutput());
    const script = fileURLToPath(
      new URL("./validate-preview-upload.mjs", import.meta.url),
    );
    const result = spawnSync(
      process.execPath,
      [script, outputPath, EXPECTED_ALIAS],
      { encoding: "utf8" },
    );
    assert.equal(result.status, 0, result.stderr);
    assert.deepEqual(JSON.parse(result.stdout), {
      versionId: VERSION_ID,
      versionUrl: VERSION_URL,
      aliasUrl: ALIAS_URL,
      alias: EXPECTED_ALIAS,
      workerName: PREVIEW_WORKER_NAME,
      workersDevSubdomain: WORKERS_SUBDOMAIN,
    });
  } finally {
    await rm(directory, { recursive: true, force: true });
  }
});

test("rejects every missing or duplicate receipt field", async (t) => {
  const fields = [
    ["Worker Version ID", VERSION_ID],
    ["Version Preview URL", VERSION_URL],
    ["Version Preview Alias URL", ALIAS_URL],
  ];
  for (const [label, value] of fields) {
    await t.test(`missing ${label}`, () => {
      const output = validOutput()
        .split("\n")
        .filter((line) => !line.startsWith(`${label}:`))
        .join("\n");
      assert.throws(
        () => validatePreviewUpload(output, EXPECTED_ALIAS),
        new RegExp(`exactly one ${label}`, "i"),
      );
    });
    await t.test(`duplicate ${label}`, () => {
      const output = `${validOutput()}${label}: ${value}\n`;
      assert.throws(
        () => validatePreviewUpload(output, EXPECTED_ALIAS),
        new RegExp(`exactly one ${label}`, "i"),
      );
    });
  }
});

test("rejects malformed receipt field syntax and invalid transcript values", async (t) => {
  for (const output of [undefined, null, Buffer.from("output"), ""]) {
    await t.test(`invalid output ${String(output)}`, () => {
      assert.throws(
        () => validatePreviewUpload(output, EXPECTED_ALIAS),
        /non-empty string/i,
      );
    });
  }
  for (const label of [
    "Worker Version ID",
    "Version Preview URL",
    "Version Preview Alias URL",
  ]) {
    await t.test(`missing separator space for ${label}`, () => {
      const output = validOutput().replace(`${label}: `, `${label}:`);
      assert.throws(
        () => validatePreviewUpload(output, EXPECTED_ALIAS),
        new RegExp(`${label}.*malformed`, "i"),
      );
    });
    await t.test(`malformed duplicate ${label}`, () => {
      const output = `${validOutput()}${label}:malformed\n`;
      assert.throws(
        () => validatePreviewUpload(output, EXPECTED_ALIAS),
        new RegExp(`exactly one ${label}`, "i"),
      );
    });
  }
});

test("rejects malformed version IDs and provider-version prefixes", async (t) => {
  for (const [name, value] of [
    ["not UUID", "12345678"],
    ["uppercase UUID", VERSION_ID.toUpperCase()],
    ["braced UUID", `{${VERSION_ID}}`],
    ["trailing text", `${VERSION_ID} uploaded`],
  ]) {
    await t.test(name, () => {
      const output = replaceLine(validOutput(), "Worker Version ID", value);
      assert.throws(
        () => validatePreviewUpload(output, EXPECTED_ALIAS),
        /version id/i,
      );
    });
  }
  await t.test("UUID prefix mismatch", () => {
    const output = replaceLine(
      validOutput(),
      "Version Preview URL",
      VERSION_URL.replace("12345678-", "87654321-"),
    );
    assert.throws(
      () => validatePreviewUpload(output, EXPECTED_ALIAS),
      /version preview url.*prefix/i,
    );
  });
});

test("rejects malformed or unexpected version URLs", async (t) => {
  for (const [name, value] of [
    ["http", VERSION_URL.replace("https://", "http://")],
    ["wrong worker", VERSION_URL.replace(PREVIEW_WORKER_NAME, "other-worker")],
    ["wrong suffix", VERSION_URL.replace("workers.dev", "example.com")],
    ["suffix confusion", `${VERSION_URL}.example.com`],
    [
      "extra subdomain label",
      VERSION_URL.replace(".workers.dev", ".extra.workers.dev"),
    ],
    [
      "leading-hyphen subdomain",
      VERSION_URL.replace(WORKERS_SUBDOMAIN, "-invalid"),
    ],
    [
      "trailing-hyphen subdomain",
      VERSION_URL.replace(WORKERS_SUBDOMAIN, "invalid-"),
    ],
    ["port", `${VERSION_URL}:443`],
    ["path", `${VERSION_URL}/path`],
    ["query", `${VERSION_URL}?x=1`],
    ["fragment", `${VERSION_URL}#fragment`],
    ["userinfo", VERSION_URL.replace("https://", "https://user@")],
  ]) {
    await t.test(name, () => {
      const output = replaceLine(validOutput(), "Version Preview URL", value);
      assert.throws(
        () => validatePreviewUpload(output, EXPECTED_ALIAS),
        /version preview url/i,
      );
    });
  }
});

test("rejects malformed, mismatched, or reused-looking aliases", async (t) => {
  for (const value of [
    "pr-42",
    "p0-r5m-a3",
    "p16-r0-a3",
    "p16-r5m-a0",
    "p016-r5m-a3",
    "p16-r05m-a3",
    "p16-r5m-a03",
    "P16-r5m-a3",
    "p16-r5m-a3-",
    `p${"a".repeat(40)}-r${"b".repeat(40)}-a3`,
  ]) {
    await t.test(value, () => {
      assert.throws(
        () => validatePreviewUpload(validOutput(), value),
        /alias/i,
      );
    });
  }

  await t.test("alias URL names another receipt", () => {
    const output = replaceLine(
      validOutput(),
      "Version Preview Alias URL",
      ALIAS_URL.replace(EXPECTED_ALIAS, "p16-r5m-a4"),
    );
    assert.throws(
      () => validatePreviewUpload(output, EXPECTED_ALIAS),
      /alias url/i,
    );
  });
});

test("rejects malformed alias URLs and cross-subdomain receipts", async (t) => {
  for (const [name, value] of [
    ["http", ALIAS_URL.replace("https://", "http://")],
    ["wrong worker", ALIAS_URL.replace(PREVIEW_WORKER_NAME, "other-worker")],
    ["wrong suffix", ALIAS_URL.replace("workers.dev", "example.com")],
    ["suffix confusion", `${ALIAS_URL}.example.com`],
    ["path", `${ALIAS_URL}/path`],
    ["query", `${ALIAS_URL}?x=1`],
    ["fragment", `${ALIAS_URL}#fragment`],
    ["port", `${ALIAS_URL}:443`],
    ["userinfo", ALIAS_URL.replace("https://", "https://user@")],
    [
      "different workers.dev subdomain",
      ALIAS_URL.replace(WORKERS_SUBDOMAIN, "another-preview"),
    ],
  ]) {
    await t.test(name, () => {
      const output = replaceLine(
        validOutput(),
        "Version Preview Alias URL",
        value,
      );
      assert.throws(
        () => validatePreviewUpload(output, EXPECTED_ALIAS),
        /alias url/i,
      );
    });
  }
});

test("rejects ANSI and control characters anywhere in the transcript", async (t) => {
  for (const [name, control] of [
    ["ANSI escape", "\u001b[32m"],
    ["NUL", "\u0000"],
    ["tab", "\u0009"],
    ["carriage return", "\u000d"],
    ["delete", "\u007f"],
    ["C1 control", "\u009b"],
  ]) {
    await t.test(name, () => {
      assert.throws(
        () =>
          validatePreviewUpload(`${control}${validOutput()}`, EXPECTED_ALIAS),
        /control|ansi/i,
      );
    });
  }
});
