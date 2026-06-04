import { execFileSync } from 'node:child_process';
import { existsSync, readFileSync, writeFileSync } from 'node:fs';
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
    .filter((branch) => branch.name !== 'origin');
}

const branches = refRows();
const currentBranch = git(['branch', '--show-current']) || 'detached';
const remote = git(['remote', 'get-url', 'origin']);
const head = git(['rev-parse', '--short', 'HEAD']);
const main = branches.find((branch) => branch.name === 'main')?.commit ?? '';
const dirty = git(['status', '--short']).split(/\r?\n/).filter(Boolean).length;

const previous = existsSync(outFile) ? JSON.parse(readFileSync(outFile, 'utf8')) : {};

const snapshot = {
  ...previous,
  fetched_at: new Date().toISOString(),
  source: 'local git checkout + GitHub remote',
  repo: {
    ...(previous.repo ?? {}),
    id: 'repo:Workflow',
    name: 'Workflow',
    owner: 'Jonnyton',
    remote_url: remote,
    current_branch: currentBranch,
    head,
    main,
    dirty_note:
      dirty === 0
        ? 'Working tree clean when repo snapshot was generated.'
        : `Working tree had ${dirty} changed paths when repo snapshot was generated.`
  },
  branches,
  areas: previous.areas ?? [],
  workflow_branches: previous.workflow_branches ?? [],
  routes: previous.routes ?? [],
  edges: previous.edges ?? []
};

writeFileSync(outFile, `${JSON.stringify(snapshot, null, 2)}\n`, 'utf8');
console.log(`Wrote ${outFile}`);
