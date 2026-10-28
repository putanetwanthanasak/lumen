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
