/**
 * Screen 3: คิดก่อน (DESIGN.md section 7.3).
 * Enter price, months and monthly amount; the preview returns the verdict and one
 * bar per month. "บันทึก" records with the same client_request_id (a double tap or a
 * retry records once); "ยังไม่ซื้อ" records nothing. Recording is always allowed.
 */
import { useEffect, useRef, useState, type FormEvent } from "react";
import { ApiError, getSettings, previewInstallment, recordInstallment } from "../api.ts";
import type { InstallmentKind, RecordedOut, SettingsOut } from "../api-types.ts";
import { THINK } from "../copy.ts";
import { Icon } from "../components/Icon.tsx";
import { Screen } from "../components/Screen.tsx";
import { Alert, Button, Card, ErrorState, Field, Loading, SettingsMissing } from "../components/ui.tsx";
import { MonthBars, VerdictCard } from "../components/Verdict.tsx";
import { SCENARIOS, type Scenario } from "../mock/persona.ts";
import { formatBaht, toSatang } from "../money.ts";
import { navigate } from "../router.ts";
import { addMonths, monthOf, thaiMonth } from "../thaiMonth.ts";
import {
  answerPreview,
  edit,
  emptyForm,
  entryToRecord,
  startPreview,
  toEntry,
  type Errors,
  type Form,
  type Stage as FormStage,
} from "../thinkFirstForm.ts";
import { useLoad } from "../useLoad.ts";

const FIRST_DUE_CHOICES = 4;
const KINDS: InstallmentKind[] = ["purchase", "cash_withdrawal", "cash_loan"];

export function ThinkFirstScreen() {
  const [load, reload] = useLoad(getSettings);
  return (
    <Screen route="think" title={THINK.title} back="home">
      {load.state === "loading" && <Loading lines={3} />}
      {load.state === "error" && <ErrorState onRetry={reload} />}
      {load.state === "ready" &&
        (load.data === null ? (
          <SettingsMissing onSetUp={() => navigate("settings")} />
        ) : (
          <ThinkFirst settings={load.data} />
        ))}
    </Screen>
  );
}

type Stage = FormStage | { name: "recorded"; result: RecordedOut } | { name: "notBuying" };

/** Demo deep link: "?persona&scene=YELLOW#/think" opens with that example checked. */
function sceneFromUrl(): Scenario | null {
  const scene = new URLSearchParams(window.location.search).get("scene");
  return scene === "GREEN" || scene === "YELLOW" || scene === "RED" ? scene : null;
}

function formFor(scenario: Scenario, base: Form): Form {
  const s = SCENARIOS[scenario];
  return { ...base, name: s.item_name, price: s.item_price, months: String(s.months), monthly: s.monthly_amount };
}

function ThinkFirst({ settings }: { settings: SettingsOut }) {
  const [form, setForm] = useState<Form>(() => {
    const scene = sceneFromUrl();
    return scene === null ? emptyForm(new Date()) : formFor(scene, emptyForm(new Date()));
  });
  const [errors, setErrors] = useState<Errors>({});
  const [stage, setStage] = useState<Stage>({ name: "form" });
  const [busy, setBusy] = useState(false);
  const pending = useRef<string | null>(null); // the preview request still waited for
  const [problem, setProblem] = useState<"failed" | "settings" | null>(null);

  const set = <K extends keyof Form>(key: K, value: Form[K]) => {
    setForm((f) => ({ ...f, [key]: value }));
    pending.current = null;
    // A changed entry is a new entry: a pending or shown verdict no longer applies.
    setStage((s) => (s.name === "checking" || s.name === "verdict" ? edit(s) : s));
  };

  function fill(scenario: Scenario) {
    setForm((f) => formFor(scenario, f));
    setErrors({});
    pending.current = null;
    setStage({ name: "form" });
  }

  function handleError(error: unknown) {
    setProblem(error instanceof ApiError && error.code === "SETTINGS_REQUIRED" ? "settings" : "failed");
  }

  useEffect(() => {
    if (sceneFromUrl() !== null) void preview();
    // Once, on open: the deep link's example.
  }, []);

  async function check(event: FormEvent) {
    event.preventDefault();
    await preview();
  }

  async function preview() {
    const built = toEntry(form, crypto.randomUUID());
    if (!built.ok) {
      setErrors(built.errors);
      return;
    }
    setErrors({});
    setProblem(null);
    const id = built.entry.client_request_id;
    pending.current = id;
    setStage(startPreview(built.entry));
    try {
      const verdict = await previewInstallment(built.entry);
      setStage((s) => (s.name === "checking" ? answerPreview(s, id, verdict) : s));
    } catch (error) {
      // Only an error for the request still waited for is reported.
      if (pending.current === id) {
        handleError(error);
        setStage({ name: "form" });
      }
    }
  }

  async function record() {
    const entry = entryToRecord(stage.name === "verdict" ? stage : { name: "form" });
    if (entry === null) return;
    setProblem(null);
    setBusy(true);
    try {
      // Same entry, same client_request_id: a retry after a lost answer records once.
      setStage({ name: "recorded", result: await recordInstallment(entry) });
    } catch (error) {
      handleError(error);
    } finally {
      setBusy(false);
    }
  }

  function again() {
    setForm(emptyForm(new Date()));
    setStage({ name: "form" });
  }

  if (problem === "settings") return <SettingsMissing onSetUp={() => navigate("settings")} />;
  if (stage.name === "recorded") return <Recorded result={stage.result} onAgain={again} />;
  if (stage.name === "notBuying") {
    return (
      <Card className="flex flex-col gap-4">
        <Alert tone="ok" title={THINK.notBuyingDone} />
        <Button onClick={again} variant="secondary">
          {THINK.another}
        </Button>
        <Button onClick={() => navigate("home")} variant="ghost" icon="home">
          {THINK.backHome}
        </Button>
      </Card>
    );
  }

  return (
    <>
      <p className="text-body text-ink-muted">{THINK.intro}</p>
      <div className="flex flex-col gap-2 rounded-field border-2 border-dashed border-info-line bg-info-bg p-3">
        <span className="text-caption font-semibold text-info-ink">{THINK.demoTitle}</span>
        <div className="grid grid-cols-3 gap-2">
          {(["GREEN", "YELLOW", "RED"] as const).map((scenario) => (
            <button
              key={scenario}
              type="button"
              onClick={() => fill(scenario)}
              className="min-h-11 cursor-pointer rounded-pill border-2 border-info-line bg-card px-2 text-body font-semibold text-info-ink hover:bg-info-bg"
            >
              {THINK.demoScenario[scenario]}
            </button>
          ))}
        </div>
      </div>

      <form noValidate onSubmit={check} className="flex flex-col gap-4">
        <Card className="flex flex-col gap-5">
          <fieldset className="flex flex-col gap-2">
            <legend className="mb-2 text-body font-semibold text-ink">{THINK.kindTitle}</legend>
            <div className="grid grid-cols-3 gap-2">
              {KINDS.map((kind) => (
                <label
                  key={kind}
                  className={`flex min-h-12 cursor-pointer items-center justify-center rounded-field border-2 px-1 text-center text-body font-semibold ${
                    form.kind === kind ? "border-leaf-700 bg-leaf-50 text-leaf-800" : "border-line bg-card text-ink-muted"
                  }`}
                >
                  <input
                    type="radio"
                    name="kind"
                    checked={form.kind === kind}
                    onChange={() => set("kind", kind)}
                    className="sr-only"
                  />
                  {THINK.kinds[kind]}
                </label>
              ))}
            </div>
            {form.kind !== "purchase" && <p className="text-body text-ink-muted">{THINK.cashNoSaving}</p>}
          </fieldset>
          <Field
            label={THINK.itemName}
            value={form.name}
            onChange={(v) => set("name", v)}
            placeholder={THINK.itemNamePlaceholder}
            maxLength={100}
          />
          <Field
            label={form.kind === "purchase" ? THINK.price : THINK.cashAmount}
            value={form.price}
            onChange={(v) => set("price", v)}
            inputMode="decimal"
            suffix="บาท"
            placeholder="เช่น 12,000"
            error={errors.price ?? null}
          />
          <div className="grid grid-cols-2 gap-3">
            <Field
              label={THINK.months}
              value={form.months}
              onChange={(v) => set("months", v)}
              inputMode="numeric"
              suffix="เดือน"
              placeholder="เช่น 10"
              maxLength={3}
              error={errors.months ?? null}
            />
            <Field
              label={THINK.monthly}
              value={form.monthly}
              onChange={(v) => set("monthly", v)}
              inputMode="decimal"
              suffix="บาท"
              placeholder="เช่น 1,200"
              error={errors.monthly ?? null}
            />
          </div>
          <FirstDue value={form.firstDue} onChange={(v) => set("firstDue", v)} />
        </Card>
        {(stage.name === "form" || stage.name === "checking") && (
          <Button size="lg" type="submit" busy={stage.name === "checking"} icon="think">
            {stage.name === "checking" ? THINK.checking : THINK.check}
          </Button>
        )}
      </form>

      {problem === "failed" && <Alert tone="info" title={THINK.failed} />}

      {stage.name === "verdict" && (
        <>
          <VerdictCard verdict={stage.verdict.verdict} />
          <Card>
            <MonthBars months={stage.verdict.months} budget={settings.monthly_installment_budget} />
          </Card>
          <p className="text-center text-body text-ink-muted">
            {THINK.nowTotal(formatBaht(stage.verdict.monthly_total))}
          </p>
          <div className="grid grid-cols-2 gap-3">
            <Button variant="secondary" onClick={() => setStage({ name: "notBuying" })} disabled={busy}>
              {THINK.notBuying}
            </Button>
            <Button onClick={() => void record()} busy={busy}>
              {busy ? THINK.recording : THINK.record}
            </Button>
          </div>
        </>
      )}
    </>
  );
}

function FirstDue({ value, onChange }: { value: string; onChange: (v: string) => void }) {
  const next = addMonths(monthOf(new Date()), 1);
  const choices = Array.from({ length: FIRST_DUE_CHOICES }, (_, i) => addMonths(next, i));
  return (
    <label className="flex flex-col gap-1.5">
      <span className="text-body font-semibold text-ink">{THINK.firstDue}</span>
      <select
        value={value}
        onChange={(event) => onChange(event.target.value)}
        className="min-h-12 cursor-pointer rounded-field border-2 border-line bg-card px-4 text-lead text-ink focus:border-leaf-600"
      >
        {choices.map((month) => (
          <option key={month} value={month}>
            {thaiMonth(month)}
          </option>
        ))}
      </select>
    </label>
  );
}

function Recorded({ result, onAgain }: { result: RecordedOut; onAgain: () => void }) {
  const savedSomething = toSatang(result.saved_amount) > 0n;
  return (
    <>
      <Card className="flex flex-col items-center gap-3 py-8 text-center">
        <span className="inline-flex h-16 w-16 items-center justify-center rounded-pill bg-leaf-700 text-white">
          <Icon name="check" size={36} />
        </span>
        <h2 className="text-title font-bold text-ink">{THINK.savedTitle}</h2>
        <p className="text-body text-ink-muted">{THINK.newTotalLabel}</p>
        <p className="text-display font-bold text-ink">{formatBaht(result.monthly_total)}</p>
      </Card>
      <Card className="flex items-center gap-4">
        <span className="inline-flex h-12 w-12 items-center justify-center rounded-pill bg-leaf-50 text-leaf-700">
          <Icon name="shield" size={28} />
        </span>
        <div className="flex flex-col">
          <p className="text-body text-ink-muted">{savedSomething ? THINK.savedLabel : THINK.savedNothing}</p>
          {savedSomething && <p className="text-title font-bold text-ok-ink">{formatBaht(result.saved_amount)}</p>}
        </div>
      </Card>
      {result.warnings.verdict !== "GREEN" && <VerdictCard verdict={result.warnings.verdict} />}
      <Button onClick={() => navigate("home")} icon="home">
        {THINK.backHome}
      </Button>
      <Button onClick={onAgain} variant="secondary">
        {THINK.another}
      </Button>
    </>
  );
}
