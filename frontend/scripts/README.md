# Manual checks

Run by hand, never in CI: they need Chrome and the running dev server, and adding
a browser to the project would be a new package.

## nav-layer-check.mjs

Checks that the bottom nav, raised centre button included, is drawn above
everything that scrolls, on every screen (UI-27; DESIGN.md 5.8, "Layers").

You need Node 22.12 or later, Chrome or Chromium (set `CHROME=/path/to/chrome`
if it is not on your `PATH`), and the dev server. No package is installed: it
uses Node's own `fetch` and `WebSocket` and the Chrome DevTools Protocol.

```bash
npm run dev -- --mode mock          # one terminal, from frontend/ (the views use the mock's scenes)
node scripts/nav-layer-check.mjs    # another terminal, from frontend/
```

| Option | Values | Default |
|---|---|---|
| `--width` | `390` (a phone), `370` (the phone frame in a desktop window), `both` | `both` |
| `--height` | `tall`, `short`, `tiny`, `all` (the lower the window, the more cards pass under the button) | `tiny` |
| `--only` | part of a view name, for example `home-persona` | every view |
| `--shots` | a folder for a screenshot of each card under the raised button | none |
| `--url` | the dev server | `http://127.0.0.1:5173` |

**Views:** every Home scene (with the paid-off list open in one), ภาระผ่อนรายเดือน,
both buffer scenes, the alerts, the form with and without the cash kinds, settings,
and the Demo panel open. With the
Demo panel open, the panel must be on top instead of the nav.

**How it checks:** it loads each view fresh, then scrolls the body in 4px steps. At
each step it asks Chrome what is on top (`document.elementsFromPoint`, which follows
paint order) at points inside the raised button and along the nav's top edge.

**Result:** one line per view.

| Exit code | Meaning |
|---|---|
| 0 | The nav was on top at every point. |
| 1 | Something else was on top somewhere. The script lists what it was, and the box that gave it a layer of its own (a `relative`, a `z-index`, an `opacity`). |
| 2 | Chrome or the dev server is missing. |

The default run takes about 2 minutes, and `--height all` about 6.

## month-labels-check.mjs

Checks the result chart's month labels and bars (UI-40; DESIGN.md 5.4) in Chrome, for
the red demo (12 months), the green demo (10 months), and red over 24 and 36 months,
at 360, 390 and 430px wide.

The same needs as above: Node, Chrome, and the dev server in mock mode.

```bash
npm run dev -- --mode mock                 # one terminal, from frontend/
node scripts/month-labels-check.mjs        # another terminal, from frontend/
```

| Option | Values | Default |
|---|---|---|
| `--dpr` | the device pixel ratio to draw at | `3` |
| `--only` | part of a view name: `red`, `green`, `red-24`, `red-36` | every view |
| `--url` | the dev server | `http://127.0.0.1:5173` |

**What it checks, for each view and width:**
- Up to 12 months every bar has a label; beyond that every k-th from the first, with k = ceil(months / 12).
- Labels are 11px, each centred on its own bar (within 1px), and inside the plot.
- In the two demos, labels are at least 2px apart. Beyond 12 months, no two labels overlap.
- Every bar is painted the same width, and every gap too (spread at most 0.5px).

**How it checks:**
- The labels and the plot are measured in the page (`getBoundingClientRect`).
- The bars are measured in a screenshot of a 1px strip just above their base: runs of pixels that are not the white card. Layout gives every bar the same fractional width, so only the painted pixels show bars that Chrome rounded apart.

| Exit code | Meaning |
|---|---|
| 0 | Every check passed. |
| 1 | A check failed. The script prints each failure under the view and width. |
| 2 | Chrome or the dev server is missing. |

A run takes about 75 seconds.
