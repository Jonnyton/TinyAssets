#!/usr/bin/env node

import { execFileSync } from "node:child_process";
import { readFileSync } from "node:fs";
import { dirname, resolve } from "node:path";
import { fileURLToPath } from "node:url";

import {
  assertNoRetiredSignatures,
  atomicWriteMirrors,
  buildRepoSnapshot,
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
    "refs/heads",
    "refs/remotes/origin",
  ]);
  return raw
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
}

function main() {
  const branches = refRows();
  const currentBranch = git(["branch", "--show-current"]) || "detached";
  const remote = git(["remote", "get-url", "origin"]);
  const head = git(["rev-parse", "--short", "HEAD"]);
  const mainCommit =
    branches.find((branch) => branch.name === "main")?.commit ??
    branches.find((branch) => branch.name === "origin/main")?.commit ??
    "";
  const dirty = git(["status", "--short"])
    .split(/\r?\n/)
    .filter(Boolean).length;
  const topology = JSON.parse(readFileSync(TOPOLOGY_PATH, "utf8"));
  const snapshot = buildRepoSnapshot({
    fetchedAt: new Date().toISOString(),
    repo: {
      id: "repo:TinyAssets",
      name: "TinyAssets",
      owner: "Jonnyton",
      remote_url: remote,
      current_branch: currentBranch,
      head,
      main: mainCommit,
      dirty_note:
        dirty === 0
          ? "Working tree clean when repo snapshot was generated."
          : `Working tree had ${dirty} changed paths when repo snapshot was generated.`,
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
