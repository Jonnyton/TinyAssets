/**
 * fmt.ts — the ONE date/stamp formatter for the whole site.
 *
 * Persona crawl 2026-06-09 found three date formats and future-dated UTC
 * stamps ("Jun 10" on a Jun 9 visit) across pages. Timestamp discipline is
 * the site's core promise, so: every visible stamp goes through these.
 * Rule: viewer-local time, one format, explicit "local" never needed —
 * what the visitor's calendar says is the truth they can check.
 */

const MONTHS = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec'];

function pad2(value: number): string {
  return String(value).padStart(2, '0');
}

/** "9 Jun 2026" — deterministic UTC for SSR/client hydration fallbacks. */
export function fmtDateStable(value: string | number | Date | null | undefined): string {
  const d = toDate(value);
  if (!d) return 'unknown';
  return `${d.getUTCDate()} ${MONTHS[d.getUTCMonth()]} ${d.getUTCFullYear()}`;
}

/** "9 Jun 2026, 21:09 UTC" — deterministic UTC for SSR/client hydration fallbacks. */
export function fmtStampStable(value: string | number | Date | null | undefined): string {
  const d = toDate(value);
  if (!d) return 'unknown';
  return `${d.getUTCDate()} ${MONTHS[d.getUTCMonth()]} ${d.getUTCFullYear()}, ${pad2(d.getUTCHours())}:${pad2(d.getUTCMinutes())} UTC`;
}

/** Locale-stable thousands grouping for text rendered during hydration. */
export function fmtCount(value: number): string {
  return value.toLocaleString('en-US');
}

/** "9 Jun 2026" — viewer-local. */
export function fmtDate(value: string | number | Date | null | undefined): string {
  const d = toDate(value);
  if (!d) return 'unknown';
  return d.toLocaleDateString('en-GB', { day: 'numeric', month: 'short', year: 'numeric' });
}

/** "9 Jun 2026, 21:09" — viewer-local. */
export function fmtStamp(value: string | number | Date | null | undefined): string {
  const d = toDate(value);
  if (!d) return 'unknown';
  return (
    d.toLocaleDateString('en-GB', { day: 'numeric', month: 'short', year: 'numeric' }) +
    ', ' +
    d.toLocaleTimeString('en-GB', { hour: '2-digit', minute: '2-digit' })
  );
}

/** "just now" / "4m ago" / "6h ago" / "3d ago" — for read-stamps. */
export function fmtRel(value: string | number | Date | null | undefined): string {
  const d = toDate(value);
  if (!d) return 'unknown';
  const diff = Date.now() - d.getTime();
  if (diff < 90_000) return 'just now';
  if (diff < 3_600_000) return `${Math.floor(diff / 60_000)}m ago`;
  if (diff < 86_400_000) return `${Math.floor(diff / 3_600_000)}h ago`;
  return `${Math.floor(diff / 86_400_000)}d ago`;
}

function toDate(value: string | number | Date | null | undefined): Date | null {
  if (value === null || value === undefined || value === '') return null;
  if (value instanceof Date) return Number.isNaN(value.getTime()) ? null : value;
  if (typeof value === 'number') {
    const ms = value > 1_000_000_000_000 ? value : value * 1000;
    const d = new Date(ms);
    return Number.isNaN(d.getTime()) ? null : d;
  }
  const ms = Date.parse(value);
  return Number.isNaN(ms) ? null : new Date(ms);
}
