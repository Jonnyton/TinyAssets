import { execFileSync } from 'node:child_process';
import { writeFileSync } from 'node:fs';
import { dirname, resolve } from 'node:path';
import { fileURLToPath } from 'node:url';

const here = dirname(fileURLToPath(import.meta.url));
const repoRoot = resolve(here, '../../..');
const outFile = resolve(here, '../src/lib/content/repo-snapshot.json');

function git(args) {
  return execFileSync('git', args, {
    cwd: repoRoot,
    encoding: 'utf8',
    stdio: ['ignore', 'pipe', 'pipe']
  }).trim();
}

function refRows() {
  const raw = git([
    'for-each-ref',
    '--format=%(refname:short)|%(objectname:short)|%(committerdate:iso8601-strict)|%(subject)',
    'refs/heads',
    'refs/remotes/origin'
  ]);
  return raw
    .split(/\r?\n/)
    .filter(Boolean)
    .map((line) => {
      const [name, commit, date, ...subjectParts] = line.split('|');
      return {
        id: `git:${name}`,
        name,
        kind: name.startsWith('origin/') || name === 'origin' ? 'remote' : 'local',
        commit,
        date,
        subject: subjectParts.join('|')
      };
    })
    .filter((branch) => branch.name === 'origin/main');
}

const branches = refRows();
if (branches.length === 0) {
  throw new Error(
    'refs/remotes/origin/main not found — fetch before generating the repo snapshot'
  );
}
const remote = git(['remote', 'get-url', 'origin']);
const head = branches[0].commit;
const main = head;

const snapshot = {
  fetched_at: new Date().toISOString(),
  source: 'canonical origin/main git reference',
  repo: {
    id: 'repo:TinyAssets',
    name: 'TinyAssets',
    owner: 'Jonnyton',
    remote_url: remote,
    current_branch: 'origin/main',
    head,
    main,
    dirty_note: 'Generated from the canonical origin/main reference.'
  },
  branches,
  areas: [],
  workflow_branches: [],
  routes: [],
  edges: []
};

writeFileSync(outFile, `${JSON.stringify(snapshot, null, 2)}\n`, 'utf8');
console.log(`Wrote ${outFile}`);
