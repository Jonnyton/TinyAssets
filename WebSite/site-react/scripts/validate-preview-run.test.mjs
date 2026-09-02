import assert from "node:assert/strict";
import { mkdtemp, rm, writeFile } from "node:fs/promises";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { spawnSync } from "node:child_process";
import test from "node:test";
import { fileURLToPath } from "node:url";

import {
  MAX_ARTIFACT_BYTES,
  validatePreviewRun,
} from "./validate-preview-run.mjs";

const HEAD_SHA = "a".repeat(40);
const MERGE_SHA = "c".repeat(40);
const DIGEST = `sha256:${"b".repeat(64)}`;

function validInputs() {
  const repository = {
    id: 101,
    full_name: "tinyassets/tinyassets",
    default_branch: "main",
  };
  const pullRequest = {
    number: 42,
    state: "open",
    base: {
      ref: "main",
      repo: { id: repository.id, full_name: repository.full_name },
    },
    head: {
      sha: HEAD_SHA,
      repo: { id: repository.id, full_name: repository.full_name },
    },
  };
  const workflowRun = {
    id: 202,
    run_attempt: 3,
    status: "completed",
    conclusion: "success",
    event: "pull_request",
    workflow_id: 303,
    path: ".github/workflows/preview-worker.yml",
    head_sha: HEAD_SHA,
    repository: { id: repository.id, full_name: repository.full_name },
    head_repository: { id: repository.id, full_name: repository.full_name },
    pull_requests: [
      {
        number: pullRequest.number,
        head: {
          sha: HEAD_SHA,
          repo: { id: repository.id, full_name: repository.full_name },
        },
      },
    ],
  };
  const expectedWorkflow = {
    id: workflowRun.workflow_id,
    path: ".github/workflows/preview-worker.yml",
  };
  const expectedArtifactName = `react-preview-${pullRequest.number}-${workflowRun.run_attempt}`;
  const artifactList = {
    total_count: 1,
    artifacts: [
      {
        id: 404,
        name: expectedArtifactName,
        expired: false,
        size_in_bytes: 4096,
        digest: DIGEST,
        workflow_run: {
          id: workflowRun.id,
          head_sha: HEAD_SHA,
          head_repository_id: repository.id,
        },
      },
    ],
  };
  return {
    workflowRun,
    expectedWorkflow,
    pullRequest,
    repository,
    artifactList,
    expectedArtifactName,
  };
}

function reject(mutator, pattern) {
  const inputs = validInputs();
  mutator(inputs);
  assert.throws(() => validatePreviewRun(inputs), pattern);
}

test("returns a deterministic normalized receipt for one trusted run", () => {
  const inputs = validInputs();
  const expectedReceipt = {
    runId: 202,
    runAttempt: 3,
    prNumber: 42,
    headSha: HEAD_SHA,
    artifactId: 404,
    artifactDigest: DIGEST,
    artifactSize: 4096,
    alias: "p16-r5m-a3",
  };
  assert.deepEqual(validatePreviewRun(inputs), expectedReceipt);
  assert.deepEqual(validatePreviewRun(inputs), validatePreviewRun(inputs));
  assert.deepEqual(
    validatePreviewRun(
      inputs.workflowRun,
      inputs.expectedWorkflow,
      inputs.pullRequest,
      inputs.repository,
      inputs.artifactList,
      inputs.expectedArtifactName,
    ),
    expectedReceipt,
  );
});

test("CLI reads five JSON inputs and prints the normalized receipt", async () => {
  const inputs = validInputs();
  const directory = await mkdtemp(join(tmpdir(), "tinyassets-preview-run-"));
  try {
    const entries = [
      ["workflow-run.json", inputs.workflowRun],
      ["expected-workflow.json", inputs.expectedWorkflow],
      ["pull-request.json", inputs.pullRequest],
      ["repository.json", inputs.repository],
      ["artifact-list.json", inputs.artifactList],
    ];
    await Promise.all(
      entries.map(([name, value]) =>
        writeFile(join(directory, name), JSON.stringify(value)),
      ),
    );
    const script = fileURLToPath(
      new URL("./validate-preview-run.mjs", import.meta.url),
    );
    const result = spawnSync(
      process.execPath,
      [
        script,
        ...entries.map(([name]) => join(directory, name)),
        inputs.expectedArtifactName,
      ],
      { encoding: "utf8" },
    );
    assert.equal(result.status, 0, result.stderr);
    assert.deepEqual(JSON.parse(result.stdout), {
      runId: 202,
      runAttempt: 3,
      prNumber: 42,
      headSha: HEAD_SHA,
      artifactId: 404,
      artifactDigest: DIGEST,
      artifactSize: 4096,
      alias: "p16-r5m-a3",
    });
  } finally {
    await rm(directory, { recursive: true, force: true });
  }
});

test("alias is DNS-safe, bounded, and unique to the run attempt", () => {
  const first = validInputs();
  const nextRun = validInputs();
  nextRun.workflowRun.id = 203;
  nextRun.artifactList.artifacts[0].workflow_run.id = 203;
  const retry = validInputs();
  retry.workflowRun.run_attempt = 4;
  retry.expectedArtifactName = "react-preview-42-4";
  retry.artifactList.artifacts[0].name = retry.expectedArtifactName;
  const maximum = validInputs();
  maximum.pullRequest.number = Number.MAX_SAFE_INTEGER;
  maximum.workflowRun.pull_requests[0].number = Number.MAX_SAFE_INTEGER;
  maximum.workflowRun.id = Number.MAX_SAFE_INTEGER;
  maximum.workflowRun.run_attempt = Number.MAX_SAFE_INTEGER;
  maximum.artifactList.artifacts[0].workflow_run.id = Number.MAX_SAFE_INTEGER;
  maximum.expectedArtifactName = `react-preview-${Number.MAX_SAFE_INTEGER}-${Number.MAX_SAFE_INTEGER}`;
  maximum.artifactList.artifacts[0].name = maximum.expectedArtifactName;

  const aliases = [
    validatePreviewRun(first).alias,
    validatePreviewRun(nextRun).alias,
    validatePreviewRun(retry).alias,
    validatePreviewRun(maximum).alias,
  ];
  assert.deepEqual(aliases, [
    "p16-r5m-a3",
    "p16-r5n-a3",
    "p16-r5m-a4",
    "p2gosa7pa2gv-r2gosa7pa2gv-a2gosa7pa2gv",
  ]);
  assert.equal(new Set(aliases).size, aliases.length);
  for (const alias of aliases) {
    assert.match(alias, /^p[0-9a-z]+-r[0-9a-z]+-a[0-9a-z]+$/);
    assert.ok(alias.length + 1 + "tiny-site-react-preview".length <= 63);
  }
});

test("rejects non-successful and incomplete workflow runs", async (t) => {
  await t.test("failed", () =>
    reject(({ workflowRun }) => {
      workflowRun.conclusion = "failure";
    }, /conclusion/i),
  );
  await t.test("cancelled", () =>
    reject(({ workflowRun }) => {
      workflowRun.conclusion = "cancelled";
    }, /conclusion/i),
  );
  await t.test("not completed", () =>
    reject(({ workflowRun }) => {
      workflowRun.status = "in_progress";
    }, /status/i),
  );
});

test("rejects the wrong trigger, workflow identity, path, or repository", async (t) => {
  await t.test("wrong event", () =>
    reject(({ workflowRun }) => {
      workflowRun.event = "push";
    }, /event/i),
  );
  await t.test("wrong workflow id", () =>
    reject(({ workflowRun }) => {
      workflowRun.workflow_id += 1;
    }, /workflow id/i),
  );
  await t.test("wrong run path", () =>
    reject(({ workflowRun }) => {
      workflowRun.path = ".github/workflows/other.yml";
    }, /workflow path/i),
  );
  await t.test("wrong expected path", () =>
    reject(({ expectedWorkflow }) => {
      expectedWorkflow.path = ".github/workflows/other.yml";
    }, /workflow path/i),
  );
  await t.test("wrong run repository", () =>
    reject(({ workflowRun }) => {
      workflowRun.repository.id += 1;
    }, /repository/i),
  );
  await t.test("wrong head repository", () =>
    reject(({ workflowRun }) => {
      workflowRun.head_repository.full_name = "attacker/fork";
    }, /head repository/i),
  );
});

test("rejects absent, ambiguous, closed, stale, forked, or off-default PRs", async (t) => {
  await t.test("empty associated PRs", () =>
    reject(({ workflowRun }) => {
      workflowRun.pull_requests = [];
    }, /exactly one/i),
  );
  await t.test("multiple associated PRs", () =>
    reject(({ workflowRun }) => {
      workflowRun.pull_requests.push(
        structuredClone(workflowRun.pull_requests[0]),
      );
    }, /exactly one/i),
  );
  await t.test("closed current PR", () =>
    reject(({ pullRequest }) => {
      pullRequest.state = "closed";
    }, /open/i),
  );
  await t.test("non-default base", () =>
    reject(({ pullRequest }) => {
      pullRequest.base.ref = "release";
    }, /default branch/i),
  );
  await t.test("stale associated head", () =>
    reject(({ workflowRun }) => {
      workflowRun.pull_requests[0].head.sha = "d".repeat(40);
    }, /head sha/i),
  );
  await t.test("stale current PR head", () =>
    reject(({ pullRequest }) => {
      pullRequest.head.sha = "d".repeat(40);
    }, /head sha/i),
  );
  await t.test("malformed workflow-run head", () =>
    reject(({ workflowRun }) => {
      workflowRun.head_sha = "not-a-sha";
    }, /workflow run head sha/i),
  );
  await t.test("historical workflow-run head", () =>
    reject(({ workflowRun, artifactList }) => {
      workflowRun.head_sha = MERGE_SHA;
      artifactList.artifacts[0].workflow_run.head_sha = MERGE_SHA;
    }, /must match the current pull request head sha/i),
  );
  await t.test("forked current head", () =>
    reject(({ pullRequest }) => {
      pullRequest.head.repo.id = 999;
      pullRequest.head.repo.full_name = "attacker/fork";
    }, /head repository/i),
  );
  await t.test("associated PR number mismatch", () =>
    reject(({ workflowRun }) => {
      workflowRun.pull_requests[0].number = 43;
    }, /pull request number/i),
  );
});

test("rejects missing, duplicate, expired, or incorrectly named artifacts", async (t) => {
  await t.test("missing", () =>
    reject(({ artifactList }) => {
      artifactList.artifacts = [];
    }, /exactly one/i),
  );
  await t.test("duplicate", () =>
    reject(({ artifactList }) => {
      artifactList.artifacts.push(structuredClone(artifactList.artifacts[0]));
    }, /exactly one/i),
  );
  await t.test("expired", () =>
    reject(({ artifactList }) => {
      artifactList.artifacts[0].expired = true;
    }, /expired/i),
  );
  await t.test("wrong name", () =>
    reject(({ artifactList }) => {
      artifactList.artifacts[0].name = "react-preview-42-4";
    }, /exactly one/i),
  );
  await t.test("expected name is not numbered for the PR and run attempt", () =>
    reject((inputs) => {
      inputs.expectedArtifactName = "react-preview-42-4";
      inputs.artifactList.artifacts[0].name = "react-preview-42-4";
    }, /artifact name/i),
  );
});

test("rejects artifacts from the wrong run, head, or repository", async (t) => {
  await t.test("wrong run", () =>
    reject(({ artifactList }) => {
      artifactList.artifacts[0].workflow_run.id += 1;
    }, /artifact workflow run/i),
  );
  await t.test("wrong head", () =>
    reject(({ artifactList }) => {
      artifactList.artifacts[0].workflow_run.head_sha = "d".repeat(40);
    }, /artifact head sha/i),
  );
  await t.test("wrong repository", () =>
    reject(({ artifactList }) => {
      artifactList.artifacts[0].workflow_run.head_repository_id += 1;
    }, /artifact head repository/i),
  );
});

test("rejects non-positive, oversized, or malformed artifact metadata", async (t) => {
  assert.equal(MAX_ARTIFACT_BYTES, 25 * 1024 * 1024);
  const atLimit = validInputs();
  atLimit.artifactList.artifacts[0].size_in_bytes = MAX_ARTIFACT_BYTES;
  assert.equal(validatePreviewRun(atLimit).artifactSize, MAX_ARTIFACT_BYTES);

  await t.test("empty artifact", () =>
    reject(({ artifactList }) => {
      artifactList.artifacts[0].size_in_bytes = 0;
    }, /artifact size/i),
  );
  await t.test("oversized", () =>
    reject(({ artifactList }) => {
      artifactList.artifacts[0].size_in_bytes = MAX_ARTIFACT_BYTES + 1;
    }, /artifact size/i),
  );
  await t.test("bad digest algorithm", () =>
    reject(({ artifactList }) => {
      artifactList.artifacts[0].digest = `sha512:${"b".repeat(64)}`;
    }, /digest/i),
  );
  await t.test("bad digest hex", () =>
    reject(({ artifactList }) => {
      artifactList.artifacts[0].digest = `sha256:${"z".repeat(64)}`;
    }, /digest/i),
  );
});
