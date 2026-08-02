import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { dirname, resolve } from 'node:path';
import test from 'node:test';
import { fileURLToPath } from 'node:url';

const here = dirname(fileURLToPath(import.meta.url));
const snapshotPaths = [
  resolve(here, '../src/lib/content/mcp-snapshot.json'),
  resolve(here, '../../site-react/lib/mcp-snapshot.json')
];
const repoSnapshotPath = resolve(
  here,
  '../src/lib/content/repo-snapshot.json'
);
const retiredGoalIds = new Set(['4ff5862cc26d', 'f10caea2e437']);

for (const snapshotPath of snapshotPaths) {
  test(`${snapshotPath} excludes retired TinyAssets automation goals`, () => {
    const snapshot = JSON.parse(readFileSync(snapshotPath, 'utf8'));
    const presentGoalIds = new Set(snapshot.goals.map((goal) => goal.id));

    for (const goalId of retiredGoalIds) {
      assert.equal(presentGoalIds.has(goalId), false);
      assert.equal(Object.hasOwn(snapshot.tags, `goal:${goalId}`), false);
    }

    assert.equal(snapshot.stats.goals, snapshot.goals.length);
    assert.doesNotMatch(
      JSON.stringify(snapshot),
      /patch-loop|community-driven live-state loop|run automatically after wiki action=file_bug/i
    );
  });
}

test('repository snapshot contains no unsourced or retired graph data', () => {
  const snapshot = JSON.parse(readFileSync(repoSnapshotPath, 'utf8'));
  assert.deepEqual(snapshot.areas, []);
  assert.deepEqual(snapshot.workflow_branches, []);
  assert.deepEqual(snapshot.routes, []);
  assert.deepEqual(snapshot.edges, []);
  assert.doesNotMatch(
    JSON.stringify(snapshot),
    /4ff5862cc26d|f10caea2e437|patch-loop|community-driven live-state loop/i
  );
});
