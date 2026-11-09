/**
 * Exact money arithmetic for the MOCK SERVER ONLY, in BigInt satang.
 *
 * The real backend does this with Decimal. The screens never import this file
 * (DESIGN.md section 3); it exists so the mock can answer like the backend.
 */
import { fromSatang, toSatang, type Money } from "../money.ts";

// One copy of each: the form's exact product (money.ts timesMonths) uses them too.
export { fromSatang, toSatang };

export function sum(values: readonly Money[]): Money {
  return fromSatang(values.reduce((acc, v) => acc + toSatang(v), 0n));
}
