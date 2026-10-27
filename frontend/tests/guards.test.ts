/**
 * Source guards over frontend/src and DESIGN.md:
 * UI-06 (critical): no floating-point handling of money in the client.
 * UI-07: src/api.ts is the only place that fetches.
 * UI-10: no em dash and no banned brand names (CLAUDE.md rules 5 and 10).
 * UI-32: "เช็กก่อนผ่อน", spelt with ก, never "เช็ค" or the old "ตรวจสอบก่อนผ่อน".
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

test("UI_32_check_before_installment_is_spelt_เช็ก_everywhere", () => {
  // Wording change (part 5): "เช็ก" with ก, never "เช็ค"; the old name is gone.
  assert.deepEqual(scan([...files, DESIGN], /เช็ค|ตรวจสอบก่อนผ่อน/), []);
});

test("UI_22_the_scrollbar_is_hidden_inside_the_phone_frame_only", () => {
  // The phone frame's scrolling body hides its scrollbar (Firefox and WebKit rules)...
  const css = readFileSync(join(SRC, "index.css"), "utf8");
  assert.match(css, /\.phone-scroll\s*\{\s*scrollbar-width:\s*none;\s*\}/);
  assert.match(css, /\.phone-scroll::-webkit-scrollbar\s*\{\s*display:\s*none;\s*\}/);
  // ...and nothing else does: no global rule on html, body or *.
  assert.deepEqual(
    scan(files, /scrollbar-width|::-webkit-scrollbar/).map((h) => h.text),
    ["scrollbar-width: none;", ".phone-scroll::-webkit-scrollbar {"],
  );
  // It still scrolls, and takes keyboard focus so arrow keys and Page Down work.
  const screen = readFileSync(join(SRC, "components", "Screen.tsx"), "utf8");
  assert.match(screen, /<main\s+tabIndex=\{0\}\s+className=\{`phone-scroll [^`]*overflow-y-auto/);
});

test("UI_26_the_phone_frame_never_scrolls_and_hidden_inputs_stay_in_the_scrolling_body", () => {
  // The frame clips (overflow: clip cannot be scrolled, even by focus or code)...
  const app = readFileSync(join(SRC, "App.tsx"), "utf8");
  assert.match(app, /className="relative h-dvh w-full overflow-clip /);
  assert.doesNotMatch(app, /overflow-hidden/);
  // ...and every visually hidden input sits in a `relative` label, so focusing it
  // scrolls <main>, not the frame (the bug: the frame scrolled 157px and lifted the nav).
  // From each sr-only class back to its tag: an `=>` inside the tag would stop a
  // `[^>]*` scan, which once matched none of the inputs (B-UI-55).
  let inputs = 0;
  const hits = files.flatMap((file) => {
    const text = readFileSync(file, "utf8");
    return [...text.matchAll(/className="sr-only"/g)].flatMap((m) => {
      if (!text.startsWith("<input", text.lastIndexOf("<", m.index))) return [];
      inputs += 1;
      const label = text.lastIndexOf("<label", m.index);
      const tag = label === -1 ? "" : text.slice(label, m.index);
      return /\brelative\b/.test(tag) ? [] : [`${relative(ROOT, file)} at ${m.index}`];
    });
  });
  assert.deepEqual(hits, []);
  // The term choices went with the consolidation screen (part 4).
  assert.ok(inputs >= 2, `found ${inputs} hidden inputs; expected the first due and saving mode choices`);
  // Only <main> scrolls: the bars around it never shrink.
  const screen = readFileSync(join(SRC, "components", "Screen.tsx"), "utf8");
  assert.match(screen, /<header className="[^"]*shrink-0/);
  assert.match(screen, /<main\s+tabIndex=\{0\}\s+className=\{`phone-scroll min-h-0 flex-1 overflow-y-auto/);
  assert.match(screen, /<nav aria-label=\{NAV.menu\} className="shrink-0 /);
});
