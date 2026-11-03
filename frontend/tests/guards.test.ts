/**
 * Source guards over frontend/src and DESIGN.md:
 * UI-06 (critical): no floating-point handling of money in the client.
 * UI-07: src/api.ts is the only place that fetches.
 * UI-10: no em dash and no banned brand names (CLAUDE.md rules 5 and 10).
 * UI-32: "เช็ก" wording, spelt with ก: never "เช็ค", and no button or nav label
 *   says "ตรวจสอบ" (descriptive sentences may).
 * UI-27: layers come from order, never from z-index numbers (nav.test.ts draws them).
 * UI-44: the logo has no yellow badge: the app's logo, the favicon and DESIGN.md's options.
 * UI-45: the persona is ม่อน, user demo-mon, everywhere in frontend/ and DESIGN.md.
 */
import assert from "node:assert/strict";
import { existsSync, readdirSync, readFileSync, statSync } from "node:fs";
import { join, relative } from "node:path";
import { test } from "node:test";
import { HOME, NAV, THINK } from "../src/copy.ts";
import { DEMO_USER, PERSONA_NAME } from "../src/mock/persona.ts";
import { BANNED, BANNED_EXACT, BANNED_EXACT_PATTERN, BANNED_PATTERN } from "./banned.ts";

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

// The names are built from parts in banned.ts, so no file spells out what it forbids.
// The tests are scanned too (review F1, Session 21): a guard's own list once named them.
const testFiles = sourceFiles(join(ROOT, "tests"));

test("UI_10_no_banned_brand_names_in_src_design_md_or_tests", () => {
  assert.deepEqual(scan([...files, DESIGN, ...testFiles], BANNED_PATTERN), []);
  assert.deepEqual(scan([...files, DESIGN, ...testFiles], BANNED_EXACT_PATTERN), []);
});

test("UI_10_the_brand_scan_catches_each_name_and_spares_ordinary_code", () => {
  for (const name of BANNED) assert.ok(BANNED_PATTERN.test(name.toLowerCase()), name);
  for (const name of BANNED_EXACT) assert.ok(BANNED_EXACT_PATTERN.test(`app ${name} home`), name);
  for (const line of ["make(lock)", "the loan would make a month RED", "typecheck + production", "i + 1"]) {
    assert.ok(!BANNED_EXACT_PATTERN.test(line), line);
  }
});

test("UI_32_check_before_installment_is_spelt_เช็ก_everywhere", () => {
  // Wording change (parts 5 and 7): "เช็ก" with ก, never "เช็ค"; the old names are gone.
  assert.deepEqual(scan([...files, DESIGN], /เช็ค|ตรวจสอบก่อนผ่อน|ตรวจสอบรายการอื่น/), []);
  // Every button and nav label that checks says "เช็ก" (part 7).
  for (const label of [NAV.think, HOME.thinkCta, THINK.title, THINK.another]) {
    assert.match(label, /^เช็ก/, label);
    assert.doesNotMatch(label, /ตรวจสอบ/, label);
  }
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
  // (a template literal since the header can carry a feature's accent, the buffer's teal)
  assert.match(screen, /<header\s+className=\{?[`"][^`"]*shrink-0/);
  // (`isolate` first: each bar is its own layer, UI-27 in nav.test.ts)
  assert.match(screen, /<main\s+tabIndex=\{0\}\s+className=\{`phone-scroll isolate min-h-0 flex-1 overflow-y-auto/);
  assert.match(screen, /<nav aria-label=\{NAV.menu\} className="isolate shrink-0 /);
});

test("UI_27_layers_come_from_order_never_from_z_index_numbers", () => {
  // The nav is on top because it is drawn last, in a layer of its own (nav.test.ts),
  // never because of a bigger number. The one z-index is the Demo panel's: the overlay
  // that covers the whole frame, the nav included.
  const zIndex = scan(files, /\bz-(\d|\[|auto\b)|zIndex/).map((h) => `${h.file}: ${/\bz-[^\s"'`]+/.exec(h.text)?.[0] ?? h.text}`);
  assert.deepEqual(zIndex, ["src/components/DemoPanel.tsx: z-30"]);
  // Every screen draws its body and its nav through a shell, so each has those layers:
  // Screen.tsx for KidNee's screens, HostScreen.tsx for the host app's home (#/account,
  // Session 21), which has its own header and bar and the same layer rules.
  assert.deepEqual(scan(files, /<(main|nav)\b/).map((h) => h.file), [
    "src/components/HostScreen.tsx",
    "src/components/HostScreen.tsx",
    "src/components/Screen.tsx",
    "src/components/Screen.tsx",
  ]);
  const host = readFileSync(join(SRC, "components", "HostScreen.tsx"), "utf8");
  assert.match(host, /<main\s+tabIndex=\{0\}\s+className=\{`phone-scroll isolate min-h-0 flex-1 overflow-y-auto/);
  assert.match(host, /<nav aria-label=\{ACCOUNT.nav.menu\} className=\{`isolate shrink-0 /);
  const screens = readdirSync(join(SRC, "screens"));
  assert.equal(screens.length, 8);
  for (const name of screens) {
    const shell = name === "Account.tsx" ? /<HostScreen\b/ : /<Screen\b/;
    assert.match(readFileSync(join(SRC, "screens", name), "utf8"), shell, name);
  }
});

// ---- UI-44: no yellow badge on the logo ------------------------------------------------

/** The x of every circle in an SVG: the bean's two eyes are at 17 and 26. */
const circles = (svg: string) => [...svg.matchAll(/<circle\b[^>]*\bcx="(\d+)"/g)].map((m) => m[1]);
const YELLOW = /\bsun-\d|#ffc94d|#ffd977/i;

test("UI_44_the_logo_has_no_yellow_badge_in_the_app_the_favicon_or_design_md", () => {
  const logo = readFileSync(join(SRC, "components", "Logo.tsx"), "utf8");
  const bean = /export function LogoBean[\s\S]*?\n}\n/.exec(logo)?.[0] ?? "";
  const favicon = readFileSync(join(ROOT, "public", "favicon.svg"), "utf8");
  // The bean keeps its body, its eyes and its smile; nothing on its edge.
  assert.deepEqual(circles(bean), ["17", "26"]);
  assert.deepEqual(circles(favicon), ["17", "26"]);
  // No yellow in the logo, the favicon or the tokens, nor in DESIGN.md's two options.
  const options = [...readFileSync(DESIGN, "utf8").matchAll(/```svg\n([\s\S]*?)```/g)].map((m) => m[1] ?? "");
  assert.equal(options.length, 2);
  assert.deepEqual(circles(options[0] ?? ""), ["17", "26"]);
  const texts: [string, string][] = [
    ["Logo.tsx", logo],
    ["favicon.svg", favicon],
    ["index.css", readFileSync(join(SRC, "index.css"), "utf8")],
    ["DESIGN.md option A", options[0] ?? ""],
    ["DESIGN.md option B", options[1] ?? ""],
  ];
  for (const [name, text] of texts) assert.doesNotMatch(text, YELLOW, name);
  // Guard the guard: the badge as it was is caught.
  assert.deepEqual(circles('<circle cx="17" r="2"/><circle cx="26" r="2"/><circle cx="37" cy="36" r="6" fill="#ffc94d"/>'), ["17", "26", "37"]);
  assert.match('fill="var(--color-sun-400)"', YELLOW);
});

// ---- UI-45: the persona is ม่อน ----------------------------------------------------------

/** Every text file under a folder (the build output and packages left out). */
function textFiles(dir: string): string[] {
  return readdirSync(dir).flatMap((name) => {
    const path = join(dir, name);
    if (statSync(path).isDirectory()) return ["node_modules", "dist", ".test-build"].includes(name) ? [] : textFiles(path);
    return /\.(ts|tsx|mjs|js|css|html|md|json|svg)$/.test(name) ? [path] : [];
  });
}

test("UI_45_the_persona_is_ม่อน_and_the_demo_user_demo_mon_everywhere", () => {
  assert.equal(PERSONA_NAME, "ม่อน");
  assert.equal(DEMO_USER, "demo-mon");
  // Built from parts so this file does not contain the old name it forbids.
  const old = new RegExp([["มิ้", "นท์"], ["demo-", "mint"], ["Mi", "nt"]].map(([a, b]) => `${a}${b}`).join("|"));
  const everywhere = [...textFiles(ROOT), DESIGN].filter((file) => !file.endsWith("package-lock.json"));
  assert.ok(everywhere.some((file) => file.endsWith(join("tests", "home.test.ts"))), "the tests are scanned too");
  assert.deepEqual(scan(everywhere, old), []);
  assert.ok(old.test("demo-" + "mint") && !old.test("demo-mon"), "guard the guard");
});
