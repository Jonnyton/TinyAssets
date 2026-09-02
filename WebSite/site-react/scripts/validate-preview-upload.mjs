import { readFile } from "node:fs/promises";
import path from "node:path";
import { pathToFileURL } from "node:url";

export const PREVIEW_WORKER_NAME = "tiny-site-react-preview";

const UUID_PATTERN =
  /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/u;
const ALIAS_PATTERN =
  /^p[1-9a-z][0-9a-z]*-r[1-9a-z][0-9a-z]*-a[1-9a-z][0-9a-z]*$/u;
const DNS_LABEL_PATTERN = "[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?";
const VERSION_URL_PATTERN = new RegExp(
  `^https://([0-9a-f]{8})-${PREVIEW_WORKER_NAME}\\.(${DNS_LABEL_PATTERN})\\.workers\\.dev$`,
  "u",
);
const MAX_DNS_LABEL_LENGTH = 63;

function reject(message) {
  throw new Error(`Preview upload rejected: ${message}`);
}

function escapeRegExp(value) {
  return value.replace(/[.*+?^${}()|[\]\\]/gu, "\\$&");
}

function extractExactlyOne(lines, label) {
  const marker = `${label}:`;
  const candidates = lines.filter((line) => line.startsWith(marker));
  if (candidates.length !== 1) {
    reject(`expected exactly one ${label} field, found ${candidates.length}`);
  }

  const prefix = `${marker} `;
  if (!candidates[0].startsWith(prefix)) {
    reject(`${label} field is malformed`);
  }

  return candidates[0].slice(prefix.length);
}

function assertSafeTranscript(output) {
  if (typeof output !== "string" || output.length === 0) {
    reject("Wrangler output must be a non-empty string");
  }
  if (/[\u0000-\u0009\u000b-\u001f\u007f-\u009f]/u.test(output)) {
    reject("Wrangler output contains ANSI or control characters");
  }
}

export function validatePreviewUpload(output, expectedAlias) {
  assertSafeTranscript(output);
  if (typeof expectedAlias !== "string" || !ALIAS_PATTERN.test(expectedAlias)) {
    reject(
      "expected alias is not a canonical never-reused base36 preview alias",
    );
  }
  if (`${expectedAlias}-${PREVIEW_WORKER_NAME}`.length > MAX_DNS_LABEL_LENGTH) {
    reject("expected alias and fixed Worker name exceed the DNS label limit");
  }

  const lines = output.split("\n");
  const versionId = extractExactlyOne(lines, "Worker Version ID");
  const versionUrl = extractExactlyOne(lines, "Version Preview URL");
  const aliasUrl = extractExactlyOne(lines, "Version Preview Alias URL");

  if (!UUID_PATTERN.test(versionId)) {
    reject("Worker Version ID must be one lowercase canonical UUID");
  }

  const versionUrlMatch = VERSION_URL_PATTERN.exec(versionUrl);
  if (versionUrlMatch === null) {
    reject(
      "Version Preview URL must use HTTPS, the fixed Worker name, and one valid workers.dev subdomain",
    );
  }
  const [, versionPrefix, workersDevSubdomain] = versionUrlMatch;
  if (versionPrefix !== versionId.slice(0, 8)) {
    reject("Version Preview URL prefix does not match the Worker Version ID");
  }

  const aliasUrlPattern = new RegExp(
    `^https://${escapeRegExp(expectedAlias)}-${PREVIEW_WORKER_NAME}\\.(${DNS_LABEL_PATTERN})\\.workers\\.dev$`,
    "u",
  );
  const aliasUrlMatch = aliasUrlPattern.exec(aliasUrl);
  if (aliasUrlMatch === null) {
    reject(
      "Version Preview Alias URL must use the expected alias, fixed Worker name, and one valid workers.dev subdomain",
    );
  }
  if (aliasUrlMatch[1] !== workersDevSubdomain) {
    reject(
      "Version Preview Alias URL must use the same workers.dev subdomain as the version URL",
    );
  }

  return {
    versionId,
    versionUrl,
    aliasUrl,
    alias: expectedAlias,
    workerName: PREVIEW_WORKER_NAME,
    workersDevSubdomain,
  };
}

async function main() {
  const [outputPath, expectedAlias] = process.argv.slice(2);
  if (!outputPath || !expectedAlias) {
    reject(
      "usage: validate-preview-upload.mjs <wrangler-output-file> <expected-alias>",
    );
  }
  const output = await readFile(outputPath, "utf8");
  const receipt = validatePreviewUpload(output, expectedAlias);
  process.stdout.write(`${JSON.stringify(receipt)}\n`);
}

if (
  process.argv[1] &&
  pathToFileURL(path.resolve(process.argv[1])).href === import.meta.url
) {
  try {
    await main();
  } catch (error) {
    process.stderr.write(`${error.message}\n`);
    process.exitCode = 1;
  }
}
