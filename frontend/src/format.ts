export function formatCost(usd: number | null): string {
  if (usd === null) return "price unknown";
  if (usd === 0) return "$0";
  if (usd < 0.01) return `$${usd.toFixed(4)}`;
  return `$${usd.toFixed(2)}`;
}

export function formatTokens(count: number): string {
  return count >= 1000 ? `${(count / 1000).toFixed(1)}k` : String(count);
}

/** A quote from a brand document, without the markdown it was written in: a leading list dash, number
 * or ">" and the stars or underscores around bold text. The stored quote stays exact, as proof. */
export function plainQuote(quote: string): string {
  return quote
    .replace(/^\s*(?:[-*+>]|\d+[.)])\s+/, "")
    .replace(/(\*\*|__)(.+?)\1/g, "$2")
    .replace(/`([^`]+)`/g, "$1")
    .trim();
}
