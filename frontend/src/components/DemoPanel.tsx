/**
 * The Demo panel (DESIGN.md section 7.8): a dashed "Demo" button in the header,
 * clearly not part of the app, opens a sheet over the phone frame. It simulates
 * payday for a month (POST /demo/payday) and switches the mock between the demo
 * scenes.
 */
import { useEffect, useState } from "react";
import { ApiError, runPayday, setDemoScene, USE_MOCK, type DemoScene } from "../api.ts";
import type { PaydayOut } from "../api-types.ts";
import { COMMON, DEMO, PAYDAY_OUTCOME } from "../copy.ts";
import { formatBaht } from "../money.ts";
import { navigate } from "../router.ts";
import { addMonths, monthOf, thaiMonth } from "../thaiMonth.ts";
import { Alert, Button } from "./ui.tsx";

const MONTH_CHOICES = 4;

let openSheet: (() => void) | null = null;

/** The header's "Demo" button; the sheet lives at frame level in DemoPanel. */
export function DemoButton() {
  return (
    <button
      type="button"
      onClick={() => openSheet?.()}
      className="min-h-11 cursor-pointer rounded-pill border-2 border-dashed border-info-line bg-info-bg px-3 text-caption font-bold text-info-ink"
    >
      {DEMO.open}
    </button>
  );
}

export function DemoPanel() {
  const [open, setOpen] = useState(false);
  useEffect(() => {
    openSheet = () => setOpen(true);
    return () => {
      openSheet = null;
    };
  }, []);
  return open ? <Sheet onClose={() => setOpen(false)} /> : null;
}

function Sheet({ onClose }: { onClose: () => void }) {
  const now = monthOf(new Date());
  const months = Array.from({ length: MONTH_CHOICES }, (_, i) => addMonths(now, i));
  const [month, setMonth] = useState(addMonths(now, 1));
  const [busy, setBusy] = useState(false);
  const [result, setResult] = useState<{ created: boolean; out: PaydayOut } | null>(null);
  const [message, setMessage] = useState<string | null>(null);

  async function payday() {
    setBusy(true);
    setMessage(null);
    try {
      setResult(await runPayday(month));
    } catch (error) {
      setResult(null);
      // Thai only, never the raw error text (review B2 F7).
      setMessage(
        error instanceof ApiError && error.status === 404
          ? DEMO.paydayUnavailable
          : error instanceof ApiError && error.code === "SETTINGS_REQUIRED"
            ? COMMON.settingsMissingBody
            : DEMO.paydayFailed,
      );
    } finally {
      setBusy(false);
    }
  }

  async function scene(name: DemoScene) {
    setBusy(true);
    try {
      await setDemoScene(name);
      setResult(null);
      setMessage(DEMO.done);
      navigate(name === "first_launch" ? "settings" : "home");
      // Screens load when they open: remount the one on show so it reads the new scene.
      window.dispatchEvent(new Event("kidnee-demo-scene"));
      onClose();
    } finally {
      setBusy(false);
    }
  }

  return (
    <div role="dialog" aria-modal="true" aria-labelledby="demo-title" className="absolute inset-0 z-30 flex items-end bg-ink/40">
      <div className="phone-scroll flex max-h-[85%] w-full flex-col gap-4 overflow-y-auto rounded-t-card border-t-4 border-dashed border-info-line bg-card p-5">
        <div className="flex items-center justify-between">
          <h2 id="demo-title" className="text-lead font-bold text-info-ink">
            {DEMO.title}
          </h2>
          <button type="button" onClick={onClose} className="min-h-11 cursor-pointer rounded-pill px-3 text-body font-semibold text-info-ink underline">
            {DEMO.close}
          </button>
        </div>
        <p className="text-body text-ink-muted">{DEMO.note}</p>

        <section className="flex flex-col gap-3">
          <h3 className="text-body font-bold text-ink">{DEMO.paydayTitle}</h3>
          <label className="flex flex-col gap-1.5">
            <span className="text-body text-ink">{DEMO.paydayMonth}</span>
            <select
              value={month}
              onChange={(e) => {
                setMonth(e.target.value);
                setResult(null);
              }}
              className="min-h-12 cursor-pointer rounded-field border-2 border-line bg-card px-4 text-lead"
            >
              {months.map((m) => (
                <option key={m} value={m}>
                  {thaiMonth(m)}
                </option>
              ))}
            </select>
          </label>
          <Button onClick={() => void payday()} busy={busy} variant="secondary">
            {DEMO.paydayRun}
          </Button>
          {result !== null && (
            <Alert
              tone={result.out.outcome === "over_budget" ? "warn" : result.out.outcome === "leftover_saved" ? "ok" : "info"}
              title={PAYDAY_OUTCOME[result.out.outcome]}
            >
              <p>{DEMO.paydayResult(formatBaht(result.out.month_total), formatBaht(result.out.budget))}</p>
              {!result.created && <p>{DEMO.paydayRepeat}</p>}
            </Alert>
          )}
          {message !== null && <Alert tone="info" title={message} />}
        </section>

        {USE_MOCK && (
          <section className="flex flex-col gap-2">
            <h3 className="text-body font-bold text-ink">{DEMO.scenesTitle}</h3>
            <Button variant="ghost" onClick={() => void scene("first_launch")} disabled={busy}>
              {DEMO.sceneFirst}
            </Button>
            <Button variant="ghost" onClick={() => void scene("persona")} disabled={busy}>
              {DEMO.scenePersona}
            </Button>
            <Button variant="ghost" onClick={() => void scene("over_budget")} disabled={busy}>
              {DEMO.sceneOver}
            </Button>
            <Button variant="ghost" onClick={() => void scene("over_budget_now")} disabled={busy}>
              {DEMO.sceneOverNow}
            </Button>
          </section>
        )}
      </div>
    </div>
  );
}
