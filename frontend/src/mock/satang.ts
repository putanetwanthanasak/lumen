/**
 * Exact money arithmetic for the MOCK SERVER ONLY, in BigInt satang.
 *
 * The real backend does this with Decimal. The screens never import this file
 * (DESIGN.md section 3); it exists so the mock can answer like the backend.
 */
import { toSatang, type Money } from "../money.ts";

export { toSatang };

/** 150050n -> "1500.50". */
export function fromSatang(value: bigint): Money {
  const negative = value < 0n;
  const digits = (negative ? -value : value).toString().padStart(3, "0");
  const text = `${digits.slice(0, -2)}.${digits.slice(-2)}`;
  return negative ? `-${text}` : text;
}

export function sum(values: readonly Money[]): Money {
  return fromSatang(values.reduce((acc, v) => acc + toSatang(v), 0n));
}
