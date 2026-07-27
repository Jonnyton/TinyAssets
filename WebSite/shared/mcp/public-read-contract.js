const PAGE_INVENTORY_SINCE = "1970-01-01T00:00:00Z";
const PAGE_INVENTORY_LIMIT = 100;

/**
 * @param {string} [changedSince]
 * @returns {{ name: 'read_page', args: { changed_since: string, max_results: number } }}
 */
export function pageInventoryCall(changedSince = PAGE_INVENTORY_SINCE) {
  return {
    name: "read_page",
    args: {
      changed_since: changedSince,
      max_results: PAGE_INVENTORY_LIMIT,
    },
  };
}

/**
 * @param {'goals' | 'graphs' | 'runs'} target
 * @param {number} limit
 * @returns {{ name: 'read_graph', args: { target: 'goals' | 'graphs' | 'runs', limit: number } }}
 */
export function publicGraphCall(target, limit) {
  return {
    name: "read_graph",
    args: { target, limit },
  };
}

/**
 * @param {string} goalId
 * @returns {{ name: 'read_graph', args: { target: 'goal', goal_id: string } }}
 */
export function publicGoalCall(goalId) {
  return {
    name: "read_graph",
    args: { target: "goal", goal_id: goalId },
  };
}

/**
 * @param {string} runId
 * @returns {{ name: 'read_graph', args: { target: 'run', run_id: string } }}
 */
export function publicRunCall(runId) {
  return {
    name: "read_graph",
    args: { target: "run", run_id: runId },
  };
}

/**
 * @param {string} page
 * @returns {{ name: 'read_page', args: { page: string } }}
 */
export function publicPageCall(page) {
  return {
    name: "read_page",
    args: { page: page.replace(/\.md$/, "") },
  };
}

/**
 * @param {any} payload
 * @param {string} source
 * @returns {Record<string, any>}
 */
export function requireObjectResult(payload, source) {
  if (!payload || typeof payload !== "object" || Array.isArray(payload)) {
    throw new Error(`${source} returned no structured result`);
  }
  if (payload.error) {
    throw new Error(`${source} failed: ${String(payload.error)}`);
  }
  return payload;
}

/**
 * @param {any} payload
 * @param {string} key
 * @param {string} source
 * @returns {any[]}
 */
export function requireCollection(payload, key, source) {
  const result = requireObjectResult(payload, source);
  if (!Array.isArray(result[key])) {
    throw new Error(`${source} did not return a ${key} array`);
  }
  return result[key];
}

/**
 * @param {any} payload
 * @param {string} source
 * @returns {Record<string, any> & { content: string }}
 */
export function requirePageBody(payload, source) {
  const result = requireObjectResult(payload, source);
  if (typeof result.content !== "string") {
    throw new Error(`${source} did not return a content string`);
  }
  return /** @type {Record<string, any> & { content: string }} */ (result);
}

/**
 * @param {number} expected
 * @param {number} attempted
 * @param {number} failed
 */
export function assertCompleteCrawl(expected, attempted, failed) {
  if (attempted !== expected) {
    throw new Error(`snapshot page crawl attempted ${attempted} of ${expected} pages`);
  }
  if (failed > 0) {
    throw new Error(
      `snapshot page crawl incomplete: ${failed} page read${failed === 1 ? "" : "s"} failed`,
    );
  }
}

/**
 * @param {any} payload
 * @returns {{ promoted: any[], drafts: any[] }}
 */
export function splitPageInventory(payload) {
  const result = requireObjectResult(payload, "read_page inventory");
  if (!Array.isArray(result.results)) {
    throw new Error("read_page inventory did not return a results array");
  }
  /** @type {Array<Record<string, any>>} */
  const results = result.results;
  const count = Number(result.count);
  const total = Number(result.total_matches);
  const truncated = Number(result.truncated_count);
  if (
    !Number.isInteger(count) ||
    !Number.isInteger(total) ||
    !Number.isInteger(truncated) ||
    count < 0 ||
    total < 0 ||
    truncated < 0 ||
    count !== results.length ||
    total !== count + truncated
  ) {
    throw new Error(
      "read_page inventory returned inconsistent completeness metadata",
    );
  }
  const scope =
    typeof result.scope === "string" && result.scope.trim()
      ? result.scope.trim()
      : "unknown";
  const scopeNote =
    typeof result.scope_note === "string" ? result.scope_note.trim() : "";
  if (scope !== "all" || scopeNote) {
    throw new Error(
      `read_page inventory is incomplete (scope: ${scope})`,
    );
  }
  if (truncated > 0) {
    throw new Error(
      `read_page inventory truncated ${truncated} of ${total} pages`,
    );
  }

  return {
    promoted: results.filter((page) => !page.is_draft),
    drafts: results.filter((page) => Boolean(page.is_draft)),
  };
}
