/**
 * The names CLAUDE.md rule 5 forbids, built from parts so no file in the repo spells
 * them out, this one and the tests that scan for them included (review F1, Session 21).
 * Not a test file: guards.test.ts (UI-10) and mainAccount.test.ts (UI-61) import it.
 */

/** Matched without case; a space inside a name matches any spacing, or none. */
export const BANNED = [
  ["K", "Bank"],
  ["KB", "TG"],
  ["Kasi", "korn"],
  ["K ", "PLUS"],
  ["K", "PLUS"],
  ["Sho", "pee"],
  ["กสิ", "กร"],
  ["ช้อป", "ปี้"],
].map(([a, b]) => `${a}${b}`);

/** Matched with case, as whole words: lower-case "make" and "k + 1" are ordinary code. */
export const BANNED_EXACT = [
  ["MA", "KE"],
  ["K", "+"],
].map(([a, b]) => `${a}${b}`);

const escape = (s: string) => s.replace(/[+.]/g, "\\$&");

export const BANNED_PATTERN = new RegExp(BANNED.map((n) => n.replace(/ /g, "\\s*")).join("|"), "i");
export const BANNED_EXACT_PATTERN = new RegExp(BANNED_EXACT.map((n) => `(?<![A-Za-z])${escape(n)}(?![A-Za-z])`).join("|"));
