import { readFile } from "node:fs/promises";
import path from "node:path";
import { pathToFileURL } from "node:url";

export const EXPECTED_WORKFLOW_PATH = ".github/workflows/preview-worker.yml";
export const MAX_ARTIFACT_BYTES = 300 * 1024 * 1024;

function reject(message) {
  throw new Error(`Preview run rejected: ${message}`);
}

function requireObject(value, label) {
  if (value === null || typeof value !== "object" || Array.isArray(value)) {
    reject(`${label} must be an object`);
  }
  return value;
}

function requirePositiveInteger(value, label) {
  if (!Number.isSafeInteger(value) || value <= 0) {
    reject(`${label} must be a positive safe integer`);
  }
  return value;
}

function requireString(value, label) {
  if (typeof value !== "string" || value.length === 0) {
    reject(`${label} must be a non-empty string`);
  }
  return value;
}

function assertRepository(candidate, repository, label) {
  const value = requireObject(candidate, label);
  if (value.id !== repository.id || value.full_name !== repository.full_name) {
    reject(`${label} does not match the trusted repository`);
  }
}

function normalizeArguments(
  workflowRunOrOptions,
  expectedWorkflow,
  pullRequest,
  repository,
  artifactList,
  expectedArtifactName,
) {
  if (
    arguments.length === 1 &&
    workflowRunOrOptions !== null &&
    typeof workflowRunOrOptions === "object"
  ) {
    return workflowRunOrOptions;
  }
  return {
    workflowRun: workflowRunOrOptions,
    expectedWorkflow,
    pullRequest,
    repository,
    artifactList,
    expectedArtifactName,
  };
}

export function validatePreviewRun(...args) {
  const inputs = normalizeArguments(...args);
  const workflowRun = requireObject(inputs.workflowRun, "workflow run");
  const expectedWorkflow = requireObject(
    inputs.expectedWorkflow,
    "expected workflow",
  );
  const pullRequest = requireObject(inputs.pullRequest, "current pull request");
  const repository = requireObject(inputs.repository, "repository");
  const artifactList = requireObject(inputs.artifactList, "artifact list");

  const repositoryId = requirePositiveInteger(repository.id, "repository id");
  const repositoryName = requireString(
    repository.full_name,
    "repository full name",
  );
  const defaultBranch = requireString(
    repository.default_branch,
    "repository default branch",
  );
  const trustedRepository = {
    id: repositoryId,
    full_name: repositoryName,
  };

  if (workflowRun.status !== "completed") {
    reject("workflow run status must be completed");
  }
  if (workflowRun.conclusion !== "success") {
    reject("workflow run conclusion must be success");
  }
  if (workflowRun.event !== "pull_request") {
    reject("workflow run event must be pull_request");
  }

  const workflowId = requirePositiveInteger(
    expectedWorkflow.id,
    "expected workflow id",
  );
  if (workflowRun.workflow_id !== workflowId) {
    reject("workflow id does not match the trusted workflow");
  }
  if (
    expectedWorkflow.path !== EXPECTED_WORKFLOW_PATH ||
    workflowRun.path !== EXPECTED_WORKFLOW_PATH
  ) {
    reject(`workflow path must be exactly ${EXPECTED_WORKFLOW_PATH}`);
  }

  const runId = requirePositiveInteger(workflowRun.id, "workflow run id");
  const runAttempt = requirePositiveInteger(
    workflowRun.run_attempt,
    "workflow run attempt",
  );
  assertRepository(
    workflowRun.repository,
    trustedRepository,
    "workflow run repository",
  );
  assertRepository(
    workflowRun.head_repository,
    trustedRepository,
    "workflow run head repository",
  );

  if (
    !Array.isArray(workflowRun.pull_requests) ||
    workflowRun.pull_requests.length !== 1
  ) {
    reject("workflow run must have exactly one associated pull request");
  }
  const associatedPullRequest = requireObject(
    workflowRun.pull_requests[0],
    "associated pull request",
  );
  const prNumber = requirePositiveInteger(
    pullRequest.number,
    "current pull request number",
  );
  if (associatedPullRequest.number !== prNumber) {
    reject(
      "associated pull request number does not match the current pull request",
    );
  }
  if (pullRequest.state !== "open") {
    reject("current pull request must be open");
  }

  const base = requireObject(pullRequest.base, "current pull request base");
  if (base.ref !== defaultBranch) {
    reject("current pull request base must be the repository default branch");
  }
  assertRepository(
    base.repo,
    trustedRepository,
    "current pull request base repository",
  );

  const head = requireObject(pullRequest.head, "current pull request head");
  assertRepository(
    head.repo,
    trustedRepository,
    "current pull request head repository",
  );
  const headSha = requireString(head.sha, "current pull request head sha");
  if (!/^[0-9a-f]{40}$/u.test(headSha)) {
    reject(
      "current pull request head sha must be a lowercase 40-character hex digest",
    );
  }

  const associatedHead = requireObject(
    associatedPullRequest.head,
    "associated pull request head",
  );
  if (associatedHead.sha !== headSha) {
    reject(
      "associated pull request head sha must match the current pull request head sha",
    );
  }
  const workflowRunHeadSha = requireString(
    workflowRun.head_sha,
    "workflow run head sha",
  );
  if (!/^[0-9a-f]{40}$/u.test(workflowRunHeadSha)) {
    reject("workflow run head sha must be a lowercase 40-character hex digest");
  }
  const associatedHeadRepository = requireObject(
    associatedHead.repo,
    "associated pull request head repository",
  );
  if (associatedHeadRepository.id !== repositoryId) {
    reject(
      "associated pull request head repository does not match the trusted repository",
    );
  }

  const expectedArtifactName = requireString(
    inputs.expectedArtifactName,
    "expected artifact name",
  );
  const derivedArtifactName = `react-preview-${prNumber}-${runAttempt}`;
  if (expectedArtifactName !== derivedArtifactName) {
    reject(
      "expected artifact name must match the current pull request number and run attempt",
    );
  }
  if (!Array.isArray(artifactList.artifacts)) {
    reject("artifact list artifacts must be an array");
  }
  const matchingArtifacts = artifactList.artifacts.filter(
    (artifact) => artifact?.name === expectedArtifactName,
  );
  if (matchingArtifacts.length !== 1) {
    reject(
      "artifact list must contain exactly one artifact with the expected name",
    );
  }

  const artifact = requireObject(matchingArtifacts[0], "artifact");
  if (artifact.expired !== false) {
    reject("artifact must not be expired");
  }
  const artifactId = requirePositiveInteger(artifact.id, "artifact id");
  const artifactSize = requirePositiveInteger(
    artifact.size_in_bytes,
    "artifact size",
  );
  if (artifactSize > MAX_ARTIFACT_BYTES) {
    reject(`artifact size must not exceed ${MAX_ARTIFACT_BYTES} bytes`);
  }
  const artifactDigest = requireString(artifact.digest, "artifact digest");
  if (!/^sha256:[0-9a-f]{64}$/u.test(artifactDigest)) {
    reject(
      "artifact digest must be sha256 followed by 64 lowercase hex characters",
    );
  }

  const artifactRun = requireObject(
    artifact.workflow_run,
    "artifact workflow run",
  );
  if (artifactRun.id !== runId) {
    reject("artifact workflow run id does not match the triggering run");
  }
  if (artifactRun.head_sha !== workflowRunHeadSha) {
    reject("artifact head sha does not match the triggering workflow run");
  }
  if (artifactRun.head_repository_id !== repositoryId) {
    reject("artifact head repository does not match the trusted repository");
  }

  return {
    runId,
    runAttempt,
    prNumber,
    headSha,
    artifactId,
    artifactDigest,
    artifactSize,
    alias: `pr-${prNumber}`,
  };
}

async function readJson(filePath, label) {
  try {
    return JSON.parse(await readFile(filePath, "utf8"));
  } catch (error) {
    throw new Error(
      `Could not read ${label} JSON from ${filePath}: ${error.message}`,
    );
  }
}

async function main() {
  const [
    workflowRunPath,
    expectedWorkflowPath,
    pullRequestPath,
    repositoryPath,
    artifactListPath,
    expectedArtifactName,
  ] = process.argv.slice(2);
  if (
    !workflowRunPath ||
    !expectedWorkflowPath ||
    !pullRequestPath ||
    !repositoryPath ||
    !artifactListPath ||
    !expectedArtifactName
  ) {
    throw new Error(
      "Usage: validate-preview-run.mjs <workflow-run.json> <expected-workflow.json> <pull-request.json> <repository.json> <artifact-list.json> <expected-artifact-name>",
    );
  }

  const receipt = validatePreviewRun({
    workflowRun: await readJson(workflowRunPath, "workflow run"),
    expectedWorkflow: await readJson(expectedWorkflowPath, "expected workflow"),
    pullRequest: await readJson(pullRequestPath, "pull request"),
    repository: await readJson(repositoryPath, "repository"),
    artifactList: await readJson(artifactListPath, "artifact list"),
    expectedArtifactName,
  });
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
