import assert from 'node:assert/strict';
import { execFileSync } from 'node:child_process';
import {
  copyFileSync,
  mkdirSync,
  mkdtempSync,
  readFileSync,
  rmSync,
  writeFileSync
} from 'node:fs';
import { tmpdir } from 'node:os';
import { dirname, resolve } from 'node:path';
import test from 'node:test';
import { fileURLToPath } from 'node:url';

const here = dirname(fileURLToPath(import.meta.url));
const sourceScript = resolve(here, 'snapshot-repo.mjs');

function git(root, args) {
  return execFileSync('git', args, {
    cwd: root,
    encoding: 'utf8',
    stdio: ['ignore', 'pipe', 'pipe']
  });
}

test('regeneration drops unsourced graph data from the previous snapshot', (t) => {
  const root = mkdtempSync(resolve(tmpdir(), 'tinyassets-repo-snapshot-'));
  t.after(() => rmSync(root, { recursive: true, force: true }));

  const scriptDir = resolve(root, 'WebSite', 'site', 'scripts');
  const contentDir = resolve(root, 'WebSite', 'site', 'src', 'lib', 'content');
  const scriptPath = resolve(scriptDir, 'snapshot-repo.mjs');
  const snapshotPath = resolve(contentDir, 'repo-snapshot.json');
  mkdirSync(scriptDir, { recursive: true });
  mkdirSync(contentDir, { recursive: true });
  copyFileSync(sourceScript, scriptPath);

  git(root, ['init', '--initial-branch=main']);
  git(root, ['config', 'user.email', 'snapshot-test@tinyassets.invalid']);
  git(root, ['config', 'user.name', 'Snapshot Test']);
  writeFileSync(resolve(root, 'README.md'), '# fixture\n', 'utf8');
  git(root, ['add', 'README.md']);
  git(root, ['commit', '-m', 'fixture']);
  git(root, ['remote', 'add', 'origin', 'https://example.invalid/TinyAssets.git']);
  git(root, ['branch', 'provider/private-work']);
  git(root, ['update-ref', 'refs/remotes/origin/main', 'HEAD']);
  git(root, ['update-ref', 'refs/remotes/origin/provider/private-work', 'HEAD']);

  const retired = { id: 'area:patch-loop', label: 'Patch loop' };
  writeFileSync(
    snapshotPath,
    `${JSON.stringify({
      fetched_at: '2026-05-01T00:00:00Z',
      patch_loop_feed: [{ id: 'loop:cheat' }],
      stats: { loop_runs: 186 },
      repo: { default_branch: 'cheat-loop', open_issues: 9 },
      areas: [retired],
      workflow_branches: [{ id: 'branch:retired-loop' }],
      routes: [{ id: 'route:retired-loop' }],
      edges: [{ from: retired.id, to: 'branch:retired-loop' }]
    }, null, 2)}\n`,
    'utf8'
  );

  execFileSync(process.execPath, [scriptPath], {
    cwd: root,
    encoding: 'utf8',
    stdio: ['ignore', 'pipe', 'pipe']
  });

  const regenerated = JSON.parse(readFileSync(snapshotPath, 'utf8'));
  assert.deepEqual(
    regenerated.branches.map((branch) => branch.name),
    ['origin/main']
  );
  assert.equal(regenerated.repo.current_branch, 'origin/main');
  assert.equal(regenerated.repo.head, regenerated.branches[0].commit);
  assert.equal(regenerated.repo.main, regenerated.branches[0].commit);
  assert.equal(
    regenerated.repo.dirty_note,
    'Generated from the canonical origin/main reference.'
  );
  assert.equal(Object.hasOwn(regenerated, 'patch_loop_feed'), false);
  assert.equal(Object.hasOwn(regenerated, 'stats'), false);
  assert.equal(Object.hasOwn(regenerated.repo, 'default_branch'), false);
  assert.equal(Object.hasOwn(regenerated.repo, 'open_issues'), false);
  assert.deepEqual(regenerated.areas, []);
  assert.deepEqual(regenerated.workflow_branches, []);
  assert.deepEqual(regenerated.routes, []);
  assert.deepEqual(regenerated.edges, []);
});

test('regeneration fails when the canonical origin/main reference is absent', (t) => {
  const root = mkdtempSync(resolve(tmpdir(), 'tinyassets-repo-snapshot-'));
  t.after(() => rmSync(root, { recursive: true, force: true }));

  const scriptDir = resolve(root, 'WebSite', 'site', 'scripts');
  const contentDir = resolve(root, 'WebSite', 'site', 'src', 'lib', 'content');
  const scriptPath = resolve(scriptDir, 'snapshot-repo.mjs');
  mkdirSync(scriptDir, { recursive: true });
  mkdirSync(contentDir, { recursive: true });
  copyFileSync(sourceScript, scriptPath);

  git(root, ['init', '--initial-branch=main']);
  git(root, ['config', 'user.email', 'snapshot-test@tinyassets.invalid']);
  git(root, ['config', 'user.name', 'Snapshot Test']);
  writeFileSync(resolve(root, 'README.md'), '# fixture\n', 'utf8');
  git(root, ['add', 'README.md']);
  git(root, ['commit', '-m', 'fixture']);
  git(root, ['remote', 'add', 'origin', 'https://example.invalid/TinyAssets.git']);

  assert.throws(
    () =>
      execFileSync(process.execPath, [scriptPath], {
        cwd: root,
        encoding: 'utf8',
        stdio: ['ignore', 'pipe', 'pipe']
      }),
    (error) => {
      assert.match(
        String(error.stderr),
        /refs\/remotes\/origin\/main not found — fetch before generating/
      );
      return true;
    }
  );
});
