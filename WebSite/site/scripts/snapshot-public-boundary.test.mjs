import assert from 'node:assert/strict';
import { existsSync, readFileSync } from 'node:fs';
import { resolve } from 'node:path';
import test from 'node:test';

const snapshotSource = readFileSync(
  resolve('scripts', 'snapshot-mcp.mjs'),
  'utf8'
);
const publicContractSource = readFileSync(
  resolve('..', 'shared', 'mcp', 'public-read-contract.js'),
  'utf8'
);
const deployWorkflow = readFileSync(
  resolve('..', '..', '.github', 'workflows', 'deploy-site.yml'),
  'utf8'
);
const siteReadme = readFileSync(resolve('README.md'), 'utf8');
const repoRoot = resolve('..', '..');
const snapshotPaths = [
  resolve('src', 'lib', 'content', 'mcp-snapshot.json'),
  resolve('..', 'site-react', 'lib', 'mcp-snapshot.json')
];

test('public snapshots refuse authenticated caller context', () => {
  assert.match(
    snapshotSource,
    /if\s*\(process\.env\.MCP_BEARER\)\s*\{[^}]*anonymous[^}]*process\.exit\(1\)/s
  );
  assert.doesNotMatch(deployWorkflow, /^\s*MCP_BEARER:/m);
  assert.doesNotMatch(snapshotSource, /Authorization:\s*`Bearer/);
  assert.match(siteReadme, /snapshot refreshes run anonymously/i);
  assert.doesNotMatch(siteReadme, /(?:set|provide)[^.\n]*MCP_BEARER/i);
  assert.match(snapshotSource, /assertAnonymousSnapshotUrl\(\s*MCP_URL\s*\)/);
  assert.match(
    snapshotSource,
    /assertAnonymousSnapshotUrl\(\s*MCP_URL\s*\)[\s\S]{0,500}log\(`fetching from \$\{MCP_URL\}/,
    'URL credentials must be rejected before the URL is logged'
  );
});

test('public snapshots never read the unsafe goal projection', () => {
  assert.doesNotMatch(snapshotSource, /publicGraphCall\(\s*['"]goals['"]/);
  assert.doesNotMatch(snapshotSource, /read_graph goals/);
});

test('checked-in Goal rows require independent public-publication provenance', () => {
  const snapshots = snapshotPaths.map((path) =>
    JSON.parse(readFileSync(path, 'utf8'))
  );
  assert.deepEqual(snapshots[0], snapshots[1], 'public snapshot mirrors must match');

  for (const snapshot of snapshots) {
    const serialized = JSON.stringify(snapshot);
    const goalIdentities = new Set([
      ...snapshot.goals.map((goal) => goal.id),
      ...[...serialized.matchAll(/"goal:([a-f0-9]{12})"/g)].map(
        (match) => match[1]
      )
    ]);

    assert.equal(snapshot.stats.goals, snapshot.goals.length);
    assert.deepEqual(
      [...goalIdentities],
      ['dd187997039b'],
      'only independently proven Goal identity may appear anywhere in the public artifact'
    );
    assert.doesNotMatch(
      serialized,
      /62f977e7ff0c|454b6e72348b|4ce84ff648d4/,
      'known orphaned Goal identities must not survive in public metadata'
    );
    for (const goal of snapshot.goals) {
      assert.equal(goal.visibility, 'public');
      assert.ok(
        Array.isArray(goal.publication_provenance) &&
          goal.publication_provenance.length > 0,
        `${goal.id} must name independent publication evidence`
      );
      for (const relativePath of goal.publication_provenance) {
        const evidencePath = resolve(repoRoot, relativePath);
        assert.ok(existsSync(evidencePath), `${relativePath} must exist`);
        const evidence = readFileSync(evidencePath, 'utf8');
        assert.match(evidence, new RegExp(goal.id));
        assert.match(evidence, /visibility:\s*public|public-source goal/i);
      }
    }
  }
});

test('retired change-loop drafts and their metadata stay out of public snapshots', () => {
  for (const path of snapshotPaths) {
    const snapshot = JSON.parse(readFileSync(path, 'utf8'));
    const serialized = JSON.stringify(snapshot);

    assert.equal(snapshot.stats.wiki_drafts, snapshot.wiki.drafts.length);
    assert.deepEqual(snapshot.universes, []);
    assert.deepEqual(snapshot.wiki, {
      bugs: [],
      concepts: [],
      notes: [],
      plans: [],
      drafts: [],
    });
    assert.deepEqual(snapshot.edges, []);
    assert.deepEqual(Object.keys(snapshot.tags), ["goal:dd187997039b"]);
    assert.equal(snapshot.stats.wiki_promoted, 0);
    assert.equal(snapshot.stats.universes, 0);
    assert.equal(snapshot.stats.edges, 0);
    assert.doesNotMatch(
      serialized,
      /Community Change Loop v1 (?:Builder Notes|Piece Map)|community-change-loop-v1-(?:builder-notes|piece-map)/i
    );
  }
});

test('required snapshots fail when the MCP SDK is unavailable', () => {
  assert.match(
    snapshotSource,
    /if\s*\(!sdk\)\s*\{\s*process\.exit\(process\.env\.SNAPSHOT_REQUIRED\s*===\s*['"]1['"]\s*\?\s*1\s*:\s*0\)/s
  );
});

test('page crawling rejects truncated bodies before extracting references', () => {
  assert.match(
    snapshotSource,
    /requirePageBody\(\s*parseToolResponse\(r\)\s*,\s*['"]read_page page body['"]\s*,\s*page\.path\s*\)/
  );
  assert.match(snapshotSource, /\bassertBodyMatchesSourceHash\(body\)/);
  assert.match(snapshotSource, /createHash\(['"]sha256['"]\)/);
  assert.match(snapshotSource, /content did not match its source-read proof/);
});

test('full snapshot replacement stays disabled without audience-safe publication evidence', () => {
  assert.match(snapshotSource, /\bsplitFullPageInventory\s*\(/);
  assert.match(
    snapshotSource,
    /publicPageCall\(\s*page\.path\s*,\s*wikiList\.validatedPaths\s*\)/
  );
  assert.doesNotMatch(snapshotSource, /\bsplitPageInventory\s*\(/);
  assert.match(
    snapshotSource,
    /requireCompleteCollection\([\s\S]{0,240}['"]universes['"][\s\S]{0,240}100\s*,?\s*\)/
  );
  assert.match(
    publicContractSource,
    /Full public snapshot replacement requires independent audience-safe publication evidence/
  );
});
