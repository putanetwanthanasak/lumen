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

test("UI_06_no_floating_point_handling_of_money_in_src", () => {
  // Number(), Math.*, parseFloat, parseInt and toFixed are allowed only on a line that
  // says why it is not money ("ui-06-allow: ..."): a day, a percent, a count, a size.
  const hits = scan(
    files,
    /\bparseFloat\(|\bparseInt\(|\.toFixed\(|\bNumber\(|\bMath\.|\btoLocaleString\(|type="number"/,
    /ui-06-allow: \S/,
  );
  assert.deepEqual(hits, []);
});

test("UI_06_the_scanner_catches_a_float_on_money", () => {
  // Guard the guard: the pattern must see the usual mistakes.
  const sample = ["const t = parseFloat(total);", "x.toFixed(2)", "Number(row.total)", 'type="number"'];
  for (const line of sample) {
    assert.ok(/\bparseFloat\(|\.toFixed\(|\bNumber\(|type="number"/.test(line), line);
  }
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
