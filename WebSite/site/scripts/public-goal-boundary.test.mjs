import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { dirname, resolve } from "node:path";
import test from "node:test";
import { fileURLToPath } from "node:url";

const here = dirname(fileURLToPath(import.meta.url));
const clients = [
  resolve(here, "../src/lib/mcp/live.ts"),
  resolve(here, "../../site-react/lib/live.ts"),
];

for (const clientPath of clients) {
  const source = readFileSync(clientPath, "utf8");

  test(`${clientPath} does not expose an unenforced public-goal network reader`, () => {
    assert.doesNotMatch(source, /\bpublicGoalCall\b/);
    assert.doesNotMatch(source, /\bfetchPublicGoals?\b/);
    assert.doesNotMatch(
      source,
      /publicGraphCall\(\s*["']goals["']/,
      "read_graph goals is not a server-enforced public-only projection",
    );
  });

  test(`${clientPath} preserves honest local goal data and safe graph reads`, () => {
    assert.match(source, /goals:\s*\[\]/);
    assert.match(source, /goalCount:\s*null/);
    assert.match(source, /goals:\s*baked\.goals\s*\?\?\s*\[\]/);
    assert.match(source, /publicGraphCall\(\s*["']graphs["']/);
    assert.doesNotMatch(
      source,
      /publicGraphCall\(\s*["']runs?["']/,
      "read_graph runs is not a server-enforced public-only projection",
    );
    assert.doesNotMatch(source, /\bfetchPublicRuns?\b/);
    assert.doesNotMatch(source, /read_graph runs?\b/i);
  });

  test(`${clientPath} does not derive vitals from the unsafe run projection`, () => {
    assert.doesNotMatch(source, /lastSignalSource\?:\s*["']run["']/);
    assert.doesNotMatch(source, /lastSignalSource\s*=\s*["']run["']/);
    assert.doesNotMatch(source, /\bactiveRun\b/);
  });

  test(`${clientPath} does not download the operator get_status payload`, () => {
    assert.doesNotMatch(source, /callTool\(\s*["']get_status["']/);
    assert.doesNotMatch(source, /\brequireObjectResult\b/);
  });
}

test("React workflow activity uses only visibility-filtered universe discovery", () => {
  const source = readFileSync(resolve(here, "../../site-react/lib/live.ts"), "utf8");
  assert.match(source, /publicGraphCall\(\s*["']graphs["']/);
  assert.doesNotMatch(source, /\bfetchWorkflowActivity\b|\bWorkflowActivity\b|\bWorkflowRun\b/);
  assert.doesNotMatch(source, /publicGraphCall\(\s*["'](?:run|runs|goal|goals)["']/);
});
