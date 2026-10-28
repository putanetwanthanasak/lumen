/**
 * Manual check, never run in CI (it needs Chrome and the dev server): the bottom nav,
 * raised centre button included, is the top layer over everything that scrolls, on
 * every screen and scene (UI-27, DESIGN.md 5.8 "Layers"). See scripts/README.md.
 *
 * For each view it scrolls the body in 4px steps and, at each step, asks Chrome what
 * is on top (document.elementsFromPoint, which follows paint order) at points inside
 * the raised button and along the nav's top edge. Every one must be the nav, or the
 * Demo panel while it is open. No package: Node's fetch and WebSocket, and the Chrome
 * DevTools Protocol.
 *
 * Usage, from frontend/ with `npm run dev` running:
 *   node scripts/nav-layer-check.mjs [--width 390|370|both] [--height tall|short|tiny|all]
 *                                    [--only <view name part>] [--shots <dir>] [--url <dev server>]
 * Exit code: 0 all on top, 1 something else on top somewhere, 2 Chrome or the dev server missing.
 */
import { spawn } from "node:child_process";
import { accessSync, constants, mkdirSync, mkdtempSync, rmSync, writeFileSync } from "node:fs";
import { tmpdir } from "node:os";
import { delimiter, join } from "node:path";

const args = Object.fromEntries(
  process.argv.slice(2).reduce((pairs, arg, i, all) => (arg.startsWith("--") ? [...pairs, [arg.slice(2), all[i + 1] ?? ""]] : pairs), []),
);
const BASE = (args.url ?? "http://127.0.0.1:5173").replace(/\/$/, "");
const WIDTHS = { 390: "390", 370: "370", both: ["390", "370"] }[args.width ?? "both"];
// [desktop window, phone] heights. The lower the window, the more of each screen's
// cards pass under the raised button; "tiny" brings even the first card (Home's hero).
const HEIGHTS = { tall: [900, 844], short: [560, 480], tiny: [440, 400] };
const RUN_HEIGHTS = args.height === "all" ? Object.keys(HEIGHTS) : [args.height ?? "tiny"];
if (WIDTHS === undefined || RUN_HEIGHTS.some((h) => !(h in HEIGHTS))) {
  console.error("--width is 390, 370 or both; --height is tall, short, tiny or all");
  process.exit(2);
}

// action: the start of a button's text to press first, "expand" for the first folded
// row in the body, or "demo" to open the Demo panel (which must stay above the nav).
const VIEWS = [
  { name: "home-persona", route: "home", scene: "persona" },
  { name: "home-persona-ai-open", route: "home", scene: "persona", action: "อ่านต่อ" },
  { name: "home-over-budget", route: "home", scene: "over_budget", action: "expand" },
  { name: "home-over-budget-now", route: "home", scene: "over_budget_now" },
  { name: "home-offer-interested", route: "home", scene: "over_budget_now", action: "สนใจรวมหนี้" },
  { name: "home-empty-buffer", route: "home", scene: "over_budget_empty_buffer" },
  { name: "home-ai-slow", route: "home", scene: "ai_slow" },
  { name: "home-ai-failing", route: "home", scene: "ai_failing" },
  { name: "months", route: "months", scene: "over_budget", action: "expand" },
  { name: "buffer", route: "buffer", scene: "persona" },
  { name: "buffer-empty", route: "buffer", scene: "over_budget_empty_buffer" },
  { name: "alerts", route: "alerts", scene: "persona" },
  { name: "alerts-over-budget-now", route: "alerts", scene: "over_budget_now" },
  { name: "think", route: "think", scene: "persona" },
  { name: "think-cash", route: "think", scene: "persona", action: "เป็นรายการเงินสด?" },
  { name: "settings", route: "settings", scene: "persona" },
  { name: "demo-panel-open", route: "home", scene: "persona", action: "demo", expect: "dialog" },
].filter((view) => args.only === undefined || view.name.includes(args.only));

// ---- Chrome ----------------------------------------------------------------------

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
  const profile = mkdtempSync(join(tmpdir(), "nav-layer-check-"));
  const chrome = spawn(binary, [
    "--headless=new",
    "--remote-debugging-port=0", // any free port; Chrome prints the one it took
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
  // Chrome's network service can outlive the main process by a few milliseconds and
  // write its state into the profile as it quits, so "exit" is too early to remove it.
  // "close" comes once every process holding Chrome's output, its children too, is gone.
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

/** One page over the DevTools Protocol. */
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

// ---- the scan, run inside the page ---------------------------------------------------

const SCAN = (expect) => `(() => {
  const main = document.querySelector("main");
  const nav = document.querySelector("nav");
  if (!main || !nav) return null;
  const bar = main.nextElementSibling !== nav ? main.nextElementSibling : null;
  const top = ${JSON.stringify(expect)} === "dialog" ? document.querySelector('[role="dialog"]') : nav;
  const navBox = nav.getBoundingClientRect();
  const circle = nav.querySelectorAll("li")[1].querySelector("a > span").getBoundingClientRect();
  // Inside the raised circle, from its top to just under the nav's edge; then the edge.
  const r = circle.width / 2, cx = circle.left + r, cy = circle.top + r;
  const points = [];
  for (let y = Math.ceil(circle.top) + 1; y < navBox.top + 4; y += 2)
    for (let x = Math.ceil(circle.left) + 1; x < circle.right - 1; x += 4)
      if ((x - cx) ** 2 + (y - cy) ** 2 < (r - 1.5) ** 2) points.push([x, y]);
  for (let x = Math.ceil(navBox.left) + 2; x < navBox.right - 2; x += 8) points.push([x, Math.ceil(navBox.top) + 1]);
  const describe = (el) => {
    const cls = typeof el.className === "string" ? el.className : el.getAttribute("class") ?? "";
    return el.tagName.toLowerCase() + (cls ? "." + cls.trim().split(/\\s+/).slice(0, 6).join(".") : "");
  };
  const words = (n) => (n.innerText || n.textContent || "").replace(/\\s+/g, " ").trim().slice(0, 30);
  // A card is the top-level box under the body's column (or the footer, or the bar).
  const cardOf = (el) => {
    if (bar && bar.contains(el)) return "action bar";
    let n = el;
    while (n && n.parentElement && n.parentElement !== main.firstElementChild && n.parentElement !== main) n = n.parentElement;
    if (!n || n === main.firstElementChild || !main.contains(n)) return "gap between cards";
    return n.parentElement === main ? "footer" : n.tagName.toLowerCase() + ' "' + words(n) + '"';
  };
  // What gives an element its own layer: each such ancestor inside the body or the bar.
  const lifts = (el) => {
    const out = [];
    for (let n = el; n && n !== main && n !== bar; n = n.parentElement) {
      const s = getComputedStyle(n);
      const why = [];
      if (s.position !== "static") why.push("position:" + s.position);
      if (s.zIndex !== "auto") why.push("z-index:" + s.zIndex);
      if (s.transform !== "none") why.push("transform");
      if (s.opacity !== "1") why.push("opacity:" + s.opacity);
      if (s.isolation === "isolate") why.push("isolation");
      if (why.length) out.push(describe(n) + " {" + why.join(", ") + "}");
    }
    return out;
  };
  const max = main.scrollHeight - main.clientHeight;
  const cards = {};
  const failures = {};
  let samples = 0;
  let bad = 0;
  for (let y = 0; ; y = Math.min(y + 4, max)) {
    main.scrollTop = y;
    for (const [x, py] of points) {
      const stack = document.elementsFromPoint(x, py);
      samples += 1;
      const ok = stack[0] !== undefined && top !== null && top.contains(stack[0]);
      const under = stack.find((el) => (main.contains(el) && el !== main) || (bar && bar.contains(el)));
      if (under) {
        const c = (cards[cardOf(under)] ??= { samples: 0, notOnTop: 0, scroll: y });
        c.samples += 1;
        if (!ok) c.notOnTop += 1;
      }
      if (!ok) {
        bad += 1;
        const key = stack[0] ? describe(stack[0]) : "nothing";
        (failures[key] ??= { count: 0, scroll: y, lifts: stack[0] ? lifts(stack[0]) : [] }).count += 1;
      }
    }
    if (y >= max) break;
  }
  return {
    layers: { body: getComputedStyle(main).isolation, bar: bar ? getComputedStyle(bar).isolation : null, nav: getComputedStyle(nav).isolation },
    samples,
    notOnTop: bad,
    cards,
    failures,
    clip: { x: navBox.left, y: circle.top - 64, width: navBox.width, height: navBox.bottom - circle.top + 64 },
  };
})()`;

async function runView(page, view, width, height) {
  const { send, evaluate } = page;
  const frame = width === "370"; // the desktop phone frame: 390 wide with a 10px border
  await send(
    "Emulation.setDeviceMetricsOverride",
    frame
      ? { width: 1280, height: HEIGHTS[height][0], deviceScaleFactor: 2, mobile: false }
      : { width: 390, height: HEIGHTS[height][1], deviceScaleFactor: 2, mobile: true },
  );
  // Through about:blank, so each view is a fresh document: going from one view's URL to
  // the next changes only the #, which keeps the page and its state (an open Demo panel
  // once covered every later view). Chrome gives a loaderId only for a new document.
  await send("Page.navigate", { url: "about:blank" });
  const nav = await send("Page.navigate", { url: `${BASE}/?persona#/${view.route}` });
  if (nav.result?.loaderId === undefined) return { problems: ["the page was not loaded fresh"] };
  for (let i = 0; i < 50 && !(await evaluate(`document.querySelector("main") !== null`).catch(() => false)); i += 1) await wait(100);
  // The scene through the app's own mock (the same module instance as the app).
  await evaluate(`(async () => {
    const api = await import("/src/api.ts");
    await api.setDemoScene(${JSON.stringify(view.scene)});
    window.dispatchEvent(new Event("kidnee-demo-scene"));
  })()`);
  await wait(view.scene === "ai_slow" ? 1500 : 2200); // the mock answers after 450ms per call
  const problems = [];
  if (view.action !== undefined) {
    const how = await evaluate(`(() => {
      const action = ${JSON.stringify(view.action)};
      let el = null;
      if (action === "expand") el = document.querySelector('main button[aria-expanded="false"]');
      else if (action === "demo") el = [...document.querySelectorAll("header button")].find((b) => b.textContent.includes("Demo"));
      else el = [...document.querySelectorAll("button")].find((b) => b.textContent.trim().startsWith(action));
      if (!el) return "none";
      el.click();
      return "clicked";
    })()`);
    if (how !== "clicked") problems.push(`no button for "${view.action}"`);
    await wait(900);
  }
  const out = await evaluate(SCAN(view.expect ?? "nav"));
  if (out === null) return { problems: [...problems, "no <main> or no <nav>"] };
  if (args.shots !== undefined) {
    mkdirSync(args.shots, { recursive: true });
    let i = 0;
    for (const c of Object.values(out.cards)) {
      i += 1;
      await evaluate(`document.querySelector("main").scrollTop = ${c.scroll + 8}`);
      await wait(120);
      const shot = await send("Page.captureScreenshot", { format: "png", clip: { ...out.clip, scale: 1 } });
      writeFileSync(join(args.shots, `${view.name}-${width}-${height}-${String(i).padStart(2, "0")}.png`), Buffer.from(shot.result.data, "base64"));
    }
  }
  return { ...out, problems };
}

// ---- main ------------------------------------------------------------------------

try {
  await fetch(BASE);
} catch {
  console.error(`No dev server at ${BASE}: start it with npm run dev (or pass --url)`);
  process.exit(2);
}
const chrome = await startChrome();
let failed = 0;
let points = 0;
try {
  const page = await openPage(chrome.port);
  for (const width of [WIDTHS].flat()) {
    for (const height of RUN_HEIGHTS) {
      for (const view of VIEWS) {
        const r = await runView(page, view, width, height);
        const where = `${view.name} ${width}px ${height}`;
        if (r.samples === undefined) {
          failed += 1;
          console.log(`FAIL ${where}: ${r.problems.join("; ")}`);
          continue;
        }
        points += r.samples;
        const cards = Object.keys(r.cards).length;
        if (r.notOnTop === 0 && r.problems.length === 0) {
          console.log(`ok   ${where}: ${view.expect ?? "nav"} on top at all ${r.samples} points, ${cards} cards under it`);
          continue;
        }
        failed += 1;
        console.log(`FAIL ${where}: something else on top at ${r.notOnTop} of ${r.samples} points (layers ${JSON.stringify(r.layers)})`);
        for (const problem of r.problems) console.log(`       ${problem}`);
        for (const [topmost, f] of Object.entries(r.failures).slice(0, 5)) {
          console.log(`       on top: ${topmost} (${f.count} points, first at scroll ${f.scroll}px)`);
          for (const lift of f.lifts) console.log(`         its layer: ${lift}`);
        }
      }
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
console.log(failed === 0 ? `All on top: ${points} points.` : `${failed} view(s) failed.`);
process.exit(failed === 0 ? 0 : 1);
