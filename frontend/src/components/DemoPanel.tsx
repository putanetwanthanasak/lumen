/**
 * The Demo panel (DESIGN.md section 7.8): a dashed "Demo" button in the header,
 * clearly not part of the app, opens a sheet over the phone frame. It shows only
 * while the demo endpoints are on (DEMO_ENDPOINTS_ENABLED, UI-49). It switches between
 * the seeded personas (X-Demo-User) and simulates payday for a month (POST
 * /demo/payday). With `--mode mock` it switches the mock's scenes instead of personas.
 */
import { useEffect, useState } from "react";
import { ApiError, demoEndpointsEnabled, needsSettings, runPayday, setDemoScene, USE_MOCK, type DemoScene } from "../api.ts";
import type { PaydayOut } from "../api-types.ts";
import { DEMO, PAYDAY_OUTCOME } from "../copy.ts";
import { formatBaht } from "../money.ts";
import { demoUser, PERSONAS, setDemoUser } from "../personas.ts";
import { navigate } from "../router.ts";
import { addMonths, monthOf, thaiMonth } from "../thaiMonth.ts";
import { Icon } from "./Icon.tsx";
import { Alert, Button } from "./ui.tsx";

const MONTH_CHOICES = 4;

let openSheet: (() => void) | null = null;

// Asked once per page: a probe that writes nothing (src/api.ts).
let enabled: Promise<boolean> | null = null;

function useDemoEnabled(): boolean {
  const [on, setOn] = useState(false);
  useEffect(() => {
    enabled ??= demoEndpointsEnabled();
    let live = true;
    enabled.then((value) => live && setOn(value));
    return () => {
      live = false;
    };
  }, []);
  return on;
}

/** The screen on show reads its data again (App remounts it). */
function reloadScreen(): void {
  window.dispatchEvent(new Event("kidnee-demo-scene"));
}

/** The header's "Demo" button, only while the demo endpoints are on; the sheet lives at frame level in DemoPanel. */
export function DemoButton() {
  if (!useDemoEnabled()) return null;
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
      reloadScreen(); // the buffer may have changed
    } catch (error) {
      setResult(null);
      if (needsSettings(error)) {
        navigate("settings");
        onClose();
        return;
      }
      // Thai only, never the raw error text (review B2 F7).
      setMessage(error instanceof ApiError && error.status === 404 ? DEMO.paydayUnavailable : DEMO.paydayFailed);
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
      reloadScreen();
      onClose();
    } finally {
      setBusy(false);
    }
  }

  function persona(id: string) {
    setDemoUser(id);
    setResult(null);
    navigate("home");
    reloadScreen();
    onClose();
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

        {!USE_MOCK && (
          <section className="flex flex-col gap-2">
            <h3 className="text-body font-bold text-ink">{DEMO.personaTitle}</h3>
            <p className="text-caption text-ink-muted">{DEMO.personaNote}</p>
            {PERSONAS.map((p) => {
              const on = p.id === demoUser();
              return (
                <button
                  key={p.id}
                  type="button"
                  aria-pressed={on}
                  onClick={() => persona(p.id)}
                  className={`flex min-h-12 cursor-pointer flex-col items-start gap-0.5 rounded-field border-2 px-4 py-2 text-left ${
                    on ? "border-info-line bg-info-bg" : "border-line bg-card hover:bg-surface"
                  }`}
                >
                  <span className="flex items-center gap-2 text-body font-semibold text-ink">
                    {on && <Icon name="check" size={18} />}
                    {p.name ?? DEMO.personaPlain} <span className="font-normal text-ink-muted">({p.id})</span>
                  </span>
                  <span className="text-caption text-ink-muted">{p.story}</span>
                </button>
              );
            })}
          </section>
        )}

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
            <Button variant="ghost" onClick={() => void scene("over_budget_empty_buffer")} disabled={busy}>
              {DEMO.sceneOverEmpty}
            </Button>
            <Button variant="ghost" onClick={() => void scene("ai_slow")} disabled={busy}>
              {DEMO.sceneAiSlow}
            </Button>
            <Button variant="ghost" onClick={() => void scene("ai_failing")} disabled={busy}>
              {DEMO.sceneAiFailing}
            </Button>
          </section>
        )}
      </div>
    </div>
  );
}
