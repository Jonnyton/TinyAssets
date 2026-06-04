#!/usr/bin/env node
/**
 * snapshot-mcp.mjs — pull live MCP data into src/lib/content/mcp-snapshot.json.
 *
 * Calls wiki/goals/universe on tinyassets.io/mcp via the official
 * @modelcontextprotocol/sdk client (StreamableHTTPClientTransport). Crawls
 * each promoted page to extract [[wiki-links]] and YAML-frontmatter sources
 * + tags so /graph can render real cross-page connections.
 *
 * Fail-soft: connection failures keep the existing snapshot. Atomic write
 * (temp + rename) avoids FUSE chunked-write truncation.
 *
 * Run:    npm run snapshot
 * Env:    MCP_URL, MCP_BEARER (optional)
 */

import { writeFileSync, readFileSync, existsSync, renameSync, unlinkSync } from 'node:fs';
import { dirname, resolve } from 'node:path';
import { fileURLToPath } from 'node:url';

const SCRIPT_DIR = dirname(fileURLToPath(import.meta.url));
const ROOT = resolve(SCRIPT_DIR, '..');
const SNAPSHOT_PATH = resolve(ROOT, 'src', 'lib', 'content', 'mcp-snapshot.json');
const MCP_URL = process.env.MCP_URL ?? 'https://tinyassets.io/mcp';
const BEARER = process.env.MCP_BEARER ?? '';
const PAGE_FETCH_CONCURRENCY = 4;

function log(msg) { console.log(`[snapshot] ${msg}`); }
function warn(msg) { console.warn(`[snapshot] WARN: ${msg}`); }

async function loadSdk() {
  try {
    const mod = await import('@modelcontextprotocol/sdk/client/index.js');
    const transportMod = await import('@modelcontextprotocol/sdk/client/streamableHttp.js');
    return { Client: mod.Client, StreamableHTTPClientTransport: transportMod.StreamableHTTPClientTransport };
  } catch (e) {
    warn(`SDK not installed (${e.message}). Run \`npm install\` first.`);
    return null;
  }
}

function parseToolResponse(result) {
  const textContent = result?.content?.find((c) => c?.type === 'text');
  if (!textContent?.text) return null;
  try {
    const parsed = JSON.parse(textContent.text);
    if (parsed && typeof parsed.result === 'string') {
      try { return JSON.parse(parsed.result); } catch { return parsed.result; }
    }
    return parsed;
  } catch {
    return textContent.text;
  }
}

function classifyPath(path) {
  if (!path) return 'other';
  const p = String(path);
  if (p.startsWith('drafts/')) return 'drafts';
  if (p.includes('/bugs/')) return 'bugs';
  if (p.includes('/concepts/')) return 'concepts';
  if (p.includes('/notes/')) return 'notes';
  if (p.includes('/plans/')) return 'plans';
  return 'other';
}

function buildBugId(path) {
  const m = String(path).match(/BUG-(\d+)/i);
  return m ? `BUG-${m[1]}` : path;
}

// Convert a wiki path like "pages/bugs/BUG-005-foo.md" → canonical node id.
function pathToNodeId(path) {
  if (!path) return null;
  const cat = classifyPath(path);
  if (cat === 'bugs') return `bug:${buildBugId(path)}`;
  if (cat === 'drafts') return `draft:${path}`;
  if (cat === 'concepts') return `concept:${path.split('/').pop()?.replace(/\.md$/, '') ?? path}`;
  if (cat === 'notes') return `note:${path.split('/').pop()?.replace(/\.md$/, '') ?? path}`;
  if (cat === 'plans') return `plan:${path.split('/').pop()?.replace(/\.md$/, '') ?? path}`;
  return null;
}

// Resolve a [[reference]] token — could be BUG-NNN, a slug, or an external page.
function resolveRef(ref, knownIds) {
  const r = String(ref).trim();
  // BUG-NNN
  const bugMatch = r.match(/^BUG-?(\d+)$/i);
  if (bugMatch) {
    const id = `bug:BUG-${bugMatch[1].padStart(3, '0')}`;
    return knownIds.has(id) ? id : null;
  }
  // Try matching a known concept/note/plan slug directly
  for (const t of ['concept', 'note', 'plan', 'draft']) {
    const id = `${t}:${r}`;
    if (knownIds.has(id)) return id;
  }
  // Slug normalization: lowercase, dashes
  const norm = r.toLowerCase().replace(/[\s_]+/g, '-');
  for (const t of ['concept', 'note', 'plan']) {
    const id = `${t}:${norm}`;
    if (knownIds.has(id)) return id;
  }
  return null;
}

// Pull simple list values from YAML frontmatter without a real parser.
function parseFrontmatterList(fm, key) {
  if (!fm) return [];
  // Try inline form: tags: [a, b, c]
  const inline = fm.match(new RegExp(`^${key}:\\s*\\[([^\\]]*)\\]`, 'm'));
  if (inline) {
    return inline[1].split(',').map((s) => s.trim().replace(/['"]/g, '')).filter(Boolean);
  }
  // Try block form: tags:\n  - a\n  - b
  const block = fm.match(new RegExp(`^${key}:\\s*\\n((?:\\s+-\\s+.+\\n?)+)`, 'm'));
  if (block) {
    return block[1].split('\n').map((line) => line.replace(/^\s+-\s+/, '').trim().replace(/['"]/g, '')).filter(Boolean);
  }
  return [];
}

function extractRefs(content) {
  if (!content) return { refs: [], tags: [], sources: [] };

  // [[wiki-link]] refs
  const wikiRefs = [...content.matchAll(/\[\[([^\]\n]+)\]\]/g)].map((m) => m[1]);

  // Bare BUG-NNN tokens that aren't already inside [[]]
  // Match BUG-001 through BUG-099 etc. case-insensitive
  const bareRefs = [...content.matchAll(/\bBUG-?\d{1,4}\b/gi)].map((m) => m[0]);

  // Frontmatter is between first two --- lines
  const fmMatch = content.match(/^---\n([\s\S]*?)\n---/);
  const fm = fmMatch ? fmMatch[1] : '';
  const body = fmMatch ? content.slice(fmMatch[0].length) : content;

  // Multiple frontmatter list fields commonly used to express relationships
  const tags = parseFrontmatterList(fm, 'tags');
  const sources = parseFrontmatterList(fm, 'sources');
  const fmRelated = [
    ...parseFrontmatterList(fm, 'related'),
    ...parseFrontmatterList(fm, 'related_bugs'),
    ...parseFrontmatterList(fm, 'related_pages'),
    ...parseFrontmatterList(fm, 'supersedes'),
    ...parseFrontmatterList(fm, 'supersedes_individual_bugs'),
    ...parseFrontmatterList(fm, 'blocks'),
    ...parseFrontmatterList(fm, 'blocked_by'),
    ...parseFrontmatterList(fm, 'fixes'),
    ...parseFrontmatterList(fm, 'see_also')
  ];

  // Body bare tokens are weaker signal; only count them when appearing outside frontmatter
  const bodyBareRefs = [...body.matchAll(/\bBUG-?\d{1,4}\b/gi)].map((m) => m[0]);

  return {
    refs: [...new Set([...wikiRefs, ...bodyBareRefs])],
    tags,
    sources: [...new Set([...sources, ...fmRelated])]
  };
}

async function main() {
  const sdk = await loadSdk();
  if (!sdk) { process.exit(0); return; }

  log(`fetching from ${MCP_URL} ...`);
  const transport = new sdk.StreamableHTTPClientTransport(new URL(MCP_URL), {
    requestInit: BEARER ? { headers: { Authorization: `Bearer ${BEARER}` } } : {}
  });
  const client = new sdk.Client(
    { name: 'workflow-site-snapshot', version: '0.2.0' },
    { capabilities: {} }
  );

  try {
    await Promise.race([
      client.connect(transport),
      new Promise((_, reject) => setTimeout(() => reject(new Error('connect timeout')), 30_000))
    ]);
    log('connected.');

    async function tool(name, args) {
      try {
        const r = await client.callTool({ name, arguments: args });
        return parseToolResponse(r);
      } catch (e) {
        warn(`tool ${name}(${JSON.stringify(args)}) failed: ${e.message}`);
        return null;
      }
    }

    log('listing wiki / goals / universes ...');
    const [wikiList, goalsList, universesList] = await Promise.all([
      tool('wiki', { action: 'list' }),
      tool('goals', { action: 'list' }),
      tool('universe', { action: 'list' })
    ]);

    // Shape data
    const goals = (goalsList?.goals ?? []).map((g) => ({
      id: g.goal_id ?? g.id,
      name: g.name ?? '',
      summary: g.description ?? '',
      tags: typeof g.tags === 'string' ? g.tags.split(',').map((t) => t.trim()).filter(Boolean) : (g.tags ?? []),
      author: g.author ?? 'anonymous',
      visibility: g.visibility ?? 'public'
    }));

    const universes = (universesList?.universes ?? []).map((u) => ({
      id: u.id,
      phase: u.phase_human ?? u.phase ?? 'unknown',
      word_count: u.word_count ?? 0,
      last_activity_at: u.last_activity_at ?? null,
      accept_rate: u.accept_rate ?? null
    }));

    const wiki = { bugs: [], concepts: [], notes: [], plans: [], drafts: [], other: [] };
    for (const p of wikiList?.promoted ?? []) {
      const cat = classifyPath(p.path);
      const slug = p.path ?? '';
      const title = p.title ?? slug;
      if (cat === 'bugs') {
        // Pad to BUG-NNN three-digit form for stable IDs
        const m = slug.match(/BUG-?(\d+)/i);
        const padded = m ? `BUG-${m[1].padStart(3, '0')}` : buildBugId(slug);
        wiki.bugs.push({ id: padded, title, slug });
      } else if (cat === 'drafts') {
        wiki.other.push({ slug, title });
      } else if (wiki[cat]) {
        wiki[cat].push({ slug, title });
      }
    }
    for (const p of wikiList?.drafts ?? []) {
      wiki.drafts.push({ slug: p.path ?? '', title: p.title ?? p.path });
    }

    // Dedup by canonical id/slug — live MCP sometimes returns case variants
    // (e.g. BUG-003-... and bug-003-...) that pad to the same canonical id.
    // Without this dedup, Svelte's keyed {#each} blocks throw each_key_duplicate.
    function dedupBy(arr, keyFn) {
      const seen = new Set();
      const out = [];
      for (const item of arr) {
        const k = keyFn(item);
        if (seen.has(k)) continue;
        seen.add(k);
        out.push(item);
      }
      return out;
    }
    wiki.bugs = dedupBy(wiki.bugs, (b) => b.id);
    wiki.concepts = dedupBy(wiki.concepts, (c) => c.slug);
    wiki.notes = dedupBy(wiki.notes, (n) => n.slug);
    wiki.plans = dedupBy(wiki.plans, (pl) => pl.slug);
    wiki.drafts = dedupBy(wiki.drafts, (d) => d.slug);

    // Build the set of known node IDs for ref resolution.
    const knownIds = new Set();
    for (const b of wiki.bugs) knownIds.add(`bug:${b.id}`);
    for (const c of wiki.concepts) knownIds.add(`concept:${c.slug.split('/').pop()?.replace(/\.md$/, '') ?? c.slug}`);
    for (const n of wiki.notes) knownIds.add(`note:${n.slug.split('/').pop()?.replace(/\.md$/, '') ?? n.slug}`);
    for (const pl of wiki.plans) knownIds.add(`plan:${pl.slug.split('/').pop()?.replace(/\.md$/, '') ?? pl.slug}`);
    for (const d of wiki.drafts) knownIds.add(`draft:${d.slug}`);
    for (const g of goals) knownIds.add(`goal:${g.id}`);
    for (const u of universes) knownIds.add(`universe:${u.id}`);

    // Crawl page bodies for references + tags. Concurrency-limited.
    log(`crawling ${(wikiList?.promoted ?? []).length} page bodies (concurrency=${PAGE_FETCH_CONCURRENCY}) ...`);
    const pageMeta = {}; // path → { refs: [], tags: [], sources: [] }
    const queue = [...(wikiList?.promoted ?? [])];
    let inFlight = 0, done = 0;
    await new Promise((doneResolve) => {
      function pump() {
        if (queue.length === 0 && inFlight === 0) { doneResolve(); return; }
        while (inFlight < PAGE_FETCH_CONCURRENCY && queue.length > 0) {
          const page = queue.shift();
          inFlight++;
          tool('wiki', { action: 'read', page: page.path.replace(/\.md$/, '') })
            .then((body) => {
              if (body?.content) {
                pageMeta[page.path] = extractRefs(body.content);
              }
            })
            .catch(() => {})
            .finally(() => {
              inFlight--;
              done++;
              if (done % 10 === 0) log(`  ${done} pages crawled`);
              pump();
            });
        }
      }
      pump();
    });
    log(`crawled ${done} pages. Resolving references ...`);

    // Build the edge list. Each edge: { from: nodeId, to: nodeId, kind: 'ref' | 'source' }.
    const edges = [];
    const seenEdges = new Set();
    function addEdge(from, to, kind) {
      if (!from || !to || from === to) return;
      const key = `${from}|${to}|${kind}`;
      if (seenEdges.has(key)) return;
      seenEdges.add(key);
      edges.push({ from, to, kind });
    }
    for (const [path, meta] of Object.entries(pageMeta)) {
      const fromId = pathToNodeId(path);
      if (!fromId) continue;
      for (const r of meta.refs) {
        const toId = resolveRef(r, knownIds);
        if (toId) addEdge(fromId, toId, 'ref');
      }
      for (const s of meta.sources) {
        // Sources may be paths like "pages/bugs/BUG-001" or freeform ranges.
        // Try direct path → id first.
        const toId = pathToNodeId(s) ?? resolveRef(s, knownIds);
        if (toId) addEdge(fromId, toId, 'source');
      }
    }

    // Tags per node — surfaces clustering.
    const tags = {};
    for (const [path, meta] of Object.entries(pageMeta)) {
      const id = pathToNodeId(path);
      if (id && meta.tags?.length) tags[id] = meta.tags;
    }
    for (const g of goals) {
      if (g.tags?.length) tags[`goal:${g.id}`] = g.tags;
    }

    const promoted = wiki.bugs.length + wiki.concepts.length + wiki.notes.length + wiki.plans.length + wiki.other.length;
    if (promoted === 0 && goals.length === 0 && universes.length === 0) {
      throw new Error('all responses empty — aborting to avoid clobbering existing snapshot');
    }

    const snapshot = {
      fetched_at: new Date().toISOString(),
      source: 'tinyassets.io/mcp',
      stats: {
        wiki_promoted: promoted,
        wiki_drafts: wiki.drafts.length,
        goals: goals.length,
        universes: universes.length,
        edges: edges.length
      },
      goals,
      universes,
      wiki: { bugs: wiki.bugs, concepts: wiki.concepts, notes: wiki.notes, plans: wiki.plans, drafts: wiki.drafts },
      edges,
      tags
    };

    // Atomic write: temp file + rename, immune to FUSE chunked-write truncation.
    const tmpPath = SNAPSHOT_PATH + '.tmp';
    try { unlinkSync(tmpPath); } catch {}
    writeFileSync(tmpPath, JSON.stringify(snapshot, null, 2) + '\n');
    renameSync(tmpPath, SNAPSHOT_PATH);
    log(`wrote ${SNAPSHOT_PATH} (${promoted} promoted, ${wiki.drafts.length} drafts, ${goals.length} goals, ${universes.length} universes, ${edges.length} edges)`);
  } catch (err) {
    warn(`refresh failed: ${err?.message ?? err}`);
    if (existsSync(SNAPSHOT_PATH)) {
      try {
        const stat = JSON.parse(readFileSync(SNAPSHOT_PATH, 'utf-8'));
        warn(`keeping existing snapshot from ${stat.fetched_at}`);
      } catch {}
    }
  } finally {
    try { await client.close(); } catch {}
  }
  process.exit(0);
}

main().catch((e) => {
  warn(`unhandled: ${e?.message ?? e}`);
  process.exit(0);
});
