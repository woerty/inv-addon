/** Format a price in cents as a German euro string, e.g. 199 -> "€1,99".
 *  Returns "" for null/undefined so callers can omit missing prices. */
export const formatPrice = (cents: number | null | undefined): string =>
  cents != null ? `€${(cents / 100).toFixed(2).replace(".", ",")}` : "";
