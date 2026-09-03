// Plain JS on purpose: the node test suite drives this exact function with
// fixtures, so the rule that keeps a non-discoverable universe off the page is
// tested against the real code path rather than against a regex over source.

import { sanitizePublicUniverse } from "../../shared/mcp/public-read-contract.js";

/**
 * @typedef {{ id: string, phase: string, word_count: number, last_activity_at: string | null }} Row
 */

/**
 * Rows for anything the public read contract accepts as discoverable.
 *
 * A live read is already sanitized server-side by the shared contract, but the
 * checked-in snapshot is only a JSON import with a TypeScript assertion on it,
 * so both paths come through here. `sanitizePublicUniverse` throws on a record
 * whose visibility is missing, private, or anything but explicitly
 * discoverable; one bad record is dropped rather than blanking the page, which
 * is the honest behaviour for a stale snapshot.
 *
 * @param {unknown} universes
 * @returns {Row[]}
 */
export function discoverableRows(universes) {
  if (!Array.isArray(universes)) return [];
  const rows = [];
  for (const universe of universes) {
    let safe;
    try {
      safe = sanitizePublicUniverse(universe);
    } catch {
      continue;
    }
    rows.push({
      id: safe.id,
      phase: safe.phase_human ?? safe.phase ?? "unknown",
      word_count: typeof safe.word_count === "number" ? safe.word_count : 0,
      last_activity_at: typeof safe.last_activity_at === "string" ? safe.last_activity_at : null,
    });
  }
  return rows;
}

export default discoverableRows;
