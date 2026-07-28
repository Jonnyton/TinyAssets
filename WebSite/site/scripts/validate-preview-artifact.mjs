import { createHash } from "node:crypto";
import {
  constants,
  lstat,
  mkdir,
  open,
  opendir,
  readdir,
  writeFile,
} from "node:fs/promises";
import path from "node:path";
import { pathToFileURL } from "node:url";

export const DEFAULT_LIMITS = Object.freeze({
  maxDirectoryCount: 2_000,
  maxEntryCount: 12_000,
  maxDepth: 32,
  maxFileBytes: 25 * 1024 * 1024,
  maxFileCount: 10_000,
  maxRelativePathBytes: 1_024,
  maxRelativePathChars: 512,
  maxTotalBytes: 250 * 1024 * 1024,
});

const ALLOWED_EXTENSIONS = new Set([
  ".avif",
  ".css",
  ".gif",
  ".htm",
  ".html",
  ".ico",
  ".jpeg",
  ".jpg",
  ".js",
  ".json",
  ".map",
  ".mp4",
  ".otf",
  ".png",
  ".svg",
  ".ttf",
  ".txt",
  ".wasm",
  ".webmanifest",
  ".webp",
  ".woff",
  ".woff2",
  ".xml",
]);

const FORBIDDEN_BASENAMES = new Set([
  ".git",
  ".github",
  ".npmrc",
  ".wrangler",
  "_headers",
  "_redirects",
  "_routes.json",
  "_worker.js",
  "cname",
  "package-lock.json",
  "package.json",
  "pnpm-lock.yaml",
  "wrangler.json",
  "wrangler.jsonc",
  "wrangler.toml",
  "yarn.lock",
]);

const ARCHIVE_EXTENSIONS = [
  ".7z",
  ".br",
  ".bz2",
  ".gz",
  ".rar",
  ".cab",
  ".dmg",
  ".iso",
  ".lz",
  ".lz4",
  ".tar",
  ".tar.bz2",
  ".tar.gz",
  ".tar.xz",
  ".tgz",
  ".xz",
  ".zip",
  ".zst",
];

function assertPositiveInteger(value, name) {
  if (!Number.isSafeInteger(value) || value <= 0) {
    throw new Error(`${name} must be a positive safe integer`);
  }
}

function normalizedLimits(overrides) {
  const limits = { ...DEFAULT_LIMITS, ...overrides };
  assertPositiveInteger(limits.maxDirectoryCount, "maxDirectoryCount");
  assertPositiveInteger(limits.maxEntryCount, "maxEntryCount");
  assertPositiveInteger(limits.maxDepth, "maxDepth");
  assertPositiveInteger(limits.maxFileBytes, "maxFileBytes");
  assertPositiveInteger(limits.maxFileCount, "maxFileCount");
  assertPositiveInteger(limits.maxRelativePathBytes, "maxRelativePathBytes");
  assertPositiveInteger(limits.maxRelativePathChars, "maxRelativePathChars");
  assertPositiveInteger(limits.maxTotalBytes, "maxTotalBytes");
  return limits;
}

function assertSafeComponent(component) {
  const lower = component.toLowerCase();
  const unsafe =
    component.length === 0 ||
    component !== component.normalize("NFC") ||
    component.startsWith(".") ||
    component.endsWith(".") ||
    component.endsWith(" ") ||
    component.includes("..") ||
    component.includes("/") ||
    component.includes("\\") ||
    component.includes(":") ||
    /[\u0000-\u001f\u007f]/u.test(component) ||
    /%(?:2e|2f|5c)/iu.test(component);
  if (unsafe) {
    throw new Error(`Unsafe artifact path component: ${JSON.stringify(component)}`);
  }
  if (FORBIDDEN_BASENAMES.has(lower)) {
    throw new Error(`Forbidden artifact entry: ${component}`);
  }
}

function assertAllowedFile(relativePath) {
  const basename = path.posix.basename(relativePath);
  const lower = basename.toLowerCase();
  if (
    FORBIDDEN_BASENAMES.has(lower) ||
    lower.startsWith("wrangler.") ||
    lower === "package-lock.json" ||
    lower === "package.json"
  ) {
    throw new Error(`Forbidden artifact file: ${relativePath}`);
  }
  if (ARCHIVE_EXTENSIONS.some((extension) => lower.endsWith(extension))) {
    throw new Error(`Forbidden archive in artifact: ${relativePath}`);
  }
  const extension = path.posix.extname(lower);
  if (!ALLOWED_EXTENSIONS.has(extension)) {
    throw new Error(`Unexpected artifact file extension: ${relativePath}`);
  }
}

function assertSeparateTrees(source, destination) {
  const sourceToDestination = path.relative(source, destination);
  const destinationToSource = path.relative(destination, source);
  if (
    source === destination ||
    (sourceToDestination !== "" &&
      !sourceToDestination.startsWith(`..${path.sep}`) &&
      sourceToDestination !== ".." &&
      !path.isAbsolute(sourceToDestination)) ||
    (destinationToSource !== "" &&
      !destinationToSource.startsWith(`..${path.sep}`) &&
      destinationToSource !== ".." &&
      !path.isAbsolute(destinationToSource))
  ) {
    throw new Error("Artifact source and destination must be separate, non-nested trees");
  }
}

async function assertDirectory(pathname, label) {
  let metadata;
  try {
    metadata = await lstat(pathname);
  } catch (error) {
    if (error?.code === "ENOENT") {
      throw new Error(`${label} does not exist: ${pathname}`);
    }
    throw error;
  }
  if (metadata.isSymbolicLink() || !metadata.isDirectory()) {
    throw new Error(`${label} must be a real directory, not a symlink or non-directory`);
  }
}

async function assertCleanDestination(destination) {
  let metadata;
  try {
    metadata = await lstat(destination);
  } catch (error) {
    if (error?.code === "ENOENT") return;
    throw error;
  }
  if (metadata.isSymbolicLink() || !metadata.isDirectory()) {
    throw new Error("Preview artifact destination must be an empty, real directory");
  }
  if ((await readdir(destination)).length !== 0) {
    throw new Error("Preview artifact destination must be empty");
  }
}

async function inventory(source, limits) {
  const files = [];
  const directories = new Set();
  const canonicalPaths = new Set();
  let entryCount = 0;
  let totalBytes = 0;

  async function walk(absoluteDirectory, relativeDirectory, depth) {
    const directory = await opendir(absoluteDirectory);
    for await (const entry of directory) {
      assertSafeComponent(entry.name);
      const relativePath = relativeDirectory
        ? `${relativeDirectory}/${entry.name}`
        : entry.name;
      const entryDepth = depth + 1;
      if (entryDepth > limits.maxDepth) {
        throw new Error(
          `Artifact exceeds the maximum depth of ${limits.maxDepth}: ${relativePath}`,
        );
      }
      const relativePathChars = [...relativePath].length;
      if (relativePathChars > limits.maxRelativePathChars) {
        throw new Error(
          `Artifact relative path exceeds the character limit of ${limits.maxRelativePathChars}: ${relativePath}`,
        );
      }
      const relativePathBytes = Buffer.byteLength(relativePath, "utf8");
      if (relativePathBytes > limits.maxRelativePathBytes) {
        throw new Error(
          `Artifact relative path exceeds the UTF-8 byte limit of ${limits.maxRelativePathBytes}: ${relativePath}`,
        );
      }
      entryCount += 1;
      if (entryCount > limits.maxEntryCount) {
        throw new Error(
          `Artifact exceeds the total-entry limit of ${limits.maxEntryCount}`,
        );
      }
      const canonicalPath = relativePath.normalize("NFC").toLowerCase();
      if (canonicalPaths.has(canonicalPath)) {
        throw new Error(`Artifact contains a case- or Unicode-colliding path: ${relativePath}`);
      }
      canonicalPaths.add(canonicalPath);

      const absolutePath = path.join(absoluteDirectory, entry.name);
      const metadata = await lstat(absolutePath);
      if (metadata.isSymbolicLink()) {
        throw new Error(`Artifact contains a symlink: ${relativePath}`);
      }
      if (metadata.isDirectory()) {
        if (directories.size + 1 > limits.maxDirectoryCount) {
          throw new Error(
            `Artifact exceeds the directory-count limit of ${limits.maxDirectoryCount}`,
          );
        }
        directories.add(relativePath);
        await walk(absolutePath, relativePath, entryDepth);
        continue;
      }
      if (!metadata.isFile()) {
        throw new Error(`Artifact contains a non-regular entry: ${relativePath}`);
      }
      if (metadata.nlink !== 1) {
        throw new Error(`Artifact contains a hard-linked file: ${relativePath}`);
      }
      assertAllowedFile(relativePath);
      if ((metadata.mode & 0o111) !== 0) {
        throw new Error(`Artifact contains an executable file: ${relativePath}`);
      }
      if (metadata.size > limits.maxFileBytes) {
        throw new Error(`Artifact file exceeds the per-file size limit: ${relativePath}`);
      }
      if (files.length + 1 > limits.maxFileCount) {
        throw new Error(`Artifact exceeds the file-count limit of ${limits.maxFileCount}`);
      }
      totalBytes += metadata.size;
      if (totalBytes > limits.maxTotalBytes) {
        throw new Error(`Artifact exceeds the total-size limit of ${limits.maxTotalBytes} bytes`);
      }
      files.push({
        absolutePath,
        relativePath,
        size: metadata.size,
        mode: metadata.mode,
        dev: metadata.dev,
        ino: metadata.ino,
        mtimeMs: metadata.mtimeMs,
      });
    }
  }

  await walk(source, "", 0);
  files.sort((left, right) =>
    left.relativePath < right.relativePath ? -1 : left.relativePath > right.relativePath ? 1 : 0,
  );

  const filePaths = new Set(files.map((entry) => entry.relativePath));
  for (const requiredFile of ["index.html", "404.html"]) {
    if (!filePaths.has(requiredFile)) {
      throw new Error(`Preview artifact is missing required root file ${requiredFile}`);
    }
  }
  if (!directories.has("_next/static")) {
    throw new Error("Preview artifact is missing required directory _next/static");
  }

  return { files, totalBytes };
}

async function readUnchangedRegularFile(entry) {
  const flags = constants.O_RDONLY | (constants.O_NOFOLLOW ?? 0);
  let handle;
  try {
    handle = await open(entry.absolutePath, flags);
    const before = await handle.stat();
    if (
      !before.isFile() ||
      (before.mode & 0o111) !== 0 ||
      before.size !== entry.size ||
      before.dev !== entry.dev ||
      before.ino !== entry.ino ||
      before.nlink !== 1 ||
      before.mtimeMs !== entry.mtimeMs
    ) {
      throw new Error(`Artifact file changed during validation: ${entry.relativePath}`);
    }
    const contents = await handle.readFile();
    const after = await handle.stat();
    if (
      after.size !== before.size ||
      after.mtimeMs !== before.mtimeMs ||
      contents.byteLength !== entry.size
    ) {
      throw new Error(`Artifact file changed while copying: ${entry.relativePath}`);
    }
    return contents;
  } catch (error) {
    if (error?.code === "ELOOP") {
      throw new Error(`Artifact file became a symlink: ${entry.relativePath}`);
    }
    throw error;
  } finally {
    await handle?.close();
  }
}

export async function validateAndCopyPreviewArtifact(
  sourceArgument,
  destinationArgument,
  limitOverrides = {},
) {
  if (!sourceArgument || !destinationArgument) {
    throw new Error("Usage: validate-preview-artifact.mjs <artifact-root> <clean-destination>");
  }

  const source = path.resolve(sourceArgument);
  const destination = path.resolve(destinationArgument);
  assertSeparateTrees(source, destination);
  await assertDirectory(source, "Preview artifact root");
  await assertCleanDestination(destination);

  const limits = normalizedLimits(limitOverrides);
  const { files, totalBytes } = await inventory(source, limits);

  await mkdir(destination, { recursive: true });
  const manifestFiles = [];
  for (const entry of files) {
    const contents = await readUnchangedRegularFile(entry);
    const outputPath = path.join(destination, ...entry.relativePath.split("/"));
    await mkdir(path.dirname(outputPath), { recursive: true });
    await writeFile(outputPath, contents, { flag: "wx", mode: 0o644 });
    manifestFiles.push({
      path: entry.relativePath,
      size: contents.byteLength,
      sha256: createHash("sha256").update(contents).digest("hex"),
    });
  }

  return {
    version: 1,
    fileCount: manifestFiles.length,
    totalBytes,
    files: manifestFiles,
  };
}

async function main() {
  try {
    const manifest = await validateAndCopyPreviewArtifact(process.argv[2], process.argv[3]);
    process.stdout.write(`${JSON.stringify(manifest, null, 2)}\n`);
  } catch (error) {
    process.stderr.write(`Preview artifact rejected: ${error.message}\n`);
    process.exitCode = 1;
  }
}

if (process.argv[1] && pathToFileURL(path.resolve(process.argv[1])).href === import.meta.url) {
  await main();
}
