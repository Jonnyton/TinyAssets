import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { resolve } from 'node:path';
import test from 'node:test';

const snapshotSource = readFileSync(
  resolve('scripts', 'snapshot-mcp.mjs'),
  'utf8'
);
const deployWorkflow = readFileSync(
  resolve('..', '..', '.github', 'workflows', 'deploy-site.yml'),
  'utf8'
);
const siteReadme = readFileSync(resolve('README.md'), 'utf8');

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

test('required snapshots fail when the MCP SDK is unavailable', () => {
  assert.match(
    snapshotSource,
    /if\s*\(!sdk\)\s*\{\s*process\.exit\(process\.env\.SNAPSHOT_REQUIRED\s*===\s*['"]1['"]\s*\?\s*1\s*:\s*0\)/s
  );
});

test('page crawling rejects truncated bodies before extracting references', () => {
  assert.match(
    snapshotSource,
    /if\s*\(body\?\.truncated\s*!==\s*false\)\s*\{\s*throw new Error\([^)]*truncated[^)]*\)/s
  );
});

test('full snapshot replacement requires a complete all-scope inventory', () => {
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
});
