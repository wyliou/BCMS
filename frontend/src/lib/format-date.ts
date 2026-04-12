/**
 * Formats a nullable ISO timestamp for zh-TW locale display.
 *
 * @param ts - ISO timestamp string or null/undefined.
 * @returns Localized date-time string, or em-dash for null/undefined.
 */
export function formatLocalDateTime(ts: string | null | undefined): string {
  if (!ts) return '\u2014';
  return new Date(ts).toLocaleString('zh-TW');
}
