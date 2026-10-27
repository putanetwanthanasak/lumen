/**
 * Source guards over frontend/src and DESIGN.md:
 * UI-06 (critical): no floating-point handling of money in the client.
 * UI-07: src/api.ts is the only place that fetches.
 * UI-10: no em dash and no banned brand names (CLAUDE.md rules 5 and 10).
 */
import assert from "node:assert/strict";
import { existsSync, readdirSync, readFileSync, statSync } from "node:fs";
import { join, relative } from "node:path";
import { test } from "node:test";

// npm runs the tests from frontend/ (the tests are compiled to .test-build first).
const ROOT = process.cwd();
if (!existsSync(join(ROOT, "src", "api.ts"))) throw new Error("run the tests from frontend/: npm test");
const SRC = join(ROOT, "src");
const DESIGN = join(ROOT, "..", "DESIGN.md");

function sourceFiles(dir: string): string[] {
  return readdirSync(dir).flatMap((name) => {
    const path = join(dir, name);
    return statSync(path).isDirectory() ? sourceFiles(path) : /\.(ts|tsx|css)$/.test(name) ? [path] : [];
  });
}

type Hit = { file: string; line: number; text: string };

function scan(files: string[], pattern: RegExp, allow?: RegExp): Hit[] {
  return files.flatMap((file) =>
    readFileSync(file, "utf8")
      .split("\n")
      .flatMap((text, i) =>
        pattern.test(text) && !(allow?.test(text) ?? false)
          ? [{ file: relative(ROOT, file), line: i + 1, text: text.trim() }]
          : [],
      ),
  );
}

const files = sourceFiles(SRC);

// Ways a money string becomes a float: Number(), unary plus, parseFloat/parseInt,
// toFixed, Math.*, toLocaleString, a number input. One pattern, used by both tests
// below (review F6).
const FLOAT_ON_MONEY =
  /\bparseFloat\(|\bparseInt\(|\.toFixed\(|\bNumber\(|\bMath\.|\btoLocaleString\(|type="number"|(^|[=(,!?:&|]|\breturn)\s*\+\s*[A-Za-z_(]/;

test("UI_06_no_floating_point_handling_of_money_in_src", () => {
  // Allowed only on a line that says why it is not money ("ui-06-allow: ..."):
  // a day, a percent, a count, a drawing size.
  assert.deepEqual(scan(files, FLOAT_ON_MONEY, /ui-06-allow: \S/), []);
});

test("UI_06_the_scanner_catches_a_float_on_money", () => {
  // Guard the guard, with the same pattern the scan uses.
  const caught = [
    "const t = parseFloat(total);",
    "x.toFixed(2)",
    "Number(row.total)",
    'type="number"',
    "const over = +thisMonth.total > +budget;",
    "return +amount;",
    "f(+a.total)",
    "Math.round(x)",
    "total.toLocaleString()",
  ];
  for (const line of caught) assert.ok(FLOAT_ON_MONEY.test(line), line);
  const allowed = ["const a = b + c;", "i += 1;", "`${a}+${b}`", 'x = "+66";'];
  for (const line of allowed) assert.ok(!FLOAT_ON_MONEY.test(line), line);
});

test("UI_07_only_api_ts_calls_fetch", () => {
  const hits = scan(files, /\bfetch\(|XMLHttpRequest|axios/).filter((h) => h.file !== join("src", "api.ts"));
  assert.deepEqual(hits, []);
});

test("UI_10_no_em_dash_in_src_or_design_md", () => {
  assert.deepEqual(scan([...files, DESIGN], /—/), []);
});

// Built from parts so this file does not contain the names it forbids.
const BANNED = [
  ["K", "Bank"],
  ["KB", "TG"],
  ["Kasi", "korn"],
  ["K ", "PLUS"],
  ["K", "PLUS"],
  ["Sho", "pee"],
  ["กสิ", "กร"],
  ["ช้อป", "ปี้"],
].map(([a, b]) => `${a}${b}`);

test("UI_10_no_banned_brand_names_in_src_or_design_md", () => {
  const pattern = new RegExp(BANNED.map((n) => n.replace(/ /g, "\\s*")).join("|"), "i");
  assert.deepEqual(scan([...files, DESIGN], pattern), []);
});
