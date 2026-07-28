import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { dirname, resolve } from "node:path";
import test from "node:test";
import { fileURLToPath } from "node:url";
import { parse } from "yaml";

const here = dirname(fileURLToPath(import.meta.url));
const read = (relativePath) => readFileSync(resolve(here, relativePath), "utf8");

const buildWorkflowText = read("../../../.github/workflows/preview-worker.yml");
const deployWorkflowText = read(
  "../../../.github/workflows/preview-worker-deploy.yml",
);
const securityWorkflowText = read(
  "../../../.github/workflows/preview-security.yml",
);
const buildWorkflow = parse(buildWorkflowText);
const deployWorkflow = parse(deployWorkflowText);
const securityWorkflow = parse(securityWorkflowText);
const trustedWorkerConfig = read("../../site-react/wrangler.preview.toml");
const trustedWorkerProgram = read("../../site-react/cf-worker/worker.js");
const deployToolsPackage = JSON.parse(
  read("../../site-react/preview-deploy-tools/package.json"),
);
const deployToolsLock = JSON.parse(
  read("../../site-react/preview-deploy-tools/package-lock.json"),
);

const ACTIONS = Object.freeze({
  checkout: "actions/checkout@11d5960a326750d5838078e36cf38b85af677262",
  download:
    "actions/download-artifact@d3f86a106a0bac45b974a628896c90dbdf5c8093",
  setupNode:
    "actions/setup-node@49933ea5288caeca8642d1e84afbd3f7d6820020",
  upload:
    "actions/upload-artifact@ea165f8d65b6e75b540449e92b4886f43607fa02",
});
const ALLOWED_ACTIONS = new Set(Object.values(ACTIONS));

function actionSteps(workflow) {
  return Object.values(workflow.jobs).flatMap((job) =>
    job.steps.filter((step) => step.uses),
  );
}

function namedStep(job, name) {
  const step = job.steps.find((candidate) => candidate.name === name);
  assert.ok(step, `missing workflow step: ${name}`);
  return step;
}

test("pull-request build has one unprivileged static-export job", () => {
  assert.deepEqual(Object.keys(buildWorkflow.on), ["pull_request"]);
  assert.deepEqual(buildWorkflow.on.pull_request.paths, [
    "WebSite/site-react/**",
    "WebSite/shared/**",
    "WebSite/site/scripts/preview-worker-security.test.mjs",
    "WebSite/site/scripts/validate-preview-*.mjs",
    "WebSite/site/package.json",
    "WebSite/site/package-lock.json",
    "WebSite/design-system/**",
    ".github/workflows/preview-worker.yml",
    ".github/workflows/preview-worker-deploy.yml",
  ]);
  assert.deepEqual(buildWorkflow.permissions, { contents: "read" });
  assert.deepEqual(Object.keys(buildWorkflow.jobs), ["build"]);
  assert.equal(buildWorkflow.jobs.build.environment, undefined);
  assert.doesNotMatch(buildWorkflowText, /\bsecrets\s*(?:\.|\[)/);
  assert.doesNotMatch(buildWorkflowText, /\bpull-requests:\s*write\b/);
  assert.doesNotMatch(buildWorkflowText, /\bcache\b/i);
  assert.doesNotMatch(buildWorkflowText, /\bwrangler\b/i);

  const checkout = buildWorkflow.jobs.build.steps.find(
    (step) => step.uses === ACTIONS.checkout,
  );
  assert.deepEqual(checkout.with, { "persist-credentials": false });
  const upload = buildWorkflow.jobs.build.steps.find(
    (step) => step.uses === ACTIONS.upload,
  );
  assert.deepEqual(upload.with, {
    name: "react-preview-${{ github.event.pull_request.number }}-${{ github.run_attempt }}",
    path: "WebSite/site-react/out/",
    "if-no-files-found": "error",
    "include-hidden-files": false,
    overwrite: false,
    "retention-days": 1,
  });
});

test("preview trust-boundary contract is an unfiltered required-check candidate", () => {
  assert.deepEqual(Object.keys(securityWorkflow.on), ["pull_request", "push"]);
  assert.equal(securityWorkflow.on.pull_request, null);
  assert.deepEqual(securityWorkflow.on.push, { branches: ["main"] });
  assert.deepEqual(securityWorkflow.permissions, { contents: "read" });
  assert.deepEqual(Object.keys(securityWorkflow.jobs), ["contract"]);
  const { contract } = securityWorkflow.jobs;
  assert.equal(contract.environment, undefined);
  assert.deepEqual(contract.permissions, undefined);
  assert.doesNotMatch(
    securityWorkflowText,
    /\bsecrets\s*(?:\.|\[)|\b(?:issues|pull-requests|actions):\s*write\b|\bcache\b|\bwrangler\b/i,
  );
  const checkout = contract.steps.find((step) => step.uses === ACTIONS.checkout);
  assert.deepEqual(checkout.with, { "persist-credentials": false });
  const testStep = namedStep(contract, "Run preview trust-boundary contracts");
  assert.equal(testStep["working-directory"], "WebSite/site");
  assert.equal(testStep.run, "npm ci\nnpm test\n");
});

test("every external action is one exact reviewed commit", () => {
  const allSteps = [
    ...actionSteps(buildWorkflow),
    ...actionSteps(deployWorkflow),
    ...actionSteps(securityWorkflow),
  ];
  assert.ok(allSteps.length > 0);
  for (const step of allSteps) {
    assert.ok(ALLOWED_ACTIONS.has(step.uses), `unreviewed action: ${step.uses}`);
    assert.match(step.uses, /@[0-9a-f]{40}$/);
  }
});

test("trusted workflow-run graph keeps artifact intake outside the environment", () => {
  assert.deepEqual(Object.keys(deployWorkflow.on), ["workflow_run"]);
  assert.deepEqual(deployWorkflow.on.workflow_run, {
    workflows: ["preview-worker"],
    types: ["completed"],
  });
  assert.deepEqual(deployWorkflow.permissions, {});
  assert.equal(
    deployWorkflow.concurrency.group,
    "preview-worker-deploy-${{ github.event.workflow_run.pull_requests[0].number || github.event.workflow_run.id }}",
  );
  assert.equal(deployWorkflow.concurrency["cancel-in-progress"], false);
  assert.deepEqual(Object.keys(deployWorkflow.jobs), [
    "intake",
    "deploy",
    "comment",
  ]);

  const { intake, deploy, comment } = deployWorkflow.jobs;
  assert.equal(intake.environment, undefined);
  assert.deepEqual(intake.permissions, {
    actions: "read",
    contents: "read",
    "pull-requests": "read",
  });
  assert.deepEqual(deploy.environment, { name: "react-preview" });
  assert.deepEqual(deploy.permissions, {
    actions: "read",
    contents: "read",
    "pull-requests": "read",
  });
  assert.deepEqual(comment.permissions, { "pull-requests": "write" });
  assert.equal(comment.environment, undefined);

  for (const job of [intake, deploy]) {
    const checkouts = job.steps.filter((step) => step.uses === ACTIONS.checkout);
    assert.equal(checkouts.length, 1);
    assert.equal(checkouts[0].with.ref, "${{ github.sha }}");
    assert.equal(checkouts[0].with.path, "trusted-source");
    assert.equal(checkouts[0].with["persist-credentials"], false);
  }

  const intakeDownload = intake.steps.find(
    (step) => step.uses === ACTIONS.download,
  );
  assert.equal(
    intakeDownload.with["artifact-ids"],
    "${{ steps.receipt.outputs.artifact_id }}",
  );
  assert.equal(intakeDownload.with["run-id"], "${{ github.event.workflow_run.id }}");
  const deployDownload = deploy.steps.find(
    (step) => step.uses === ACTIONS.download,
  );
  assert.equal(
    deployDownload.with["artifact-ids"],
    "${{ needs.intake.outputs.sanitized_artifact_id }}",
  );

  const intakeValidation = namedStep(
    intake,
    "Validate run, PR, workflow, and exact artifact identity",
  ).run;
  assert.match(intakeValidation, /validate-preview-run\.mjs/);
  assert.match(intakeValidation, /react-preview-\$\{PR_NUMBER\}-\$\{RUN_ATTEMPT\}/);
  const artifactValidation = namedStep(
    intake,
    "Sanitize static export and write deterministic manifest",
  ).run;
  assert.match(artifactValidation, /validate-preview-artifact\.mjs/);
  const revalidation = namedStep(
    deploy,
    "Revalidate manifest and stage trusted Worker",
  ).run;
  assert.match(revalidation, /validate-preview-artifact\.mjs/);
  assert.match(revalidation, /\bcmp\b/);
});

test("Cloudflare credentials exist only on the locked per-PR version upload", () => {
  const { intake, deploy, comment } = deployWorkflow.jobs;
  const upload = namedStep(deploy, "Upload trusted per-PR preview version");
  assert.deepEqual(
    Object.keys(upload.env).sort(),
    [
      "CLOUDFLARE_ACCOUNT_ID",
      "CLOUDFLARE_API_TOKEN",
      "EXPECTED_HEAD_SHA",
      "PREVIEW_ALIAS",
      "PR_NUMBER",
    ],
  );
  assert.equal(
    upload.env.CLOUDFLARE_API_TOKEN,
    "${{ secrets.CLOUDFLARE_PREVIEW_API_TOKEN }}",
  );
  assert.equal(
    upload.env.CLOUDFLARE_ACCOUNT_ID,
    "${{ vars.CLOUDFLARE_PREVIEW_ACCOUNT_ID }}",
  );
  assert.deepEqual(
    deployWorkflowText.match(
      /\$\{\{[^}]*\bsecrets\s*(?:\.|\[)[^}]*\}\}/g,
    ),
    ["${{ secrets.CLOUDFLARE_PREVIEW_API_TOKEN }}"],
  );
  assert.doesNotMatch(
    JSON.stringify(intake),
    /CLOUDFLARE_|\bsecrets\s*(?:\.|\[)/,
  );
  assert.doesNotMatch(
    JSON.stringify(comment),
    /CLOUDFLARE_|\bsecrets\s*(?:\.|\[)/,
  );
  assert.equal(
    upload.run,
    `set -euo pipefail
test -n "\${CLOUDFLARE_API_TOKEN}"
test -n "\${CLOUDFLARE_ACCOUNT_ID}"
tool="\${GITHUB_WORKSPACE}/trusted-source/WebSite/site-react/preview-deploy-tools/node_modules/.bin/wrangler"
deployment="\${RUNNER_TEMP}/preview-deployment"
"\${tool}" versions upload \\
  --config "\${deployment}/wrangler.preview.toml" \\
  --preview-alias "\${PREVIEW_ALIAS}" \\
  --message "TinyAssets PR #\${PR_NUMBER} \${EXPECTED_HEAD_SHA}" \\
  --experimental-provision=false \\
  --experimental-auto-create=false 2>&1 \\
  | tee "\${RUNNER_TEMP}/wrangler-output.log"
`,
  );
  assert.doesNotMatch(deployWorkflowText, /\bpull_request_target\b/);
  assert.doesNotMatch(deployWorkflowText, /\bcache\b/i);
});

test("immutable preview receipt binds source artifact and Cloudflare version", () => {
  const { deploy, comment } = deployWorkflow.jobs;
  assert.equal(
    deploy.outputs.url,
    "${{ steps.preview-url.outputs.version_url }}",
  );
  assert.equal(
    deploy.outputs.alias_url,
    "${{ steps.preview-url.outputs.alias_url }}",
  );
  assert.equal(
    deploy.outputs.version_id,
    "${{ steps.preview-url.outputs.version_id }}",
  );

  const receiptStep = namedStep(deploy, "Record immutable preview identity");
  assert.deepEqual(receiptStep.env, {
    PREVIEW_ALIAS: "${{ needs.intake.outputs.alias }}",
  });
  assert.equal(
    receiptStep.run,
    `set -euo pipefail
receipt="\${RUNNER_TEMP}/preview-upload-receipt.json"
node "\${GITHUB_WORKSPACE}/trusted-source/WebSite/site/scripts/validate-preview-upload.mjs" \\
  "\${RUNNER_TEMP}/wrangler-output.log" \\
  "\${PREVIEW_ALIAS}" > "\${receipt}"
{
  echo "alias_url=$(jq -r .aliasUrl "\${receipt}")"
  echo "version_id=$(jq -r .versionId "\${receipt}")"
  echo "version_url=$(jq -r .versionUrl "\${receipt}")"
} >> "\${GITHUB_OUTPUT}"
`,
  );

  const commentStep = namedStep(
    comment,
    "Recheck head and upsert preview comment",
  );
  assert.equal(
    commentStep.env.INPUT_ARTIFACT_DIGEST,
    "${{ needs.intake.outputs.input_artifact_digest }}",
  );
  assert.equal(
    commentStep.env.VERSION_ID,
    "${{ needs.deploy.outputs.version_id }}",
  );
  assert.equal(commentStep.env.RUN_ID, "${{ needs.intake.outputs.run_id }}");
  assert.equal(
    commentStep.env.RUN_ATTEMPT,
    "${{ needs.intake.outputs.run_attempt }}",
  );
  assert.match(commentStep.run, /Artifact:/);
  assert.match(commentStep.run, /Cloudflare version:/);
  assert.match(commentStep.run, /Never-reused alias:/);
});

test("privileged toolchain and Worker target are fixed by trusted files", () => {
  assert.equal(deployToolsPackage.dependencies.wrangler, "4.114.0");
  assert.equal(deployToolsLock.packages[""].dependencies.wrangler, "4.114.0");
  assert.equal(
    deployToolsLock.packages["node_modules/wrangler"].version,
    "4.114.0",
  );
  assert.match(
    deployToolsLock.packages["node_modules/wrangler"].integrity,
    /^sha512-/,
  );
  assert.match(trustedWorkerConfig, /^name = "tiny-site-react-preview"$/m);
  assert.match(trustedWorkerConfig, /^main = "cf-worker\/worker\.js"$/m);
  assert.match(trustedWorkerConfig, /^workers_dev = true$/m);
  assert.match(trustedWorkerConfig, /^preview_urls = true$/m);
  assert.doesNotMatch(
    trustedWorkerConfig,
    /^\s*(?:routes?|custom_domains?)\s*=/m,
  );
  assert.match(trustedWorkerConfig, /^directory = "\.\/out"$/m);
  assert.match(
    trustedWorkerConfig,
    /^run_worker_first = \["\/mcp", "\/mcp\/\*"\]$/m,
  );
});

test("untrusted browser JavaScript receives no production MCP bridge", () => {
  assert.match(
    trustedWorkerProgram,
    /url\.pathname === "\/mcp" \|\| url\.pathname\.startsWith\("\/mcp\/"\)/,
  );
  assert.match(trustedWorkerProgram, /status: 503/);
  assert.match(trustedWorkerProgram, /"cache-control": "no-store"/);
  assert.doesNotMatch(trustedWorkerProgram, /tinyassets\.io\/mcp/);
  assert.doesNotMatch(
    trustedWorkerProgram,
    /\b(?:authorization|cookie|set-cookie|www-authenticate)\b/i,
  );
});
