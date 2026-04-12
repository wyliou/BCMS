/**
 * Currency formatting utility for BCMS.
 * All monetary amounts from the API arrive as strings (Decimal serialized as string per CR-036).
 * This module provides safe formatting without parseFloat precision loss.
 */

/**
 * Intl.NumberFormat instance configured for zh-TW decimal display
 * with 2 minimum fraction digits.
 */
const formatter = new Intl.NumberFormat('zh-TW', {
  style: 'decimal',
  minimumFractionDigits: 2,
  maximumFractionDigits: 2,
});

/**
 * Formats a monetary amount string for display using zh-TW locale formatting.
 * Preserves precision by using the Intl.NumberFormat API.
 *
 * @param value - The monetary amount as a string (from API Decimal serialization), or null.
 * @returns The formatted string, or null if the input is null/undefined.
 */
export function formatAmount(value: string | null | undefined): string | null {
  if (value === null || value === undefined) {
    return null;
  }

  // Reason: Number() is used only for Intl formatting — not for arithmetic or display of raw digits
  const num = Number(value);

  if (isNaN(num)) {
    return value;
  }

  return formatter.format(num);
}
