/**
 * Manual check, never run in CI (it needs Chrome and the dev server in mock mode): the
 * result chart's month labels and bars (UI-40, DESIGN.md 5.4). See scripts/README.md.
 *
 * For the red demo (12 months), the green demo (10), and red over 24 and 36 months, at
 * 360, 390 and 430px wide, it checks:
 *   - up to 12 months every bar has a label; beyond, every k-th from the first, k = ceil(n / 12);
 *   - the labels are 11px, each centred on its own bar (within 1px), at least 2px from
 *     the next in the two demos (never overlapping beyond 12 months), and inside the plot;
 *   - every bar is painted the same width and every gap too (spread at most 0.5px).
 * Labels are measured in the page (getBoundingClientRect). Bars are measured in a
 * screenshot, since layout gives every bar the same fractional width and the unevenness
 * only appears when Chrome draws their edges on whole pixels.
 *
 * Usage, from frontend/ with `npm run dev -- --mode mock` running:
 *   node scripts/month-labels-check.mjs [--dpr 3] [--only <view name part>] [--url <dev server>]
 * Exit code: 0 all good, 1 a check failed, 2 Chrome or the dev server missing.
 */
import { spawn } from "node:child_process";
import { accessSync, constants, mkdtempSync, rmSync } from "node:fs";
import { tmpdir } from "node:os";
import { delimiter, join } from "node:path";

const args = Object.fromEntries(
  process.argv.slice(2).reduce((pairs, arg, i, all) => (arg.startsWith("--") ? [...pairs, [arg.slice(2), all[i + 1] ?? ""]] : pairs), []),
);
const BASE = (args.url ?? "http://127.0.0.1:5173").replace(/\/$/, "");
const DPR = Number(args.dpr ?? "3");
const WIDTHS = [360, 390, 430];
const LABELLED_MONTHS = 12;

// demo: the Demo strip's button that fills the form; fill: months typed over its term;
// apart: the least room between two labels. The demos need 2px; beyond 12 months only
// that no two overlap (at 360px a 36-month plot has no more room: see the log).
const VIEWS = [
  { name: "red", demo: "เกินเกณฑ์", months: 12, apart: 2 },
  { name: "green", demo: "อยู่ในงบ", months: 10, apart: 2 },
  { name: "red-24", demo: "เกินเกณฑ์", months: 24, fill: "24", apart: 0 },
  { name: "red-36", demo: "เกินเกณฑ์", months: 36, fill: "36", apart: 0 },
].filter((view) => args.only === undefined || view.name.includes(args.only));

// ---- Chrome (as in nav-layer-check.mjs) -------------------------------------------

function findChrome() {
  const names = ["google-chrome", "google-chrome-stable", "chromium", "chromium-browser"];
  const candidates = [
    process.env.CHROME,
    ...(process.env.PATH ?? "").split(delimiter).flatMap((dir) => names.map((name) => join(dir, name))),
    "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome",
  ];
  return candidates.find((path) => {
    if (!path) return false;
    try {
      accessSync(path, constants.X_OK);
      return true;
    } catch {
      return false;
    }
  });
}

async function startChrome() {
  const binary = findChrome();
  if (binary === undefined) {
    console.error("Chrome not found: install it, or set CHROME=/path/to/chrome");
    process.exit(2);
  }
  const profile = mkdtempSync(join(tmpdir(), "month-labels-check-"));
  const chrome = spawn(binary, [
    "--headless=new",
    "--remote-debugging-port=0",
    `--user-data-dir=${profile}`,
    "--no-first-run",
    "--no-default-browser-check",
    "--disable-gpu",
    "--hide-scrollbars",
    "about:blank",
  ]);
  const port = await new Promise((resolve, reject) => {
    let seen = "";
    const timer = setTimeout(() => reject(new Error("Chrome did not start")), 20000);
    chrome.stderr.on("data", (chunk) => {
      seen += chunk;
      const found = /DevTools listening on ws:\/\/[^:]+:(\d+)\//.exec(seen);
      if (found) {
        clearTimeout(timer);
        resolve(found[1]);
      }
    });
    chrome.on("exit", () => reject(new Error(`Chrome exited: ${seen.slice(-300)}`)));
  });
  const closed = new Promise((resolve) => chrome.once("close", resolve));
  chrome.stdout.resume();
  const stop = async () => {
    if (chrome.exitCode === null && chrome.signalCode === null) chrome.kill();
    const gone = await Promise.race([closed.then(() => true), wait(10000).then(() => false)]);
    if (gone) rmSync(profile, { recursive: true, force: true });
    else console.error(`Chrome did not quit within 10s; its profile is left in ${profile}`);
  };
  return { port, stop };
}

async function openPage(port) {
  const target = await (await fetch(`http://127.0.0.1:${port}/json/new?about:blank`, { method: "PUT" })).json();
  const ws = new WebSocket(target.webSocketDebuggerUrl);
  await new Promise((resolve, reject) => {
    ws.onopen = resolve;
    ws.onerror = reject;
  });
  let id = 0;
  const pending = new Map();
  const errors = [];
  ws.onmessage = (event) => {
    const msg = JSON.parse(event.data);
    if (msg.method === "Runtime.exceptionThrown") errors.push(msg.params.exceptionDetails.exception?.description ?? msg.params.exceptionDetails.text);
    if (msg.id !== undefined && pending.has(msg.id)) {
      pending.get(msg.id)(msg);
      pending.delete(msg.id);
    }
  };
  const send = (method, params = {}) =>
    new Promise((resolve) => {
      id += 1;
      pending.set(id, resolve);
      ws.send(JSON.stringify({ id, method, params }));
    });
  const evaluate = async (expression) => {
    const out = await send("Runtime.evaluate", { expression, awaitPromise: true, returnByValue: true });
    if (out.result?.exceptionDetails) throw new Error(JSON.stringify(out.result.exceptionDetails));
    return out.result?.result?.value;
  };
  await send("Page.enable");
  await send("Runtime.enable");
  const close = async () => {
    await send("Target.closeTarget", { targetId: target.id });
    ws.close();
  };
  return { send, evaluate, errors, close };
}

const wait = (ms) => new Promise((resolve) => setTimeout(resolve, ms));

// ---- one view ------------------------------------------------------------------------

/** The form filled by a demo button (months typed over, if any), then checked. */
async function openResult(page, view, width) {
  const { send, evaluate } = page;
  await send("Emulation.setDeviceMetricsOverride", { width, height: 900, deviceScaleFactor: DPR, mobile: true });
  await send("Page.navigate", { url: "about:blank" });
  await send("Page.navigate", { url: `${BASE}/?persona#/think` });
  for (let i = 0; i < 50 && !(await evaluate(`document.querySelector("main") !== null`).catch(() => false)); i += 1) await wait(100);
  await evaluate(`(async () => {
    const api = await import("/src/api.ts");
    await api.setDemoScene("persona");
    window.dispatchEvent(new Event("kidnee-demo-scene"));
  })()`);
  await wait(2200); // the mock answers after 450ms per call
  const press = (start) =>
    evaluate(`(() => {
      const el = [...document.querySelectorAll("button")].find((b) => b.textContent.trim().startsWith(${JSON.stringify(start)}));
      if (!el) return false;
      el.click();
      return true;
    })()`);
  if (!(await press(view.demo))) return `no demo button "${view.demo}"`;
  await wait(600);
  if (view.fill !== undefined) {
    const filled = await evaluate(`(() => {
      const label = [...document.querySelectorAll("label")].find((l) => l.textContent.trim().startsWith("จำนวนเดือนที่ผ่อน"));
      const input = label && document.getElementById(label.htmlFor);
      if (!input) return false;
      Object.getOwnPropertyDescriptor(HTMLInputElement.prototype, "value").set.call(input, ${JSON.stringify(view.fill)});
      input.dispatchEvent(new Event("input", { bubbles: true }));
      input.dispatchEvent(new FocusEvent("focusout", { bubbles: true }));
      return true;
    })()`);
    if (!filled) return "no months field";
    await wait(400);
  }
  if (!(await press("ประเมินภาระผ่อน"))) return "no check button";
  for (let i = 0; i < 40 && !(await evaluate(`document.querySelector("figure .grid") !== null`)); i += 1) await wait(100);
  return null;
}

// The plot, its bars and its labels, from layout. Each label belongs to the bar in its grid column.
const LAYOUT = `(() => {
  const grid = document.querySelector("figure .grid");
  if (!grid) return null;
  const box = (el) => { const r = el.getBoundingClientRect(); return { left: r.left, right: r.right, top: r.top, bottom: r.bottom }; };
  const bars = [...grid.children].filter((el) => el.matches("div.row-start-1:not(.col-span-full)"));
  const labels = [...grid.children].filter((el) => el.matches(".row-start-2"));
  const columns = bars.map((b) => b.style.gridColumn);
  return {
    plot: box(grid),
    bars: bars.map(box),
    labels: labels.map((l) => ({ ...box(l), text: l.textContent, bar: columns.indexOf(l.style.gridColumn), size: getComputedStyle(l).fontSize })),
  };
})()`;

// The painted bars along one row of a screenshot strip: runs of pixels that are not
// the white card, in device pixels.
const PAINTED = (png) => `(async () => {
  const bitmap = await createImageBitmap(await (await fetch("data:image/png;base64,${png}")).blob());
  const canvas = new OffscreenCanvas(bitmap.width, bitmap.height);
  const ctx = canvas.getContext("2d");
  ctx.drawImage(bitmap, 0, 0);
  const y = Math.floor(bitmap.height / 2);
  const row = ctx.getImageData(0, y, bitmap.width, 1).data;
  const runs = [];
  let start = -1;
  for (let x = 0; x <= bitmap.width; x += 1) {
    const on = x < bitmap.width && 765 - row[x * 4] - row[x * 4 + 1] - row[x * 4 + 2] > 60;
    if (on && start < 0) start = x;
    if (!on && start >= 0) { runs.push([start, x]); start = -1; }
  }
  return runs;
})()`;

const spread = (values) => (values.length === 0 ? 0 : Math.max(...values) - Math.min(...values));
const fmt = (v) => (Math.round(v * 100) / 100).toString();

async function checkView(page, view, width) {
  const problem = await openResult(page, view, width);
  if (problem !== null) return { problems: [problem] };
  // In view, so the screenshot strip below is on screen.
  await page.evaluate(`document.querySelector("figure .grid")?.scrollIntoView({ block: "center" })`);
  await wait(300);
  const layout = await page.evaluate(LAYOUT);
  if (layout === null) return { problems: ["no chart"] };
  const { plot, bars, labels } = layout;
  const problems = [];

  if (bars.length !== view.months) problems.push(`${bars.length} bars, expected ${view.months}`);
  const k = view.months <= LABELLED_MONTHS ? 1 : Math.ceil(view.months / LABELLED_MONTHS);
  const want = bars.map((_, i) => i).filter((i) => i % k === 0);
  const got = labels.map((l) => l.bar);
  if (JSON.stringify(got) !== JSON.stringify(want)) problems.push(`labels under bars ${got.join(",")}, expected ${want.join(",")}`);

  const sizes = [...new Set(labels.map((l) => l.size))];
  if (sizes.length !== 1 || sizes[0] !== "11px") problems.push(`label size ${sizes.join("/")}, expected 11px`);
  let worstCentre = 0;
  let closest = Infinity;
  for (const [i, l] of labels.entries()) {
    const bar = bars[l.bar];
    if (bar === undefined) continue;
    const off = Math.abs((l.left + l.right) / 2 - (bar.left + bar.right) / 2);
    worstCentre = Math.max(worstCentre, off);
    if (off > 1) problems.push(`${l.text} is ${fmt(off)}px off its bar's centre`);
    if (l.left < plot.left || l.right > plot.right) problems.push(`${l.text} sticks out of the plot (${fmt(l.left)} to ${fmt(l.right)}, plot ${fmt(plot.left)} to ${fmt(plot.right)})`);
    const next = labels[i + 1];
    if (next !== undefined) {
      closest = Math.min(closest, next.left - l.right);
      if (next.left - l.right < view.apart) problems.push(`${l.text} and ${next.text} are ${fmt(next.left - l.right)}px apart`);
    }
  }

  // A 1px strip just above the bars' base, where every bar is painted.
  const base = Math.min(...bars.map((b) => b.bottom));
  const shot = await page.send("Page.captureScreenshot", {
    format: "png",
    clip: { x: plot.left, y: base - 2, width: plot.right - plot.left, height: 1, scale: 1 },
  });
  const runs = await page.evaluate(PAINTED(shot.result.data));
  const widths = runs.map(([a, b]) => (b - a) / DPR);
  const gaps = runs.slice(1).map(([a], i) => (a - runs[i][1]) / DPR);
  if (runs.length !== bars.length) problems.push(`${runs.length} bars painted, expected ${bars.length}`);
  if (spread(widths) > 0.5) problems.push(`bar widths ${[...new Set(widths)].map(fmt).join("/")}px (spread ${fmt(spread(widths))})`);
  if (spread(gaps) > 0.5) problems.push(`gaps ${[...new Set(gaps)].map(fmt).join("/")}px (spread ${fmt(spread(gaps))})`);

  return {
    problems,
    summary:
      `${bars.length} bars, ${labels.length} labels (${sizes.join("/")}), centres within ${fmt(worstCentre)}px, ` +
      `labels ${fmt(closest === Infinity ? 0 : closest)}px apart at least, bars ${[...new Set(widths)].map(fmt).join("/")}px, ` +
      `gaps ${[...new Set(gaps)].map(fmt).join("/")}px`,
  };
}

// ---- main ------------------------------------------------------------------------

if (!(DPR >= 1)) {
  console.error("--dpr is a number, 1 or more");
  process.exit(2);
}
try {
  await fetch(BASE);
} catch {
  console.error(`No dev server at ${BASE}: start it with npm run dev -- --mode mock (or pass --url)`);
  process.exit(2);
}
const chrome = await startChrome();
let failed = 0;
try {
  const page = await openPage(chrome.port);
  for (const view of VIEWS) {
    for (const width of WIDTHS) {
      const r = await checkView(page, view, width);
      const where = `${view.name} ${width}px`;
      if (r.problems.length === 0) {
        console.log(`ok   ${where}: ${r.summary}`);
        continue;
      }
      failed += 1;
      console.log(`FAIL ${where}${r.summary ? `: ${r.summary}` : ""}`);
      for (const problem of r.problems) console.log(`       ${problem}`);
    }
  }
  if (page.errors.length > 0) {
    failed += 1;
    console.log(`FAIL page errors: ${page.errors.slice(0, 3).join(" | ")}`);
  }
  await page.close();
} finally {
  await chrome.stop();
}
console.log(failed === 0 ? `All good at DPR ${DPR}.` : `${failed} view(s) failed.`);
process.exit(failed === 0 ? 0 : 1);
