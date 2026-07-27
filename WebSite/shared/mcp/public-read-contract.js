const PAGE_INVENTORY_SINCE = "1970-01-01T00:00:00Z";
const PAGE_INVENTORY_LIMIT = 100;
const validatedPathSets = new WeakMap();
const CREDENTIAL_PARAMETER_NAMES = new Set([
  "accesstoken",
  "refreshtoken",
  "idtoken",
  "token",
  "apikey",
  "key",
  "auth",
  "authorization",
  "signature",
  "sig",
  "bearer",
  "credential",
  "credentials",
  "password",
  "passwd",
  "secret",
  "clientsecret",
  "xamzcredential",
  "xamzsignature",
  "xamzsecuritytoken",
  "xgoogcredential",
  "xgoogsignature",
  "jwt",
  "session",
  "sessionid",
  "oauthcode",
  "authorizationcode",
  "privatekey",
]);

/** @param {string} value */
function normalizedParameterName(value) {
  return value.toLowerCase().replace(/[^a-z0-9]/g, "");
}

/** @param {string} value */
function isCredentialParameterName(value) {
  const normalized = normalizedParameterName(value);
  return (
    CREDENTIAL_PARAMETER_NAMES.has(normalized) ||
    /(?:token|secret|password|passwd|credential|signature)$/.test(normalized)
  );
}

/**
 * @param {URLSearchParams} params
 * @returns {boolean}
 */
function containsCredentialMaterial(params) {
  for (const [name, value] of params) {
    if (isCredentialParameterName(name)) {
      return true;
    }
    if (/^\s*bearer(?:\s|%20)+\S/i.test(value)) {
      return true;
    }
  }
  return false;
}

/** @param {string} page */
function canonicalPagePath(page) {
  if (typeof page !== "string" || !page.trim()) {
    throw new Error("public page path must be a non-empty string");
  }
  return page.trim().replace(/\.md$/, "");
}

/**
 * @param {Record<string, unknown>} args
 * @param {string[]} expected
 */
function hasExactKeys(args, expected) {
  if (!args || typeof args !== "object" || Array.isArray(args)) return false;
  const actual = Object.keys(args).sort();
  const expectedSorted = [...expected].sort();
  return actual.length === expectedSorted.length &&
    actual.every((key, index) => key === expectedSorted[index]);
}

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
 * @param {string} value
 * @returns {string}
 */
export function assertAnonymousSnapshotUrl(value) {
  const parsed = new URL(value);
  const fragment = parsed.hash.slice(1);
  let decodedFragment = fragment;
  try {
    decodedFragment = decodeURIComponent(fragment);
  } catch {
    // URLSearchParams still handles any valid pairs below; malformed escaped
    // fragments are not treated as credential-free by decoding alone.
  }
  const fragmentQueryIndex = fragment.indexOf("?");
  const fragmentParams = [
    new URLSearchParams(fragment),
    ...(fragmentQueryIndex >= 0
      ? [new URLSearchParams(fragment.slice(fragmentQueryIndex + 1))]
      : []),
  ];
  if (
    parsed.username ||
    parsed.password ||
    containsCredentialMaterial(parsed.searchParams) ||
    fragmentParams.some(containsCredentialMaterial) ||
    /^\s*bearer(?:\s|:)+\S/i.test(decodedFragment)
  ) {
    throw new Error(
      "Public snapshots must run anonymously; MCP URL credentials are forbidden",
    );
  }
  return value;
}

/**
 * @param {'graphs'} target
 * @param {number} limit
 * @returns {{ name: 'read_graph', args: { target: 'graphs', limit: number } }}
 */
export function publicGraphCall(target, limit) {
  if (target !== "graphs") {
    throw new Error("The public read contract only supports target=graphs");
  }
  if (!Number.isInteger(limit) || limit < 1 || limit > PAGE_INVENTORY_LIMIT) {
    throw new Error(
      `The public read_graph limit must be an integer from 1-100`,
    );
  }
  return {
    name: "read_graph",
    args: { target, limit },
  };
}

/**
 * Fail closed before a public Playground call initializes a session or reaches
 * the network. The Playground is a fixed discovery surface, not a generic MCP
 * proxy.
 *
 * @param {string} name
 * @param {Record<string, unknown>} args
 */
export function assertPublicPlaygroundCall(name, args) {
  if (
    name === "read_graph" &&
    hasExactKeys(args, ["limit", "target"]) &&
    args.target === "graphs" &&
    typeof args.limit === "number" &&
    Number.isInteger(args.limit) &&
    args.limit >= 1 &&
    args.limit <= PAGE_INVENTORY_LIMIT
  ) {
    return;
  }
  if (
    name === "read_page" &&
    hasExactKeys(args, ["changed_since", "max_results"]) &&
    typeof args.changed_since === "string" &&
    args.changed_since.trim().length > 0 &&
    args.max_results === PAGE_INVENTORY_LIMIT
  ) {
    return;
  }
  throw new Error(
    "The public Playground only supports read_graph target=graphs with limit " +
      "1-100 and the bounded read_page discovery inventory.",
  );
}

/**
 * Copy a known public scalar without allowing nested or unexpected response
 * data to cross into the browser UI.
 *
 * @param {Record<string, any>} source
 * @param {Record<string, any>} target
 * @param {string} key
 * @param {string} type
 * @param {boolean} [nullable]
 */
function copyPublicScalar(source, target, key, type, nullable = false) {
  if (!(key in source)) return;
  const value = source[key];
  if (nullable && value === null) {
    target[key] = null;
    return;
  }
  if (
    typeof value !== type ||
    (type === "number" && !Number.isFinite(value))
  ) {
    throw new Error(`public MCP response field ${key} has an invalid type`);
  }
  target[key] = value;
}

/** @param {any} value */
function sanitizePublicUniverse(value) {
  if (!value || typeof value !== "object" || Array.isArray(value)) {
    throw new Error("read_graph graphs returned an invalid universe record");
  }
  if (typeof value.id !== "string" || !value.id.trim()) {
    throw new Error("read_graph graphs returned a universe without an id");
  }
  const safe = { id: value.id };
  copyPublicScalar(value, safe, "visibility", "string");
  copyPublicScalar(value, safe, "has_premise", "boolean");
  copyPublicScalar(value, safe, "has_soul", "boolean");
  copyPublicScalar(value, safe, "word_count", "number");
  copyPublicScalar(value, safe, "phase", "string", true);
  copyPublicScalar(value, safe, "phase_human", "string");
  copyPublicScalar(value, safe, "staleness", "string");
  copyPublicScalar(value, safe, "last_activity_at", "string", true);
  copyPublicScalar(value, safe, "accept_rate", "number", true);
  return safe;
}

/** @param {any} value */
function sanitizePublicPageSummary(value) {
  if (!value || typeof value !== "object" || Array.isArray(value)) {
    throw new Error("read_page inventory returned an invalid page record");
  }
  if (typeof value.path !== "string" || !value.path.trim()) {
    throw new Error("read_page inventory returned a page without a path");
  }
  const safe = { path: value.path.trim() };
  copyPublicScalar(value, safe, "title", "string");
  copyPublicScalar(value, safe, "type", "string");
  copyPublicScalar(value, safe, "updated", "string");
  copyPublicScalar(value, safe, "is_draft", "boolean");
  copyPublicScalar(value, safe, "excerpt", "string");
  return safe;
}

/**
 * Validate the response against the same fixed call contract used before the
 * request, then return only fields suitable for the public Playground.
 * Unknown top-level and record fields are deliberately dropped.
 *
 * @param {string} name
 * @param {Record<string, unknown>} args
 * @param {any} payload
 * @returns {Record<string, any>}
 */
export function sanitizePublicPlaygroundResponse(name, args, payload) {
  assertPublicPlaygroundCall(name, args);
  if (name === "read_graph") {
    const universes = requireCollection(
      payload,
      "universes",
      "read_graph graphs",
    ).map(sanitizePublicUniverse);
    return { universes, count: universes.length };
  }

  const inventory = splitPageInventory(payload);
  const results = payload.results.map(sanitizePublicPageSummary);
  return {
    results,
    count: results.length,
    total_matches: results.length,
    truncated_count: 0,
    scope: inventory.scope,
    scope_note: inventory.scopeNote,
  };
}

/**
 * @param {string} page
 * @param {Set<string>} validatedPaths
 * @returns {{ name: 'read_page', args: { page: string } }}
 */
export function publicPageCall(page, validatedPaths) {
  const provenPaths = validatedPathSets.get(validatedPaths);
  const canonical = canonicalPagePath(page);
  if (!provenPaths?.has(canonical)) {
    throw new Error(
      `read_page path "${canonical}" was not present in the validated inventory`,
    );
  }
  return {
    name: "read_page",
    args: { page: canonical },
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
 * Require a complete collection from a read surface that has a request cap but
 * no cursor or total-count metadata. Filling the cap is ambiguous and cannot
 * replace a full checked-in snapshot.
 *
 * @param {any} payload
 * @param {string} key
 * @param {string} source
 * @param {number} requestLimit
 * @returns {any[]}
 */
export function requireCompleteCollection(payload, key, source, requestLimit) {
  const collection = requireCollection(payload, key, source);
  if (collection.length >= requestLimit) {
    throw new Error(
      `${source} cannot prove completeness at request limit of ${requestLimit}`,
    );
  }
  return collection;
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
 * @template {"discovery" | "all"} Scope
 * @param {any} payload
 * @param {Scope} requiredScope
 * @returns {{ promoted: any[], drafts: any[], validatedPaths: Set<string>, scope: Scope, scopeNote: string }}
 */
function splitInventory(payload, requiredScope) {
  const result = requireObjectResult(payload, "read_page inventory");
  if (!Array.isArray(result.results)) {
    throw new Error("read_page inventory did not return a results array");
  }
  /** @type {Array<Record<string, any>>} */
  const results = result.results;
  const count = result.count;
  const total = result.total_matches;
  const truncated = result.truncated_count;
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
  if (count === PAGE_INVENTORY_LIMIT) {
    throw new Error(
      `read_page inventory cannot prove completeness at request limit of ${PAGE_INVENTORY_LIMIT}`,
    );
  }
  const scope =
    typeof result.scope === "string" && result.scope.trim()
      ? result.scope.trim()
      : "unknown";
  const scopeNote =
    typeof result.scope_note === "string" ? result.scope_note.trim() : "";
  const validScope =
    requiredScope === "discovery"
      ? scope === "discovery" && Boolean(scopeNote)
      : scope === "all" && !scopeNote;
  if (!validScope) {
    const purpose =
      requiredScope === "all" ? "full snapshot inventory" : "read_page inventory";
    throw new Error(
      `${purpose} is incomplete (scope: ${scope})`,
    );
  }
  if (truncated > 0) {
    throw new Error(
      `read_page inventory truncated ${truncated} of ${total} pages`,
    );
  }

  const canonicalPaths = results.map((page) => canonicalPagePath(page?.path));
  if (new Set(canonicalPaths).size !== canonicalPaths.length) {
    throw new Error("read_page inventory returned duplicate page paths");
  }
  const validatedPaths = new Set(canonicalPaths);
  validatedPathSets.set(validatedPaths, new Set(canonicalPaths));
  return {
    promoted: results.filter((page) => !page.is_draft),
    drafts: results.filter((page) => Boolean(page.is_draft)),
    validatedPaths,
    scope: requiredScope,
    scopeNote,
  };
}

/**
 * @param {any} payload
 * @returns {{ promoted: any[], drafts: any[], validatedPaths: Set<string>, scope: 'discovery', scopeNote: string }}
 */
export function splitPageInventory(payload) {
  return splitInventory(payload, "discovery");
}

/**
 * A checked-in full snapshot may only be replaced from an explicit complete
 * all-scope inventory. Discovery scope intentionally omits coordination pages
 * and therefore cannot prove that a full snapshot is complete.
 *
 * @param {any} payload
 * @returns {{ promoted: any[], drafts: any[], validatedPaths: Set<string>, scope: 'all', scopeNote: string }}
 */
export function splitFullPageInventory(payload) {
  return splitInventory(payload, "all");
}
