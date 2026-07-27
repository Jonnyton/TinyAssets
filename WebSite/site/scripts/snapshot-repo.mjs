#!/usr/bin/env node

import { execFileSync } from "node:child_process";
import { readFileSync } from "node:fs";
import { dirname, resolve } from "node:path";
import { fileURLToPath } from "node:url";

import {
  assertNoRetiredSignatures,
  atomicWriteMirrors,
  buildRepoSnapshot,
  normalizePublicOriginRefs,
  sanitizePublicRemoteUrl,
  serializeSnapshot,
} from "./snapshot-helpers.mjs";

const SCRIPT_DIR = dirname(fileURLToPath(import.meta.url));
const REPO_ROOT = resolve(SCRIPT_DIR, "../../..");
const SITE_ROOT = resolve(SCRIPT_DIR, "..");
const TOPOLOGY_PATH = resolve(
  SITE_ROOT,
  "src",
  "lib",
  "content",
  "repo-topology.json",
);
const OUTPUT_PATH = resolve(
  SITE_ROOT,
  "src",
  "lib",
  "content",
  "repo-snapshot.json",
);

function git(args) {
  return execFileSync("git", args, {
    cwd: REPO_ROOT,
    encoding: "utf8",
    stdio: ["ignore", "pipe", "pipe"],
  }).trim();
}

function refRows() {
  const raw = git([
    "for-each-ref",
    "--format=%(refname:short)|%(objectname:short)|%(committerdate:iso8601-strict)|%(subject)",
    "refs/remotes/origin",
  ]);
  const refs = raw
    .split(/\r?\n/)
    .filter(Boolean)
    .map((line) => {
      const [name, commit, date, ...subjectParts] = line.split("|");
      return {
        id: `git:${name}`,
        name,
        kind:
          name.startsWith("origin/") || name === "origin" ? "remote" : "local",
        commit,
        date,
        subject: subjectParts.join("|"),
      };
    })
    .filter((branch) => branch.name !== "origin");
  return normalizePublicOriginRefs(refs);
}

function main() {
  const branches = refRows();
  const remote = sanitizePublicRemoteUrl(git(["remote", "get-url", "origin"]));
  const mainCommit =
    branches.find((branch) => branch.name === "main")?.commit ?? "";
  const topology = JSON.parse(readFileSync(TOPOLOGY_PATH, "utf8"));
  const snapshot = buildRepoSnapshot({
    fetchedAt: new Date().toISOString(),
    repo: {
      id: "repo:TinyAssets",
      name: "TinyAssets",
      owner: "Jonnyton",
      remote_url: remote,
      main: mainCommit,
    },
    branches,
    topology,
  });
  assertNoRetiredSignatures(snapshot);
  const bytes = serializeSnapshot(snapshot);
  atomicWriteMirrors([OUTPUT_PATH], bytes);
  if (readFileSync(OUTPUT_PATH, "utf8") !== bytes) {
    throw new Error("post-write repository snapshot check failed");
  }
  console.log(
    `[snapshot:repo] wrote ${OUTPUT_PATH} (${branches.length} refs, ` +
      `${snapshot.areas.length} areas, ${snapshot.workflow_branches.length} workflow branches)`,
  );
}

try {
  main();
} catch (error) {
  console.error(`[snapshot:repo] ERROR: ${error?.stack ?? error}`);
  process.exitCode = 1;
}
